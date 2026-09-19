"""真实 PostgreSQL / Superset / V2 API 集成回归，不调用模型、不修改权限。

运行前先完成 integrations/superset/v2 的初始化，再在项目根目录执行：
    uv run python scripts/validate_v2_superset.py

验证分为两层：先在原 SQLite 合成数据上计算独立 oracle，再彻底禁止在线
路径读取人员 SQLite。应用的会话和历史放入临时目录，退出后自动删除。
本脚本不重置课堂规则，不创建 Superset 对象，也不改变 PostgreSQL 数据。
"""

import argparse
import csv
import hashlib
import io
import json
import os
import sys
from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import HTTPException
from fastapi.testclient import TestClient

# 直接运行 scripts/ 下的文件时，也能找到项目里的 backend 包。
PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from backend.hr import config  # noqa: E402
from backend.hr.api import _limits, app  # noqa: E402
from backend.hr.v2 import api, auth, graph, query, reference, store  # noqa: E402
from backend.hr.v2 import superset_source as source  # noqa: E402
from backend.hr.v2.schema import FIELDS, Plan  # noqa: E402


def digest(value):
    """报告只保存合成结果的摘要，避免把完整人员明细重复写进报告。"""
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


class Checks:
    def __init__(self):
        self.items = []

    def equal(self, name, actual, expected, *, evidence=None):
        passed = actual == expected
        entry = {"name": name, "passed": passed}
        if evidence is not None:
            entry["evidence"] = evidence
        if not passed:
            entry["actual_hash"] = digest(actual)
            entry["expected_hash"] = digest(expected)
            # 仅在失败时保留有限、无凭据的业务结果，方便定位日期/舍入差异。
            entry["actual_sample"] = actual[:3] if isinstance(actual, list) else actual
            entry["expected_sample"] = expected[:3] if isinstance(expected, list) else expected
        self.items.append(entry)
        print(("PASS " if passed else "FAIL ") + name, flush=True)
        if not passed:
            raise AssertionError(name)

    def denied(self, name, operation, status_codes=(403,)):
        try:
            operation()
        except HTTPException as exc:
            self.equal(name, exc.status_code in status_codes, True,
                       evidence={"status_code": exc.status_code})
        else:
            self.equal(name, "查询被接受", "查询被拒绝")


def persona(key):
    # 每次返回新字典，不在不同请求之间共用适配器的授权快照缓存。
    return dict(next(p for p in store.PERSONAS if p["id"] == key))


def plan_persona(case):
    return persona({"HR-01": "manager", "HR-02": "hrbp"}.get(case, "hr_lead"))


def offline_oracle():
    """明确读取原演示数据，仅在启用 Superset 在线路径之前执行一次。"""
    rows = store.people()
    policy = store.policy()
    plans = json.loads((PROJECT / "evaluation/demo-v2-plans.json").read_text())["plans"]

    def calculate(p, plan):
        # 此处主动传递 source 和独立 BFS 计算的 scope，不能调用运行时 auth.grants。
        scope = reference.independent_scope(p, plan, rows, policy)
        return reference.calculate(p, plan, source=rows, scope=scope)

    identities = {}
    for p in store.PERSONAS:
        all_plan = Plan(population="all")
        ids, _ = reference.independent_scope(p, all_plan, rows, policy)
        identities[p["id"]] = {
            "ids": sorted(ids),
            "active_count": calculate(p, Plan())["totals"]["count"],
        }
    cases = {case: calculate(plan_persona(case), Plan.model_validate(raw))
             for case, raw in plans.items()}
    return {"rows": rows, "policy": policy, "plans": plans, "cases": cases,
            "identities": identities, "fingerprint": digest(rows)}


def upstream_payload(dataset_key, columns):
    return {
        "datasource": {"id": source.manifest()["datasets"][dataset_key]["id"], "type": "table"},
        "force": True, "result_format": "json", "result_type": "full",
        "queries": [source.raw_query(columns)],
    }


def no_upstream_data(response):
    """错误结果不能当作空业务结果；这里仅用于确认越权请求没有返回明细。"""
    if response.status_code >= 400:
        return True
    payload = response.json()
    if payload.get("errors"):
        return True
    return all(not item.get("data") for item in payload.get("result", []))


