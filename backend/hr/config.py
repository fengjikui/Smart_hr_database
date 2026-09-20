"""应用唯一配置入口；业务数据源由 HR_QUERY_BACKEND 显式选择。"""

import os
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("HR_DATA_DIR", PROJECT / "data"))
# SQLite 仅保存应用会话/历史；people.sqlite 是可重现的离线样本与导入来源。
APP_DB = DATA_DIR / "sessions.sqlite"
MODEL_URL = os.getenv("LM_STUDIO_URL", "http://127.0.0.1:1234/v1")
MODEL_ID = os.getenv("LM_STUDIO_MODEL", "hr-qwen")
MODEL_TIMEOUT = float(os.getenv("LM_STUDIO_TIMEOUT", "90"))
