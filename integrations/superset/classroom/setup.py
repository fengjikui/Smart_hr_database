"""在正在运行的 Superset 容器内准备课堂对象。

执行环境：python /lab/classroom/setup.py，由 run.py 通过 docker exec 调用。
只操作 learn_* / LEARN_* 命名空间，不重启服务，不改原 HR 实验。
重要：创建空业务角色，但不替学生授予数据集权限，也不创建 RLS。
"""

import hashlib
import hmac
import json
import os
from pathlib import Path

import psycopg2
from generate import USERS, generate
from psycopg2 import sql
from superset.app import create_app

ROOT = Path(__file__).resolve().parent


def password(name):
    """从本地密钥派生课堂专用密码；不硬编码、不打印到日志。"""
    return hmac.new(os.environ["LAB_DEMO_SEED"].encode(), name.encode(), hashlib.sha256).hexdigest()[:24]


def prepare_database():
    """把确定性业务事实写入 PostgreSQL；重复运行不覆盖学生已修改的数据。"""
    conn = psycopg2.connect(host="postgres", dbname="hr_lab", user="postgres",
                            password=os.environ["POSTGRES_PASSWORD"])
    data = generate()
    with conn, conn.cursor() as cur:
        for role in ["learn_public_reader", "learn_private_reader"]:
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,))
            if not cur.fetchone():
                cur.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD %s").format(sql.Identifier(role)),
                            (password(role),))
            cur.execute(sql.SQL("GRANT CONNECT ON DATABASE hr_lab TO {}").format(sql.Identifier(role)))
        cur.execute((ROOT / "schema.sql").read_text())
        for person in data["people"]:
            cur.execute("""INSERT INTO learn_data.people
                (person_id,employee_no,name,department,manager_id,hrbp_id,education)
                VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""", tuple(person.values()))
        for entry in data["payroll"]:
            cur.execute("INSERT INTO learn_data.payroll VALUES (%s,%s) ON CONFLICT DO NOTHING",
                        (entry["person_id"], entry["salary"]))
        for order in data["orders"]:
            cur.execute("""INSERT INTO learn_data.orders
                (order_id,owner_id,region,order_date,amount,classification,customer_name,customer_phone)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""", tuple(order.values()))
        for policy in [("employee", False, False, False), ("manager", True, False, False),
                       ("hrbp", True, True, False), ("hrlead", True, True, True)]:
            cur.execute("INSERT INTO learn_auth.role_policy VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING", policy)
    return conn


