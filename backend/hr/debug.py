"""Persist actual pipeline I/O, scoped to its owner and current grant snapshot."""

import hashlib
import json
import re
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError

from . import config
from .db import application
from .security import scope_ids

# V1 节点日志与应用库中的 debug_runs 对应；V2 自有运行记录，不共用此表。
# 日志里有授权内业务输出，读取时既校验归属，也要求当前授权指纹与记录时一致。
CURRENT_RUN = ContextVar("hr_debug_run", default=None)
GRANT_FIELDS = (
    "id",
    "employee_id",
    "role",
    "scope_mode",
    "scope_root",
    "salary_aggregate",
    "can_export",
    "enabled",
    "policy_version",
)


def now():
    return datetime.now(UTC).isoformat()


def safe(value):
    # 对凭据/内部推理脱敏并限制体积；它只是日志清洗，不代替身份与行权限检查。
    if isinstance(value, dict):
        result = {
            str(k): "[已脱敏]"
            if re.search(
                r"csrf|cookie|authorization|token_hash|api_key|password|reasoning_content", str(k), re.I
            )
            else safe(v)
            for k, v in list(value.items())[:1000]
        }
        if len(value) > 1000:
            result["_truncated_fields"] = len(value) - 1000
        return result
    if isinstance(value, (list, tuple)):
        result = [safe(v) for v in value[:500]]
        if len(value) > 500:
            result.append({"_truncated_items": len(value) - 500})
        return result
    if isinstance(value, str):
        value = re.sub(r"<think>.*?</think>", "[内部推理已省略]", value, flags=re.S)
        value = re.sub(r"(?i)Bearer\s+[^\s\"']+|sk-[A-Za-z0-9_-]{12,}", "[凭据已脱敏]", value)
        return value if len(value) <= 40000 else value[:40000] + f"\n[截断：原文{len(value)}字符]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return safe(str(value))


def actor(principal):
    return {k: principal.get(k) for k in GRANT_FIELDS}


def grant_fingerprint(principal):
    payload = {"actor": actor(principal), "scope": scope_ids(principal), "policy": config.POLICY_VERSION}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def ensure_schema(path=None):
    with application(path) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS debug_runs (
            id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES principals(id),
            grant_fingerprint TEXT NOT NULL, question TEXT NOT NULL, status TEXT NOT NULL,
            started_at TEXT NOT NULL, finished_at TEXT, duration_ms REAL NOT NULL DEFAULT 0,
            payload TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_debug_owner ON debug_runs(owner_id, started_at DESC);
        """)


def recover_interrupted():
    with application() as db:
        for row in db.execute("SELECT id,payload FROM debug_runs WHERE status='running'").fetchall():
            payload = json.loads(row["payload"])
            for node in payload["nodes"]:
                if node["status"] == "running":
                    node.update(status="interrupted", error={"message": "服务重启，执行未完成。"})
            payload.update(
                status="interrupted", finished_at=now(), error={"message": "服务重启，执行未完成。"}
            )
            db.execute(
                "UPDATE debug_runs SET status=?,finished_at=?,payload=? WHERE id=?",
                ("interrupted", payload["finished_at"], json.dumps(payload, ensure_ascii=False), row["id"]),
            )


def error_info(error):
    if isinstance(error, ValidationError):
        return {
            "type": "SchemaValidationError",
            "message": "模型输出未通过查询计划结构校验",
            "issues": error.errors(include_input=False, include_context=False),
        }
    if isinstance(error, HTTPException):
        return {"type": "HTTPException", "status_code": error.status_code, "message": error.detail}
    return {"type": type(error).__name__, "message": safe(str(error))}


class DebugRun:
    # 节点开始、结束均落盘；进程中断后可保留已完成部分，而不是伪造完整成功轨迹。
    def __init__(self, principal, question):
        ensure_schema()
        self.owner = principal["id"]
        self.fingerprint = grant_fingerprint(principal)
        self.started = time.perf_counter()
        self.data = {
            "id": uuid4().hex,
            "question": safe(question),
            "owner_id": self.owner,
            "status": "running",
            "started_at": now(),
            "finished_at": None,
            "duration_ms": 0,
            "model": config.MODEL_ID,
            "catalog_version": config.CATALOG_VERSION,
            "nodes": [],
            "result": None,
            "error": None,
            "capture_policy": "仅当前身份且授权未变化时可读；记录应用输入输出。凭据和内部推理脱敏；薪酬原始聚合不记录，结果保护后再展示。最多500项数组、1000字段对象、40000字符文本，截断会标注。",
        }
        self.persist()

    @property
    def id(self):
        return self.data["id"]

    def persist(self):
        self.data["duration_ms"] = round((time.perf_counter() - self.started) * 1000, 2)
        with application() as db:
            db.execute(
                "INSERT INTO debug_runs VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status,finished_at=excluded.finished_at,duration_ms=excluded.duration_ms,payload=excluded.payload",
                (
                    self.id,
                    self.owner,
                    self.fingerprint,
                    self.data["question"],
                    self.data["status"],
                    self.data["started_at"],
                    self.data["finished_at"],
                    self.data["duration_ms"],
                    json.dumps(self.data, ensure_ascii=False),
                ),
            )
            db.execute(
                "DELETE FROM debug_runs WHERE owner_id=? AND status!='running' AND id NOT IN (SELECT id FROM debug_runs WHERE owner_id=? ORDER BY started_at DESC LIMIT 50)",
                (self.owner, self.owner),
            )

    @contextmanager
    def step(self, key, name, inputs):
        start = time.perf_counter()
        node = {
            "id": f"{key}-{len(self.data['nodes']) + 1}",
            "key": key,
            "name": name,
            "status": "running",
            "started_at": now(),
            "duration_ms": 0,
            "input": safe(inputs),
            "output": None,
            "error": None,
        }
        self.data["nodes"].append(node)
        self.persist()
        output = {}
        try:
            yield output
        except BaseException as exc:
            node.update(
                status="error" if isinstance(exc, Exception) else "interrupted", error=safe(error_info(exc))
            )
            raise
        else:
            node["status"] = "success"
        finally:
            node["output"] = safe(output)
            node["duration_ms"] = round((time.perf_counter() - start) * 1000, 2)
            self.persist()

    def finish(self, status, result=None, error=None):
        self.data.update(status=status, finished_at=now(), result=safe(result), error=safe(error))
        self.persist()


@contextmanager
def step(key, name, inputs):
    run = CURRENT_RUN.get()
    if run is None:
        yield {}
    else:
        with run.step(key, name, inputs) as output:
            yield output


def list_runs(principal):
    fingerprint = grant_fingerprint(principal)
    with application() as db:
        return [
            dict(row)
            for row in db.execute(
                "SELECT id,question,status,started_at,finished_at,duration_ms FROM debug_runs WHERE owner_id=? AND grant_fingerprint=? ORDER BY started_at DESC LIMIT 50",
                (principal["id"], fingerprint),
            )
        ]


def read_run(principal, run_id):
    # 撤权后不再暴露旧日志：owner 与当前 grant_fingerprint 同时匹配才允许读。
    fingerprint = grant_fingerprint(principal)
    with application() as db:
        row = db.execute(
            "SELECT payload FROM debug_runs WHERE id=? AND owner_id=? AND grant_fingerprint=?",
            (run_id, principal["id"], fingerprint),
        ).fetchone()
    if not row:
        raise HTTPException(404, detail="调试记录不存在、不属于当前身份，或原授权已变化。")
    return json.loads(row[0])
