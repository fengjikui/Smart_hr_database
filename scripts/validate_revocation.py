"""真实修改 当前 权限并核验 API 撤权；所有修改在 finally 中恢复。

运行前先完成一般回归；本脚本必须串行运行，不能与演示或其他验证并发。
只修改本次集成自己的角色/数据/RLS，临时会话与历史放临时目录。
"""

import json
import os
import subprocess
import sys
import tempfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from backend.hr import (  # noqa: E402
    config,  # noqa: E402
    service,
    store,
)
from backend.hr.api import _limits, app  # noqa: E402
from backend.hr.schema import Plan  # noqa: E402


def remote(action, state=None):
    env = dict(os.environ, DOCKER_HOST=os.getenv("HR_DOCKER_HOST",
               f"unix://{Path.home()}/.colima/hr-superset/docker.sock"))
    # 唯一容器来自本项目compose；不改全局Docker context。
    lookup = subprocess.run(["docker", "ps", "--filter", "label=com.docker.compose.project=hr-superset-lab",
                             "--filter", "label=com.docker.compose.service=superset", "--format", "{{.ID}}"],
                            env=env, check=True, capture_output=True, text=True)
    container = lookup.stdout.strip()
    if not container or "\n" in container:
        raise RuntimeError("未找到唯一的Superset实验容器")
    command = ["docker", "exec", container, "python", "/lab/probe.py", action]
    if state is not None:
        command.append(json.dumps(state))
    result = subprocess.run(command, env=env, text=True, capture_output=True, timeout=40, check=True)
    return json.loads(result.stdout.strip().splitlines()[-1])


def main():
    checks = []

    def record(name, condition):
        assert condition, name
        checks.append({"name": name, "passed": True})

    state = remote("capture")
    recovery = ROOT / "integrations/superset/.local/application/probe-recovery.json"
    recovery.write_text(json.dumps(state, ensure_ascii=False, indent=2))
    try:
        with tempfile.TemporaryDirectory(prefix="hr-superset-revoke-") as temp, patch.dict(
                os.environ, {"HR_QUERY_BACKEND": "superset"}), patch.object(
                config, "APP_DB", Path(temp) / "app.sqlite"), closing(TestClient(app)) as client:
            # 仅初始化本次验证的临时会话和历史数据库。
            store.ensure()
            _limits.clear()

            def login(persona):
                record("切换身份 " + persona, client.post("/api/session", json={"persona_id": persona}).status_code == 200)
                boot = client.get("/api/bootstrap")
                boot.raise_for_status()
                return {"X-CSRF-Token": boot.json()["principal"]["csrf"]}

            headers = login("manager")
            principal = dict(store.PERSONAS[2])
            saved = service.save_run(principal, "撤权测试专用", service.run_query(principal, Plan()))
            remote("manager_self")
            response = client.post("/api/query", headers=headers, json={})
            record("PG业务策略关闭管理线后人数变1", response.status_code == 200 and response.json()["totals"]["count"] == 1)
            record("旧历史随PG策略失效", client.get("/api/history/" + saved["id"]).status_code == 404)
            record("关系页随策略收缩", len(client.get("/api/relations").json()["rows"]) == 1)
            verify = client.post("/api/verify", headers=headers, json={}).json()
            record("核验不会泄露旧人群", verify["passed"] and verify["totals"]["count"] == 1)
            remote("restore", state)

            remote("narrow_rls")
            response = client.post("/api/query", headers=headers, json={})
            record("直接改Superset RLS使Agent只返回冯基魁", response.status_code == 200 and response.json()["totals"]["count"] == 1)
            record("RLS变化后历史失效", client.get("/api/history/" + saved["id"]).status_code == 404)
            remote("restore", state)

            # HR 的完整快照来自合同人员视图，而普通统计走公共视图；过去只检查
            # 合同快照时，公共出口单独收窄无法使旧历史失效。这里直接回归该缺口。
            headers = login("hr_lead")
            principal = dict(store.PERSONAS[0])
            hr_saved = service.save_run(principal, "公共出口历史撤权测试", service.run_query(principal, Plan()))
            event_plan = Plan(population="all", date_field="employment_events", start_date="2026-01-01",
                              end_date=store.AS_OF, metrics=["hires", "departures"])
            event_saved = service.save_run(principal, "事件出口历史撤权测试",
                                           service.run_query(principal, event_plan))
            remote("narrow_rls")
            response = client.post("/api/query", headers=headers, json={})
            record("HR合同快照未变时公共RLS仍限制新查询", response.status_code == 200
                   and response.json()["totals"]["count"] == 1)
            record("HR公共RLS变化后旧公共历史失效", client.get("/api/history/" + hr_saved["id"]).status_code == 404)
            record("HR公共RLS变化后历史列表移除旧记录", hr_saved["id"] not in {
                row["id"] for row in client.get("/api/history").json()})
            remote("restore", state)

            remote("revoke_events")
            record("仅撤销事件数据集时旧事件历史不能旁路",
                   client.get("/api/history/" + event_saved["id"]).status_code == 403)
            record("仅撤销事件数据集时历史列表关闭", client.get("/api/history").status_code == 403)
            record("仅撤销事件数据集时新事件查询拒绝", client.post(
                "/api/query", headers=headers, json=event_plan.model_dump()).status_code == 403)
            remote("restore", state)

            remote("narrow_events")
            response = client.post("/api/query", headers=headers, json=event_plan.model_dump())
            record("仅收窄事件RLS时新事件查询返回零事件", response.status_code == 200
                   and response.json()["totals"] == {"hires": 0, "departures": 0})
            record("仅收窄事件RLS时旧事件历史失效",
                   client.get("/api/history/" + event_saved["id"]).status_code == 404)
            record("仅收窄事件RLS时旧公共历史也失效",
                   client.get("/api/history/" + hr_saved["id"]).status_code == 404)
            remote("restore", state)

            headers = login("employee")
            for action, status in [("revoke_public", 403), ("unmap_employee", 403), ("cycle", 409), ("orphan", 409)]:
                remote(action)
                record(action + " 查询拒绝", client.post("/api/query", headers=headers, json={}).status_code == status)
                record(action + " 历史不能旁路", client.get("/api/history").status_code == status)
                remote("restore", state)
            record("撤回故障后恢复本人一人", client.post("/api/query", headers=headers, json={}).json()["totals"]["count"] == 1)
    finally:
        remote("restore", state)
    record("角色数据RLS精确恢复", remote("capture") == state)
    result = {"tested_at": datetime.now(UTC).isoformat(), "passed": True, "check_count": len(checks),
              "checks": checks, "restored": True, "scope": "真实Superset、PostgreSQL与当前 HTTP API；无模型调用"}
    target = ROOT / "reports/superset-revocation.json"
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
