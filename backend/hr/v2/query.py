"""Allowlisted SQL compiler; no model-written SQL is accepted."""

import itertools
import sqlite3
import time
from datetime import date, timedelta

from fastapi import HTTPException

from . import auth, store
from .schema import DIMENSIONS, FIELDS, LEVELS, METRICS, SCHOOLS


def dependencies(plan):
    fields = set(plan.columns if plan.kind == "people" else [])
    if plan.population == "confirmed":
        fields.update(["formalize_flag", "confirmation_date"])
    fields.update(f.field for f in plan.filters)
    fields.update(d for d in plan.group_by if d in FIELDS)
    for d in plan.group_by:
        if d.endswith("_month") and d != "event_month":
            fields.add(
                {
                    "onboard_month": "onboard_date",
                    "termin_month": "termin_date",
                    "confirmation_month": "confirmation_date",
                }[d]
            )
    if plan.kind == "aggregate":
        for m in plan.metrics:
            fields.update(METRICS[m][2])
    fields.update(o.field for o in plan.order_by if o.field in FIELDS)
    if plan.date_field:
        fields.update(
            ["onboard_date", "termin_date"] if plan.date_field == "employment_events" else [plan.date_field]
        )
    return fields


def validate(p, plan):
    auth.refresh(p)
    if plan.kind not in ("people", "aggregate"):
        raise HTTPException(422, plan.message or "请完善问题")
    if not dependencies(plan) <= auth.allowed_fields(p):
        raise HTTPException(403, "当前角色没有这些字段或指标的权限")
    if plan.kind == "people" and not store.policy()["roles"][p["role"]]["details"]:
        raise HTTPException(403, "当前角色未开放明细查询")
    if plan.date_field and plan.date_field != "contract_end_date" and plan.end_date > store.AS_OF:
        raise HTTPException(422, "该事实日期不能晚于数据截止日；合同到期可查询未来")
    if plan.date_field == "employment_events" and plan.kind == "people":
        raise HTTPException(422, "入离职组合用于聚合，人员明细请明确入职或离职日期")
    if "event_month" in plan.group_by and plan.date_field != "employment_events":
        raise HTTPException(422, "事件月份需入离职组合期间")
    for dim, field in [
        ("onboard_month", "onboard_date"),
        ("termin_month", "termin_date"),
        ("confirmation_month", "confirmation_date"),
    ]:
        if dim in plan.group_by and plan.date_field != field:
            raise HTTPException(422, "月份分组必须与期间字段一致")
    if plan.date_field == "employment_events" and any(
        m not in ("hires", "departures", "net_change", "count") for m in plan.metrics
    ):
        raise HTTPException(422, "组合事件统计只支持人数、入职、离职和净增；其他指标请单独查询")
    if plan.population != "all" and any(m in ("hires", "departures", "net_change") for m in plan.metrics):
        raise HTTPException(422, "入离职指标必须使用全部状态，避免漏掉目前已离职的员工")
    ids, grant = auth.scoped(p, plan.scope)
    if plan.departments:
        rows = store.people()
        accessible = {r["dept_cn_name"] for r in rows if r["person_id"] in ids}
        if not set(plan.departments) <= accessible:
            raise HTTPException(403, "所选部门不可用或超出当前授权范围")
    for f in plan.filters:
        if f.field == "age":
            if f.op == "contains":
                raise HTTPException(422, "年龄只支持数值比较，不能使用包含")
            try:
                if any(not 0 <= int(v) <= 120 for v in f.values):
                    raise ValueError()
            except ValueError as exc:
                raise HTTPException(422, "年龄需为0至120的整数") from exc
        if f.field.endswith("_date") and f.op != "not_null":
            try:
                for v in f.values:
                    date.fromisoformat(v)
            except ValueError as exc:
                raise HTTPException(422, "日期请使用YYYY-MM-DD") from exc
        if f.field == "diploma_code_desc" and f.op in ("gte", "lte") and f.values[0] not in LEVELS:
            raise HTTPException(422, "学历范围请使用已定义的学历名称")
    valid_order = (
        set(plan.columns) | set(FIELDS) if plan.kind == "people" else set(plan.group_by) | set(plan.metrics)
    )
    if any(o.field not in valid_order for o in plan.order_by):
        raise HTTPException(422, "排序字段不属于本次结果")
    if plan.kind == "people" and plan.group_by:
        raise HTTPException(422, "明细查询不使用分组，请切换统计模式")
    return ids, grant