@contextmanager
def unmapped_client():
    """真实反例账号已具备数据集访问权，但故意没有员工身份映射。"""
    username = source.manifest()["unmapped"]["username"]
    credentials = source.read_local("credentials.json")
    url = os.getenv("HR_V2_SUPERSET_URL", "http://127.0.0.1:8088").rstrip("/")
    with httpx.Client(base_url=url, timeout=30, trust_env=False) as client:
        token = source.checked_response(client.post("/api/v1/security/login", json={
            "username": username, "password": credentials[username],
            "provider": "db", "refresh": False,
        }))["access_token"]
        client.headers["Authorization"] = "Bearer " + token
        client.headers["X-CSRFToken"] = source.checked_response(
            client.get("/api/v1/security/csrf_token/"))["result"]
        yield client


def verify_direct(checks, oracle):
    checks.equal("PostgreSQL 导入行数", source.manifest()["row_count"], len(oracle["rows"]))
    checks.equal("导入数据与原 SQLite 指纹一致", source.manifest()["data_fingerprint"], oracle["fingerprint"])
    for key, expected in oracle["identities"].items():
        p = persona(key)
        snapshot = source.snapshot(p, refresh=True)
        checks.equal(key + " 授权人员 ID 集合", sorted(snapshot["grant"]["ids"]), expected["ids"],
                     evidence={"candidate_count": len(expected["ids"])})
        checks.equal(key + " 字段组与独立配置一致", sorted(snapshot["fields"]),
                     sorted(f for f, info in FIELDS.items()
                            if info[1] in oracle["policy"]["roles"][key]["field_groups"]))
        actual = query.execute(p, Plan())
        checks.equal(key + " 真实 PostgreSQL 在职人数", actual["totals"]["count"],
                     expected["active_count"], evidence={"active_count": expected["active_count"]})
        checks.equal(key + " 执行 SQL 有用户隔离条件", "_viewer_id" in actual["sql"], True)

    # 逐题比较全量结果而非分页结果，保证不是仅取前 50/100 行进行统计。
    for case, raw in oracle["plans"].items():
        actual = query.execute(plan_persona(case), Plan.model_validate(raw))
        expected = oracle["cases"][case]
        checks.equal(case + " 全量明细/分组与独立 Python 一致", actual["_all_rows"], expected["rows"],
                     evidence={"rows": len(expected["rows"]), "hash": digest(expected["rows"])})
        checks.equal(case + " 合计与独立 Python 一致", actual["totals"], expected["totals"],
                     evidence={"totals": expected["totals"]})

    employee = persona("employee")
    other = query.execute(employee, Plan(kind="people", columns=["person_id"],
                                        filters=[{"field": "person_id", "values": ["P0002"]}]))
    checks.equal("员工业务筛选不能扩大到他人", other["_all_rows"], [])
    for key, plan in {
        "明细列": Plan(kind="people", columns=["contract_end_date"]),
        "筛选列": Plan(filters=[{"field": "contract_end_date", "values": [store.AS_OF]}]),
        "排序列": Plan(kind="people", order_by=[{"field": "contract_end_date", "direction": "asc"}]),
    }.items():
        checks.denied("员工合同" + key + "被拒绝", lambda plan=plan: query.execute(persona("employee"), plan))

    # 不经过 Agent 校验，直接攻击上游接口，证明限制也在 Superset/PG 层生效。
    with source.session(persona("employee")) as client:
        hidden = client.post("/api/v1/chart/data", json=upstream_payload(
            "people_public", ["person_id", "contract_end_date"]))
        checks.equal("上游公共数据集不能指定隐藏合同列", no_upstream_data(hidden), True,
                     evidence={"http_status": hidden.status_code})
        private = client.post("/api/v1/chart/data", json=upstream_payload(
            "people_contract", ["person_id", "contract_end_date"]))
        checks.equal("上游合同数据集拒绝员工", private.status_code in (401, 403), True,
                     evidence={"http_status": private.status_code})
        database_id = source.manifest()["datasets"]["people_public"]["database_id"]
        sql_lab = client.post("/api/v1/sqllab/execute/", json={
            "database_id": database_id, "schema": "v2_api", "runAsync": False,
            "sql": "SELECT person_id FROM v2_api.people_public", "queryLimit": 10,
        })
        checks.equal("员工没有 SQL Lab 执行权", sql_lab.status_code in (401, 403), True,
                     evidence={"http_status": sql_lab.status_code})

    with unmapped_client() as client:
        for dataset, columns in [("context", ["person_id"]), ("people_public", ["person_id"])]:
            payload = source.checked_response(client.post("/api/v1/chart/data", json=upstream_payload(dataset, columns)))
            result = payload["result"][0]
            checks.equal("未映射账号 " + dataset + " 查询无上游错误", bool(result.get("error")), False)
            checks.equal("未映射账号 " + dataset + " 返回空集", result["data"], [])


