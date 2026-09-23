"""分层真实验收：协议/权限→五种身份→20 Plan→HTTP/撤权；默认不调用模型。

必须经 lab.py run 执行。只用固定实验 Compose 运行可逆探针，每次改动 finally
精确恢复。报告只存结果哈希/状态，私有恢复快照放 .local，绝不操作课堂容器。
"""
import asyncio
import json
import os
import sys
import time
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
from fastapi import HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.hr import config, service, store  # noqa: E402
from backend.hr import superset_mcp as m
from backend.hr import superset_source as source
from backend.hr.api import _limits, app  # noqa: E402
from backend.hr.schema import Plan  # noqa: E402
from integrations.superset_mcp.lab import APPLICATION, LOCAL, PROJECT, compose, private_json  # noqa: E402
from scripts.validate_superset import Checks, digest, offline_oracle, persona, verify_direct  # noqa: E402


def require_isolated():
    if (os.getenv('HR_SUPERSET_URL') != 'http://127.0.0.1:18088'
            or os.getenv('HR_SUPERSET_DIR') != str(APPLICATION)
            or os.getenv('HR_QUERY_BACKEND') != 'superset_mcp'):
        raise SystemExit('拒绝非实验目标；请使用 lab.py run 启动验证。')


def remote(action, state=None, *, account=False):
    args = ['exec', '-T', 'superset', 'python', '/mcp-lab/account_probe.py' if account else '/lab/probe.py', action]
    if state is not None:
        args.append(json.dumps(state))
    result = compose(*args, capture=True)
    return json.loads(result.stdout.strip().splitlines()[-1])


def chart_id(level='public'):
    url = source.manifest()['datasets']['people_' + level]['urls']['chart']
    return int(parse_qs(urlparse(url).query)['slice_id'][0])


async def call(session, tool, request):
    return m.decode(await session.call_tool(tool, {'request': request}))


def signed(claims=None, secret=None):
    settings = json.loads((LOCAL / 'mcp-signing.json').read_text())
    payload = {'sub': 'v2_employee', 'iss': 'hr-mcp-lab', 'aud': 'superset-mcp',
               'exp': int(time.time()) + 120, 'scope': 'mcp:read'}
    payload.update(claims or {})
    return jwt.encode(payload, secret or settings['secret'], algorithm='HS256')


