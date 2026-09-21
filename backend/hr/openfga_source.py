"""OpenFGA 决策 + PostgreSQL 执行的唯一在线数据入口。

浏览器仅选择演示 persona，服务器映射到稳定 person_id。OpenFGA 不执行 SQL；
这里是可信执行点，负责把授权 ID/字段组写入事务局部变量。数据库账号与 FGA
管理密钥只在服务端使用，不能交给普通查询用户；生产需隔离管理与查询网关。
"""

import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path

import psycopg
from fastapi import HTTPException
from psycopg.rows import dict_row

from . import config, fga_client
from .schema import FIELDS

CAPABILITIES = [
    "reports",
    "hrbp",
    "inherit_hrbp",
    "details",
    "export",
    "basic",
    "education",
    "employment",
    "contract",
]


def enabled():
    return os.getenv("HR_QUERY_BACKEND", "superset") == "openfga"


def settings():
    path = Path(os.getenv("HR_OPENFGA_CONFIG", config.PROJECT / "integrations/openfga/.local/runtime.json"))
    try:
        value = json.loads(path.read_text())
        if value["pg"]["user"] != "hr_fga_reader":
            raise ValueError()
        return value
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(503, "OpenFGA 只读运行配置未就绪") from exc


@contextmanager
def database(snapshot=None):
    try:
        with psycopg.connect(**settings()["pg"], row_factory=dict_row, connect_timeout=5) as conn:
            conn.execute("SET TRANSACTION READ ONLY")
            conn.execute("SET LOCAL search_path TO hr_api, pg_catalog")
            if snapshot:
                # 所有值都参数绑定；set_config 的第三参数 true 表示仅当前事务有效。
                for key, value in [
                    ("generation", snapshot["publication"]["id"]),
                    ("allowed_ids", json.dumps(snapshot["grant"]["ids"])),
                    ("groups", json.dumps(snapshot["rules"]["field_groups"])),
                ]:
                    conn.execute("SELECT set_config(%s,%s,true)", ("hr." + key, value))
            yield conn
    except psycopg.Error as exc:
        raise HTTPException(503, "OpenFGA 业务数据库查询失败，未回退到本地数据") from exc


def publication():
    with database() as conn:
        value = conn.execute(
            "SELECT p.*,r.version AS current_revision FROM hr_control.active a JOIN hr_control.publications p ON p.id=a.publication CROSS JOIN hr_control.revision r"
        ).fetchone()
    if not value:
        raise HTTPException(503, "OpenFGA 尚未发布数据快照")
    if value["source_revision"] != value["current_revision"]:
        raise HTTPException(409, "业务数据或身份已变化，等待 OpenFGA 同步后重试")
    return value


