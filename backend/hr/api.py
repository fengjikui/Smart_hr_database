import asyncio
import csv
import io
import json
import os
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import config
from .agent import answer, model_status
from .catalog import catalog, search
from .db import application, business, rows
from .models import DashboardRequest, PersonaRequest, QueryPlan, QuestionRequest
from .query import execute
from .security import COOKIE_NAME, SESSION_SECONDS, audit, create_session, get_principal, public_principal, require_csrf, scope_ids
from .seed import PERSONAS, generate
from .validate import validate


@asynccontextmanager
async def lifespan(app):
    if os.getenv('HR_MODE','demo')!='demo':
        raise RuntimeError('当前交付是回环地址演示版。生产 SSO 和数据库隔离尚需按部署文档接入。')
    if not config.BUSINESS_DB.exists() or not config.APP_DB.exists():
        generate()
    yield


app=FastAPI(title='澄观 HR Intelligence',version='0.1.0',lifespan=lifespan,docs_url='/api/docs',openapi_url='/api/openapi.json')
app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost','testserver'])
_limits=defaultdict(deque)
ALLOWED_ORIGINS={'http://127.0.0.1:3000','http://localhost:3000','http://127.0.0.1:8000','http://localhost:8000','http://testserver'}


@app.middleware('http')
async def boundaries(request: Request,call_next):
    origin=request.headers.get('origin')
    if origin and origin not in ALLOWED_ORIGINS:
        return JSONResponse({'detail':'来源不受信任。'},status_code=403)
    if request.headers.get('sec-fetch-site')=='cross-site':
        return JSONResponse({'detail':'不接受跨站请求。'},status_code=403)
    try:
        if int(request.headers.get('content-length','0'))>8192:
            return JSONResponse({'detail':'请求体超过大小限制。'},status_code=413)
    except ValueError:
        return JSONResponse({'detail':'无效请求。'},status_code=400)
    key=(request.cookies.get(COOKIE_NAME,'anonymous'),request.url.path=='/api/chat')
    now=time.monotonic()
    queue=_limits[key]
    while queue and queue[0]<now-60:
        queue.popleft()
    if len(queue)>=(12 if key[1] else 180):
        return JSONResponse({'detail':'请求过于频繁，请稍后重试。'},status_code=429,headers={'Retry-After':'60'})
    queue.append(now)
    if len(_limits)>1000:
        for old in list(_limits)[:500]:
            if old!=key:
                del _limits[old]
    response=await call_next(request)
    response.headers['Cache-Control']='no-store, private'
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['X-Frame-Options']='DENY'
    return response


@app.get('/api/health')
async def health():
    return {'status':'ok','mode':'local-demo','synthetic':True}


@app.get('/api/demo/personas')
def personas():
    return {'personas':[{k:p[k] for k in ['id','label','title','role']} for p in PERSONAS],'demo_only':True}


@app.post('/api/demo/session')
def session(body: PersonaRequest,request: Request,response: Response):
    # This endpoint deliberately permits role switching ONLY in loopback demo mode.
    token=create_session(body.persona_id,request.cookies.get(COOKIE_NAME))
    response.set_cookie(COOKIE_NAME,token,max_age=SESSION_SECONDS,httponly=True,samesite='strict',secure=False,path='/')
    return {'ok':True,'demo_only':True}


@app.get('/api/bootstrap')
async def bootstrap(principal=Depends(get_principal)):
    with business() as db:
        metadata=dict(db.execute('SELECT key,value FROM dataset_meta'))
    return {'principal':await asyncio.to_thread(public_principal,principal),'model':await model_status(),'dataset':{'as_of':metadata['as_of'],'calendar_start':metadata['calendar_start'],'synthetic':True},'catalog_version':catalog()['version'],'personas':personas()['personas']}


@app.get('/api/model')
async def model(principal=Depends(get_principal)):
    return await model_status()


@app.get('/api/overview')
def overview(principal=Depends(get_principal)):
    definitions=[('headcount','none','as_of'),('attendance_rate','none','this_month'),('approved_overtime_hours','none','this_month'),('abnormal_count','none','this_month'),('headcount','division','as_of'),('headcount','month','last_6_months'),('late_count','day','this_month')]
    answers=[execute(principal,QueryPlan(metric=m,dimension=d,period=p),record_audit=False) for m,d,p in definitions]
    return {'kpis':answers[:4],'distribution':answers[4],'trend':answers[5],'attendance_trend':answers[6]}


@app.post('/api/query')
def query(plan: QueryPlan,request: Request,principal=Depends(get_principal)):
    require_csrf(request,principal)
    return execute(principal,plan)


@app.post('/api/chat')
async def chat(body: QuestionRequest,request: Request,principal=Depends(get_principal)):
    require_csrf(request,principal)
    return await answer(principal,body.question,body.previous_id)


@app.get('/api/catalog')
def get_catalog(q: str=Query(default='',max_length=80),principal=Depends(get_principal)):
    return {'metrics':search(principal,q),'version':catalog()['version'],'storage':'Git 版本化 JSON → SQLite 指标目录 + FTS5 派生索引'}


