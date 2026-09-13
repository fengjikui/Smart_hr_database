"""Generate the complete reviewable dictionary from the same source as the UI."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.hr import config  # noqa: E402
from backend.hr.data_dictionary import inventory  # noqa: E402
from backend.hr.db import application  # noqa: E402
from backend.hr.seed import initialize_app  # noqa: E402


def cell(value):
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def generate():
    initialize_app(config.APP_DB)
    with application() as db:
        principal = dict(db.execute("SELECT * FROM principals WHERE id='ceo'").fetchone())
    data = inventory(principal)
    summary = data["summary"]
    lines = [
        "# 当前数据库、完整字段及指标口径",
        "",
        "由 `uv run python scripts/document_schema.py` 从实际 SQLite 结构、指标目录和 SQL 编译器生成，与系统“数据库与口径”页共用同一数据源。",
        "",
        f"当前为 **{summary['business_tables']} 张业务表、{summary['application_tables']} 个应用逻辑表/全文索引、{summary['semantic_tables']} 个语义逻辑表/全文索引、{summary['fields']} 个字段、{summary['metrics']} 个指标**。字段数按各表列数相加，同名关联键分别计数。",
        "全部为合成数据；字段存在不代表 Agent 已支持该字段。FTS5 自动影子表不计入逻辑表。表内不附人员、私人资料或会话实际值。",
        "",
        "## 存储位置与职责",
        "",
        "| 层 | 位置 | 职责 |",
        "|---|---|---|",
    ]
    for item in data["storage"]:
        lines.append(f"| {item['name']} | `{item['location']}` | {item['purpose']} |")
    lines += [
        "",
        "## 数据集元信息",
        "",
        "```json",
        json.dumps(data["dataset"], ensure_ascii=False, indent=2),
        "```",
        "",
    ]
    lines += ["## 所有表与字段总览", "", "| 库 / 表 | 用途与粒度 | 全部字段 |", "|---|---|---|"]
    for table in data["tables"]:
        fields = ", ".join(f"`{f['name']}`" for f in table["fields"])
        lines.append(f"| {table['database']} / `{table['name']}` | {table['description']} | {fields} |")
    lines += [
        "",
        "## 字段、键、索引与实际建表约束",
        "",
        "日期为 YYYY-MM-DD，打卡为距午夜的分钟数。PK 后数字为复合主键内位置；NOT NULL 列是 PRAGMA 的实际声明，SQLite 主键语义另见原始 DDL。完整 CHECK、UNIQUE、外键与部分索引条件保留在 SQL 中。",
        "",
    ]
    for table in data["tables"]:
        lines += [f"### `{table['name']}`", "", f"{table['description']}。数据库：{table['database']}。", ""]
        if table["row_count"] is not None:
            lines += [f"当前合成行数：{table['row_count']:,}。", ""]
        lines += ["| 字段 | 类型 | 声明约束 / 关联 | 含义 |", "|---|---|---|---|"]
        for field in table["fields"]:
            constraints = []
            if field["primary_key_position"]:
                constraints.append(f"PK({field['primary_key_position']})")
            if field["not_null"]:
                constraints.append("NOT NULL")
            if field["default"] is not None:
                constraints.append(f"DEFAULT {field['default']}")
            constraints.extend(
                f"→ {fk['table']}.{fk['to']}" for fk in table["foreign_keys"] if fk["from"] == field["name"]
            )
            lines.append(
                f"| `{field['name']}` | {field['type']} | {cell('; '.join(constraints) or '—')} | {cell(field['description'])} |"
            )
        lines += ["", "```sql", table["create_sql"] + ";", "```", ""]
        if table["indexes"]:
            lines += ["| 索引 | 列 | 唯一 | 部分索引 | 来源 |", "|---|---|---|---|---|"]
            for index in table["indexes"]:
                lines.append(
                    f"| `{index['name']}` | {', '.join(index['columns'])} | {bool(index['unique'])} | {bool(index['partial'])} | {index['origin']} |"
                )
            lines.append("")
            explicit = [index["sql"] + ";" for index in table["indexes"] if index["sql"]]
            if explicit:
                lines += ["```sql", "\n".join(explicit), "```", ""]
    lines += [
        f"## 已开放的{summary['metrics']}个指标",
        "",
        f"目录版本 `{data['catalog_version']}`；下列表达式从实际编译的 SQL 提取。表达式依赖同一 SQL 的授权集合、日期与任职 CTE，不能脱离这些条件执行。完整示例计划及 SQL 可在系统中展开，也保存在同目录 `data-dictionary.json` 中。",
        "",
    ]
    for metric in data["metrics"]:
        dimensions = ", ".join(f"{label} (`{name}`)" for name, label in metric["dimension_labels"].items())
        lines += [
            f"### {metric['name']} `{metric['id']}`",
            "",
            metric["description"],
            "",
            f"- 单位：{metric['unit']}；业务域：{metric['domain']}。",
            f"- 可分组：{dimensions}；也可不分组，单次只支持一个分组维度。",
            f"- 数据来源：{', '.join(metric['source'])}。",
            f"- 别名：{', '.join(metric['aliases'])}。",
            f"- 敏感级别：`{metric['sensitivity']}`；最小组规模：{metric['minimum_group_size']}。",
            f"- 责任人：{metric['owner']}；指标版本：{metric['version']}。",
            f"- 示例问题：{metric['example']}",
            "",
            "实际聚合表达式：",
            "",
            "```sql",
            metric["sql_expression"] or str(metric.get("example_error")),
            "```",
            "",
        ]
    lines += ["## 共用业务口径与能力边界", ""]
    for rule in data["conventions"]:
        lines += [f"### {rule['name']}", "", rule["value"], ""]
    lines += [
        "## 表已建立，但尚未开放的能力",
        "",
        "绩效评价、培训、招聘需求已有合成关系表，尚无对应问数指标；年龄、性别、专业与学习形式筛选未开放。私人电话、证件和银行账号不进入模型工具或查询白名单。基本月薪不是完整工资支付流水，目前没有奖金、补贴、扣款、社保、公积金、实发工资的计算与支付模型。",
        "",
        "本机 SQLite 演示使用应用授权与只读 SQL 编译器。正式接入需验证真实宽表映射、HR 确认口径、企业 SSO 与数据库级行列防护。调试信息的记录范围和访问规则见 `docs/DEBUGGING.md`。",
        "",
    ]
    (ROOT / "docs/DATA_DICTIONARY.md").write_text("\n".join(lines))
    (ROOT / "docs/data-dictionary.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    generate()
