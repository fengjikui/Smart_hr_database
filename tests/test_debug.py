import asyncio
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.hr import agent, config
from backend.hr.api import _limits, app
from backend.hr.db import application
from backend.hr.debug import DebugRun, recover_interrupted
from backend.hr.seed import initialize_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    path = tmp_path / "app.sqlite"
    initialize_app(path)
    monkeypatch.setattr(config, "APP_DB", path)
    _limits.clear()
    with TestClient(app) as client:
        yield client


def mock_model(monkeypatch, answers):
    values = iter(answers)
    original = httpx.AsyncClient

    def handle(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "hr-qwen"}]})
        item = next(values)
        if isinstance(item, Exception):
            raise item
        message = (
            item
            if isinstance(item, dict) and "reasoning_content" in item
            else {"content": item if isinstance(item, str) else json.dumps(item)}
        )
        return httpx.Response(
            200,
            json={
                "model": "hr-qwen",
                "choices": [{"message": message, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 50, "completion_tokens": 20},
            },
        )

    monkeypatch.setattr(
        agent.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs)
    )


def login(client, who="employee"):
    client.post("/api/demo/session", json={"persona_id": who}).raise_for_status()
    return {"X-CSRF-Token": client.get("/api/bootstrap").json()["principal"]["csrf"]}


def chat(client, headers, question="我有多少人？"):
    return client.post("/api/chat", headers=headers, json={"question": question})


def trace(client, response):
    run_id = response.json().get("debug_run_id") or response.headers["X-Debug-Run-Id"]
    result = client.get(f"/api/debug/runs/{run_id}")
    assert result.status_code == 200, result.text
    return result.json()


def test_actual_nodes_capture_model_sql_and_results(client, monkeypatch):
    mock_model(monkeypatch, [{"metric": "headcount", "period": "as_of"}])
    headers = login(client)
    response = chat(client, headers)
    assert response.status_code == 200
    run = trace(client, response)
    nodes = {n["key"]: n for n in run["nodes"]}
    assert run["status"] == "success"
    assert run["result"]["rows"][0]["value"] == 1
    assert nodes["model"]["input"]["request"]["messages"][1]["content"] == "我有多少人？"
    assert nodes["model"]["output"]["response"]["metric"] == "headcount"
    assert nodes["schema"]["output"]["valid"]
    assert nodes["compile"]["output"]["filtered_employee_ids"] == [52]
    assert nodes["database"]["input"]["parameters"]["s0"] == 52
    assert nodes["database"]["output"]["rows"][0]["value"] == 1
    assert nodes["format"]["output"]["period"]["end"] == "2026-09-11"
    assert all(n["status"] == "success" and n["duration_ms"] > 0 for n in run["nodes"])
    assert headers["X-CSRF-Token"] not in json.dumps(run)


def test_unsupported_filter_stops_before_model(client, monkeypatch):
    mock_model(monkeypatch, [])
    response = chat(client, login(client), "女性员工多少人")
    assert response.status_code == 422
    run = trace(client, response)
    assert run["status"] == "blocked"
    assert [n["key"] for n in run["nodes"]] == ["request", "authorization", "capability"]
    assert run["nodes"][-1]["error"]["status_code"] == 422


def test_timeout_has_failed_model_node_and_no_sql(client, monkeypatch):
    mock_model(monkeypatch, [httpx.ReadTimeout("model timeout")])
    response = chat(client, login(client))
    assert response.status_code == 504
    run = trace(client, response)
    assert run["nodes"][-1]["key"] == "model"
    assert run["nodes"][-1]["error"]["type"] == "ReadTimeout"
    assert run["status"] == "error"


def test_retry_keeps_both_model_inputs_and_validation_error(client, monkeypatch):
    mock_model(monkeypatch, [{"metric": "invented"}, {"metric": "headcount", "period": "as_of"}])
    response = chat(client, login(client))
    run = trace(client, response)
    assert run["status"] == "success"
    models = [n for n in run["nodes"] if n["key"] == "model"]
    assert len(models) == 2
    assert len(models[1]["input"]["request"]["messages"]) == 3
    failures = [n for n in run["nodes"] if n["status"] == "error"]
    assert failures[0]["error"]["issues"][0]["loc"] == ["metric"]


def test_invalid_json_and_reasoning_prose_are_not_disclosed(client, monkeypatch):
    mock_model(
        monkeypatch, [{"content": "", "reasoning_content": "INTERNAL_REASONING_SECRET"}, "invalid json"]
    )
    response = chat(client, login(client))
    assert response.status_code == 503
    run = trace(client, response)
    assert "INTERNAL_REASONING_SECRET" not in json.dumps(run)
    assert len([n for n in run["nodes"] if n["key"] == "schema"]) == 2
    assert not any(n["key"] == "database" for n in run["nodes"])


