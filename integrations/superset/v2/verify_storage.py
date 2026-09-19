"""只读核验 V2 迁移与权限结构；不添加、删除、改写任何授权对象。

数据一致性使用 PostgreSQL 实际读取的完整宽表重新计算指纹，而不是相信
snapshot 元数据里的声明。数据库权限也用实际只读账号执行 SELECT 反例验证。
"""

import hashlib
import json
from datetime import datetime, timezone

import psycopg2
from setup import LOCAL, password, pg, read_fixture
from superset.app import create_app


def legacy_snapshot(db, sm, RowLevelSecurityFilter):
    """按首次安装前相同格式盘点旧实验与学生练习，确保没有覆盖已有配置。"""
    prefixes = ("LEARN_", "HR_LAB_")
    return {
        "roles": {r.name: sorted(str(p) for p in r.permissions)
                  for r in db.session.query(sm.role_model).all() if r.name.startswith(prefixes)},
        "rules": {r.name: {"clause": r.clause, "group": r.group_key,
                           "roles": sorted(x.name for x in r.roles),
                           "tables": sorted(t.id for t in r.tables),
                           "type": getattr(r.filter_type, "value", r.filter_type)}
                  for r in db.session.query(RowLevelSecurityFilter).all() if r.name.startswith(prefixes)},
    }


