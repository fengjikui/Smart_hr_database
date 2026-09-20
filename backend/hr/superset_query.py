"""把 当前受限查询计划交给 Superset 执行，保留 PostgreSQL 的真实 SQL。

这里不是第二套行权限引擎：查询中没有 Python 算出的授权人员 ID 清单。
当前登录人的数据范围由 Superset 数据集上的 RLS 限制，PostgreSQL 在该
范围内完成筛选和聚合。这里仅翻译用户的问题，例如“直属下属”“按部门统计”。

允许的 SQL 表达式完全来自本文件的固定模板和 schema 白名单。模型只能提交
Plan，不能提交任意 SQL、子查询或临时数据集。字符串按 PostgreSQL 字面量
转义；SQL 最外层的 SELECT / FROM / RLS / GROUP BY 由 Superset 生成。
"""

import time

from fastapi import HTTPException

from . import query, store
from .schema import DIMENSIONS, FIELDS, LEVELS, METRICS, SCHOOLS, Plan

# 演示数据共 300 人，事件最多 600 行。多取一行用于检测上限，不能把截断的
# 结果冒充完整统计。扩容时应改成服务端分页协议，不应只把这里改成无限大。
RESULT_LIMIT = 1001


def literal(value):
    """将受限 Plan 中的标量编码成 PostgreSQL SQL 字面量，而非 SQL 代码。"""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(value)
    if not isinstance(value, str) or "\x00" in value:
        raise HTTPException(422, "查询条件包含不支持的值")
    # 使用 E 字符串并同时转义反斜线和单引号，不依赖连接的
    # standard_conforming_strings 设置；引号中的分号仍只是普通文本。
    return "E'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


def listing(values):
    return ", ".join(literal(value) for value in values) or "NULL"


def sql_expression(label, expression):
    """Superset QueryObject 支持的显式 SQL 指标/维度格式。"""
    return {"expressionType": "SQL", "label": label, "sqlExpression": expression}


