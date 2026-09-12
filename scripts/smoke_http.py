"""Check the production frontend proxy and authorization over real HTTP."""

import argparse
import json
from pathlib import Path

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:3000")
    parser.add_argument("--model", action="store_true")
    args = parser.parse_args()
    checks = []
    with httpx.Client(base_url=args.url, timeout=100, trust_env=False) as client:
        page = client.get("/")
        assert page.status_code == 200
        for header in ["x-content-type-options", "x-frame-options", "content-security-policy"]:
            assert header in page.headers, f"Missing page header: {header}"
        assert client.get("/api/bootstrap").status_code == 401
        checks.append("production HTML and security headers; API authentication")
        for persona, expected in [("ceo", 459), ("rd", 168), ("employee", 1)]:
            login = client.post("/api/demo/session", json={"persona_id": persona})
            assert login.status_code == 200, login.text
            boot = client.get("/api/bootstrap").json()
            csrf = boot["principal"]["csrf"]
            plan = {"kind": "metric", "metric": "headcount", "period": "as_of"}
            assert client.post("/api/query", json=plan).status_code == 403
            response = client.post("/api/query", json=plan, headers={"X-CSRF-Token": csrf})
            assert response.status_code == 200, response.text
            assert response.json()["rows"][0]["value"] == expected, response.text
            checks.append(f"{persona}: {expected} authorized active employees; CSRF enforced")
            dictionary = client.get("/api/data-dictionary")
            assert dictionary.status_code == (200 if persona == "ceo" else 403)
            if persona == "ceo":
                assert dictionary.json()["summary"] == {
                    "business_tables": 21,
                    "application_tables": 8,
                    "fields": 157,
                    "metrics": 14,
                }
            blocked = client.post(
                "/api/chat", json={"question": "查询30岁以上员工人数"}, headers={"X-CSRF-Token": csrf}
            )
            assert blocked.status_code == 422
            run_id = blocked.headers["x-debug-run-id"]
            debug = client.get(f"/api/debug/runs/{run_id}").json()
            assert debug["status"] == "blocked"
            assert [node["key"] for node in debug["nodes"]] == ["request", "authorization", "capability"]
            assert debug["nodes"][-1]["error"]["status_code"] == 422
            checks.append(f"{persona}: dictionary role enforced; failed-query trace linked through proxy")
        salary = client.post("/api/query", json={"metric": "avg_salary"}, headers={"X-CSRF-Token": csrf})
        assert salary.status_code == 403
        checks.append("employee cannot access salary aggregate")
        if args.model:
            client.post("/api/demo/session", json={"persona_id": "ceo"}).raise_for_status()
            csrf = client.get("/api/bootstrap").json()["principal"]["csrf"]
            answer = client.post(
                "/api/chat",
                json={"question": "我的直属和间接下属分别有多少人？"},
                headers={"X-CSRF-Token": csrf},
            )
            assert answer.status_code == 200, answer.text
            result = answer.json()
            assert result["status"] == "success", result
            assert {row["value"] for row in result["rows"]} == {5, 453}, result
            checks.append("real LM Studio through production proxy: 5 direct / 453 indirect")
            debug = client.get(f"/api/debug/runs/{result['debug_run_id']}").json()
            nodes = {node["key"]: node for node in debug["nodes"]}
            assert debug["status"] == "success"
            assert nodes["model"]["input"]["request"]["model"] == "hr-qwen"
            assert nodes["model"]["output"]["http_status"] == 200
            assert nodes["schema"]["output"]["valid"] is True
            assert nodes["database"]["output"]["row_count"] == 2
            assert debug["result"]["rows"] == result["rows"]
            checks.append(
                "real model input/output, schema validation, SQL rows and final response visible in debug"
            )
    report = {"passed": True, "mode": "production-http", "live_model": args.model, "checks": checks}
    filename = "http-smoke.json" if args.model else "http-smoke-ci.json"
    output = Path(__file__).resolve().parents[1] / "reports" / filename
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(output.read_text())


if __name__ == "__main__":
    main()