def prepare_superset():
    # Superset 自己的 ORM 保存用户、角色、数据集和图表。
    # 元数据库与前面 PostgreSQL 的业务表是两个不同职责。
    from superset import db
    from superset import security_manager as sm
    from superset.connectors.sqla.models import SqlaTable
    from superset.models.core import Database
    from superset.models.dashboard import Dashboard
    from superset.models.slice import Slice

    conn = prepare_database()
    admin = sm.find_user(username="learn_admin")
    if not admin:
        admin = sm.add_user("learn_admin", "课堂", "管理员", "learn_admin@example.invalid",
                            sm.find_role("Admin"), password("learn_admin"))
    reader = sm.add_role("LEARN_Reader")  # 初始没有任何数据集权限，留给学生手工填写。
    for username, person_id, role_name, policy, regions in USERS:
        role = sm.add_role(role_name)
        user = sm.find_user(username=username)
        if not user:
            user = sm.add_user(username, "课堂", username, username + "@example.invalid",
                               [sm.find_role("Gamma"), reader, role], password(username))
        # 已存在的用户不重新赋角色，避免覆盖学生在界面里的练习。
        if person_id:
            with conn, conn.cursor() as cur:
                cur.execute("INSERT INTO learn_auth.identity_map VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                            (user.id, username, person_id, policy))
                for region in regions:
                    cur.execute("INSERT INTO learn_auth.user_regions VALUES (%s,%s) ON CONFLICT DO NOTHING",
                                (user.id, region))

    result = {"datasets": {}, "users": ["learn_admin", *[u[0] for u in USERS]], "initial_rls_created": 0}
    specs = [
        ("orders", "public", "01 订单与区域", ["order_id", "owner_id", "region", "amount", "classification", "phone_masked"]),
        ("people", "public", "02 人员与汇报线", ["person_id", "name", "department", "manager_id", "hrbp_id", "education"]),
        ("payroll", "private", "03 敏感薪资", ["person_id", "name", "department", "salary"]),
        ("orders_private", "private", "04 完整模拟电话", ["order_id", "region", "amount", "customer_phone"]),
    ]
    for table_name, level, title, columns in specs:
        database = db.session.query(Database).filter_by(database_name=f"LEARN_{level}").first()
        if database is None:
            user = f"learn_{level}_reader"
            database = Database(database_name=f"LEARN_{level}")
            database.sqlalchemy_uri = f"postgresql+psycopg2://{user}:{password(user)}@postgres:5432/hr_lab"
            database.expose_in_sqllab = level == "public"  # 只有管理员用 SQL Lab 核对；学生不赋 sql_lab。
            database.allow_dml = False
            database.allow_ctas = False
            database.allow_cvas = False
            database.allow_run_async = False
            db.session.add(database)
            db.session.commit()
        table = db.session.query(SqlaTable).filter_by(database_id=database.id, schema="learn_api",
                                                    table_name=table_name).first()
        if table is None:
            table = SqlaTable(database=database, schema="learn_api", table_name=table_name, owners=[admin])
            db.session.add(table)
            db.session.commit()
            table.fetch_metadata()
            db.session.commit()
        # 创建可供角色界面选择的 permission，但不把它赋给 LEARN_Reader。
        sm.add_permission_view_menu("datasource_access", table.get_perm())
        chart_title = "LEARN · " + title
        chart = db.session.query(Slice).filter_by(slice_name=chart_title).first()
        if chart is None:
            chart = Slice(slice_name=chart_title, datasource_id=table.id, datasource_type="table",
                          datasource_name=table.table_name, viz_type="table", owners=[admin])
            chart.params = json.dumps({"datasource": f"{table.id}__table", "viz_type": "table",
                "query_mode": "raw", "all_columns": columns, "metrics": [], "groupby": [],
                "adhoc_filters": [], "row_limit": 100, "time_range": "No filter",
                "include_search": True, "page_length": 20})
            chart.query_context = json.dumps({"datasource": {"id": table.id, "type": "table"},
                "force": True, "result_format": "json", "result_type": "full", "queries": [{
                    "columns": columns, "metrics": [], "filters": [], "row_limit": 100,
                    "orderby": [], "extras": {}}]})
            db.session.add(chart)
            db.session.flush()
        slug = "learn-" + table_name.replace("_", "-")
        dashboard = db.session.query(Dashboard).filter_by(slug=slug).first()
        if dashboard is None:
            dashboard = Dashboard(slug=slug, dashboard_title=chart_title, published=True,
                                  owners=[admin], slices=[chart], json_metadata="{}")
            dashboard.position_json = json.dumps({
                "DASHBOARD_VERSION_KEY": "v2",
                "ROOT_ID": {"id": "ROOT_ID", "type": "ROOT", "children": ["GRID_ID"]},
                "GRID_ID": {"id": "GRID_ID", "type": "GRID", "children": ["ROW-learn"], "parents": ["ROOT_ID"]},
                "HEADER_ID": {"id": "HEADER_ID", "type": "HEADER", "meta": {"text": chart_title}},
                "ROW-learn": {"id": "ROW-learn", "type": "ROW", "children": ["CHART-learn"],
                    "parents": ["ROOT_ID", "GRID_ID"], "meta": {"background": "BACKGROUND_TRANSPARENT"}},
                "CHART-learn": {"id": "CHART-learn", "type": "CHART", "children": [],
                    "parents": ["ROOT_ID", "GRID_ID", "ROW-learn"],
                    "meta": {"chartId": chart.id, "width": 12, "height": 60, "sliceName": chart_title}},
            })
            db.session.add(dashboard)
        db.session.commit()
        result["datasets"][table_name] = {"id": table.id, "permission": table.get_perm(),
            "database_id": database.id, "dashboard": f"http://127.0.0.1:8088/superset/dashboard/{slug}/"}
    conn.close()
    # stdout 最后一行只有非敏感清单，宿主机 run.py 据此保存可阅读的课堂入口。
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    with create_app().app_context():
        prepare_superset()
