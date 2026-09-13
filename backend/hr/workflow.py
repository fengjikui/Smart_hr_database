"""Bounded LangGraph orchestration; SQL and authorization remain deterministic.

Each invocation has isolated state. No checkpoint, cross-user memory, remote tracing,
model-written SQL or dynamic model-selected executable tools are configured.
"""

import asyncio
import json
import re
import time
from datetime import UTC, datetime
from importlib.metadata import version
from typing import TypedDict
from uuid import uuid4

import httpx
from fastapi import HTTPException
from langgraph.graph import END, START, StateGraph
from langsmith import tracing_context
from pydantic import ValidationError

from . import agent, config, semantics
from .db import application, business
from .debug import actor, step
from .intent import enforce, explicit_constraints
from .models import MetadataRequest, QueryPlan
from .query import execute
from .security import audit, scope_ids


class State(TypedDict, total=False):
    principal: dict
    question: str
    previous_id: str | None
    started: float
    as_of: str
    previous: dict | None
    constraints: dict
    discovery: dict
    disclosure: dict
    messages: list[dict]
    plan: QueryPlan | MetadataRequest
    usage: dict
    attempts: int
    repairs: int
    expansions: int
    next: str
    output: dict
    requested_ids: list[str]


def receive(state: State):
    with step(
        "request", "接收问题", {"question": state["question"], "previous_id": state["previous_id"]}
    ) as trace:
        trace.update(
            question=state["question"].strip(),
            received_at=datetime.now(UTC).isoformat(),
            framework="LangGraph",
            workflow_version="hr-graph-1.0",
        )
    return {"question": state["question"].strip()}


def authorize(state: State):
    principal = state["principal"]
    with step("authorization", "身份与人员范围", {"principal_id": principal["id"]}) as trace:
        ids = scope_ids(principal)
        trace.update(
            actor=actor(principal),
            authorized_employee_ids=ids,
            candidate_count=len(ids),
            note="包含历史离职人员；在职数由指标计算。",
            policy_version=config.POLICY_VERSION,
        )
    return {}


def capability(state: State):
    question = state["question"]
    with step("capability", "能力边界检查", {"question": question}) as trace:
        unsupported = re.search(
            r"性别|女性|男性|女员工|男员工|年龄|\d+\s*岁|同比|环比|预测|排名|工资.{0,8}(超过|高于|低于)|薪资.{0,8}(超过|高于|低于)",
            question,
        )
        if unsupported:
            trace.update(allowed=False, matched_text=unsupported.group(0), rule="unsupported_conditions")
            audit(state["principal"], "agent.intent", "unsupported")
            raise HTTPException(
                422,
                detail="当前尚未开放年龄、性别、数值阈值、同比环比、排名或预测条件。系统没有忽略条件执行查询。",
            )
        constraints, notes = explicit_constraints(question)
        trace.update(allowed=True, explicit_constraints=constraints, grounding_notes=notes)
    return {"constraints": constraints}


def context(state: State):
    with step("context", "读取截止日与本人前次计划", {"previous_id": state["previous_id"]}) as trace:
        with business() as db:
            as_of = db.execute("SELECT value FROM dataset_meta WHERE key='as_of'").fetchone()[0]
        previous = None
        if state["previous_id"]:
            with application() as db:
                row = db.execute(
                    "SELECT plan FROM conversations WHERE id=? AND principal_id=? AND outcome=?",
                    (state["previous_id"], state["principal"]["id"], "success"),
                ).fetchone()
            if not row:
                raise HTTPException(404, detail="前次查询不存在或不属于当前身份。请重新描述问题。")
            previous = json.loads(row[0])
        trace.update(
            as_of=as_of,
            previous_plan=previous,
            context_strategy="相关定义逐步读取；不注入全量字段、组织或院校值。",
        )
    return {"as_of": as_of, "previous": previous}


def discover(state: State):
    with step(
        "discovery", "检索相关语义定义", {"question": state["question"], "constraints": state["constraints"]}
    ) as trace:
        result = semantics.discover(
            state["principal"], state["question"], state["constraints"], state["previous"]
        )
        trace.update(result)
    return {"discovery": result}


def make_messages(state: State, disclosure):
    data = {**disclosure, "index": state["discovery"]["index"], "constraints": state["constraints"]}
    return [
        {
            "role": "system",
            "content": agent.instructions(state["principal"], state["as_of"], state["previous"], data),
        },
        {"role": "user", "content": state["question"]},
    ]


