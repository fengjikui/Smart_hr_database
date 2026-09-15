"""Exercise real Superset REST endpoints against isolated PostgreSQL fixtures."""

import json
import os
import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent
FIXTURE = json.loads((ROOT / "fixtures.json").read_text())
CREDENTIALS = json.loads((ROOT / ".local/credentials.json").read_text())
CHECKS = []


@contextmanager
def client_for(username):
    with httpx.Client(base_url="http://127.0.0.1:8088", trust_env=False, timeout=60) as c:
        response = c.post(
            "/api/v1/security/login",
            json={
                "username": username,
                "password": CREDENTIALS[username],
                "provider": "db",
                "refresh": False,
            },
        )
        response.raise_for_status()
        c.headers["Authorization"] = "Bearer " + response.json()["access_token"]
        response = c.get("/api/v1/security/csrf_token/")
        response.raise_for_status()
        c.headers["X-CSRFToken"] = response.json()["result"]
        yield c


def chart(c, dataset_id, columns=None, filters=None, metrics=None):
    return c.post(
        "/api/v1/chart/data",
        json={
            "datasource": {"id": dataset_id, "type": "table"},
            "force": True,
            "result_format": "json",
            "result_type": "full",
            "queries": [
                {
                    "columns": ["person_id"] if columns is None else columns,
                    "metrics": metrics or [],
                    "filters": filters or [],
                    "row_limit": 100,
                    "orderby": [],
                    "extras": {},
                }
            ],
        },
    )


def rows(response):
    response.raise_for_status()
    result = response.json()["result"][0]
    assert not result.get("error"), result.get("error")
    return result["data"]


def check(name, actual, expected):
    assert actual == expected, f"{name}: actual={actual!r}; expected={expected!r}"
    CHECKS.append({"name": name, "passed": True, "actual": actual})


def sql(c, database_id, statement):
    return c.post(
        "/api/v1/sqllab/execute/",
        json={
            "database_id": database_id,
            "schema": "analytics",
            "sql": statement,
            "runAsync": False,
            "queryLimit": 100,
        },
    )


def pg(statement, expect_ok=True):
    env = {
        **os.environ,
        "DOCKER_HOST": os.environ.get(
            "HR_LAB_DOCKER_HOST", f"unix://{Path.home()}/.colima/hr-superset/docker.sock"
        ),
    }
    result = subprocess.run(
        (["docker-compose"] if shutil.which("docker-compose") else ["docker", "compose"])
        + [
            "-f",
            str(ROOT / "compose.yaml"),
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "postgres",
            "-d",
            "hr_lab",
            "-v",
            "ON_ERROR_STOP=1",
            "-Atc",
            statement,
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    if expect_ok and result.returncode:
        raise RuntimeError(result.stderr)
    return result


def main():
    with client_for("lab_admin") as admin:
        response = admin.get("/api/v1/dataset/")
        response.raise_for_status()
        datasets = {d["table_name"]: d for d in response.json()["result"]}
    public_id = datasets["people_public"]["id"]
    private_id = datasets["people_private"]["id"]
    database_id = datasets["people_public"]["database"]["id"]
    for username, expected in FIXTURE["expected"].items():
        with client_for(username) as c:
            actual = sorted(r["person_id"] for r in rows(chart(c, public_id)))
            check(username + " 动态行权限", actual, expected)
    with client_for("lab_employee") as c:
        attempted = [p["person_id"] for p in FIXTURE["people"]]
        data = rows(chart(c, public_id, filters=[{"col": "person_id", "op": "IN", "val": attempted}]))
        check("扩大业务筛选不能扩大授权", sorted(r["person_id"] for r in data), ["E"])
        private = chart(c, private_id, columns=["person_id", "salary"])
        check("员工禁止访问薪资数据集", private.status_code in (401, 403), True)
        hidden = chart(c, public_id, columns=["person_id", "salary"])
        check(
            "公共数据集不能通过指定列名读取薪资",
            hidden.status_code >= 400
            or bool(hidden.json().get("errors"))
            or any(r.get("error") for r in hidden.json().get("result", [])),
            True,
        )
        denied = sql(c, database_id, "SELECT person_id FROM analytics.people_public")
        check("普通问数用户无SQL Lab执行权限", denied.status_code in (401, 403), True)
        check(
            "员工不能修改RLS规则",
            c.post("/api/v1/rowlevelsecurity/", json={}).status_code in (401, 403),
            True,
        )
    with client_for("lab_hr_lead") as c:
        data = rows(chart(c, private_id, columns=["person_id", "salary"]))
        check(
            "HR薪资数据集同时保留行限制",
            sorted(r["person_id"] for r in data),
            FIXTURE["expected"]["lab_hr_lead"],
        )
        check("HR可读取被授权薪资列", all(isinstance(r["salary"], (int, float)) for r in data), True)
        grouped = rows(chart(c, public_id, columns=["department"], metrics=["count"]))
        check("部门聚合总数与授权人员一致", sum(r["count"] for r in grouped), 7)
        pg("UPDATE authz.role_policy SET inherit_hrbp=false WHERE role_key='hr_lead'")
        try:
            check(
                "关闭继承配置即时撤销服务范围",
                sorted(r["person_id"] for r in rows(chart(c, public_id))),
                ["B", "C"],
            )
        finally:
            pg("UPDATE authz.role_policy SET inherit_hrbp=true WHERE role_key='hr_lead'")
        check(
            "恢复继承配置",
            sorted(r["person_id"] for r in rows(chart(c, public_id))),
            FIXTURE["expected"]["lab_hr_lead"],
        )
    with client_for("lab_manager") as c:
        pg("UPDATE hr.people SET head_person_id='G' WHERE person_id='D'")
        try:
            check("管理环导致授权失败关闭", rows(chart(c, public_id)), [])
        finally:
            pg("UPDATE hr.people SET head_person_id='A' WHERE person_id='D'")
    check(
        "公共连接不能直接读取薪资视图",
        pg(
            "SET ROLE hr_public_reader; SELECT salary FROM analytics.people_private", expect_ok=False
        ).returncode
        != 0,
        True,
    )
    check(
        "公共连接不能直接读取原始人员表",
        pg("SET ROLE hr_public_reader; SELECT * FROM hr.people", expect_ok=False).returncode != 0,
        True,
    )
    with client_for("lab_sql_tester") as c:
        registered = sql(c, database_id, "SELECT person_id FROM analytics.people_public ORDER BY person_id")
        registered.raise_for_status()
        check(
            "专用探针：已注册数据集的SQL Lab行过滤",
            sorted(r["person_id"] for r in registered.json()["data"]),
            ["E"],
        )
        unregistered = sql(
            c, database_id, "SELECT person_id FROM analytics.unregistered_probe ORDER BY person_id"
        )
        unregistered.raise_for_status()
        check("边界证据：未注册视图不会自动获得数据集RLS", len(unregistered.json()["data"]), 12)
    report = {
        "superset_version": "6.1.0",
        "passed": True,
        "checks": CHECKS,
        "scope": "真实REST + PostgreSQL；不宣称已测试MCP传输、OA或生产并发",
        "warning": "未注册视图的12行结果是有意设置的反例，证明不能将Superset当作任意SQL防火墙；普通业务角色未授予SQL Lab。",
    }
    (ROOT / ".local/validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
