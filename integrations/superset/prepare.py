"""Generate local-only credentials. Never overwrite an existing lab's secrets."""

import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent
# 宿主机首次建实验密钥；Superset 元数据库、业务读者和演示登录账号各有独立凭据。
# 重跑复用 lab.env，避免服务已使用旧密钥而脚本突然生成新密码导致失联。
local = ROOT / ".local"
local.mkdir(mode=0o700, exist_ok=True)
env_path = local / "lab.env"
if not env_path.exists():
    values = {
        key: secrets.token_hex(32)
        for key in (
            "POSTGRES_PASSWORD",
            "META_PASSWORD",
            "PUBLIC_DB_PASSWORD",
            "PRIVATE_DB_PASSWORD",
            "SUPERSET_SECRET_KEY",
            "LAB_DEMO_SEED",
        )
    }
    fd = os.open(env_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write("".join(f"{key}={value}\n" for key, value in values.items()))
else:
    values = dict(line.split("=", 1) for line in env_path.read_text().splitlines())
users = ["lab_admin"] + [u["username"] for u in json.loads((ROOT / "fixtures.json").read_text())["users"]]
credentials = {
    user: hmac.new(values["LAB_DEMO_SEED"].encode(), user.encode(), hashlib.sha256).hexdigest()[:24]
    for user in users
}
path = local / "credentials.json"
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as f:
    json.dump(credentials, f, indent=2)
print("Local credentials prepared in integrations/superset/.local/credentials.json")
