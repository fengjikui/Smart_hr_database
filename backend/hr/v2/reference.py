"""Independent Python reference: no SQL compiler or permission resolver imports.

Only immutable field/metric vocabulary and the source data are shared. This is a
separate implementation used to reconcile the current synthetic data, not proof
that the business assumptions have been approved.
"""

from collections import defaultdict, deque
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from functools import cmp_to_key
from itertools import product

from . import store
from .schema import LEVELS, SCHOOLS


def independent_scope(p, plan, rows, policy):
    children = defaultdict(list)
    for r in rows:
        children[r["head_person_id"]].append(r["person_id"])
    depths = {p["person_id"]: 0}
    queue = deque([p["person_id"]])
    while queue:
        node = queue.popleft()
        for child in children[node]:
            if child in depths:
                raise ValueError("管理关系有环")
            depths[child] = depths[node] + 1
            queue.append(child)
    rules = policy["roles"][p["role"]]
    reports = set(depths) - {p["person_id"]} if rules["reports"] else set()
    own = {r["person_id"] for r in rows if r["dept_hrbp_id"] == p["person_id"]} if rules["hrbp"] else set()
    inherited = (
        {r["person_id"] for r in rows if r["dept_hrbp_id"] in reports}
        if rules["inherit_hrbp"] and rules["reports"]
        else set()
    )
    scopes = {
        "all": {p["person_id"]} | reports | own | inherited,
        "self": {p["person_id"]},
        "reports": reports,
        "direct": {x for x in reports if depths[x] == 1},
        "indirect": {x for x in reports if depths[x] > 1},
        "hrbp": own,
        "inherited_hrbp": inherited,
    }
    return scopes[plan.scope], depths


