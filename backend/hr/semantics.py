"""Versioned semantic registry and permission-filtered, bounded metadata retrieval.

JSON is authoritative. SQLite tables and FTS5 are disposable published read models.
No employee values are sampled for retrieval or examples.
"""

import hashlib
import json
import re
import sqlite3
from functools import lru_cache
from pathlib import Path
from threading import RLock

from fastapi import HTTPException

from . import config

# V1 语义真源在 semantic/*.json；semantic.sqlite/FTS5 只是可重建的查询索引。
# 这里检索的是字段说明和指标口径，不检索员工事实，也不是向量数据库方案。
VERSION = "hr-semantics-1.0"
SOURCE_NAMES = ("catalog.json", "proposed-metrics.json", "fields.json", "tables.json", "questions.json")
_LOCK = RLock()
MAX_DISCLOSURE_CHARS = 6500
MAX_EXPANSIONS = 2


def database_path():
    # Derive from the active app path so isolated tests never publish to the live registry.
    return config.APP_DB.with_name("semantic.sqlite")


def source_key():
    return tuple(
        (str(config.PROJECT / "semantic" / n), (config.PROJECT / "semantic" / n).stat().st_mtime_ns)
        for n in SOURCE_NAMES
    )


@lru_cache(maxsize=4)
def source_documents(key):
    documents = []
    digest = hashlib.sha256()
    for path, _ in key:
        raw = Path(path).read_bytes()
        digest.update(raw)
        data = json.loads(raw)
        for item in data.get("metrics", []):
            documents.append(
                {
                    **item,
                    "id": "metric:" + item["id"],
                    "metric_id": item["id"],
                    "kind": "metric",
                    "visibility": item.get(
                        "visibility",
                        "salary" if item.get("sensitivity", "internal") != "internal" else "internal",
                    ),
                }
            )
        documents.extend(data.get("fields", []))
        documents.extend(data.get("tables", []))
        documents.extend(data.get("questions", []))
        for relation in data.get("relationships", []):
            documents.append(
                {
                    **relation,
                    "kind": "relationship",
                    "name": relation["from_field"] + " → " + relation["to_field"],
                    "aliases": [],
                    "description": relation["join_rule"],
                    "meaning": relation["join_rule"],
                    "not_meaning": relation["fanout_warning"],
                    "status": "reference_only",
                    "visibility": "governance",
                    "version": VERSION,
                }
            )
    seen = set()
    for doc in documents:
        if doc["id"] in seen:
            raise ValueError("语义ID重复: " + doc["id"])
        seen.add(doc["id"])
        for field in ("name", "meaning", "not_meaning", "status", "visibility"):
            if not doc.get(field):
                raise ValueError(f"语义条目{doc['id']}缺少{field}")
    for doc in documents:
        for field in doc.get("field_ids", []):
            if field not in seen:
                raise ValueError("字段引用不存在: " + field)
        for metric in doc.get("metric_ids", []):
            if "metric:" + metric not in seen:
                raise ValueError("指标引用不存在: " + metric)
    return documents, digest.hexdigest()


def publish():
    # 先校验定义引用并计算源文件指纹；内容未变便复用已发布读模型，否则事务更新。
    documents, revision = source_documents(source_key())
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK, sqlite3.connect(path, timeout=5) as db:
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='semantic_meta'").fetchone():
            previous = db.execute("SELECT value FROM semantic_meta WHERE key='revision'").fetchone()
            if previous and previous[0] == revision:
                return revision
        db.executescript(Path(__file__).with_name("semantic_schema.sql").read_text())
        db.execute("BEGIN IMMEDIATE")
        db.execute("DELETE FROM semantic_documents")
        db.execute("DELETE FROM semantic_search")
        for doc in documents:
            db.execute(
                "INSERT INTO semantic_documents VALUES (?,?,?,?,?,?,?)",
                (
                    doc["id"],
                    doc["kind"],
                    doc.get("table_id"),
                    doc["status"],
                    doc["visibility"],
                    VERSION,
                    json.dumps(doc, ensure_ascii=False),
                ),
            )
            # Negative definitions deliberately excluded from positive recall.
            positive = " ".join(
                [doc["name"], *doc.get("aliases", []), doc.get("meaning", ""), doc.get("description", "")]
            )
            db.execute("INSERT INTO semantic_search VALUES (?,?,?)", (doc["id"], doc["name"], positive))
        db.executemany(
            "INSERT OR REPLACE INTO semantic_meta VALUES (?,?)",
            [("version", VERSION), ("revision", revision), ("documents", str(len(documents)))],
        )
    return revision