def months(start, end):
    cursor = date.fromisoformat(start).replace(day=1)
    stop = date.fromisoformat(end)
    result = []
    while cursor <= stop:
        result.append(cursor.strftime("%Y-%m"))
        cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
    return result


class Compiler:
    def __init__(self, p, plan):
        self.p, self.plan = p, plan
        self.ids, self.grant = validate(p, plan)
        self.params = {"snapshot": store.AS_OF, "start": plan.start_date, "end": plan.end_date}
        self.serial = 0

    def bind(self, value):
        self.serial += 1
        key = f"v{self.serial}"
        self.params[key] = value
        return ":" + key

    def listing(self, values):
        return ",".join(self.bind(v) for v in values) or "NULL"

    def expr(self, field, alias="p"):
        if field == "age":
            return f"CASE WHEN {alias}.birth_date IS NOT NULL THEN CAST(strftime('%Y',:snapshot) AS INTEGER)-CAST(strftime('%Y',{alias}.birth_date) AS INTEGER)-(strftime('%m-%d',:snapshot)<strftime('%m-%d',{alias}.birth_date)) END"
        if field == "relation":
            direct = [eid for eid in self.ids if self.grant["depths"].get(eid) == 1]
            indirect = [eid for eid in self.ids if self.grant["depths"].get(eid, 0) >= 2]
            return f"CASE WHEN {alias}.person_id={self.bind(self.p['person_id'])} THEN '本人' WHEN {alias}.person_id IN ({self.listing(direct)}) THEN '直属下属' WHEN {alias}.person_id IN ({self.listing(indirect)}) THEN '间接下属' ELSE 'HRBP服务人员' END"
        if field.endswith("_month"):
            source = {
                "event_month": "event_day",
                "onboard_month": "onboard_date",
                "termin_month": "termin_date",
                "confirmation_month": "confirmation_date",
            }[field]
            return f"COALESCE(substr({alias}.{source},1,7),'未知')"
        return f'{alias}."{field}"'

    def condition(self, f):
        expr = self.expr(f.field)
        values = f.values
        if f.field == "diploma_code_desc" and f.op in ("gte", "lte"):
            expr = "CASE " + expr + " " + " ".join(f"WHEN '{k}' THEN {v}" for k, v in LEVELS.items()) + " END"
            values = [LEVELS[v] for v in values]
        elif f.field == "age":
            values = [int(v) for v in values]
        if f.op == "not_null":
            return f"{expr} IS NOT NULL"
        if f.op == "in":
            return f"{expr} IN ({self.listing(values)})"
        if f.op == "contains":
            return f"instr({expr},{self.bind(values[0])})>0"
        op = {"eq": "=", "gte": ">=", "lte": "<="}[f.op]
        return f"{expr}{op}{self.bind(values[0])}"

    def base(self):
        plan = self.plan
        conditions = [f"p.person_id IN ({self.listing(self.ids)})"]
        if plan.departments:
            conditions.append(f"p.dept_cn_name IN ({self.listing(plan.departments)})")
        if plan.population == "active":
            conditions.append(
                "p.onboard_date<=:snapshot AND (p.termin_date IS NULL OR p.termin_date>:snapshot)"
            )
        if plan.population == "confirmed":
            conditions.append("p.formalize_flag='是' AND p.confirmation_date<=:snapshot")
        conditions.extend(self.condition(f) for f in plan.filters)
        base = "SELECT p.* FROM people p WHERE " + " AND ".join(conditions)
        if plan.date_field == "employment_events":
            facts = "SELECT b.*,onboard_date AS event_day,1 AS is_hire,0 AS is_exit FROM base b WHERE onboard_date BETWEEN :start AND :end UNION ALL SELECT b.*,termin_date,0,1 FROM base b WHERE termin_date BETWEEN :start AND :end"
        else:
            cond = f'WHERE "{plan.date_field}" BETWEEN :start AND :end' if plan.date_field else ""
            facts = f"SELECT b.*,NULL AS event_day,CASE WHEN onboard_date BETWEEN :start AND :end THEN 1 ELSE 0 END AS is_hire,CASE WHEN termin_date BETWEEN :start AND :end THEN 1 ELSE 0 END AS is_exit FROM base b {cond}"
        return f"WITH base AS ({base}), facts AS ({facts}) "

    def metric(self, name):
        predicates = {
            "masters": "p.diploma_code_desc IN ('硕士研究生','博士研究生')",
            "doctors": "p.degree_code_desc='博士' AND p.education_expired_date<=:snapshot",
            "outsource": "p.labour_type_code_desc='外包'",
            "school_985": f"p.school_name IN ({self.listing([s for s, v in SCHOOLS.items() if v[0]])})",
            "school_211": f"p.school_name IN ({self.listing([s for s, v in SCHOOLS.items() if v[1]])})",
        }
        count = "COUNT(DISTINCT p.person_id)"
        if name == "count":
            return [(name, count)]
        if name == "hires":
            return [(name, "COALESCE(SUM(p.is_hire),0)")]
        if name == "departures":
            return [(name, "COALESCE(SUM(p.is_exit),0)")]
        if name == "net_change":
            return [(name, "COALESCE(SUM(p.is_hire),0)-COALESCE(SUM(p.is_exit),0)")]
        if name in ("avg_age", "avg_confirmation_days"):
            value = (
                self.expr("age")
                if name == "avg_age"
                else "CASE WHEN p.confirmation_date>=p.onboard_date AND p.confirmation_date<=:snapshot THEN julianday(p.confirmation_date)-julianday(p.onboard_date) END"
            )
            return [(name, f"ROUND(AVG({value}),2)"), (name + "_sample_size", f"COUNT({value})")]
        key = name.removesuffix("_count").removesuffix("_ratio")
        numerator = f"COUNT(DISTINCT CASE WHEN {predicates[key]} THEN p.person_id END)"
        if name.endswith("_count"):
            return [(name, numerator)]
        return [
            (name, f"ROUND(100.0*{numerator}/NULLIF({count},0),2)"),
            (name + "_numerator", numerator),
            (name + "_denominator", count),
        ]

    def compile(self):
        prefix = self.base()
        plan = self.plan
        if plan.kind == "people":
            projections = [f'{self.expr(c)} AS "{c}"' for c in plan.columns]
            sql = prefix + "SELECT " + ",".join(projections) + " FROM facts p"
            ordering = plan.order_by or []
            order = []
            for o in ordering:
                expression = self.expr(o.field)
                order.extend([f"({expression} IS NULL) ASC", f"{expression} {o.direction.upper()}"])
            order.append("p.person_id ASC")
            sql += " ORDER BY " + ",".join(order)
            count_sql = prefix + "SELECT COUNT(*) AS count FROM facts p"
            return sql, count_sql, None
        pairs = [item for m in plan.metrics for item in self.metric(m)]
        projections = [f'{expr} AS "{key}"' for key, expr in pairs]
        dimensions = [f"COALESCE({self.expr(d)},'未知') AS \"{d}\"" for d in plan.group_by]
        sql = prefix + "SELECT " + ",".join(dimensions + projections) + " FROM facts p"
        if plan.group_by:
            sql += " GROUP BY " + ",".join('"' + d + '"' for d in plan.group_by)
        total_sql = prefix + "SELECT " + ",".join(projections) + " FROM facts p"
        domain_sql = prefix + "SELECT DISTINCT p.dept_cn_name FROM base p"
        return sql, total_sql, domain_sql


