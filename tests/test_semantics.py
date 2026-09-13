import json

import pytest
from fastapi import HTTPException
from test_debug import chat, login, mock_model, trace
from test_debug import client as client

from backend.hr import config, semantics, workflow
from backend.hr.data_dictionary import inventory
from backend.hr.db import application


def principal(who="ceo"):
    with application() as db:
        return dict(db.execute("SELECT * FROM principals WHERE id=?", (who,)).fetchone())


def test_registry_exactly_covers_schema_and_references(client):
    docs = semantics.all_documents(principal())
    fields = {d["id"]: d for d in docs if d["kind"] == "field"}
    schema = inventory(principal())
    actual = {f"{t['name']}.{f['name']}" for t in schema["tables"] for f in t["fields"]}
    assert set(fields) == actual
    assert len(fields) == 200
    assert len([d for d in docs if d["kind"] == "table"]) == 35
    assert len([d for d in docs if d["kind"] == "metric"]) == 32
    assert len([d for d in docs if d["kind"] == "question"]) == 160
    assert len({d["id"] for d in docs}) == len(docs)
    for d in docs:
        assert d["meaning"] and d["not_meaning"]
        if d["kind"] in ("metric", "field"):
            assert len(d["aliases"]) >= 2
        for ident in d.get("field_ids", []):
            assert ident in fields
    for f in fields.values():
        assert f["id"] == f["table_id"] + "." + f["field_id"]
        assert f["examples_policy"]
    assert len({f["meaning"] for f in fields.values()}) > 150


def test_metadata_and_salary_are_permission_filtered(client):
    login(client, "employee")
    listing = client.get("/api/semantics").json()
    ids = {d["id"] for d in listing["documents"]}
    assert "metric:headcount" in ids
    assert "metric:avg_salary" not in ids
    assert "sessions.token_hash" not in ids
    for ident in ("metric:avg_salary", "compensation.monthly_base", "sessions.token_hash", "invented.field"):
        response = client.get("/api/semantics/documents/" + ident)
        assert response.status_code == 404
    login(client, "ceo")
    assert client.get("/api/semantics/documents/sessions.token_hash").status_code == 200
    with pytest.raises(HTTPException) as failure:
        semantics.read_documents(principal(), ["sessions.token_hash"], model=True)
    assert failure.value.status_code == 404


def test_registry_idempotent_and_revision_pinned(client):
    rev = semantics.publish()
    timestamp = semantics.database_path().stat().st_mtime_ns
    assert semantics.publish() == rev
    assert semantics.database_path().stat().st_mtime_ns == timestamp
    with pytest.raises(HTTPException) as failure:
        semantics.read_documents(principal(), ["metric:headcount"], model=True, revision="stale")
    assert failure.value.status_code == 409
    assert semantics.database_path().parent == config.APP_DB.parent


@pytest.mark.parametrize(
    ("question", "metric"),
    [
        ("咱们公司眼下多少人", "headcount"),
        ("这个月办入职手续的有几位", "hires"),
        ("本月批准的额外工作时长有多久", "approved_overtime_hours"),
        ("本月大家晚离岗了多久", "late_departure_hours"),
        ("最近员工请了几天假", "leave_days"),
        ("这一季度新来多少博士", "hires"),
        ("部门里研究生占比呢", "education_ratio"),
        ("这月打卡迟到累计几次", "late_count"),
        ("最近一个月出勤率怎么样", "attendance_rate"),
        ("今年各部门进出人员和净增一起看", "workforce_changes"),
        ("周六周日加班一共多长时间", "weekend_overtime_hours"),
        ("现在平均司龄几个月", "avg_tenure"),
        ("本月离职率多少", "turnover_rate"),
        ("基本月薪均值按事业部看", "avg_salary"),
    ],
)
def test_colloquial_retrieval_regressions(question, metric, client):
    from backend.hr.intent import explicit_constraints

    constraints, _ = explicit_constraints(question)
    result = semantics.discover(principal(), question, constraints)
    assert "metric:" + metric in result["initial_ids"], result["hits"]


def test_explicit_metadata_loop_is_real_and_bounded(client, monkeypatch):
    mock_model(
        monkeypatch,
        [{"kind": "inspect", "ids": ["metric:headcount"]}, {"metric": "headcount", "period": "as_of"}],
    )
    response = chat(client, login(client))
    assert response.status_code == 200, response.text
    run = trace(client, response)
    assert response.json()["orchestration"]["metadata_expansions"] == 1
    assert response.json()["orchestration"]["model_calls"] == 2
    keys = [n["key"] for n in run["nodes"]]
    assert keys.count("disclosure") == 2
    assert keys.index("inspection") < keys.index("database")
    assert run["result"]["rows"][0]["value"] == 1
    assert "sessions" not in json.dumps(
        next(n for n in run["nodes"] if n["key"] == "model")["input"]["request"]["messages"]
    )


