import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from backend.hr import config
from backend.hr.db import application
from backend.hr.models import QueryPlan
from backend.hr.query import execute
from backend.hr.security import scope_ids
from backend.hr.seed import initialize_app


@pytest.fixture(autouse=True)
def isolated_application(tmp_path, monkeypatch):
    path = tmp_path / "app.sqlite"
    initialize_app(path)
    monkeypatch.setattr(config, "APP_DB", path)


def principal(name):
    with application() as db:
        return dict(db.execute("SELECT * FROM principals WHERE id=?", (name,)).fetchone())


def test_ceo_scope_matches_independent_manager_walk():
    ceo = principal("ceo")
    direct = scope_ids(ceo, "direct")
    indirect = scope_ids(ceo, "indirect")
    assert len(direct) == 5
    assert len(indirect) == 474
    assert set(direct).isdisjoint(indirect)
    assert len(scope_ids(ceo)) == 480


def test_headcount_matches_database_and_groups_sum():
    p = principal("ceo")
    total = execute(p, QueryPlan(metric="headcount"))["rows"][0]["value"]
    grouped = execute(p, QueryPlan(metric="headcount", dimension="division"))["rows"]
    assert total == 459
    assert sum(r["value"] for r in grouped) == total


def test_manager_cannot_reach_other_divisions():
    p = principal("rd")
    assert set(scope_ids(p)) < set(scope_ids(principal("ceo")))
    with pytest.raises(HTTPException) as exc:
        execute(p, QueryPlan(department="企业销售部"))
    assert exc.value.status_code == 403


def test_private_field_not_a_plan_capability():
    with pytest.raises(ValidationError):
        QueryPlan.model_validate({"metric": "headcount", "sql": "select * from employee_private"})
    with pytest.raises(ValidationError):
        QueryPlan.model_validate({"dimension": "monthly_base"})


def test_salary_is_bound_to_role_and_safe_query_shape():
    with pytest.raises(HTTPException):
        execute(principal("rd"), QueryPlan(metric="avg_salary"))
    with pytest.raises(HTTPException):
        execute(principal("ceo"), QueryPlan(metric="avg_salary", employee_name="林知远"))
    result = execute(principal("ceo"), QueryPlan(metric="avg_salary", dimension="division"))
    assert any(r.get("protected") for r in result["rows"])
    assert all(r["value"] is None for r in result["rows"] if r.get("protected"))


@pytest.mark.parametrize(
    "metric",
    [
        "headcount",
        "hires",
        "departures",
        "turnover_rate",
        "avg_tenure",
        "attendance_rate",
        "late_count",
        "late_rate",
        "abnormal_count",
        "approved_overtime_hours",
        "late_departure_hours",
        "avg_work_hours",
        "leave_days",
    ],
)
def test_metrics_compile_and_are_finite(metric):
    result = execute(principal("ceo"), QueryPlan(metric=metric, dimension="division"))
    assert result["status"] == "success"
    assert all(r["value"] is None or r["value"] >= 0 for r in result["rows"])


def test_overtime_never_equals_observed_late_departure_by_default():
    p = principal("ceo")
    approved = execute(p, QueryPlan(metric="approved_overtime_hours"))["rows"][0]["value"]
    observed = execute(p, QueryPlan(metric="late_departure_hours"))["rows"][0]["value"]
    assert 0 < approved < observed


def test_employee_only_sees_self_in_details():
    result = execute(principal("employee"), QueryPlan(kind="people"))
    assert [r["employee_no"] for r in result["rows"]] == ["CC00052"]
    assert not any("salary" in k or "phone" in k for k in result["rows"][0])


def test_history_trend_has_six_distinct_snapshots():
    result = execute(principal("ceo"), QueryPlan(dimension="month", period="last_6_months"))
    assert len(result["rows"]) == 6
    assert result["rows"][-1]["value"] == 459


def test_future_query_is_rejected():
    with pytest.raises(HTTPException):
        execute(principal("ceo"), QueryPlan(period="custom", start_date="2099-01-01", end_date="2099-01-02"))


def test_daily_attendance_compiled_cte_is_readable():
    result = execute(principal("ceo"), QueryPlan(metric="late_count", dimension="day"))
    assert len(result["rows"]) == 9
    assert (
        sum(r["value"] for r in result["rows"])
        == execute(principal("ceo"), QueryPlan(metric="late_count"))["rows"][0]["value"]
    )


def test_salary_complementary_suppression_blocks_total_subtraction():
    result = execute(principal("ceo"), QueryPlan(metric="avg_salary", dimension="division"))
    assert result["suppressed_groups"] >= 2
    assert sum(bool(r.get("protected")) for r in result["rows"]) >= 2
