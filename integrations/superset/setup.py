"""容器内初始化完整 当前 演示；由宿主机 run.py 调用，不打印任何密码。

默认 setup 只补建缺失对象，保留已存在的业务数据、用户角色和 RLS 编辑。
只有显式 --sync-data 才重导 SQLite 人员快照和角色策略；仍不重置 Superset 权限。
"""

import argparse
import hashlib
import hmac
import json
import os
import re
from pathlib import Path

import psycopg2
from psycopg2 import sql
from psycopg2.extras import Json, execute_values
from superset.app import create_app

ROOT = Path(__file__).resolve().parent
LOCAL = ROOT / ".local" / "application"
DATABASE = "hr_v2"
BASE_URL = "http://127.0.0.1:8088"


def password(name):
    """稳定派生本地专用密码，使重跑不需要打印或传递明文凭据。"""
    return hmac.new(os.environ["LAB_DEMO_SEED"].encode(), name.encode(), hashlib.sha256).hexdigest()[:24]


def pg(dbname=DATABASE):
    # 这是搭建/检查阶段的 PostgreSQL 管理连接，不是在线 Agent 的查询连接。
    # postgres 是 Compose 服务名；此函数在 Superset 容器内执行，因此用内部端口。
    return psycopg2.connect(host="postgres", dbname=dbname, user="postgres",
                            password=os.environ["POSTGRES_PASSWORD"])


