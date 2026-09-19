# V1 已实现指标目录：Git 中 catalog.json 发布到应用库，供 UI、计划校验和查询解释读取。
# 与 semantics.py 的综合口径检索互补；新增目录条目不会自动生成对应 SQL 编译能力。
import json

from . import config
from .db import application


def publish_catalog():
    source = json.loads(config.CATALOG_PATH.read_text())
    if source["version"] != config.CATALOG_VERSION:
        raise ValueError("指标源版本与应用版本不一致")
    ids = [m["id"] for m in source["metrics"]]
    if len(ids) != len(set(ids)):
        raise ValueError("指标 ID 重复")
    with application() as db:
        if source["version"] == "hr-metrics-1.1":
            # v1 department meant the exact assignment node, now explicitly named team.
            for row in db.execute(
                "SELECT id,plan FROM dashboards WHERE catalog_version='hr-metrics-1.0'"
            ).fetchall():
                plan = json.loads(row["plan"])
                if plan.get("dimension") == "department":
                    plan["dimension"] = "team"
                db.execute(
                    "UPDATE dashboards SET plan=?,catalog_version=? WHERE id=?",
                    (json.dumps(plan, ensure_ascii=False), source["version"], row["id"]),
                )
            for row in db.execute("SELECT id,plan FROM conversations WHERE plan IS NOT NULL").fetchall():
                plan = json.loads(row["plan"])
                if "education_scope" not in plan:
                    if plan.get("dimension") == "department":
                        plan["dimension"] = "team"
                    plan["education_scope"] = "highest"
                    db.execute(
                        "UPDATE conversations SET plan=? WHERE id=?",
                        (json.dumps(plan, ensure_ascii=False), row["id"]),
                    )
        db.execute("DELETE FROM metrics")
        db.execute("DELETE FROM metric_search")
        for item in source["metrics"]:
            db.execute(
                "INSERT INTO metrics VALUES (?,?,?)",
                (item["id"], json.dumps(item, ensure_ascii=False), source["version"]),
            )
            db.execute(
                "INSERT INTO metric_search VALUES (?,?)",
                (item["id"], " ".join([item["name"], item["description"], *item["aliases"]])),
            )
    return len(ids)


def catalog():
    with application() as db:
        definitions = db.execute("SELECT definition,version FROM metrics ORDER BY rowid").fetchall()
    if not definitions or any(row["version"] != config.CATALOG_VERSION for row in definitions):
        raise ValueError("运行指标目录未发布或版本不一致，请重启应用发布目录")
    return {
        "version": config.CATALOG_VERSION,
        "metrics": [json.loads(row["definition"]) for row in definitions],
    }


def metric(metric_id: str):
    return next(m for m in catalog()["metrics"] if m["id"] == metric_id)


def visible_catalog(principal):
    return [
        m for m in catalog()["metrics"] if m["sensitivity"] == "internal" or principal["salary_aggregate"]
    ]


def search(principal, query=""):
    allowed = visible_catalog(principal)
    if not query:
        return allowed
    # Chinese one/two-character terms use exact substring matching; longer prose
    # benefits from the derived FTS5 trigram index. Neither source can grant access.
    lowered = query.casefold().strip()
    hits = {m["id"] for m in allowed if lowered in json.dumps(m, ensure_ascii=False).casefold()}
    if len(lowered) >= 3:
        with application() as db:
            found = db.execute(
                "SELECT id FROM metric_search WHERE metric_search MATCH ? LIMIT 30",
                ('"' + lowered.replace('"', '""') + '"',),
            ).fetchall()
            hits.update(r[0] for r in found)
    return [m for m in allowed if m["id"] in hits]
