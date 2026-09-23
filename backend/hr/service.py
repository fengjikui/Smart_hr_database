"""统一业务服务：安全返回查询、独立对账、历史存档与统计下钻。

API 和 LangGraph 共用这些函数，避免聊天、核验、导出或恢复历史各写一套
权限逻辑。历史保存的是当时结果，不会悄悄用新数据重新计算旧回答。
"""

import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException

from . import auth, openfga_source, query, reference, store, superset_source
from .schema import FIELDS, METRICS, Plan


def summary(result):
    """仅用结果单元格生成中文摘要，数字、比例分母和有效样本数不交给模型补写。"""
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
    """查询前后比较指纹，丢弃执行期间身份/授权/数据发生变化的结果。"""
    # Superset 分支的 fingerprint 会重新读上游授权快照，并非只读本地版本号。
    # 前后检查可发现观察点之间的变化，但不是跨多次 HTTP/SQL 的原子事务。
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
    """对比全量查询结果与独立 Python 计算，不只检查当前分页。

    Superset 在线参考只能使用当前已授权快照，避免对账差异成为全量数据旁路；
    授权名单本身是否正确由离线回归的独立 BFS 验证，而非由此接口自我证明。
    """
    before = auth.fingerprint(p)
    actual = query.execute(p, plan)
    if superset_source.enabled():
        from .superset_query import Compiler

        snapshot = superset_source.snapshot(p)
        compiler = Compiler(p, plan, snapshot)
        # HR 的解释快照可能来自合同出口；本次公共/事件出口的 RLS 可以更窄。
        # 独立核验必须与本次实际出口相交，不能把另一个出口的旧人群放入差异响应。
        visible = snapshot["query_scopes"][compiler.dataset_key]["rows"]
        allowed_ids = {row[0] for row in visible}
        event_scope = ({(row[0], row[2], row[3], row[4]) for row in visible}
                       if compiler.dataset_key.startswith("events_") else None)
        expected = reference.calculate(p, plan, source=snapshot["rows"],
            scope=(set(compiler.ids) & allowed_ids, compiler.grant["depths"]), event_scope=event_scope)
    elif openfga_source.enabled():
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
        "method": ("PostgreSQL结果 vs 当前已授权快照的独立Python计算" if superset_source.enabled() or openfga_source.enabled()
                   else "只读SQL结果 vs 独立Python逐人员过滤与分组；权限采用独立BFS遍历"),
        "limitation": "验证演示口径下的计算一致性；在线对账不独立证明授权范围正确，权限名单另由离线回归核验；不代替业务确认口径，也不证明模型理解符合提问本意。",
        "fingerprint": before,
        "data_version": store.DATA_VERSION,
        "as_of": store.AS_OF,
    }


def save_run(p, question, result, parent_id=None, trace=None, fingerprint=None):
    """把结果与节点轨迹绑定本人及权限指纹；保存前再验权，避免晚到结果落库。"""
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
    """只列出本人且仍匹配当前权限/数据指纹的记录，不暴露其他人的问题标题。"""
    # 历史存在应用 SQLite，但读历史之前仍向 Superset 确认当前授权；不能因
    # “这是旧结果”而跳过撤权检查。上游不可用时也不会继续返回缓存历史。
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
    """聊天恢复和独立调试页共用入口；知道记录 ID 并不意味着有读取权限。"""
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
    """从当前真实聚合组构造更窄的人员计划，随后仍由 run_query 完整鉴权执行。"""
    query.validate(p, plan)
    if plan.kind != "aggregate" or metric not in plan.metrics or set(group) != set(plan.group_by):
        raise HTTPException(422, "请选择本次结果中的分组和指标")
    # 重新确认组确实存在；不能信任前端传来的任意部门/月份，把它当成授权证明。
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
    # 净增是两个集合计数之差，没有一份唯一对应的人员名单，因此要分别钻取。
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
    # 只投影解释本次指标/条件所需的字段及姓名工号，避免核验表暴露无关信息。
    raw["columns"] = [k for k in FIELDS if k in needed][:12]
    return Plan.model_validate(raw)