class Compiler:
    """保持 当前指标口径，仅将 SQLite 表达式换成 PostgreSQL 表达式。"""

    def __init__(self, p, plan, snapshot):
        # 即使内部调用者用 model_construct 跳过 Pydantic，仍再次校验白名单。
        self.plan = Plan.model_validate(plan.model_dump())
        self.p = p
        self.snapshot = snapshot
        self.ids, self.grant = query.validate(p, self.plan)
        required = query.dependencies(self.plan)
        if not required <= set(snapshot["fields"]):
            raise HTTPException(403, "当前 Superset 角色没有这些字段或指标的权限")
        contract = any(FIELDS[field][1] == "contract" for field in required)
        self.dataset_key = ("events" if plan.date_field == "employment_events" else "people") + (
            "_contract" if contract else "_public"
        )
        self.params = {
            "snapshot": store.AS_OF,
            "start": plan.start_date,
            "end": plan.end_date,
            "scope": plan.scope,
            "departments": list(plan.departments),
            "filters": [f.model_dump() for f in plan.filters],
        }

    def expr(self, field):
        if field not in FIELDS and field not in DIMENSIONS:
            raise HTTPException(422, "字段不在查询白名单中")
        # age / relation / 各种月份是 PostgreSQL 已注册视图的列，不能通过
        # 请求参数换成其他表或任意 SQL。年龄按同一个固定数据截止日计算。
        return '"' + field + '"'

    def condition(self, filt):
        expression, values = self.expr(filt.field), filt.values
        if filt.field == "diploma_code_desc" and filt.op in ("gte", "lte"):
            expression = (
                "CASE " + expression + " "
                + " ".join(f"WHEN {literal(name)} THEN {level}" for name, level in LEVELS.items())
                + " END"
            )
            values = [LEVELS[value] for value in values]
        elif filt.field == "age":
            values = [int(value) for value in values]
        if filt.op == "not_null":
            return f"{expression} IS NOT NULL"
        if filt.op == "in":
            return f"{expression} IN ({listing(values)})"
        if filt.op == "contains":
            # strpos 与 SQLite instr 一样按字面包含，百分号/下划线不是通配符。
            return f"strpos({expression}, {literal(values[0])}) > 0"
        operator = {"eq": "=", "gte": ">=", "lte": "<="}[filt.op]
        return f"{expression} {operator} {literal(values[0])}"

    def where(self, include_period=True):
        plan = self.plan
        # 这些条件只能缩小 RLS 已授权的集合。例如 _reports=true 并不能让
        # 当前人看到其他管理者的下属，因为 Superset 还会附加当前用户 RLS。
        scope = {
            "all": "TRUE",
            "self": f'"person_id" = {literal(self.p["person_id"])}',
            "reports": '"_reports" IS TRUE',
            "direct": '"_reports" IS TRUE AND "_depth" = 1',
            "indirect": '"_reports" IS TRUE AND "_depth" >= 2',
            "hrbp": '"_hrbp" IS TRUE',
            "inherited_hrbp": '"_inherited" IS TRUE',
        }[plan.scope]
        conditions = [scope]
        if plan.departments:
            conditions.append(f'"dept_cn_name" IN ({listing(plan.departments)})')
        if plan.population == "active":
            conditions.append(
                f'"onboard_date" <= {literal(store.AS_OF)} AND '
                f'("termin_date" IS NULL OR "termin_date" > {literal(store.AS_OF)})'
            )
        if plan.population == "confirmed":
            conditions.append(
                f'"formalize_flag" = {literal("是")} AND "confirmation_date" <= {literal(store.AS_OF)}'
            )
        conditions.extend(self.condition(filt) for filt in plan.filters)
        if include_period and plan.date_field:
            field = '"event_day"' if plan.date_field == "employment_events" else self.expr(plan.date_field)
            conditions.append(f"{field} BETWEEN {literal(plan.start_date)} AND {literal(plan.end_date)}")
        return " AND ".join(f"({condition})" for condition in conditions)

    def metric(self, name):
        """把一个业务指标展开成 PostgreSQL 表达式；辅助分母/样本量同样在库中计算。"""
        count = 'COUNT(DISTINCT "person_id")'
        if name == "count":
            return [(name, count)]
        if name in ("hires", "departures", "net_change"):
            if self.plan.date_field == "employment_events":
                hire, departure = 'COALESCE(SUM("is_hire"), 0)', 'COALESCE(SUM("is_exit"), 0)'
            else:
                # 非组合事件场景与原编译器一致：在已选日期维度形成的人群中，
                # 分别统计同一期间内发生的入职和离职，不把当前在职当作前提。
                start, end = literal(self.plan.start_date), literal(self.plan.end_date)
                hire = f'COALESCE(SUM(CASE WHEN "onboard_date" BETWEEN {start} AND {end} THEN 1 ELSE 0 END), 0)'
                departure = f'COALESCE(SUM(CASE WHEN "termin_date" BETWEEN {start} AND {end} THEN 1 ELSE 0 END), 0)'
            return [(name, {"hires": hire, "departures": departure, "net_change": f"{hire} - {departure}"}[name])]
        if name in ("avg_age", "avg_confirmation_days"):
            value = (
                '"age"'
                if name == "avg_age"
                else f'CASE WHEN "confirmation_date" >= "onboard_date" AND "confirmation_date" <= {literal(store.AS_OF)} '
                'THEN CAST("confirmation_date" AS DATE) - CAST("onboard_date" AS DATE) END'
            )
            return [(name, f"ROUND(CAST(AVG({value}) AS NUMERIC), 2)"), (name + "_sample_size", f"COUNT({value})")]
        predicates = {
            "masters": '"diploma_code_desc" IN (\'硕士研究生\', \'博士研究生\')',
            "doctors": f'"degree_code_desc" = {literal("博士")} AND "education_expired_date" <= {literal(store.AS_OF)}',
            "outsource": f'"labour_type_code_desc" = {literal("外包")}',
            "school_985": f'"school_name" IN ({listing([school for school, flags in SCHOOLS.items() if flags[0]])})',
            "school_211": f'"school_name" IN ({listing([school for school, flags in SCHOOLS.items() if flags[1]])})',
        }
        key = name.removesuffix("_count").removesuffix("_ratio")
        numerator = f'COUNT(DISTINCT CASE WHEN {predicates[key]} THEN "person_id" END)'
        if name.endswith("_count"):
            return [(name, numerator)]
        return [
            (name, f"ROUND(100.0 * {numerator} / NULLIF({count}, 0), 2)"),
            (name + "_numerator", numerator),
            (name + "_denominator", count),
        ]

    def query_object(self, columns, metrics, *, include_period=True, people=False):
        """只描述业务筛选和展示方式；实际 FROM 与查看人 RLS 由 Superset 补入。"""
        return {
            "columns": columns,
            "metrics": metrics,
            "extras": {"where": self.where(include_period), "having": ""},
            "filters": [],
            "orderby": [["person_id", True]] if people else [],
            "row_limit": RESULT_LIMIT,
            "row_offset": 0,
            "is_timeseries": False,
        }

    def compile(self):
        """一次请求可含结果、独立总计和补零部门域，避免用分页/分组结果反推合计。"""
        plan = self.plan
        if plan.kind == "people":
            # 排序列可不展示，但查询仍需该列供全量结果稳定排序使用。
            fields = list(dict.fromkeys([*plan.columns, *(o.field for o in plan.order_by), "person_id"]))
            for field in fields:
                self.expr(field)
            result = self.query_object(fields, [], people=True)
            total = self.query_object([], [sql_expression("count", 'COUNT(DISTINCT "person_id")')])
            return [result, total]
        metrics = [sql_expression(name, expression) for metric in plan.metrics for name, expression in self.metric(metric)]
        dimensions = [sql_expression(dim, f"COALESCE({self.expr(dim)}, '未知')") for dim in plan.group_by]
        result = self.query_object(dimensions, metrics)
        total = self.query_object([], metrics)
        queries = [result, total]
        if plan.group_by and plan.start_date and any(dim.endswith("_month") for dim in plan.group_by):
            # 空月份的部门取值范围在日期筛选前确定，与原来的 base CTE 一致。
            queries.append(self.query_object(["dept_cn_name"], [], include_period=False))
        return queries