def visible(doc, principal, model=False):
    # 元数据同样受权限过滤：不能先把敏感口径/治理关系全塞给模型，再只遮住最终结果。
    if doc["visibility"] == "salary" and not principal["salary_aggregate"]:
        return False
    if doc["visibility"] == "governance":
        return not model and principal["id"] == "ceo"
    if model and doc["status"] not in ("available", "planned"):
        return False
    return True


def all_documents(principal, *, model=False):
    publish()
    with sqlite3.connect(f"file:{database_path()}?mode=ro", uri=True) as db:
        docs = [
            json.loads(row[0])
            for row in db.execute("SELECT definition FROM semantic_documents ORDER BY rowid")
        ]
    return [d for d in docs if visible(d, principal, model)]


def compact(doc):
    return {
        key: doc[key]
        for key in ("id", "kind", "name", "aliases", "status", "table_id", "metric_id")
        if key in doc
    } | {"summary": doc.get("meaning", doc.get("description", ""))[:150]}


def normalized(text):
    return re.sub(r"\s+", "", text.casefold())


def search(principal, query="", *, kind=None, limit=60, model=False):
    docs = all_documents(principal, model=model)
    if kind:
        docs = [d for d in docs if d["kind"] == kind]
    if not query.strip():
        return [compact(d) for d in docs[:limit]]
    q = normalized(query)
    terms = list(dict.fromkeys(re.findall(r"[a-z_][a-z_0-9.]*|[\u4e00-\u9fff]{2,}", q)))
    grams = list(
        dict.fromkeys(
            q[i : i + 3] for i in range(len(q) - 2) if re.fullmatch(r"[\u4e00-\u9fff]{3}", q[i : i + 3])
        )
    )[:80]
    fts = {}
    expression = " OR ".join('"' + x.replace('"', '""') + '"' for x in [*terms, *grams] if len(x) >= 3)
    if expression:
        with sqlite3.connect(f"file:{database_path()}?mode=ro", uri=True) as db:
            fts = {
                row[0]: row[1]
                for row in db.execute(
                    "SELECT id,bm25(semantic_search,0,3,1) FROM semantic_search WHERE semantic_search MATCH ? ORDER BY rank LIMIT 500",
                    (expression,),
                )
            }
    ranked = []
    for doc in docs:
        score = 0.0
        reasons = []
        for terms in doc.get("retrieval_terms", []):
            if all(normalized(term) in q for term in terms):
                score += 24
                reasons.append("组合词: " + "+".join(terms))
        if q == normalized(doc["id"]):
            score += 100
            reasons.append("完整ID")
        for alias in [doc["name"], *doc.get("aliases", [])]:
            a = normalized(alias)
            if len(a) >= 2 and a in q:
                score += 8 + min(len(a), 12)
                reasons.append(alias)
            elif len(q) >= 2 and q in a:
                score += 4
        if doc["id"] in fts:
            score += min(5, -fts[doc["id"]])
            reasons.append("FTS5子串")
        if score > 0:
            ranked.append((score, doc, reasons))
    ranked.sort(key=lambda row: (-row[0], row[1]["id"]))
    return [
        compact(d) | {"score": round(score, 3), "matched_by": reasons[:8]}
        for score, d, reasons in ranked[:limit]
    ]


def read_documents(principal, ids, *, model=False, revision=None):
    current = publish()
    if revision and revision != current:
        raise HTTPException(409, detail="语义定义已更新，请重新提问以使用同一版本的口径。")
    if len(ids) > 24:
        raise HTTPException(422, detail="单次最多读取24个语义条目。")
    lookup = {doc["id"]: doc for doc in all_documents(principal, model=model)}
    if any(ident not in lookup for ident in ids):
        raise HTTPException(404, detail="语义条目不存在或不在当前可读范围，未扩大权限。")
    return [lookup[ident] for ident in dict.fromkeys(ids)]


