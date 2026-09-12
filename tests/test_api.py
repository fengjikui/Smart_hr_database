import json

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.hr import config
from backend.hr.api import _limits, app
from backend.hr.db import application, business
from backend.hr.seed import initialize_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    path = tmp_path / "app.sqlite"
    initialize_app(path)
    monkeypatch.setattr(config, "APP_DB", path)
    _limits.clear()
    with TestClient(app) as c:
        yield c


def login(client, who="ceo"):
    assert client.post("/api/demo/session", json={"persona_id": who}).status_code == 200
    result = client.get("/api/bootstrap").json()
    return {"X-CSRF-Token": result["principal"]["csrf"]}


@pytest.mark.parametrize(
    "path",
    [
        "/api/bootstrap",
        "/api/overview",
        "/api/catalog",
        "/api/organization",
        "/api/dashboards",
        "/api/governance",
    ],
)
def test_all_data_endpoints_require_identity(client, path):
    assert client.get(path).status_code == 401


def test_cross_origin_and_unknown_hosts_rejected(client):
    assert (
        client.post(
            "/api/demo/session", headers={"Origin": "https://evil.example"}, json={"persona_id": "ceo"}
        ).status_code
        == 403
    )
    assert client.get("/api/health", headers={"Host": "evil.example"}).status_code == 400


def test_csrf_and_input_whitelist(client):
    headers = login(client)
    assert client.post("/api/query", json={"metric": "headcount"}).status_code == 403
    assert (
        client.post(
            "/api/query",
            headers=headers,
            json={"metric": "headcount", "sql": "SELECT * FROM employee_private"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/query", headers=headers, json={"metric": "headcount", "dimension": "monthly_base"}
        ).status_code
        == 422
    )
    assert (
        client.post("/api/query", headers=headers, json={"metric": "headcount", "limit": 999999}).status_code
        == 422
    )


def test_overview_works_without_inference(client):
    login(client)
    response = client.get("/api/overview")
    assert response.status_code == 200, response.text
    assert len(response.json()["kpis"]) == 4
    assert response.json()["kpis"][0]["rows"][0]["value"] == 459


def test_permission_scope_is_not_taken_from_client_headers(client):
    headers = login(client, "employee")
    response = client.post(
        "/api/query",
        headers={**headers, "X-Role": "executive", "X-Employee-Id": "1"},
        json={"kind": "people"},
    )
    assert response.status_code == 200
    assert [r["employee_no"] for r in response.json()["rows"]] == ["CC00052"]
    assert client.post("/api/query", headers=headers, json={"metric": "avg_salary"}).status_code == 403
    assert client.post("/api/export", headers=headers, json={"metric": "headcount"}).status_code == 403


def test_catalog_and_org_do_not_reveal_unauthorized_data(client):
    login(client, "employee")
    metrics = client.get("/api/catalog").json()["metrics"]
    assert "avg_salary" not in {m["id"] for m in metrics}
    org = client.get("/api/organization").json()
    assert len(org["people"]["rows"]) == 1
    assert not any(d["name"] == "企业销售部" for d in org["departments"])
    assert client.get("/api/governance").status_code == 403


def test_dashboards_are_personal_and_plans_are_reexecuted(client):
    headers = login(client, "ceo")
    saved = client.post(
        "/api/dashboards", headers=headers, json={"title": "人数", "plan": {"metric": "headcount"}}
    )
    assert saved.status_code == 201
    ident = saved.json()["id"]
    board = client.get("/api/dashboards").json()["dashboards"][0]
    assert board["result"]["rows"][0]["value"] == 459
    with application() as db:
        stored = dict(db.execute("SELECT * FROM dashboards WHERE id=?", (ident,)).fetchone())
    assert "rows" not in json.loads(stored["plan"])
    headers = login(client, "rd")
    assert client.get("/api/dashboards").json()["dashboards"] == []
    assert client.delete("/api/dashboards/" + ident, headers=headers).status_code == 404


def test_revocation_applies_to_saved_dashboard_on_next_request(client):
    headers = login(client)
    client.post(
        "/api/dashboards",
        headers=headers,
        json={"title": "薪资", "plan": {"metric": "avg_salary", "dimension": "division"}},
    )
    with application() as db:
        db.execute("UPDATE principals SET salary_aggregate=0,policy_version=2 WHERE id='ceo'")
    board = client.get("/api/dashboards").json()["dashboards"][0]
    assert board["result"] is None
    assert "权限" in board["error"]


def test_disabled_principal_and_expired_session(client):
    login(client)
    with application() as db:
        db.execute("UPDATE principals SET enabled=0 WHERE id='ceo'")
    assert client.get("/api/overview").status_code == 401


def test_read_only_business_connection_rejects_writes():
    import sqlite3

    with business() as db:
        with pytest.raises(sqlite3.OperationalError):
            db.execute("UPDATE employees SET name='bad' WHERE id=1")


def test_csv_export_and_caching_headers(client):
    headers = login(client)
    response = client.post(
        "/api/export", headers=headers, json={"metric": "headcount", "dimension": "division"}
    )
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "no-store" in response.headers["cache-control"]
    assert response.text.startswith("\ufeff")
    assert "产品研发事业部" in response.text


def test_agent_failure_is_visible_and_does_not_fabricate_answer(client, monkeypatch):
    async def unavailable(*args, **kwargs):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr("backend.hr.agent.ask_model", unavailable)
    headers = login(client)
    response = client.post("/api/chat", headers=headers, json={"question": "有多少人？"})
    assert response.status_code == 503
    assert "未执行数据库查询" in response.json()["detail"]


def test_agent_cannot_use_another_personas_conversation(client):
    headers = login(client, "rd")
    with application() as db:
        db.execute(
            "INSERT INTO conversations VALUES (?,?,?,?,?,?)",
            ("foreign", "ceo", "人数", '{"metric":"headcount"}', "success", "2026-09-11"),
        )
    response = client.post(
        "/api/chat", headers=headers, json={"question": "再按部门", "previous_id": "foreign"}
    )
    assert response.status_code == 404


def test_unsupported_filter_is_not_silently_dropped(client, monkeypatch):
    async def must_not_run(*args, **kwargs):
        raise AssertionError("unsupported condition should be checked before inference")

    monkeypatch.setattr("backend.hr.agent.ask_model", must_not_run)
    headers = login(client)
    response = client.post("/api/chat", headers=headers, json={"question": "按部门和性别统计人数"})
    assert response.status_code == 422
    assert "没有忽略" in response.json()["detail"]


def test_detail_intent_preserves_scope_and_time(client, monkeypatch):
    from backend.hr.models import QueryPlan

    async def mistaken_plan(*args, **kwargs):
        return QueryPlan(metric="abnormal_count", dimension="day", relation="self"), {}

    monkeypatch.setattr("backend.hr.agent.ask_model", mistaken_plan)
    headers = login(client, "employee")
    response = client.post("/api/chat", headers=headers, json={"question": "查看我本月的考勤异常明细"})
    assert response.status_code == 200
    assert response.json()["plan"]["kind"] == "attendance"
    assert response.json()["plan"]["relation"] == "self"
    assert all(r["employee_no"] == "CC00052" for r in response.json()["rows"])
