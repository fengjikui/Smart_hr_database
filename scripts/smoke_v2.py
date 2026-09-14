"""HTTP smoke for the built V2 frontend proxy; no inference or policy mutations."""

import argparse
import json
from pathlib import Path

import httpx


def main(base_url):
    checks = []
    with httpx.Client(
        base_url=base_url, trust_env=False, timeout=15, headers={"Accept-Encoding": "identity"}
    ) as client:

        def login(role):
            response = client.post("/api/v2/session", json={"persona_id": role})
            response.raise_for_status()
            boot = client.get("/api/v2/bootstrap")
            boot.raise_for_status()
            client.headers["X-CSRF-Token"] = boot.json()["principal"]["csrf"]
            return boot.json()

        boot = login("hr_lead")
        assert len(boot["catalog"]["fields"]) == 26
        assert boot["principal"]["count"] == 226
        checks.append("26字段目录及默认HR权限")
        plan = {
            "kind": "people",
            "columns": ["employee_no", "name", "school_name"],
            "filters": [{"field": "school_name", "op": "contains", "values": ["清华"]}],
            "page_size": 10,
        }
        r = client.post("/api/v2/query", json=plan)
        r.raise_for_status()
        data = r.json()
        assert data["total_rows"] == 41 and len(data["rows"]) == 10
        assert set(data["rows"][0]) == set(plan["columns"])
        checks.append("列筛选覆盖全部41人而非当前10条")
        v = client.post("/api/v2/verify", json=plan)
        v.raise_for_status()
        assert v.json()["passed"] and v.json()["compared_rows"] == 41
        checks.append("完整41行独立对账")
        assert client.post("/api/v2/query", json={"sql": "SELECT * FROM people"}).status_code == 422
        checks.append("自由SQL拒绝")
        boot = login("employee")
        assert boot["principal"]["count"] == 1
        assert not any(f["key"] == "contract_end_date" for f in boot["catalog"]["fields"])
        r = client.post("/api/v2/query", json={"kind": "people", "columns": ["employee_no", "name"]})
        r.raise_for_status()
        assert r.json()["rows"] == [{"employee_no": "00031266", "name": "冯基魁"}]
        assert client.post("/api/v2/export", json={}).status_code == 403
        checks.append("员工仅本人且无合同/导出权限")
        page = client.get("/demo")
        page.raise_for_status()
        assert "HR 数据工作台" in page.text
        checks.append("生产构建页面可访问")
    report = {"passed": True, "checks": checks, "base_url": base_url, "model_inference": False}
    Path("reports").mkdir(exist_ok=True)
    Path("reports/demo-v2-http.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:3000")
    main(parser.parse_args().base_url)
