"""本地权限演示的平台配置；由 SUPERSET_CONFIG_PATH 指向此文件。

密钥从环境变量读取，不写入 Git。这里是整个平台的能力开关，不负责给某个
业务用户授权；用户角色、数据集访问权和 RLS 仍需分别配置。
"""

import os

# 元数据库只存平台用户、角色、图表等对象，
# 业务事实在各自数据源数据库。这里开放模板以使用 current_user_id()，不是开放任意模型 SQL。
SECRET_KEY = os.environ["SUPERSET_SECRET_KEY"]
SQLALCHEMY_DATABASE_URI = (
    "postgresql+psycopg2://superset_meta:" + os.environ["META_PASSWORD"] + "@postgres:5432/superset_meta"
)
FEATURE_FLAGS = {
    # 让 RLS 中的 {{ current_user_id() }} 按平台登录人求值；不是模型传入的 ID。
    "ENABLE_TEMPLATE_PROCESSING": True,
    # 此开关不是授予 SQL Lab 使用权，也不能替代业务数据集上的 RLS 配置。
    "RLS_IN_SQLLAB": True,
    # 限制临时表达式中的子查询；本项目只提交白名单生成的表达式。
    "ALLOW_ADHOC_SUBQUERY": False,
    # 本演示以数据集访问授权为主，不启用按 dashboard 角色授权的另一条路径。
    "DASHBOARD_RBAC": False,
}
# SQL Lab 的实验特性开关不等于业务用户获准使用 SQL Lab；用户角色还需单独授权。
# 当前应用既不暴露连接到 SQL Lab，也不授业务账号对应能力，避免绕开受控数据集。
# 撤权演示关闭查询结果缓存，便于观察配置变化；生产缓存需另设计失效策略。
CACHE_CONFIG = {"CACHE_TYPE": "NullCache"}
DATA_CACHE_CONFIG = {"CACHE_TYPE": "NullCache"}
# 这是 SQL Lab 的超时配置；不代表已配置 Celery/消息队列或启用异步 worker。
SQLLAB_ASYNC_TIME_LIMIT_SEC = 60
SQLLAB_TIMEOUT = 60
ROW_LIMIT = 1000
# Chart Data POST 也走 CSRF 防护；适配器登录后会额外取 CSRF token。
WTF_CSRF_ENABLED = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_HTTPONLY = True
TALISMAN_ENABLED = False  # 仅配合本地 HTTP 演示；生产需另配 HTTPS 与安全响应头。
# 开放安全管理 API 的路由能力不等于授权普通用户使用；仍由平台权限判断。
FAB_ADD_SECURITY_API = True
ENABLE_PROXY_FIX = False
LOAD_EXAMPLES = False
BABEL_DEFAULT_LOCALE = "en"
LANGUAGES = {"en": {"flag": "us", "name": "English"}, "zh": {"flag": "cn", "name": "Chinese"}}