def calculate(p, plan, *, source=None, scope=None):
    # 在线核验可传入 Superset 已授权快照：参考计算不能成为全量数据泄露的旁路。
    # 离线集成验收仍用默认的独立 BFS 验证完整权限名单。
    source = store.people() if source is None else source
    snapshot = date.fromisoformat(store.AS_OF)
    visible, depths = independent_scope(p, plan, source, store.policy()) if scope is None else scope
    records = []
    for original in source:
        row = dict(original)
        if row["birth_date"]:
            birth = date.fromisoformat(row["birth_date"])
            row["age"] = (
                snapshot.year - birth.year - int((snapshot.month, snapshot.day) < (birth.month, birth.day))
            )
        else:
            row["age"] = None
        if row["person_id"] not in visible:
            continue
        if plan.departments and row["dept_cn_name"] not in plan.departments:
            continue
        if plan.population == "active" and (
            row["onboard_date"] > store.AS_OF or row["termin_date"] and row["termin_date"] <= store.AS_OF
        ):
            continue
        if plan.population == "confirmed" and (
            row["formalize_flag"] != "是"
            or not row["confirmation_date"]
            or row["confirmation_date"] > store.AS_OF
        ):
            continue
        accepted = True
        for f in plan.filters:
            actual = row[f.field]
            values = f.values
            if f.field == "diploma_code_desc" and f.op in ("gte", "lte"):
                actual = LEVELS.get(actual)
                values = [LEVELS.get(v) for v in values]
            elif f.field == "age":
                values = [int(v) for v in values]
            if f.op == "not_null":
                match = actual is not None
            elif actual is None:
                match = False
            elif f.op == "in":
                match = actual in values
            elif f.op == "eq":
                match = actual == values[0]
            elif f.op == "contains":
                match = values[0] in actual
            elif f.op == "gte":
                match = actual >= values[0]
            else:
                match = actual <= values[0]
            if not match:
                accepted = False
                break
        if accepted:
            records.append(row)

    def in_range(value):
        return bool(value and plan.start_date and plan.start_date <= value <= plan.end_date)

    facts = []
    for row in records:
        if plan.date_field == "employment_events":
            for field in ("onboard_date", "termin_date"):
                if in_range(row[field]):
                    facts.append(
                        {
                            **row,
                            "_day": row[field],
                            "_hire": int(field == "onboard_date"),
                            "_exit": int(field == "termin_date"),
                        }
                    )
        elif not plan.date_field or in_range(row[plan.date_field]):
            facts.append(
                {
                    **row,
                    "_day": None,
                    "_hire": int(in_range(row["onboard_date"])),
                    "_exit": int(in_range(row["termin_date"])),
                }
            )

    def dimension(row, key):
        if key == "relation":
            d = depths.get(row["person_id"])
            return (
                "本人" if d == 0 else "直属下属" if d == 1 else "间接下属" if d and d > 1 else "HRBP服务人员"
            )
        if key.endswith("_month"):
            field = {
                "event_month": "_day",
                "onboard_month": "onboard_date",
                "termin_month": "termin_date",
                "confirmation_month": "confirmation_date",
            }[key]
            return row[field][:7] if row[field] else "未知"
        return row[key] if row[key] is not None else "未知"

    def metrics(group):
        unique = {r["person_id"]: r for r in group}
        persons = list(unique.values())
        out = {}
        for m in plan.metrics:
            if m == "count":
                out[m] = len(unique)
            elif m == "hires":
                out[m] = sum(r["_hire"] for r in group)
            elif m == "departures":
                out[m] = sum(r["_exit"] for r in group)
            elif m == "net_change":
                out[m] = sum(r["_hire"] - r["_exit"] for r in group)
            elif m.startswith("avg_"):
                vals = (
                    [r["age"] for r in group if r["age"] is not None]
                    if m == "avg_age"
                    else [
                        (
                            date.fromisoformat(r["confirmation_date"]) - date.fromisoformat(r["onboard_date"])
                        ).days
                        for r in group
                        if r["confirmation_date"]
                        and r["onboard_date"] <= r["confirmation_date"] <= store.AS_OF
                    ]
                )
                out[m] = (
                    float(
                        (Decimal(sum(vals)) / Decimal(len(vals))).quantize(
                            Decimal("0.01"), rounding=ROUND_HALF_UP
                        )
                    )
                    if vals
                    else None
                )
                out[m + "_sample_size"] = len(vals)
            else:
                key = m.removesuffix("_count").removesuffix("_ratio")

                def qualifies(r, key=key):
                    if key == "masters":
                        return LEVELS.get(r["diploma_code_desc"], 0) >= 4
                    if key == "doctors":
                        return (
                            r["degree_code_desc"] == "博士"
                            and bool(r["education_expired_date"])
                            and r["education_expired_date"] <= store.AS_OF
                        )
                    if key == "outsource":
                        return r["labour_type_code_desc"] == "外包"
                    return bool(SCHOOLS.get(r["school_name"], (0, 0))[0 if key == "school_985" else 1])

                numerator = sum(qualifies(r) for r in persons)
                if m.endswith("_count"):
                    out[m] = numerator
                else:
                    out[m] = (
                        float(
                            (Decimal(numerator) * 100 / Decimal(len(persons))).quantize(
                                Decimal("0.01"), rounding=ROUND_HALF_UP
                            )
                        )
                        if persons
                        else None
                    )
                    out[m + "_numerator"] = numerator
                    out[m + "_denominator"] = len(persons)
        return out

    if plan.kind == "people":
        orders = [(o.field, o.direction) for o in plan.order_by] + [("person_id", "asc")]

        def compare(a, b):
            for key, direction in orders:
                x, y = a[key], b[key]
                if x == y:
                    continue
                if x is None:
                    return 1
                if y is None:
                    return -1
                delta = 1 if x > y else -1
                return delta if direction == "asc" else -delta
            return 0

        result = [{k: r[k] for k in plan.columns} for r in sorted(facts, key=cmp_to_key(compare))]
        return {"rows": result, "totals": {"count": len(result)}}
    groups = defaultdict(list)
    for r in facts:
        groups[tuple(dimension(r, d) for d in plan.group_by)].append(r)
    if not plan.group_by:
        groups[()] = facts
    if (
        plan.group_by
        and plan.start_date
        and any(d.endswith("_month") for d in plan.group_by)
        and all(d == "dept_cn_name" or d.endswith("_month") for d in plan.group_by)
    ):
        start = date.fromisoformat(plan.start_date)
        end = date.fromisoformat(plan.end_date)
        month_numbers = range(start.year * 12 + start.month - 1, end.year * 12 + end.month)
        months = [f"{n // 12:04}-{n % 12 + 1:02}" for n in month_numbers]
        departments = sorted({r["dept_cn_name"] for r in records})
        for values in product(*[departments if d == "dept_cn_name" else months for d in plan.group_by]):
            groups[values]
    result = [{**dict(zip(plan.group_by, k, strict=True)), **metrics(v)} for k, v in groups.items()]
    orders = [(o.field, o.direction) for o in plan.order_by] + [(d, "asc") for d in plan.group_by]

    def compare(a, b):
        for key, direction in orders:
            x, y = a[key], b[key]
            if x == y:
                continue
            if x is None:
                return 1
            if y is None:
                return -1
            delta = 1 if x > y else -1
            return delta if direction == "asc" else -delta
        return 0

    return {"rows": sorted(result, key=cmp_to_key(compare)), "totals": metrics(facts)}
