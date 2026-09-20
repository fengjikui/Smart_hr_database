"""权限入口的失败路径：不允许本地回退、错配身份或截断快照。"""

from contextlib import contextmanager

import httpx
import pytest
from fastapi import HTTPException

from backend.hr import auth, store
from backend.hr import superset_source as source


def test_manual_learning_rejects_stale_manifest(tmp_path, monkeypatch):
    """即使残留旧对象 ID，学习模式也不得据此登录业务账号查询。"""
    monkeypatch.setenv("HR_SUPERSET_DIR", str(tmp_path))
    (tmp_path / "manifest.json").write_text('{"principals": {}}')
    (tmp_path / "manual-learning.json").write_text('{"state":"ready"}')
    with pytest.raises(HTTPException) as error:
        source.manifest()
    assert error.value.status_code == 503
    assert "手工重建" in error.value.detail
    (tmp_path / "manual-learning.json").unlink()
    assert source.manifest() == {"principals": {}}


@pytest.fixture
def remote(monkeypatch, request):
    key = getattr(request, "param", "employee")
    p = dict(next(p for p in store.PERSONAS if p["id"] == key))
    subject = {"username": "v2_employee", "user_id": 42, "person_id": p["person_id"], "role": p["role"]}
    monkeypatch.setenv("HR_QUERY_BACKEND", "superset")
    datasets = {name: {"id": index} for index, name in enumerate(
        ["people_public", "events_public", "people_contract", "events_contract", "context"], 1)}
    monkeypatch.setattr(source, "manifest", lambda: {"principals": {p["id"]: subject}, "datasets": datasets})

    @contextmanager
    def session(_):
        yield object()

    monkeypatch.setattr(source, "session", session)
    context = {"superset_user_id": 42, "persona_id": p["id"], "person_id": p["person_id"],
               "role_key": p["role"], "policy_version": 1, "rules_json": store.default_policy()["roles"][key],
               "as_of": store.AS_OF, "data_fingerprint": "test-data", "graph_valid": True}
    row = {**next(r for r in store.generate_rows() if r["person_id"] == p["person_id"]),
           "_viewer_id": 42, "_depth": 0, "_reports": False,
           "_hrbp": False, "_inherited": False, "_origins": [{"kind": "self", "path": [p["person_id"]], "text": "本人"}]}
    return p, context, row


def route(monkeypatch, context, rows, total=None, *, dataset_rows=None, totals=None, denied=()):
    """模拟各数据集独立 RLS，而不是让所有出口共享同一份人员结果。"""
    dataset_rows, totals = dataset_rows or {}, totals or {}
    calls = []

    def query(_, dataset, queries):
        calls.append(dataset)
        if dataset in denied:
            raise HTTPException(403, "Superset 数据集访问被撤销")
        if dataset == "context":
            return [{"data": context, "query": "context RLS"}]
        values = rows
        if dataset.startswith("events_"):
            values = [{**row, "event_day": row["onboard_date"], "is_hire": 1, "is_exit": 0} for row in rows]
        values = dataset_rows.get(dataset, values)
        count = totals.get(dataset, len(values) if total is None else total)
        projected = [{column: row[column] for column in queries[1]["columns"] if column in row} for row in values]
        return [{"data": [{"n": count}]}, {"data": projected, "query": dataset + " RLS"}]

    monkeypatch.setattr(source, "_chart", query)
    return calls


def test_snapshot_and_fingerprint_refresh_without_local_people(remote, monkeypatch):
    p, context, row = remote
    monkeypatch.setattr(store, "people", lambda: pytest.fail("Superset运行路径不能读取SQLite全量"))
    route(monkeypatch, [context], [row])
    first = auth.fingerprint(p)
    assert auth.grants(p)["ids"] == [p["person_id"]]
    assert "contract_end_date" not in auth.allowed_fields(p)
    route(monkeypatch, [context], [])
    assert auth.fingerprint(p) != first
    assert auth.scoped(p, "self")[0] == []


