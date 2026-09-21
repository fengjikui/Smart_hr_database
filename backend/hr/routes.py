"""HTTP 边界：会话/CSRF → 类型化请求 → auth、service 或 LangGraph。

页面、自助核验和聊天都复用同一后端身份，不能由浏览器传入 Superset 用户或
数据库连接。这里的身份选择属于本机演示，不是生产 SSO；Superset 模式也
不把服务端凭据返回浏览器。路由本身尽量不重复实现查询与授权规则。
"""

import csv
import io
import json

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import Field

from . import auth, config, openfga_source, query, registry, service, store, superset_source
from .model import model_status
from .schema import Plan, Question, Strict

router = APIRouter(prefix="/api", tags=["HR 查询"])


class Persona(Strict):
    persona_id: str = Field(max_length=30)


class Drill(Strict):
    plan: Plan
    group: dict[str, str]
    metric: str = Field(max_length=50)


def checked(request: Request, p=Depends(auth.principal)):
    """组合已有会话与 CSRF 依赖；POST 查询、下钻、核验和导出共同使用。"""
    auth.csrf(request, p)
    return p


@router.get("/health")
def health():
    store.ensure()
    return {
        "status": "ok",
        "version": store.DATA_VERSION,
        "as_of": store.AS_OF,
        "synthetic": True,
        "source_fields": 26,
        "query_backend": "openfga" if openfga_source.enabled() else "superset" if superset_source.enabled() else "sqlite",
    }


# 演示入口允许操作者切换预定义身份；真实部署需要替换为可信认证后的映射。
@router.post("/session")
def session(body: Persona, request: Request, response: Response):
    token = auth.session(body.persona_id, request.cookies.get(auth.COOKIE))
    response.set_cookie(
        auth.COOKIE, token, max_age=8 * 3600, httponly=True, samesite="strict", secure=False, path="/"
    )
    return {"ok": True, "demo_only": True}


# 页面启动时一起取得身份、授权目录、数据版本和模型状态，避免先展示全量目录。
@router.get("/bootstrap")
async def bootstrap(p=Depends(auth.principal)):
    return {
        "principal": auth.public(p),
        "personas": store.PERSONAS,
        "catalog": registry.catalog(p),
        "model": await model_status(),
        "data_version": store.DATA_VERSION,
        "fingerprint": auth.fingerprint(p),
        "query_backend": "openfga" if openfga_source.enabled() else "superset" if superset_source.enabled() else "sqlite",
    }


# 结构化查询入口用于可视化编辑器；自然语言 chat 最终也经过同一个 run_query。
@router.post("/query")
def execute(body: Plan, p=Depends(checked)):
    return service.run_query(p, body)


@router.post("/verify")
def verify(body: Plan, p=Depends(checked)):
    return service.reconcile(p, body)


@router.post("/drill")
def drill(body: Drill, p=Depends(checked)):
    return service.run_query(p, service.drill_plan(p, body.plan, body.group, body.metric))


@router.post("/chat")
async def chat(body: Question, p=Depends(checked)):
    from .graph import answer

    return await answer(p, body)


@router.get("/history")
def history(p=Depends(auth.principal)):
    return service.history(p)


@router.get("/history/{rid}")
def read(rid: str, p=Depends(auth.principal)):
    return service.read_run(p, rid)


# 题单只供演示导航；模型运行图不根据问题编号查找标准答案。
@router.get("/cases")
def cases(p=Depends(auth.principal)):
    return json.loads((config.PROJECT / "evaluation/cases.json").read_text())


# 关系页也必须鉴权，不能为了画图额外读取未授权祖先/HRBP 的姓名。
@router.get("/relations")
def relations(p=Depends(auth.principal)):
    grant = auth.grants(p)
    if not auth.policy(p)["roles"][p["role"]]["details"]:
        raise HTTPException(403, "当前角色未开放人员明细")
    lookup = {r["person_id"]: r for r in auth.people(p)}
    rows = []
    for eid in grant["ids"]:
        person = lookup[eid]
        paths = []
        for origin in grant["origins"][eid]:
            paths.append({**origin, "names": [lookup[n]["name"] if n in lookup else "未授权路径节点"
                                               for n in origin["path"]]})
        rows.append(
            {
                **{k: person[k] for k in ("person_id", "employee_no", "name", "dept_cn_name")},
                "depth": grant["depths"].get(eid),
                "reasons": paths,
            }
        )
    return {"rows": rows, "policy_version": grant["policy_version"], "assumption": True}


# 这组配置 API 仅服务原 SQLite 演示；Superset 模式拒绝本地规则写入。
@router.get("/policy")
def policy(p=Depends(auth.principal)):
    if openfga_source.enabled():
        raise HTTPException(409, "OpenFGA 模式请配置模型/源策略并发布")
    if superset_source.enabled():
        raise HTTPException(409, "Superset 模式的配置入口在 Superset 与 PostgreSQL，本地规则编辑已停用")
    if p["id"] != "admin":
        raise HTTPException(403, "仅配置管理员可查看完整配置")
    return store.policy()


@router.post("/policy/preview")
def preview(body: auth.PolicyChange, p=Depends(checked)):
    candidate, changes = auth.policy_preview(p, body)
    return {"policy": candidate, "changes": changes}


@router.post("/policy/apply")
def apply(body: auth.PolicyChange, p=Depends(checked)):
    return auth.apply_policy(p, body)


# 导出不是另一个直连数据库通道：沿用查询编译、完整授权与前后指纹检查。
# 当前 export 开关只约束本应用；不会自动关闭 Superset 自带下载菜单。
@router.post("/export")
def export(body: Plan, p=Depends(checked)):
    if not auth.policy(p)["roles"][p["role"]]["export"]:
        raise HTTPException(403, "当前角色未开放导出")
    before = auth.fingerprint(p)
    result = query.execute(p, body)
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    keys = [c["key"] for c in result["columns"]]
    writer.writerow([c["label"] for c in result["columns"]])

    def safe(v):
        if v is None:
            return ""
        value = str(v)
        # CSV 打开到表格软件时，防止 =/+/-/@ 等被解释成公式；前导零工号也保留为文本。
        return (
            "'" + value
            if value.lstrip().startswith(("=", "+", "-", "@"))
            or value.startswith(("\t", "\r", "\n"))
            or (value.startswith("0") and value.isdigit())
            else value
        )

    for row in result["_all_rows"]:
        writer.writerow([safe(row.get(k)) for k in keys])
    auth.refresh(p)
    if before != auth.fingerprint(p):
        raise HTTPException(409, "导出期间权限或数据已变化")
    return Response(
        "\ufeff" + stream.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="hr-query.csv"'},
    )
