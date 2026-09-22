"""宿主机手工学习助手：只生成本机文件、只读盘点，不替用户初始化数据库。

prepare 生成待审阅 SQL 和私有凭据；inventory 读取真实 ID；mapping 生成待执行
映射 SQL；bind 核对已完成的映射并写 Agent 清单。均不移除手工学习标记。
"""
import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path

from run import LOCAL, container_command, read_seed, write_database_credentials, write_private_json

OUTPUT = LOCAL / "learning"


def literal(value):
    """只为固定可信合成材料编码值；生成 SQL 的字符串引号必须转义。"""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    return "'" + value.replace("'", "''") + "'"


def write_sql(name, value):
    OUTPUT.mkdir(parents=True, exist_ok=True, mode=0o700)
    OUTPUT.chmod(0o700)
    path = OUTPUT / name
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(value + "\n")
    return path


def load_fixture():
    fixture = json.loads((LOCAL / "fixtures.json").read_text())
    digest = hashlib.sha256(json.dumps(fixture["people"], ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    if digest != fixture["data_fingerprint"]:
        raise ValueError("原样本指纹不符，停止生成材料")
    # 导入结构以程序词汇表为准，防止材料出现任意表名/列名。
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from backend.hr.schema import FIELDS
    if [f["id"] for f in fixture["fields"]] != list(FIELDS):
        raise ValueError("样本字段与代码不一致")
    if len(fixture["people"]) != 300 or any(set(p) != set(FIELDS) for p in fixture["people"]):
        raise ValueError("此手册要求完整 300 人样本")
    return fixture


def import_sql(fixture):
    """这段脚本只在用户手工执行时写库；三条教学记录整体替换成完整快照。"""
    columns = [f["id"] for f in fixture["fields"]]
    out = ["-- 用完整 300 人替换课堂三条部分记录；没有改动 identity_map。",
           "\\set ON_ERROR_STOP on", "SET standard_conforming_strings = on;", "BEGIN;",
           "DELETE FROM v2_data.people;", "INSERT INTO v2_data.people (" + ",".join(columns) + ") VALUES"]
    out.append(",\n".join("(" + ",".join(literal(row[c]) for c in columns) + ")" for row in fixture["people"]) + ";")
    out += ["-- 角色策略也恢复为原五种角色；覆盖课堂 manager 配置。", "DELETE FROM v2_auth.role_policy;"]
    for role, rule in fixture["policy"]["roles"].items():
        values = [role, rule["reports"], rule["hrbp"], rule["inherit_hrbp"], rule["field_groups"],
                  rule["details"], rule["export"], fixture["policy"]["version"]]
        out.append("INSERT INTO v2_auth.role_policy VALUES (" + ",".join(map(literal, values)) + ");")
    out += ["DELETE FROM v2_auth.snapshot;", "INSERT INTO v2_auth.snapshot VALUES (" + ",".join(map(literal,
        [True, fixture["as_of"], fixture["data_fingerprint"], fixture["data_version"], fixture["fields"]])) + ");"]
    for field in fixture["fields"]:
        description = f"{field['label']}；字段组={field['group']}；{field['description']}"
        out.append(f"COMMENT ON COLUMN v2_data.people.{field['id']} IS {literal(description)};")
    for key in ["head_person_id", "dept_hrbp_id", "dept_cn_name", "onboard_date", "termin_date"]:
        out.append(f"CREATE INDEX IF NOT EXISTS v2_people_{key} ON v2_data.people({key});")
    out += ["DO $$ BEGIN IF NOT (SELECT graph_valid FROM v2_auth.graph_health) THEN",
            "RAISE EXCEPTION '组织关系异常，导入必须回滚'; END IF; END $$;", "COMMIT;"]
    return "\n".join(out)


def prepare():
    # 生成凭据文件不是创建账号；CREATE ROLE/建视图/导入数据都留待手工执行。
    # setdefault 保留已有平台密码，不因重新生成学习材料而替换登录资料。
    fixture = load_fixture()
    seed = read_seed()
    credentials_path = LOCAL / "credentials.json"
    credentials = json.loads(credentials_path.read_text()) if credentials_path.exists() else {}
    for name in ["v2_setup_admin", "v2_unmapped", *["v2_" + p["id"] for p in fixture["personas"]]]:
        credentials.setdefault(name, hmac.new(seed.encode(), name.encode(), hashlib.sha256).hexdigest()[:24])
    write_private_json(credentials_path, credentials)
    write_database_credentials()
    write_sql("22_import.sql", import_sql(fixture))
    # 容器内 Recorder 只收集 create_people_views 生成的 SQL，不执行 CREATE VIEW。
    # 因此自动初始化与手工材料复用同一份视图定义，减少两套口径漂移。
    views = container_command("learning_inspect.py", "views")
    write_sql("23_views.sql", "\\set ON_ERROR_STOP on\nBEGIN;\n" + "\n\n".join(views) + "\nCOMMIT;")
    connections = json.loads((LOCAL / "database-credentials.json").read_text())
    access = ["-- 包含本机密码，禁止提交/分享。角色首次创建时执行一次。",
              "\\set ON_ERROR_STOP on", "BEGIN;", "REVOKE ALL ON DATABASE hr_v2 FROM PUBLIC;"]
    for level, connection in connections.items():
        user = connection["username"]
        access += [f"CREATE ROLE {user} LOGIN PASSWORD {literal(connection['password'])};",
            f"GRANT CONNECT ON DATABASE hr_v2 TO {user};",
            f"GRANT USAGE ON SCHEMA v2_api TO {user};",
            f"GRANT SELECT ON v2_api.people_{level},v2_api.events_{level} TO {user};",
            f"ALTER ROLE {user} SET default_transaction_read_only=on;",
            f"ALTER ROLE {user} SET statement_timeout='10s';"]
    access += ["GRANT SELECT ON v2_api.context TO v2_public_reader;", "COMMIT;"]
    write_sql("24_access.sql", "\n".join(access))
    print("仅生成材料，未导入数据库、未创建用户：", OUTPUT)
    print("SQL 共 3 份；登录资料在 credentials.json，连接资料在 database-credentials.json。")


def mapping_sql(fixture, actual):
    # actual 来自平台实时盘点；账号 ID 只有真正创建用户后才知道。
    # 输出是待执行的 INSERT 文件，不直接把身份写入业务数据库。
    lines = ["-- ID 取自本次实际平台配置；请核对后手工执行。", "\\set ON_ERROR_STOP on", "BEGIN;"]
    for persona in fixture["personas"]:
        username = "v2_" + persona["id"]
        if username not in actual["users"]:
            raise ValueError("缺少业务用户：" + username)
        user_id = actual["users"][username]["id"]
        if type(user_id) is not int or user_id <= 0:
            raise ValueError("平台用户 ID 无效")
        values = [user_id, username, persona["id"], persona["person_id"], persona["role"]]
        # 故意不静默 upsert，重复执行或绑定冲突应先核对，不猜哪个映射正确。
        lines.append("INSERT INTO v2_auth.identity_map VALUES (" + ",".join(map(literal, values)) + ");")
    return "\n".join([*lines, "COMMIT;"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "inventory", "mapping", "bind"])
    args = parser.parse_args()
    if args.action == "prepare":
        prepare()
    elif args.action in ("inventory", "mapping"):
        actual = container_command("learning_inspect.py", "inventory")
        write_private_json(OUTPUT / "inventory.json", actual)
        if args.action == "mapping":
            print(write_sql("31_identity.sql", mapping_sql(load_fixture(), actual)))
        else:
            print(json.dumps(actual, ensure_ascii=False, indent=2))
    else:
        # bind 仅将已核对的实际对象 ID 写给 Agent；不授予新权限，也不解除学习锁。
        result = container_command("learning_inspect.py", "binding")
        write_private_json(LOCAL / "manifest.json", result)
        print("已核对并保存 Agent 清单；未修改权限、未解除学习标记：", LOCAL / "manifest.json")


if __name__ == "__main__":
    main()