def read_fixture():
    # 新容器使用独立只读挂载；既有容器仍可从原本机清单位置读取。
    fixture = json.loads(Path(os.getenv("HR_FIXTURE_PATH", LOCAL / "fixtures.json")).read_text())
    ids = [f["id"] for f in fixture["fields"]]
    if not all(re.fullmatch(r"[a-z][a-z0-9_]*", key) for key in ids):
        raise ValueError("字段 ID 不符合安全标识符规范")
    if any(f["sql_type"] not in ("text", "integer") for f in fixture["fields"]):
        raise ValueError("字段类型不在白名单中")
    if len(set(ids)) != len(ids) or any(set(p) != set(ids) for p in fixture["people"]):
        raise ValueError("重复字段或人员字段不完整")
    # 指纹检查导出文件是否完整一致，不是签名或权限证明；输入仍必须是受控文件。
    actual = hashlib.sha256(json.dumps(fixture["people"], ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    if actual != fixture["data_fingerprint"]:
        raise ValueError("数据指纹不符，拒绝导入被部分修改的文件")
    return fixture


def prepare_database(fixture, sync_data=False):
    """在现有 PostgreSQL 实例内新建数据库；不重启容器、不影响 hr_lab。"""
    bootstrap = pg("postgres")
    bootstrap.autocommit = True  # CREATE DATABASE 不可处于事务块内。
    with bootstrap.cursor() as cur:
        # 两个共享数据库账号负责限制可读对象/列；它们不代表某一名员工。
        # 员工行隔离在后续 Superset RLS 完成，不能把 reader 密码发给业务用户。
        for level in ["public", "contract"]:
            name = "v2_" + level + "_reader"
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (name,))
            if not cur.fetchone():
                cur.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD %s").format(sql.Identifier(name)),
                            (password(name),))
        cur.execute("SELECT 1 FROM pg_database WHERE datname=%s", (DATABASE,))
        if not cur.fetchone():
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(DATABASE)))
        # PUBLIC 是所有角色默认共享的授权集合，不是 public schema。
        # 此处撤销数据库级默认权限，不影响超级用户，也不会清空其他显式对象授权。
        cur.execute("REVOKE ALL ON DATABASE hr_v2 FROM PUBLIC")
        cur.execute("GRANT CONNECT ON DATABASE hr_v2 TO v2_public_reader,v2_contract_reader")
    bootstrap.close()

    conn = pg()
    with conn, conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS v2_data")
        definitions = [sql.SQL("{} {}{}").format(sql.Identifier(f["id"]), sql.SQL(f["sql_type"]),
            sql.SQL(" PRIMARY KEY" if f["id"] == "person_id" else "")) for f in fixture["fields"]]
        cur.execute(sql.SQL("CREATE TABLE IF NOT EXISTS v2_data.people ({})").format(sql.SQL(",").join(definitions)))
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS v2_employee_no ON v2_data.people(employee_no)")
        for key in ["head_person_id", "dept_hrbp_id", "dept_cn_name", "onboard_date", "termin_date"]:
            cur.execute(sql.SQL("CREATE INDEX IF NOT EXISTS {} ON v2_data.people({})").format(
                sql.Identifier("v2_people_" + key), sql.Identifier(key)))
        # schema.sql 建立角色策略、身份映射、递归关系视图和 context 出口；
        # 人员/事件出口需要动态列清单，所以由下面 create_people_views 单独创建。
        cur.execute((ROOT / "schema.sql").read_text())
        cur.execute("SELECT count(*) FROM v2_auth.snapshot")
        initialized = bool(cur.fetchone()[0])
        if not initialized or sync_data:
            # 同一事务替换整份事实和策略：读者看见旧快照或新快照，不会看见半份数据。
            cur.execute("DELETE FROM v2_data.people")
            columns = [f["id"] for f in fixture["fields"]]
            statement = sql.SQL("INSERT INTO v2_data.people ({}) VALUES %s").format(
                sql.SQL(",").join(map(sql.Identifier, columns)))
            execute_values(cur, statement.as_string(conn), [[p[c] for c in columns] for p in fixture["people"]])
            cur.execute("DELETE FROM v2_auth.role_policy")
            # 这里导入的是业务能力（汇报线、HRBP、字段组），不是 Superset 平台角色。
            for role, rule in fixture["policy"]["roles"].items():
                cur.execute("INSERT INTO v2_auth.role_policy VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (role, rule["reports"], rule["hrbp"], rule["inherit_hrbp"], Json(rule["field_groups"]),
                     rule["details"], rule["export"], fixture["policy"]["version"]))
            cur.execute("""INSERT INTO v2_auth.snapshot VALUES (true,%s,%s,%s,%s)
                ON CONFLICT(singleton) DO UPDATE SET as_of=EXCLUDED.as_of,
                data_fingerprint=EXCLUDED.data_fingerprint,data_version=EXCLUDED.data_version,
                field_definitions=EXCLUDED.field_definitions""",
                (fixture["as_of"], fixture["data_fingerprint"], fixture["data_version"], Json(fixture["fields"])))
        for field in fixture["fields"]:
            cur.execute(sql.SQL("COMMENT ON COLUMN v2_data.people.{} IS %s").format(sql.Identifier(field["id"])),
                (f"{field['label']}；字段组={field['group']}；{field['description']}",))
        create_people_views(cur, fixture["fields"])
        # PostgreSQL 最小权限：公共连接不能读取宽表、策略表或合同出口。
        for level in ["public", "contract"]:
            role = sql.Identifier("v2_" + level + "_reader")
            cur.execute(sql.SQL("GRANT USAGE ON SCHEMA v2_api TO {}").format(role))
            cur.execute(sql.SQL("GRANT SELECT ON v2_api.people_{},v2_api.events_{} TO {}").format(
                sql.SQL(level), sql.SQL(level), role))
            # 默认只读与超时是额外保护；对象权限仍依赖上面的 GRANT 和默认不授予。
            # default_transaction_read_only 本身不是禁止有权限用户写入的完整安全边界。
            cur.execute(sql.SQL("ALTER ROLE {} SET default_transaction_read_only=on").format(role))
            cur.execute(sql.SQL("ALTER ROLE {} SET statement_timeout='10s'").format(role))
        cur.execute("GRANT SELECT ON v2_api.context TO v2_public_reader")
        cur.execute("SELECT graph_valid FROM v2_auth.graph_health")
        if not cur.fetchone()[0]:
            raise ValueError("当前 数据存在管理环、主管孤儿或 HRBP 孤儿，本次导入回滚")
    return conn


