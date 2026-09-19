"""备课验收：通过真实 Superset REST 与 PostgreSQL 验证将要手填的规则。

只允许在课堂尚未开始的空角色、无 RLS 状态运行。
测试暂时修改 LEARN 自有角色，finally 恢复；绝不清空学生已经写好的规则。
普通学习过程中请用 run.py inspect，只读观察，不要运行本文件。
"""

import json
from datetime import datetime, timezone

import psycopg2
import requests
from generate import EXPECTED, USERS
from setup import password
from superset.app import create_app


def main():
    from superset import db
    from superset import security_manager as sm
    from superset.connectors.sqla.models import RowLevelSecurityFilter, SqlaTable
    from superset.models.core import Database
    from superset.utils.core import RowLevelSecurityFilterType

    tables = {t.table_name: t for t in db.session.query(SqlaTable).join(Database).filter(
        Database.database_name.in_(["LEARN_public", "LEARN_private"])).all()}
    assert set(tables) == {"orders", "people", "payroll", "orders_private"}
    roles = {name: sm.find_role(name) for name in ["LEARN_Reader", *[u[2] for u in USERS]]}
    # 只检查课堂相关规则；既有 HR 实验完全不受本次验收影响。
    for rule in db.session.query(RowLevelSecurityFilter).all():
        if any(t.id in {x.id for x in tables.values()} for t in rule.tables):
            raise RuntimeError("课堂已有 RLS，请保留学习状态；改用 run.py inspect 只读检查。")
    if any(role.permissions for role in roles.values()):
        raise RuntimeError("课堂已有角色配置，请保留学习状态；本验收只在首次备课时运行。")

    checks, created, clients = [], [], {}

    def record(name, actual, expected):
        assert actual == expected, f"{name}: actual={actual!r}, expected={expected!r}"
        checks.append({"name": name, "passed": True, "actual": actual})

    def client(username):
        if username not in clients:
            session = requests.Session()
            session.trust_env = False
            session.headers["Accept"] = "application/json"
            response = session.post("http://127.0.0.1:8088/api/v1/security/login", json={
                "username": username, "password": password(username), "provider": "db", "refresh": False}, timeout=20)
            response.raise_for_status()
            session.headers["Authorization"] = "Bearer " + response.json()["access_token"]
            csrf = session.get("http://127.0.0.1:8088/api/v1/security/csrf_token/", timeout=20)
            csrf.raise_for_status()
            session.headers["X-CSRFToken"] = csrf.json()["result"]
            clients[username] = session
        return clients[username]

    def query(username, name="orders", filters=None, metrics=None, columns=None, denied=False):
        default = {"orders": ["order_id", "region", "amount", "phone_masked"],
                   "people": ["person_id", "department"], "payroll": ["person_id", "salary"],
                   "orders_private": ["order_id", "customer_phone"]}
        response = client(username).post("http://127.0.0.1:8088/api/v1/chart/data", json={
            "datasource": {"id": tables[name].id, "type": "table"}, "force": True,
            "result_format": "json", "result_type": "full", "queries": [{
                "columns": default[name] if columns is None else columns,
                "metrics": metrics or [], "filters": filters or [], "row_limit": 100,
                "orderby": [], "extras": {}}]}, timeout=30)
        if denied:
            record(f"{username} 无 {name} 数据集权限", response.status_code, 403)
            return []
        response.raise_for_status()
        result = response.json()["result"][0]
        assert not result.get("error"), result
        return result["data"]

    def grant(role_name, *names):
        roles[role_name].permissions = [sm.add_permission_view_menu("datasource_access", tables[name].get_perm())
                                        for name in names]
        db.session.commit()

    def add_rule(name, clause, table="orders", role="LEARN_East", base=False, group=None):
        rule = RowLevelSecurityFilter(name="LEARN_CHECK_" + name, clause=clause,
            filter_type=RowLevelSecurityFilterType.BASE if base else RowLevelSecurityFilterType.REGULAR,
            tables=[tables[table]], roles=[] if base else [roles[role]], group_key=group)
        db.session.add(rule)
        db.session.flush()
        created.append(rule.id)
        db.session.commit()
        return rule

    def clear_rules():
        for rule_id in created:
            rule = db.session.get(RowLevelSecurityFilter, rule_id)
            if rule:
                db.session.delete(rule)
        db.session.commit()
        created.clear()

    try:
        query("learn_east", denied=True)
        grant("LEARN_Reader", "orders")
        rows = query("learn_east")
        record("只授数据集、未加RLS：12笔", len(rows), 12)
        record("初始合计", sum(r["amount"] for r in rows), 78000)
        record("公共出口只返回脱敏电话", all("****" in r["phone_masked"] for r in rows), True)
        east = add_rule("east", "region = 'EAST'")
        record("Regular华东范围", sorted(r["order_id"] for r in query("learn_east")), EXPECTED["east_order_ids"])
        record("Regular不会自动保护其他角色", len(query("learn_west")), 12)
        record("业务过滤不能扩大RLS", query("learn_east", filters=[{"col": "region", "op": "==", "val": "WEST"}]), [])
        metric = {"expressionType": "SIMPLE", "column": {"column_name": "amount"}, "aggregate": "SUM", "label": "total"}
        record("聚合在行过滤后计算", query("learn_east", metrics=[metric], columns=[])[0]["total"], 21000)
        public = add_rule("public", "classification = 'PUBLIC'")
        record("不同组取交集", sorted(r["order_id"] for r in query("learn_east")), EXPECTED["east_public_ids"])
        east.group_key = public.group_key = "classroom_or"
        db.session.commit()
        record("同组取并集", len(query("learn_east")), 10)
        clear_rules()
        add_rule("own", "owner_id IN (SELECT person_id FROM learn_auth.identity_map WHERE superset_user_id = {{ current_user_id() }})", base=True)
        record("可信当前用户匹配本人订单", sorted(r["order_id"] for r in query("learn_east")), EXPECTED["own_east_ids"])
        record("未映射账号动态规则返回0行", len(query("learn_unmapped")), 0)
        clear_rules()
        add_rule("regions", "region IN (SELECT region FROM learn_auth.user_regions WHERE superset_user_id = {{ current_user_id() }})", base=True)
        for user, count in [("learn_east", 6), ("learn_west", 3), ("learn_manager", 9), ("learn_unmapped", 0)]:
            record(f"动态多区域：{user}", len(query(user)), count)
        clear_rules()
        grant("LEARN_Reader", "orders", "people")
        add_rule("reports", "person_id IN (SELECT target_id FROM learn_auth.visible_people WHERE superset_user_id = {{ current_user_id() }})", table="people", base=True)
        for user, ids in [("learn_east", ["E"]), ("learn_manager", EXPECTED["manager_people"]),
                          ("learn_hrbp", EXPECTED["hrbp_people"]), ("learn_hrlead", EXPECTED["hrlead_people"]),
                          ("learn_unmapped", [])]:
            record(f"汇报与服务范围：{user}", sorted(r["person_id"] for r in query(user, "people")), ids)
        filtered = query("learn_manager", "people", filters=[{"col": "department", "op": "==", "val": "华东销售部"}])
        record("部门与汇报范围取交集", sorted(r["person_id"] for r in filtered), EXPECTED["manager_department_people"])
        query("learn_east", "payroll", denied=True)
        grant("LEARN_Finance", "payroll", "orders_private")
        record("单独授权敏感数据集", len(query("learn_finance", "payroll")), 12)
        record("财务可读取完整模拟电话", query("learn_finance", "orders_private")[0]["customer_phone"].startswith("000"), True)
        query("learn_east", "orders_private", denied=True)
        # 这里直接使用公共数据库账号，证明禁止读取不是前端隐藏造成的。
        conn = psycopg2.connect(host="postgres", dbname="hr_lab", user="learn_public_reader",
                                password=password("learn_public_reader"))
        try:
            for statement in ["SELECT * FROM learn_data.orders", "SELECT salary FROM learn_api.payroll",
                              "SELECT customer_phone FROM learn_api.orders_private"]:
                try:
                    with conn, conn.cursor() as cur:
                        cur.execute(statement)
                    raise AssertionError("公共连接意外读到了敏感对象")
                except psycopg2.errors.InsufficientPrivilege:
                    record("数据库拒绝：" + statement, True, True)
        finally:
            conn.close()
        grant("LEARN_Reader")
        query("learn_east", denied=True)
    finally:
        # 即使测试中途失败，也尽力撤回本次授予的角色和临时 RLS。
        db.session.rollback()
        clear_rules()
        for role in roles.values():
            role.permissions = []
        db.session.commit()
        for session in clients.values():
            session.close()
    record("课堂空角色已恢复", all(not role.permissions for role in roles.values()), True)
    print(json.dumps({"tested_at": datetime.now(timezone.utc).isoformat(), "passed": True,  # noqa: UP017 -- Superset镜像Python3.10
        "check_count": len(checks), "checks": checks, "handoff": "空业务角色、无课堂RLS，留给学生手填",
        "scope": "真实Superset REST及PostgreSQL；未接真实SSO，不是生产性能验收"}, ensure_ascii=False))


if __name__ == "__main__":
    with create_app().app_context():
        main()