def checked_rows(result):
    """检查一批完整结果，超过演示边界直接拒绝，不能把截断数据交给后续核验。"""
    if result.get("error") or result.get("status") == "failed":
        raise HTTPException(502, "Superset 执行查询失败，请查看节点调试信息")
    rows = result.get("data")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise HTTPException(502, "Superset 返回的数据格式不符合查询协议")
    if len(rows) >= RESULT_LIMIT:
        raise HTTPException(422, "查询结果超过演示全量核验上限，请缩小筛选范围后重试")
    return rows


def execute(p, plan):
    """取得授权快照→校验/编译 Plan→真实 Chart Data 查询→整理统一返回结构。

    PostgreSQL 完成业务筛选和聚合；此处只补零、稳定排序、分页和列标签。
    _all_rows 仅给服务端核验/导出使用，普通 API 由 service 删除。
    """
    # 延迟导入避免 query.execute 的后端分派产生循环引用。
    from . import superset_source

    started = time.perf_counter()
    snapshot = superset_source.snapshot(p)
    compiler = Compiler(p, plan, snapshot)
    plan = compiler.plan
    requested = compiler.compile()
    results = superset_source.chart(p, compiler.dataset_key, requested)
    if not isinstance(results, list) or len(results) != len(requested):
        raise HTTPException(502, "Superset 返回的查询数量不完整")
    batches = [checked_rows(result) for result in results]
    if len(batches[1]) != 1:
        raise HTTPException(502, "Superset 未返回唯一的总体统计，已停止展示不完整结果")
    rows, totals = batches[0], batches[1][0]
    if plan.kind == "people":
        # 必须获得全部数据后才在页面上分页，确保导出、核验、排序一致。
        if totals.get("count") != len(rows):
            raise HTTPException(502, "明细数量与总体统计不一致，请刷新重试")
        rows = sorted(rows, key=lambda row: str(row["person_id"]))
        rows = query.order_rows(rows, plan)
        rows = [{field: row.get(field) for field in plan.columns} for row in rows]
    else:
        if len(batches) == 3:
            departments = sorted({row["dept_cn_name"] for row in batches[2] if row.get("dept_cn_name") is not None})
            rows = query.fill_zeros(rows, plan, departments)
        rows = query.order_rows(rows, plan)
    columns = (
        [{"key": field, "label": FIELDS[field][0]} for field in plan.columns]
        if plan.kind == "people"
        else [{"key": dim, "label": DIMENSIONS[dim]} for dim in plan.group_by]
    )
    if plan.kind == "aggregate":
        for metric in plan.metrics:
            columns.append({"key": metric, "label": METRICS[metric][0] + f"（{METRICS[metric][1]}）"})
            if metric.endswith("_ratio"):
                columns.extend([
                    {"key": metric + "_numerator", "label": "符合人数 · " + METRICS[metric][0]},
                    {"key": metric + "_denominator", "label": "分母 · " + METRICS[metric][0]},
                ])
            if metric.startswith("avg_"):
                columns.append({"key": metric + "_sample_size", "label": "有效样本 · " + METRICS[metric][0]})
    source_queries = list(snapshot.get("source_queries", []))
    source_queries.extend(result.get("query", "") for result in results)
    return {
        "status": "success",
        "plan": plan.model_dump(),
        "rows": rows[(plan.page - 1) * plan.page_size : plan.page * plan.page_size],
        "columns": columns,
        "total_rows": len(rows),
        "totals": totals,
        "page": plan.page,
        "page_size": plan.page_size,
        "sql": results[0].get("query", ""),
        "parameters": compiler.params,
        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        "as_of": store.AS_OF,
        "scope_count": len(compiler.ids),
        "policy_version": compiler.grant["policy_version"],
        "notes": [
            "合成数据；关系与字段解释是可调整的演示假设。",
            "组织归属采用当前部门，未重建历史任职。",
            "学校与学历取宽表当前教育记录；毕业日期映射为演示假设。",
            "查询通过当前演示身份登录 Superset；RLS 在 PostgreSQL 聚合前生效。",
        ],
        "execution_backend": "superset",
        "source_queries": source_queries,
        "_all_rows": rows,
    }
