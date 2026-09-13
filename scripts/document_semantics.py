"""Reproducible Chinese semantic reference; no business data is queried."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.hr.semantics import VERSION, source_documents, source_key  # noqa: E402


def cell(value):
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def outputs():
    docs, revision = source_documents(source_key())
    fields = [d for d in docs if d["kind"] == "field"]
    metrics = [d for d in docs if d["kind"] == "metric"]
    questions = [d for d in docs if d["kind"] == "question"]
    lines = [
        "# 语义定义完整清单",
        "",
        f"由 `scripts/document_semantics.py` 从 Git JSON 定义源生成。语义版本 `{VERSION}`；发布指纹 `{revision}`。",
        "",
        f"包括 {len(fields)} 个字段、{len(metrics)} 个指标定义（17个可执行、15个规划）。完整问题库见 [HR问题库](HR_QUESTION_BANK.md)，设计决策见 [语义层与查询图](SEMANTIC_ARCHITECTURE.md)。",
        "",
        "字段存在与列出规划公式均不等于已开放查询。权限、白名单和计算实现仍由服务端控制；所有示例均为人工合成的格式或枚举，不扫描员工实际值。",
        "",
        "## 字段：表ID.字段ID",
        "",
    ]
    for table in [d for d in docs if d["kind"] == "table"]:
        lines += [
            f"### `{table['table_id']}` · {table['name']}",
            "",
            table["meaning"],
            "",
            f"粒度：{table['grain']}。不表示：{table['not_meaning']}",
            "",
            "| 字段唯一ID / 类型 | 名称与口语别名 | 表示什么 | 不表示什么 | 单位 / 示例值 / 可空 |",
            "|---|---|---|---|---|",
        ]
        for field in fields:
            if field["table_id"] == table["table_id"]:
                lines.append(
                    f"| `{field['id']}`<br>{field['data_type']} | {cell(field['name'])}<br>{cell('、'.join(field['aliases']))} | {cell(field['meaning'])} | {cell(field['not_meaning'])} | {cell(field.get('unit', '—'))}<br>{cell(field.get('examples', []))}<br>可空：{field['nullable']} |"
                )
        lines.append("")
    lines += ["## 指标口径", ""]
    labels = {
        "meaning": "表示什么",
        "not_meaning": "不表示什么",
        "definition": "计算公式",
        "grain": "粒度",
        "time_rule": "时间口径",
        "inclusions": "纳入范围",
        "exclusions": "排除范围",
        "null_rule": "空值与除零",
        "grouping_rule": "分组约束",
        "permission_rule": "权限规则",
        "missing_requirements": "尚需完成",
        "owner": "负责人",
    }
    for metric in metrics:
        lines += [
            f"### `{metric['id']}` · {metric['name']}",
            "",
            f"状态：{'可执行' if metric['status'] == 'available' else '规划，禁止执行'}；单位：{metric['unit']}。",
            "",
            f"口语别名：{'、'.join(metric['aliases'])}",
            "",
        ]
        for key, label in labels.items():
            if metric.get(key):
                lines.append(f"- **{label}**：{metric[key]}")
        lines += [
            "",
            "依赖字段：" + "、".join(f"`{f}`" for f in metric["field_ids"]),
            "",
            "提问示例：" + "；".join(v["question"] for v in metric["examples"]),
            "",
        ]
    reference = "\n".join(lines) + "\n"
    lines = [
        "# HR与主管问题库",
        "",
        f"共 {len(questions)} 个业务问题，版本 `{VERSION}`。这是产品发现与演示题库，不是独立模型准确率证明。模型评测另有隔离的用例与报告。",
        "",
        "当前102个问题映射已开放指标，45个问题映射规划口径，13个问题需要澄清或拒绝。不同身份的可见问题会按敏感级别过滤，所有查询继续受人员范围限制。",
        "",
        "| 编号 | 用户问题 | 关联指标 | 状态 | 业务目的 |",
        "|---|---|---|---|---|",
    ]
    status = {"available": "已支持", "planned": "待建设", "clarification_or_denial": "需澄清/拦截"}
    for q in questions:
        lines.append(
            f"| {q['id']} | {cell(q['question'])} | {cell('、'.join(q['metric_ids']))} | {status[q['status']]} | {cell(q['rationale'])} |"
        )
    return {"docs/SEMANTIC_REFERENCE.md": reference, "docs/HR_QUESTION_BANK.md": "\n".join(lines) + "\n"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for filename, body in outputs().items():
        target = ROOT / filename
        if args.check:
            if not target.exists() or target.read_text() != body:
                raise SystemExit(f"语义文档需要重新生成：{filename}")
        else:
            target.write_text(body)
    print("语义定义与160个问题文档校验通过" if args.check else "语义定义与160个问题文档已生成")
