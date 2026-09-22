"""官方 MCP 6.1.0 的部署适配层：只绑定身份，不注册/替换任何工具。

原生 CLI 的 JWTVerifier 负责验签，却未将 token subject 写入 Flask g.user。
这里使用官方公开的中间件扩展点，把已验证身份绑定到独立请求上下文。
所有工具、DAO、数据集鉴权和 ChartDataCommand 仍来自 apache/superset 镜像。
"""
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_access_token
from fastmcp.server.middleware import Middleware
from flask import g
from superset.mcp_service.app import init_fastmcp_server
from superset.mcp_service.auth import load_user_with_relationships
from superset.mcp_service.flask_singleton import get_flask_app
from superset.mcp_service.server import build_middleware_list


class PrincipalBinding(Middleware):
    async def on_call_tool(self, context, call_next):
        """验签由 FastMCP 完成；无用户、停用用户、解析失败一律拒绝，不设开发兜底。"""
        token = get_access_token()
        claims = getattr(token, 'claims', {}) if token else {}
        username = claims.get('sub')
        if not isinstance(username, str) or not username:
            raise ToolError('Authenticated subject required')
        app = get_flask_app()
        # 每个异步任务单独 push request/app context，官方 auth_hook 会保留该请求的 g。
        # 不复用 SQLAlchemy user/roles 对象；每次调用重读，角色撤销即时生效。
        with app.test_request_context('/mcp', method='POST'):
            user = load_user_with_relationships(username=username)
            if user is None or not user.is_active:
                raise ToolError('Unknown or inactive subject')
            g.user = user
            return await call_next(context)


def main():
    app = get_flask_app()
    # 不走原 _create_auth_provider 吞异常返回 None 的分支；签名配置错误直接退出。
    auth = app.config['MCP_AUTH_FACTORY'](app)
    if auth is None or not app.config['MCP_AUTH_ENABLED'] or app.config.get('MCP_DEV_USERNAME'):
        raise RuntimeError('Authenticated multi-user mode is required')
    server = init_fastmcp_server(auth=auth, middleware=[PrincipalBinding(), *build_middleware_list()])
    server.run(transport='streamable-http', host='0.0.0.0', port=5008, stateless_http=True)


if __name__ == '__main__':
    main()
