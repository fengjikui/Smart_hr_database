"""Read structural metadata only; never sample session or private table values."""

import sqlite3

from fastapi import HTTPException

from . import config, semantics
from .catalog import catalog
from .db import business
from .metadata import FIELDS, TABLES
from .models import QueryPlan
from .query import DIMENSION_LABELS, compile_query

CONVENTIONS = [
    {"name": "数据范围", "value": "全部为可复现合成数据，演示时区Asia/Shanghai；今天/本月按数据截止日解释。"},
    {
        "name": "组织与授权",
        "value": "公司→事业部→部门→团队。当前管理闭包决定授权集合；本人depth=0、直属=1、间接>=2；HRBP用服务组织范围。",
    },
    {
        "name": "在职与历史归属",
        "value": "hire_date<=统计日，termination_date为空或>统计日。任职有效期[valid_from,valid_to)，历史分组按业务发生日任职。离职归属离职日前一天。",
    },
    {
        "name": "弹性班次",
        "value": "08:00–09:30到岗，09:30整不迟到。演示补充净工作480分钟、午休60分钟，应离岗=max(18:00,到岗+9小时)。",
    },
    {
        "name": "晚离岗与加班",
        "value": "晚离岗=max(下班-应离岗,0)；仅已批准申请计加班。两者分别建模，不自动等同。模拟打卡最晚22:00。",
    },
    {
        "name": "日历与请假",
        "value": "日历从演示当年1月1日至数据日；周一至周五为应出勤日，周末独立记录加班打卡和申请。未接法定节假日调休、半天假、跨夜班。正常/远程算完成出勤，缺卡与缺勤不算。",
    },
    {
        "name": "除零、空值与精度",
        "value": "比率分母为0返回NULL。人数为去重员工，人次为员工×日期。比例、均值与小时数按SQL保留2位；界面部分摘要显示1位。",
    },
    {
        "name": "查询边界",
        "value": "单维度，入职/离职/净增为预定义组合指标。明细1–100行；聚合最多400组；日期差不超过366天。支持已完成学历/学位/学校条件及入离职名单。未开放部门数量、年龄/性别/专业/学习形式筛选、自由多指标、多维度、排名、同比环比和预测。",
    },
    {
        "name": "历史趋势",
        "value": "人数月趋势统计月末，当前月截至数据日；入职按入职日，离职按离职日。没有事实的分组可能缺席，不补造历史记录。",
    },
    {
        "name": "教育背景与学校去重",
        "value": "学历与学位分开存储，历史问数按业务发生日已经完成的最高教育经历取值；硕士默认精确硕士学位，硕士及以上按学历层级包含博士。某校毕业默认匹配任一已完成经历，多校OR按员工去重；同一经历需同时满足学校与学位等条件。",
    },
    {
        "name": "教育占比的分子与分母",
        "value": "学历/学位/211或985占比默认最高已完成教育经历。分子为满足教育条件的去重员工，分母为同组织同权限的全部在职员工，含教育未知者；指定入职/离职人群时改用期间事件人群，学历仍按事件日判断。分母0返回NULL，保留分子分母。985与211合并使用OR，不能相加；双一流不是同一标签。",
    },
    {
        "name": "部门汇总与期间",
        "value": "各部门指三级部门并包含下属团队，公司及事业部直属人员单列；各团队保留具体任职组织。部门过滤按业务发生日任职归属，并与当前授权取交集。上季度为上一完整自然季度；今年从1月1日至数据截止日。内部调动不计入离职；入离职组合及周末加班为无事件的授权组织显示0。",
    },
    {
        "name": "周末加班",
        "value": "周六或周日且day_type=周末的已批准申请分钟之和/60。独立打卡验证申请不超净工时；待审批/已拒绝不计入，不用晚离岗冒充。批准加班总时长包含工作日与周末，周末指标仅子集；未指定期间默认本月。",
    },
    {
        "name": "薪酬保护",
        "value": "只开放当前全授权范围/事业部的基本月薪均值，仅CNY。小于5人及必要互补组隐藏；禁止人员筛选、历史差分、明细和导出。",
    },
]
STORAGE = [
    {
        "name": "业务库",
        "location": "data/hr.sqlite",
        "purpose": "员工、教育经历、院校、任职、组织、考勤等24张关系表；查询服务只读。",
    },
    {
        "name": "应用库",
        "location": "data/app.sqlite",
        "purpose": "身份、会话、指标、看板、审计、对话与逐节点调试记录；与业务库分离。",
    },
    {
        "name": "指标定义源",
        "location": "semantic/catalog.json",
        "purpose": "Git版本化的名称、定义、来源、维度、责任人与敏感级别；发布到应用库metrics。",
    },
    {
        "name": "检索索引",
        "location": "app.sqlite.metric_search",
        "purpose": "兼容原指标搜索页面的派生索引；Agent使用独立语义库的检索与渐进式披露。",
    },
    {
        "name": "语义定义与检索库",
        "location": "semantic/*.json → data/semantic.sqlite",
        "purpose": "Git管理表、字段、指标和问题的定义；发布为结构化文档与FTS5子串索引。LangGraph先检索再按需披露，不注入全部字段；暂不使用向量索引。",
    },
    {
        "name": "公式实现",
        "location": "backend/hr/query.py",
        "purpose": "确定性SQL编译器实现口径和权限；下面的公式与示例SQL从实际编译结果提取。",
    },
]