def create_people_views(cur, fields):
    """数据源列隔离：公共出口没有合同列；合同出口同时核对业务字段组。"""
    for level in ["public", "contract"]:
        # 这里得到“每个查看人各自的候选行”，不是已经完成最终登录隔离的全局人员表。
        # 同一员工可出现多次；只有 Superset 注入 _viewer_id 后才是某个登录人的结果。
        columns = [f["id"] for f in fields if level == "contract" or f["group"] != "contract"]
        # 附加的授权列便于受控查询、核验和节点解释，不能由模型指定查看人。
        condition = "AND r.field_groups ? 'contract'" if level == "contract" else ""
        # p 是人员事实，g 是查看人→人员的可见关系，i 把查看人绑定业务角色，r 是策略。
        # 普通 VIEW 不保存计算结果；security_barrier 约束优化器，不负责识别登录人。
        cur.execute(sql.SQL("""CREATE OR REPLACE VIEW v2_api.people_{} WITH(security_barrier=true) AS
            SELECT {},g.superset_user_id AS _viewer_id,g.depth AS _depth,
                   g.reports AS _reports,g.hrbp AS _hrbp,g.inherited AS _inherited,g.origins AS _origins,
                   CASE WHEN p.person_id=i.person_id THEN '本人'
                        WHEN g.reports AND g.depth=1 THEN '直属下属'
                        WHEN g.reports THEN '间接下属' ELSE 'HRBP服务人员' END AS relation,
                   substring(p.onboard_date,1,7) AS onboard_month,
                   substring(p.termin_date,1,7) AS termin_month,
                   substring(p.confirmation_date,1,7) AS confirmation_month
            FROM v2_data.people p JOIN v2_auth.visible_people g ON g.target_id=p.person_id
            JOIN v2_auth.identity_map i ON i.superset_user_id=g.superset_user_id
            JOIN v2_auth.role_policy r ON r.role_key=i.role_key
            WHERE true {}""").format(sql.SQL(level), sql.SQL(",").join(
                sql.SQL("p.{}").format(sql.Identifier(c)) for c in columns), sql.SQL(condition)))
        # 把一行人员记录转换成入职/离职事件：有离职日期的人可以贡献两行。
        # UNION ALL 保留不同事件；人数用 DISTINCT person_id，事件数用 SUM 标记。
        # Superset 会分别注册事件数据集，因此事件数据集也必须单独绑定 RLS。
        cur.execute(sql.SQL("""CREATE OR REPLACE VIEW v2_api.events_{} WITH(security_barrier=true) AS
            SELECT p.*,onboard_date AS event_day,substring(onboard_date,1,7) AS event_month,
                   1::integer AS is_hire,0::integer AS is_exit FROM v2_api.people_{} p WHERE onboard_date IS NOT NULL
            UNION ALL
            SELECT p.*,termin_date AS event_day,substring(termin_date,1,7) AS event_month,
                   0::integer AS is_hire,1::integer AS is_exit FROM v2_api.people_{} p WHERE termin_date IS NOT NULL
            """).format(sql.SQL(level), sql.SQL(level), sql.SQL(level)))


