import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException

from . import auth, query, reference, store, superset_source
from .schema import FIELDS, METRICS, Plan


def summary(result):
    plan = Plan.model_validate(result["plan"])
    period = f"，期间 {plan.start_date} 至 {plan.end_date}" if plan.date_field else ""
    if plan.kind == "people":
        sentence = f"在当前授权范围内{period}，共找到 {result['total_rows']} 名符合条件的员工。当前显示 {len(result['rows'])} 条。"
    else:
        values = []
        for key in plan.metrics:
            value = result["totals"][key]
            text = "暂无有效样本" if value is None else f"{value} {METRICS[key][1]}"
            if key.endswith("_ratio"):
                text += f"（{result['totals'][key + '_numerator']}/{result['totals'][key + '_denominator']}）"
            if key.startswith("avg_"):
                text += f"（有效样本 {result['totals'][key + '_sample_size']} 人）"
            values.append(METRICS[key][0] + " " + text)
        sentence = f"在当前授权范围内{period}，" + "；".join(values) + "。"
        if plan.group_by:
            sentence += f" 共 {result['total_rows']} 个分组，合计按完整人群重新计算。"
    return sentence + " 数据截止 " + store.AS_OF + "；组织采用当前部门。"


def run_query(p, plan):
    before = auth.fingerprint(p)
    result = query.execute(p, plan)
    auth.refresh(p)
    if before != auth.fingerprint(p):
        raise HTTPException(409, "查询期间权限或数据已变化，请重新查询")
    result.pop("_all_rows")
    result["summary"] = summary(result)
    result["fingerprint"] = before
    return result


def reconcile(p, plan):
    before = auth.fingerprint(p)
    actual = query.execute(p, plan)
    if superset_source.enabled():
        ids, grant = auth.scoped(p, plan.scope)
        expected = reference.calculate(p, plan, source=auth.people(p), scope=(set(ids), grant["depths"]))
    else:
        expected = reference.calculate(p, plan)
    auth.refresh(p)
    if before != auth.fingerprint(p):
        raise HTTPException(409, "对账期间权限或数据已变化")
    differences = []
    for i in range(max(len(actual["_all_rows"]), len(expected["rows"]))):
        a = actual["_all_rows"][i] if i < len(actual["_all_rows"]) else None
        e = expected["rows"][i] if i < len(expected["rows"]) else None
        if a != e:
            differences.append({"row": i + 1, "query": a, "reference": e})
    if actual["totals"] != expected["totals"]:
        differences.append({"row": "totals", "query": actual["totals"], "reference": expected["totals"]})

    def digest(rows):
        return hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

    return {
        "passed": not differences,
        "compared_rows": len(expected["rows"]),
        "difference_count": len(differences),
        "differences": differences[:10],
        "query_hash": digest(actual["_all_rows"]),
        "reference_hash": digest(expected["rows"]),
        "totals": expected["totals"],
        "method": ("Superset/PostgreSQL结果 vs 当前已授权快照的独立Python计算" if superset_source.enabled()
                   else "只读SQL结果 vs 独立Python逐人员过滤与分组；权限采用独立BFS遍历"),
        "limitation": "验证演示口径下的计算一致性；在线对账不独立证明授权范围正确，权限名单另由离线回归核验；不代替业务确认口径，也不证明模型理解符合提问本意。",
        "fingerprint": before,
        "data_version": store.DATA_VERSION,
        "as_of": store.AS_OF,
    }


def save_run(p, question, result, parent_id=None, trace=None, fingerprint=None):
    auth.refresh(p)
    fingerprint = fingerprint or auth.fingerprint(p)
    if fingerprint != auth.fingerprint(p):
        raise HTTPException(409, "权限或数据已变化，结果已丢弃")
    rid = uuid4().hex
    payload = {**result, "id": rid, "question": question, "parent_id": parent_id, "trace": trace or []}
    with store.connection() as db:
        db.execute(
            "INSERT INTO runs VALUES (?,?,?,?,?,?,?,?)",
            (
                rid,
                p["id"],
                fingerprint,
                question,
                parent_id,
                result["status"],
                datetime.now(UTC).isoformat(),
                json.dumps(payload, ensure_ascii=False),
            ),
        )
    return payload


