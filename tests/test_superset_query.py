"""请求协议与防回退测试；真实 Superset / PostgreSQL 对账另由集成脚本执行。

测试故意只模拟 Superset 的 HTTP 返回值：执行器必须直接采用服务器聚合结果，
不能读取本地 people.sqlite 重新计算。编译检查则沿用 独立隔离的权限样本。
"""

import json
import sys
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from backend import hr
from backend.hr import auth, config, query, store, superset_query
from backend.hr.schema import FIELDS, METRICS, Plan

PLANS = json.loads((config.PROJECT / "evaluation/plans.json").read_text())["plans"]


@pytest.fixture
def environment(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "APP_DB", tmp_path / "app.sqlite")
    store.ensure()
    principal = next(persona for persona in store.PERSONAS if persona["id"] == "hr_lead")
    snapshot = {
        "fields": set(FIELDS),
        "grant": auth.grants(principal),
        "rules": store.policy()["roles"][principal["role"]],
        "source_queries": ["SELECT authorized_context FROM visible_context"],
    }
    return principal, snapshot


@pytest.mark.parametrize("case", PLANS)
def test_twenty_plans_produce_governed_dataset_requests(environment, case):
    principal, snapshot = environment
    principal = next(
        persona for persona in store.PERSONAS
        if persona["id"] == {"HR-01": "manager", "HR-02": "hrbp"}.get(case, "hr_lead")
    )
    compiler = superset_query.Compiler(principal, Plan.model_validate(PLANS[case]), snapshot)
    requests = compiler.compile()
    assert compiler.dataset_key in {"people_public", "people_contract", "events_public", "events_contract"}
    assert len(requests) >= 2
    serialized = json.dumps(requests, ensure_ascii=False)
    # 授权人员集合不能成为 Agent 向数据库传递的安全边界；登录人由 chart()
    # 的服务端身份绑定选择，不能通过业务查询请求自行指定 _viewer_id。
    assert '"person_id" IN' not in serialized
    assert "_viewer_id" not in serialized
    assert "SELECT " not in serialized and "WITH " not in serialized
    assert all(req["row_limit"] == superset_query.RESULT_LIMIT for req in requests)
    assert all("datasource" not in req for req in requests)


@pytest.mark.parametrize("scope, expected", [
    ("all", "(TRUE)"),
    ("self", '"person_id" ='),
    ("reports", '"_reports" IS TRUE'),
    ("direct", '"_depth" = 1'),
    ("indirect", '"_depth" >= 2'),
    ("hrbp", '"_hrbp" IS TRUE'),
    ("inherited_hrbp", '"_inherited" IS TRUE'),
])
def test_scope_is_only_a_business_intersection(environment, scope, expected):
    principal, snapshot = environment
    where = superset_query.Compiler(principal, Plan(scope=scope), snapshot).where()
    assert expected in where
    assert "_viewer_id" not in where and '"person_id" IN' not in where


def test_metric_contracts_are_computed_in_postgresql(environment):
    principal, snapshot = environment
    compiler = superset_query.Compiler(principal, Plan(), snapshot)
    expressions = {metric: dict(compiler.metric(metric)) for metric in METRICS if metric not in {"hires", "departures", "net_change"}}
    assert 'COUNT(DISTINCT "person_id")' == expressions["count"]["count"]
    assert "NULLIF" in expressions["masters_ratio"]["masters_ratio"]
    assert {"masters_ratio", "masters_ratio_numerator", "masters_ratio_denominator"} == set(expressions["masters_ratio"])
    assert "CAST(AVG(" in expressions["avg_age"]["avg_age"]
    assert 'CAST("confirmation_date" AS DATE) - CAST("onboard_date" AS DATE)' in expressions["avg_confirmation_days"]["avg_confirmation_days"]
    assert "2026-09-11" in expressions["doctors_count"]["doctors_count"]


def test_events_select_registered_view_and_separate_total(environment):
    principal, snapshot = environment
    plan = Plan(population="all", date_field="employment_events", start_date="2026-01-01", end_date=store.AS_OF,
                group_by=["event_month", "dept_cn_name"], metrics=["count", "hires", "departures", "net_change"])
    compiler = superset_query.Compiler(principal, plan, snapshot)
    requests = compiler.compile()
    assert compiler.dataset_key == "events_public"
    assert '"event_day" BETWEEN' in requests[0]["extras"]["where"]
    assert requests[1]["columns"] == []  # 总计独立聚合，不对各组比率求平均。
    assert '"event_day" BETWEEN' not in requests[2]["extras"]["where"]
    expressions = {metric["label"]: metric["sqlExpression"] for metric in requests[0]["metrics"]}
    assert 'SUM("is_hire")' in expressions["hires"]
    assert 'SUM("is_exit")' in expressions["departures"]


def test_contract_access_follows_every_dependency(environment):
    principal, snapshot = environment
    plan = Plan(kind="people", columns=["name"], order_by=[{"field": "contract_end_date", "direction": "asc"}])
    compiler = superset_query.Compiler(principal, plan, snapshot)
    assert compiler.dataset_key == "people_contract"
    snapshot["fields"] = {field for field in FIELDS if FIELDS[field][1] != "contract"}
    with pytest.raises(HTTPException) as error:
        superset_query.Compiler(principal, plan, snapshot)
    assert error.value.status_code == 403


