"""唯一 FastAPI 入口：生命周期、HTTP 安全边界和业务路由装配。"""

import os
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import auth, store, superset_source
from .routes import router


@asynccontextmanager
async def lifespan(app):
    # 可切换身份的演示仅允许在本机使用，生产接入必须另行实现可信 SSO。
    if os.getenv("HR_MODE", "demo") != "demo":
        raise RuntimeError("当前是本机演示，生产部署需要接入 SSO 与数据库隔离。")
    superset_source.enabled()  # 拼错后端配置应立即拒绝，不能悄悄改用 SQLite。
    store.ensure()
    yield


app = FastAPI(title="澄观 HR Intelligence", version="0.1.0", lifespan=lifespan,
              docs_url="/api/docs", openapi_url="/api/openapi.json")
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
app.include_router(router)
_limits = defaultdict(deque)
ALLOWED_ORIGINS = {
    "http://127.0.0.1:3000",
    "http://localhost:3000",
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://testserver",
}
# 默认不增加来源；仅服务端启动配置可增加隔离页面地址，不能由请求头决定。
ALLOWED_ORIGINS.update(filter(None, os.getenv("HR_EXTRA_ORIGINS", "").split(",")))


@app.middleware("http")
async def boundaries(request: Request, call_next):
    # 所有接口统一执行来源、请求大小、速率及响应头约束。
    origin = request.headers.get("origin")
    if origin and origin not in ALLOWED_ORIGINS:
        return JSONResponse({"detail": "来源不受信任。"}, status_code=403)
    if request.headers.get("sec-fetch-site") == "cross-site":
        return JSONResponse({"detail": "不接受跨站请求。"}, status_code=403)
    try:
        if int(request.headers.get("content-length", "0")) > 8192:
            return JSONResponse({"detail": "请求体超过大小限制。"}, status_code=413)
    except ValueError:
        return JSONResponse({"detail": "无效请求。"}, status_code=400)
    cookie_name = auth.COOKIE
    key = (request.cookies.get(cookie_name, "anonymous"), request.url.path == "/api/chat")
    now = time.monotonic()
    queue = _limits[key]
    while queue and queue[0] < now - 60:
        queue.popleft()
    if len(queue) >= (12 if key[1] else 180):
        return JSONResponse(
            {"detail": "请求过于频繁，请稍后重试。"}, status_code=429, headers={"Retry-After": "60"}
        )
    queue.append(now)
    if len(_limits) > 1000:
        for old in list(_limits)[:500]:
            if old != key:
                del _limits[old]
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    return response
