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
CATALOG_VERSION = "hr-metrics-1.0"
DEMO_DATE = "2026-09-11"