def create_chart(db, Slice, Dashboard, admin, table, level):
    # Slice 是 Superset 的图表对象，Dashboard 是排版容器，均保存在元数据库。
    # 图表只引用数据集 ID 和展示列，不复制业务数据，也不替代数据集权限/RLS。
    title = "当前 · " + ("人员与汇报范围" if level == "public" else "合同字段权限")
    columns = ["employee_no", "name", "dept_cn_name", "diploma_code_desc", "school_name", "relation"]
    if level == "contract":
        columns += ["contract_type_code_desc", "contract_end_date"]
    chart = db.session.query(Slice).filter_by(slice_name=title).first()
    if chart is None:
        chart = Slice(slice_name=title, datasource_id=table.id, datasource_type="table",
            datasource_name=table.table_name, viz_type="table", owners=[admin])
        chart.params = json.dumps({"datasource": f"{table.id}__table", "viz_type": "table", "query_mode": "raw",
            "all_columns": columns, "metrics": [], "groupby": [], "adhoc_filters": [], "row_limit": 1000,
            "time_range": "No filter", "include_search": True, "page_length": 20})
        # QueryContext 描述一次查询；all_columns 是图表表单字段，queries.columns
        # 是执行协议字段。两者保持同一投影，保存图表不等于执行查询。
        chart.query_context = json.dumps({"datasource": {"id": table.id, "type": "table"}, "force": True,
            "result_format": "json", "result_type": "full", "queries": [{"columns": columns,
                "metrics": [], "filters": [], "row_limit": 1000, "orderby": [], "extras": {}}]})
        db.session.add(chart)
        db.session.flush()
    slug = "v2-people-" + level
    dashboard = db.session.query(Dashboard).filter_by(slug=slug).first()
    if dashboard is None:
        dashboard = Dashboard(slug=slug, dashboard_title=title, published=True,
            owners=[admin], slices=[chart], json_metadata="{}")
        dashboard.position_json = json.dumps({"DASHBOARD_VERSION_KEY": "v2",
            "ROOT_ID": {"id": "ROOT_ID", "type": "ROOT", "children": ["GRID_ID"]},
            "GRID_ID": {"id": "GRID_ID", "type": "GRID", "children": ["ROW-v2"], "parents": ["ROOT_ID"]},
            "HEADER_ID": {"id": "HEADER_ID", "type": "HEADER", "meta": {"text": title}},
            "ROW-v2": {"id": "ROW-v2", "type": "ROW", "children": ["CHART-v2"],
                "parents": ["ROOT_ID", "GRID_ID"], "meta": {"background": "BACKGROUND_TRANSPARENT"}},
            "CHART-v2": {"id": "CHART-v2", "type": "CHART", "children": [],
                "parents": ["ROOT_ID", "GRID_ID", "ROW-v2"],
                "meta": {"chartId": chart.id, "width": 12, "height": 65, "sliceName": title}}})
        db.session.add(dashboard)
    db.session.commit()
    return {"dashboard": f"{BASE_URL}/superset/dashboard/{slug}/",
            "chart": f"{BASE_URL}/explore/?slice_id={chart.id}"}