def disclose(state: State):
    ids = state["discovery"]["initial_ids"]
    with step(
        "disclosure", "首次披露相关口径与字段", {"ids": ids, "revision": state["discovery"]["revision"]}
    ) as trace:
        result = semantics.disclose(
            state["principal"], ids, state["constraints"], state["discovery"]["revision"]
        )
        trace.update(result)
    planned = next(
        (d for d in result["documents"] if d["kind"] == "metric" and d["status"] == "planned"), None
    )
    if planned:
        return {
            "disclosure": result,
            "next": "decision",
            "plan": QueryPlan(
                kind="clarify",
                message=f"{planned['name']}目前只有规划口径，尚未开放查询。需要：{planned.get('missing_requirements', '补齐数据与编译实现')}"[
                    :300
                ],
            ),
        }
    return {"disclosure": result, "messages": make_messages(state, result), "next": "model"}


async def model(state: State):
    with step("capacity", "模型并发检查", {"max_concurrency": 1, "attempt": state["attempts"] + 1}) as trace:
        if agent._gate.locked():
            raise HTTPException(429, detail="本地模型正在处理一个问题，请稍后重试。固定看板仍可使用。")
        trace.update(available=True)
    try:
        async with agent._gate:
            plan, usage = await agent.ask_model(state["messages"])
    except (ValidationError, ValueError, KeyError, TypeError) as exc:
        if state["repairs"] < 1:
            return {"next": "repair", "attempts": state["attempts"] + 1}
        audit(state["principal"], "agent", "error")
        raise HTTPException(503, detail="模型两次未产生有效结构，未执行数据库查询。") from exc
    except httpx.TimeoutException as exc:
        audit(state["principal"], "agent", "timeout")
        raise HTTPException(504, detail="本地模型响应超时。请重试或使用固定看板。") from exc
    except httpx.HTTPError as exc:
        audit(state["principal"], "agent", "error")
        raise HTTPException(503, detail="本地模型暂时不可用，未执行数据库查询，请检查 LM Studio。") from exc
    return {
        "plan": plan,
        "usage": usage,
        "attempts": state["attempts"] + 1,
        "next": "inspect" if isinstance(plan, MetadataRequest) else "intent",
    }


def repair(state: State):
    with step("repair", "结构错误修复重试", {"attempt": 1, "maximum_retries": 1}) as trace:
        instruction = {
            "role": "user",
            "content": "上次输出未通过结构校验。仅输出合法JSON；查询必须明确metric，需要补充定义时输出kind=inspect和ids/search。不得编造字段。",
        }
        trace.update(appended_message=instruction)
    return {"messages": [*state["messages"], instruction], "repairs": 1}


def intent(state: State):
    plan = state["plan"]
    with step(
        "intent", "明细意图与计划校正", {"question": state["question"], "model_plan": plan.model_dump()}
    ) as trace:
        corrected = (
            plan.kind == "metric"
            and plan.metric in ("abnormal_count", "late_count")
            and bool(re.search(r"明细|名单|哪些人", state["question"]))
        )
        if corrected:
            plan = plan.model_copy(update={"kind": "attendance", "dimension": "none"})
        plan, changes = enforce(plan, state["question"], state["constraints"])
        trace.update(
            corrected=corrected or bool(changes),
            grounded_changes=changes,
            explicit_constraints=state["constraints"],
            final_plan=plan.model_dump(),
            rule="不得遗漏明确条件；记录模型计划与校正值。",
        )
    if plan.kind in ("clarify", "refuse"):
        return {"plan": plan, "next": "decision"}
    required = ["metric:" + plan.metric, *semantics.education_fields(plan.model_dump())]
    missing = [i for i in required if i not in state["disclosure"]["disclosed_ids"]]
    return {"plan": plan, "requested_ids": missing, "next": "inspect" if missing else "reauthorize"}


def current_principal(state: State):
    with application() as db:
        current = db.execute(
            "SELECT * FROM principals WHERE id=? AND enabled=1", (state["principal"]["id"],)
        ).fetchone()
    if not current:
        raise HTTPException(403, detail="当前身份授权已失效。")
    return dict(current)


