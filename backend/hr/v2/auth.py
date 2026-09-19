import hashlib
import json
import secrets
import time
from datetime import UTC, datetime

from fastapi import HTTPException, Request
from pydantic import Field

from . import store, superset_source
from .schema import FIELDS, Strict

COOKIE = "hr_v2_session"


class RolePolicy(Strict):
    reports: bool = True
    hrbp: bool = False
    inherit_hrbp: bool = False
    field_groups: list[str] = Field(min_length=1, max_length=5)
    details: bool = True
    export: bool = False


class PolicyChange(Strict):
    expected_version: int
    roles: dict[str, RolePolicy]


def session(persona, old=None):
    store.ensure()
    if persona not in {p["id"] for p in store.PERSONAS}:
        raise HTTPException(404, "演示身份不存在")
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
    with store.connection() as db:
        if old:
            db.execute("DELETE FROM sessions WHERE hash=?", (hashlib.sha256(old.encode()).hexdigest(),))
        db.execute("DELETE FROM sessions WHERE expires<?", (time.time(),))
        db.execute(
            "INSERT INTO sessions VALUES (?,?,?,?)",
            (hashlib.sha256(token.encode()).hexdigest(), persona, csrf, time.time() + 8 * 3600),
        )
    return token


def principal(request: Request):
    store.ensure()
    token = request.cookies.get(COOKIE, "")
    with store.connection(readonly=True) as db:
        row = db.execute(
            "SELECT persona,csrf FROM sessions WHERE hash=? AND expires>?",
            (hashlib.sha256(token.encode()).hexdigest(), time.time()),
        ).fetchone()
    if not row:
        raise HTTPException(401, "请选择演示身份")
    return {
        **next(p for p in store.PERSONAS if p["id"] == row["persona"]),
        "csrf": row["csrf"],
        "session_hash": hashlib.sha256(token.encode()).hexdigest(),
    }


def csrf(request, p):
    if not secrets.compare_digest(request.headers.get("x-csrf-token", ""), p["csrf"]):
        raise HTTPException(403, "请求校验失败，请刷新重试")


def refresh(p):
    if p.get("session_hash"):
        with store.connection(readonly=True) as db:
            row = db.execute(
                "SELECT persona FROM sessions WHERE hash=? AND expires>?", (p["session_hash"], time.time())
            ).fetchone()
        if not row or row["persona"] != p["id"]:
            raise HTTPException(401, "会话已切换或失效")
    return p


def grants(p, config=None, rows=None):
    if superset_source.enabled() and config is None and rows is None:
        return superset_source.snapshot(p)["grant"]
    config = config or store.policy()
    rows = rows if rows is not None else store.people()
    lookup = {r["person_id"]: r for r in rows}
    for row in rows:
        if row.get("dept_hrbp_id") and row["dept_hrbp_id"] not in lookup:
            raise HTTPException(409, "HRBP关系引用了不存在的人员")
    root = p["person_id"]
    if root not in lookup:
        raise HTTPException(403, "身份未映射到人员主键")
    rules = config["roles"][p["role"]]
    # Independently traverse each source manager chain, detect all bad cycles/orphans.
    depths = {}
    for person in rows:
        node = person["person_id"]
        path = []
        while node is not None:
            if node in path:
                raise HTTPException(409, "管理关系出现环，请修复后再查询")
            if node not in lookup:
                raise HTTPException(409, "管理关系引用了不存在的人员")
            path.append(node)
            node = lookup[node]["head_person_id"]
        if root in path:
            depths[person["person_id"]] = path.index(root)
    reports = {eid for eid, depth in depths.items() if depth > 0} if rules["reports"] else set()
    direct_hrbp = {r["person_id"] for r in rows if r["dept_hrbp_id"] == root} if rules["hrbp"] else set()
    # Permission inheritance follows management edges only, not arbitrary visible people.
    inherited = (
        {r["person_id"] for r in rows if r["dept_hrbp_id"] in reports}
        if rules["inherit_hrbp"] and rules["reports"]
        else set()
    )
    ids = {root} | reports | direct_hrbp | inherited
    origins = {}
    for eid in sorted(ids):
        reasons = []
        if eid == root:
            reasons.append({"kind": "self", "path": [root], "text": "本人"})
        if eid in reports:
            path = [eid]
            while path[-1] != root:
                path.append(lookup[path[-1]]["head_person_id"])
            path.reverse()
            reasons.append({"kind": "reports", "path": path, "text": "管理线下属"})
        if eid in direct_hrbp:
            reasons.append({"kind": "hrbp", "path": [root, eid], "text": "本人 HRBP 服务"})
        if eid in inherited:
            provider = lookup[eid]["dept_hrbp_id"]
            path = [provider]
            while path[-1] != root:
                path.append(lookup[path[-1]]["head_person_id"])
            path.reverse()
            reasons.append({"kind": "inherited_hrbp", "path": path + [eid], "text": "继承下属 HRBP 服务"})
        origins[eid] = reasons
    return {
        "ids": sorted(ids),
        "depths": depths,
        "reports": sorted(reports),
        "hrbp": sorted(direct_hrbp),
        "inherited_hrbp": sorted(inherited),
        "origins": origins,
        "policy_version": config["version"],
    }


