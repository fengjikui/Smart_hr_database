"""Pinned official binaries and isolated local process lifecycle; no model inference."""

import argparse
import hashlib
import json
import os
import platform
import signal
import socket
import subprocess
import sys
import tarfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
# 与项目主服务分离：引擎 HTTP 8090、实验网页 8091、引擎 gRPC 8092。
# 二进制、引擎 SQLite、配置历史、PID 和日志均留在本实验 .local 中，不进 Git。
LOCAL = ROOT / ".local"
BIN = LOCAL / "bin"
SERVER_VERSION = "1.20.0"
CLI_VERSION = "0.7.20"


def install():
    # 固定版本并核对官方校验和；只解出指定可执行文件，不展开整个压缩包到工作目录。
    system = platform.system().lower()
    arch = {"aarch64": "arm64", "arm64": "arm64", "x86_64": "amd64"}[platform.machine()]
    BIN.mkdir(parents=True, exist_ok=True)
    for name, repo, version, directory in [
        ("openfga", "openfga/openfga", SERVER_VERSION, "server"),
        ("fga", "openfga/cli", CLI_VERSION, "cli"),
    ]:
        folder = LOCAL / "downloads" / directory
        folder.mkdir(parents=True, exist_ok=True)
        archive = f"{name}_{version}_{system}_{arch}.tar.gz"
        for filename in [archive, "checksums.txt"]:
            destination = folder / filename
            if not destination.exists():
                url = f"https://github.com/{repo}/releases/download/v{version}/{filename}"
                with urllib.request.urlopen(url, timeout=120) as source:
                    destination.write_bytes(source.read())
        checksums = (folder / "checksums.txt").read_text().splitlines()
        expected = next(line.split()[0] for line in checksums if line.split()[-1] == archive)
        actual = hashlib.sha256((folder / archive).read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError(f"Checksum mismatch: {archive}")
        with tarfile.open(folder / archive) as package:
            member = next(m for m in package.getmembers() if m.isfile() and Path(m.name).name == name)
            executable = package.extractfile(member)
            if executable is None:
                raise RuntimeError(f"Missing executable: {name}")
            (BIN / name).write_bytes(executable.read())
        (BIN / name).chmod(0o755)
        print(f"Verified {name} {version}: sha256 {actual}")


def wait_http(url, attempts=160):
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except (OSError, TimeoutError):
            time.sleep(0.25)
    raise RuntimeError(f"Service did not become healthy: {url}; inspect {LOCAL / 'logs'}")


def owned_pid(name):
    # 不能仅凭 PID 文件杀进程：PID 可能被复用，必须同时匹配本实验命令标识。
    path = LOCAL / f"{name}.pid"
    if not path.exists():
        return None
    pid = int(path.read_text())
    command = subprocess.run(["ps", "-p", str(pid), "-o", "args="], capture_output=True, text=True)
    marker = str(BIN / "openfga") if name == "engine" else "integrations.openfga.server:app"
    return pid if command.returncode == 0 and marker in command.stdout else None


def port_free(port):
    with socket.socket() as connection:
        return connection.connect_ex(("127.0.0.1", port)) != 0


def start():
    # 只复用健康的本实验进程；发现端口被别人占用就停止启动，不清理未知进程。
    if owned_pid("engine") and owned_pid("web"):
        wait_http("http://127.0.0.1:8091/api/health")
        print("OpenFGA 权限实验室：http://127.0.0.1:8091")
        return
    if any(not port_free(port) for port in [8090, 8091, 8092]):
        raise RuntimeError("8090/8091/8092 已占用；请检查实验室 status，不会停止其他进程。")
    if not (BIN / "openfga").exists() or not (BIN / "fga").exists():
        install()
    logs = LOCAL / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, GOMAXPROCS="2", GOMEMLIMIT="128MiB", OMP_NUM_THREADS="1")
    database = f"file:{LOCAL / 'engine.db'}"
    subprocess.run([str(BIN / "openfga"), "migrate", "--datastore-engine", "sqlite", "--datastore-uri", database], check=True, env=env)
    commands = {
        "engine": [str(BIN / "openfga"), "run", "--datastore-engine", "sqlite", "--datastore-uri", database,
                   "--http-addr", "127.0.0.1:8090", "--grpc-addr", "127.0.0.1:8092", "--playground-enabled=false", "--metrics-enabled=false", "--log-level", "warn"],
        "web": [sys.executable, "-m", "uvicorn", "integrations.openfga.server:app", "--host", "127.0.0.1", "--port", "8091"],
    }
    started = []
    # 任一启动失败只回收本次启动且仍匹配标识的进程，不影响项目主服务和其他程序。
    try:
        for name, command in commands.items():
            with (logs / f"{name}.log").open("ab") as output:
                process = subprocess.Popen(command, cwd=ROOT.parent.parent, env=env, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
            (LOCAL / f"{name}.pid").write_text(str(process.pid))
            started.append(name)
            wait_http(f"http://127.0.0.1:{8090 if name == 'engine' else 8091}/{ 'healthz' if name == 'engine' else 'api/health'}")
    except Exception:
        for name in started:
            pid = owned_pid(name)
            if pid:
                os.kill(pid, signal.SIGTERM)
        raise
    print("OpenFGA 权限实验室：http://127.0.0.1:8091")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["install", "up", "stop", "status"])
    action = parser.parse_args().action
    if action == "install":
        install()
    elif action == "up":
        start()
    elif action == "stop":
        for name in ["web", "engine"]:
            pid = owned_pid(name)
            if pid:
                os.kill(pid, signal.SIGTERM)
                print(f"Stopped {name} ({pid})")
    else:
        print(json.dumps({name: owned_pid(name) for name in ["engine", "web"]}))


if __name__ == "__main__":
    main()
