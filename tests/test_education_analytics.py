import json
import sqlite3
from collections import defaultdict
from datetime import date

import pytest
from fastapi import HTTPException

from backend.hr import config
from backend.hr.catalog import publish_catalog
from backend.hr.db import application, business
from backend.hr.education import LEVELS
from backend.hr.intent import enforce, explicit_constraints
from backend.hr.models import QueryPlan
from backend.hr.query import execute, period_bounds
from backend.hr.seed import initialize_app


@pytest.fixture(autouse=True)
def isolated_app(tmp_path, monkeypatch):
    path = tmp_path / "app.sqlite"
    initialize_app(path)
    monkeypatch.setattr(config, "APP_DB", path)


def principal(who="ceo"):
    with application() as db:
        return dict(db.execute("SELECT * FROM principals WHERE id=?", (who,)).fetchone())


def query(who="ceo", **plan):
    return execute(principal(who), QueryPlan(**plan))


def source():
    with business() as db:
        return {
            name: [dict(r) for r in db.execute("SELECT * FROM " + name)]
            for name in [
                "employees",
                "employee_education",
                "schools",
                "assignments",
                "departments",
                "overtime_requests",
            ]
        }


def matches_education(
    data, eid, day, *, degree=None, school_ids=None, tier=None, any_completed=False, min_rank=0
):
    records = [
        q for q in data["employee_education"] if q["employee_id"] == eid and q["graduation_date"] <= day
    ]
    if not any_completed and records:
        records = [max(records, key=lambda q: (q["education_rank"], q["graduation_date"], q["id"]))]
    schools = {s["id"]: s for s in data["schools"]}
    return any(
        (not degree or q["degree"] == degree)
        and (not school_ids or q["school_id"] in school_ids)
        and (not tier or schools[q["school_id"]][tier])
        and q["education_rank"] >= min_rank
        for q in records
    )


def active(e, day="2026-09-11"):
    return e["hire_date"] <= day and (not e["termination_date"] or e["termination_date"] > day)


def department_label(data, eid, day):
    assignment = next(
        a
        for a in data["assignments"]
        if a["employee_id"] == eid and a["valid_from"] <= day and (not a["valid_to"] or a["valid_to"] > day)
    )
    departments = {d["id"]: d for d in data["departments"]}
    d = departments[assignment["department_id"]]
    return (
        departments[d["parent_id"]]["name"]
        if d["level"] == 4
        else d["name"]
        if d["level"] == 3
        else d["name"] + "（直属）"
    )


@pytest.mark.parametrize(
    "period,snapshot,expected",
    [
        ("last_quarter", "2026-09-11", ("2026-04-01", "2026-06-30")),
        ("last_quarter", "2026-01-09", ("2025-10-01", "2025-12-31")),
        ("this_quarter", "2026-09-11", ("2026-07-01", "2026-09-11")),
        ("this_year", "2026-09-11", ("2026-01-01", "2026-09-11")),
        ("last_year", "2025-03-01", ("2024-01-01", "2024-12-31")),
        ("last_week", "2026-09-11", ("2026-08-31", "2026-09-06")),
        ("this_week", "2026-09-11", ("2026-09-07", "2026-09-11")),
    ],
)
def test_calendar_periods(period, snapshot, expected):
    assert period_bounds(QueryPlan(period=period), snapshot) == expected


def test_department_doctors_include_descendant_teams_and_match_source():
    data = source()
    expected = [
        e
        for e in data["employees"]
        if active(e)
        and department_label(data, e["id"], "2026-09-11") == "平台研发部"
        and matches_education(data, e["id"], "2026-09-11", degree="博士")
    ]
    result = query(department="平台研发部", degree="博士", period="as_of")
    assert result["rows"][0]["value"] == len(expected) > 0
    details = query(kind="people", department="平台研发部", degree="博士", period="as_of")
    assert {row["employee_no"] for row in details["rows"]} == {e["employee_no"] for e in expected}
    assert all(row["highest_degree"] == "博士" and row["graduation_school"] for row in details["rows"])


def test_last_quarter_doctor_hires_match_event_dates():
    data = source()
    expected = [
        e
        for e in data["employees"]
        if "2026-04-01" <= e["hire_date"] <= "2026-06-30"
        and matches_education(data, e["id"], e["hire_date"], degree="博士")
    ]
    result = query(metric="hires", degree="博士", period="last_quarter")
    assert result["rows"][0]["value"] == len(expected) > 0
    assert result["period"] == {"start": "2026-04-01", "end": "2026-06-30"}


