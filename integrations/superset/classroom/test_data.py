"""生成器的独立约束测试：不连接课堂、不替学生配置权限。"""

from integrations.superset.classroom.generate import EXPECTED, generate


def test_deterministic_referentially_valid_data():
    data = generate()
    assert data == generate()
    people = {p["person_id"]: p for p in data["people"]}
    assert len(people) == len(data["people"]) == 12
    for person in people.values():
        assert len(person["employee_no"]) == 8 and person["employee_no"].startswith("0")
        for key in ["manager_id", "hrbp_id"]:
            assert person[key] is None or person[key] in people
        seen, current = set(), person["person_id"]
        while current:
            assert current not in seen, "管理关系必须无环"
            seen.add(current)
            current = people[current]["manager_id"]
    assert all(o["owner_id"] in people for o in data["orders"])
    assert all(p["person_id"] in people for p in data["payroll"])
    assert all(o["customer_phone"].startswith("000") for o in data["orders"])


def test_hand_calculated_totals_and_intersections():
    orders = generate()["orders"]
    assert len(orders) == 12
    assert sum(o["amount"] for o in orders) == 78000
    for region, prefix in [("EAST", "east"), ("WEST", "west"), ("NORTH", "north")]:
        subset = [o for o in orders if o["region"] == region]
        assert [o["order_id"] for o in subset] == EXPECTED[f"{prefix}_order_ids"]
        assert sum(o["amount"] for o in subset) == EXPECTED[f"{prefix}_amount"]
    assert [o["order_id"] for o in orders if o["region"] == "EAST" and o["classification"] == "PUBLIC"] == EXPECTED["east_public_ids"]
    assert sum(o["region"] == "EAST" or o["classification"] == "PUBLIC" for o in orders) == 10
