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
from .education import education_joins, filter_description, has_filter, predicate
from .models import QueryPlan
from .security import audit, scope_ids

# V1 查询编译器：这些固定 SQL 片段是开发者白名单，不接受模型传入 SQL 表达式。
# V2 的结构化计划、字段和执行路径另见 v2/query.py 与 v2/superset_query.py。
DIMENSIONS = {
    "none": "'合计'",
    "division": "COALESCE(v.name,'公司管理层')",
    "department": "CASE WHEN d.level=4 THEN parent_d.name WHEN d.level=3 THEN d.name ELSE d.name||'（直属）' END",
    "team": "d.name",
    "education": "COALESCE(he.education_level,'未知')",
    "degree": "COALESCE(he.degree,'未知')",
    "school": "COALESCE(hs.name,'未知')",
    "quarter": "SUBSTR(f.event_day,1,4)||'-Q'||CAST((CAST(SUBSTR(f.event_day,6,2) AS INTEGER)+2)/3 AS INTEGER)",
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
    "department": "部门（含下属团队）",
    "team": "团队/任职组织",
    "education": "最高学历",
    "degree": "最高学位",
    "school": "最高学历毕业院校",
    "quarter": "季度",
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
    "weekend_overtime_hours",
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
    "employee_education",
    "schools",
    "aggregated",
    "buckets",
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
    elif plan.period in ("this_year", "last_year"):
        year = snapshot.year - (plan.period == "last_year")
        start, end = date(year, 1, 1), snapshot if plan.period == "this_year" else date(year, 12, 31)
    elif plan.period in ("this_quarter", "last_quarter"):
        quarter_start = snapshot.replace(month=((snapshot.month - 1) // 3) * 3 + 1, day=1)
        if plan.period == "this_quarter":
            start, end = quarter_start, snapshot
        else:
            end = quarter_start - timedelta(days=1)
            start = end.replace(month=((end.month - 1) // 3) * 3 + 1, day=1)
    elif plan.period in ("this_week", "last_week"):
        monday = snapshot - timedelta(days=snapshot.weekday())
        start, end = (
            (monday, snapshot)
            if plan.period == "this_week"
            else (monday - timedelta(days=7), monday - timedelta(days=1))
        )
    else:
        start, end = date.fromisoformat(plan.start_date), date.fromisoformat(plan.end_date)
    if start > end or end > snapshot or (end - start).days > 366:
        raise HTTPException(422, detail="请选择演示数据截止日以内、最长 366 天的有效期间。")
    return start.isoformat(), end.isoformat()


def department_ids(db, name):
    departments = rows(db, "SELECT id,name FROM departments")
    matches = [d for d in departments if d["name"] == name]
    if not matches:
        matches = [d for d in departments if name in d["name"]]
    if len(matches) != 1:
        raise HTTPException(422, detail="请使用一个明确的组织名称，或在组织页面选择范围。")
    return [
        r[0]
        for r in db.execute(
            "WITH RECURSIVE tree(id) AS (SELECT ? UNION ALL SELECT d.id FROM departments d JOIN tree t ON d.parent_id=t.id) SELECT id FROM tree",
            (matches[0]["id"],),
        )
    ]


def filtered_scope(principal, plan, db):
    # 先求权限集合，再与业务部门/人员筛选求交；“全公司”或同名搜索不能突破授权上限。
    ids = scope_ids(principal, plan.relation)
    if plan.department:
        depts = department_ids(db, plan.department)
        marks = ",".join("?" for _ in depts)
        matching = {
            r[0]
            for r in db.execute(
                f"SELECT employee_id FROM assignments WHERE department_id IN ({marks})", depts
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
    # 顺序很重要：验证指标能力与敏感限制 → 解读时间 → 求授权人群 → 拼白名单 SQL。
    # 用户值使用绑定参数；表名、维度、聚合表达式只能来自本模块定义。
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
            or has_filter(plan)
            or plan.education_scope != "highest"
            or plan.period not in ("as_of", "today", "this_month")
        ):
            raise HTTPException(
                403, detail="薪酬仅开放当前全授权范围或事业部汇总，不支持人员筛选、历史差分和明细。"
            )
    if plan.kind == "metric" and plan.dimension != "none" and plan.dimension not in m["dimensions"]:
        raise HTTPException(422, detail=f"{m['name']}暂不支持按{DIMENSION_LABELS[plan.dimension]}统计。")
    if (
        plan.kind == "people"
        and plan.metric not in ("headcount", "hires", "departures")
        or plan.kind == "attendance"
        and plan.metric not in ("abnormal_count", "late_count")
    ):
        raise HTTPException(422, detail="明细查询仅开放人员基本信息与考勤异常字段。")
    if plan.metric == "education_ratio" and not has_filter(plan):
        raise HTTPException(422, detail="教育背景占比需要指定学历、学位、学校或院校标签条件。")
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
    org_where = "1=1"
    if plan.department:
        org_ids = department_ids(db, plan.department)
        for i, ident in enumerate(org_ids):
            params[f"org{i}"] = ident
        org_where = "a.department_id IN (" + ",".join(f":org{i}" for i in range(len(org_ids))) + ")"
    for i, eid in enumerate(ids):
        params[f"s{i}"] = eid
    placeholders = ",".join(f":s{i}" for i in range(len(ids))) or "NULL"
    scope = f"scoped AS (SELECT * FROM employees WHERE id IN ({placeholders}))"
    if plan.kind == "people":
        point = (
            ":end"
            if plan.metric == "headcount"
            else "e.hire_date"
            if plan.metric == "hires"
            else "date(e.termination_date,'-1 day')"
        )
        employment = (
            "e.hire_date<=:end AND (e.termination_date IS NULL OR e.termination_date>:end)"
            if plan.metric == "headcount"
            else f"e.{'hire_date' if plan.metric == 'hires' else 'termination_date'} BETWEEN :start AND :end"
        )
        education_where = predicate(plan, db, params, point)
        matched_education = (
            "," + predicate(plan, db, params, point, detail=True) + " AS matching_education"
            if has_filter(plan)
            else ""
        )
        sql = f"""WITH {scope}
        SELECT e.employee_no,e.name,d.name AS department,p.name AS position,
          CASE WHEN a.manager_id IS NULL THEN '无上级' ELSE COALESCE(manager.name,'不在查看范围') END AS manager,e.employment_type,l.name AS location,e.hire_date,e.termination_date,
          CASE WHEN e.id=:viewer THEN '本人' WHEN rc.depth=1 THEN '直属下属' WHEN rc.depth>1 THEN '间接下属' ELSE '服务范围' END AS relation,
          he.education_level AS highest_education,he.degree AS highest_degree,hs.name AS graduation_school,he.major,he.graduation_date,he.study_mode AS education_mode{matched_education}
        FROM scoped e JOIN assignments a ON a.employee_id=e.id AND a.valid_from<={point} AND (a.valid_to IS NULL OR a.valid_to>{point})
        JOIN departments d ON d.id=a.department_id JOIN positions p ON p.id=a.position_id JOIN locations l ON l.id=e.location_id
        LEFT JOIN employees manager ON manager.id=a.manager_id AND manager.id IN ({placeholders})
        LEFT JOIN reporting_closure rc ON rc.descendant_id=e.id AND rc.ancestor_id=:viewer
        {education_joins(point)}
        WHERE {employment} AND {org_where} AND {education_where} ORDER BY e.id LIMIT :limit"""
        columns = [
            ("employee_no", "员工编号"),
            ("name", "姓名"),
            ("department", "任职组织"),
            ("position", "岗位"),
            ("manager", "直属上级"),
            ("employment_type", "用工类型"),
            ("location", "工作地"),
            ("hire_date", "入职日期"),
            ("termination_date", "离职日期"),
            ("relation", "关系"),
            ("highest_education", "最高学历"),
            ("highest_degree", "最高学位"),
            ("graduation_school", "最高学历毕业院校"),
            ("major", "专业"),
            ("graduation_date", "毕业日期"),
            ("education_mode", "学习形式"),
        ]
        if has_filter(plan):
            columns.append(("matching_education", "本次匹配的毕业经历"))
        return sql, params, columns, ids, metadata
    if plan.kind == "attendance":
        education_where = predicate(plan, db, params, "f.day")
        sql = f"""WITH {scope}
        SELECT e.employee_no AS employee_no,e.name AS name,d.name AS department,f.day AS day,f.status AS status,
        CASE WHEN f.check_in IS NULL THEN '未打卡' ELSE printf('%02d:%02d',f.check_in/60,f.check_in%60) END AS check_in,
        CASE WHEN f.check_out IS NULL THEN '未打卡' ELSE printf('%02d:%02d',f.check_out/60,f.check_out%60) END AS check_out,
        f.late_minutes AS late_minutes,f.early_minutes AS early_minutes
        FROM attendance_daily f JOIN scoped e ON e.id=f.employee_id
        JOIN assignments a ON a.employee_id=e.id AND a.valid_from<=f.day AND (a.valid_to IS NULL OR a.valid_to>f.day)
        JOIN departments d ON d.id=a.department_id WHERE f.day BETWEEN :start AND :end AND {org_where} AND {education_where}
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
    if plan.metric == "education_ratio" and plan.cohort != "active":
        field = "hire_date" if plan.cohort == "hires" else "termination_date"
        attr = "e.hire_date" if plan.cohort == "hires" else "date(e.termination_date,'-1 day')"
        fact = f"SELECT e.id AS employee_id,e.{field} AS event_day,{attr} AS attr_day,1 AS amount FROM scoped e WHERE e.{field} BETWEEN :start AND :end"
        expression = "COUNT(DISTINCT e.id)"
    elif plan.metric in ("headcount", "avg_tenure", "avg_salary", "education_ratio"):
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
    elif plan.metric == "workforce_changes":
        fact = """SELECT id AS employee_id,hire_date AS event_day,hire_date AS attr_day,1 AS hires,0 AS departures FROM scoped WHERE hire_date BETWEEN :start AND :end
        UNION ALL SELECT id,termination_date,date(termination_date,'-1 day'),0,1 FROM scoped WHERE termination_date BETWEEN :start AND :end"""
        expression = "COALESCE(SUM(f.hires),0)-COALESCE(SUM(f.departures),0)"
    elif plan.metric == "turnover_rate":
        fact = """SELECT id AS employee_id,:begin AS event_day,:begin AS attr_day,1 AS opening,0 AS closing,0 AS exits FROM scoped WHERE hire_date<=:begin AND (termination_date IS NULL OR termination_date>:begin)
        UNION ALL SELECT id,:end,:end,0,1,0 FROM scoped WHERE hire_date<=:end AND (termination_date IS NULL OR termination_date>:end)
        UNION ALL SELECT id,termination_date,date(termination_date,'-1 day'),0,0,1 FROM scoped WHERE termination_date BETWEEN :start AND :end"""
        expression = "ROUND(200.0*SUM(f.exits)/NULLIF(SUM(f.opening)+SUM(f.closing),0),2)"
    elif plan.metric in ("leave_days", "approved_overtime_hours", "weekend_overtime_hours"):
        source, amount = (
            ("leave_requests", "days")
            if plan.metric == "leave_days"
            else ("overtime_requests", "minutes/60.0")
        )
        fact = f"SELECT employee_id,day AS event_day,day AS attr_day,{amount} AS amount FROM {source} WHERE day BETWEEN :start AND :end AND approval_status='已批准'"
        if plan.metric == "weekend_overtime_hours":
            fact += " AND day_type='周末' AND strftime('%w',day) IN ('0','6')"
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
    education_where = predicate(plan, db, params, "f.attr_day")
    dim = DIMENSIONS[plan.dimension]
    group = "" if plan.dimension == "none" else "GROUP BY label"
    columns = [("label", DIMENSION_LABELS[plan.dimension]), ("value", m["name"]), ("sample_size", "涉及人数")]
    extra = ""
    where = f"{org_where} AND {education_where}"
    if plan.metric == "education_ratio":
        numerator = f"COUNT(DISTINCT CASE WHEN {education_where} THEN e.id END)"
        expression = f"ROUND(100.0*{numerator}/NULLIF(COUNT(DISTINCT e.id),0),2)"
        extra = f",{numerator} AS numerator,COUNT(DISTINCT e.id) AS denominator"
        where = org_where
        columns = [
            ("label", DIMENSION_LABELS[plan.dimension]),
            ("numerator", "符合条件人数"),
            (
                "denominator",
                {
                    "active": "在职总人数（分母）",
                    "hires": "期间入职人数（分母）",
                    "departures": "期间离职人数（分母）",
                }[plan.cohort],
            ),
            ("value", "占比（%）"),
        ]
    elif plan.metric == "workforce_changes":
        extra = ",COALESCE(SUM(f.hires),0) AS hires,COALESCE(SUM(f.departures),0) AS departures"
        columns = [
            ("label", DIMENSION_LABELS[plan.dimension]),
            ("hires", "入职人数"),
            ("departures", "离职人数"),
            ("value", "净增人数"),
        ]
    education_join = (
        education_joins("f.attr_day") if plan.dimension in ("education", "degree", "school") else ""
    )
    joins = f"""JOIN assignments a ON a.employee_id=e.id AND a.valid_from<=f.attr_day AND (a.valid_to IS NULL OR a.valid_to>f.attr_day)
    JOIN departments d ON d.id=a.department_id LEFT JOIN departments parent_d ON parent_d.id=d.parent_id LEFT JOIN departments v ON v.id=d.division_id
    JOIN positions p ON p.id=a.position_id JOIN job_families j ON j.id=p.family_id JOIN locations l ON l.id=e.location_id
    LEFT JOIN reporting_closure rc ON rc.descendant_id=e.id AND rc.ancestor_id=:viewer {education_join}"""
    aggregate = f"SELECT {dim} AS label,{expression} AS value,COUNT(DISTINCT e.id) AS sample_size{extra} FROM facts f JOIN scoped e ON e.id=f.employee_id {joins} WHERE {where} {group}"
    sql = f"WITH {scope}, facts AS ({fact}) {aggregate}"
    if plan.metric in ("workforce_changes", "weekend_overtime_hours") and plan.dimension in (
        "division",
        "department",
        "team",
    ):
        # Include authorized organization groups with no events; historic groups with events remain.
        buckets = f"""SELECT DISTINCT {dim} AS bucket_label FROM scoped e JOIN assignments a ON a.employee_id=e.id
        JOIN departments d ON d.id=a.department_id LEFT JOIN departments parent_d ON parent_d.id=d.parent_id LEFT JOIN departments v ON v.id=d.division_id
        WHERE a.valid_from<=:end AND (a.valid_to IS NULL OR a.valid_to>:start) AND e.hire_date<=:end AND (e.termination_date IS NULL OR e.termination_date>:start) AND {org_where}
        UNION SELECT label FROM aggregated"""
        extras = (
            ",COALESCE(a.hires,0) AS hires,COALESCE(a.departures,0) AS departures"
            if plan.metric == "workforce_changes"
            else ""
        )
        sql = f"WITH {scope}, facts AS ({fact}), aggregated AS ({aggregate}), buckets AS ({buckets}) SELECT b.bucket_label AS label,COALESCE(a.value,0) AS value,COALESCE(a.sample_size,0) AS sample_size{extras} FROM buckets b LEFT JOIN aggregated a ON a.label=b.bucket_label"
    sql += (
        " ORDER BY "
        + ("label" if plan.dimension in ("day", "month", "quarter", "relation") else "value DESC,label")
        + " LIMIT 400"
    )
    return sql, params, columns, ids, metadata


def execute(principal, plan: QueryPlan, record_audit=True):
    # 编译后仍设置 SQLite 表/函数 authorizer 与执行期限；不靠“模型答应只读”保证安全。
    # 最后做薪资小样本保护、摘要、审计；原始受限聚合不直接写入调试记录。
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
                "strftime",
                "group_concat",
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
            if plan.metric == "workforce_changes":
                summary = f"期间入职 {sum(row['hires'] for row in result)} 人、离职 {sum(row['departures'] for row in result)} 人，净增 {sum(row['value'] for row in result)} 人。内部调动不计入离职。"
            elif plan.kind == "metric":
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
            conditions = []
            if plan.department:
                conditions.append(f"组织：{plan.department}及下属组织，与当前权限取交集。")
            if has_filter(plan):
                conditions.append(filter_description(plan))
            if plan.metric == "education_ratio":
                conditions.append(
                    "分母为同组全部授权"
                    + {"active": "在职员工", "hires": "期间入职员工", "departures": "期间离职员工"}[
                        plan.cohort
                    ]
                    + "，不应用教育条件；未知教育背景也计入分母，分母为0返回空值。"
                )
            if plan.metric == "weekend_overtime_hours":
                conditions.append("周六、周日的已批准加班申请工时；未指定期间时默认本月。")
            if plan.dimension == "department":
                conditions.append("按三级部门汇总，包含下属团队；公司和事业部直属人员单列。")
            warnings.extend(conditions)
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
                "applied_conditions": conditions,
                "suppressed_groups": suppressed,
                "chart_type": "comparison"
                if plan.metric == "workforce_changes"
                else "line"
                if plan.dimension in ("month", "day", "quarter")
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
