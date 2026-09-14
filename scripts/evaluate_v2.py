"""Serial live-model acceptance against hand-authored plans and independent reference.

Runs in an isolated application/data directory, preserving the live demo. The
production planner never imports this fixture. Report failures without filtering.
"""

import argparse
import asyncio
import json
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.hr import config
from backend.hr.v2 import query, reference, service, store
from backend.hr.v2.graph import answer
from backend.hr.v2.schema import Plan, Question


def pressure():
    if sys.platform != "darwin":
        return {"available": False}
    outputs = {}
    for command in (["uptime"], ["memory_pressure"], ["pmset", "-g", "therm"]):
        p = subprocess.run(command, capture_output=True, text=True, timeout=10)
        outputs[command[0]] = p.stdout[-700:]
    return outputs


def compare(actual, expected):
    # Column order and tie ordering can differ; values, identities, groups and all totals cannot.
    def canonical(rows):
        return sorted(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows)

    return canonical(actual) == canonical(expected)


async def main(args):
    source = json.loads(
        (
            config.PROJECT
            / ("evaluation/demo-v2-paraphrases.json" if args.variants else "evaluation/demo-v2-cases.json")
        ).read_text()
    )
    plans = json.loads((config.PROJECT / "evaluation/demo-v2-plans.json").read_text())["plans"]
    selected = set(args.cases.split(",")) if args.cases else {c["id"] for c in source["cases"]}
    report = {
        "started_at": datetime.now(UTC).isoformat(),
        "model": config.MODEL_ID,
        "isolated": True,
        "cases": [],
        "pressure": [pressure()],
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="hr-v2-eval-") as directory:
        config.APP_DB = Path(directory) / "app.sqlite"
        store.ensure()
        previous = {}
        report["data_fingerprint"] = store.data_fingerprint()
        for case in source["cases"]:
            if case["id"] not in selected:
                continue
            plan_key = case.get("base_id", case["id"])
            p = next(
                p
                for p in store.PERSONAS
                if p["id"] == {"HR-01": "manager", "HR-02": "hrbp"}.get(plan_key, "hr_lead")
            )
            started = time.monotonic()
            expected = reference.calculate(p, Plan.model_validate(plans[plan_key]))
            try:
                parent = previous.get(case.get("previous_case_id"))
                if case.get("previous_case_id") and not parent:
                    raise ValueError("Required previous case did not succeed")
                if parent:
                    service.read_run(p, parent)  # Exercise persisted history restore, not in-memory rows.
                result = await answer(p, Question(question=case["question"], previous_id=parent))
                actual = (
                    query.execute(p, Plan.model_validate(result["plan"]))
                    if result["status"] == "success"
                    else None
                )
                passed = bool(
                    actual
                    and compare(actual["_all_rows"], expected["rows"])
                    and actual["totals"] == expected["totals"]
                )
                if result["status"] == "success":
                    previous[case["id"]] = result["id"]
                raw = [
                    t["output"].get("candidate")
                    for t in result.get("trace", [])
                    if t["name"] == "模型生成计划"
                ]
                item = {
                    "id": case["id"],
                    "passed": passed,
                    "elapsed_s": round(time.monotonic() - started, 2),
                    "status": result["status"],
                    "question": case["question"],
                    "expected_plan": plans[plan_key],
                    "actual_plan": result.get("plan"),
                    "expected": expected,
                    "actual": {"rows": actual["_all_rows"], "totals": actual["totals"]} if actual else None,
                    "message": result.get("message"),
                    "model_attempts": len(raw),
                    "rule_bindings": sum(
                        t["name"] == "明确条件绑定（规则补齐）" for t in result.get("trace", [])
                    ),
                    "raw_candidates": raw,
                    "trace": result.get("trace", []),
                }
            except Exception as exc:
                item = {
                    "id": case["id"],
                    "passed": False,
                    "error": str(exc),
                    "elapsed_s": round(time.monotonic() - started, 2),
                }
            report["cases"].append(item)
            if len(report["cases"]) % 4 == 0:
                report["pressure"].append(pressure())
            report["passed"] = sum(c["passed"] for c in report["cases"])
            report["total"] = len(report["cases"])
            out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
            print(
                json.dumps(
                    {
                        k: v
                        for k, v in item.items()
                        if k in ("id", "passed", "elapsed_s", "status", "message", "model_attempts", "error")
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
    report["completed_at"] = datetime.now(UTC).isoformat()
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(f"Passed {report['passed']}/{report['total']}; report {out}", flush=True)
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--variants", action="store_true")
    parser.add_argument("--cases", default="")
    parser.add_argument("--output", default="reports/demo-v2-model.json")
    raise SystemExit(asyncio.run(main(parser.parse_args())))