@pytest.mark.parametrize("failure", ["missing", "wrong_identity", "cycle", "wrong_viewer", "truncated", "duplicate"])
def test_snapshot_fails_closed(remote, monkeypatch, failure):
    p, context, row = remote
    contexts, rows, total = [context], [row], None
    if failure == "missing":
        contexts = []
    elif failure == "wrong_identity":
        context["person_id"] = "P9999"
    elif failure == "cycle":
        context["graph_valid"] = False
    elif failure == "wrong_viewer":
        row["_viewer_id"] = 999
    elif failure == "truncated":
        total = 300
    elif failure == "duplicate":
        rows = [row, row]
    route(monkeypatch, contexts, rows, total)
    with pytest.raises(HTTPException):
        source.snapshot(p)


def test_upstream_errors_are_not_returned_as_empty_results():
    for status in (401, 403, 500):
        with pytest.raises(HTTPException):
            source.checked_response(httpx.Response(status, json={"error": "internal detail"}))


def test_unknown_backend_never_implicitly_uses_sqlite(monkeypatch):
    monkeypatch.setenv("HR_QUERY_BACKEND", "typo")
    with pytest.raises(HTTPException, match="未知"):
        source.enabled()


@pytest.mark.parametrize("remote", ["employee", "hr_lead"], indirect=True)
def test_fingerprint_checks_only_policy_required_dataset_exits(remote, monkeypatch):
    p, context, row = remote
    calls = route(monkeypatch, [context], [row])
    source.snapshot(p)
    expected = {"context", "people_public", "events_public"}
    if p["id"] == "hr_lead":
        expected |= {"people_contract", "events_contract"}
    assert set(calls) == expected
    assert len(calls) == len(expected)  # 选中的完整人员快照不重复获取。


@pytest.mark.parametrize("remote", ["hr_lead"], indirect=True)
@pytest.mark.parametrize("dataset", ["people_public", "events_public", "events_contract"])
def test_other_dataset_rls_change_invalidates_hr_fingerprint(remote, monkeypatch, dataset):
    p, context, row = remote
    route(monkeypatch, [context], [row])
    before = auth.fingerprint(p)
    # 合同人员/context 完全不变，仅另一个查询出口变为空集。
    route(monkeypatch, [context], [row], dataset_rows={dataset: []})
    assert auth.fingerprint(p) != before
    assert auth.grants(p)["ids"] == [p["person_id"]]


@pytest.mark.parametrize("remote", ["hr_lead"], indirect=True)
@pytest.mark.parametrize("dataset", ["people_public", "events_public", "people_contract", "events_contract"])
def test_dataset_access_revocation_cannot_reuse_old_snapshot(remote, monkeypatch, dataset):
    p, context, row = remote
    route(monkeypatch, [context], [row])
    auth.fingerprint(p)
    route(monkeypatch, [context], [row], denied={dataset})
    with pytest.raises(HTTPException) as exc:
        auth.fingerprint(p)
    assert exc.value.status_code == 403


@pytest.mark.parametrize("remote", ["hr_lead"], indirect=True)
@pytest.mark.parametrize("failure", ["truncated", "wrong_viewer", "duplicate", "missing_key"])
def test_event_scope_failure_is_not_a_valid_fingerprint(remote, monkeypatch, failure):
    p, context, row = remote
    event = {**row, "event_day": row["onboard_date"], "is_hire": 1, "is_exit": 0}
    events, totals = [event], {}
    if failure == "truncated":
        totals["events_public"] = 2
    elif failure == "wrong_viewer":
        event["_viewer_id"] = 99
    elif failure == "duplicate":
        events = [event, event]
    else:
        del event["event_day"]
    route(monkeypatch, [context], [row], dataset_rows={"events_public": events}, totals=totals)
    with pytest.raises(HTTPException):
        source.snapshot(p)


def test_event_fingerprint_tracks_day_and_type_not_row_order(remote, monkeypatch):
    p, context, row = remote
    event = {**row, "event_day": "2026-01-01", "is_hire": 1, "is_exit": 0}
    exit_event = {**event, "is_hire": 0, "is_exit": 1}
    route(monkeypatch, [context], [row], dataset_rows={"events_public": [event, exit_event]})
    first = auth.fingerprint(p)
    route(monkeypatch, [context], [row], dataset_rows={"events_public": [exit_event, event]})
    assert auth.fingerprint(p) == first
    route(monkeypatch, [context], [row], dataset_rows={"events_public": [event]})
    assert auth.fingerprint(p) != first