def order_rows(rows, plan):
    # Stable default ordering; explicit sorts retain deterministic group tie breaks.
    ordered = sorted(rows, key=lambda r: tuple(str(r.get(k, "")) for k in plan.group_by))
    for o in reversed(plan.order_by):
        present = [r for r in ordered if r.get(o.field) is not None]
        absent = [r for r in ordered if r.get(o.field) is None]
        ordered = sorted(present, key=lambda r: r[o.field], reverse=o.direction == "desc") + absent
    return ordered


def fill_zeros(rows, plan, departments):
    if not plan.group_by or not plan.start_date or not any(d.endswith("_month") for d in plan.group_by):
        return rows
    if any(d != "dept_cn_name" and not d.endswith("_month") for d in plan.group_by):
        return rows
    domains = [
        departments if d == "dept_cn_name" else months(plan.start_date, plan.end_date) for d in plan.group_by
    ]
    current = {tuple(r[d] for d in plan.group_by) for r in rows}
    for values in itertools.product(*domains):
        if values in current:
            continue
        r = dict(zip(plan.group_by, values, strict=True))
        for m in plan.metrics:
            r[m] = None if m.startswith("avg_") or m.endswith("_ratio") else 0
            if m.startswith("avg_"):
                r[m + "_sample_size"] = 0
            if m.endswith("_ratio"):
                r.update({m + "_numerator": 0, m + "_denominator": 0})
        rows.append(r)
    return rows