def scoped(p, scope="all", config=None, rows=None):
    grant = grants(p, config, rows)
    if scope == "all":
        return grant["ids"], grant
    if scope == "self":
        return [p["person_id"]] if p["person_id"] in grant["ids"] else [], grant
    if scope in ("reports", "hrbp", "inherited_hrbp"):
        return grant[scope], grant
    return [
        eid
        for eid in grant["reports"]
        if (grant["depths"][eid] == 1 if scope == "direct" else grant["depths"][eid] >= 2)
    ], grant


def allowed_fields(p, config=None):
    if superset_source.enabled() and config is None:
        return superset_source.snapshot(p)["fields"]
    rules = (config or store.policy())["roles"][p["role"]]
    return {name for name, info in FIELDS.items() if info[1] in rules["field_groups"]}


def fingerprint(p):
    if superset_source.enabled():
        # 历史读取、模型前后、结果返回前均重新查询，撤权不能靠旧会话缓存绕过。
        return superset_source.snapshot(p, refresh=True)["fingerprint"]
    payload = {
        "persona": p["id"],
        "role": p["role"],
        "policy": store.policy(),
        "scope": grants(p)["ids"],
        "data": store.data_fingerprint(),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def policy(p):
    """业务配置唯一来源随执行后端选择，不混用两份授权配置。"""
    if superset_source.enabled():
        snap = superset_source.snapshot(p)
        return {"version": snap["grant"]["policy_version"], "assumption": True,
                "roles": {p["role"]: snap["rules"]}}
    return store.policy()


def people(p):
    """Superset 模式下连候选部门/关系说明也只能来自当前用户可读的人群。"""
    if superset_source.enabled():
        return superset_source.snapshot(p)["rows"]
    return store.people()


def public(p):
    grant = grants(p)
    rules = policy(p)["roles"][p["role"]]

    def active(r):
        return r["onboard_date"] <= store.AS_OF and (not r["termin_date"] or r["termin_date"] > store.AS_OF)

    rows = [r for r in people(p) if r["person_id"] in grant["ids"]]
    return {
        **{k: p[k] for k in ["id", "person_id", "name", "role", "label"]},
        "csrf": p.get("csrf"),
        "count": sum(active(r) for r in rows),
        "candidate_count": len(rows),
        "policy_version": grant["policy_version"],
        "can_configure": p["id"] == "admin" and not superset_source.enabled(),
        "authorization_backend": "superset" if superset_source.enabled() else "local",
        "rules": rules,
    }


def policy_preview(p, body):
    if superset_source.enabled():
        raise HTTPException(409, "Superset 模式请在 Superset 配置角色/RLS，在 PostgreSQL 配置业务关系；本地规则编辑已停用")
    if p["id"] != "admin":
        raise HTTPException(403, "仅演示配置管理员可以配置规则")
    current = store.policy()
    if body.expected_version != current["version"]:
        raise HTTPException(409, "配置已变化，请重新加载")
    if set(body.roles) != set(current["roles"]):
        raise HTTPException(422, "必须包含全部已知演示角色")
    roles = {k: v.model_dump() for k, v in body.roles.items()}
    for value in roles.values():
        if "basic" not in value["field_groups"] or not set(value["field_groups"]) <= set(
            x[1] for x in FIELDS.values()
        ):
            raise HTTPException(422, "字段组需包含basic且只能使用目录中的分组")
        if value["inherit_hrbp"] and not value["reports"]:
            raise HTTPException(422, "继承下属HRBP范围需要开启管理线范围")
    candidate = {**current, "roles": roles, "version": current["version"] + 1}
    diffs = []
    for persona in store.PERSONAS:
        before = set(grants(persona, current)["ids"])
        after = set(grants(persona, candidate)["ids"])
        diffs.append(
            {
                "persona": persona["label"],
                "added": sorted(after - before),
                "removed": sorted(before - after),
                "before": len(before),
                "after": len(after),
            }
        )
    return candidate, diffs


def apply_policy(p, body):
    candidate, diffs = policy_preview(p, body)
    with store.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        current = json.loads(db.execute("SELECT value FROM settings WHERE key='policy'").fetchone()[0])
        if current["version"] != body.expected_version:
            raise HTTPException(409, "配置版本冲突")
        db.execute("UPDATE settings SET value=? WHERE key='policy'", (json.dumps(candidate),))
        db.execute(
            "INSERT INTO audit(actor,action,created_at,details) VALUES (?,?,?,?)",
            (
                p["id"],
                "policy.apply",
                datetime.now(UTC).isoformat(),
                json.dumps({"version": candidate["version"], "changes": diffs}, ensure_ascii=False),
            ),
        )
    return {"policy": candidate, "changes": diffs}
