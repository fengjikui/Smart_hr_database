"""复用白名单计划编译，替换 PostgreSQL 方言，并经受控 RLS 视图查询。

本模块从不接受用户 SQL。字段/排序/聚合仍由 query.validate 做完整依赖校验；
授权名单来自 OpenFGA，查询条件不能通过 OR 等字符串拼接扩大该名单。
"""

import re
import time
from decimal import Decimal

from . import openfga_source as source
from . import query


class Compiler(query.Compiler):
    def expr(self, field, alias="p"):
        if field == "age":
            return f"CASE WHEN {alias}.birth_date IS NOT NULL THEN EXTRACT(YEAR FROM age(CAST(:snapshot AS date),CAST({alias}.birth_date AS date)))::integer END"
        return super().expr(field, alias)

    def condition(self, f):
        if f.op == "contains":
            return f"position({self.bind(f.values[0])} in {self.expr(f.field)})>0"
        return super().condition(f)

    def metric(self, name):
        if name == "avg_confirmation_days":
            value = "CASE WHEN p.confirmation_date>=p.onboard_date AND p.confirmation_date<=:snapshot THEN CAST(p.confirmation_date AS date)-CAST(p.onboard_date AS date) END"
            return [(name, f"ROUND(AVG({value}),2)"), (name + "_sample_size", f"COUNT({value})")]
        return super().metric(name)

    def compile(self):
        # 所有 :name 都由编译器产生，用户值只在 params 中，不对用户字符串做替换。
        return tuple(
            re.sub(r"(?<!:):([a-z][a-z0-9_]*)", r"%(\1)s", value) if value else None
            for value in super().compile()
        )


def normalized(row):
    return {k: float(v) if isinstance(v, Decimal) else v for k, v in row.items()}


def execute(p, plan):
    started = time.perf_counter()
    snap = source.snapshot(p, refresh=True)
    compiler = Compiler(p, plan)
    sql, totals_sql, domain_sql = compiler.compile()
    with source.database(snap) as conn:
        rows = [normalized(r) for r in conn.execute(sql, compiler.params)]
        totals = normalized(conn.execute(totals_sql, compiler.params).fetchone())
        if domain_sql:
            departments = [r["dept_cn_name"] for r in conn.execute(domain_sql, compiler.params)]
            rows = query.fill_zeros(rows, plan, departments)
        if plan.kind == "aggregate":
            rows = query.order_rows(rows, plan)
    result = query.format_result(compiler, sql, rows, totals, started)
    result.update(execution_backend="openfga", source_queries=snap["source_queries"])
    result["notes"].append("OpenFGA 决定授权；PostgreSQL RLS 视图执行筛选；服务账号仅供可信后端。")
    return result
