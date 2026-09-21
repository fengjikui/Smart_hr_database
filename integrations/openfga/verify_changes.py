"""动态变更/撤权的真实集成实验，仅修改独立 OpenFGA 演示库。

执行前保存源表快照到私有 recovery 文件；正常退出或异常均在 finally 恢复并
重新发布。不要与人工学习/后台 watch 同时执行；强制 kill 后按手册恢复。
"""

import copy
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from psycopg.types.json import Jsonb

from backend.hr import auth, config, openfga_source, query, service, store
from backend.hr.schema import Plan
from integrations.openfga import run


def restore(backup):
    with run.admin() as conn:
        conn.execute("DELETE FROM hr_source.identities")
        conn.execute("DELETE FROM hr_source.people")
        conn.execute("DELETE FROM hr_source.policy")
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO hr_source.people VALUES(%s,%s)",
                [(r["person_id"], Jsonb(r)) for r in backup["rows"]],
            )
            cur.executemany(
                "INSERT INTO hr_source.identities VALUES(%s,%s,%s)",
                [(r["persona"], r["person_id"], r["role_key"]) for r in backup["identities"]],
            )
            cur.execute("INSERT INTO hr_source.policy VALUES(true,%s)", (Jsonb(backup["policy"]),))
    run.sync()


def main():
    checks = []

    def equal(name, actual, expected):
        assert actual == expected, name
        checks.append({"name": name, "passed": True})
        print("PASS " + name, flush=True)

    def denied(name, operation, status):
        try:
            operation()
        except HTTPException as exc:
            equal(name, exc.status_code, status)
        else:
            raise AssertionError(name)

    def principal(key="manager"):
        return dict(next(p for p in store.PERSONAS if p["id"] == key))

    recovery = run.LOCAL / "change-recovery.json"
    if recovery.exists():
        raise RuntimeError("存在未恢复实验；先按手册检查 change-recovery.json")
    with run.admin() as conn:
        backup = {
            "rows": [
                r["record"] for r in conn.execute("SELECT record FROM hr_source.people ORDER BY person_id")
            ],
            "identities": conn.execute("SELECT * FROM hr_source.identities ORDER BY persona").fetchall(),
            "policy": conn.execute("SELECT config FROM hr_source.policy").fetchone()["config"],
        }
    run.private(recovery, json.dumps(backup, ensure_ascii=False, indent=2))
    try:
        with (
            tempfile.TemporaryDirectory(prefix="fga-change-") as temp,
            patch.dict(os.environ, {"HR_QUERY_BACKEND": "openfga"}),
            patch.object(config, "APP_DB", Path(temp) / "sessions.sqlite"),
        ):
            store.ensure()
            before = service.run_query(principal(), Plan())
            old = service.save_run(principal(), "全部授权在职人数", before)
            revoked = copy.deepcopy(backup["policy"])
            revoked["roles"]["manager"]["reports"] = False
            revoked["version"] += 1
            with run.admin() as conn:
                conn.execute("UPDATE hr_source.policy SET config=%s", (Jsonb(revoked),))
            denied("源变更提交后、同步前拒绝旧授权", lambda: auth.fingerprint(principal()), 409)
            run.sync()
            equal("撤管理线后只剩本人", query.execute(principal(), Plan())["totals"]["count"], 1)
            denied("旧历史失效", lambda: service.read_run(principal(), old["id"]), 404)
            restore(backup)
            equal("恢复管理线", query.execute(principal(), Plan())["totals"]["count"], 169)
            with run.admin() as conn:
                conn.execute(
                    "UPDATE hr_source.people SET record=jsonb_set(record,'{head_person_id}',%s) WHERE person_id='P0005'",
                    (Jsonb("P0010"),),
                )
            run.sync()
            equal("调岗后原主管失去员工", "P0005" in auth.grants(principal())["ids"], False)
            equal("调岗不改变本人访问", auth.grants(principal("employee"))["ids"], ["P0005"])
            restore(backup)
            hired = copy.deepcopy(next(r for r in backup["rows"] if r["person_id"] == "P0005"))
            hired.update(person_id="P0301", employee_no="SIM0301", name="同步新入职（模拟）")
            with run.admin() as conn:
                conn.execute("INSERT INTO hr_source.people VALUES(%s,%s)", ("P0301", Jsonb(hired)))
            run.sync()
            equal("新入职自动加入主管范围", "P0301" in auth.grants(principal())["ids"], True)
            equal(
                "新员工未开账号也有业务记录", len(openfga_source.publication()["metadata"]["identities"]), 5
            )
            with run.admin() as conn:
                conn.execute("DELETE FROM hr_source.identities WHERE persona='employee'")
            run.sync()
            denied("停用账号映射后拒绝", lambda: auth.fingerprint(principal("employee")), 403)
            # 模拟关系只写了一批就断连。新 store 不得替换当前 active。
            active_before_failure = openfga_source.publication()["id"]
            with run.admin() as conn:
                conn.execute("UPDATE hr_source.policy SET config=config")
            original_post = run.fga_client.post
            writes = 0

            def interrupted_post(client, path, body):
                nonlocal writes
                if path.endswith("/write"):
                    writes += 1
                    if writes == 2:
                        raise HTTPException(503, "模拟关系同步中途断连")
                return original_post(client, path, body)

            with patch.object(run.fga_client, "post", interrupted_post):
                denied("关系写入中断导致发布失败", run.sync, 503)
            with run.admin() as conn:
                equal(
                    "部分写入不切换 active",
                    conn.execute("SELECT publication FROM hr_control.active").fetchone()["publication"],
                    active_before_failure,
                )
            denied("部分发布后不使用旧授权", lambda: auth.fingerprint(principal()), 409)
            run.sync()
            # 在有效版本上制造非法组织环；同步失败不能发布部分结果。
            active = openfga_source.publication()["id"]
            with run.admin() as conn:
                conn.execute(
                    "UPDATE hr_source.people SET record=jsonb_set(record,'{head_person_id}',%s) WHERE person_id='P0001'",
                    (Jsonb("P0002"),),
                )
            try:
                run.sync()
            except ValueError:
                equal("非法关系阻止发布", True, True)
            else:
                raise AssertionError("非法关系发布成功")
            with run.admin() as conn:
                equal(
                    "失败不切换 active",
                    conn.execute("SELECT publication FROM hr_control.active").fetchone()["publication"],
                    active,
                )
            denied("非法待同步期间拒绝查询", lambda: auth.fingerprint(principal()), 409)
    finally:
        restore(backup)
        recovery.unlink()
    target = config.PROJECT / "reports/openfga-changes.json"
    target.write_text(
        json.dumps({"passed": True, "restored": True, "checks": checks}, ensure_ascii=False, indent=2)
    )
    print(f"动态实验完成 {len(checks)} 项，源表已恢复：{target}")


if __name__ == "__main__":
    main()