def inspect(state: State):
    with step(
        "inspection",
        "补充读取请求与边界",
        {
            "request": state["plan"].model_dump(),
            "automatically_required_ids": state.get("requested_ids", []),
            "expansions_used": state["expansions"],
            "maximum_expansions": semantics.MAX_EXPANSIONS,
        },
    ) as trace:
        if state["expansions"] >= semantics.MAX_EXPANSIONS:
            trace.update(allowed=False, database_executed=False, reason="补充读取次数已用完")
            return {
                "next": "decision",
                "plan": QueryPlan(
                    kind="clarify",
                    message="两轮补充读取后仍未形成满足口径的计划。请把问题缩小为一个指标，并明确统计对象和时间。",
                ),
            }
        principal = current_principal(state)
        plan = state["plan"]
        ids = []
        if isinstance(plan, MetadataRequest):
            ids = list(plan.ids)
            if plan.search:
                hits = semantics.search(principal, plan.search, kind="metric", limit=2, model=True)
                if not hits:
                    hits = semantics.search(principal, plan.search, kind="field", limit=2, model=True)
                trace["search_results"] = hits
                ids.extend(h["id"] for h in hits)
        else:
            ids = ["metric:" + plan.metric, *semantics.education_fields(plan.model_dump())]
        ids = list(dict.fromkeys(ids))
        if not ids:
            trace.update(allowed=False, reason="无匹配定义")
            return {
                "next": "decision",
                "plan": QueryPlan(kind="clarify", message="没有找到对应的已发布口径，请明确指标名称。"),
            }
        # Exact IDs are validated against the current grant; never expose missing/private ID differences.
        semantics.read_documents(principal, ids, model=True, revision=state["discovery"]["revision"])
        if not any(i.startswith("metric:") for i in ids):
            ids = [*ids, *(i for i in state["disclosure"]["disclosed_ids"] if i.startswith("metric:"))]
        trace.update(allowed=True, requested_ids=ids, current_actor=actor(principal))
    constraints = state["constraints"] if isinstance(plan, MetadataRequest) else plan.model_dump()
    with step(
        "disclosure",
        "补充披露并重建有限上下文",
        {"ids": ids, "iteration": state["expansions"] + 1, "revision": state["discovery"]["revision"]},
    ) as trace:
        result = semantics.disclose(principal, ids, constraints, state["discovery"]["revision"])
        trace.update(result)
    planned = next(
        (d for d in result["documents"] if d["kind"] == "metric" and d["status"] == "planned"), None
    )
    if planned:
        return {
            "disclosure": result,
            "expansions": state["expansions"] + 1,
            "plan": QueryPlan(
                kind="clarify",
                message=f"{planned['name']}尚未开放查询，需要：{planned.get('missing_requirements', '补齐实现')}"[
                    :300
                ],
            ),
            "next": "decision",
        }
    # Replace irrelevant initial definitions instead of endlessly appending transcripts.
    messages = make_messages({**state, "principal": principal}, result)
    messages.append(
        {
            "role": "user",
            "content": f"已按需补充读取定义。剩余补充次数：{semantics.MAX_EXPANSIONS - state['expansions'] - 1}。请依据上述完整口径重新输出计划；若仍无法满足请求请澄清。",
        }
    )
    return {
        "principal": principal,
        "disclosure": result,
        "messages": messages,
        "expansions": state["expansions"] + 1,
        "next": "model",
    }


def reauthorize(state: State):
    with step(
        "reauthorize",
        "执行前重新鉴权与口径覆盖检查",
        {"original_actor": actor(state["principal"]), "semantic_revision": state["discovery"]["revision"]},
    ) as trace:
        current = current_principal(state)
        required = ["metric:" + state["plan"].metric, *semantics.education_fields(state["plan"].model_dump())]
        semantics.read_documents(current, required, model=True, revision=state["discovery"]["revision"])
        if not set(required) <= set(state["disclosure"]["disclosed_ids"]):
            raise HTTPException(422, detail="执行所需口径尚未披露，已停止。")
        trace.update(
            current_actor=actor(current),
            authorized_employee_ids=scope_ids(current),
            required_ids=required,
            covered=True,
        )
    return {"principal": current}


async def query(state: State):
    output = await asyncio.to_thread(execute, state["principal"], state["plan"])
    return {"output": output}


def decision(state: State):
    plan = state["plan"]
    with step("decision", "返回澄清或拒绝", {"plan": plan.model_dump()}) as trace:
        output = {
            "status": plan.kind,
            "summary": plan.message or "请明确希望查看的指标或时间范围。",
            "plan": plan.model_dump(),
            "rows": [],
            "columns": [],
        }
        trace.update(output, database_executed=False)
        audit(state["principal"], "agent", plan.kind)
    return {"output": output}


