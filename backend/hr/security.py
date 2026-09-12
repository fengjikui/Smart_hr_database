import hashlib
import secrets
import time
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException, Request

from . import config
from .db import application, business, rows

COOKIE_NAME='hr_session'
SESSION_SECONDS=8*3600


def get_principal(request: Request):
    token=request.cookies.get(COOKIE_NAME,'')
    with application() as db:
        row=db.execute('SELECT p.*,s.csrf FROM sessions s JOIN principals p ON p.id=s.principal_id WHERE s.token_hash=? AND s.expires_at>? AND p.enabled=1',(hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
    if not row:
        raise HTTPException(401,detail='请选择一个演示身份后继续。')
    return dict(row)


def require_csrf(request: Request, principal):
    if not secrets.compare_digest(request.headers.get('x-csrf-token',''),principal['csrf']):
        raise HTTPException(403,detail='请求校验失败，请刷新页面后重试。')


def create_session(persona_id: str, old_token: str | None = None):
    with application() as db:
        if not db.execute('SELECT 1 FROM principals WHERE id=? AND enabled=1',(persona_id,)).fetchone():
            raise HTTPException(404,detail='演示身份不可用。')
        if old_token:
            db.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256(old_token.encode()).hexdigest(),))
        db.execute('DELETE FROM sessions WHERE expires_at<?',(time.time(),))
        token=secrets.token_urlsafe(32)
        csrf=secrets.token_urlsafe(24)
        db.execute('INSERT INTO sessions VALUES (?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),persona_id,csrf,time.time()+SESSION_SECONDS))
    return token


def scope_ids(principal, relation='all'):
    with business() as db:
        if principal['scope_mode']=='reports':
            candidates=rows(db,'SELECT descendant_id,depth FROM reporting_closure WHERE ancestor_id=?',(principal['scope_root'],))
        elif principal['scope_mode']=='organization':
            candidates=rows(db,'SELECT a.employee_id AS descendant_id,-1 AS depth FROM assignments a JOIN departments d ON a.department_id=d.id WHERE a.valid_to IS NULL AND (d.division_id=? OR d.id=?)',(principal['scope_root'],principal['scope_root']))
        elif principal['scope_mode']=='self':
            candidates=[{'descendant_id':principal['employee_id'],'depth':0}]
        else:
            candidates=[]
        if relation=='self':
            return [principal['employee_id']] if any(r['descendant_id']==principal['employee_id'] for r in candidates) else []
        if relation!='all':
            personal=dict(db.execute('SELECT descendant_id,depth FROM reporting_closure WHERE ancestor_id=?',(principal['employee_id'],)))
            candidates=[r for r in candidates if (relation=='direct' and personal.get(r['descendant_id'])==1) or (relation=='indirect' and personal.get(r['descendant_id'],0)>=2) or (relation=='subordinates' and personal.get(r['descendant_id'],0)>0)]
    return sorted(r['descendant_id'] for r in candidates)


def public_principal(principal):
    ids=scope_ids(principal)
    with business() as db:
        snapshot=db.execute("SELECT value FROM dataset_meta WHERE key='as_of'").fetchone()[0]
        placeholders=','.join('?' for _ in ids) or 'NULL'
        active=db.execute(f'SELECT COUNT(*) FROM employees WHERE id IN ({placeholders}) AND hire_date<=? AND (termination_date IS NULL OR termination_date>?)',(*ids,snapshot,snapshot)).fetchone()[0]
        direct=scope_ids(principal,'direct')
        indirect=scope_ids(principal,'indirect')
        active_set={r[0] for r in db.execute('SELECT id FROM employees WHERE hire_date<=? AND (termination_date IS NULL OR termination_date>?)',(snapshot,snapshot))}
    return {**{k:principal[k] for k in ['id','employee_id','role','label','title','scope_mode','scope_root','policy_version']},'salary_aggregate':bool(principal['salary_aggregate']),'can_export':bool(principal['can_export']),'scope_count':active,'direct_count':len(set(direct)&active_set),'indirect_count':len(set(indirect)&active_set),'scope_label':'全公司授权范围' if principal['id']=='ceo' else '研发事业部服务范围' if principal['scope_mode']=='organization' else '本人及管理范围' if principal['scope_mode']=='reports' else '仅本人','csrf':principal['csrf']}


def audit(principal, action, outcome, metric_id=None, scope_count=None, duration_ms=0):
    with application() as db:
        db.execute('INSERT INTO audit_events VALUES (?,?,?,?,?,?,?,?,?)',(uuid4().hex,principal['id'],action,outcome,metric_id,scope_count,f'{config.POLICY_VERSION}:{principal["policy_version"]}',round(duration_ms,2),datetime.now(timezone.utc).isoformat()))
