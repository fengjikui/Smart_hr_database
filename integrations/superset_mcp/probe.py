"""可复现最小真实协议调用；输出脱敏证据，不输出签名、密码或请求头。"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

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
        print(json.dumps(proof, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--persona', choices=[p['id'] for p in store.PERSONAS], default='employee')
    asyncio.run(run(parser.parse_args().persona))
