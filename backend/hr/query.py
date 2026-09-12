"""Typed plans compile to allowlisted SQL; the model never executes SQL."""

import calendar
import sqlite3
import time
from datetime import date, timedelta

from fastapi import HTTPException

from . import config
from .catalog import metric
from .db import business, rows
from .debug import actor, step
from .models import QueryPlan
from .security import audit, scope_ids

DIMENSIONS = {
    "none": "'合计'",
    "division": "COALESCE(v.name,'公司管理层')",
    "department": "d.name",
    "job_family": "j.name",
    "location": "l.name",
    "employment_type": "e.employment_type",
    "relation": "CASE WHEN e.id=:viewer THEN '本人' WHEN rc.depth=1 THEN '直属下属' WHEN rc.depth>1 THEN '间接下属' ELSE '服务组织人员' END",
    "month": "SUBSTR(f.event_day,1,7)",
    "day": "f.event_day",
}
DIMENSION_LABELS = {
    "none": "范围",
    "division": "事业部",
    "department": "部门",
    "job_family": "岗位序列",
    "location": "工作地",
    "employment_type": "用工类型",
    "relation": "汇报关系",
    "month": "月份",
    "day": "日期",
}
ATTENDANCE_METRICS = {
    "attendance_rate",
    "late_count",
    "late_rate",
    "abnormal_count",
    "approved_overtime_hours",
    "late_departure_hours",
    "avg_work_hours",
    "leave_days",
}
READ_TABLES = {
    "employees",
    "assignments",
    "departments",
    "positions",
    "job_families",
    "locations",
    "reporting_closure",
    "attendance_daily",
    "overtime_requests",
    "leave_requests",
    "compensation",
    "facts",
    "scoped",
}