def test_unread_metric_automatically_disclosed_and_replanned(client, monkeypatch):
    mock_model(
        monkeypatch,
        [{"metric": "avg_tenure", "period": "as_of"}, {"metric": "avg_tenure", "period": "as_of"}],
    )
    response = chat(client, login(client))
    assert response.status_code == 200, response.text
    assert response.json()["orchestration"]["metadata_expansions"] == 1
    assert "metric:avg_tenure" in response.json()["orchestration"]["disclosed_ids"]


def test_repeated_inspection_ends_without_sql(client, monkeypatch):
    mock_model(monkeypatch, [{"kind": "inspect", "ids": ["metric:headcount"]}] * 3)
    response = chat(client, login(client))
    assert response.json()["status"] == "clarify"
    assert response.json()["orchestration"]["model_calls"] == 3
    assert response.json()["orchestration"]["metadata_expansions"] == 2
    assert not any(n["key"] == "database" for n in trace(client, response)["nodes"])


@pytest.mark.parametrize("ident", ["metric:avg_salary", "sessions.token_hash", "invented.field"])
def test_model_inspection_cannot_read_unauthorized_ids(client, monkeypatch, ident):
    mock_model(monkeypatch, [{"kind": "inspect", "ids": [ident]}])
    response = chat(client, login(client))
    assert response.status_code == 404
    assert not any(n["key"] == "database" for n in trace(client, response)["nodes"])


def test_planned_metric_is_disclosed_but_never_compiled(client, monkeypatch):
    mock_model(monkeypatch, [])
    response = chat(client, login(client, "ceo"), "今年新员工90天留存率")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "clarify"
    assert response.json()["orchestration"]["model_calls"] == 0
    assert not any(n["key"] == "database" for n in trace(client, response)["nodes"])


def test_inspect_is_not_a_direct_query_plan(client):
    headers = login(client)
    assert (
        client.post(
            "/api/query", headers=headers, json={"kind": "inspect", "ids": ["metric:headcount"]}
        ).status_code
        == 422
    )


def test_workflow_descriptor_is_compiled_graph(client):
    assert client.get("/api/workflow").status_code == 401
    login(client)
    result = client.get("/api/workflow").json()
    assert result["framework"] == "LangGraph"
    assert len(result["nodes"]) == 14
    assert {"source": "inspect", "target": "model", "conditional": True} in result["edges"]
    assert result["external_tracing"] is False
    assert workflow.graph.checkpointer is None


def test_revocation_during_model_prevents_execution(client, monkeypatch):
    from backend.hr import agent
    from backend.hr.models import QueryPlan

    async def revoke(messages):
        with application() as db:
            db.execute("UPDATE principals SET enabled=0 WHERE id='employee'")
        return QueryPlan(metric="headcount", period="as_of"), {}

    monkeypatch.setattr(agent, "ask_model", revoke)
    response = chat(client, login(client))
    assert response.status_code == 403
    with application() as db:
        payload = json.loads(
            db.execute("SELECT payload FROM debug_runs ORDER BY started_at DESC LIMIT 1").fetchone()[0]
        )
    assert not any(n["key"] == "database" for n in payload["nodes"])


def test_one_repair_plus_two_inspections_is_maximum_four_calls(client, monkeypatch):
    mock_model(
        monkeypatch,
        [
            "invalid",
            {"kind": "inspect", "ids": ["metric:headcount"]},
            {"kind": "inspect", "ids": ["metric:headcount"]},
            {"metric": "headcount", "period": "as_of"},
        ],
    )
    response = chat(client, login(client))
    assert response.status_code == 200, response.text
    assert response.json()["orchestration"]["model_calls"] == 4
    assert response.json()["orchestration"]["repairs"] == 1
    assert response.json()["orchestration"]["metadata_expansions"] == 2


async def test_env_cannot_enable_remote_tracing(monkeypatch):
    from langsmith.run_helpers import get_tracing_context

    monkeypatch.setenv("LANGSMITH_TRACING", "true")

    async def observe(state, config):
        assert get_tracing_context()["enabled"] is False
        assert config["recursion_limit"] == 32
        return {"output": {"status": "tested"}}

    monkeypatch.setattr(workflow.graph, "ainvoke", observe)
    assert await workflow.run({}, "test") == {"status": "tested"}


def test_unknown_or_mixed_education_conditions_never_dropped(client, monkeypatch):
    mock_model(monkeypatch, [])
    response = chat(client, login(client, "ceo"), "各部门本科和硕士合起来有多少人")
    assert response.status_code == 422


def test_average_daily_work_is_not_a_second_grouping_dimension(client):
    from backend.hr.intent import explicit_constraints

    constraints, _ = explicit_constraints("各部门平均每天净工时")
    assert constraints["dimension"] == "department"


@pytest.mark.parametrize("phrase", ["至少是硕士研究生", "不低于硕士", "至少为本科"])
def test_minimum_education_phrasing_preserves_range(client, phrase):
    from backend.hr.intent import explicit_constraints

    constraints, _ = explicit_constraints(f"按部门看看现在学历{phrase}的员工占比")
    assert constraints["minimum_education"] == ("本科" if "本科" in phrase else "硕士研究生")
    assert constraints["degree"] is None
    assert constraints["metric"] == "education_ratio"
