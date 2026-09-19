"""Configure stock Superset datasets, Gamma roles and a Base RLS rule for the lab."""

import hashlib
import hmac
import json
import os
from pathlib import Path

import psycopg2
from superset.app import create_app

ROOT = Path(__file__).resolve().parent
# 首版小样本 HR_LAB 实验：输入本目录 fixtures.json，业务数据库是 hr_lab。
# 不是把 V2 的 300 人导入这里；完整 V2 导入位于 v2/setup.py，使用独立 hr_v2。
# 本脚本可重设自己 HR_LAB_* 对象；课堂 LEARN_* 与完整演示 V2_* 分别有独立初始化入口。
fixture = json.loads((ROOT / "fixtures.json").read_text())


def password(username):
    return hmac.new(os.environ["LAB_DEMO_SEED"].encode(), username.encode(), hashlib.sha256).hexdigest()[:24]


app = create_app()
with app.app_context():
    from superset import db
    from superset import security_manager as sm
    from superset.connectors.sqla.models import RowLevelSecurityFilter, SqlaTable
    from superset.models.core import Database
    from superset.models.dashboard import Dashboard
    from superset.models.slice import Slice
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
    # Superset 的成熟能力是身份、角色、数据集访问与 RLS 注入；管理/HRBP 业务关系
    # 仍由 schema.sql 中我们编写的 PostgreSQL 视图计算，不是 Superset 内置 HR 规则。
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
        # db_user 是共享数据库读者，user 是 Superset 登录人；RLS 通过登录 ID 关联业务人。
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
    # Stock Superset charts make role switching visible without writing a custom UI.
    for level, title, slug in [
        ("public", "HR 权限实验 · 人员范围", "hr-permission-lab"),
        ("private", "HR 权限实验 · 敏感字段", "hr-private-lab"),
    ]:
        table = datasets[level]
        columns = ["person_id", "name", "department", "education", "school"]
        if level == "private":
            columns.append("salary")
        chart = db.session.query(Slice).filter_by(slice_name=title).first()
        if chart is None:
            chart = Slice(slice_name=title)
        chart.datasource_id, chart.datasource_type = table.id, "table"
        chart.datasource_name, chart.viz_type = table.table_name, "table"
        chart.owners = [admin]
        chart.params = json.dumps(
            {
                "datasource": f"{table.id}__table",
                "viz_type": "table",
                "query_mode": "raw",
                "all_columns": columns,
                "metrics": [],
                "groupby": [],
                "adhoc_filters": [],
                "row_limit": 100,
                "time_range": "No filter",
                "include_search": True,
                "page_length": 20,
                "table_timestamp_format": "smart_date",
            }
        )
        chart.query_context = json.dumps(
            {
                "datasource": {"id": table.id, "type": "table"},
                "force": True,
                "result_format": "json",
                "result_type": "full",
                "queries": [
                    {
                        "columns": columns,
                        "metrics": [],
                        "filters": [],
                        "row_limit": 100,
                        "orderby": [],
                        "extras": {},
                    }
                ],
            }
        )
        db.session.add(chart)
        db.session.flush()
        dashboard = db.session.query(Dashboard).filter_by(slug=slug).first()
        if dashboard is None:
            dashboard = Dashboard(slug=slug)
            db.session.add(dashboard)
        dashboard.dashboard_title, dashboard.published = title, True
        dashboard.owners, dashboard.slices = [admin], [chart]
        dashboard.json_metadata = "{}"
        dashboard.position_json = json.dumps(
            {
                "DASHBOARD_VERSION_KEY": "v2",
                "ROOT_ID": {"id": "ROOT_ID", "type": "ROOT", "children": ["GRID_ID"]},
                "GRID_ID": {"id": "GRID_ID", "type": "GRID", "children": ["ROW-lab"], "parents": ["ROOT_ID"]},
                "HEADER_ID": {"id": "HEADER_ID", "type": "HEADER", "meta": {"text": title}},
                "ROW-lab": {
                    "id": "ROW-lab",
                    "type": "ROW",
                    "children": ["CHART-lab"],
                    "parents": ["ROOT_ID", "GRID_ID"],
                    "meta": {"background": "BACKGROUND_TRANSPARENT"},
                },
                "CHART-lab": {
                    "id": "CHART-lab",
                    "type": "CHART",
                    "children": [],
                    "parents": ["ROOT_ID", "GRID_ID", "ROW-lab"],
                    "meta": {"chartId": chart.id, "width": 12, "height": 60, "sliceName": title},
                },
            }
        )
        db.session.commit()
    connection.close()
    print("HR Superset permission lab configured. No business credentials printed.")
