"""可复现最小真实协议调用；输出脱敏证据，不输出签名、密码或请求头。"""
import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.hr import store  # noqa: E402
from backend.hr import superset_mcp as m
from backend.hr import superset_source as source


async def run(persona):
    p = dict(next(p for p in store.PERSONAS if p['id'] == persona))
    async with m.protocol(m.token_for(p)) as session:
        initialized = await session.initialize()
        listed = await session.list_tools()
        proof = {'persona': persona, 'protocol': initialized.protocolVersion,
                 'server': initialized.serverInfo.model_dump(), 'tools': [t.name for t in listed.tools]}
        for name, request in [('list_datasets', {'select_columns': ['id', 'table_name'], 'page_size': 100,
                                                'use_cache': False, 'force_refresh': True}),
                              ('get_dataset_info', {'identifier': source.manifest()['datasets']['people_public']['id']})]:
            result = await session.call_tool(name, {'request': request})
            try:
                data = m.decode(result)
                proof[name] = data if name == 'list_datasets' else {
                    'id': data['id'], 'table_name': data['table_name'],
                    'columns': [c['column_name'] for c in data['columns']]}
            except Exception:
                proof[name] = {'error': True, 'content': [c.text[:1000] for c in result.content if c.type == 'text']}
        # 已保存图表的实际数据调用；仅输出集合摘要，不把合成人员明细灌入报告。
        chart_url = source.manifest()['datasets']['people_public']['urls']['chart']
        identifier = int(parse_qs(urlparse(chart_url).query)['slice_id'][0])
        data = m.decode(await session.call_tool('get_chart_data', {'request': {
            'identifier': identifier, 'force_refresh': True, 'use_cache': False}}))
        numbers = sorted(row['employee_no'] for row in data['data'])
        proof['get_chart_data'] = {'returned_rows': len(numbers),
            'employee_numbers_hash': hashlib.sha256(json.dumps(numbers).encode()).hexdigest(),
            'completeness': '这里只记录返回规模；完整性另与独立样本集合和 REST 对照验证'}
        print(json.dumps(proof, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--persona', choices=[p['id'] for p in store.PERSONAS], default='employee')
    asyncio.run(run(parser.parse_args().persona))
