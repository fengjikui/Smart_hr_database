"""仅供自动验收的可逆故障探针；只允许修改本次创建的 V2 对象。

宿主机验证程序先 capture，最后必须 restore。这里不是对业务开放的 API。
不会访问此前 HR_LAB/LEARN 角色或课堂数据库。
"""

import json
import sys

from psycopg2.extras import Json
from setup import pg
from superset.app import create_app

EVENT_PROBE_NAME = "V2_PROBE_public_events_deny"


def main(action, value):
    from superset import db
    from superset import security_manager as sm
    from superset.connectors.sqla.models import RowLevelSecurityFilter, SqlaTable

    role = sm.find_role("V2_Data_public")
    rls = db.session.query(RowLevelSecurityFilter).filter_by(name="V2_scope_public").one()
    event_table = db.session.query(SqlaTable).filter_by(schema="v2_api", table_name="events_public").one()
    conn = pg()
    try:
        with conn, conn.cursor() as cur:
            if action == "capture":
                if db.session.query(RowLevelSecurityFilter).filter_by(name=EVENT_PROBE_NAME).first():
                    raise ValueError("上次事件探针尚未恢复，请先使用 probe-recovery.json 恢复，拒绝覆盖现场")
                cur.execute("SELECT reports,version FROM v2_auth.role_policy WHERE role_key='manager'")
                reports, version = cur.fetchone()
                cur.execute("SELECT head_person_id FROM v2_data.people WHERE person_id='P0004'")
                manager = cur.fetchone()[0]
                cur.execute("SELECT row_to_json(i) FROM v2_auth.identity_map i WHERE persona_id='employee'")
                identity = cur.fetchone()[0]
                result = {"manager_reports": reports, "manager_version": version, "head_person_id": manager,
                          "employee_identity": identity, "public_permissions": sorted(p.id for p in role.permissions),
                          "public_clause": rls.clause, "event_probe_absent": True}
            elif action == "manager_self":
                cur.execute("UPDATE v2_auth.role_policy SET reports=false,version=version+1 WHERE role_key='manager'")
                result = {"changed": "manager_self"}
            elif action == "revoke_public":
                role.permissions = []
                db.session.commit()
                result = {"changed": "public_dataset_access"}
            elif action == "revoke_events":
                # 只撤销事件数据集：人员出口依然可读，用来发现旧指纹遗漏事件授权的问题。
                before = len(role.permissions)
                role.permissions = [permission for permission in role.permissions
                                    if not (permission.permission.name == "datasource_access"
                                            and permission.view_menu.name == event_table.get_perm())]
                if len(role.permissions) != before - 1:
                    raise ValueError("没有找到唯一的事件数据集授权；本次探针不生效")
                db.session.commit()
                result = {"changed": "public_events_access"}
            elif action == "narrow_events":
                from superset.utils.core import RowLevelSecurityFilterType

                if db.session.query(RowLevelSecurityFilter).filter_by(name=EVENT_PROBE_NAME).first():
                    raise ValueError("事件探针名称已存在，拒绝覆盖")
                # 单独叠加 Base RLS，仅作用事件表；公共/合同人员快照完全不变。
                db.session.add(RowLevelSecurityFilter(name=EVENT_PROBE_NAME, clause="1 = 0",
                    filter_type=RowLevelSecurityFilterType.BASE, tables=[event_table], roles=[],
                    group_key=None, description="V2 自动撤权测试的临时事件规则，必须恢复"))
                db.session.commit()
                result = {"changed": "public_events_rls"}
            elif action == "narrow_rls":
                # 只缩小普通人员/事件数据集，不改context，证明RLS本身影响Agent全链路。
                rls.clause = "_viewer_id = {{ current_user_id() }} AND person_id = 'P0005'"
                db.session.commit()
                result = {"changed": "rls"}
            elif action == "unmap_employee":
                cur.execute("DELETE FROM v2_auth.identity_map WHERE persona_id='employee'")
                result = {"changed": "identity_map"}
            elif action in ("cycle", "orphan"):
                cur.execute("UPDATE v2_data.people SET head_person_id=%s WHERE person_id='P0004'",
                            ("P0005" if action == "cycle" else "missing-person",))
                result = {"changed": action}
            elif action == "restore":
                from flask_appbuilder.security.sqla.models import PermissionView

                cur.execute("UPDATE v2_auth.role_policy SET reports=%s,version=%s WHERE role_key='manager'",
                            (value["manager_reports"], value["manager_version"]))
                cur.execute("UPDATE v2_data.people SET head_person_id=%s WHERE person_id='P0004'",
                            (value["head_person_id"],))
                cur.execute("""INSERT INTO v2_auth.identity_map
                    SELECT * FROM json_populate_record(NULL::v2_auth.identity_map,%s)
                    ON CONFLICT(superset_user_id) DO NOTHING""", (Json(value["employee_identity"]),))
                role.permissions = db.session.query(PermissionView).filter(
                    PermissionView.id.in_(value["public_permissions"])).all()
                rls.clause = value["public_clause"]
                if value.get("event_probe_absent"):
                    probe = db.session.query(RowLevelSecurityFilter).filter_by(name=EVENT_PROBE_NAME).first()
                    if probe:
                        db.session.delete(probe)
                db.session.commit()
                result = {"restored": True}
            else:
                raise ValueError("不支持的验收动作")
        print(json.dumps(result, ensure_ascii=False))
    finally:
        conn.close()


if __name__ == "__main__":
    with create_app().app_context():
        main(sys.argv[1], json.loads(sys.argv[2]) if len(sys.argv) > 2 else {})