def snapshot(p, refresh=False):
    if not refresh and p.get("_openfga_snapshot") is not None:
        return p["_openfga_snapshot"]
    pub = publication()
    meta = pub["metadata"]
    from . import store

    if meta["as_of"] != store.AS_OF:
        raise HTTPException(409, "OpenFGA 数据截止日与指标目录不一致")
    matches = [v for v in meta["identities"] if v["persona"] == p["id"]]
    if len(matches) != 1 or matches[0]["person_id"] != p["person_id"] or matches[0]["role_key"] != p["role"]:
        raise HTTPException(403, "OpenFGA 身份映射缺失或与演示会话不匹配")
    edges = {r["person_id"]: r for r in meta["edges"]}
    if not edges or len(edges) > 1000:
        raise HTTPException(503, "OpenFGA 课堂候选全集超限或为空")
    ids = sorted(edges)
    root = p["person_id"]
    relations = ["viewer", "reports_access", "hrbp_access", "inherited_access"]
    pairs = [(r, "person:" + eid) for r in relations for eid in ids]
    with fga_client.client(settings()) as client:
        caps = dict(
            zip(
                CAPABILITIES,
                fga_client.batch(
                    client, pub, "user:" + root, [(cap, "company:main") for cap in CAPABILITIES]
                ),
                strict=True,
            )
        )
        answers = fga_client.batch(client, pub, "user:" + root, pairs)
    allowed = {
        relation: {
            eid for eid, yes in zip(ids, answers[i * len(ids) : (i + 1) * len(ids)], strict=True) if yes
        }
        for i, relation in enumerate(relations)
    }
    visible = allowed["viewer"]
    if any(not allowed[r] <= visible for r in relations[1:]):
        raise HTTPException(503, "OpenFGA 模型不满足范围关系契约")
    # 仅为可见对象解释深度/路径，不参与决定哪些人可见。
    depths, origins = {}, {}

    def chain(eid):
        path, cursor = [], eid
        while cursor is not None:
            if cursor not in edges or cursor in path:
                raise HTTPException(409, "发布快照中的组织关系异常")
            path.append(cursor)
            if cursor == root:
                return list(reversed(path))
            cursor = edges[cursor]["head_person_id"]
        return []

    for eid in sorted(visible):
        path = chain(eid)
        if path:
            depths[eid] = len(path) - 1
        reasons = []
        if eid == root:
            reasons.append({"kind": "self", "path": [root], "text": "本人"})
        if eid in allowed["reports_access"]:
            reasons.append({"kind": "reports", "path": path, "text": "OpenFGA 管理线"})
        if eid in allowed["hrbp_access"]:
            reasons.append({"kind": "hrbp", "path": [root, eid], "text": "OpenFGA 本人 HRBP 服务"})
        if eid in allowed["inherited_access"]:
            reasons.append(
                {
                    "kind": "inherited_hrbp",
                    "path": chain(edges[eid]["dept_hrbp_id"]) + [eid],
                    "text": "OpenFGA 继承下属 HRBP 服务",
                }
            )
        origins[eid] = reasons
    rules = {k: caps[k] for k in CAPABILITIES[:5]}
    rules["field_groups"] = [k for k in CAPABILITIES[5:] if caps[k]]
    if "basic" not in rules["field_groups"]:
        raise HTTPException(403, "OpenFGA 未授予基础字段访问")
    grant = {
        "ids": sorted(visible),
        "depths": depths,
        "reports": sorted(allowed["reports_access"]),
        "hrbp": sorted(allowed["hrbp_access"]),
        "inherited_hrbp": sorted(allowed["inherited_access"]),
        "origins": origins,
        "policy_version": meta["policy_version"],
    }
    result = {
        "publication": pub,
        "rules": rules,
        "grant": grant,
        "fields": {k for k, v in FIELDS.items() if v[1] in rules["field_groups"]},
    }
    with database(result) as conn:
        rows = conn.execute("SELECT * FROM hr_api.people ORDER BY person_id").fetchall()
    if {r["person_id"] for r in rows} != visible:
        raise HTTPException(503, "OpenFGA 授权与 PostgreSQL 出口不一致")
    result["rows"] = [{k: v for k, v in r.items() if k in result["fields"]} for r in rows]
    result["fingerprint"] = hashlib.sha256(
        json.dumps(
            {
                "publication": pub["id"],
                "subject": matches[0],
                "grant": grant,
                "rules": rules,
                "rows": result["rows"],
            },
            sort_keys=True,
            ensure_ascii=False,
        ).encode()
    ).hexdigest()
    result["source_queries"] = [
        {
            "engine": "OpenFGA BatchCheck",
            "store_id": pub["store_id"],
            "model_id": pub["model_id"],
            "user": "user:" + root,
            "consistency": "HIGHER_CONSISTENCY",
            "candidate_count": len(ids),
            "check_count": len(pairs) + len(CAPABILITIES),
            "allowed_count": len(visible),
            "capabilities": caps,
            "publication": pub["id"],
        }
    ]
    # 授权期间刚好发生同步/源变动，整次快照丢弃。调用方在输出前仍再次校验指纹。
    if publication()["id"] != pub["id"]:
        raise HTTPException(409, "OpenFGA 发布版本已变化，请重新查询")
    p["_openfga_snapshot"] = result
    return result
