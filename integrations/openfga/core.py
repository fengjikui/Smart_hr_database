"""Translate factual records to tuples; OpenFGA alone evaluates authorization."""

import json
import os
import subprocess
import tempfile
import threading
import time
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import httpx
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from integrations.openfga.runtime import BIN, LOCAL, ROOT

# 独立 OpenFGA 权限实验：事实来自本目录 fixtures.json/已发布配置，不读取 V1/V2 数据库。
# 应用负责校验事实、同步直接关系、查询并执行引擎结论；递归授权判断交给 OpenFGA。
# OpenFGA 不替我们执行业务 SQL，也不会自动成为 V2 Agent 当前的授权后端。
Identifier = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,39}$")]
CAPABILITIES = ["reports_enabled", "hrbp_enabled", "inherit_hrbp_enabled", "private_enabled", "export_enabled"]
REASONS = {"owner": "本人", "report_grant": "管理汇报线", "hrbp_grant": "直接 HRBP 服务", "inherited_hrbp_grant": "下属 HRBP 服务继承"}
RELATIONS = ["view_basic", "view_private", "can_export", *REASONS]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Person(Record):
    person_id: Identifier
    name: Annotated[str, Field(min_length=1, max_length=60)]
    department: Annotated[str, Field(min_length=1, max_length=60)]
    head_person_id: Identifier | None
    dept_hrbp_id: Identifier | None
    education: Annotated[str, Field(max_length=20)]
    school: Annotated[str, Field(max_length=60)]
    job: Identifier
    active: StrictBool
    salary: Annotated[int, Field(strict=True, ge=0, le=1000000)]


class Role(Record):
    label: Annotated[str, Field(min_length=1, max_length=40)]
    reports_enabled: StrictBool
    hrbp_enabled: StrictBool
    inherit_hrbp_enabled: StrictBool
    private_enabled: StrictBool
    export_enabled: StrictBool


class Configuration(Record):
    people: Annotated[list[Person], Field(min_length=1, max_length=50)]
    roles: dict[Identifier, Role]
    job_roles: dict[Identifier, Identifier]

    @model_validator(mode="after")
    def validate_facts(self):
        # 在写入引擎前拒绝孤儿和管理环，这是数据质量防线，不是另写一套权限判断。
        people = {p.person_id: p for p in self.people}
        if len(people) != len(self.people):
            raise ValueError("person_id 不能重复")
        if len(self.roles) > 20 or len(self.job_roles) > 30:
            raise ValueError("演示最多支持 20 个角色、30 个岗位映射")
        for role in self.job_roles.values():
            if role not in self.roles:
                raise ValueError(f"岗位映射引用了不存在的角色：{role}")
        for person in self.people:
            if person.job not in self.job_roles:
                raise ValueError(f"岗位没有角色映射：{person.job}")
            for reference in [person.head_person_id, person.dept_hrbp_id]:
                if reference and reference not in people:
                    raise ValueError(f"{person.person_id} 引用了不存在的人员：{reference}")
            # Data-quality validation only. This never determines anyone's permissions.
            visited = {person.person_id}
            current = person.head_person_id
            while current:
                if current in visited:
                    raise ValueError(f"管理关系存在环：{person.person_id}")
                visited.add(current)
                current = people[current].head_person_id
        return self


class EngineError(RuntimeError):
    pass


class ConflictError(RuntimeError):
    pass