def discover(principal, question, constraints, previous=None):
    # 先返回轻量目录与少量相关指标；planned 只用于解释缺口，不获得编译执行资格。
    docs = all_documents(principal, model=True)
    metrics = {d["id"]: d for d in docs if d["kind"] == "metric"}
    hits = search(principal, question, kind="metric", limit=8, model=True)
    related_questions = search(principal, question, kind="question", limit=3, model=True)
    question_docs = {d["id"]: d for d in docs if d["kind"] == "question"}
    known_question_metrics = [
        "metric:" + metric
        for hit in related_questions
        if normalized(hit["name"]) == normalized(question)
        for metric in question_docs[hit["id"]].get("metric_ids", [])
    ]
    selected = []
    if constraints.get("metric"):
        selected.append("metric:" + constraints["metric"])
    if previous and re.search(r"再|那|改为|换成|上一|这些|其中", question):
        selected.append("metric:" + previous["metric"])
    selected.extend(known_question_metrics)
    selected.extend(h["id"] for h in hits if h["status"] == "available")
    if not selected:
        selected = ["metric:headcount"]
    selected = list(dict.fromkeys(i for i in selected if i in metrics))[:2]
    # A proposed metric with a strong exact alias is disclosed as unavailable, never compiled.
    planned = [
        h["id"]
        for h in hits
        if h["status"] == "planned" and any(r != "FTS5子串" for r in h.get("matched_by", []))
    ]
    selected = list(dict.fromkeys([*planned[:1], *selected]))[:3]
    return {
        "revision": publish(),
        "version": VERSION,
        "query": question,
        "hits": hits,
        "related_questions": related_questions,
        "known_question_metric_ids": known_question_metrics,
        "initial_ids": selected,
        "index": [{"id": d["id"], "name": d["name"], "status": d["status"]} for d in metrics.values()],
        "strategy": "先权限过滤，再别名/ID精确匹配+FTS5子串召回；仅披露相关定义，无向量检索或业务值扫描",
    }


def education_fields(plan):
    if any(
        plan.get(k) for k in ("degree", "education_level", "minimum_education", "schools", "school_tier")
    ) or plan.get("dimension") in ("education", "degree", "school"):
        result = [
            "employee_education.degree",
            "employee_education.education_level",
            "employee_education.graduation_date",
            "employee_education.school_id",
        ]
        if plan.get("minimum_education"):
            result.append("employee_education.education_rank")
        if plan.get("school_tier"):
            result.extend(["schools.is_211", "schools.is_985"])
        return result
    return []


def disclose(principal, ids, constraints, revision, *, extra_ids=()):
    # 渐进披露的出口：读取相关口径及依赖字段，固定字符预算，不无限追加整个目录。
    # revision 将一次工作流绑定到同一份定义，避免途中发布新口径造成解释和执行错位。
    docs = all_documents(principal, model=True)
    lookup = {d["id"]: d for d in docs}
    chosen = read_documents(principal, list(dict.fromkeys([*ids, *extra_ids])), model=True, revision=revision)
    selected = {d["id"]: d for d in chosen}
    field_ids = list(
        dict.fromkeys([*education_fields(constraints), *(f for d in chosen for f in d.get("field_ids", []))])
    )
    for ident in field_ids:
        if ident in lookup and lookup[ident]["kind"] == "field":
            selected[ident] = lookup[ident]
    # A metric can disclose more than a dozen fields, but the aggregate character budget is strict.
    payload = []
    omitted = []
    used = 0
    for doc in selected.values():
        keys = (
            "id",
            "kind",
            "name",
            "meaning",
            "not_meaning",
            "definition",
            "field_ids",
            "data_type",
            "unit",
            "examples",
            "time_rule",
            "null_rule",
            "permission_rule",
            "missing_requirements",
            "status",
            "dimensions",
        )
        item = {k: doc[k] for k in keys if k in doc}
        size = len(json.dumps(item, ensure_ascii=False))
        if used + size > MAX_DISCLOSURE_CHARS:
            omitted.append(doc["id"])
            continue
        payload.append(item)
        used += size
    if any(i not in {d["id"] for d in payload} for i in ids):
        raise HTTPException(422, detail="相关定义超过单次上下文预算，请缩小问题范围。")
    return {
        "documents": payload,
        "disclosed_ids": [d["id"] for d in payload],
        "omitted_ids": omitted,
        "characters": used,
        "budget_characters": MAX_DISCLOSURE_CHARS,
        "revision": revision,
        "examples_policy": "只提供人工格式/枚举示例，不扫描个人实际值；复杂值别名暂不新增",
    }


def inventory(principal, query="", kind=None):
    docs = all_documents(principal)
    return {
        "version": VERSION,
        "revision": publish(),
        "documents": search(principal, query, kind=kind, limit=500),
        "counts": {
            k: sum(d["kind"] == k for d in docs)
            for k in ("table", "field", "metric", "question", "relationship")
        },
        "metric_status": {
            "available": sum(d["kind"] == "metric" and d["status"] == "available" for d in docs),
            "planned": sum(d["kind"] == "metric" and d["status"] == "planned" for d in docs),
        },
        "storage": {
            "source": "semantic/*.json，Git审阅的唯一语义定义源",
            "published": "data/semantic.sqlite，结构化元数据",
            "index": "semantic_search，FTS5派生索引，可重建",
            "vector": "未启用；未来可增加向量召回，但不替代权限和确定性口径",
        },
        "policy": "参考字段与规划指标不等于已开放的查询能力。值仅提供人工示例，暂不扩展口语值字典。",
    }