async def protocol_checks(checks, oracle, report):
    async def one(key):
        p = persona(key)
        async with m.protocol(m.token_for(p)) as session:
            initialized = await session.initialize()
            tools = await session.list_tools()
            names = [tool.name for tool in tools.tools]
            checks.equal(key + ' 初始化/发现', {'list_datasets', 'get_chart_data'} <= set(names), True)
            report['protocol'] = initialized.protocolVersion
            report['tools'] = names
            catalog = await call(session, 'list_datasets', {'page_size': 100, 'select_columns': ['id', 'table_name'],
                                                           'use_cache': False, 'force_refresh': True})
            contract = 'contract' in oracle['policy']['roles'][p['role']]['field_groups']
            expected_names = ['context', 'events_public', 'people_public']
            if contract:
                expected_names += ['events_contract', 'people_contract']
            checks.equal(key + ' MCP 目录范围', sorted(d['table_name'] for d in catalog['datasets']), sorted(expected_names))
            info = await call(session, 'get_dataset_info', {'identifier': source.manifest()['datasets']['people_public']['id']})
            checks.equal(key + ' 公共目录不含合同字段', any('contract' in c['column_name'] for c in info['columns']), False)
            result = await call(session, 'get_chart_data', {'identifier': chart_id(), 'force_refresh': True, 'use_cache': False})
            numbers = sorted(row['employee_no'] for row in result['data'])
            expected = sorted(row['employee_no'] for row in oracle['rows'] if row['person_id'] in oracle['identities'][key]['ids'])
            checks.equal(key + ' 官方 MCP 图表精确人员集合', numbers, expected,
                         evidence={'count': len(numbers), 'employee_numbers_hash': digest(numbers)})
            with source.session(p) as rest:
                rows = source._chart(rest, 'people_public', [source.raw_query(['employee_no'])])[0]['data']
            checks.equal(key + ' MCP 与同身份 REST 人员集合', numbers, sorted(row['employee_no'] for row in rows))
            requests = [
                ('execute_sql', {'database_id': 1, 'sql': 'SELECT 1', 'limit': 1}),
                ('create_virtual_dataset', {'database_id': 1, 'sql': 'SELECT 1', 'dataset_name': 'MCP_denied_probe'}),
                ('update_chart', {'identifier': chart_id(), 'chart_name': 'denied probe'}),
            ]
            if not contract:
                requests += [('get_dataset_info', {'identifier': source.manifest()['datasets']['people_contract']['id']}),
                             ('get_chart_data', {'identifier': chart_id('contract'), 'force_refresh': True})]
            for tool, request in requests:
                try:
                    await call(session, tool, request)
                except HTTPException:
                    checks.equal(key + ' 服务端拒绝 ' + tool, True, True)
                else:
                    checks.equal(key + ' 服务端拒绝 ' + tool, False, True)
            # 只读业务角色不能修改 RLS 或数据集；与工具列表是否展示分别记录。
            with source.session(p) as rest:
                checks.equal(key + ' REST 拒绝修改数据集', rest.put('/api/v1/dataset/1',
                    json={'description': 'denied probe'}).status_code in (401, 403), True)
                checks.equal(key + ' REST 拒绝修改 RLS', rest.put('/api/v1/rowlevelsecurity/1',
                    json={'clause': '1=1'}).status_code in (401, 403), True)
            return numbers

    for key in oracle['identities']:
        await one(key)
    # 两个长期独立协议会话交错；同时只有两个请求，无负载压测。
    async with m.protocol(m.token_for(persona('employee'))) as a, m.protocol(m.token_for(persona('hr_lead'))) as b:
        await a.initialize()
        await b.initialize()
        async def listing(s):
            r = await call(s, 'get_chart_data', {'identifier': chart_id(), 'force_refresh': True, 'use_cache': False})
            return sorted(row['employee_no'] for row in r['data'])
        x, y = await asyncio.gather(listing(a), listing(b))
        y2, x2 = await asyncio.gather(listing(b), listing(a))
        checks.equal('两身份交错不串结果', [x, y], [x2, y2])
        checks.equal('两身份授权集合确实不同', x != y, True)

    for name, token in [('missing', ''), ('invalid', 'invalid'), ('expired', signed({'exp': int(time.time()) - 10})),
                        ('wrong_signature', signed(secret='x' * 64)), ('wrong_audience', signed({'aud': 'other'})),
                        ('wrong_issuer', signed({'iss': 'other'})), ('missing_scope', signed({'scope': ''}))]:
        # 不打印 ExceptionGroup（可能含请求信息）；直接验证 HTTP 认证状态。
        async with httpx.AsyncClient(trust_env=False, timeout=5) as http:
            response = await http.post('http://127.0.0.1:15008/mcp', headers={
                **({'Authorization': 'Bearer ' + token} if token else {}), 'Accept': 'application/json, text/event-stream'},
                json={'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
                    'protocolVersion': '2025-11-25', 'capabilities': {}, 'clientInfo': {'name': 'probe', 'version': '1'}}})
        checks.equal(name + ' 凭据拒绝', response.status_code in (401, 403), True, evidence={'status': response.status_code})
    with source.session(persona('employee')) as rest:
        rest_token = rest.headers['Authorization'].removeprefix('Bearer ')
    async with httpx.AsyncClient(trust_env=False, timeout=5) as http:
        response = await http.post('http://127.0.0.1:15008/mcp', headers={
            'Authorization': 'Bearer ' + rest_token}, json={})
    checks.equal('REST token 不能用于 MCP', response.status_code, 401)
    for username in ['v2_missing_user', 'v2_unmapped']:
        async with m.protocol(signed({'sub': username})) as session:
            await session.initialize()
            raw = await session.call_tool('get_chart_data', {'request': {'identifier': chart_id(), 'force_refresh': True}})
            if username == 'v2_unmapped':
                # 官方 get_chart_data 将 RLS 后零行表达为 NoData；不能泛把所有错误当作空集。
                data = json.loads(raw.content[0].text)
                checks.equal('未映射账号官方图表明确 NoData', data.get('error_type'), 'NoData')
            else:
                checks.equal('未知 Superset 用户被拒绝', 'Unknown or inactive subject' in raw.content[0].text, True)


