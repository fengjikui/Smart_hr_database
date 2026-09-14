import copy
import json

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from backend.hr import config
from backend.hr.v2 import auth, store
from backend.hr.v2.schema import FIELDS, Plan


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "APP_DB", tmp_path / "app.sqlite")
    store.ensure()


def persona(name):
    return next(p for p in store.PERSONAS if p["id"] == name)


def test_only_question_and_relation_fields():
    cases = json.loads((config.PROJECT / "evaluation/demo-v2-cases.json").read_text())["cases"]
    expected = {f for c in cases for f in c["required_source_fields"]} | {"dept_master_id"}
    assert set(FIELDS) == expected
    assert len(FIELDS) == 26
    rows = store.people()
    assert len(rows) == 300
    assert all(set(r) == expected for r in rows)
    assert next(r for r in rows if r["person_id"] == "P0005")["employee_no"] == "00031266"
    assert rows == store.generate_rows()


def test_reference_integrity_and_dates():
    rows = store.people()
    ids = {r["person_id"] for r in rows}
    for r in rows:
        assert r["head_person_id"] is None or r["head_person_id"] in ids
        assert r["dept_hrbp_id"] in ids
        assert r["education_expired_date"] <= r["onboard_date"] <= store.AS_OF
        assert not r["termin_date"] or r["termin_date"] >= r["onboard_date"]
        assert not r["confirmation_date"] or r["onboard_date"] <= r["confirmation_date"] <= store.AS_OF
        assert r["onboard_date"] <= r["current_employment_start_date"] <= store.AS_OF


def test_inherited_cross_line_grants():
    result = auth.grants(persona("hr_lead"))
    assert "P0004" not in result["reports"]
    assert "P0004" in result["inherited_hrbp"]
    assert "P0005" in result["inherited_hrbp"]
    assert any(r["path"] == ["P0002", "P0003", "P0004"] for r in result["origins"]["P0004"])
    assert "P0010" not in result["ids"]
    assert len(result["ids"]) == len(set(result["ids"]))


def test_hrbp_service_is_not_transitive_management():
    p = persona("hrbp")
    result = auth.grants(p)
    assert "P0004" in result["hrbp"]
    assert "P0003" in result["ids"]
    assert "P0010" not in result["ids"]
    assert not result["reports"]


def test_manager_and_employee():
    result = auth.grants(persona("manager"))
    assert {"P0005", "P0006"} <= set(result["reports"])
    assert not result["inherited_hrbp"]
    assert "P0002" not in result["ids"]
    assert auth.grants(persona("employee"))["ids"] == ["P0005"]
    assert auth.scoped(persona("employee"), "direct")[0] == []


def test_unbounded_depth_and_cycle_failure():
    rows = store.people()
    # >32 management levels are supported independently of LangGraph's step count.
    for i in range(12, 70):
        rows[i - 1]["head_person_id"] = "P0004" if i == 12 else f"P{i - 1:04}"
    result = auth.grants(persona("manager"), rows=rows)
    assert result["depths"]["P0069"] == 58
    rows[11]["head_person_id"] = "P0069"
    with pytest.raises(HTTPException) as exc:
        auth.grants(persona("manager"), rows=rows)
    assert exc.value.status_code == 409


def test_missing_manager_and_valid_hrbp_self():
    rows = store.people()
    assert auth.grants(persona("hrbp"), rows=rows)
    rows[4]["head_person_id"] = "missing"
    with pytest.raises(HTTPException):
        auth.grants(persona("hrbp"), rows=rows)


def test_policy_preview_apply_revoke_and_conflict():
    before = auth.fingerprint(persona("hr_lead"))
    candidate = copy.deepcopy(store.policy())
    candidate["roles"]["hr_lead"]["inherit_hrbp"] = False
    body = auth.PolicyChange(expected_version=candidate["version"], roles=candidate["roles"])
    config_after, diff = auth.policy_preview(persona("admin"), body)
    assert config_after["version"] == 2
    assert "P0004" in next(d for d in diff if d["persona"] == persona("hr_lead")["label"])["removed"]
    assert "P0004" in auth.grants(persona("hr_lead"))["ids"]
    auth.apply_policy(persona("admin"), body)
    assert "P0004" not in auth.grants(persona("hr_lead"))["ids"]
    assert auth.fingerprint(persona("hr_lead")) != before
    with pytest.raises(HTTPException):
        auth.apply_policy(persona("admin"), body)


def test_policy_and_field_boundaries():
    p = store.policy()
    body = auth.PolicyChange(expected_version=p["version"], roles=p["roles"])
    with pytest.raises(HTTPException):
        auth.apply_policy(persona("hr_lead"), body)
    assert "contract_end_date" not in auth.allowed_fields(persona("manager"))
    assert "contract_end_date" in auth.allowed_fields(persona("hrbp"))
    with pytest.raises(ValidationError):
        Plan(columns=["salary"])
    with pytest.raises(ValidationError):
        Plan(sql="SELECT * FROM people")
