"""手工课堂的容器内只读工具：提取原视图 SQL、盘点实际用户/数据集 ID。

绝不调用 prepare_superset/prepare_database，不补建或改写平台对象。
宿主机 learning.py 负责保存输出；此程序只向调用程序输出 JSON，不输出密码。
"""
import argparse
import json

from setup import create_people_views, pg, read_fixture


def views():
    """复用原 SQL 生成函数，但将 execute 替换为收集，数据库仅用于转义。"""
    statements = []
    conn = pg("postgres")
    try:
        class Recorder:
            def execute(self, statement):
                # 模拟 cursor.execute 的签名，但只序列化 SQL；真实连接仅用于
                # psycopg2 标识符转义，绝不将收集到的 CREATE 语句提交给数据库。
                statements.append(statement.as_string(conn).strip() + ";")
        create_people_views(Recorder(), read_fixture()["fields"])
    finally:
        conn.close()
    return statements


def inventory():
    """真实 ID 必须从本次手工配置读取，不能用初始化前的旧清单。"""
    from superset.app import create_app
    with create_app().app_context():
        from superset import db
        from superset import security_manager as sm
        from superset.connectors.sqla.models import SqlaTable
        from superset.models.core import Database
        # 盘点的是用户和已注册数据集，不单独返回连接列表；datasets 为空
        # 不能据此断言数据库连接尚未创建，连接需要查询 Database 模型核对。
        result = {"users": {}, "datasets": {}}
        fixture = read_fixture()
        for name in ["v2_setup_admin", "v2_unmapped", *["v2_" + p["id"] for p in fixture["personas"]]]:
            user = sm.find_user(username=name)
            if user:
                result["users"][name] = {"id": user.id, "roles": sorted(r.name for r in user.roles)}
        for table in db.session.query(SqlaTable).join(Database).filter(
                Database.database_name.in_(["V2_public", "V2_contract"])).all():
            if table.schema != "v2_api":
                continue
            level = "contract" if table.table_name.endswith("contract") else "public"
            if table.database.database_name != "V2_" + level:
                raise ValueError("数据集绑定了错误连接：" + table.table_name)
            if table.table_name in result["datasets"]:
                raise ValueError("数据集重名：" + table.table_name)
            result["datasets"][table.table_name] = {
                "id": table.id, "database_id": table.database_id,
                "schema": table.schema, "table_name": table.table_name,
                "permission": table.get_perm(), "columns": [c.column_name for c in table.columns],
                "urls": {"explore": f"http://127.0.0.1:8088/explore/?datasource_type=table&datasource_id={table.id}"}}
        return result


def binding():
    """核对人员映射后返回兼容 Agent 的清单，不创建或修改任何配置。"""
    # 确认“应用身份→Superset 账号→员工主键/业务角色”和五个出口均对得上。
    # 这里只验证映射结构；真实 RLS/越权测试仍须由后续验收执行。
    actual = inventory()
    fixture = read_fixture()
    expected = {"people_public", "people_contract", "events_public", "events_contract", "context"}
    if set(actual["datasets"]) != expected:
        raise ValueError("请先完成五个数据集，当前为：" + str(sorted(actual["datasets"])))
    conn = pg()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT superset_user_id,username,persona_id,person_id,role_key FROM v2_auth.identity_map")
            mappings = {r[2]: r for r in cur.fetchall()}
            principals = {}
            for persona in fixture["personas"]:
                key = persona["id"]
                name = "v2_" + key
                user = actual["users"].get(name)
                if not user:
                    raise ValueError("缺少用户：" + name)
                expected_row = (user["id"], name, key, persona["person_id"], persona["role"])
                if mappings.get(key) != expected_row:
                    raise ValueError("账号映射未匹配，请检查：" + key)
                principals[key] = {"username": name, "user_id": user["id"],
                    "person_id": persona["person_id"], "role": persona["role"], "label": persona["label"]}
            if set(mappings) != set(principals):
                raise ValueError("身份映射包含非预期记录")
            for name in ("v2_unmapped", "v2_setup_admin"):
                if name not in actual["users"]:
                    raise ValueError("缺少用户：" + name)
            cur.execute("SELECT as_of,data_fingerprint,data_version FROM v2_auth.snapshot")
            snapshot = cur.fetchone()
            if not snapshot or snapshot != (fixture["as_of"], fixture["data_fingerprint"], fixture["data_version"]):
                raise ValueError("快照元数据与原样本不符")
            cur.execute("SELECT count(*) FROM v2_data.people")
            count = cur.fetchone()[0]
            if count != fixture["row_count"]:
                raise ValueError("人员行数不符；请先导入完整样本")
            cur.execute("SELECT graph_valid FROM v2_auth.graph_health")
            if cur.fetchone() != (True,):
                raise ValueError("组织关系异常")
    finally:
        conn.close()
    # 这个清单只记录身份和数据集；权限正确性另由 verify-storage 和真实回归检查。
    return {"database": "hr_v2", "base_url": "http://127.0.0.1:8088", "datasets": actual["datasets"],
        "principals": principals, "row_count": count, "as_of": snapshot[0],
        "data_fingerprint": snapshot[1], "data_version": snapshot[2],
        "unmapped": {"username": "v2_unmapped", "user_id": actual["users"]["v2_unmapped"]["id"]},
        "setup_admin": {"username": "v2_setup_admin", "user_id": actual["users"]["v2_setup_admin"]["id"]}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["views", "inventory", "binding"])
    args = parser.parse_args()
    print(json.dumps({"views": views, "inventory": inventory, "binding": binding}[args.action](), ensure_ascii=False))
