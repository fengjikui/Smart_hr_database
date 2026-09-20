"""有界 LangGraph：身份校验→目录披露→模型计划→校验→执行→解释与存档。

模型只选择结构化 Plan，不持有数据库凭据、不生成可自由执行的 SQL。
数字回答由已执行单元格套入确定性模板，避免第二次模型生成时改写数字。
补读定义和修正计划都经过 validate 节点路由，并有次数与总耗时上限。
"""

import asyncio
import json
import re
import time
from datetime import date, timedelta
from typing import Any, TypedDict

import httpx
from fastapi import HTTPException
from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from . import auth, config, grounding, query, registry, service, store
from .model import _gate
from .schema import Plan


class State(TypedDict, total=False):
    # principal/fingerprint 是本轮可信上下文；question/candidate 是待校验输入。
    principal: dict
    question: str
    parent_id: str | None
    fingerprint: str
    previous: dict | None
    catalog: dict
    documents: list
    messages: list
    trace: list
    # candidate 保留模型原始候选；plan 只在校验成功后写入，execute 不读原候选。
    candidate: dict
    plan: Any
    result: dict
    attempts: int
    inspections: int
    errors: list
    next: str


def record(s, name, inputs, outputs, started):
    """追加可展示的节点输入/输出；最终与本人历史绑定，不能在这里写入凭据。"""
    s["trace"].append(
        {
            "name": name,
            "input": inputs,
            "output": outputs,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        }
    )


