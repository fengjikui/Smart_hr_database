import json

import pytest
from fastapi import HTTPException

from backend.hr import config
from backend.hr.v2 import auth, query, reference, service, store
from backend.hr.v2.schema import Plan

PLANS = json.loads((config.PROJECT / "evaluation/demo-v2-plans.json").read_text())["plans"]


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "APP_DB", tmp_path / "app.sqlite")
    store.ensure()


def persona(case):
    return next(
        p for p in store.PERSONAS if p["id"] == {"HR-01": "manager", "HR-02": "hrbp"}.get(case, "hr_lead")
    )


@pytest.mark.parametrize("case", PLANS)
def test_twenty_queries_against_independent_person_reference(case):
    plan = Plan.model_validate(PLANS[case])
    p = persona(case)
    result = query.execute(p, plan)
    ref = reference.calculate(p, plan)
    assert result["_all_rows"] == ref["rows"]
    assert result["totals"] == ref["totals"]
    assert service.reconcile(p, plan)["passed"]


def test_all_pages_filter_and_total_consistency():
    p = persona("HR-10")
    all_rows = query.execute(p, Plan(kind="people", columns=["employee_no", "name", "age"], page_size=200))
    second = query.execute(
        p, Plan(kind="people", columns=["employee_no", "name", "age"], page=2, page_size=200)
    )
    full = all_rows["rows"] + second["rows"]
    assert len(full) == all_rows["total_rows"] == 226
    assert len({r["employee_no"] for r in full}) == 226
    filtered = query.execute(
        p,
        Plan(
            kind="people",
            columns=["employee_no", "age"],
            filters=[{"field": "age", "op": "gte", "values": ["40"]}],
            order_by=[{"field": "age", "direction": "desc"}],
            page_size=10,
        ),
    )
    expected = [r for r in full if r["age"] is not None and r["age"] >= 40]
    assert filtered["total_rows"] == len(expected) > 10
    assert filtered["totals"]["count"] == len(expected)
    assert filtered["rows"][0]["age"] == max(r["age"] for r in expected)


def test_scope_intersection_and_sensitive_dependencies():
    p = next(p for p in store.PERSONAS if p["id"] == "manager")
    with pytest.raises(HTTPException):
        query.execute(p, Plan(departments=["企业销售部"]))
    with pytest.raises(HTTPException):
        query.execute(
            p,
            Plan(
                kind="people", columns=["name"], order_by=[{"field": "contract_end_date", "direction": "asc"}]
            ),
        )
    with pytest.raises(HTTPException):
        query.execute(p, Plan(filters=[{"field": "contract_end_date", "values": ["2026-09-12"]}]))
    with pytest.raises(HTTPException):
        query.execute(
            p,
            Plan(
                date_field="employment_events",
                start_date="2026-01-01",
                end_date=store.AS_OF,
                metrics=["departures"],
            ),
        )


def test_history_owner_data_and_policy_revocation():
    p = persona("HR-10")
    plan = Plan.model_validate(PLANS["HR-10"])
    saved = service.save_run(p, "学校统计", service.run_query(p, plan))
    assert service.read_run(p, saved["id"])["plan"] == plan.model_dump()
    with pytest.raises(HTTPException):
        service.read_run(next(p for p in store.PERSONAS if p["id"] == "hrbp"), saved["id"])
    policy = store.policy()
    policy["roles"]["hr_lead"]["inherit_hrbp"] = False
    auth.apply_policy(store.PERSONAS[-1], auth.PolicyChange(expected_version=1, roles=policy["roles"]))
    assert service.history(p) == []
    with pytest.raises(HTTPException):
        service.read_run(p, saved["id"])


def test_result_summary_uses_verified_numerator_denominator():
    result = service.run_query(persona("HR-15"), Plan.model_validate(PLANS["HR-15"]))
    assert str(result["totals"]["count"]) in result["summary"]
    assert (
        f"{result['totals']['masters_ratio_numerator']}/{result['totals']['masters_ratio_denominator']}"
        in result["summary"]
    )
    assert "_all_rows" not in result


def test_drill_dept_ratio_and_month():
    p = persona("HR-09")
    plan = Plan.model_validate(PLANS["HR-09"])
    result = query.execute(p, plan)
    row = result["rows"][0]
    group = {"dept_cn_name": row["dept_cn_name"]}
    detail = service.drill_plan(p, plan, group, "school_985_ratio")
    assert query.execute(p, detail)["total_rows"] == row["school_985_ratio_numerator"]
    plan = Plan.model_validate(PLANS["HR-07"])
    row = query.execute(p, plan)["rows"][0]
    detail = service.drill_plan(p, plan, {k: row[k] for k in plan.group_by}, "hires")
    assert query.execute(p, detail)["total_rows"] == row["hires"]


def test_unknown_education_and_zero_months():
    result = query.execute(persona("HR-11"), Plan.model_validate(PLANS["HR-11"]))
    assert any(r["diploma_code_desc"] == "未知" for r in result["rows"])
    assert sum(r["count"] for r in result["rows"]) == result["totals"]["count"]
    result = query.execute(persona("HR-06"), Plan.model_validate(PLANS["HR-06"]))
    assert len(result["rows"]) == 16
    assert any(r["departures"] == 0 for r in result["rows"])


def test_data_change_revokes_history():
    p = persona("HR-10")
    result = service.save_run(p, "记录", service.run_query(p, Plan()))
    with store.connection("people") as db:
        db.execute("UPDATE people SET name='新姓名' WHERE person_id='P0005'")
    with pytest.raises(HTTPException):
        service.read_run(p, result["id"])


def test_sql_values_do_not_become_sql():
    p = persona("HR-10")
    result = query.execute(p, Plan(filters=[{"field": "name", "op": "eq", "values": ["' OR 1=1 --"]}]))
    assert result["totals"]["count"] == 0
    assert "' OR 1=1 --" not in result["sql"]
    assert len(store.people()) == 300