def test_structured_reasoning_channel_only_exposes_json(client, monkeypatch):
    mock_model(
        monkeypatch,
        [
            {
                "content": "",
                "reasoning_content": '<think>INTERNAL_SECRET</think>{"metric":"headcount","period":"as_of"}',
            }
        ],
    )
    response = chat(client, login(client))
    run = trace(client, response)
    assert run["status"] == "success"
    assert "INTERNAL_SECRET" not in json.dumps(run)
    assert next(n for n in run["nodes"] if n["key"] == "model")["output"]["response"]["metric"] == "headcount"


def test_owner_and_live_grant_checks(client, monkeypatch):
    mock_model(monkeypatch, [{"metric": "headcount"}])
    response = chat(client, login(client, "rd"))
    run_id = response.json()["debug_run_id"]
    login(client, "ceo")
    assert client.get(f"/api/debug/runs/{run_id}").status_code == 404
    login(client, "rd")
    with application() as db:
        db.execute("UPDATE principals SET scope_mode='self',policy_version=policy_version+1 WHERE id='rd'")
    assert client.get(f"/api/debug/runs/{run_id}").status_code == 404
    assert client.get("/api/debug/runs").json()["runs"] == []


def test_salary_raw_aggregate_never_enters_debug(client, monkeypatch):
    mock_model(monkeypatch, [{"metric": "avg_salary", "period": "as_of", "dimension": "division"}])
    response = chat(client, login(client, "ceo"), "按事业部统计基本月薪均值")
    run = trace(client, response)
    nodes = {n["key"]: n for n in run["nodes"]}
    assert nodes["database"]["output"]["rows"] is None
    assert nodes["protection"]["output"]["suppressed_groups"] >= 2
    for source in [
        nodes["protection"]["output"],
        nodes["format"]["input"],
        nodes["format"]["output"],
        run["result"],
    ]:
        protected = [r for r in source["rows"] if r.get("protected")]
        assert protected and all(r["value"] is None and r["sample_size"] is None for r in protected)


def test_running_node_visible_before_model_finishes(client, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    original = httpx.AsyncClient

    async def handle(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": []})
        entered.set()
        await asyncio.to_thread(release.wait, 3)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"metric":"headcount"}'}, "finish_reason": "stop"}]},
        )

    monkeypatch.setattr(
        agent.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs)
    )
    headers = login(client)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(chat, client, headers)
        try:
            assert entered.wait(2)
            run_id = client.get("/api/debug/runs").json()["runs"][0]["id"]
            run = client.get(f"/api/debug/runs/{run_id}").json()
            assert run["status"] == "running"
            assert run["nodes"][-1]["key"] == "model"
            assert run["nodes"][-1]["status"] == "running"
        finally:
            release.set()
        assert pending.result(timeout=3).status_code == 200


def test_schema_inventory_covers_actual_fields_and_expressions(client, monkeypatch):
    mock_model(monkeypatch, [])
    login(client, "ceo")
    response = client.get("/api/data-dictionary")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["summary"]["business_tables"] == 24
    assert result["summary"]["application_tables"] == 8
    assert len(result["metrics"]) == 17
    people = next(t for t in result["tables"] if t["name"] == "employees")
    assert len(people["fields"]) == 17
    assert people["row_count"] == 480
    assert "CHECK" in people["create_sql"]
    assert people["indexes"] and people["foreign_keys"]
    assert all(m["sql_expression"] and m["example_sql"] for m in result["metrics"])
    login(client, "rd")
    assert client.get("/api/data-dictionary").status_code == 403


def test_debug_endpoints_require_authentication(client):
    for path in ["/api/debug/runs", "/api/debug/runs/unknown", "/api/data-dictionary"]:
        assert client.get(path).status_code == 401


def test_restart_marks_incomplete_and_retention_is_bounded(client):
    with application() as db:
        principal = dict(db.execute("SELECT * FROM principals WHERE id='employee'").fetchone())
    unfinished = DebugRun(principal, "未完成查询")
    recover_interrupted()
    with application() as db:
        assert (
            db.execute("SELECT status FROM debug_runs WHERE id=?", (unfinished.id,)).fetchone()[0]
            == "interrupted"
        )
    for i in range(51):
        DebugRun(principal, f"测试{i}").finish("success")
    with application() as db:
        assert db.execute("SELECT COUNT(*) FROM debug_runs WHERE owner_id='employee'").fetchone()[0] == 50


@pytest.mark.parametrize("candidate", [{}, {"kind": "metric"}])
def test_empty_model_plan_must_retry_instead_of_default_headcount(client, monkeypatch, candidate):
    mock_model(monkeypatch, [candidate, {"metric": "headcount", "period": "as_of"}])
    response = chat(client, login(client))
    run = trace(client, response)
    assert response.status_code == 200
    assert len([n for n in run["nodes"] if n["key"] == "model"]) == 2
    assert any(n["key"] == "schema" and n["status"] == "error" for n in run["nodes"])
