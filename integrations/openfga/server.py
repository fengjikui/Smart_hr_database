"""Local synthetic-data administrator demo. Identity switching is not authentication."""

import csv
import io
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import Field, ValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from integrations.openfga.core import ConflictError, EngineError, Lab, Record
from integrations.openfga.runtime import ROOT, SERVER_VERSION

lab = Lab()
# 此 Web 服务是可编辑合成事实/模型的本机管理实验，不是生产鉴权网关。
# /api/roster 的 user 参数是“选谁来模拟”，不等价于已验证的企业登录身份。
token = secrets.token_urlsafe(32)


@asynccontextmanager
async def lifespan(app):
    lab.state()
    yield


app = FastAPI(title="OpenFGA HR 权限实验室", docs_url=None, redoc_url=None, lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])


@app.middleware("http")
async def local_demo_boundary(request: Request, call_next):
    # 配置写入要求本机页面令牌及同源；这个保护与 OpenFGA 的人员可见性判断职责不同。
    if request.method not in {"GET", "HEAD"}:
        origin = request.headers.get("origin")
        expected_origin = str(request.base_url).rstrip("/")
        if request.headers.get("x-demo-token") != token or (origin and origin != expected_origin):
            return JSONResponse({"detail": "只允许本机演示页面提交配置"}, status_code=403)
        if int(request.headers.get("content-length", "0")) > 100000:
            return JSONResponse({"detail": "配置超过演示大小限制"}, status_code=413)
    response = await call_next(request)
    response.headers.update({"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                             "Content-Security-Policy": "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'",
                             "Referrer-Policy": "no-referrer"})
    return response


@app.exception_handler(EngineError)
async def engine_error(request, exc):
    return JSONResponse({"detail": str(exc)}, status_code=503)


@app.exception_handler(ConflictError)
async def conflict_error(request, exc):
    return JSONResponse({"detail": str(exc)}, status_code=409)


@app.exception_handler(ValueError)
async def invalid_configuration(request, exc):
    return JSONResponse({"detail": str(exc)}, status_code=400)


@app.exception_handler(ValidationError)
async def invalid_record(request, exc):
    return JSONResponse({"detail": str(exc)}, status_code=400)


@app.exception_handler(PermissionError)
async def forbidden(request, exc):
    return JSONResponse({"detail": str(exc)}, status_code=403)


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/assets/{name}")
def asset(name: str):
    if name not in {"app.js", "style.css"}:
        raise HTTPException(404)
    return FileResponse(ROOT / "static" / name)


@app.get("/api/health")
def health():
    engine = lab.engine.request("GET", "/healthz")
    return {"status": "ok", "engine": engine, "version": SERVER_VERSION}


@app.get("/api/state")
def state():
    return {**lab.state(), "history": lab.history(), "demo_token": token, "engine_version": SERVER_VERSION}


@app.get("/api/roster")
def roster(user: str, department: str = ""):
    return lab.query(user, department)


@app.get("/api/check")
def check(user: str, target: str, relation: str = "view_basic"):
    return lab.explain(user, target, relation)


@app.get("/api/export")
def export(user: str, department: str = ""):
    result = lab.query(user, department, export=True)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["person_id", "姓名", "部门", "学历", "学校", "模拟月薪"])
    for row in result["rows"]:
        values = [row[key] for key in ["person_id", "name", "department", "education", "school", "salary"]]
        writer.writerow(["'" + value if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")) else value for value in values])
    return Response("\ufeff" + output.getvalue(), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="synthetic-roster.csv"'})


class Publish(Record):
    config: dict
    model_source: str = Field(max_length=20000)
    expected_version: int = Field(ge=0)


class Revision(Record):
    expected_version: int = Field(ge=0)
    version: int = Field(default=0, ge=0)


@app.post("/api/publish")
def publish(body: Publish):
    # expected_version 提供乐观锁；真正的校验、模型转换、试算和原子切换在 Lab.publish。
    return lab.publish(body.config, body.model_source, body.expected_version)


@app.post("/api/reset")
def reset(body: Revision):
    config, source = lab.defaults()
    return lab.publish(config, source, body.expected_version, "恢复初始演示样本")


@app.post("/api/rollback")
def rollback(body: Revision):
    return lab.rollback(body.version, body.expected_version)
