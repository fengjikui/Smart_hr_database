import csv
import io
import json

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import Field

from .. import config
from ..agent import model_status
from . import auth, query, registry, service, store
from .schema import Plan, Question, Strict

router = APIRouter(prefix="/api/v2", tags=["HR Demo V2"])


class Persona(Strict):
    persona_id: str = Field(max_length=30)


class Drill(Strict):
    plan: Plan
    group: dict[str, str]
    metric: str = Field(max_length=50)


def checked(request: Request, p=Depends(auth.principal)):
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
    }


@router.post("/session")
def session(body: Persona, request: Request, response: Response):
    token = auth.session(body.persona_id, request.cookies.get(auth.COOKIE))
    response.set_cookie(
        auth.COOKIE, token, max_age=8 * 3600, httponly=True, samesite="strict", secure=False, path="/"
    )
    return {"ok": True, "demo_only": True}


@router.get("/bootstrap")
async def bootstrap(p=Depends(auth.principal)):
    return {
        "principal": auth.public(p),
        "personas": store.PERSONAS,
        "catalog": registry.catalog(p),
        "model": await model_status(),
        "data_version": store.DATA_VERSION,
        "fingerprint": auth.fingerprint(p),
    }


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


@router.get("/cases")
def cases(p=Depends(auth.principal)):
    return json.loads((config.PROJECT / "evaluation/demo-v2-cases.json").read_text())


@router.get("/relations")
def relations(p=Depends(auth.principal)):
    grant = auth.grants(p)
    if not store.policy()["roles"][p["role"]]["details"]:
        raise HTTPException(403, "当前角色未开放人员明细")
    lookup = {r["person_id"]: r for r in store.people()}
    rows = []
    for eid in grant["ids"]:
        person = lookup[eid]
        paths = []
        for origin in grant["origins"][eid]:
            paths.append({**origin, "names": [lookup[n]["name"] for n in origin["path"]]})
        rows.append(
            {
                **{k: person[k] for k in ("person_id", "employee_no", "name", "dept_cn_name")},
                "depth": grant["depths"].get(eid),
                "reasons": paths,
            }
        )
    return {"rows": rows, "policy_version": grant["policy_version"], "assumption": True}


@router.get("/policy")
def policy(p=Depends(auth.principal)):
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


@router.post("/export")
def export(body: Plan, p=Depends(checked)):
    if not store.policy()["roles"][p["role"]]["export"]:
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
        # CSV is text; prevent spreadsheet formula injection including leading whitespace.
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
