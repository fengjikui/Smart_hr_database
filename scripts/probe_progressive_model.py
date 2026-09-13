"""Opt-in fault injection: omit initial detail to test real LM Studio inspect control.

This is not a normal-query accuracy case. Only the retrieval result is altered;
model, metadata authorization, graph edges, schema and SQL execution are real.
"""

import asyncio
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.hr import config, semantics  # noqa: E402
from backend.hr.agent import answer  # noqa: E402
from backend.hr.db import application  # noqa: E402
from backend.hr.debug import read_run  # noqa: E402
from backend.hr.seed import initialize_app  # noqa: E402


async def main():
    original = semantics.discover

    def omit_initial(*args, **kwargs):
        return {
            **original(*args, **kwargs),
            "initial_ids": [],
            "fault_injection": "省略首次详细口径以验证模型自主inspect；保留真实轻量索引",
        }

    semantics.discover = omit_initial
    try:
        with application() as db:
            principal = dict(db.execute("SELECT * FROM principals WHERE id='ceo'").fetchone())
        result = await answer(principal, "当前全公司平均司龄是多少？请依据司龄的定义回答。")
        run = read_run(principal, result["debug_run_id"])
        attempts = [n["output"].get("response") for n in run["nodes"] if n["key"] == "model"]
        passed = (
            result["status"] == "success"
            and result["plan"]["metric"] == "avg_tenure"
            and any(isinstance(v, dict) and v.get("kind") == "inspect" for v in attempts)
        )
        report = {
            "passed": passed,
            "mode": "real-LM-Studio-with-retrieval-fault-injection",
            "injected_fault": "首次披露无详细指标，轻量索引保留；不修改模型消息、模型返回或SQL结果",
            "question": run["question"],
            "model_attempts": attempts,
            "orchestration": result.get("orchestration"),
            "nodes": [
                {"key": n["key"], "status": n["status"], "duration_ms": n["duration_ms"]}
                for n in run["nodes"]
            ],
            "rows": result.get("rows"),
        }
        (ROOT / "reports/langgraph-progressive-probe.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        )
        print(json.dumps(report, ensure_ascii=False))
        return 0 if passed else 1
    finally:
        semantics.discover = original


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="hr-progressive-probe-") as directory:
        config.APP_DB = Path(directory) / "app.sqlite"
        initialize_app(config.APP_DB)
        raise SystemExit(asyncio.run(main()))