def main():
    from superset import db
    from superset import security_manager as sm
    from superset.connectors.sqla.models import RowLevelSecurityFilter, SqlaTable
    from superset.models.core import Database

    fixture = read_fixture()
    checks = []

    def check(name, actual, expected):
        if actual != expected:
            raise AssertionError(f"{name}: actual={actual!r}, expected={expected!r}")
        checks.append({"name": name, "passed": True, "actual": actual})

    conn = pg()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM v2_data.people ORDER BY person_id")
            fields = [c.name for c in cur.description]
            rows = [dict(zip(fields, row, strict=True)) for row in cur.fetchall()]
            check("全量宽表列顺序与原 V2 相同", fields, [f["id"] for f in fixture["fields"]])
            check("全量人员行数与导出一致", len(rows), len(fixture["people"]))
            check("当前标准演示完整 300 人", len(rows), 300)
            check("当前标准演示完整 26 字段", len(fields), 26)
            check("工号前导零仍保留", next(r["employee_no"] for r in rows if r["person_id"] == "P0005"), "00031266")
            fingerprint = hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            check("PostgreSQL 逐字段完整快照 SHA-256 与 SQLite 导出一致", fingerprint, fixture["data_fingerprint"])
            cur.execute("SELECT data_fingerprint,as_of FROM v2_auth.snapshot")
            stored = cur.fetchone()
            check("数据库元数据记录实际指纹与快照日", list(stored), [fingerprint, fixture["as_of"]])
            cur.execute("SELECT graph_valid FROM v2_auth.graph_health")
            check("管理线及 HRBP 图无环且无孤儿", cur.fetchone()[0], True)
    finally:
        conn.close()

    # 使用读者实际连接执行越权 SELECT；不能把任何 SQL 错误都视为权限拒绝。
    for level in ["public", "contract"]:
        username = "v2_" + level + "_reader"
        reader = psycopg2.connect(host="postgres", dbname="hr_v2", user=username, password=password(username))
        try:
            statements = ["SELECT * FROM v2_data.people", "SELECT * FROM v2_auth.identity_map",
                          "SELECT * FROM v2_auth.role_policy"]
            if level == "public":
                statements += ["SELECT contract_end_date FROM v2_api.people_contract",
                               "SELECT contract_end_date FROM v2_api.events_contract"]
            for statement in statements:
                try:
                    with reader, reader.cursor() as cur:
                        cur.execute(statement)
                    raise AssertionError(f"{username} 意外可读取 {statement}")
                except psycopg2.errors.InsufficientPrivilege:
                    check(f"{username} 数据库权限拒绝：{statement}", True, True)
            with reader, reader.cursor() as cur:
                cur.execute(f"SELECT * FROM v2_api.people_{level} LIMIT 0")
                names = [c.name for c in cur.description]
                check(f"{level} 出口合同列物理隔离", "contract_end_date" in names, level == "contract")
                cur.execute("SHOW default_transaction_read_only")
                check(f"{username} 默认只读", cur.fetchone()[0], "on")
        finally:
            reader.close()

    roles = [r for r in db.session.query(sm.role_model).all() if r.name.startswith("V2_")]
    role_names = {"V2_Data_public", "V2_Data_contract", "V2_Context",
                  *["V2_Role_" + p["role"] for p in fixture["personas"]]}
    check("8 个 V2 自定义角色", sorted(r.name for r in roles), sorted(role_names))
    users = [u for u in db.session.query(sm.user_model).all() if u.username.startswith("v2_")]
    usernames = ["v2_setup_admin", "v2_unmapped", *["v2_" + p["id"] for p in fixture["personas"]]]
    check("7 个 V2 独立账号", sorted(u.username for u in users), sorted(usernames))
    forbidden_roles = {"Admin", "Alpha", "sql_lab"}
    forbidden_permissions = {"database_access", "all_datasource_access", "all_database_access", "can_sqllab"}
    for user in users:
        if user.username == "v2_setup_admin":
            check("配置管理员与业务身份分离", "Admin" in {r.name for r in user.roles}, True)
            continue
        check(f"{user.username} 不含超级角色或 SQL Lab 角色",
              sorted({r.name for r in user.roles} & forbidden_roles), [])
        check(f"{user.username} 不含数据库全访问、全数据集或 SQL Lab 权限",
              sorted({p.permission.name for r in user.roles for p in r.permissions} & forbidden_permissions), [])

    tables = db.session.query(SqlaTable).join(Database).filter(Database.database_name.in_(
        ["V2_public", "V2_contract"])).all()
    check("5 个注册物理视图数据集", sorted(t.table_name for t in tables),
          ["context", "events_contract", "events_public", "people_contract", "people_public"])
    check("数据集没有附加自定义虚拟 SQL", all(not t.sql for t in tables), True)
    table_by_name = {t.table_name: t for t in tables}
    rules = [r for r in db.session.query(RowLevelSecurityFilter).all() if r.name.startswith("V2_")]
    expected_rules = {
        "V2_scope_public": (["people_public", "events_public"], "_viewer_id = {{ current_user_id() }}"),
        "V2_scope_contract": (["people_contract", "events_contract"], "_viewer_id = {{ current_user_id() }}"),
        "V2_context_scope": (["context"], "superset_user_id = {{ current_user_id() }}"),
    }
    check("3 条 V2 RLS", sorted(r.name for r in rules), sorted(expected_rules))
    for rule in rules:
        names, clause = expected_rules[rule.name]
        check(rule.name + " 是 Base 且无豁免角色",
              (getattr(rule.filter_type, "value", rule.filter_type), len(rule.roles)), ("Base", 0))
        check(rule.name + " 精确绑定预期数据集", sorted(t.id for t in rule.tables),
              sorted(table_by_name[n].id for n in names))
        check(rule.name + " 使用可信登录 ID", rule.clause, clause)
        check(rule.name + " 未加入可放宽的 OR 组", bool(rule.group_key), False)

    baseline = LOCAL / "existing-permissions-before.txt"
    if baseline.exists():
        before = json.loads(baseline.read_text().strip().splitlines()[-1])
        current = legacy_snapshot(db, sm, RowLevelSecurityFilter)
        check("旧 HR 实验和课堂学生角色/RLS 配置完全保留", current, before)
        # 报告不重复写整份旧权限列表；只保留验证结论与对象数即可。
        checks[-1]["actual"] = {"roles": len(current["roles"]), "rules": len(current["rules"])}
    else:
        checks.append({"name": "旧课堂配置快照比较", "skipped": True,
                       "reason": "没有安装前快照；CI 新环境允许跳过这一项"})
    print(json.dumps({"passed": True, "checked_at": datetime.now(timezone.utc).isoformat(),  # noqa: UP017
                      "check_count": sum(c.get("passed", False) for c in checks),
                      "checks": checks}, ensure_ascii=False))


if __name__ == "__main__":
    with create_app().app_context():
        main()