def test_combined_changes_match_independent_events_and_department_rollup():
    data = source()
    expected = defaultdict(lambda: [0, 0])
    for e in data["employees"]:
        for column, field in enumerate(["hire_date", "termination_date"]):
            day = e[field]
            if day and "2026-01-01" <= day <= "2026-09-11":
                attr = date.fromordinal(date.fromisoformat(day).toordinal() - column).isoformat()
                expected[department_label(data, e["id"], attr)][column] += 1
    result = query(metric="workforce_changes", dimension="department", period="this_year")
    for row in result["rows"]:
        hires, departures = expected[row["label"]]
        assert (row["hires"], row["departures"], row["value"]) == (hires, departures, hires - departures)
    assert sum(r["hires"] for r in result["rows"]) == sum(v[0] for v in expected.values())
    assert any(r["hires"] == r["departures"] == 0 for r in result["rows"])
    assert not any("一组" in r["label"] or "二组" in r["label"] for r in result["rows"])
    assert result["chart_type"] == "comparison"


def test_departure_details_include_former_staff_dates():
    data = source()
    result = query(kind="people", metric="departures", period="this_year", limit=100)
    expected = {
        e["employee_no"]
        for e in data["employees"]
        if e["termination_date"] and "2026-01-01" <= e["termination_date"] <= "2026-09-11"
    }
    assert {r["employee_no"] for r in result["rows"]} == expected
    assert all(r["termination_date"] and r["highest_education"] for r in result["rows"])


def test_weekend_overtime_excludes_weekdays_pending_and_rejected():
    data = source()
    totals = defaultdict(int)
    for row in data["overtime_requests"]:
        if (
            "2026-09-01" <= row["day"] <= "2026-09-11"
            and date.fromisoformat(row["day"]).weekday() >= 5
            and row["approval_status"] == "已批准"
        ):
            totals[department_label(data, row["employee_id"], row["day"])] += row["minutes"]
    result = query(metric="weekend_overtime_hours", dimension="department", period="this_month")
    assert sum(totals.values()) > 0
    assert all(row["value"] == round(totals[row["label"]] / 60, 2) for row in result["rows"])
    all_hours = query(metric="approved_overtime_hours")["rows"][0]["value"]
    assert 0 < query(metric="weekend_overtime_hours")["rows"][0]["value"] < all_hours
    assert query(metric="weekend_overtime_hours", period="this_week")["rows"][0]["value"] == 0


def test_multi_school_counts_employees_once_even_with_multiple_degrees():
    data = source()
    groups = [
        {
            e["id"]
            for e in data["employees"]
            if active(e)
            and matches_education(data, e["id"], "2026-09-11", school_ids={school}, any_completed=True)
        }
        for school in (1, 2)
    ]
    assert groups[0] & groups[1]
    answer = query(schools=["清华", "北京大学", "北大"], education_scope="any_completed")
    assert answer["rows"][0]["value"] == len(groups[0] | groups[1]) < len(groups[0]) + len(groups[1])
    highest = query(schools=["清华大学", "北京大学"], education_scope="highest")["rows"][0]["value"]
    assert highest < answer["rows"][0]["value"]


@pytest.mark.parametrize("tier", ["985", "211", "985或211", "211非985", "双非"])
def test_school_ratio_denominator_is_not_education_filtered(tier):
    data = source()
    active_people = [e for e in data["employees"] if active(e)]
    is985 = {e["id"] for e in active_people if matches_education(data, e["id"], "2026-09-11", tier="is_985")}
    is211 = {e["id"] for e in active_people if matches_education(data, e["id"], "2026-09-11", tier="is_211")}
    expected = {
        "985": is985,
        "211": is211,
        "985或211": is985 | is211,
        "211非985": is211 - is985,
        "双非": {e["id"] for e in active_people} - is211,
    }[tier]
    row = query(metric="education_ratio", school_tier=tier)["rows"][0]
    assert row["denominator"] == len(active_people) == 459
    assert row["numerator"] == len(expected)
    assert row["value"] == round(100 * len(expected) / len(active_people), 2)


