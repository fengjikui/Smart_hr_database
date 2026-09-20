"""生成本机密钥；已存在时不覆盖，防止 Superset 登录和数据连接失效。"""

import os
import secrets
from pathlib import Path

local = Path(__file__).resolve().parent / ".local"
local.mkdir(mode=0o700, exist_ok=True)
env_path = local / "lab.env"
if not env_path.exists():
    values = {key: secrets.token_hex(32) for key in (
        "POSTGRES_PASSWORD", "META_PASSWORD", "SUPERSET_SECRET_KEY", "LAB_DEMO_SEED",
    )}
    fd = os.open(env_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write("".join(f"{key}={value}\n" for key, value in values.items()))
print("Superset 本机密钥已准备；已有密钥未修改。")