def verify_http(checks, oracle):
    # 不启用 TestClient lifespan，避免旧版 V1 启动过程写入原数据库。
    # 只有本机模型健康状态与计划器被替换；全部认证、Superset、PG 查询均真实执行。
    client = TestClient(app, raise_server_exceptions=True)
    _limits.clear()
    try:
        checks.equal("未登录 bootstrap 被拒绝", client.get("/api/v2/bootstrap").status_code, 401)

        def login(key):
            checks.equal(key + " HTTP 演示登录", client.post("/api/v2/session", json={"persona_id": key}).status_code, 200)
            response = client.get("/api/v2/bootstrap")
            checks.equal(key + " HTTP bootstrap 成功", response.status_code, 200)
            boot = response.json()
            checks.equal(key + " HTTP bootstrap 显示 Superset", boot["query_backend"], "superset")
            checks.equal(key + " HTTP bootstrap 在职人数", boot["principal"]["count"],
                         oracle["identities"][key]["active_count"])
            return {"X-CSRF-Token": boot["principal"]["csrf"]}, boot

        # 覆盖五个真实会话身份，确保浏览器切换身份后使用对应 Superset 业务账号。
        for key in oracle["identities"]:
            headers, boot = login(key)
            relations = client.get("/api/v2/relations")
            checks.equal(key + " HTTP 关系查询成功", relations.status_code, 200)
            checks.equal(key + " HTTP 关系名单", sorted(r["person_id"] for r in relations.json()["rows"]),
                         oracle["identities"][key]["ids"])
            response = client.post("/api/v2/query", headers=headers, json={})
            checks.equal(key + " HTTP 聚合查询成功", response.status_code, 200)
            checks.equal(key + " HTTP 聚合人数", response.json()["totals"]["count"],
                         oracle["identities"][key]["active_count"])

        headers, _ = login("hr_lead")
        plan = {"kind": "people", "columns": ["employee_no", "name"], "page_size": 1}
        checks.equal("缺少 CSRF 被拒绝", client.post("/api/v2/query", json=plan).status_code, 403)
        checks.equal("前端自由 SQL 被拒绝", client.post("/api/v2/query", headers=headers,
                                                       json={"sql": "SELECT * FROM people"}).status_code, 422)
        checked = client.post("/api/v2/verify", headers=headers, json=plan)
        checks.equal("HTTP 核验成功", checked.status_code, 200)
        checks.equal("HTTP 核验全量而非当前页", checked.json()["compared_rows"],
                     oracle["identities"]["hr_lead"]["active_count"])
        checks.equal("HTTP 核验计算一致", checked.json()["passed"], True)

        aggregate = Plan(group_by=["dept_cn_name"])
        grouped = client.post("/api/v2/query", headers=headers, json=aggregate.model_dump())
        checks.equal("HTTP 下钻前聚合成功", grouped.status_code, 200)
        first = grouped.json()["rows"][0]
        drilled = client.post("/api/v2/drill", headers=headers, json={
            "plan": aggregate.model_dump(), "group": {"dept_cn_name": first["dept_cn_name"]}, "metric": "count",
        })
        checks.equal("HTTP 下钻成功", drilled.status_code, 200)
        checks.equal("HTTP 下钻人数等于授权组人数", drilled.json()["total_rows"], first["count"])
        exported = client.post("/api/v2/export", headers=headers, json=plan)
        checks.equal("HR HTTP 导出成功", exported.status_code, 200)
        export_rows = list(csv.DictReader(io.StringIO(exported.text.lstrip("\ufeff"))))
        checks.equal("HTTP 导出全量而非当前页", len(export_rows), oracle["identities"]["hr_lead"]["active_count"])
        checks.equal("HTTP 导出保留前导零工号", "'00031266" in exported.text, True)

        # 固定计划器输出，仅验证真实 LangGraph 授权→执行→存历史链路。
        # 这项不能被表述为真实模型理解能力/LM Studio 推理通过。
        async def deterministic_planner(_messages):
            candidate = Plan().model_dump()
            return candidate, {"candidate": candidate, "test_double": "固定计划器；无模型推理"}

        with patch.object(graph, "call_model", deterministic_planner):
            chatted = client.post("/api/v2/chat", headers=headers, json={"question": "当前在职人数是多少？"})
        checks.equal("LangGraph 真实执行链路成功（计划器替身）", chatted.status_code, 200)
        saved = chatted.json()
        checks.equal("LangGraph 聚合结果正确", saved["totals"]["count"], oracle["identities"]["hr_lead"]["active_count"])
        checks.equal("LangGraph 留存节点输入输出", bool(saved["trace"]), True)
        history_url = "/api/v2/history/" + saved["id"]
        restored = client.get(history_url)
        checks.equal("本人可恢复调试历史", restored.status_code, 200)
        checks.equal("历史恢复保留结果", restored.json()["totals"], saved["totals"])
        checks.equal("本人历史列表包含本次查询", saved["id"] in [r["id"] for r in client.get("/api/v2/history").json()], True)
        old_token = client.cookies.get(auth.COOKIE)

        employee_headers, employee_boot = login("employee")
        checks.equal("员工目录不披露合同列", "contract_end_date" in {f["key"] for f in employee_boot["catalog"]["fields"]}, False)
        checks.equal("跨用户历史和调试内容被拒绝", client.get(history_url).status_code, 404)
        checks.equal("跨用户历史列表不含他人记录", saved["id"] in [r["id"] for r in client.get("/api/v2/history").json()], False)
        checks.equal("员工 HTTP 导出被拒绝", client.post("/api/v2/export", headers=employee_headers, json=plan).status_code, 403)
        checks.equal("员工 HTTP 合同列被拒绝", client.post("/api/v2/query", headers=employee_headers,
            json={"kind": "people", "columns": ["contract_end_date"]}).status_code, 403)
        stale = TestClient(app)
        try:
            stale.cookies.set(auth.COOKIE, old_token)
            checks.equal("身份切换撤销旧会话", stale.get("/api/v2/bootstrap").status_code, 401)
        finally:
            stale.close()
    finally:
        client.close()


