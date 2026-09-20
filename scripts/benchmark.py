"""Small, serial 当前 benchmark using isolated state; never invokes the model."""

import json
import statistics
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.hr import config, service, store
from backend.hr.schema import Plan


def main():
    plans = json.loads((config.PROJECT / "evaluation/plans.json").read_text())["plans"]
    times = []
    with tempfile.TemporaryDirectory(prefix="hr-benchmark-") as folder:
        config.APP_DB = Path(folder) / "app.sqlite"
        store.ensure()
        for _ in range(3):
            for case, raw in plans.items():
                p = next(
                    p
                    for p in store.PERSONAS
                    if p["id"] == {"HR-01": "manager", "HR-02": "hrbp"}.get(case, "hr_lead")
                )
                started = time.perf_counter()
                service.run_query(p, Plan.model_validate(raw))
                times.append((time.perf_counter() - started) * 1000)
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "source_rows": 300,
        "serial_requests": len(times),
        "model_inference": False,
        "median_ms": round(statistics.median(times), 2),
        "p95_ms": round(sorted(times)[int(len(times) * 0.95) - 1], 2),
        "max_ms": round(max(times), 2),
        "includes": "权限遍历、数据/权限指纹、SQL、全量合计、分页和摘要；不含HTTP/浏览器/模型",
        "limitations": "仅本机300人合成数据，不能据此推断真实PostgreSQL大规模性能。",
    }
    Path("reports").mkdir(exist_ok=True)
    Path("reports/performance.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