def http_and_revocation(checks):
    """覆盖新查询、核验、历史/调试、导出；探针仅修改实验，最终比较恢复快照。"""
    _limits.clear()
    with TestClient(app) as client:
        def login(key):
            client.post('/api/session', json={'persona_id': key}).raise_for_status()
            boot = client.get('/api/bootstrap')
            boot.raise_for_status()
            checks.equal(key + ' HTTP 明确标记混合路径', boot.json()['query_backend'], 'superset_mcp_catalog_rest_query')
            return {'X-CSRF-Token': boot.json()['principal']['csrf']}
        headers = login('hr_lead')
        checks.equal('实验 Cookie 独立', 'hr_mcp_session' in client.cookies and 'hr_session' not in client.cookies, True)
        checks.equal('前端 SQL 不进入工具', client.post('/api/query', headers=headers, json={'sql': 'SELECT 1'}).status_code, 422)
        plan = Plan()
        p = persona('hr_lead')
        saved = service.save_run(p, 'MCP 撤权验证', service.run_query(p, plan))
        state = remote('capture')
        private_json(LOCAL / 'probe-recovery.json', state)
        try:
            for action in ['narrow_rls', 'narrow_events', 'revoke_public', 'revoke_events']:
                try:
                    remote(action)
                    history = client.get('/api/history/' + saved['id'])
                    checks.equal(action + ' 历史/调试失效', history.status_code in (403, 404), True)
                    for route in ['query', 'verify', 'export']:
                        r = client.post('/api/' + route, headers=headers, json=plan.model_dump())
                        if action.startswith('revoke'):
                            checks.equal(action + ' ' + route + ' 拒绝', r.status_code, 403)
                        else:
                            checks.equal(action + ' ' + route + ' 成功且重新鉴权', r.status_code, 200)
                            if action == 'narrow_rls' and route != 'export':
                                checks.equal(action + ' ' + route + ' 仅剩一人', r.json()['totals']['count'], 1)
                            if action == 'narrow_rls' and route == 'export':
                                checks.equal('收窄 RLS 后导出不含旧分组', len(r.text.splitlines()), 2)
                    if action == 'narrow_events':
                        event_plan = Plan(population='all', date_field='employment_events',
                            start_date='2026-01-01', end_date=store.AS_OF, metrics=['hires', 'departures'])
                        r = client.post('/api/verify', headers=headers, json=event_plan.model_dump())
                        checks.equal('事件撤权后核验不重建旧事件', r.json()['totals'], {'hires': 0, 'departures': 0})
                        checks.equal('事件撤权后核验一致', r.json()['passed'], True)
                finally:
                    remote('restore', state)
            for key, action, expected in [('manager', 'manager_self', 200), ('employee', 'unmap_employee', 403),
                                           ('manager', 'cycle', 409), ('manager', 'orphan', 409)]:
                headers = login(key)
                saved2 = service.save_run(persona(key), action, service.run_query(persona(key), plan))
                try:
                    remote(action)
                    r = client.post('/api/query', headers=headers, json={})
                    checks.equal(action + ' 新查询', r.status_code, expected)
                    checks.equal(action + ' 历史/调试拒绝旧权限', client.get('/api/history/' + saved2['id']).status_code in (403, 404, 409), True)
                    if expected == 200:
                        checks.equal('主管权限收缩为本人', r.json()['totals']['count'], 1)
                finally:
                    remote('restore', state)
        finally:
            remote('restore', state)
        checks.equal('角色/映射/汇报线/RLS 精确恢复', remote('capture'), state)
        account_state = remote('capture', account=True)
        private_json(LOCAL / 'account-recovery.json', account_state)
        # 复用撤销前已签发的 JWT，证明服务端每次工具调用重新加载角色和 active。
        token = m.token_for(persona('employee'))
        async def check_old_token(action):
            async with m.protocol(token) as session:
                await session.initialize()
                raw = await session.call_tool('get_dataset_info', {'request': {
                    'identifier': source.manifest()['datasets']['people_public']['id']}})
                try:
                    m.decode(raw)
                except HTTPException:
                    checks.equal(action + ' 旧 JWT 不能保留旧权限', True, True)
                else:
                    checks.equal(action + ' 旧 JWT 不能保留旧权限', False, True)
        try:
            for action in ['revoke_role', 'disable']:
                remote(action, account=True)
                asyncio.run(check_old_token(action))
                remote('restore', account_state, account=True)
        finally:
            remote('restore', account_state, account=True)
        checks.equal('账号角色和启停状态精确恢复', remote('capture', account=True), account_state)
        headers = login('hr_lead')
        with patch.dict(os.environ, {'HR_SUPERSET_MCP_URL': 'http://127.0.0.1:1/mcp'}):
            for route, op in [('query', lambda: client.post('/api/query', headers=headers, json={})),
                              ('history', lambda: client.get('/api/history')),
                              ('verify', lambda: client.post('/api/verify', headers=headers, json={})),
                              ('export', lambda: client.post('/api/export', headers=headers, json={}))]:
                checks.equal('MCP 故障关闭 ' + route, op().status_code, 503)


def main():
    require_isolated()
    checks = Checks()
    report = {'tested_at': datetime.now(UTC).isoformat(), 'passed': False, 'checks': checks.items,
              'model_test': '未在本脚本运行；固定 Plan 不能冒充自然语言模型测试',
              'execution': 'MCP 目录 + 官方 MCP 已保存图表验权 + Agent REST Plan 查询'}
    target = PROJECT / 'reports/superset-mcp-validation.json'
    target.parent.mkdir(exist_ok=True)
    try:
        oracle = offline_oracle()
        report['structured_plans'] = list(oracle['plans'])
        asyncio.run(protocol_checks(checks, oracle, report))
        with TemporaryDirectory(prefix='hr-mcp-validation-') as directory, ExitStack() as stack:
            stack.enter_context(patch.object(config, 'APP_DB', Path(directory) / 'app.sqlite'))
            store.ensure()
            stack.enter_context(patch.object(store, 'people', side_effect=AssertionError('禁止在线读人员 SQLite')))
            verify_direct(checks, oracle)
            http_and_revocation(checks)
        report['passed'] = True
    finally:
        report['check_count'] = len(checks.items)
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({'passed': report['passed'], 'check_count': report['check_count']}))


if __name__ == '__main__':
    main()
