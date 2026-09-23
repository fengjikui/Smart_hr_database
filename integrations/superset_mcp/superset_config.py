"""独立实验的 Web/MCP 共享平台配置；秘密只来自实验私有 env_file。"""
import os
import runpy

# 复用课堂配置的安全默认值，但在独立容器/网络中解析 postgres 服务名。
# 不加载课堂 .env、卷、账号或应用状态；同名库仅存在于各自 PostgreSQL 实例。
globals().update({k: v for k, v in runpy.run_path('/lab/superset_config.py').items() if k.isupper()})
# 不同端口仍共享 Cookie 域；实验 Web 登录不能覆盖课堂浏览器会话。
SESSION_COOKIE_NAME = "hr_superset_mcp_session"
MCP_AUTH_ENABLED = True  # 默认官方为 False；实验强制身份认证，不能静默落入开发模式。
MCP_DEV_USERNAME = None
MCP_RBAC_ENABLED = True  # 保持官方工具级 FAB 权限检查。
MCP_JWT_ALGORITHM = 'HS256'
MCP_JWT_SECRET = os.environ['MCP_JWT_SECRET']  # 独立于 Web SECRET_KEY，不接受 REST 登录 token。
MCP_JWT_ISSUER = 'hr-mcp-lab'
MCP_JWT_AUDIENCE = 'superset-mcp'
MCP_REQUIRED_SCOPES = ['mcp:read']  # 这是 token 准入条件；并不自动阻止写工具，写权限由 FAB 控制。
MCP_JWT_DEBUG_ERRORS = False
MCP_TOOL_SEARCH_CONFIG = {'enabled': False}  # 展开官方完整工具表，便于审计；Agent 另有严格白名单。
MCP_CACHE_CONFIG = {'enabled': False}  # 不跨身份/请求缓存目录或业务响应。
MCP_SERVICE_URL = 'http://127.0.0.1:18088'
MCP_DEBUG = False


def strict_auth_factory(app):
    """官方可插拔工厂：配置错误直接启动失败，防止默认工厂返回 None 关闭认证。"""
    from fastmcp.server.auth.providers.jwt import JWTVerifier
    return JWTVerifier(public_key=app.config['MCP_JWT_SECRET'], algorithm='HS256',
                       issuer=MCP_JWT_ISSUER, audience=MCP_JWT_AUDIENCE,
                       required_scopes=MCP_REQUIRED_SCOPES)


MCP_AUTH_FACTORY = strict_auth_factory
