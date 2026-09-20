"""从正在运行的字段/指标定义生成中文文档；--check 用于 CI 防止文档漂移。"""

import argparse
import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from backend.hr.registry import ALIASES, NOTES  # noqa: E402
from backend.hr.schema import FIELDS, METRICS  # noqa: E402
from backend.hr.store import AS_OF  # noqa: E402


def render():
    lines = ["# 字段、指标与演示问题", "",
             "由 `scripts/document_catalog.py` 从当前源码生成。修改 `schema.py` / `registry.py` 后重新生成，不手工维护第二份口径。", "",
             f"数据快照日：{AS_OF}。每人一行；历史事件按当前部门分组，无任职/汇报线历史。", "",
             "## 人员字段", "",
             "| 字段 ID | 中文 | 权限组 | 定义 | 口语别名 | 不代表什么 |",
             "|---|---|---|---|---|---|"]
    for key, (label, group, definition) in FIELDS.items():
        lines.append(f"| `people.{key}` | {label} | {group} | {definition} | {'、'.join(ALIASES.get(key, []))} | {NOTES.get(key, '以字段定义为准。')} |")
    lines += ["", "## 指标", "", "所有指标先与当前授权范围取交集。零分母返回空值，比例分母含未知，平均数排除未知；四舍五入保留两位小数。", "",
              "| ID | 名称 | 单位 | 依赖字段 | 口径 |", "|---|---|---|---|---|"]
    for key, (label, unit, fields, definition) in METRICS.items():
        lines.append(f"| `metric.{key}` | {label} | {unit} | {', '.join(fields)} | {definition} |")
    lines += ["", "## 20 个演示问题", "", "对应 `evaluation/cases.json`；预期计划在 `plans.json`，独立基准在 `golden.json`。", ""]
    cases = json.loads((PROJECT / "evaluation/cases.json").read_text())["cases"]
    for case in cases:
        lines.append(f"- **{case['id']}**：{case['question']}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    target = PROJECT / "docs/DATA_DICTIONARY.md"
    content = render()
    if args.check:
        if not target.exists() or target.read_text() != content:
            raise SystemExit("字段文档与源码不一致，请运行 uv run python scripts/document_catalog.py")
        print("字段、指标和题单文档与源码一致。")
    else:
        target.write_text(content)
        print(target)
