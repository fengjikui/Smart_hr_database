"""Run against the real pinned OpenFGA server. Stores and files are test-isolated."""

import json
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from integrations.openfga.core import FGA, Configuration, ConflictError, EngineError, Lab

EXPECTED = {
    "A": list("ABCDEFGHIJKX"), "B": list("BCDEFGJ"), "C": list("CDEFGJ"),
    "D": list("DEFGHI"), "E": ["E"], "F": list("FG"), "G": ["G"],
    "H": list("HI"), "I": ["I"], "J": list("JK"), "K": ["K"],
    "X": list("HIKX"), "UNMAPPED": [],
}


def ids(result):
    return sorted(row["person_id"] for row in result["rows"])


def clean_stores(lab):
    for path in (lab.directory / "revisions").glob("*.json"):
        state = json.loads(path.read_text())
        lab.engine.request("DELETE", f"/stores/{state['store_id']}")


@pytest.fixture(scope="module")
def baseline(tmp_path_factory):
    lab = Lab(tmp_path_factory.mktemp("openfga-baseline"))
    lab.state()
    yield lab
    clean_stores(lab)


@pytest.fixture
def changing(tmp_path):
    lab = Lab(tmp_path)
    lab.state()
    yield lab
    clean_stores(lab)


def update(lab, mutation=None, source=None):
    state = lab.state()
    config = deepcopy(state["config"])
    if mutation:
        mutation(config)
    return lab.publish(config, source or state["model_source"], state["version"])


def person(config, key):
    return next(row for row in config["people"] if row["person_id"] == key)


@pytest.mark.parametrize("user", EXPECTED)
def test_exact_roster_for_every_identity(baseline, user):
    result = baseline.query(user)
    assert ids(result) == EXPECTED[user]
    assert result["matched_total"] == len(EXPECTED[user])
    assert all(item["output"]["result"] for item in result["trace"])


def test_department_intersects_permission_scope(baseline):
    result = baseline.query("D", "可信与AI实验室")
    assert result["visible_total"] == 6
    assert ids(result) == list("DEFG")
    assert baseline.query("D", "制造部")["matched_total"] == 0


@pytest.mark.parametrize("user,target,allowed", [("C", "J", True), ("C", "K", False), ("B", "J", True), ("B", "K", False), ("D", "G", True)])
def test_separate_management_and_hrbp_paths(baseline, user, target, allowed):
    assert baseline.explain(user, target, "view_basic")["allowed"] is allowed


@pytest.mark.parametrize("user,private", [("A", False), ("B", True), ("C", True), ("D", False), ("E", False)])
def test_private_fields_require_both_scope_and_capability(baseline, user, private):
    rows = baseline.query(user)["rows"]
    assert all((row["salary"] is not None) is private for row in rows)
    assert baseline.explain("C", "K", "view_private")["allowed"] is False


@pytest.mark.parametrize("user", ["A", "C", "D", "E"])
def test_export_is_separate_permission(baseline, user):
    with pytest.raises(PermissionError):
        baseline.query(user, export=True)
    assert ids(baseline.query("B", export=True)) == EXPECTED["B"]


def test_disable_hrbp_inheritance(changing):
    update(changing, lambda c: c["roles"]["hr_lead"].update(inherit_hrbp_enabled=False))
    assert ids(changing.query("B")) == list("BC")
    assert ids(changing.query("C")) == EXPECTED["C"]


def test_edit_framework_dsl_to_direct_reports(changing):
    source = changing.state()["model_source"].replace("define report_grant: management_chain", "define report_grant: direct_manager")
    update(changing, source=source)
    assert ids(changing.query("D")) == list("DEFH")
    assert changing.explain("D", "G", "view_basic")["allowed"] is False


def test_position_change_revokes_manager_capability(changing):
    update(changing, lambda c: person(c, "D").update(job="employee"))
    assert ids(changing.query("D")) == ["D"]


def test_reporting_transfer_updates_old_and_new_manager(changing):
    update(changing, lambda c: person(c, "G").update(head_person_id="H"))
    assert ids(changing.query("F")) == ["F"]
    assert ids(changing.query("H")) == list("GHI")
    assert ids(changing.query("D")) == EXPECTED["D"]


def test_hrbp_transfer_updates_both_service_scopes(changing):
    update(changing, lambda c: person(c, "J").update(dept_hrbp_id="X"))
    assert ids(changing.query("C")) == list("CDEFG")
    assert ids(changing.query("B")) == list("BCDEFG")
    assert ids(changing.query("X")) == list("HIJKX")