def date_hints(question):
    """将明确相对时间绑定到数据快照日；这里不使用电脑当天日期漂移演示结果。"""
    today = date.fromisoformat(store.AS_OF)
    hints = {}
    monday = today - timedelta(days=today.weekday())
    if "上周" in question:
        hints = {"start_date": str(monday - timedelta(days=7)), "end_date": str(monday - timedelta(days=1))}
    match = re.search(r"(?:过去|近|最近)(\d+)天", question)
    if match:
        hints = {"start_date": str(today - timedelta(days=int(match[1]) - 1)), "end_date": str(today)}
    match = re.search(r"未来(\d+)天", question)
    if match:
        hints = {
            "start_date": str(today + timedelta(days=1)),
            "end_date": str(today + timedelta(days=int(match[1]))),
        }
    if "上季度" in question:
        qstart = date(today.year, ((today.month - 1) // 3) * 3 + 1, 1)
        end = qstart - timedelta(days=1)
        hints = {"start_date": str(date(end.year, ((end.month - 1) // 3) * 3 + 1, 1)), "end_date": str(end)}
    match = re.search(r"今年(\d{1,2})月至?(\d{1,2})月", question)
    if match:
        import calendar

        a, b = map(int, match.groups())
        if 1 <= a <= b <= 12:
            hints = {
                "start_date": str(date(today.year, a, 1)),
                "end_date": str(date(today.year, b, calendar.monthrange(today.year, b)[1])),
            }
    if not hints and "今年" in question:
        hints = {"start_date": str(date(today.year, 1, 1)), "end_date": str(today)}
    return hints


def authorize(s):
    """固定本轮身份与权限指纹，只从本人且仍有效的成功历史恢复上一轮 Plan。"""
    started = time.perf_counter()
    p = s["principal"]
    auth.refresh(p)
    s["fingerprint"] = auth.fingerprint(p)
    previous = None
    if s.get("parent_id"):
        old = service.read_run(p, s["parent_id"])
        if old["status"] != "success":
            raise HTTPException(422, "只能从成功的历史查询继续追问")
        previous = old["plan"]
    s.update(previous=previous, attempts=0, inspections=0, errors=[], documents=[])
    record(
        s,
        "身份与历史校验",
        {"persona": p["id"], "previous_id": s.get("parent_id")},
        {
            "policy_version": auth.policy(p)["version"],
            "previous_plan": previous,
            "visible_count": len(auth.grants(p)["ids"]),
        },
        started,
    )
    return s


def discover(s):
    """先披露授权目录索引，再给匹配词条详情；模型可通过 inspect 有限补读。

    这里是版本化字段目录检索，不是向量数据库检索，也不读取验收题目答案。
    部门候选来自当前授权人员，不能把不可见部门作为模型上下文泄露出去。
    """
    started = time.perf_counter()
    catalog = registry.catalog(s["principal"])
    s["catalog"] = catalog
    index = [
        {"id": d["id"], "label": d["label"], "aliases": d["aliases"]}
        for d in catalog["fields"] + catalog["metrics"]
    ]
    matched = [
        d
        for d in catalog["fields"] + catalog["metrics"]
        if any(a in s["question"] for a in [d["label"]] + d["aliases"])
    ]
    required = {"metric.count"}
    for doc in matched[:8]:
        required.add(doc["id"])
        required.update(doc.get("fields", []))
    s["documents"] = registry.disclose(s["principal"], sorted(required))
    field_index = {d["key"]: {"label": d["label"], "meaning": d["description"]} for d in catalog["fields"]}
    metric_index = {
        d["key"]: {"label": d["label"], "definition": d["definition"]} for d in catalog["metrics"]
    }
    instruction = f"""你是HR查询计划器，只生成JSON，禁止SQL。/no_think
一名员工一条当前记录，字段表为people。合成数据截止日{store.AS_OF}，时区Asia/Shanghai。
字段索引：{json.dumps(field_index, ensure_ascii=False)}
指标索引：{json.dumps(metric_index, ensure_ascii=False)}
本次已披露详情：{json.dumps(s["documents"], ensure_ascii=False)}
分组维度：{json.dumps(catalog["dimensions"], ensure_ascii=False)}
可选择的部门：{json.dumps(catalog["departments"], ensure_ascii=False)}
前次成功计划（追问时继承未改变条件）：{json.dumps(s["previous"], ensure_ascii=False)}
确定性时间解释：{json.dumps(date_hints(s["question"]), ensure_ascii=False)}
明确条件：{json.dumps(grounding.constraints(s["question"], s["previous"]), ensure_ascii=False)}
规则：
1. kind=aggregate统计，kind=people明细；缺少口径kind=inspect，inspect_ids最多6个索引ID（people.字段、metric.指标），最多2轮；不支持或有歧义kind=clarify并说明message。不得忽略不能表达的条件。
2. scope=all是当前全部授权，绝不是扩大权限；直属及间接用reports且排除本人；只直属direct，只间接indirect；本人服务HRBP用scope=hrbp，通过下属HRBP查看用scope=inherited_hrbp。禁止使用dept_hrbp_id=self作为过滤，self不是人员主键；范围由scope表达。直属与间接分别展示group_by包含relation。默认在职population=active；入离职期间人数/明细用all，不要求现在仍在职；今年已转正用confirmed。
3. 日期用YYYY-MM-DD。date_field入职onboard_date、离职termin_date、合同到期contract_end_date、实际转正confirmation_date、当前任职current_employment_start_date。入职+离职+净增用employment_events及hires,departures,net_change三个指标。月份用与日期对应的onboard_month/termin_month/event_month/confirmation_month，配合dept_cn_name最多2个维度。没有期间时日期字段和起止为null。
4. 按部门、每个部门、两个部门对比用group_by=["dept_cn_name"]，部门仅填写明确名称，学校/专业多值OR用in，一个字段多条件与其他字段AND。不要为“各部门”填写全部部门列表。
5. “硕士及以上”筛选diploma_code_desc gte 硕士研究生；全日制full_time_flag eq 是；校招hire_type_code_desc eq 校园招聘；年龄区间gte/lte含边界，值均字符串。学位博士是degree_code_desc，不是学历。博士学位人数用doctors_count，自动检查毕业时间。仅目前学历记录，非完整历史。
6. 比例使用metrics中现有ratio指标，不能同时用对应条件筛掉分母；985、211同时查询给school_985_count,school_211_count,school_985_ratio,school_211_ratio。硕士及以上人数+占比给count,masters_count,masters_ratio。外包比例及人数总数给count,outsource_count,outsource_ratio。
7. 人员明细columns只包含问题点名的字段，按提问顺序；专业first_major，毕业时间education_expired_date，部门dept_cn_name。排序order_by包含field和direction asc/desc；未要求排序则空列表。统计不带多余columns条件。零月份服务端补齐。
8. 追问给出完整新计划，继承前次人群、部门、时间和未修改筛选；“把学校改成”必须替换原school_name条件。没有前次上下文时不能猜“这些人”。所有教育条件作用同一当前记录。
9. 不能查不存在的薪酬、考勤、绩效或历史汇报线；拒绝写入、删除、自由SQL及绕过权限。不要将无法回答的问题换成人数。
10. 必须明确kind与metrics（统计）或columns（明细）；page=1,page_size=50；最多5指标、12明细字段、12筛选。不填person_id权限集合，由后端强制处理。"""
    s["messages"] = [{"role": "system", "content": instruction}, {"role": "user", "content": s["question"]}]
    record(
        s,
        "目录检索与初步披露",
        {"question": s["question"], "catalog_version": catalog["version"]},
        {"index": index, "documents": s["documents"], "date_hints": date_hints(s["question"])},
        started,
    )
    return s


async def call_model(messages):
    """请求本地 OpenAI 兼容端点，约束 JSON Schema；只返回候选计划及调试证据。"""
    schema = Plan.model_json_schema()
    schema["required"] = list(schema["properties"])
    for definition in schema.get("$defs", {}).values():
        if "properties" in definition:
            definition["required"] = list(definition["properties"])
    payload = {
        "model": config.MODEL_ID,
        "messages": messages,
        "temperature": 0,
        "max_tokens": 1600,
        "chat_template_kwargs": {"enable_thinking": False},
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "hr_query_plan", "schema": schema},
        },
    }
    async with httpx.AsyncClient(trust_env=False, timeout=config.MODEL_TIMEOUT) as client:
        response = await client.post(config.MODEL_URL + "/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()
    choice = data["choices"][0]
    if choice.get("finish_reason") == "length":
        raise ValueError("模型输出被长度限制截断")
    message = choice["message"]
    raw = message.get("content") or message.get("reasoning_content", "")
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.S).strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    candidate = json.loads(raw)
    if not isinstance(candidate, dict):
        raise ValueError("模型未输出JSON对象")
    return candidate, {
        "request": payload,
        "candidate": candidate,
        "usage": data.get("usage", {}),
        "finish_reason": choice.get("finish_reason"),
    }


async def model_node(s):
    """一次模型调用计为一次 attempt；协议/连接失败转为澄清，不尝试猜测执行。"""
    started = time.perf_counter()
    s["attempts"] += 1
    try:
        candidate, detail = await call_model(s["messages"])
        s["candidate"] = candidate
        record(s, "模型生成计划", {"attempt": s["attempts"], "messages": s["messages"]}, detail, started)
    except (ValueError, httpx.HTTPError, KeyError) as exc:
        s["candidate"] = {"kind": "clarify", "message": "本地模型暂未返回有效计划，请稍后重试。"}
        record(s, "模型调用失败", {"attempt": s["attempts"]}, {"error_type": type(exc).__name__}, started)
    return s


def validate_node(s):
    """将候选变成可信 Plan，或设置 next 指向补读、重试、结束。

    依次检查显式类型→可审计条件绑定→Pydantic 结构→字段/范围权限→口语条件。
    inspect 最多两次；一般计划错误最多获得一次修正机会，总模型尝试不超过四次。
    401/403/409 表示身份或权限问题，直接 blocked，不能让模型反复尝试绕过。
    """
    started = time.perf_counter()
    candidate = s["candidate"]
    try:
        if candidate.get("kind") not in ("aggregate", "people", "inspect", "clarify"):
            raise ValueError("必须明确查询类型")
        if candidate["kind"] == "aggregate" and not candidate.get("metrics"):
            raise ValueError("必须明确统计指标")
        if candidate["kind"] == "people" and not candidate.get("columns"):
            raise ValueError("必须明确请求字段")
        candidate, bindings = grounding.normalize(
            s["question"], candidate, s["previous"], date_hints(s["question"])
        )
        # 规则补齐必须单列 trace，不能把修正后的成功算作模型原始输出正确。
        if bindings:
            record(
                s,
                "明确条件绑定（规则补齐）",
                {"raw_candidate": s["candidate"]},
                {"changes": bindings, "bound_candidate": candidate, "model_raw_correct": False},
                started,
            )
        plan = Plan.model_validate(candidate)
        if plan.kind == "inspect":
            if s["inspections"] >= 2 or s["attempts"] >= 4:
                raise ValueError("已达到口径补读上限")
            docs = registry.disclose(s["principal"], plan.inspect_ids)
            if not docs:
                raise ValueError("未找到这些授权定义，请使用目录中的ID")
            s["inspections"] += 1
            s["documents"].extend(docs)
            s["messages"].extend(
                [
                    {"role": "assistant", "content": json.dumps(candidate, ensure_ascii=False)},
                    {
                        "role": "user",
                        "content": "补充定义："
                        + json.dumps(docs, ensure_ascii=False)
                        + "。请生成计划或明确缺少什么。",
                    },
                ]
            )
            s["next"] = "model"
            record(s, "按需补读", {"ids": plan.inspect_ids}, {"documents": docs}, started)
            return s
        if plan.kind == "clarify":
            s["result"] = {"status": "clarify", "message": plan.message or "请说明需要查询的HR字段或指标。"}
            s["next"] = "finish"
        else:
            query.validate(s["principal"], plan)
            grounded = grounding.check(s["question"], plan, s["previous"], s["catalog"]["departments"])
            record(
                s, "提问条件对齐", {"question": s["question"], "plan": plan.model_dump()}, grounded, started
            )
            # 再次独立核对时间，防止模型修正其他条件时悄悄丢掉日期限定。
            hints = date_hints(s["question"])
            if hints and any(getattr(plan, k) != v for k, v in hints.items()):
                raise ValueError("日期条件必须保留：" + json.dumps(hints))
            if not s["previous"] and grounding.needs_previous(s["question"]):
                raise ValueError("当前缺少前次成功查询上下文，请先完成查询或从历史恢复")
            s["plan"] = plan
            s["next"] = "execute"
        record(
            s,
            "结构、口径与字段权限校验",
            {"candidate": candidate},
            {"valid": True, "next": s["next"]},
            started,
        )
    except (ValueError, ValidationError, HTTPException) as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)[:700]
        s["errors"].append(detail)
        record(
            s,
            "结构、口径与字段权限校验",
            {"candidate": candidate},
            {"valid": False, "error": detail},
            started,
        )
        if isinstance(exc, HTTPException) and exc.status_code in (401, 403, 409):
            s["result"] = {"status": "blocked", "message": detail}
            s["next"] = "finish"
        elif len(s["errors"]) <= 1 and s["attempts"] < 4:
            s["messages"].extend(
                [
                    {"role": "assistant", "content": json.dumps(candidate, ensure_ascii=False)},
                    {
                        "role": "user",
                        "content": "计划未执行，校验失败："
                        + str(detail)
                        + "。请修正；无法支持则clarify，不得忽略原条件。",
                    },
                ]
            )
            s["next"] = "model"
        else:
            s["result"] = {"status": "clarify", "message": "计划未通过校验：" + str(detail)}
            s["next"] = "finish"
    return s


def execute_node(s):
    """模型执行可能耗时：先检查期间是否撤权，再经统一 service 运行查询。"""
    started = time.perf_counter()
    auth.refresh(s["principal"])
    if s["fingerprint"] != auth.fingerprint(s["principal"]):
        raise HTTPException(409, "权限或数据在模型执行期间变化，请重新提问")
    s["result"] = service.run_query(s["principal"], s["plan"])
    record(
        s,
        "重新鉴权与只读SQL执行",
        {"plan": s["plan"].model_dump(), "policy_version": auth.policy(s["principal"])["version"]},
        {
            k: s["result"][k]
            for k in ("sql", "parameters", "rows", "totals", "total_rows", "duration_ms", "scope_count",
                      "execution_backend", "source_queries") if k in s["result"]
        },
        started,
    )
    return s


def finish_node(s):
    """成功/澄清/阻止都保存节点轨迹；存档前仍需与本轮开始的权限指纹一致。"""
    started = time.perf_counter()
    record(
        s,
        "结果组织",
        {"status": s["result"]["status"], "totals": s["result"].get("totals")},
        {
            "summary": s["result"].get("summary", s["result"].get("message")),
            "numeric_source": "执行结果单元格，确定性模板，无模型自由补写数字",
        },
        started,
    )
    s["result"] = service.save_run(
        s["principal"], s["question"], s["result"], s.get("parent_id"), s["trace"], s["fingerprint"]
    )
    return s


# 唯一回边是 validate→model；execute 不能返回模型生成新 SQL，也不存在无界循环。
# LangGraph 的 recursion_limit 约束节点步数，与人员汇报线的递归深度没有关系。
_builder = StateGraph(State)
for name, fn in [
    ("authorize", authorize),
    ("discover", discover),
    ("model", model_node),
    ("validate", validate_node),
    ("execute", execute_node),
    ("finish", finish_node),
]:
    _builder.add_node(name, fn)
_builder.add_edge(START, "authorize")
_builder.add_edge("authorize", "discover")
_builder.add_edge("discover", "model")
_builder.add_edge("model", "validate")
_builder.add_conditional_edges(
    "validate", lambda s: s["next"], {"model": "model", "execute": "execute", "finish": "finish"}
)
_builder.add_edge("execute", "finish")
_builder.add_edge("finish", END)
GRAPH = _builder.compile()


async def answer(p, body):
    """API 的异步问数入口：限制本机模型并发，并给整张图设置总超时。"""
    try:
        await asyncio.wait_for(_gate.acquire(), timeout=0.1)
    except TimeoutError as exc:
        raise HTTPException(429, "本地模型正处理另一个问题，请稍后重试") from exc
    try:
        result = await asyncio.wait_for(
            GRAPH.ainvoke(
                {"principal": p, "question": body.question, "parent_id": body.previous_id, "trace": []},
                config={"recursion_limit": 20},
            ),
            timeout=180,
        )
        return result["result"]
    except TimeoutError as exc:
        raise HTTPException(504, "本地模型处理超时，请重试或简化问题") from exc
    finally:
        _gate.release()
