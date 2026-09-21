"""真实 OpenFGA + PostgreSQL 集成验收；不调用本地模型，不修改源数据。

业务计算使用独立 Python 参考值；在线路径禁止访问 SQLite 人员。会话和
历史保存在临时目录。本脚本适用于原始 300 人种子，改过策略后需先还原。
"""

import json
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import psycopg
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.hr import auth, config, graph, openfga_source, query, reference, store
from backend.hr.api import _limits, app
from backend.hr.schema import Plan


def main():
    checks = []

    def equal(name, actual, expected):
        assert actual == expected, f"{name}: {actual!r} != {expected!r}"
        checks.append({"name": name, "passed": True})
        print("PASS " + name, flush=True)

    def denied(name, fn, codes=(403,)):
        try:
            fn()
        except HTTPException as exc:
            equal(name, exc.status_code in codes, True)
        else:
            raise AssertionError(name + " 未拒绝")

    def persona(key):
        return dict(next(p for p in store.PERSONAS if p["id"] == key))

    rows, policy = store.generate_rows(), store.default_policy()
    plans = json.loads((config.PROJECT / "evaluation/plans.json").read_text())["plans"]
    with (
        tempfile.TemporaryDirectory(prefix="hr-fga-test-") as temp,
        patch.dict(os.environ, {"HR_QUERY_BACKEND": "openfga"}),
        patch.object(config, "APP_DB", Path(temp) / "sessions.sqlite"),
    ):
        store.ensure()
        with patch.object(store, "people", side_effect=AssertionError("在线不许读取 SQLite 人员")):
            for key in [p["id"] for p in store.PERSONAS]:
                p = persona(key)
                snap = openfga_source.snapshot(p)
                ids, _ = reference.independent_scope(p, Plan(), rows, policy)
                equal(key + " 授权名单", snap["grant"]["ids"], sorted(ids))
                actual = query.execute(p, Plan())
                expected = reference.calculate(
                    p, Plan(), source=rows, scope=reference.independent_scope(p, Plan(), rows, policy)
                )
                equal(key + " 在职人数", actual["totals"], expected["totals"])
            for case, raw in plans.items():
                p = persona({"HR-01": "manager", "HR-02": "hrbp"}.get(case, "hr_lead"))
                plan = Plan.model_validate(raw)
                expected = reference.calculate(
                    p, plan, source=rows, scope=reference.independent_scope(p, plan, rows, policy)
                )
                actual = query.execute(p, plan)
                equal(case + " 分组/明细", actual["_all_rows"], expected["rows"])
                equal(case + " 合计", actual["totals"], expected["totals"])
            for key in ("manager", "employee"):
                for title, plan in [
                    ("输出", Plan(kind="people", columns=["contract_end_date"])),
                    ("筛选", Plan(filters=[{"field": "contract_end_date", "values": [store.AS_OF]}])),
                    ("排序", Plan(kind="people", order_by=[{"field": "contract_end_date"}])),
                ]:
                    denied(key + " 合同" + title, lambda p=plan, k=key: query.execute(persona(k), p))
            denied(
                "未知映射",
                lambda: openfga_source.snapshot({"id": "unknown", "person_id": "P0005", "role": "employee"}),
            )
            with openfga_source.database() as conn:
                equal(
                    "无事务授权时出口默认空",
                    conn.execute("SELECT count(*) AS n FROM hr_api.people").fetchone()["n"],
                    0,
                )
            for table in ("hr_source.people", "hr_data.people"):
                try:
                    with psycopg.connect(**openfga_source.settings()["pg"]) as conn:
                        conn.execute("SELECT * FROM " + table)
                except psycopg.errors.InsufficientPrivilege:
                    equal("只读账号拒绝原表 " + table, True, True)
                else:
                    raise AssertionError("原表越权")
            snap = openfga_source.snapshot(persona("manager"))
            with openfga_source.database(snap) as conn:
                equal(
                    "视图合同字段遮蔽",
                    conn.execute("SELECT count(contract_end_date) AS n FROM hr_api.people").fetchone()["n"],
                    0,
                )
            _limits.clear()
            with TestClient(app) as client:
                client.post("/api/session", json={"persona_id": "manager"})
                boot = client.get("/api/bootstrap").json()
                equal("界面正确标识后端", boot["query_backend"], "openfga")
                csrf = {"x-csrf-token": boot["principal"]["csrf"]}
                response = client.post("/api/query", headers=csrf, json=Plan().model_dump())
                equal("HTTP 查询", response.status_code, 200)
                equal("HTTP 在职人数", response.json()["totals"]["count"], 169)
                response = client.post("/api/verify", headers=csrf, json=Plan().model_dump())
                equal("独立核验", response.json()["passed"], True)
                equal(
                    "禁止主管导出",
                    client.post("/api/export", headers=csrf, json=Plan().model_dump()).status_code,
                    403,
                )
                equal("禁止本地配置旁路", client.get("/api/policy").status_code, 409)
                # 真实 LangGraph，固定模型输出专门验证接线；不是声称模型理解通过。
                with patch.object(
                    graph,
                    "call_model",
                    new=AsyncMock(return_value=(Plan().model_dump(), {"test_double": True})),
                ):
                    first = client.post("/api/chat", headers=csrf, json={"question": "当前授权在职人数"})
                equal("LangGraph 查询", first.status_code, 200)
                first = first.json()
                equal(
                    "节点记录包含 FGA 决策证据",
                    any("OpenFGA BatchCheck" in json.dumps(t) for t in first["trace"]),
                    True,
                )
                rid = first["id"]
                equal("本人历史可读", client.get("/api/history/" + rid).status_code, 200)
                with patch.object(
                    graph,
                    "call_model",
                    new=AsyncMock(return_value=(Plan(scope="direct").model_dump(), {"test_double": True})),
                ):
                    second = client.post(
                        "/api/chat", headers=csrf, json={"question": "那直属下属呢", "previous_id": rid}
                    )
                equal("多轮追问", second.status_code, 200)
                client.post("/api/session", json={"persona_id": "employee"})
                equal("跨身份历史拒绝", client.get("/api/history/" + rid).status_code, 404)
            # 只在事务中模拟待同步版本，然后 rollback，不改变原课堂配置。
            original_publication = openfga_source.publication()
            with patch.object(openfga_source, "publication", side_effect=HTTPException(409, "待同步")):
                denied("待同步拒绝", lambda: auth.fingerprint(persona("manager")), (409,))
            equal("发布 ID 可审计", bool(original_publication["model_id"]), True)
            with patch.object(
                openfga_source,
                "settings",
                return_value={**openfga_source.settings(), "fga_url": "http://127.0.0.1:1"},
            ):
                denied("FGA 断连不回退", lambda: auth.fingerprint(persona("manager")), (503,))
    report = {
        "passed": True,
        "checks": checks,
        "case_count": len(plans),
        "finished_at": time.time(),
        "scope": "真实 FGA/PG，LangGraph 模型输出为桩；未验证真实模型理解",
    }
    target = config.PROJECT / "reports/openfga-integration.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"完成 {len(checks)} 项检查：{target}")


if __name__ == "__main__":
    main()
