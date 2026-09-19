"""在容器内只读列举 V2 实际配置，方便核对 UI 中所见，不输出密码或连接串。"""

import json

from setup import pg
from superset.app import create_app


def main():
    from superset import db
    from superset import security_manager as sm
    from superset.connectors.sqla.models import RowLevelSecurityFilter, SqlaTable
    from superset.models.core import Database

    result = {"database": "hr_v2", "users": [], "rls": [], "datasets": []}
    for username in ["v2_hr_lead", "v2_hrbp", "v2_manager", "v2_employee", "v2_admin",
                     "v2_unmapped", "v2_setup_admin"]:
        user = sm.find_user(username=username)
        if user:
            result["users"].append({"username": user.username, "user_id": user.id,
                "roles": [r.name for r in user.roles]})
    for rule in db.session.query(RowLevelSecurityFilter).filter(RowLevelSecurityFilter.name.like("V2_%")).all():
        result["rls"].append({"name": rule.name, "type": str(rule.filter_type), "clause": rule.clause,
            "exempt_roles": [r.name for r in rule.roles], "datasets": [t.table_name for t in rule.tables]})
    for table in db.session.query(SqlaTable).join(Database).filter(Database.database_name.in_(
            ["V2_public", "V2_contract"])).all():
        result["datasets"].append({"id": table.id, "name": table.table_name, "database": table.database.database_name,
            "columns": [c.column_name for c in table.columns]})
    conn = pg()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM v2_data.people")
            result["people_count"] = cur.fetchone()[0]
            cur.execute("SELECT as_of,data_fingerprint FROM v2_auth.snapshot")
            result["as_of"], result["data_fingerprint"] = cur.fetchone()
            cur.execute("SELECT graph_valid FROM v2_auth.graph_health")
            result["graph_valid"] = cur.fetchone()[0]
            cur.execute("""SELECT i.username,count(v.target_id) FROM v2_auth.identity_map i
                LEFT JOIN v2_auth.visible_people v USING(superset_user_id) GROUP BY i.username ORDER BY i.username""")
            result["authorized_candidate_counts"] = dict(cur.fetchall())
    finally:
        conn.close()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    with create_app().app_context():
        main()