def execute(p, plan):
    started = time.perf_counter()
    c = Compiler(p, plan)
    sql, total_sql, domain_sql = c.compile()
    with store.connection("people", True) as db:
        deadline = time.monotonic() + 2
        db.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        functions = {
            "strftime",
            "substr",
            "coalesce",
            "count",
            "sum",
            "round",
            "avg",
            "julianday",
            "nullif",
            "instr",
        }

        def authorizer(action, table, column, database, trigger):
            if action == sqlite3.SQLITE_READ:
                return sqlite3.SQLITE_OK if table == "people" else sqlite3.SQLITE_DENY
            if action == sqlite3.SQLITE_FUNCTION:
                return sqlite3.SQLITE_OK if column in functions else sqlite3.SQLITE_DENY
            if action == sqlite3.SQLITE_SELECT:
                return sqlite3.SQLITE_OK
            return sqlite3.SQLITE_DENY

        db.set_authorizer(authorizer)
        rows = [dict(r) for r in db.execute(sql, c.params)]
        totals = dict(db.execute(total_sql, c.params).fetchone())
        if domain_sql:
            departments = [r[0] for r in db.execute(domain_sql, c.params)]
            rows = fill_zeros(rows, plan, departments)
        if plan.kind == "aggregate":
            rows = order_rows(rows, plan)
    count = len(rows)
    all_rows = rows
    rows = rows[(plan.page - 1) * plan.page_size : plan.page * plan.page_size]
    columns = (
        [{"key": f, "label": FIELDS[f][0]} for f in plan.columns]
        if plan.kind == "people"
        else [{"key": d, "label": DIMENSIONS[d]} for d in plan.group_by]
    )
    if plan.kind == "aggregate":
        for m in plan.metrics:
            columns.append({"key": m, "label": METRICS[m][0] + f"（{METRICS[m][1]}）"})
            if m.endswith("_ratio"):
                columns.extend(
                    [
                        {"key": m + "_numerator", "label": "符合人数 · " + METRICS[m][0]},
                        {"key": m + "_denominator", "label": "分母 · " + METRICS[m][0]},
                    ]
                )
            if m.startswith("avg_"):
                columns.append({"key": m + "_sample_size", "label": "有效样本 · " + METRICS[m][0]})
    return {
        "status": "success",
        "plan": plan.model_dump(),
        "rows": rows,
        "columns": columns,
        "total_rows": count,
        "totals": totals,
        "page": plan.page,
        "page_size": plan.page_size,
        "sql": sql,
        "parameters": c.params,
        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        "as_of": store.AS_OF,
        "scope_count": len(c.ids),
        "policy_version": c.grant["policy_version"],
        "notes": [
            "合成数据；关系与字段解释是可调整的演示假设。",
            "组织归属采用当前部门，未重建历史任职。",
            "学校与学历取宽表当前教育记录；毕业日期映射为演示假设。",
        ],
        "_all_rows": all_rows,
    }