@app.get('/api/organization')
def organization(principal=Depends(get_principal)):
    ids=scope_ids(principal)
    marks=','.join('?' for _ in ids) or 'NULL'
    with business() as db:
        snapshot=db.execute("SELECT value FROM dataset_meta WHERE key='as_of'").fetchone()[0]
        depts=rows(db,'SELECT id,name,parent_id,level,division_id FROM departments')
        assigned=rows(db,f'SELECT a.department_id,COUNT(*) AS count FROM assignments a JOIN employees e ON e.id=a.employee_id WHERE a.valid_to IS NULL AND e.id IN ({marks}) AND e.hire_date<=? AND (e.termination_date IS NULL OR e.termination_date>?) GROUP BY a.department_id',(*ids,snapshot,snapshot))
        own={r['department_id']:r['count'] for r in assigned}
        parents={d['id']:d['parent_id'] for d in depts}
        totals={d['id']:own.get(d['id'],0) for d in depts}
        for d in sorted(depts,key=lambda d:d['level'],reverse=True):
            if d['parent_id']:
                totals[d['parent_id']]+=totals[d['id']]
        visible=[{**d,'direct_employees':own.get(d['id'],0),'count':totals[d['id']]} for d in depts if totals[d['id']]>0]
    people=execute(principal,QueryPlan(kind='people',period='as_of',limit=100),record_audit=False)
    return {'departments':visible,'people':people,'principal':public_principal(principal)}


@app.get('/api/dashboards')
def dashboards(principal=Depends(get_principal)):
    with application() as db:
        cards=rows(db,'SELECT id,title,plan,catalog_version,created_at FROM dashboards WHERE owner_id=? ORDER BY created_at DESC',(principal['id'],))
    output=[]
    for card in cards:
        try:
            if card['catalog_version']!=config.CATALOG_VERSION:
                raise HTTPException(409,detail='指标目录已更新，请重新保存看板。')
            plan=QueryPlan.model_validate_json(card['plan'])
            result=execute(principal,plan,record_audit=False)
            output.append({**card,'plan':plan.model_dump(),'result':result})
        except HTTPException as exc:
            output.append({**card,'plan':None,'result':None,'error':exc.detail})
    return {'dashboards':output}


@app.post('/api/dashboards',status_code=201)
def save_dashboard(body: DashboardRequest,request: Request,principal=Depends(get_principal)):
    require_csrf(request,principal)
    if body.plan.kind!='metric':
        raise HTTPException(422,detail='个人看板仅保存汇总指标，明细不持久化为看板。')
    execute(principal,body.plan,record_audit=False)
    ident=uuid4().hex
    with application() as db:
        count=db.execute('SELECT COUNT(*) FROM dashboards WHERE owner_id=?',(principal['id'],)).fetchone()[0]
        if count>=20:
            raise HTTPException(422,detail='最多保存 20 个看板指标，请先移除不再使用的项目。')
        db.execute('INSERT INTO dashboards VALUES (?,?,?,?,?,?)',(ident,principal['id'],body.title,json.dumps(body.plan.model_dump(),ensure_ascii=False),config.CATALOG_VERSION,datetime.now(timezone.utc).isoformat()))
    audit(principal,'dashboard.save','allowed',body.plan.metric)
    return {'id':ident,'title':body.title}


@app.delete('/api/dashboards/{dashboard_id}')
def delete_dashboard(dashboard_id: str,request: Request,principal=Depends(get_principal)):
    require_csrf(request,principal)
    with application() as db:
        count=db.execute('DELETE FROM dashboards WHERE id=? AND owner_id=?',(dashboard_id,principal['id'])).rowcount
    if not count:
        raise HTTPException(404,detail='看板不存在或不可访问。')
    audit(principal,'dashboard.delete','allowed')
    return {'ok':True}


@app.post('/api/export')
def export(plan: QueryPlan,request: Request,principal=Depends(get_principal)):
    require_csrf(request,principal)
    if not principal['can_export'] or plan.metric=='avg_salary':
        audit(principal,'export','denied',plan.metric)
        raise HTTPException(403,detail='当前身份或该指标没有导出权限。')
    result=execute(principal,plan)
    output=io.StringIO()
    writer=csv.writer(output)
    writer.writerow([c['label'] for c in result['columns']])
    for row in result['rows']:
        values=[]
        for c in result['columns']:
            value=str(row.get(c['key'],'') or '')
            if value.startswith(('=','+','-','@','\t','\r')):
                value="'"+value
            values.append(value)
        writer.writerow(values)
    audit(principal,'export','allowed',plan.metric,result['scope']['count'])
    return Response('\ufeff'+output.getvalue(),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename="chengguan-hr.csv"'})


@app.get('/api/governance')
def governance(principal=Depends(get_principal)):
    if principal['role']!='executive':
        raise HTTPException(403,detail='数据治理总览仅对演示公司负责人开放。')
    report=validate()
    with application() as db:
        events=rows(db,'SELECT action,outcome,metric_id,scope_count,policy_version,duration_ms,created_at FROM audit_events WHERE principal_id=? ORDER BY created_at DESC LIMIT 30',(principal['id'],))
    return {'validation':report,'audit':events,'storage':{'business':'SQLite 只读业务库（21 张关系表）','application':'独立 SQLite 应用库：身份、会话、指标、看板与审计','semantics':'Git JSON 源文件 + 运行目录 + FTS5 派生索引','vectors':'未启用；当前目录规模不需要向量数据库'},'boundaries':['演示身份切换仅适用于本机回环部署','模型仅接收指标和获准组织元数据，不接收人员明细','所有查询使用类型计划、服务端权限注入与数据库只读检查','生产需接入 SSO、PostgreSQL RLS、集中审计及部署审批']}
