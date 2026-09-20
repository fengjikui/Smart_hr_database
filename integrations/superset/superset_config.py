"""Local permission proof only. Credentials are generated outside Git."""

import os

# 元数据库只存平台用户、角色、图表等对象，
# 业务事实在各自数据源数据库。这里开放模板以使用 current_user_id()，不是开放任意模型 SQL。
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
# SQL Lab 的实验特性开关不等于业务用户获准使用 SQL Lab；用户角色还需单独授权。
# 当前应用既不暴露连接到 SQL Lab，也不授业务账号对应能力，避免绕开受控数据集。
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
