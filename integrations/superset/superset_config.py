"""Local permission proof only. Credentials are generated outside Git."""

import os

SECRET_KEY = os.environ["SUPERSET_SECRET_KEY"]
SQLALCHEMY_DATABASE_URI = (
    "postgresql+psycopg2://superset_meta:" + os.environ["META_PASSWORD"] + "@postgres:5432/superset_meta"
)
FEATURE_FLAGS = {
    "ENABLE_TEMPLATE_PROCESSING": True,
    "RLS_IN_SQLLAB": True,
    "ALLOW_ADHOC_SUBQUERY": False,
    "DASHBOARD_RBAC": False,
}
# No query-response caching while proving immediate permission revocation.
CACHE_CONFIG = {"CACHE_TYPE": "NullCache"}
DATA_CACHE_CONFIG = {"CACHE_TYPE": "NullCache"}
SQLLAB_ASYNC_TIME_LIMIT_SEC = 60
SQLLAB_TIMEOUT = 60
ROW_LIMIT = 1000
WTF_CSRF_ENABLED = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_HTTPONLY = True
TALISMAN_ENABLED = False  # localhost HTTP only; do not reuse in production
FAB_ADD_SECURITY_API = True
ENABLE_PROXY_FIX = False
LOAD_EXAMPLES = False
BABEL_DEFAULT_LOCALE = "en"
LANGUAGES = {"en": {"flag": "us", "name": "English"}, "zh": {"flag": "cn", "name": "Chinese"}}
