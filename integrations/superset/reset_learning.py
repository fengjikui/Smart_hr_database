"""把本项目演示恢复到待手工建库状态；不会重新导入。

默认只显示帮助。--apply 会先备份，再调用容器内事务删除固定清单中的对象。
备份包含数据库密码，必须保留在 Git 忽略的 data/backups 私有目录中。
此工具只用于本机课堂环境，不是生产数据库迁移工具。
"""
import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOCAL = ROOT / '.local' / 'application'
USERS = ['v2_hr_lead', 'v2_hrbp', 'v2_manager', 'v2_employee', 'v2_admin', 'v2_unmapped']
ROLES = ['V2_Data_public', 'V2_Data_contract', 'V2_Context', *['V2_Role_' + x for x in ['hr_lead', 'hrbp', 'manager', 'employee', 'admin']]]
CONNECTIONS = ['V2_public', 'V2_contract']
RLS = ['V2_scope_public', 'V2_scope_contract', 'V2_context_scope', 'V2_PROBE_public_events_deny']


def clear_metadata():
    """容器内执行。显式白名单；任何未知外键依赖导致整笔事务回滚。"""
    from sqlalchemy import inspect, text
    from superset.app import create_app
    with create_app().app_context():
        from superset import db
        from superset import security_manager as sm
        from superset.connectors.sqla.models import RowLevelSecurityFilter, SqlaTable
        from superset.models.core import Database
        from superset.models.dashboard import Dashboard
        from superset.models.slice import Slice
        admin = sm.find_user(username='v2_setup_admin')
        assert admin and any(r.name == 'Admin' for r in admin.roles), '必须保留技术管理员'
        databases = db.session.query(Database).filter(Database.database_name.in_(CONNECTIONS)).all()
        datasets = db.session.query(SqlaTable).filter(SqlaTable.database_id.in_([d.id for d in databases])).all()
        users = [sm.find_user(username=n) for n in USERS]
        user_ids = [u.id for u in users if u]
        roles = [sm.find_role(n) for n in ROLES]
        filters = db.session.query(RowLevelSecurityFilter).filter(RowLevelSecurityFilter.name.in_(RLS)).all()
        charts = db.session.query(Slice).filter(Slice.datasource_type == 'table', Slice.datasource_id.in_([t.id for t in datasets])).all()
        dashboards = db.session.query(Dashboard).filter(Dashboard.slug.in_(['v2-people-public', 'v2-people-contract'])).all()
        result = dict(databases=len(databases), datasets=len(datasets), users=len(user_ids), roles=sum(r is not None for r in roles), rls=len(filters), charts=len(charts), dashboards=len(dashboards))
        # SQL Lab 查询记录/页签引用数据库；只清理待删除连接的记录。
        for database in databases:
            for table, column in [('query', 'database_id'), ('saved_query', 'db_id'), ('tab_state', 'database_id'), ('table_schema', 'database_id')]:
                db.session.execute(text(f'DELETE FROM "{table}" WHERE "{column}" = :id'), {'id': database.id})
        for group in [dashboards, charts, filters, datasets, databases]:
            for obj in group:
                db.session.delete(obj)
            db.session.flush()
        # 审计日志保留，已删除业务账号的可空引用置空；关联表由数据库 CASCADE 清理。
        # 不猜测非空引用的处置方式：遇到未知依赖停止，避免波及其他课堂配置。
        inspector = inspect(db.engine)
        for table in inspector.get_table_names():
            columns = {c['name']: c for c in inspector.get_columns(table)}
            for fk in inspector.get_foreign_keys(table):
                if fk['referred_table'] != 'ab_user' or len(fk['constrained_columns']) != 1:
                    continue
                column = fk['constrained_columns'][0]
                if columns[column]['nullable']:
                    for uid in user_ids:
                        db.session.execute(text(f'UPDATE "{table}" SET "{column}" = NULL WHERE "{column}" = :id'), {'id': uid})
        for user in users:
            if user:
                db.session.delete(user)
        for role in roles:
            if role:
                db.session.delete(role)
        db.session.commit()
        print(json.dumps(result))


