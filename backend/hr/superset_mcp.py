"""真实 MCP 客户端：认证、初始化、工具发现和受限目录调用。

这是官方 Python MCP SDK 的 Streamable HTTP 客户端。业务查询仍交给既有
Chart Data REST 编译器；绝不把普通 HTTP 数据查询改称 MCP。每次建立独立
会话/短期 token，结束时销毁，无全局客户端、用户缓存或自动身份重试。
"""
import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path

import httpx
import jwt
from fastapi import HTTPException
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from . import config, superset_source

ALLOWED_TOOLS = frozenset({'list_datasets'})
TIMEOUT = 25  # 整个握手+发现+调用的截止秒数，不是单个网络包的无限滑动超时。
MAX_BYTES = 1_048_576  # 含工具 schema/通知的单次 HTTP 响应最大 1 MiB。


def enabled():
    return os.getenv('HR_QUERY_BACKEND', 'superset') == 'superset_mcp'


def token_for(p):
    """签名身份仅取可信 persona→manifest 映射；密钥不放进 p、trace 或模型消息。"""
    subject = superset_source.identity(p)
    path = Path(os.getenv('HR_MCP_SIGNING_FILE',
        config.PROJECT / 'integrations/superset_mcp/.local/mcp-signing.json'))
    try:
        secret = json.loads(path.read_text())['secret']
        if not isinstance(secret, str) or len(secret) < 32:
            raise ValueError()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(503, 'MCP 服务端签名配置未就绪') from exc
    now = int(time.time())
    return jwt.encode({'sub': subject['username'], 'iss': 'hr-mcp-lab', 'aud': 'superset-mcp',
        'iat': now, 'exp': now + 120, 'scope': 'mcp:read'}, secret, algorithm='HS256')


class BoundedStream(httpx.AsyncByteStream):
    """在 SDK 解析 JSON/SSE 前限制字节，不能等无限响应已入内存才检查。"""
    def __init__(self, stream):
        self.stream = stream

    async def __aiter__(self):
        size = 0
        async for chunk in self.stream:
            size += len(chunk)
            if size > MAX_BYTES:
                raise ValueError('MCP response exceeds byte limit')
            yield chunk

    async def aclose(self):
        await self.stream.aclose()


class BoundedTransport(httpx.AsyncHTTPTransport):
    async def handle_async_request(self, request):
        response = await super().handle_async_request(request)
        response.stream = BoundedStream(response.stream)
        return response


@asynccontextmanager
async def protocol(token):
    """底层协议会话供验证脚本使用；token 不写日志，也不接受客户端提供的 URL。"""
    url = os.getenv('HR_SUPERSET_MCP_URL', 'http://127.0.0.1:15008/mcp')
    async with httpx.AsyncClient(headers={'Authorization': 'Bearer ' + token} if token else {},
        transport=BoundedTransport(retries=0), trust_env=False, timeout=TIMEOUT,
        follow_redirects=False) as http:
        async with streamable_http_client(url, http_client=http) as (read, write, _):
            async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=TIMEOUT)) as session:
                yield session


def decode(result):
    """Superset 可能返回 isError，也可能在成功协议包中携带业务 error，两者都拒绝。"""
    if result.isError:
        raise HTTPException(403, 'MCP 拒绝当前工具调用；未切换身份或数据源')
    try:
        data = result.structuredContent
        if data is None:
            blocks = [block.text for block in result.content if block.type == 'text']
            if len(blocks) != 1:
                raise ValueError()
            # 6.1.0 的异常中间件可返回 isError=false + 普通 Error 文本。
            if blocks[0].startswith('Error:'):
                raise HTTPException(403, 'MCP 工具执行被拒绝；未回退其他身份或数据源')
            data = json.loads(blocks[0])
        if not isinstance(data, dict):
            raise ValueError()
        if data.get('error') or data.get('error_type'):
            raise HTTPException(403, 'MCP 工具返回拒绝或错误；不能视为零行')
        return data
    except (ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(502, 'MCP 工具返回结构无效') from exc


async def catalog_async(p):
    """仅披露当前用户获准的固定五种出口；上游自由描述不进入模型上下文。"""
    try:
        async with asyncio.timeout(TIMEOUT):
            async with protocol(token_for(p)) as session:
                initialized = await session.initialize()
                tools = await session.list_tools()
                available = {t.name for t in tools.tools}
                if not ALLOWED_TOOLS <= available:
                    raise HTTPException(502, '官方 MCP 缺少所需目录工具')
                response = decode(await session.call_tool('list_datasets', {'request': {
                    'page': 1, 'page_size': 100, 'select_columns': ['id', 'table_name'],
                    'use_cache': False, 'force_refresh': True}}))
                rows = response.get('datasets')
                if not isinstance(rows, list) or response.get('total_count') != len(rows) or response.get('has_next'):
                    raise HTTPException(413, 'MCP 目录超过限额或不完整，拒绝使用截断目录')
                known = superset_source.manifest()['datasets']
                by_id = {v['id']: k for k, v in known.items()}
                safe = []
                for row in rows:
                    key = by_id.get(row.get('id'))
                    if key is not None and row.get('table_name') == known[key]['table_name']:
                        # 输出由本地已审阅常量/manifest 构造，不转发远端描述、SQL、owner 等。
                        safe.append(key)
                if not {'context', 'people_public', 'events_public'} <= set(safe):
                    raise HTTPException(403, 'MCP 目录缺少当前业务必需的数据集权限')
                return {'datasets': sorted(safe), 'trace': {
                    'transport': 'MCP Streamable HTTP', 'protocol_version': initialized.protocolVersion,
                    'stages': ['initialize', 'notifications/initialized', 'tools/list', 'tools/call:list_datasets'],
                    'allowed_tools': sorted(ALLOWED_TOOLS), 'dataset_count': len(safe),
                    'query_transport': 'Superset Chart Data REST → PostgreSQL'}}
    except HTTPException:
        raise
    except Exception as exc:
        # SDK 的上下文退出可能把我们自己的 HTTPException 包成 ExceptionGroup。
        # 保留已经过安全处理的 403/413，不能把明确撤权错误混成服务故障。
        pending = [exc]
        while pending:
            error = pending.pop()
            if isinstance(error, HTTPException):
                raise error from None
            if isinstance(error, BaseExceptionGroup):
                pending.extend(error.exceptions)
        # 网络/SDK 异常可能包含请求头或堆栈；只输出固定错误，禁止 str(exc)。
        raise HTTPException(503, 'MCP 不可用或认证失败，已停止查询；未回退其他身份或数据源') from exc


def catalog(p):
    """同步业务节点运行在线程中；底层 async 全部在同一个事件循环中创建与释放。"""
    return asyncio.run(catalog_async(p))