def test_master_exact_and_master_plus_proportions():
    data = source()
    rows = [
        e
        for e in data["employees"]
        if active(e) and department_label(data, e["id"], "2026-09-11") == "平台研发部"
    ]
    master = query(metric="education_ratio", department="平台研发部", degree="硕士")["rows"][0]
    higher = query(metric="education_ratio", department="平台研发部", minimum_education="硕士研究生")["rows"][
        0
    ]
    assert master["numerator"] == sum(
        matches_education(data, e["id"], "2026-09-11", degree="硕士") for e in rows
    )
    assert higher["numerator"] == sum(
        matches_education(data, e["id"], "2026-09-11", min_rank=LEVELS["硕士研究生"]) for e in rows
    )
    assert master["denominator"] == higher["denominator"] == len(rows)
    assert master["numerator"] < higher["numerator"] < len(rows)


def test_hiring_cohort_ratio_has_hire_denominator():
    data = source()
    hires = [e for e in data["employees"] if "2026-04-01" <= e["hire_date"] <= "2026-06-30"]
    row = query(metric="education_ratio", degree="博士", cohort="hires", period="last_quarter")["rows"][0]
    assert row["denominator"] == len(hires) < 459
    assert row["numerator"] == sum(
        matches_education(data, e["id"], e["hire_date"], degree="博士") for e in hires
    )


def test_zero_denominator_returns_null_and_explicit_counts():
    row = query("employee", metric="education_ratio", degree="博士", cohort="hires", period="today")["rows"][
        0
    ]
    assert row["numerator"] == row["denominator"] == 0 and row["value"] is None


@pytest.mark.parametrize(
    "plan",
    [
        {"metric": "headcount", "degree": "博士", "department": "企业销售部"},
        {"metric": "education_ratio", "school_tier": "985", "department": "企业销售部"},
        {"metric": "workforce_changes", "department": "企业销售部", "period": "this_year"},
        {"metric": "weekend_overtime_hours", "department": "企业销售部"},
    ],
)
def test_new_queries_preserve_cross_organization_boundaries(plan):
    with pytest.raises(HTTPException) as exc:
        query("rd", **plan)
    assert exc.value.status_code == 403


@pytest.mark.parametrize(
    "plan", [{"degree": "博士"}, {"schools": ["清华"]}, {"school_tier": "985"}, {"minimum_education": "本科"}]
)
def test_education_filters_cannot_narrow_salary_aggregate(plan):
    with pytest.raises(HTTPException) as exc:
        query(metric="avg_salary", **plan)
    assert exc.value.status_code == 403


def test_employee_education_results_remain_self_only():
    groups = query("employee", dimension="degree")["rows"]
    assert sum(row["value"] for row in groups) == 1
    r = query("employee", metric="education_ratio", school_tier="211")["rows"][0]
    assert r["denominator"] == 1
    assert all(row["employee_no"] == "CC00052" for row in query("employee", kind="people")["rows"])


def test_completed_degree_as_of_date_and_unknown_denominator(tmp_path, monkeypatch):
    path = tmp_path / "history.sqlite"
    with business() as db:
        copy = sqlite3.connect(path)
        db.backup(copy)
    copy.execute("DELETE FROM employee_education WHERE employee_id=52")
    copy.execute(
        "INSERT INTO employee_education(employee_id,school_id,education_level,education_rank,degree,major,start_date,graduation_date,study_mode) VALUES (52,1,'博士研究生',5,'博士','计算机','2022-01-01','2026-09-12','全日制')"
    )
    copy.commit()
    copy.close()
    monkeypatch.setattr(config, "BUSINESS_DB", path)
    row = query("employee", metric="education_ratio", degree="博士")["rows"][0]
    assert row["numerator"] == 0 and row["denominator"] == 1
    assert query("employee", kind="people")["rows"][0]["highest_degree"] is None


def test_unknown_or_injected_school_cannot_run():
    with pytest.raises(HTTPException) as exc:
        query(schools=["清华大学' OR 1=1 --"])
    assert exc.value.status_code == 422


def test_legacy_dashboard_keeps_old_assignment_grouping_after_catalog_upgrade():
    with application() as db:
        db.execute(
            "INSERT INTO dashboards VALUES (?,?,?,?,?,?)",
            (
                "legacy",
                "ceo",
                "旧部门看板",
                json.dumps({"metric": "headcount", "dimension": "department"}),
                "hr-metrics-1.0",
                "2026-09-11",
            ),
        )
    publish_catalog()
    publish_catalog()
    with application() as db:
        saved = dict(db.execute("SELECT * FROM dashboards WHERE id='legacy'").fetchone())
    assert saved["catalog_version"] == config.CATALOG_VERSION
    assert json.loads(saved["plan"])["dimension"] == "team"


