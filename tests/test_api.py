import pytest
from fastapi.testclient import TestClient

from backend.hr import auth, config, grounding, service, store
from backend.hr.api import _limits, app
from backend.hr.schema import Plan


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "APP_DB", tmp_path / "app.sqlite")
    store.ensure()
    _limits.clear()
    c = TestClient(app, raise_server_exceptions=True)
    yield c
    c.close()


def login(client, persona="hr_lead"):
    assert client.post("/api/session", json={"persona_id": persona}).status_code == 200
    boot = client.get("/api/bootstrap").json()
    return {"X-CSRF-Token": boot["principal"]["csrf"]}


def test_single_application_startup_creates_only_current_stores(tmp_path, monkeypatch):
    """真实进入生命周期，防止旧工作台初始化在目录合并后被悄悄带回。"""
    monkeypatch.setattr(config, "APP_DB", tmp_path / "sessions.sqlite")
    _limits.clear()
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["source_fields"] == 26
        assert response.json()["query_backend"] == "sqlite"
        assert client.get("/api/v2/health").status_code == 404
        assert client.get("/api/health", headers={"Host": "untrusted.example"}).status_code == 400
    assert sorted(p.name for p in tmp_path.iterdir()) == ["people.sqlite", "sessions.sqlite"]


def test_http_session_csrf_query_and_verify(client):
    assert client.get("/api/bootstrap").status_code == 401
    headers = login(client)
    plan = {"kind": "people", "columns": ["employee_no", "name"], "page_size": 10}
    assert client.post("/api/query", json=plan).status_code == 403
    r = client.post("/api/query", headers=headers, json=plan)
    assert r.status_code == 200
    data = r.json()
    assert len(data["rows"]) == 10 and data["total_rows"] == 226
    assert set(data["rows"][0]) == {"employee_no", "name"}
    assert "_all_rows" not in data
    assert client.post("/api/verify", headers=headers, json=plan).json()["passed"]
    assert (
        client.post("/api/query", headers=headers, json={"sql": "select * from people"}).status_code == 422
    )
    assert client.post("/api/query", headers=headers, json={"columns": ["salary"]}).status_code == 422


def test_http_roles_export_and_cross_origin(client):
    headers = login(client, "employee")
    assert client.post("/api/query", headers=headers, json={}).json()["totals"]["count"] == 1
    assert client.post("/api/export", headers=headers, json={}).status_code == 403
    assert client.get("/api/policy").status_code == 403
    assert (
        client.post(
            "/api/query", headers={**headers, "Origin": "http://attacker.example"}, json={}
        ).status_code
        == 403
    )
    hr = login(client)
    exported = client.post(
        "/api/export",
        headers=hr,
        json={"kind": "people", "columns": ["employee_no", "name"], "page_size": 1},
    )
    assert exported.status_code == 200 and len(exported.text.splitlines()) == 227
    assert "'00031266" in exported.text


def test_revoked_session_cannot_continue(client):
    login(client)
    token = client.cookies.get(auth.COOKIE)
    login(client, "manager")
    old = TestClient(app)
    old.cookies.set(auth.COOKIE, token)
    assert old.get("/api/bootstrap").status_code == 401
    old.close()


@pytest.mark.parametrize("status", ["success", "clarify", "blocked"])
def test_debug_history_payload_is_owner_scoped(client, status):
    login(client)
    principal = store.PERSONAS[0]
    trace = [{"name": "测试节点", "input": {"question": "示例"}, "output": None, "duration_ms": 0}]
    result = (
        service.run_query(principal, Plan())
        if status == "success"
        else {"status": status, "message": "示例说明"}
    )
    saved = service.save_run(principal, "调试历史示例", result, trace=trace)
    path = "/api/history/" + saved["id"]
    response = client.get(path)
    assert response.status_code == 200
    assert response.json()["trace"] == trace
    assert response.json()["status"] == status
    assert any(r["id"] == saved["id"] for r in client.get("/api/history").json())
    login(client, "employee")
    assert client.get(path).status_code == 404
    assert saved["id"] not in [r["id"] for r in client.get("/api/history").json()]
    assert "测试节点" not in client.get(path).text
    client.cookies.clear()
    assert client.get(path).status_code == 401


def test_details_toggle_and_history_revocation(client):
    login(client)
    p = store.PERSONAS[0]
    saved = service.save_run(p, "示例", service.run_query(p, Plan()))
    headers = login(client, "admin")
    policy = client.get("/api/policy").json()
    policy["roles"]["hr_lead"]["details"] = False
    change = {"expected_version": policy["version"], "roles": policy["roles"]}
    assert client.post("/api/policy/preview", headers=headers, json=change).status_code == 200
    assert store.policy()["version"] == 1
    assert client.post("/api/policy/apply", headers=headers, json=change).status_code == 200
    headers = login(client)
    assert client.get("/api/history/" + saved["id"]).status_code == 404
    assert client.post("/api/query", headers=headers, json={"kind": "people"}).status_code == 403
    assert client.get("/api/relations").status_code == 403
    assert client.post("/api/query", headers=headers, json={}).status_code == 200


def test_literal_condition_guard_and_followup():
    q = "清华大学或北京大学毕业的在职员工，按部门分别有多少？"
    with pytest.raises(ValueError, match="条件未完整保留"):
        grounding.check(q, Plan())
    previous = Plan(
        filters=[
            {"field": "school_name", "op": "in", "values": ["清华大学", "北京大学"]},
            {"field": "full_time_flag", "values": ["是"]},
        ]
    ).model_dump()
    with pytest.raises(ValueError):
        grounding.check(
            "把学校改成浙江大学，其他条件不变",
            Plan(filters=[{"field": "school_name", "values": ["浙江大学"]}]),
            previous,
        )