def period_bounds(plan: QueryPlan, as_of: str):
    snapshot = date.fromisoformat(as_of)
    if plan.period in ("as_of", "today"):
        start = end = snapshot
    elif plan.period == "this_month":
        start, end = snapshot.replace(day=1), snapshot
    elif plan.period == "last_month":
        end = snapshot.replace(day=1) - timedelta(days=1)
        start = end.replace(day=1)
    elif plan.period == "last_30_days":
        start, end = snapshot - timedelta(days=29), snapshot
    elif plan.period == "last_6_months":
        number = snapshot.year * 12 + snapshot.month - 1 - 5
        start, end = date(number // 12, number % 12 + 1, 1), snapshot
    else:
        start, end = date.fromisoformat(plan.start_date), date.fromisoformat(plan.end_date)
    if start > end or end > snapshot or (end - start).days > 366:
        raise HTTPException(422, detail="请选择演示数据截止日以内、最长 366 天的有效期间。")
    return start.isoformat(), end.isoformat()


def filtered_scope(principal, plan, db):
    ids = scope_ids(principal, plan.relation)
    if plan.department:
        departments = rows(db, "SELECT id,name FROM departments")
        matches = [d for d in departments if d["name"] == plan.department]
        if not matches:
            matches = [d for d in departments if plan.department in d["name"]]
        if len(matches) != 1:
            raise HTTPException(422, detail="请使用一个明确的组织名称，或在组织页面选择范围。")
        dept_ids = [
            r[0]
            for r in db.execute(
                "WITH RECURSIVE tree(id) AS (SELECT ? UNION ALL SELECT d.id FROM departments d JOIN tree t ON d.parent_id=t.id) SELECT id FROM tree",
                (matches[0]["id"],),
            )
        ]
        marks = ",".join("?" for _ in dept_ids)
        matching = {
            r[0]
            for r in db.execute(
                f"SELECT employee_id FROM assignments WHERE valid_to IS NULL AND department_id IN ({marks})",
                dept_ids,
            )
        }
        ids = sorted(set(ids) & matching)
        if not ids:
            raise HTTPException(
                403, detail="该查询范围不可用或超出当前身份授权。请查询自己的管理或服务范围。"
            )
    if plan.employee_name:
        marks = ",".join("?" for _ in ids) or "NULL"
        found = rows(
            db,
            f"SELECT id FROM employees WHERE id IN ({marks}) AND (name=? OR employee_no=?)",
            (*ids, plan.employee_name, plan.employee_name),
        )
        if len(found) > 1:
            raise HTTPException(422, detail="授权范围内存在同名员工，请使用员工编号。")
        if not found:
            raise HTTPException(403, detail="该人员不可用或不在当前授权范围内。")
        ids = [found[0]["id"]]
    return ids


def compile_query(principal, plan, db):
    if plan.kind in ("clarify", "refuse"):
        raise HTTPException(422, detail=plan.message or "请补充要查询的指标与范围。")
    m = metric(plan.metric)
    if plan.metric == "avg_salary":
        if not principal["salary_aggregate"]:
            raise HTTPException(
                403, detail="当前身份没有薪酬数据权限。你仍可查询授权范围内的人员与考勤指标。"
            )
        if (
            plan.kind != "metric"
            or plan.dimension not in ("none", "division")
            or plan.relation != "all"
            or plan.department
            or plan.employee_name
            or plan.period not in ("as_of", "today", "this_month")
        ):
            raise HTTPException(
                403, detail="薪酬仅开放当前全授权范围或事业部汇总，不支持人员筛选、历史差分和明细。"
            )
    if plan.kind == "metric" and plan.dimension != "none" and plan.dimension not in m["dimensions"]:
        raise HTTPException(422, detail=f"{m['name']}暂不支持按{DIMENSION_LABELS[plan.dimension]}统计。")
    if plan.kind != "metric" and plan.metric not in ("headcount", "abnormal_count", "late_count"):
        raise HTTPException(422, detail="明细查询仅开放人员基本信息与考勤异常字段。")
    metadata = dict(db.execute("SELECT key,value FROM dataset_meta"))
    start, end = period_bounds(plan, metadata["as_of"])
    if (plan.metric in ATTENDANCE_METRICS or plan.kind == "attendance") and start < metadata[
        "calendar_start"
    ]:
        raise HTTPException(422, detail=f"考勤数据从 {metadata['calendar_start']} 开始，请缩短时间范围。")
    ids = filtered_scope(principal, plan, db)
    params = {
        "start": start,
        "end": end,
        "begin": (date.fromisoformat(start) - timedelta(days=1)).isoformat(),
        "viewer": principal["employee_id"],
        "limit": plan.limit,
    }
    for i, eid in enumerate(ids):
        params[f"s{i}"] = eid
    placeholders = ",".join(f":s{i}" for i in range(len(ids))) or "NULL"
    scope = f"scoped AS (SELECT * FROM employees WHERE id IN ({placeholders}))"
    if plan.kind == "people":
        sql = f"""WITH {scope}
        SELECT e.employee_no AS employee_no,e.name AS name,d.name AS department,p.name AS position,
          CASE WHEN a.manager_id IS NULL THEN '无上级' ELSE COALESCE(manager.name,'不在查看范围') END AS manager,e.employment_type AS employment_type,l.name AS location,e.hire_date AS hire_date,
          CASE WHEN e.id=:viewer THEN '本人' WHEN rc.depth=1 THEN '直属下属' WHEN rc.depth>1 THEN '间接下属' ELSE '服务范围' END AS relation
        FROM scoped e JOIN assignments a ON a.employee_id=e.id AND a.valid_from<=:end AND (a.valid_to IS NULL OR a.valid_to>:end)
        JOIN departments d ON d.id=a.department_id JOIN positions p ON p.id=a.position_id JOIN locations l ON l.id=e.location_id
        LEFT JOIN employees manager ON manager.id=a.manager_id AND manager.id IN ({placeholders})
        LEFT JOIN reporting_closure rc ON rc.descendant_id=e.id AND rc.ancestor_id=:viewer
        WHERE e.hire_date<=:end AND (e.termination_date IS NULL OR e.termination_date>:end) ORDER BY e.id LIMIT :limit"""
        columns = [
            ("employee_no", "员工编号"),
            ("name", "姓名"),
            ("department", "部门"),
            ("position", "岗位"),
            ("manager", "直属上级"),
            ("employment_type", "用工类型"),
            ("location", "工作地"),
            ("hire_date", "入职日期"),
            ("relation", "关系"),
        ]
        return sql, params, columns, ids, metadata
    if plan.kind == "attendance":
        sql = f"""WITH {scope}
        SELECT e.employee_no AS employee_no,e.name AS name,d.name AS department,f.day AS day,f.status AS status,
        CASE WHEN f.check_in IS NULL THEN '未打卡' ELSE printf('%02d:%02d',f.check_in/60,f.check_in%60) END AS check_in,
        CASE WHEN f.check_out IS NULL THEN '未打卡' ELSE printf('%02d:%02d',f.check_out/60,f.check_out%60) END AS check_out,
        f.late_minutes AS late_minutes,f.early_minutes AS early_minutes
        FROM attendance_daily f JOIN scoped e ON e.id=f.employee_id
        JOIN assignments a ON a.employee_id=e.id AND a.valid_from<=f.day AND (a.valid_to IS NULL OR a.valid_to>f.day)
        JOIN departments d ON d.id=a.department_id WHERE f.day BETWEEN :start AND :end
        AND {"f.late_minutes>0" if plan.metric == "late_count" else "(f.late_minutes>0 OR f.early_minutes>0 OR f.status IN ('缺卡','缺勤'))"}
        ORDER BY f.day DESC,e.id LIMIT :limit"""
        columns = [
            ("employee_no", "员工编号"),
            ("name", "姓名"),
            ("department", "部门"),
            ("day", "日期"),
            ("status", "状态"),
            ("check_in", "上班"),
            ("check_out", "下班"),
            ("late_minutes", "迟到分钟"),
            ("early_minutes", "早退分钟"),
        ]
        return sql, params, columns, ids, metadata
    if plan.metric in ("headcount", "avg_tenure", "avg_salary"):
        points = [end]
        if plan.dimension == "month":
            points = []
            cursor = date.fromisoformat(start).replace(day=1)
            final = date.fromisoformat(end)
            while cursor <= final:
                points.append(
                    min(
                        final, cursor.replace(day=calendar.monthrange(cursor.year, cursor.month)[1])
                    ).isoformat()
                )
                cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
        for i, point in enumerate(points):
            params[f"p{i}"] = point
        dates = " UNION ALL ".join(f"SELECT :p{i} AS day" for i in range(len(points)))
        salary_join = (
            "JOIN compensation c ON c.employee_id=e.id AND c.valid_from<=t.day AND (c.valid_to IS NULL OR c.valid_to>t.day)"
            if plan.metric == "avg_salary"
            else ""
        )
        value = (
            "c.monthly_base"
            if plan.metric == "avg_salary"
            else "(julianday(t.day)-julianday(e.hire_date))/365.25"
            if plan.metric == "avg_tenure"
            else "1"
        )
        fact = f"""SELECT e.id AS employee_id,t.day AS event_day,t.day AS attr_day,{value} AS amount FROM scoped e CROSS JOIN ({dates}) t {salary_join}
        WHERE e.hire_date<=t.day AND (e.termination_date IS NULL OR e.termination_date>t.day)"""
        expression = "COUNT(DISTINCT e.id)" if plan.metric == "headcount" else "ROUND(AVG(f.amount),2)"
    elif plan.metric in ("hires", "departures"):
        field = "hire_date" if plan.metric == "hires" else "termination_date"
        attr = "e.hire_date" if plan.metric == "hires" else "date(e.termination_date,'-1 day')"
        fact = f"SELECT e.id AS employee_id,e.{field} AS event_day,{attr} AS attr_day,1 AS amount FROM scoped e WHERE e.{field} BETWEEN :start AND :end"
        expression = "COUNT(DISTINCT e.id)"
    elif plan.metric == "turnover_rate":
        fact = """SELECT id AS employee_id,:begin AS event_day,:begin AS attr_day,1 AS opening,0 AS closing,0 AS exits FROM scoped WHERE hire_date<=:begin AND (termination_date IS NULL OR termination_date>:begin)
        UNION ALL SELECT id,:end,:end,0,1,0 FROM scoped WHERE hire_date<=:end AND (termination_date IS NULL OR termination_date>:end)
        UNION ALL SELECT id,termination_date,date(termination_date,'-1 day'),0,0,1 FROM scoped WHERE termination_date BETWEEN :start AND :end"""
        expression = "ROUND(200.0*SUM(f.exits)/NULLIF(SUM(f.opening)+SUM(f.closing),0),2)"
    elif plan.metric in ("leave_days", "approved_overtime_hours"):
        source, amount = (
            ("leave_requests", "days")
            if plan.metric == "leave_days"
            else ("overtime_requests", "minutes/60.0")
        )
        fact = f"SELECT employee_id,day AS event_day,day AS attr_day,{amount} AS amount FROM {source} WHERE day BETWEEN :start AND :end AND approval_status='已批准'"
        expression = "ROUND(COALESCE(SUM(f.amount),0),2)"
    else:
        fact = "SELECT *,day AS event_day,day AS attr_day FROM attendance_daily WHERE day BETWEEN :start AND :end"
        expression = {
            "attendance_rate": "ROUND(100.0*SUM(CASE WHEN f.status IN ('正常','远程') THEN 1 ELSE 0 END)/NULLIF(SUM(CASE WHEN f.status<>'请假' THEN 1 ELSE 0 END),0),2)",
            "late_count": "COALESCE(SUM(CASE WHEN f.late_minutes>0 THEN 1 ELSE 0 END),0)",
            "late_rate": "ROUND(100.0*SUM(CASE WHEN f.late_minutes>0 THEN 1 ELSE 0 END)/NULLIF(COUNT(f.check_in),0),2)",
            "abnormal_count": "COALESCE(SUM(CASE WHEN f.late_minutes>0 OR f.early_minutes>0 OR f.status IN ('缺勤','缺卡') THEN 1 ELSE 0 END),0)",
            "late_departure_hours": "ROUND(COALESCE(SUM(f.late_departure_minutes),0)/60.0,2)",
            "avg_work_hours": "ROUND(AVG(CASE WHEN f.status IN ('正常','远程') AND f.check_in IS NOT NULL AND f.check_out IS NOT NULL THEN f.work_minutes/60.0 END),2)",
        }[plan.metric]
    dim = DIMENSIONS[plan.dimension]
    group = "" if plan.dimension == "none" else "GROUP BY label"
    sql = f"""WITH {scope}, facts AS ({fact})
    SELECT {dim} AS label,{expression} AS value,COUNT(DISTINCT e.id) AS sample_size
    FROM facts f JOIN scoped e ON e.id=f.employee_id
    JOIN assignments a ON a.employee_id=e.id AND a.valid_from<=f.attr_day AND (a.valid_to IS NULL OR a.valid_to>f.attr_day)
    JOIN departments d ON d.id=a.department_id LEFT JOIN departments v ON v.id=d.division_id
    JOIN positions p ON p.id=a.position_id JOIN job_families j ON j.id=p.family_id JOIN locations l ON l.id=e.location_id
    LEFT JOIN reporting_closure rc ON rc.descendant_id=e.id AND rc.ancestor_id=:viewer
    {group} ORDER BY {"label" if plan.dimension in ("day", "month", "relation") else "value DESC,label"} LIMIT 400"""
    return (
        sql,
        params,
        [("label", DIMENSION_LABELS[plan.dimension]), ("value", m["name"]), ("sample_size", "涉及人数")],
        ids,
        metadata,
    )


def execute(principal, plan: QueryPlan, record_audit=True):
    started = time.perf_counter()
    try:
        with business() as db:
            with step(
                "compile", "权限校验与 SQL 编译", {"plan": plan.model_dump(), "actor": actor(principal)}
            ) as trace:
                sql, params, columns, ids, metadata = compile_query(principal, plan, db)
                trace.update(
                    sql=sql,
                    parameters=params,
                    columns=columns,
                    filtered_employee_ids=ids,
                    candidate_count=len(ids),
                    dataset=metadata,
                )
            deadline = time.monotonic() + 2.0
            db.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
            # A second database-layer check: allowlisted reads/functions only.
            functions = {
                "count",
                "sum",
                "avg",
                "round",
                "coalesce",
                "nullif",
                "julianday",
                "date",
                "substr",
                "printf",
            }

            def authorize(action, arg1, arg2, database, trigger):
                if action == sqlite3.SQLITE_READ:
                    return (
                        sqlite3.SQLITE_OK
                        if arg1 in READ_TABLES
                        and (
                            arg1 != "compensation"
                            or principal["salary_aggregate"]
                            and plan.metric == "avg_salary"
                        )
                        else sqlite3.SQLITE_DENY
                    )
                if action == sqlite3.SQLITE_FUNCTION:
                    return sqlite3.SQLITE_OK if arg2 in functions else sqlite3.SQLITE_DENY
                if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_RECURSIVE):
                    return sqlite3.SQLITE_OK
                return sqlite3.SQLITE_DENY

            db.set_authorizer(authorize)
            with step(
                "database",
                "执行只读 SQL",
                {
                    "sql": sql,
                    "parameters": params,
                    "guards": {"query_only": True, "deadline_seconds": 2, "read_tables": sorted(READ_TABLES)},
                },
            ) as trace:
                result = rows(db, sql, params)
                trace.update(
                    row_count=len(result),
                    rows=result if plan.metric != "avg_salary" else None,
                    capture_note="薪酬原始聚合不写入调试记录，请查看保护后的结果。"
                    if plan.metric == "avg_salary"
                    else "数据库返回的授权内结果。",
                )
        with step(
            "protection",
            "聚合保护与空值处理",
            {"metric": plan.metric, "row_count": len(result), "minimum_salary_group": 5},
        ) as trace:
            definition = metric(plan.metric)
            suppressed = 0
            if plan.metric == "avg_salary":
                for row in result:
                    if row["sample_size"] < 5:
                        row["value"] = None
                        row["sample_size"] = None
                        row["protected"] = True
                        suppressed += 1
            if plan.metric == "avg_salary" and suppressed == 1:
                # Complementary suppression prevents reconstructing the hidden group
                # using the overall average and the other groups' known headcounts.
                eligible = [row for row in result if not row.get("protected")]
                if eligible:
                    secondary = min(eligible, key=lambda row: row["sample_size"])
                    secondary.update(value=None, sample_size=None, protected=True)
                    suppressed += 1
            if plan.kind == "metric" and not result:
                if plan.dimension == "none":
                    result = [{"label": "合计", "value": None, "sample_size": 0}]
            trace.update(rows=result, row_count=len(result), suppressed_groups=suppressed)
        with step(
            "format",
            "格式化结果与统计口径",
            {"plan": plan.model_dump(), "definition": definition, "rows": result},
        ) as trace:
            duration = round((time.perf_counter() - started) * 1000, 2)
            if plan.kind == "metric":
                summary = (
                    f"已按{DIMENSION_LABELS[plan.dimension]}统计{definition['name']}，共 {len(result)} 组。"
                    if plan.dimension != "none"
                    else f"{definition['name']}为 {result[0]['value'] if result and result[0]['value'] is not None else '暂无可展示结果'}{definition['unit'] if result and result[0]['value'] is not None else ''}。"
                )
            else:
                summary = f"已找到 {len(result)} 条授权范围内的{'人员' if plan.kind == 'people' else '考勤异常'}记录。"
            warnings = [
                "所有数据均为合成数据；“今天”以演示数据截止日为准。",
                "历史人员范围按当前授权关系确定，组织分组按业务发生时任职记录归属。",
            ]
            if plan.metric in ATTENDANCE_METRICS or plan.kind == "attendance":
                warnings.append("演示日历仅采用周一至周五，不代表实际法定节假日安排。")
            if suppressed:
                warnings.append("少于 5 人的薪酬分组及必要的互补分组已隐藏，避免结合总计反推个人薪酬。")
            if plan.kind != "metric" and len(result) == plan.limit:
                warnings.append(f"明细最多显示 {plan.limit} 条，请缩小范围查看其他记录。")
            output = {
                "status": "success",
                "summary": summary,
                "rows": result,
                "columns": [{"key": k, "label": v} for k, v in columns],
                "plan": plan.model_dump(),
                "metric": definition,
                "period": {"start": params["start"], "end": params["end"]},
                "scope": {
                    "count": len(ids),
                    "label": "当前身份授权范围",
                    "policy_version": f"{config.POLICY_VERSION}:{principal['policy_version']}",
                },
                "as_of": metadata["as_of"],
                "catalog_version": config.CATALOG_VERSION,
                "sql": sql,
                "sql_parameter_count": len(params),
                "duration_ms": duration,
                "warnings": warnings,
                "suppressed_groups": suppressed,
                "chart_type": "line"
                if plan.dimension in ("month", "day")
                else "bar"
                if plan.kind == "metric" and plan.dimension != "none"
                else "table",
            }
            trace.update(output)
        if record_audit:
            with step(
                "audit",
                "写入查询审计",
                {
                    "principal_id": principal["id"],
                    "metric": plan.metric,
                    "scope_count": len(ids),
                    "outcome": "allowed",
                    "duration_ms": duration,
                },
            ) as trace:
                audit(principal, "query", "allowed", plan.metric, len(ids), duration)
                trace.update(written=True)
        return output
    except HTTPException:
        if record_audit:
            audit(
                principal, "query", "denied", plan.metric, duration_ms=(time.perf_counter() - started) * 1000
            )
        raise
    except sqlite3.Error as exc:
        audit(principal, "query", "error", plan.metric, duration_ms=(time.perf_counter() - started) * 1000)
        raise HTTPException(422, detail="查询被执行边界中止，请缩小范围或选择支持的指标。") from exc