@pytest.mark.parametrize(
    "question,expected",
    [
        ("按最高学历毕业院校统计在职人数", {"dimension": "school", "education_scope": "highest"}),
        (
            "平台研发部现在的博士人数",
            {"metric": "headcount", "degree": "博士", "department": "平台研发部", "period": "as_of"},
        ),
        ("上季度整个公司入职的博士人数", {"metric": "hires", "degree": "博士", "period": "last_quarter"}),
        (
            "整个公司今年各部门入职和离职人数统计",
            {"metric": "workforce_changes", "dimension": "department", "period": "this_year"},
        ),
        (
            "各部门周末加班的总工时",
            {"metric": "weekend_overtime_hours", "dimension": "department", "period": "this_month"},
        ),
        (
            "清华和北大毕业的员工数量",
            {"schools": ["清华大学", "北京大学"], "education_scope": "any_completed"},
        ),
        (
            "平台研发部211/985毕业人数比例",
            {"metric": "education_ratio", "school_tier": "985或211", "department": "平台研发部"},
        ),
        (
            "平台研发部硕士及以上学历的比例",
            {"metric": "education_ratio", "minimum_education": "硕士研究生", "degree": None},
        ),
        (
            "上季度入职员工中博士占比",
            {"metric": "education_ratio", "degree": "博士", "cohort": "hires", "period": "last_quarter"},
        ),
    ],
)
def test_explicit_user_conditions_cannot_be_dropped_by_model(question, expected):
    constraints, _ = explicit_constraints(question)
    # Deliberately wrong model plan must be corrected to retain user constraints.
    plan, changes = enforce(QueryPlan(), question, constraints)
    assert all(plan.model_dump()[k] == v for k, v in expected.items())
    assert changes


@pytest.mark.parametrize(
    "q",
    [
        "清华和北大分别有多少毕业员工",
        "博士后人数",
        "双一流毕业人数",
        "哈佛大学毕业人数",
        "清华毕业人员平均薪资",
        "按部门和月份统计入离职",
    ],
)
def test_unmodeled_or_sensitive_combinations_are_explicit(q):
    with pytest.raises(HTTPException):
        explicit_constraints(q)


def test_hire_department_survives_later_cross_department_transfer(tmp_path, monkeypatch):
    data = source()
    employee = next(
        e for e in data["employees"] if e["hire_date"].startswith("2026-04") and not e["termination_date"]
    )
    eid = employee["id"]
    original = department_label(data, eid, employee["hire_date"])
    target = next(d for d in data["departments"] if d["level"] == 3 and d["name"] != original)
    assignments = [a for a in data["assignments"] if a["employee_id"] == eid]
    latest = max(assignments, key=lambda a: a["valid_from"])
    path = tmp_path / "transfer.sqlite"
    with business() as db:
        copy = sqlite3.connect(path)
        db.backup(copy)
    copy.execute("UPDATE assignments SET valid_to='2026-08-01' WHERE id=?", (latest["id"],))
    copy.execute(
        "INSERT INTO assignments(employee_id,department_id,manager_id,position_id,grade_id,valid_from,valid_to) VALUES (?,?,?,?,?,'2026-08-01',NULL)",
        (eid, target["id"], latest["manager_id"], latest["position_id"], latest["grade_id"]),
    )
    copy.commit()
    copy.close()
    monkeypatch.setattr(config, "BUSINESS_DB", path)
    original_hire = query(
        metric="hires", department=original, employee_name=employee["employee_no"], period="last_quarter"
    )
    later_hire = query(
        metric="hires",
        department=target["name"],
        employee_name=employee["employee_no"],
        period="last_quarter",
    )
    assert original_hire["rows"][0]["value"] == 1
    assert later_hire["rows"][0]["value"] == 0
    assert (
        query(department=target["name"], employee_name=employee["employee_no"], period="as_of")["rows"][0][
            "value"
        ]
        == 1
    )


def test_school_details_show_matching_history_even_when_highest_school_differs():
    result = query(kind="people", schools=["清华大学"], education_scope="any_completed", limit=100)
    assert result["rows"]
    assert all("清华大学" in r["matching_education"] for r in result["rows"])
    assert any(r["graduation_school"] != "清华大学" for r in result["rows"])


@pytest.mark.parametrize(
    "question,relation",
    [
        ("我有多少直属下属？", "direct"),
        ("查看我本月的考勤异常明细", "self"),
        ("我的间接下属有多少博士", "indirect"),
    ],
)
def test_explicit_relation_is_preserved(question, relation):
    constraints, _ = explicit_constraints(question)
    plan, _ = enforce(QueryPlan(), question, constraints)
    assert plan.relation == relation