def persist(state: State):
    output = {
        **state["output"],
        "model": config.MODEL_ID,
        "model_ms": round((time.perf_counter() - state["started"]) * 1000, 2),
        "usage": state.get("usage", {}),
        "orchestration": {
            "framework": "LangGraph",
            "version": version("langgraph"),
            "workflow_version": "hr-graph-1.0",
            "model_calls": state["attempts"],
            "repairs": state["repairs"],
            "metadata_expansions": state["expansions"],
            "semantic_revision": state["discovery"]["revision"],
            "disclosed_ids": state["disclosure"]["disclosed_ids"],
        },
    }
    with step(
        "conversation",
        "保存本轮查询计划",
        {
            "owner_id": state["principal"]["id"],
            "plan": state["plan"].model_dump(),
            "outcome": output["status"],
        },
    ) as trace:
        ident = uuid4().hex
        with application() as db:
            db.execute(
                "INSERT INTO conversations VALUES (?,?,?,?,?,?)",
                (
                    ident,
                    state["principal"]["id"],
                    state["question"],
                    json.dumps(state["plan"].model_dump(), ensure_ascii=False),
                    output["status"],
                    datetime.now(UTC).isoformat(),
                ),
            )
        output["conversation_id"] = ident
        trace.update(conversation_id=ident, saved=True, orchestration=output["orchestration"])
    return {"output": output}


builder = StateGraph(State)
for name, node in [
    ("receive", receive),
    ("authorize", authorize),
    ("capability", capability),
    ("context", context),
    ("discover", discover),
    ("disclose", disclose),
    ("model", model),
    ("repair", repair),
    ("intent", intent),
    ("inspect", inspect),
    ("reauthorize", reauthorize),
    ("query", query),
    ("decision", decision),
    ("persist", persist),
]:
    builder.add_node(name, node)
for start, end in [
    (START, "receive"),
    ("receive", "authorize"),
    ("authorize", "capability"),
    ("capability", "context"),
    ("context", "discover"),
    ("discover", "disclose"),
    ("repair", "model"),
    ("reauthorize", "query"),
    ("query", "persist"),
    ("decision", "persist"),
    ("persist", END),
]:
    builder.add_edge(start, end)
for name, targets in [
    ("disclose", ["model", "decision"]),
    ("model", ["repair", "inspect", "intent"]),
    ("intent", ["decision", "inspect", "reauthorize"]),
    ("inspect", ["model", "decision"]),
]:
    builder.add_conditional_edges(name, lambda state: state["next"], {target: target for target in targets})
graph = builder.compile(name="hr-governed-query")


def descriptor():
    compiled = graph.get_graph()
    labels = {
        "receive": "接收问题",
        "authorize": "身份与范围",
        "capability": "能力边界",
        "context": "截止日与前次计划",
        "discover": "检索语义",
        "disclose": "首次披露",
        "model": "本地模型与结构校验",
        "repair": "结构修复",
        "intent": "意图校验",
        "inspect": "按需补充定义",
        "reauthorize": "重新鉴权与口径覆盖",
        "query": "编译 / 查询 / 保护 / 格式化 / 审计",
        "decision": "澄清或拒绝",
        "persist": "保存计划",
    }
    return {
        "framework": "LangGraph",
        "version": version("langgraph"),
        "workflow_version": "hr-graph-1.0",
        "nodes": [{"id": key, "label": labels[key]} for key in labels],
        "edges": [
            {"source": e.source, "target": e.target, "conditional": e.conditional} for e in compiled.edges
        ],
        "mermaid": compiled.draw_mermaid(),
        "limits": {
            "metadata_expansions": semantics.MAX_EXPANSIONS,
            "schema_repairs": 1,
            "model_calls": 4,
            "disclosure_characters": semantics.MAX_DISCLOSURE_CHARS,
            "concurrent_model_calls": 1,
            "recursion_limit": 32,
        },
        "persistence": "每请求独立状态；不启用共享checkpointer。授权后的调试输出仅保存在本地应用库。",
        "external_tracing": False,
    }


async def run(principal, question, previous_id=None):
    # Even if a developer shell enables LangSmith, HR metadata and prompts stay local.
    with tracing_context(enabled=False):
        result = await graph.ainvoke(
            {
                "principal": principal,
                "question": question,
                "previous_id": previous_id,
                "started": time.perf_counter(),
                "attempts": 0,
                "repairs": 0,
                "expansions": 0,
            },
            config={"recursion_limit": 32},
        )
    return result["output"]
