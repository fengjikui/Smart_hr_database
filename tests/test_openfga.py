"""权限故障必须显式失败，不能将缺失/异常授权当作允许或零行。"""

import copy

import httpx
import pytest
from fastapi import HTTPException

from backend.hr import fga_client, store
from integrations.openfga.run import tuples, validate

PUB = {"store_id": "store", "model_id": "model"}


def test_batch_correlates_by_id_and_pins_model():
    bodies = []

    def handler(request):
        import json

        body = json.loads(request.content)
        bodies.append(body)
        return httpx.Response(200, json={"result": {"1": {"allowed": False}, "0": {"allowed": True}}})

    with httpx.Client(base_url="http://localhost", transport=httpx.MockTransport(handler)) as client:
        result = fga_client.batch(client, PUB, "user:P1", [("viewer", "person:P1"), ("viewer", "person:P2")])
    assert result == [True, False]
    assert bodies[0]["authorization_model_id"] == "model"
    assert bodies[0]["consistency"] == "HIGHER_CONSISTENCY"


@pytest.mark.parametrize(
    "body",
    [
        {"result": {}},
        {"result": {"0": {"allowed": "true"}}},
        {"result": {"0": {"error": {"message": "deadline exceeded"}}}},
        {"result": {"0": {"allowed": True}, "1": {"allowed": True}}},
        [],
    ],
)
def test_incomplete_or_invalid_batch_denied(body):
    with httpx.Client(
        base_url="http://localhost", transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body))
    ) as client:
        with pytest.raises(HTTPException) as error:
            fga_client.batch(client, PUB, "user:P1", [("viewer", "person:P1")])
        assert error.value.status_code == 503


def test_fga_unavailable_denied():
    with httpx.Client(
        base_url="http://localhost", transport=httpx.MockTransport(lambda r: httpx.Response(503))
    ) as client:
        with pytest.raises(HTTPException):
            fga_client.batch(client, PUB, "user:P1", [("viewer", "person:P1")])


@pytest.mark.parametrize(
    "mutation",
    [
        "cycle",
        "orphan_manager",
        "orphan_hrbp",
        "unknown_group",
        "unknown_role",
        "over_limit",
        "age_type",
        "duplicate_number",
        "duplicate_identity",
    ],
)
def test_bad_source_prevents_publication(mutation):
    rows = store.generate_rows()
    identities = [
        {"persona": p["id"], "person_id": p["person_id"], "role_key": p["role"]} for p in store.PERSONAS
    ]
    policy = copy.deepcopy(store.default_policy())
    if mutation == "cycle":
        rows[0]["head_person_id"] = "P0002"
    elif mutation == "orphan_manager":
        rows[0]["head_person_id"] = "P9999"
    elif mutation == "orphan_hrbp":
        rows[0]["dept_hrbp_id"] = "P9999"
    elif mutation == "unknown_group":
        policy["roles"]["employee"]["field_groups"].append("secret")
    elif mutation == "unknown_role":
        identities[0]["role_key"] = "missing"
    elif mutation == "age_type":
        rows[0]["age"] = True
    elif mutation == "duplicate_number":
        rows[1]["employee_no"] = rows[0]["employee_no"]
    elif mutation == "duplicate_identity":
        identities[1]["person_id"] = identities[0]["person_id"]
    else:
        rows = rows * 4
    with pytest.raises(ValueError):
        validate(rows, identities, policy)


def test_tuples_store_direct_edges_not_transitive_grants():
    rows = store.generate_rows()
    identities = [
        {"persona": p["id"], "person_id": p["person_id"], "role_key": p["role"]} for p in store.PERSONAS
    ]
    policy = store.default_policy()
    validate(rows, identities, policy)
    data = tuples(rows, identities, policy)
    assert {"user": "person:P0004", "relation": "manager", "object": "person:P0005"} in data
    assert not any(t["relation"] in ("viewer", "supervisors") for t in data)
    assert len(data) == len({(t["user"], t["relation"], t["object"]) for t in data})
