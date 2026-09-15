"""Configure stock Superset datasets, Gamma roles and a Base RLS rule for the lab."""

import hashlib
import hmac
import json
import os
from pathlib import Path

import psycopg2
from superset.app import create_app

ROOT = Path(__file__).resolve().parent
fixture = json.loads((ROOT / "fixtures.json").read_text())


def password(username):
    return hmac.new(os.environ["LAB_DEMO_SEED"].encode(), username.encode(), hashlib.sha256).hexdigest()[:24]


app = create_app()
with app.app_context():
    from superset import db
    from superset import security_manager as sm
    from superset.connectors.sqla.models import RowLevelSecurityFilter, SqlaTable
    from superset.models.core import Database
    from superset.utils.core import RowLevelSecurityFilterType

    admin = sm.find_user(username="lab_admin") or sm.add_user(
        "lab_admin", "Lab", "Admin", "lab_admin@example.com", sm.find_role("Admin"), password("lab_admin")
    )
    connection = psycopg2.connect(
        host="postgres", dbname="hr_lab", user="postgres", password=os.environ["POSTGRES_PASSWORD"]
    )
    with connection, connection.cursor() as cur:
        cur.execute((ROOT / "schema.sql").read_text())
        # This lab owns only these tables. Re-running configuration updates its fixture.
        for index, p in enumerate(fixture["people"], 1):
            cur.execute(
                """INSERT INTO hr.people VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
              ON CONFLICT(person_id) DO UPDATE SET name=EXCLUDED.name,department=EXCLUDED.department,
              head_person_id=EXCLUDED.head_person_id,dept_hrbp_id=EXCLUDED.dept_hrbp_id,
              education=EXCLUDED.education,school=EXCLUDED.school,salary=EXCLUDED.salary""",
                (
                    p["person_id"],
                    f"{index:08d}",
                    p["name"],
                    p["department"],
                    p["head_person_id"],
                    p["dept_hrbp_id"],
                    p["education"],
                    p["school"],
                    10000 + index * 500,
                ),
            )
        for name, rule in fixture["roles"].items():
            cur.execute(
                """INSERT INTO authz.role_policy VALUES (%s,%s,%s,%s,%s)
                ON CONFLICT(role_key) DO UPDATE SET reports=EXCLUDED.reports,hrbp=EXCLUDED.hrbp,
                inherit_hrbp=EXCLUDED.inherit_hrbp,private_fields=EXCLUDED.private_fields""",
                (name, rule["reports"], rule["hrbp"], rule["inherit_hrbp"], rule["private_fields"]),
            )

    datasets = {}
    data_roles = {}
    for level, db_user, key in [
        ("public", "hr_public_reader", "PUBLIC_DB_PASSWORD"),
        ("private", "hr_private_reader", "PRIVATE_DB_PASSWORD"),
    ]:
        name = "HR Lab " + level
        database = db.session.query(Database).filter_by(database_name=name).first()
        if not database:
            database = Database(database_name=name)
            db.session.add(database)
        database.sqlalchemy_uri = f"postgresql+psycopg2://{db_user}:{os.environ[key]}@postgres:5432/hr_lab"
        database.expose_in_sqllab = level == "public"
        database.allow_dml = False
        database.allow_run_async = False
        database.allow_ctas = False
        database.allow_cvas = False
        db.session.commit()
        table = (
            db.session.query(SqlaTable)
            .filter_by(database_id=database.id, schema="analytics", table_name="people_" + level)
            .first()
        )
        if not table:
            table = SqlaTable(
                database=database, schema="analytics", table_name="people_" + level, owners=[admin]
            )
            db.session.add(table)
            db.session.commit()
        table.fetch_metadata()
        db.session.commit()
        role = sm.add_role("HR_LAB_" + level)
        perm = sm.add_permission_view_menu("datasource_access", table.get_perm())
        role.permissions = [perm]
        data_roles[level] = role
        datasets[level] = table
        name = "HR_LAB_identity_scope_" + level
        rls = db.session.query(RowLevelSecurityFilter).filter_by(name=name).first()
        if not rls:
            rls = RowLevelSecurityFilter(name=name)
            db.session.add(rls)
        rls.filter_type = RowLevelSecurityFilterType.BASE
        rls.roles = []  # Applies to everyone, including mistakenly added extra business roles.
        rls.tables = [table]
        rls.group_key = None
        rls.clause = "person_id IN (SELECT target_id FROM authz.visible_people WHERE superset_user_id = {{ current_user_id() }})"
        rls.description = (
            "Default deny for missing identity; SQL relation graph implements the documented HR policy."
        )
        db.session.commit()

    for u in fixture["users"]:
        roles = [sm.find_role("Gamma"), data_roles["public"]]
        business_role = sm.add_role("HR_LAB_ROLE_" + u["role"])
        roles.append(business_role)
        if fixture["roles"][u["role"]]["private_fields"]:
            roles.append(data_roles["private"])
        if u.get("sql_boundary_probe"):
            probe_role = sm.add_role("HR_LAB_SQL_BOUNDARY_PROBE_ONLY")
            probe_role.permissions = [
                sm.add_permission_view_menu("database_access", datasets["public"].database.get_perm())
            ]
            roles.extend([sm.find_role("sql_lab"), probe_role])
        user = sm.find_user(username=u["username"])
        if not user:
            user = sm.add_user(
                u["username"],
                "Lab",
                u["role"],
                u["username"] + "@example.com",
                roles,
                password(u["username"]),
            )
        user.roles = roles
        db.session.commit()
        if u["person_id"]:
            with connection, connection.cursor() as cur:
                cur.execute(
                    """INSERT INTO authz.identity_map VALUES (%s,%s,%s,%s)
                  ON CONFLICT(superset_user_id) DO UPDATE SET username=EXCLUDED.username,
                  person_id=EXCLUDED.person_id,role_key=EXCLUDED.role_key""",
                    (user.id, u["username"], u["person_id"], u["role"]),
                )
    connection.close()
    print("HR Superset permission lab configured. No business credentials printed.")
