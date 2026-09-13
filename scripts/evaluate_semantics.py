"""Metadata validation and retrieval measurements; no model inference or live-state writes."""

import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.hr import config, semantics  # noqa: E402
from backend.hr.db import application  # noqa: E402
from backend.hr.intent import explicit_constraints  # noqa: E402
from backend.hr.seed import initialize_app  # noqa: E402


def main():
    with tempfile.TemporaryDirectory(prefix="hr-semantic-evaluation-") as directory:
        config.APP_DB = Path(directory) / "app.sqlite"
        initialize_app(config.APP_DB)
        with application() as db:
            principal = dict(db.execute("SELECT * FROM principals WHERE id='ceo'").fetchone())
        docs = semantics.all_documents(principal)
        questions = [d for d in docs if d["kind"] == "question" and d["status"] == "available"]
        results = []
        for item in questions:
            started = time.perf_counter()
            constraints, _ = explicit_constraints(item["question"])
            result = semantics.discover(principal, item["question"], constraints)
            results.append(
                {
                    "id": item["id"],
                    "question": item["question"],
                    "expected_metric_ids": item["metric_ids"],
                    "initial_ids": result["initial_ids"],
                    "recalled": any("metric:" + m in result["initial_ids"] for m in item["metric_ids"]),
                    "milliseconds": round((time.perf_counter() - started) * 1000, 2),
                }
            )
        times = sorted(r["milliseconds"] for r in results)
        report = {
            "version": semantics.VERSION,
            "revision": semantics.publish(),
            "documents": len(docs),
            "fields": sum(d["kind"] == "field" for d in docs),
            "questions": 160,
            "library_cases": len(results),
            "initial_recall": sum(r["recalled"] for r in results),
            "median_ms": round(statistics.median(times), 2),
            "p95_ms": times[int(len(times) * 0.95)],
            "note": "这是已知问题库的首次元数据召回，不是独立模型评测。未命中的指标仍可通过轻量索引和inspect补充读取；相似度不决定SQL或权限。",
            "results": results,
        }
        target = ROOT / "reports/semantic-retrieval.json"
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({k: v for k, v in report.items() if k != "results"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
