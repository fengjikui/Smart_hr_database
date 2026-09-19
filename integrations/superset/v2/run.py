"""宿主机入口：export 导出当前 V2，setup 建立隔离演示，status 只读盘点。

setup 默认不覆盖已有数据和手动权限。sync-data 是显式的数据/业务策略重导命令；
它也不会撤销用户后来在 Superset 中手工增加或删除的角色与 RLS。
本脚本不会启动、停止或重启任何现有服务。
"""

import argparse
import hashlib
import hmac
import json
import os
import shutil
import subprocess

from export import LOCAL, ROOT
from export import main as export_data


def container_command(script, *args):
    """使用既有实验 Docker socket，避免修改用户全局 Docker context。"""
    env = dict(os.environ, DOCKER_HOST=os.environ.get(
        "HR_LAB_DOCKER_HOST", f"unix://{ROOT.home()}/.colima/hr-superset/docker.sock"))
    compose = ["docker-compose"] if shutil.which("docker-compose") else ["docker", "compose"]
    lookup = subprocess.run([*compose, "-f", str(ROOT.parent / "compose.yaml"), "ps", "-q", "superset"],
        env=env, text=True, capture_output=True, check=True)
    container_id = lookup.stdout.strip()
    if not container_id:
        raise SystemExit("Superset 未运行；请先按 integrations/superset/README.md 启动已有实验环境。")
    result = subprocess.run(["docker", "exec", container_id, "python", f"/lab/v2/{script}", *args],
        env=env, text=True, capture_output=True, timeout=240)
    if result.returncode:
        raise SystemExit(result.stderr[-5000:] + "\n" + result.stdout[-3000:])
    return json.loads(result.stdout.strip().splitlines()[-1])


def read_seed():
    """只从本机已有环境文件读取派生密钥，不打印，不接触数据库或用户权限。"""
    env_file = ROOT.parent / ".local" / "lab.env"
    values = dict(line.split("=", 1) for line in env_file.read_text().splitlines()
                  if line.strip() and not line.lstrip().startswith("#") and "=" in line)
    return values["LAB_DEMO_SEED"]


def write_private_json(target, value):
    """新建和覆盖时都强制 0600；输出目录已经被仓库 Git 忽略。"""
    target.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w") as handle:
        json.dump(value, handle, indent=2)


def write_credentials(fixture):
    """Superset 业务账号凭据与 PostgreSQL 连接凭据分开保存，防止混淆。"""
    seed = read_seed()
    names = ["v2_setup_admin", "v2_unmapped", *["v2_" + p["id"] for p in fixture["personas"]]]
    credentials = {name: hmac.new(seed.encode(), name.encode(), hashlib.sha256).hexdigest()[:24]
                   for name in names}
    write_private_json(LOCAL / "credentials.json", credentials)


def write_database_credentials():
    """导出手动配置数据源所需参数；严格复用 setup.py 的 HMAC 派生机制。

    Superset 在容器内连接 postgres:5432；宿主机数据库客户端用 127.0.0.1:55432。
    仅写本机文件，不连接 Superset/PostgreSQL，也不修改账号、视图或 RLS。
    """
    seed = read_seed()
    connections = {}
    for level in ["public", "contract"]:
        username = "v2_" + level + "_reader"
        connections[level] = {"username": username,
            "password": hmac.new(seed.encode(), username.encode(), hashlib.sha256).hexdigest()[:24],
            "database": "hr_v2", "container_host": "postgres", "container_port": 5432,
            "host": "127.0.0.1", "host_port": 55432}
    target = LOCAL / "database-credentials.json"
    write_private_json(target, connections)
    return target


def setup(sync_data=False):
    fixture = export_data()
    write_credentials(fixture)
    write_database_credentials()
    args = ["--sync-data"] if sync_data else []
    manifest = container_command("setup.py", *args)
    (LOCAL / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(f"V2 独立演示已准备：数据库 {manifest['database']}，{manifest['row_count']} 人，"
          f"{len(manifest['datasets'])} 数据集，{len(manifest['roles'])} 自定义角色，{len(manifest['rls'])} RLS。")
    if manifest["data_fingerprint"] != fixture["data_fingerprint"]:
        print("注意：保留了 PostgreSQL 既有快照，与当前导出不同；需要更新时显式执行 sync-data。")
    print(f"数据源与账号映射：{LOCAL / 'manifest.json'}")
    print(f"本机登录资料（请勿提交）：{LOCAL / 'credentials.json'}")
    print(f"本机数据库连接资料（请勿提交）：{LOCAL / 'database-credentials.json'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["export", "setup", "sync-data", "status", "verify-storage",
                                          "export-connection-info"])
    args = parser.parse_args()
    if args.action == "export":
        export_data()
    elif args.action == "status":
        print(json.dumps(container_command("status.py"), ensure_ascii=False, indent=2))
    elif args.action == "verify-storage":
        report = container_command("verify_storage.py")
        (LOCAL / "storage-verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.action == "export-connection-info":
        print(write_database_credentials())
    else:
        setup(sync_data=args.action == "sync-data")


if __name__ == "__main__":
    main()
