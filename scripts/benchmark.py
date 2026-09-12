import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.hr.db import application
from backend.hr.models import QueryPlan
from backend.hr.query import execute
from backend.hr.validate import validate

with application() as db:
    principal = dict(db.execute("SELECT * FROM principals WHERE id='ceo'").fetchone())
plans = [
    QueryPlan(),
    QueryPlan(metric="attendance_rate", dimension="department"),
    QueryPlan(metric="approved_overtime_hours", dimension="month", period="last_6_months"),
    QueryPlan(dimension="month", period="last_6_months"),
    QueryPlan(kind="people", limit=100),
]


def run(i):
    start = time.perf_counter()
    result = execute(principal, plans[i % len(plans)], record_audit=False)
    return {"ms": (time.perf_counter() - start) * 1000, "rows": len(result["rows"])}


for i in range(5):
    run(i)
results = [run(i) for i in range(60)]
with ThreadPoolExecutor(max_workers=8) as pool:
    concurrent = list(pool.map(run, range(40)))


def stats(items):
    values = sorted(r["ms"] for r in items)
    return {
        "requests": len(values),
        "p50_ms": round(statistics.median(values), 2),
        "p95_ms": round(values[int((len(values) - 1) * 0.95)], 2),
        "max_ms": round(max(values), 2),
    }


report = {
    "dataset": {k: v for k, v in validate().items() if k in ("total_employees", "active_employees", "as_of")},
    "serial": stats(results),
    "concurrency_8": stats(concurrent),
    "note": "本机合成数据、同进程查询服务，包含授权和SQL，不含网络、模型推理和审计写入，不代表生产容量。",
}
Path("reports/performance.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(report, ensure_ascii=False, indent=2))