def prepare_superset(sync_data=False):
    """按依赖顺序建立平台配置，最后输出 Agent 要用的实际对象 ID。

    顺序：PG 事实/视图 → 技术管理员 → 连接/数据集 → RLS → 平台角色 →
    业务账号 → identity_map。PG 和 Superset 元数据各自提交，不是跨库原子事务；
    失败后应检查现场，不能把部分完成当成可交付状态。已有对象主要复用而不覆盖。
    """
    from superset import db
    from superset import security_manager as sm
    from superset.connectors.sqla.models import RowLevelSecurityFilter, SqlaTable
    from superset.models.core import Database
    from superset.models.dashboard import Dashboard
    from superset.models.slice import Slice
    from superset.utils.core import RowLevelSecurityFilterType

    fixture = read_fixture()
    conn = prepare_database(fixture, sync_data)
    # 技术管理员只负责配置，绝不放进下方供 Agent 执行的 principals 映射。
    admin = sm.find_user(username="v2_setup_admin") or sm.add_user(
        "v2_setup_admin", "当前", "配置管理员", "v2_setup_admin@example.invalid",
        sm.find_role("Admin"), password("v2_setup_admin"))
    tables = {}
    result = {"database": DATABASE, "base_url": BASE_URL, "datasets": {}, "principals": {},
              "roles": [], "rls": [], "as_of": None, "data_fingerprint": None}
    for name in ["people_public", "events_public", "people_contract", "events_contract", "context"]:
        level = "contract" if name.endswith("contract") else "public"
        database = db.session.query(Database).filter_by(database_name="V2_" + level).first()
        if database is None:
            # Database 是“Superset 保存的连接配置”，不是 CREATE DATABASE。
            # 对应手册第 26 步：显示名、Host、端口、账号和密码都记录在该对象中。
            database = Database(database_name="V2_" + level)
            db_user = "v2_" + level + "_reader"
            database.sqlalchemy_uri = f"postgresql+psycopg2://{db_user}:{password(db_user)}@postgres:5432/{DATABASE}"
            database.expose_in_sqllab = False
            # 对应页面的 DDL/DML、CTAS、CVAS、异步执行开关。只在新建时赋值，
            # 重跑脚本不会覆盖用户后来编辑过的开关；已有连接需另外核对。
            database.allow_dml = database.allow_ctas = database.allow_cvas = database.allow_run_async = False
            db.session.add(database)
            db.session.commit()
        # SqlaTable 是注册到 Superset 的物理数据集。引用 PG 已存在的 VIEW，
        # 不在这里复制数据或创建视图；相当于手册中“选择连接、schema、表名”。
        table = db.session.query(SqlaTable).filter_by(database_id=database.id, schema="v2_api", table_name=name).first()
        if table is None:
            table = SqlaTable(database=database, schema="v2_api", table_name=name, owners=[admin])
            db.session.add(table)
            db.session.commit()
            # 读取列名/类型等元信息，让图表接口知道允许引用的数据集字段。
            table.fetch_metadata()
            db.session.commit()
        tables[name] = table
        # 创建“可访问这个数据集”的权限项，随后再赋给指定角色；创建权限项
        # 本身不意味着任何业务用户已获权，更不决定能看到该数据集的哪些行。
        sm.add_permission_view_menu("datasource_access", table.get_perm())
        result["datasets"][name] = {"id": table.id, "database_id": database.id, "permission": table.get_perm(),
            "columns": [c.column_name for c in table.columns], "schema": "v2_api", "table_name": name,
            "urls": {"explore": f"{BASE_URL}/explore/?datasource_type=table&datasource_id={table.id}"}}
        if name.startswith("people_"):
            result["datasets"][name]["urls"].update(create_chart(db, Slice, Dashboard, admin, table, level))

    # Base 且 roles=[] 表示没有豁免角色；未映射业务用户自动 0 行。
    # current_user_id() 由 Superset 登录上下文提供，不是问题里的 person_id。
    # Base 的 roles 是豁免角色，与 Regular 的适用角色含义不同；管理员不用于验权。
    # context 的身份列名不同，所以单独一条规则；人员/事件共用同一查看人列名。
    for name, members, clause in [
        ("V2_scope_public", ["people_public", "events_public"], "_viewer_id = {{ current_user_id() }}"),
        ("V2_scope_contract", ["people_contract", "events_contract"], "_viewer_id = {{ current_user_id() }}"),
        ("V2_context_scope", ["context"], "superset_user_id = {{ current_user_id() }}"),
    ]:
        rule = db.session.query(RowLevelSecurityFilter).filter_by(name=name).first()
        if rule is None:
            rule = RowLevelSecurityFilter(name=name, clause=clause, filter_type=RowLevelSecurityFilterType.BASE,
                tables=[tables[t] for t in members], roles=[], group_key=None,
                description="当前 登录用户隔离；业务递归关系在 hr_v2.v2_auth 视图计算，不能由问题指定查看人。")
            db.session.add(rule)
        db.session.commit()
        result["rls"].append({"id": rule.id, "name": name, "clause": rule.clause,
                              "datasets": [t.table_name for t in rule.tables], "exempt_roles": [r.name for r in rule.roles]})

    # 平台角色分成数据集访问角色与业务标签角色。V2_Role_* 本身没有数据权限；
    # 真正业务范围还要用 identity_map.role_key 关联 PG 的 role_policy。
    # 不授 database_access，避免将整个连接中的其他数据集一起开放。
    role_specs = {"V2_Data_public": ["people_public", "events_public"],
                  "V2_Data_contract": ["people_contract", "events_contract"], "V2_Context": ["context"]}
    role_specs.update({"V2_Role_" + p["role"]: [] for p in fixture["personas"]})
    role_objects = {}
    for name, members in role_specs.items():
        role = sm.find_role(name)
        if role is None:
            role = sm.add_role(name)
            role.permissions = [sm.add_permission_view_menu("datasource_access", tables[t].get_perm()) for t in members]
        role_objects[name] = role
        result["roles"].append(name)
    db.session.commit()

    for persona in fixture["personas"]:
        username = "v2_" + persona["id"]
        with conn.cursor() as cur:
            cur.execute("SELECT field_groups FROM v2_auth.role_policy WHERE role_key=%s", (persona["role"],))
            policy = cur.fetchone()
            if not policy:
                raise ValueError("当前 PostgreSQL 策略缺少身份角色，请显式 sync-data 后重试")
        # Gamma 提供基础浏览能力；指定数据集访问权由自定义角色补充。
        # 合同权限既需要此处平台数据集角色，也需要 PG 字段组条件同时满足。
        roles = [sm.find_role("Gamma"), role_objects["V2_Data_public"], role_objects["V2_Context"],
                 role_objects["V2_Role_" + persona["role"]]]
        if "contract" in policy[0]:
            roles.append(role_objects["V2_Data_contract"])
        user = sm.find_user(username=username)
        if user is None:
            user = sm.add_user(username, "当前", persona["name"], username + "@example.invalid", roles, password(username))
        # 重跑不覆盖用户后来在 Superset UI 中变更的角色。
        # 必须先创建/找到真实用户，再用实际 user.id 写映射；不能猜自增 ID。
        # ON CONFLICT DO NOTHING 只保留既有映射，不负责调岗或离职时自动同步。
        with conn, conn.cursor() as cur:
            cur.execute("""INSERT INTO v2_auth.identity_map VALUES (%s,%s,%s,%s,%s)
                ON CONFLICT(superset_user_id) DO NOTHING""",
                (user.id, username, persona["id"], persona["person_id"], persona["role"]))
        result["principals"][persona["id"]] = {"username": username, "user_id": user.id,
            "person_id": persona["person_id"], "role": persona["role"], "label": persona["label"]}
    # 反例拥有公共数据集访问权，却没有 identity_map；RLS 后应返回 0 行。
    unmapped = sm.find_user(username="v2_unmapped") or sm.add_user("v2_unmapped", "当前", "未映射反例",
        "v2_unmapped@example.invalid", [sm.find_role("Gamma"), role_objects["V2_Data_public"],
        role_objects["V2_Context"]], password("v2_unmapped"))
    result["unmapped"] = {"username": unmapped.username, "user_id": unmapped.id}
    result["setup_admin"] = {"username": admin.username, "user_id": admin.id}
    db.session.commit()
    with conn.cursor() as cur:
        cur.execute("SELECT as_of,data_fingerprint,data_version FROM v2_auth.snapshot")
        result["as_of"], result["data_fingerprint"], result["data_version"] = cur.fetchone()
        cur.execute("SELECT count(*) FROM v2_data.people")
        result["row_count"] = cur.fetchone()[0]
    conn.close()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    from initialization_guard import require_automatic_setup

    require_automatic_setup(LOCAL, read_fixture)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sync-data", action="store_true")
    args = parser.parse_args()
    with create_app().app_context():
        prepare_superset(args.sync_data)
