"""宿主机命令入口：生成数据、准备课堂、只读检查学生的当前查询结果。

不修改 Docker 全局 context，也不启动或停止已有服务。只使用 lab.sh 相同的本地环境。
setup 不替学生配置 RLS；重复 setup 不会清空学生的规则、角色或业务数据。
"""

import argparse
import hashlib
import hmac
import json
import os
import shutil
import subprocess
from pathlib import Path

from generate import LOCAL, ROOT, USERS
from generate import main as generate_data


def container_command(script, *args):
    """查找当前实验自己的 Superset 容器；不依赖某个写死的容器 ID。"""
    env = dict(os.environ, DOCKER_HOST=os.environ.get(
        "HR_LAB_DOCKER_HOST", f"unix://{Path.home()}/.colima/hr-superset/docker.sock"))
    compose = ["docker-compose"] if shutil.which("docker-compose") else ["docker", "compose"]
    lookup = subprocess.run([*compose, "-f", str(ROOT.parent / "compose.yaml"), "ps", "-q", "superset"],
                            env=env, text=True, capture_output=True, check=True)
    container_id = lookup.stdout.strip()
    if not container_id:
        raise SystemExit("Superset 尚未运行。请先阅读 integrations/superset/README.md 的启动步骤。")
    result = subprocess.run(["docker", "exec", container_id, "python", f"/lab/classroom/{script}", *args],
                            env=env, text=True, capture_output=True, timeout=240)
    if result.returncode:
        # 错误需要可见，不能把初始化失败当作准备完成；程序不输出令牌或密码。
        raise SystemExit(result.stderr[-5000:] + "\n" + result.stdout[-3000:])
    return result


def setup():
    generate_data()
    # 只读取已有本地演示密钥，不向终端输出。所有课堂凭据都留在 Git 忽略目录。
    values = dict(line.split("=", 1) for line in (ROOT.parent / ".local/lab.env").read_text().splitlines())
    accounts = ["learn_admin", *[user[0] for user in USERS]]
    credentials = {name: hmac.new(values["LAB_DEMO_SEED"].encode(), name.encode(), hashlib.sha256).hexdigest()[:24]
                   for name in accounts}
    path = LOCAL / "credentials.json"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(credentials, f, indent=2)
    result = container_command("setup.py")
    manifest = json.loads(result.stdout.strip().splitlines()[-1])
    (LOCAL / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print("课堂准备完成：数据集与空角色已创建，没有替你创建 RLS。")
    print(f"本机登录资料：{path}")
    print(f"实际数据集ID与可复制权限名称：{LOCAL / 'manifest.json'}")


def inspect(username, dataset):
    """通过真实 Superset REST 查询，只读观察，不创建或修改任何授权规则。"""
    import httpx

    credentials = json.loads((LOCAL / "credentials.json").read_text())
    manifest = json.loads((LOCAL / "manifest.json").read_text())
    spec = manifest["datasets"][dataset]
    columns = {"orders": ["order_id", "owner_id", "region", "amount", "phone_masked"],
               "people": ["person_id", "name", "department"],
               "payroll": ["person_id", "salary"],
               "orders_private": ["order_id", "customer_phone"]}[dataset]
    with httpx.Client(base_url="http://127.0.0.1:8088", trust_env=False, timeout=30) as client:
        response = client.post("/api/v1/security/login", json={"username": username,
            "password": credentials[username], "provider": "db", "refresh": False})
        response.raise_for_status()
        client.headers["Authorization"] = "Bearer " + response.json()["access_token"]
        csrf = client.get("/api/v1/security/csrf_token/")
        csrf.raise_for_status()
        client.headers["X-CSRFToken"] = csrf.json()["result"]
        response = client.post("/api/v1/chart/data", json={"datasource": {"id": spec["id"], "type": "table"},
            "force": True, "result_format": "json", "result_type": "full", "queries": [{"columns": columns,
                "metrics": [], "filters": [], "row_limit": 100, "orderby": [], "extras": {}}]})
        print(f"身份={username} 数据集={dataset} HTTP={response.status_code}")
        if response.status_code in (401, 403):
            print("当前身份被拒绝（初始空角色下属于预期）。")
            return
        response.raise_for_status()
        result = response.json()["result"][0]
        if result.get("error"):
            raise SystemExit(f"查询失败，不能当作0行：{result['error']}")
        rows = result["data"]
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        print(f"行数={len(rows)}")
        if dataset == "orders":
            print(f"订单金额合计={sum(row['amount'] for row in rows)}")
        print("实际执行SQL（观察WHERE里的权限条件）：")
        print(result.get("query", "此响应未提供SQL，请在图表菜单查看 Query。"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["generate", "setup", "inspect", "verify-preparation"])
    parser.add_argument("--user", default="learn_east", choices=["learn_admin", *[u[0] for u in USERS]])
    parser.add_argument("--dataset", default="orders", choices=["orders", "people", "payroll", "orders_private"])
    args = parser.parse_args()
    if args.action == "generate":
        generate_data()
    elif args.action == "setup":
        setup()
    elif args.action == "inspect":
        inspect(args.user, args.dataset)
    else:
        result = container_command("verify.py")
        report = json.loads(result.stdout.strip().splitlines()[-1])
        (LOCAL / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
