"""少量真实自然语言链路：实际调用已加载 LM Studio 模型，不替换计划器。

验证前后检查负载；只串行运行两个问题。历史放临时文件，结果保存脱敏报告。
若模型未加载则明确报告未测，绝不把固定 Plan 结果冒充模型生成。
"""
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.hr import config, reference, store  # noqa: E402
from backend.hr.api import _limits, app  # noqa: E402
from backend.hr.schema import Plan  # noqa: E402
from integrations.superset_mcp.lab import PROJECT, load_check  # noqa: E402
from integrations.superset_mcp.validate import persona, require_isolated  # noqa: E402


def main():
    require_isolated()
    load_check()
    report = {'tested_at': datetime.now(UTC).isoformat(), 'model': config.MODEL_ID,
              'mocked_planner': False, 'passed': False, 'cases': []}
    target = PROJECT / 'reports/superset-mcp-model.json'
    try:
        with httpx.Client(trust_env=False, timeout=5) as http:
            models = http.get(config.MODEL_URL + '/models').json()['data']
        if config.MODEL_ID not in {model['id'] for model in models}:
            report['status'] = 'not_tested_model_unavailable'
            raise SystemExit('目标模型未加载；不自动重启/替换其他会话的模型。')
        rows, policy = store.people(), store.policy()
        questions = [
            ('employee', '我能看到多少在职人员？', Plan()),
            ('hr_lead', '我能看到的在职人员按部门分别有多少？请给出合计。', Plan(group_by=['dept_cn_name'])),
        ]
        with TemporaryDirectory(prefix='hr-mcp-model-') as directory, patch.object(
                config, 'APP_DB', Path(directory) / 'app.sqlite'), TestClient(app) as client:
            store.ensure()
            for key, question, expected_plan in questions:
                load_check()
                _limits.clear()
                client.post('/api/session', json={'persona_id': key}).raise_for_status()
                boot = client.get('/api/bootstrap')
                boot.raise_for_status()
                headers = {'X-CSRF-Token': boot.json()['principal']['csrf']}
                response = client.post('/api/chat', headers=headers, json={'question': question})
                response.raise_for_status()
                data = response.json()
                p = persona(key)
                expected = reference.calculate(p, expected_plan, source=rows,
                    scope=reference.independent_scope(p, expected_plan, rows, policy))
                stages = [node for node in data.get('trace', []) if 'MCP' in node['name']]
                # 同时比较分组行与合计；只比较 count 会漏掉模型丢失“按部门”等条件。
                passed = data['status'] == 'success' and data['totals'] == expected['totals'] and data['rows'] == expected['rows'] and bool(stages)
                report['cases'].append({'persona': key, 'question': question, 'passed': passed,
                    'status': data['status'], 'summary': data.get('summary', data.get('message')),
                    'plan': data.get('plan'), 'totals': data.get('totals'), 'mcp_stages': stages,
                    'execution_backend': data.get('execution_backend'),
                    'model_trace': [node for node in data.get('trace', []) if '模型' in node['name'] or '规则补齐' in node['name']]})
                print(json.dumps({'persona': key, 'passed': passed, 'summary': data.get('summary')}, ensure_ascii=False), flush=True)
                if not passed:
                    raise AssertionError('真实模型计划/执行结果与问题期望不一致')
        report['passed'] = True
        report['status'] = 'tested_live_model'
    finally:
        load_check()
        target.parent.mkdir(exist_ok=True)
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
