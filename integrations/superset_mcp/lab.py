"""独立实验唯一宿主入口：固定项目/端口/状态，拒绝误用课堂 Compose。"""
import argparse
import hashlib
import hmac
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[1]
LOCAL = ROOT / '.local'
APPLICATION = LOCAL / 'application'
PORTS = {'web': 18088, 'postgres': 55434, 'mcp': 15008, 'api': 18000}


def private_json(path, value):
    """秘密落盘 0600；报告与清单不包含 token，也不复制课堂凭据。"""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, 'w') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)


def environment():
    """覆盖可能从课堂 shell 继承的路径；子进程只访问实验应用历史和样本。"""
    return dict(os.environ, DOCKER_HOST=os.getenv('HR_DOCKER_HOST',
        f'unix://{Path.home()}/.colima/hr-superset/docker.sock'), COMPOSE_PARALLEL_LIMIT='1',
        HR_QUERY_BACKEND='superset_mcp', HR_SUPERSET_URL='http://127.0.0.1:18088',
        HR_SUPERSET_MCP_URL='http://127.0.0.1:15008/mcp', HR_SUPERSET_DIR=str(APPLICATION),
        HR_DATA_DIR=str(LOCAL / 'app'), HR_MCP_SIGNING_FILE=str(LOCAL / 'mcp-signing.json'),
        OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', UV_CONCURRENT_BUILDS='1')


def compose(*args, capture=False):
    """每次显式指定项目和文件；不依赖当前目录或全局 docker context。"""
    cli = ['docker-compose'] if shutil.which('docker-compose') else ['docker', 'compose']
    return subprocess.run([*cli, '-p', 'hr-superset-mcp', '-f', str(ROOT / 'compose.yaml'), *args],
        env=environment(), cwd=PROJECT, text=True, check=True, capture_output=capture)


def targets():
    print(json.dumps({'project': 'hr-superset-mcp', 'ports': PORTS,
        'state': 'integrations/superset_mcp/.local', 'volume': 'hr-superset-mcp_postgres-data',
        'network': 'hr-superset-mcp_default', 'base_commit': 'd2b3bc6'}, ensure_ascii=False), flush=True, file=sys.stderr)


def load_check():
    """构建/启动前记录可取得的热状态；没有温度读数时不编造温度。"""
    for command in [['uptime'], ['memory_pressure'], ['pmset', '-g', 'therm']]:
        if shutil.which(command[0]):
            subprocess.run(command, check=False)


def prepare():
    if (APPLICATION / 'manual-learning.json').exists():
        raise SystemExit('实验存在学习保护标记，拒绝自动初始化。')
    LOCAL.mkdir(mode=0o700, exist_ok=True)
    LOCAL.chmod(0o700)
    APPLICATION.mkdir(exist_ok=True)
    path = LOCAL / 'lab.env'
    if not path.exists():
        values = {key: secrets.token_hex(32) for key in ['POSTGRES_PASSWORD', 'META_PASSWORD',
            'SUPERSET_SECRET_KEY', 'LAB_DEMO_SEED', 'MCP_JWT_SECRET']}
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as handle:
            handle.write(''.join(f'{key}={value}\n' for key, value in values.items()))
    values = dict(line.split('=', 1) for line in path.read_text().splitlines())
    private_json(LOCAL / 'mcp-signing.json', {'secret': values['MCP_JWT_SECRET']})
    # 在导入 store/config 之前设置路径，保证首次样本和历史均不碰课堂工作区。
    os.environ.update(environment())
    sys.path.insert(0, str(PROJECT))
    from integrations.superset.export import snapshot
    fixture = snapshot()
    fixture['manual_learning'] = False
    (APPLICATION / 'fixtures.json').write_text(json.dumps(fixture, ensure_ascii=False))
    (APPLICATION / 'fixtures.json').chmod(0o644)
    names = ['v2_setup_admin', 'v2_unmapped', *['v2_' + p['id'] for p in fixture['personas']]]
    private_json(APPLICATION / 'credentials.json', {name: hmac.new(values['LAB_DEMO_SEED'].encode(),
        name.encode(), hashlib.sha256).hexdigest()[:24] for name in names})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['targets', 'prepare', 'build', 'up', 'bootstrap', 'status',
        'stop', 'start', 'restart', 'logs', 'run'])
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    targets()
    if args.action == 'targets':
        return
    if args.action == 'prepare':
        prepare()
    elif args.action == 'build':
        load_check()
        compose('build', 'superset')
    elif args.action == 'up':
        load_check()
        # 已有实验容器允许幂等 up；首次部署确认端口未被其他项目占用。
        existing = compose('ps', '-a', '-q', capture=True).stdout.strip()
        if not existing:
            for port in list(PORTS.values())[:3]:
                with socket.socket() as sock:
                    sock.bind(('127.0.0.1', port))
        compose('up', '-d', '--no-build')
    elif args.action == 'bootstrap':
        output = compose('exec', '-T', 'superset', 'python', '/mcp-lab/bootstrap.py', capture=True)
        value = json.loads(output.stdout.strip().splitlines()[-1])
        private_json(APPLICATION / 'manifest.json', value)
        print(f"实验就绪：{value['row_count']} 人、{len(value['principals'])} 个业务身份。")
    elif args.action == 'status':
        compose('ps', '-a')
    elif args.action == 'logs':
        compose('logs', '--tail', '60', 'mcp')
    elif args.action in {'start', 'restart'}:
        compose(args.action, 'postgres', 'superset', 'mcp')
    elif args.action == 'stop':
        compose('stop')
    elif args.action == 'run':
        # 命令参数不经过 shell；调用者仍需用受控脚本，不从自然语言构造命令。
        if not args.command:
            parser.error('run 后需要命令，例如 uv run uvicorn backend.hr.api:app --port 18000')
        subprocess.run(args.command, cwd=PROJECT, env=environment(), check=True)


if __name__ == '__main__':
    main()