def quote(identifier):
    return '"' + identifier.replace('"', '""') + '"'


def structural_tables(path, database):
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        tables = []
        for table in db.execute(
            "SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'metric_search_%' AND name NOT LIKE 'semantic_search_%' ORDER BY rowid"
        ).fetchall():
            name, ddl = table["name"], table["sql"]
            fields = [
                {
                    "name": row["name"],
                    "type": row["type"] or "FTS TEXT",
                    "not_null": bool(row["notnull"]),
                    "default": row["dflt_value"],
                    "primary_key_position": row["pk"],
                    "description": FIELDS.get(row["name"], "见建表语句"),
                }
                for row in db.execute(f"PRAGMA table_info({quote(name)})")
            ]
            foreign = [dict(row) for row in db.execute(f"PRAGMA foreign_key_list({quote(name)})")]
            indexes = []
            for row in db.execute(f"PRAGMA index_list({quote(name)})").fetchall():
                info = dict(row)
                info["columns"] = [r["name"] for r in db.execute(f"PRAGMA index_info({quote(row['name'])})")]
                info["sql"] = db.execute(
                    "SELECT sql FROM sqlite_master WHERE name=?", (row["name"],)
                ).fetchone()[0]
                indexes.append(info)
            count = (
                db.execute(f"SELECT COUNT(*) FROM {quote(name)}").fetchone()[0]
                if database == "business"
                else None
            )
            tables.append(
                {
                    "name": name,
                    "database": database,
                    "description": TABLES.get(name, "应用结构"),
                    "row_count": count,
                    "fields": fields,
                    "foreign_keys": foreign,
                    "indexes": indexes,
                    "create_sql": ddl,
                }
            )
        return tables
    finally:
        db.close()


def inventory(principal):
    if principal["id"] != "ceo":
        raise HTTPException(
            403, detail="完整技术数据字典目前仅向公司负责人演示身份开放。业务指标请使用指标字典。"
        )
    tables = structural_tables(config.BUSINESS_DB, "business") + structural_tables(
        config.APP_DB, "application"
    )
    documents = semantics.all_documents(principal)
    field_docs = {d["id"]: d for d in documents if d["kind"] == "field"}
    table_docs = {d["table_id"]: d for d in documents if d["kind"] == "table"}
    tables += structural_tables(semantics.database_path(), "semantic")
    for table in tables:
        table["description"] = table_docs[table["name"]]["description"]
        for field in table["fields"]:
            field["id"] = f"{table['name']}.{field['name']}"
            field["description"] = field_docs[field["id"]]["meaning"]
    definitions = []
    with business() as db:
        metadata = dict(db.execute("SELECT key,value FROM dataset_meta"))
        for metric in catalog()["metrics"]:
            plan = QueryPlan(
                metric=metric["id"],
                period="as_of" if metric["id"] in ("headcount", "avg_tenure", "avg_salary") else "this_month",
                degree="硕士" if metric["id"] == "education_ratio" else None,
            )
            item = {
                **metric,
                "dimension_labels": {d: DIMENSION_LABELS[d] for d in metric["dimensions"]},
                "example_plan": plan.model_dump(),
            }
            try:
                sql, _, _, _, _ = compile_query(principal, plan, db)
                item.update(
                    sql_expression=sql.split(" AS label,", 1)[1].split(" AS value,", 1)[0], example_sql=sql
                )
            except HTTPException as exc:
                item.update(sql_expression=None, example_sql=None, example_error=exc.detail)
            definitions.append(item)
    return {
        "tables": tables,
        "metrics": definitions,
        "storage": STORAGE,
        "conventions": CONVENTIONS,
        "dataset": metadata,
        "catalog_version": config.CATALOG_VERSION,
        "summary": {
            "business_tables": sum(t["database"] == "business" for t in tables),
            "application_tables": sum(t["database"] == "application" for t in tables),
            "semantic_tables": sum(t["database"] == "semantic" for t in tables),
            "fields": sum(len(t["fields"]) for t in tables),
            "metrics": len(definitions),
        },
        "note": "从实际SQLite结构与查询编译器读取；未读取私人信息或会话值。FTS5影子表为自动生成实现细节，未计入业务/应用逻辑表数量。",
    }