def verify_failure(checks):
    # 明确标为故障注入：不停止用户正在使用的 Superset，也不修改真实服务器。
    # SQLite 读取在外层被拦截，若适配器故障时尝试回退，测试会直接失败。
    with patch.object(source.httpx.Client, "post", side_effect=httpx.ConnectError("integration failure injection")):
        checks.denied("上游连接故障关闭且无 SQLite 回退（故障注入）",
                      lambda: query.execute(persona("employee"), Plan()), status_codes=(503,))


def run(report_path):
    checks = Checks()
    report = {"passed": False, "tested_at": datetime.now(UTC).isoformat(),
              "backend": "Superset Chart Data API + PostgreSQL", "checks": checks.items,
              "model_inference": False, "planner": "固定计划器只验证 LangGraph 集成链路",
              "mutation_tests": False,
              "limitations": ["未评估真实语言模型理解率、生产并发或 SSO。",
                              "本脚本不修改服务器策略；撤权/关系变更需另行受控验证。"],
              "isolation": "临时应用会话与历史；在线路径禁止读人员 SQLite；不重置课堂数据或 RLS。"}
    try:
        oracle = offline_oracle()
        report["source_row_count"] = len(oracle["rows"])
        report["source_fingerprint"] = oracle["fingerprint"]
        report["case_count"] = len(oracle["plans"])
        real_connection = store.connection

        @contextmanager
        def application_only_connection(kind="app", readonly=False):
            if kind == "people":
                raise AssertionError("Superset 在线路径试图读取人员 SQLite")
            with real_connection(kind, readonly) as db:
                yield db

        with TemporaryDirectory(prefix="hr-v2-superset-validation-") as directory, ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {"HR_V2_QUERY_BACKEND": "superset"}))
            stack.enter_context(patch.object(config, "APP_DB", Path(directory) / "app.sqlite"))
            # 只初始化临时 app 状态；临时人员文件仅满足现有 ensure 的存在性检查。
            # 随后所有在线读取都被显式禁止，不能误把重新生成数据当作真正数据源。
            store.ensure()
            stack.enter_context(patch.object(store, "people", side_effect=AssertionError("禁止读取本地全量人员")))
            stack.enter_context(patch.object(store, "connection", application_only_connection))
            stack.enter_context(patch.object(api, "model_status", AsyncMock(return_value={
                "available": False, "test_double": True, "message": "集成回归未调用模型",
            })))
            verify_direct(checks, oracle)
            verify_http(checks, oracle)
            verify_failure(checks)
        report["passed"] = True
    except Exception as exc:
        # 不序列化 HTTP 请求对象或异常上下文，避免凭据混入报告。
        report["error"] = {"type": type(exc).__name__, "message": str(exc)[:500]}
        raise
    finally:
        report["check_count"] = len(checks.items)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"passed": report["passed"], "check_count": len(checks.items),
                          "report": str(report_path)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=PROJECT / "reports/v2-superset-integration.json")
    run(parser.parse_args().report)