def test_literal_encoding_cannot_break_string_or_turn_contains_into_wildcard(environment):
    principal, snapshot = environment
    value = "O'Reilly\\_%'; OR 1=1 --"
    plan = Plan(filters=[{"field": "name", "op": "contains", "values": [value]}])
    expression = superset_query.Compiler(principal, plan, snapshot).where()
    assert "strpos(" in expression
    assert "O''Reilly\\\\_%''; OR 1=1 --" in expression
    assert " LIKE " not in expression
    with pytest.raises(HTTPException):
        superset_query.literal("bad\x00value")
    with pytest.raises(ValidationError):
        superset_query.Compiler(principal, Plan.model_construct(columns=["name; drop table people"], kind="people"), snapshot)


def source_double(monkeypatch, snapshot, results):
    calls = []

    def chart(principal, dataset_key, requests):
        calls.append({"principal": principal, "dataset": dataset_key, "queries": requests})
        return results

    # auth 的测试仍使用独立权限样本；只有 execute 的真正数据请求被替换。
    double = SimpleNamespace(enabled=lambda: False, snapshot=lambda _: snapshot, chart=chart)
    monkeypatch.setitem(sys.modules, "backend.hr.superset_source", double)
    monkeypatch.setattr(hr, "superset_source", double, raising=False)
    return calls


def test_execute_uses_remote_totals_and_retains_real_sql(environment, monkeypatch):
    principal, snapshot = environment
    results = [
        {"data": [{"dept_cn_name": "甲", "masters_ratio": 33.33, "masters_ratio_numerator": 1, "masters_ratio_denominator": 3}], "query": "SELECT aggregate FROM postgres_rls_result"},
        {"data": [{"masters_ratio": 20.0, "masters_ratio_numerator": 1, "masters_ratio_denominator": 5}], "query": "SELECT total FROM postgres_rls_result"},
    ]
    calls = source_double(monkeypatch, snapshot, results)
    # 如果执行器尝试回退到本地 SQLite 求结果，这个测试会立即失败。
    monkeypatch.setattr(query, "validate", lambda p, plan: (snapshot["grant"]["ids"], snapshot["grant"]))
    monkeypatch.setattr(store, "connection", lambda *args, **kwargs: pytest.fail("Superset 查询不能回退 SQLite"))
    result = superset_query.execute(principal, Plan(group_by=["dept_cn_name"], metrics=["masters_ratio"]))
    assert result["totals"]["masters_ratio"] == 20.0
    assert result["rows"][0]["masters_ratio"] == 33.33
    assert result["sql"] == results[0]["query"]
    assert result["execution_backend"] == "superset"
    assert results[1]["query"] in result["source_queries"]
    assert calls[0]["dataset"] == "people_public"


def test_people_sort_hidden_column_paginate_after_complete_result(environment, monkeypatch):
    principal, snapshot = environment
    calls = source_double(monkeypatch, snapshot, [
        {"data": [{"person_id": "c", "name": "丙", "age": None}, {"person_id": "b", "name": "乙", "age": 40}, {"person_id": "a", "name": "甲", "age": 40}], "query": "SELECT people"},
        {"data": [{"count": 3}], "query": "SELECT count"},
    ])
    plan = Plan(kind="people", columns=["name"], order_by=[{"field": "age", "direction": "desc"}], page=2, page_size=1)
    result = superset_query.execute(principal, plan)
    assert result["rows"] == [{"name": "乙"}]
    assert result["_all_rows"] == [{"name": "甲"}, {"name": "乙"}, {"name": "丙"}]
    assert result["total_rows"] == result["totals"]["count"] == 3
    assert calls[0]["queries"][0]["columns"] == ["name", "age", "person_id"]


def test_zero_months_preserve_totals(environment, monkeypatch):
    principal, snapshot = environment
    source_double(monkeypatch, snapshot, [
        {"data": [{"onboard_month": "2026-01", "dept_cn_name": "甲", "hires": 2}], "query": "SELECT grouped"},
        {"data": [{"hires": 2}], "query": "SELECT totals"},
        {"data": [{"dept_cn_name": "甲"}], "query": "SELECT domains"},
    ])
    plan = Plan(population="all", date_field="onboard_date", start_date="2026-01-01", end_date="2026-03-31",
                group_by=["onboard_month", "dept_cn_name"], metrics=["hires"])
    result = superset_query.execute(principal, plan)
    assert [row["hires"] for row in result["rows"]] == [2, 0, 0]
    assert result["totals"] == {"hires": 2}


@pytest.mark.parametrize("results", [
    [{"data": [], "error": "Database failure"}, {"data": [{"count": 0}]}],
    [{"data": [{"person_id": "a"}] * superset_query.RESULT_LIMIT}, {"data": [{"count": superset_query.RESULT_LIMIT}]}],
    [{"data": []}, {"data": []}],
    [{"data": []}],
    [{"data": []}, {"data": [{"count": 1}]}],
])
def test_error_truncation_and_inconsistent_counts_fail_closed(environment, monkeypatch, results):
    principal, snapshot = environment
    source_double(monkeypatch, snapshot, results)
    with pytest.raises(HTTPException):
        superset_query.execute(principal, Plan(kind="people", columns=["person_id"]))