class FGA:
    def __init__(self, url="http://127.0.0.1:8090"):
        self.url = url.rstrip("/")

    def request(self, method, path, payload=None):
        try:
            response = httpx.request(method, self.url + path, json=payload, timeout=8, trust_env=False)
        except httpx.HTTPError as exc:
            raise EngineError("OpenFGA 不可用，本次查询已停止，没有回退到自写权限规则。") from exc
        if not response.is_success:
            raise EngineError(f"OpenFGA HTTP {response.status_code}: {response.text[:1200]}")
        return response.json() if response.content else {}

    def batch(self, state, user, people, relations=RELATIONS):
        # 实验规模最多 50 人：分批 Check 各人/各动作，任何缺失或错误都拒绝整次结果。
        # 这里没有本地权限兜底；引擎不可用不能假装已授权并继续返回名单。
        checks = [{"tuple_key": {"user": f"user:{user}", "relation": relation, "object": f"employee:{person['person_id']}"}}
                  for person in people for relation in relations]
        for index, check in enumerate(checks):
            check["correlation_id"] = f"check{index}"
        decisions, trace = {}, []
        for offset in range(0, len(checks), 50):
            chunk = checks[offset:offset + 50]
            payload = {"authorization_model_id": state["model_id"], "consistency": "HIGHER_CONSISTENCY", "checks": chunk}
            path = f"/stores/{state['store_id']}/batch-check"
            start = time.perf_counter()
            response = self.request("POST", path, payload)
            results = response.get("result", {})
            for check in chunk:
                key = check["correlation_id"]
                item = results.get(key, {})
                if "error" in item or type(item.get("allowed")) is not bool:
                    raise EngineError(f"OpenFGA 未给出完整判断：{key}，已拒绝返回部分名单")
                target = check["tuple_key"]["object"].split(":", 1)[1]
                decisions[f"{target}:{check['tuple_key']['relation']}"] = item["allowed"]
            trace.append({"method": "POST", "path": path, "input": payload, "output": response,
                          "elapsed_ms": round((time.perf_counter() - start) * 1000, 2)})
        return decisions, trace


def compile_model(source, binary=None):
    # 官方 CLI 将 DSL 转成引擎模型 JSON；额外检查实验接口依赖的关系名称仍然存在。
    if not source.strip() or len(source) > 20000:
        raise ValueError("模型为空或超过 20,000 字符")
    with tempfile.TemporaryDirectory(prefix="hr-fga-model-") as folder:
        path = Path(folder) / "model.fga"
        path.write_text(source)
        try:
            output = subprocess.run([str(binary or BIN / "fga"), "model", "transform", "--file", str(path), "--output-format", "json"],
                                    capture_output=True, text=True, timeout=10,
                                    env=dict(os.environ, GOMAXPROCS="2"))
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError("官方 fga CLI 不可用或模型解析超时，请检查运行环境") from exc
    if output.returncode:
        raise ValueError("OpenFGA 模型语法错误：" + (output.stderr or output.stdout)[:1500])
    model = json.loads(output.stdout)
    types = {entry["type"]: entry for entry in model.get("type_definitions", [])}
    required = {"employee": {*RELATIONS, "manager", "hrbp", "company"}, "company": {*CAPABILITIES, "active"}, "user": set()}
    for kind, relations in required.items():
        if kind not in types or not relations.issubset(types[kind].get("relations", {})):
            raise ValueError(f"模型必须保留演示接口所需的 {kind} 类型及关系：{sorted(relations)}")
    return model


def build_tuples(config):
    """Only direct facts and role switches, never recursive permission expansion."""
    tuples = []
    # 一条主管边只写一条 manager 事实；不把传递闭包展开成大量手工授权记录。
    # 岗位 → 角色能力开关由当前配置映射，active=false 的账号不会写入有效用户能力。
    for person in config["people"]:
        resource = "employee:" + person["person_id"]
        user = "user:" + person["person_id"]
        tuples.extend([{"user": user, "relation": "owner", "object": resource},
                       {"user": "company:demo", "relation": "company", "object": resource}])
        for field, relation in [("head_person_id", "manager"), ("dept_hrbp_id", "hrbp")]:
            if person[field]:
                tuples.append({"user": "employee:" + person[field], "relation": relation, "object": resource})
        if person["active"]:
            tuples.append({"user": user, "relation": "active", "object": "company:demo"})
            role = config["roles"][config["job_roles"][person["job"]]]
            for capability in CAPABILITIES:
                if role[capability]:
                    tuples.append({"user": user, "relation": capability, "object": "company:demo"})
    return tuples