def history(p):
    auth.refresh(p)
    with store.connection(readonly=True) as db:
        return [
            dict(r)
            for r in db.execute(
                "SELECT id,question,parent_id,status,created_at FROM runs WHERE owner=? AND fingerprint=? ORDER BY created_at DESC LIMIT 100",
                (p["id"], auth.fingerprint(p)),
            )
        ]


def read_run(p, rid):
    auth.refresh(p)
    with store.connection(readonly=True) as db:
        row = db.execute(
            "SELECT payload FROM runs WHERE id=? AND owner=? AND fingerprint=?",
            (rid, p["id"], auth.fingerprint(p)),
        ).fetchone()
    if not row:
        raise HTTPException(404, "记录不存在，或当前身份、权限、数据版本已不匹配")
    return json.loads(row["payload"])


def drill_plan(p, plan, group, metric):
    query.validate(p, plan)
    if plan.kind != "aggregate" or metric not in plan.metrics or set(group) != set(plan.group_by):
        raise HTTPException(422, "请选择本次结果中的分组和指标")
    # Validate the selected group exists under current authorization before constructing detail conditions.
    result = query.execute(p, plan)
    if not any(all(r.get(k) == v for k, v in group.items()) for r in result["_all_rows"]):
        raise HTTPException(404, "分组不存在或已失效")
    raw = plan.model_dump()
    raw.update(kind="people", group_by=[], metrics=["count"], order_by=[], page=1)
    for k, v in group.items():
        if k == "relation":
            if plan.scope not in ("all", "reports", "direct", "indirect", "self"):
                raise HTTPException(422, "请保留HRBP来源范围，在核验表分别查看关系，避免扩大原人群")
            raw["scope"] = {"直属下属": "direct", "间接下属": "indirect", "本人": "self"}.get(v, plan.scope)
            if v == "HRBP服务人员":
                raise HTTPException(422, "请先选择HRBP服务范围再查看明细")
        elif k.endswith("_month"):
            import calendar
            from datetime import date

            year, month = map(int, v.split("-"))
            raw["start_date"] = max(plan.start_date, date(year, month, 1).isoformat())
            raw["end_date"] = min(
                plan.end_date, date(year, month, calendar.monthrange(year, month)[1]).isoformat()
            )
        elif v == "未知":
            raise HTTPException(422, "未知分组暂不支持下钻，请在核验表检查空值记录")
        else:
            raw["filters"].append({"field": k, "op": "eq", "values": [str(v)]})
    if raw["date_field"] == "employment_events":
        if metric not in ("hires", "departures"):
            raise HTTPException(422, "净增是入职减离职，请分别点击入职或离职查看人员")
        raw["date_field"] = "onboard_date" if metric == "hires" else "termin_date"
    if metric.startswith("masters"):
        raw["filters"].append({"field": "diploma_code_desc", "op": "gte", "values": ["硕士研究生"]})
    if metric == "doctors_count":
        raw["filters"].extend(
            [
                {"field": "degree_code_desc", "op": "eq", "values": ["博士"]},
                {"field": "education_expired_date", "op": "lte", "values": [store.AS_OF]},
            ]
        )
    if metric.startswith("school_"):
        from .schema import SCHOOLS

        idx = 0 if metric.startswith("school_985") else 1
        raw["filters"].append(
            {"field": "school_name", "op": "in", "values": [k for k, v in SCHOOLS.items() if v[idx]]}
        )
    if metric.startswith("outsource"):
        raw["filters"].append({"field": "labour_type_code_desc", "op": "eq", "values": ["外包"]})
    needed = set(query.dependencies(plan)) | {"employee_no", "name", "dept_cn_name"}
    needed.discard("person_id")
    # Only fields which explain the metric/conditions are projected, plus person identity for reconciliation.
    raw["columns"] = [k for k in FIELDS if k in needed][:12]
    return Plan.model_validate(raw)
