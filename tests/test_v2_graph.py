import json

import pytest

from backend.hr import config
from backend.hr.v2 import auth, graph, service, store
from backend.hr.v2.schema import Plan, Question


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "APP_DB", tmp_path / "app.sqlite")
    store.ensure()


@pytest.mark.asyncio
async def test_real_graph_inspection_and_condition_repair(monkeypatch):
    calls = []

    async def model(messages):
        calls.append(messages)
        candidate = (
            {"kind": "inspect", "inspect_ids": ["people.school_name"]}
            if len(calls) == 1
            else {"kind": "aggregate", "group_by": ["dept_cn_name"], "metrics": ["count"], "filters": []}
            if len(calls) == 2
            else {
                "kind": "aggregate",
                "group_by": ["dept_cn_name"],
                "metrics": ["count"],
                "filters": [{"field": "school_name", "op": "in", "values": ["清华大学", "北京大学"]}],
            }
        )
        return candidate, {"candidate": candidate}

    monkeypatch.setattr(graph, "call_model", model)
    result = await graph.answer(
        store.PERSONAS[0], Question(question="清华大学或北京大学毕业的在职员工，按部门分别有多少？")
    )
    assert result["status"] == "success" and len(calls) == 3
    assert "按需补读" in [n["name"] for n in result["trace"]]
    assert any(n["output"].get("valid") is False for n in result["trace"])
    assert result["totals"]["count"] < 226


@pytest.mark.asyncio
async def test_policy_changed_during_model_call_rejects_execution(monkeypatch):
    async def model(messages):
        policy = store.policy()
        policy["roles"]["hr_lead"]["inherit_hrbp"] = False
        auth.apply_policy(store.PERSONAS[-1], auth.PolicyChange(expected_version=1, roles=policy["roles"]))
        return {"kind": "aggregate", "metrics": ["count"]}, {}

    monkeypatch.setattr(graph, "call_model", model)
    with pytest.raises(Exception, match="权限或数据"):
        await graph.answer(store.PERSONAS[0], Question(question="当前在职人数有多少"))
    assert not service.history(store.PERSONAS[0])


@pytest.mark.asyncio
async def test_explicit_date_binding_is_reported_not_raw_model_success(monkeypatch):
    async def model(messages):
        return {
            "kind": "aggregate",
            "metrics": ["hires", "departures", "net_change"],
            "group_by": ["dept_cn_name"],
            "date_field": None,
            "start_date": "2026-08-28",
            "end_date": "2026-09-11",
        }, {}

    monkeypatch.setattr(graph, "call_model", model)
    result = await graph.answer(store.PERSONAS[0], Question(question="过去15天各部门入职、离职和净增人数"))
    assert result["status"] == "success"
    assert result["plan"]["date_field"] == "employment_events"
    assert any(n["name"] == "明确条件绑定（规则补齐）" for n in result["trace"])
    assert result["plan"]["population"] == "all"


@pytest.mark.asyncio
async def test_history_restore_preserves_multiturn_fields(monkeypatch):
    fixtures = json.loads((config.PROJECT / "evaluation/demo-v2-plans.json").read_text())["plans"]
    ids = iter(["HR-10", "HR-19", "HR-20"])

    async def model(messages):
        return Plan.model_validate(fixtures[next(ids)]).model_dump(), {}

    monkeypatch.setattr(graph, "call_model", model)
    p = store.PERSONAS[0]
    first = await graph.answer(p, Question(question="清华大学或北京大学毕业的在职员工，按部门分别有多少？"))
    second = await graph.answer(
        p,
        Question(
            question="在刚才这些人中，只看硕士及以上、全日制员工，再按部门统计。", previous_id=first["id"]
        ),
    )
    restored = service.read_run(p, second["id"])
    final = await graph.answer(
        p,
        Question(
            question="把学校改成浙江大学，其他条件不变，并列出姓名、部门、学校、学历和专业。",
            previous_id=restored["id"],
        ),
    )
    assert final["status"] == "success"
    assert len(final["plan"]["filters"]) == 3
    assert all(r["school_name"] == "浙江大学" for r in final["rows"])
    assert {r["diploma_code_desc"] for r in final["rows"]} <= {"硕士研究生", "博士研究生"}


@pytest.mark.asyncio
async def test_missing_previous_and_failed_previous_are_not_replayed(monkeypatch):
    p = store.PERSONAS[0]
    with pytest.raises(Exception, match="记录不存在"):
        await graph.answer(p, Question(question="把学校换成浙江大学", previous_id="missing"))

    async def model(messages):
        return {"kind": "clarify", "message": "未提供考勤事实"}, {}

    monkeypatch.setattr(graph, "call_model", model)
    prior = await graph.answer(p, Question(question="上月加班总时长"))
    with pytest.raises(Exception, match="成功的历史查询"):
        await graph.answer(p, Question(question="这些人有哪些", previous_id=prior["id"]))


@pytest.mark.asyncio
async def test_doctor_degree_count_uses_graduation_cutoff(monkeypatch):
    async def model(messages):
        return {
            "kind": "aggregate",
            "metrics": ["count"],
            "group_by": ["dept_cn_name"],
            "filters": [{"field": "degree_code_desc", "op": "eq", "values": ["博士"]}],
        }, {}

    monkeypatch.setattr(graph, "call_model", model)
    with store.connection("people") as db:
        db.execute(
            "UPDATE people SET degree_code_desc='博士', education_expired_date='2027-01-01' WHERE person_id='P0004'"
        )
    result = await graph.answer(
        store.PERSONAS[0], Question(question="目前已取得博士学位的在职人数，按部门统计。")
    )
    assert result["status"] == "success" and result["plan"]["metrics"] == ["doctors_count"]
    assert service.reconcile(store.PERSONAS[0], Plan.model_validate(result["plan"]))["passed"]


@pytest.mark.asyncio
async def test_same_question_cohort_does_not_need_history(monkeypatch):
    async def model(messages):
        return {
            "kind": "aggregate",
            "metrics": ["count", "avg_confirmation_days"],
            "group_by": ["dept_cn_name"],
            "population": "confirmed",
        }, {}

    monkeypatch.setattr(graph, "call_model", model)
    result = await graph.answer(
        store.PERSONAS[0], Question(question="各部门今年已转正多少人？计算这些人从入职到转正的平均用时天数。")
    )
    assert result["status"] == "success"
    assert result["plan"]["date_field"] == "confirmation_date"


@pytest.mark.asyncio
async def test_leading_anaphor_requires_history(monkeypatch):
    async def model(messages):
        return {"kind": "aggregate", "metrics": ["count"], "group_by": ["dept_cn_name"]}, {}

    monkeypatch.setattr(graph, "call_model", model)
    result = await graph.answer(store.PERSONAS[0], Question(question="这些人按部门各多少？"))
    assert result["status"] == "clarify" and "上下文" in result["message"]