class Lab:
    def __init__(self, directory=LOCAL, engine=None, cli=None):
        self.directory = Path(directory)
        self.engine = engine or FGA(os.environ.get("HR_FGA_URL", "http://127.0.0.1:8090"))
        self.cli = cli
        self.lock = threading.RLock()

    @staticmethod
    def defaults():
        return json.loads((ROOT / "fixtures.json").read_text()), (ROOT / "model.fga").read_text()

    def state(self):
        with self.lock:
            path = self.directory / "state.json"
            if not path.exists():
                config, model = self.defaults()
                return self.publish(config, model, 0, "初始化合成样本")
            return json.loads(path.read_text())

    def publish(self, config, source, expected_version, reason="配置发布"):
        # 小型实验采用每次发布新 store：写入并完整试算后才原子切换 state.json。
        # 版本比较避免多个窗口覆盖配置；失败删除新 store，保留上一版可用状态。
        config = Configuration.model_validate(config).model_dump()
        model = compile_model(source, self.cli)
        with self.lock:
            path = self.directory / "state.json"
            previous = json.loads(path.read_text()) if path.exists() else None
            if (previous["version"] if previous else 0) != expected_version:
                raise ConflictError("配置已被其他窗口更新，请刷新后重试。")
            store = self.engine.request("POST", "/stores", {"name": "hr-permission-demo"})["id"]
            try:
                prefix = f"/stores/{store}"
                model_id = self.engine.request("POST", prefix + "/authorization-models", model)["authorization_model_id"]
                tuples = build_tuples(config)
                for offset in range(0, len(tuples), 50):
                    self.engine.request("POST", prefix + "/write", {"authorization_model_id": model_id, "writes": {"tuple_keys": tuples[offset:offset + 50]}})
                state = {"version": expected_version + 1, "store_id": store, "model_id": model_id, "config": config,
                         "model_source": source, "model_json": model, "tuples": tuples, "reason": reason,
                         "published_at": datetime.now(UTC).isoformat()}
                # Confirm all combinations can be evaluated before activating the snapshot.
                for person in config["people"]:
                    self.engine.batch(state, person["person_id"], config["people"], ["view_basic", "view_private", "can_export"])
                self.directory.mkdir(parents=True, exist_ok=True)
                history = self.directory / "revisions"
                history.mkdir(exist_ok=True)
                (history / f"{state['version']:04}.json").write_text(json.dumps(state, ensure_ascii=False, indent=2))
                temporary = path.with_suffix(".tmp")
                temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2))
                temporary.replace(path)
                return state
            except Exception:
                try:
                    self.engine.request("DELETE", f"/stores/{store}")
                except EngineError:
                    pass
                raise

    def query(self, user, department="", export=False):
        # 先按引擎 view_basic 筛人，再加部门条件；薪资和导出还需各自的动作授权。
        # 用户选择仅用于本机身份切换演示，正式应用必须来自可信登录会话。
        state = self.state()
        people = state["config"]["people"]
        decisions, trace = self.engine.batch(state, user, people)
        visible = [p for p in people if decisions[f"{p['person_id']}:view_basic"]]
        matching = [p for p in visible if not department or p["department"] == department]
        if export and any(not decisions[f"{p['person_id']}:can_export"] for p in matching):
            raise PermissionError("OpenFGA 拒绝导出：当前匹配记录没有全部获得导出权限。")
        rows = []
        for person in matching:
            key = person["person_id"]
            row = {field: person[field] for field in ["person_id", "name", "department", "education", "school", "active"]}
            row["salary"] = person["salary"] if decisions[f"{key}:view_private"] else None
            row["sources"] = [label for relation, label in REASONS.items() if decisions[f"{key}:{relation}"]]
            rows.append(row)
        return {"version": state["version"], "store_id": state["store_id"], "model_id": state["model_id"],
                "user": user, "department": department, "visible_total": len(visible), "matched_total": len(rows),
                "rows": rows, "can_export": bool(rows) and all(decisions[f"{p['person_id']}:can_export"] for p in matching),
                "trace": trace}

    def explain(self, user, target, relation):
        if relation not in RELATIONS:
            raise ValueError("未知权限动作")
        state = self.state()
        person = next((p for p in state["config"]["people"] if p["person_id"] == target), None)
        if not person:
            raise ValueError("目标员工不存在")
        values, trace = self.engine.batch(state, user, [person])
        return {"allowed": values[f"{target}:{relation}"], "decisions": values, "trace": trace,
                "model_id": state["model_id"], "version": state["version"]}

    def history(self):
        folder = self.directory / "revisions"
        return [{key: state[key] for key in ["version", "reason", "published_at", "model_id"]}
                for path in sorted(folder.glob("*.json"), reverse=True)[:20]
                for state in [json.loads(path.read_text())]]

    def rollback(self, version, expected_version):
        # 回滚是“用旧内容发布新版本”，不是把版本号倒退，便于审计谁在何时恢复了什么。
        path = self.directory / "revisions" / f"{version:04}.json"
        if not path.exists():
            raise ValueError("版本不存在")
        old = json.loads(path.read_text())
        return self.publish(deepcopy(old["config"]), old["model_source"], expected_version, f"恢复版本 {version} 的配置")
