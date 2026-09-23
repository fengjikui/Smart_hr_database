"""只在实验容器中撤销账号角色/停用账号；宿主验证器负责 finally 精确恢复。"""
import json
import os
import sys

from superset.app import create_app


def main(action, state):
    if os.getenv('SUPERSET_CONFIG_PATH') != '/mcp-lab/superset_config.py':
        raise RuntimeError('拒绝非 MCP 实验容器')
    from superset import db
    from superset import security_manager as sm
    user = sm.find_user(username='v2_employee')
    if action == 'capture':
        result = {'role_ids': sorted(role.id for role in user.roles), 'active': user.active}
    elif action == 'revoke_role':
        user.roles = [role for role in user.roles if role.name != 'V2_Data_public']
        db.session.commit()
        result = {'changed': 'employee_role_membership'}
    elif action == 'disable':
        user.active = False
        db.session.commit()
        result = {'changed': 'employee_active'}
    elif action == 'restore':
        from flask_appbuilder.security.sqla.models import Role
        user.roles = db.session.query(Role).filter(Role.id.in_(state['role_ids'])).all()
        user.active = state['active']
        db.session.commit()
        result = {'restored': True}
    else:
        raise ValueError('未知探针动作')
    print(json.dumps(result))


if __name__ == '__main__':
    with create_app().app_context():
        main(sys.argv[1], json.loads(sys.argv[2]) if len(sys.argv) > 2 else {})
