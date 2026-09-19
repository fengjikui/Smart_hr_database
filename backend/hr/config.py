# 跨版本基础配置：V1 和 V2 都复用本机模型地址、项目根目录及数据目录配置。
# BUSINESS_DB/APP_DB 是 V1 的库名；V2 由这些路径的父目录推导自己的 v2_* 文件，
# 不会把 V2 的宽表写进 V1 hr.sqlite。Superset 数据源开关另见 v2/superset_source.py。
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT
DATA_DIR = Path(os.getenv("HR_DATA_DIR", PROJECT / "data"))
BUSINESS_DB = DATA_DIR / "hr.sqlite"
APP_DB = DATA_DIR / "app.sqlite"
CATALOG_PATH = PROJECT / "semantic" / "catalog.json"
MODEL_URL = os.getenv("LM_STUDIO_URL", "http://127.0.0.1:1234/v1")
MODEL_ID = os.getenv("LM_STUDIO_MODEL", "hr-qwen")
MODEL_TIMEOUT = float(os.getenv("LM_STUDIO_TIMEOUT", "90"))
POLICY_VERSION = "hr-policy-1.0"
CATALOG_VERSION = "hr-metrics-1.1"
DEMO_DATE = "2026-09-11"

DATA_VERSION = "hr-data-2"