def reset():
    """宿主机备份与编排。先完成可读性检查，最后才删除数据库。"""
    repo = ROOT.parents[1]
    env = dict(os.environ, DOCKER_HOST=os.getenv('HR_DOCKER_HOST', f'unix://{Path.home()}/.colima/hr-superset/docker.sock'))
    pg = ['docker', 'exec', 'hr-superset-lab-postgres-1']
    ss = ['docker', 'exec', 'hr-superset-lab-superset-1']
    def run(args, **kw):
        return subprocess.run(args, env=env, check=True, **kw)
    # 防止旧工作台继续产生结果/历史。只检查，不擅自杀其他人的进程。
    import socket
    for port in (3000, 8000):
        with socket.socket() as sock:
            if sock.connect_ex(('127.0.0.1', port)) == 0:
                raise SystemExit(f'请先停止本项目工作台（端口 {port} 仍在运行）')
    backup = repo / 'data' / 'backups' / ('manual-learning-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
    backup.mkdir(parents=True, mode=0o700)
    os.chmod(backup, 0o700)
    for name in ('superset_meta', 'hr_v2'):
        path = backup / (name + '.dump')
        with path.open('wb') as output:
            run([*pg, 'pg_dump', '-U', 'postgres', '-Fc', name], stdout=output)
        os.chmod(path, 0o600)
        # 将备份送入 pg_restore 仅列目录，验证归档可解析；不恢复，不改库。
        with path.open('rb') as source:
            listing = run(['docker', 'exec', '-i', 'hr-superset-lab-postgres-1', 'pg_restore', '--list'], stdin=source, capture_output=True)
        assert b'TABLE' in listing.stdout, '数据库备份未包含表'
    with (backup / 'roles.sql').open('wb') as output:
        run([*pg, 'pg_dumpall', '-U', 'postgres', '--roles-only'], stdout=output)
    shutil.copy2(ROOT / '.local' / 'lab.env', backup / 'lab.env')
    shutil.copytree(LOCAL, backup / 'application')
    for name in ('people.sqlite', 'sessions.sqlite'):
        source = repo / 'data' / name
        if source.exists():
            with sqlite3.connect(source) as a, sqlite3.connect(backup / name) as b:
                a.backup(b)
                assert b.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    for path in backup.rglob('*'):
        os.chmod(path, 0o700 if path.is_dir() else 0o600)
    hashes = {str(p.relative_to(backup)): hashlib.sha256(p.read_bytes()).hexdigest() for p in backup.rglob('*') if p.is_file()}
    (backup / 'sha256.json').write_text(json.dumps(hashes, indent=2))
    # 标记在删除前写入；失败也禁止自动 setup，供人工检查/恢复。
    from initialization_guard import stamp_fixture_guard
    stamp_fixture_guard(LOCAL)
    marker = LOCAL / 'manual-learning.json'
    marker.write_text(json.dumps({'backup': str(backup), 'state': 'resetting'}, indent=2))
    result = run([*ss, 'python', '/lab/reset_learning.py', '--inside'], capture_output=True, text=True)
    # Superset 输出可能包含启动日志，只展示末行的对象计数。
    removed = json.loads(result.stdout.strip().splitlines()[-1])
    run([*pg, 'psql', '-U', 'postgres', '-d', 'postgres', '-v', 'ON_ERROR_STOP=1', '-c', 'DROP DATABASE hr_v2 WITH (FORCE);'], capture_output=True)
    run([*pg, 'psql', '-U', 'postgres', '-d', 'postgres', '-v', 'ON_ERROR_STOP=1', '-c', 'DROP ROLE v2_public_reader; DROP ROLE v2_contract_reader;'], capture_output=True)
    # 删除过期对象 ID/账号；保留技术管理员登录资料及合成样本，供后续手工导入。
    credentials_path = LOCAL / 'credentials.json'
    credentials = json.loads(credentials_path.read_text())
    credentials_path.write_text(json.dumps({'v2_setup_admin': credentials['v2_setup_admin']}, indent=2))
    for name in ('manifest.json', 'database-credentials.json'):
        (LOCAL / name).unlink(missing_ok=True)
    # 历史保留在私有备份内；目标路径不删除，避免旧版迁移工具又复制旧会话。
    app_db = repo / 'data' / 'sessions.sqlite'
    if app_db.exists():
        with sqlite3.connect(app_db) as conn:
            for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall():
                conn.execute('DELETE FROM "' + table.replace('"', '""') + '"')
    marker.write_text(json.dumps({'backup': str(backup), 'state': 'ready', 'removed': removed}, ensure_ascii=False, indent=2))
    print(json.dumps({'backup': str(backup), 'removed': removed}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--apply', action='store_true', help='备份后清空当前 HR 演示，不影响 hr_lab')
    group.add_argument('--inside', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    clear_metadata() if args.inside else reset()