def test_leaver_cannot_access_even_own_record(changing):
    update(changing, lambda c: person(c, "B").update(active=False))
    assert ids(changing.query("B")) == []
    assert ids(changing.query("A")) == EXPECTED["A"]


def test_job_to_role_mapping_changes_all_matching_people(changing):
    update(changing, lambda c: c["job_roles"].update(manager="employee"))
    assert ids(changing.query("D")) == ["D"]
    assert ids(changing.query("H")) == ["H"]


def test_new_hire_receives_configured_role_and_relations(changing):
    def add(config):
        config["people"].append({**person(config, "E"), "person_id": "N", "name": "模拟新入职"})
    update(changing, add)
    assert ids(changing.query("N")) == ["N"]
    assert ids(changing.query("D")) == list("DEFGHIN")
    assert ids(changing.query("C")) == list("CDEFGJN")


def test_rollback_is_new_published_revision(changing):
    first = changing.state()
    update(changing, lambda c: person(c, "D").update(job="employee"))
    restored = changing.rollback(first["version"], changing.state()["version"])
    assert restored["version"] == 3
    assert restored["model_id"] != first["model_id"]
    assert ids(changing.query("D")) == EXPECTED["D"]


def test_concurrent_stale_publish_rejected(changing):
    state = changing.state()
    with pytest.raises(ConflictError):
        changing.publish(state["config"], state["model_source"], state["version"] - 1)
    assert changing.state()["version"] == state["version"]


@pytest.mark.parametrize("bad", ["cycle", "orphan", "duplicate", "unknown_job"])
def test_invalid_facts_do_not_change_active_version(changing, bad):
    def mutation(config):
        if bad == "cycle":
            person(config, "D")["head_person_id"] = "G"
        elif bad == "orphan":
            person(config, "D")["dept_hrbp_id"] = "MISSING"
        elif bad == "duplicate":
            config["people"].append(deepcopy(config["people"][0]))
        else:
            person(config, "D")["job"] = "undefined"
    with pytest.raises(ValueError):
        update(changing, mutation)
    assert changing.state()["version"] == 1


def test_invalid_model_does_not_change_active_version(changing):
    with pytest.raises(ValueError):
        update(changing, source="not a valid OpenFGA model")
    assert ids(changing.query("D")) == EXPECTED["D"]


def test_framework_semantic_rejection_preserves_previous_snapshot(changing):
    source = changing.state()["model_source"].replace("define candidate: owner or report_grant or hrbp_grant or inherited_hrbp_grant", "define candidate: missing_relation")
    with pytest.raises(EngineError):
        update(changing, source=source)
    assert changing.state()["version"] == 1


def test_engine_unavailable_fails_closed(baseline, monkeypatch):
    monkeypatch.setattr(baseline, "engine", FGA("http://127.0.0.1:1"))
    with pytest.raises(EngineError, match="没有回退"):
        baseline.query("A")


def test_incomplete_engine_results_are_not_accepted(baseline, monkeypatch):
    engine = FGA()
    monkeypatch.setattr(engine, "request", lambda *args: {"result": {}})
    with pytest.raises(EngineError, match="拒绝返回部分名单"):
        engine.batch(baseline.state(), "A", baseline.state()["config"]["people"])


def test_http_boundaries_and_export(baseline, monkeypatch):
    from integrations.openfga import server
    monkeypatch.setattr(server, "lab", baseline)
    with TestClient(server.app) as client:
        assert client.get("/api/roster?user=E").json()["matched_total"] == 1
        assert client.get("/api/export?user=D").status_code == 403
        exported = client.get("/api/export?user=B")
        assert exported.status_code == 200
        assert "模拟未授权服务下属" not in exported.text
        assert client.post("/api/reset", json={"expected_version": 1}).status_code == 403
        assert client.post("/api/reset", headers={"X-Demo-Token": server.token, "Origin": "https://untrusted.example"}, json={"expected_version": 1}).status_code == 403
        assert client.get("/api/state", headers={"Host": "untrusted.example"}).status_code == 400
        assert client.get("/").headers["cache-control"] == "no-store"


def test_fixture_model_is_bounded():
    config, _ = Lab.defaults()
    config["people"] = [config["people"][0]] * 51
    with pytest.raises(ValueError):
        Configuration.model_validate(config)
