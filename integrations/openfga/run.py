"""OpenFGA 课堂命令：材料→建库→种子→发布；每个动作可以单独学习。

同步不会更新线上 store 的一部分 tuple：先创建完整的新 store，写完并验证后
才在 PostgreSQL 提交 active 指针。源数据变化未同步时，在线查询拒绝继续。
"""

import argparse
import hashlib
import json
import os
import re
import secrets
import time
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from backend.hr import fga_client, store
from backend.hr.schema import FIELDS
from integrations.openfga.model import compile_model

ROOT = Path(__file__).resolve().parent
LOCAL = ROOT / ".local"
CAPABILITIES = [
    "reports",
    "hrbp",
    "inherit_hrbp",
    "details",
    "export",
    "basic",
    "education",
    "employment",
    "contract",
]


def private(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    fd = os.open(path, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w") as out:
        out.write(value)


def settings():
    return json.loads((LOCAL / "admin.json").read_text())


def prepare():
    if not (LOCAL / "admin.json").exists():
        password, reader, key = (secrets.token_hex(24) for _ in range(3))
        shared = {"fga_url": "http://127.0.0.1:8089", "fga_key": key}
        pg = {"host": "127.0.0.1", "port": 55433, "dbname": "hr_openfga"}
        private(
            LOCAL / "admin.json",
            json.dumps({**shared, "pg": {**pg, "user": "postgres", "password": password}}),
        )
        private(
            LOCAL / "runtime.json",
            json.dumps({**shared, "pg": {**pg, "user": "hr_fga_reader", "password": reader}}),
        )
        private(
            LOCAL / "lab.env",
            "\n".join(
                [
                    "POSTGRES_PASSWORD=" + password,
                    "POSTGRES_DB=postgres",
                    "OPENFGA_DATASTORE_ENGINE=postgres",
                    f"OPENFGA_DATASTORE_URI=postgres://postgres:{password}@postgres:5432/postgres?sslmode=disable",
                    "OPENFGA_AUTHN_METHOD=preshared",
                    "OPENFGA_AUTHN_PRESHARED_KEYS=" + key,
                    "",
                ]
            ),
        )
    private(LOCAL / "model.json", json.dumps(compile_model(), indent=2))
    print("本机凭据与模型材料就绪；尚未创建业务库/关系。")


def admin():
    return psycopg.connect(**settings()["pg"], row_factory=dict_row)


def view_statement():
    """生成受控视图定义；手工材料与初始化共享同一个生成器。"""
    projections = []
    for field, info in FIELDS.items():
        value = sql.SQL("record->>{}").format(sql.Literal(field))
        if field == "age":
            value = sql.SQL("({})::integer").format(value)
        projections.append(
            sql.SQL(
                "CASE WHEN COALESCE(NULLIF(current_setting('hr.groups',true),''),'[]')::jsonb ? {} THEN {} END AS {}"
            ).format(sql.Literal(info[1]), value, sql.Identifier(field))
        )
    return sql.SQL(
        "CREATE VIEW hr_api.people WITH (security_barrier=true) AS SELECT {} FROM hr_data.people"
    ).format(sql.SQL(",").join(projections))


def materials():
    """只写私有 SQL 材料，不连接数据库、不创建对象；给手工学习使用。"""
    prepare()
    out = LOCAL / "learning"
    private(out / "01_database.sql", "CREATE DATABASE hr_openfga;\n")
    private(
        out / "02_schema.sql",
        "\\set ON_ERROR_STOP on\nBEGIN;\n" + (ROOT / "schema.sql").read_text() + "\nCOMMIT;\n",
    )
    private(
        out / "03_view.sql",
        "\\set ON_ERROR_STOP on\nBEGIN;\n"
        + view_statement().as_string()
        + ";\nALTER VIEW hr_api.people OWNER TO hr_fga_view_owner;\nGRANT SELECT ON hr_api.people TO hr_fga_reader;\nCOMMIT;\n",
    )
    runtime = json.loads((LOCAL / "runtime.json").read_text())
    private(
        out / "04_reader.sql",
        sql.SQL("ALTER ROLE hr_fga_reader LOGIN PASSWORD {};\n")
        .format(sql.Literal(runtime["pg"]["password"]))
        .as_string(),
    )
    statements = ["\\set ON_ERROR_STOP on", "BEGIN;"]
    for row in store.generate_rows():
        statements.append(
            sql.SQL("INSERT INTO hr_source.people VALUES({},{}::jsonb);")
            .format(sql.Literal(row["person_id"]), sql.Literal(json.dumps(row, ensure_ascii=False)))
            .as_string()
        )
    for p in store.PERSONAS:
        statements.append(
            sql.SQL("INSERT INTO hr_source.identities VALUES({},{},{});")
            .format(sql.Literal(p["id"]), sql.Literal(p["person_id"]), sql.Literal(p["role"]))
            .as_string()
        )
    statements.append(
        sql.SQL("INSERT INTO hr_source.policy VALUES(true,{}::jsonb);")
        .format(sql.Literal(json.dumps(store.default_policy())))
        .as_string()
    )
    private(out / "05_seed.sql", "\n".join([*statements, "COMMIT;", ""]))
    print("已生成五份手工 SQL；包含私有密码，不提交 Git：", out)


def initialize():
    config = settings()
    with psycopg.connect(**{**config["pg"], "dbname": "postgres"}, autocommit=True) as conn:
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname='hr_openfga'").fetchone():
            conn.execute("CREATE DATABASE hr_openfga")
    with admin() as conn:
        if conn.execute("SELECT to_regclass('hr_source.people') AS value").fetchone()["value"]:
            print("业务结构已存在；未覆盖。")
            return
        conn.execute((ROOT / "schema.sql").read_text())
        conn.execute(view_statement())
        conn.execute("ALTER VIEW hr_api.people OWNER TO hr_fga_view_owner")
        conn.execute("GRANT SELECT ON hr_api.people TO hr_fga_reader")
        runtime = json.loads((LOCAL / "runtime.json").read_text())
        conn.execute(
            sql.SQL("ALTER ROLE hr_fga_reader LOGIN PASSWORD {}").format(
                sql.Literal(runtime["pg"]["password"])
            )
        )
    print("已创建独立 hr_openfga 业务库、RLS 与只读出口；未改 Superset。")


def seed():
    with admin() as conn:
        if conn.execute("SELECT count(*) AS n FROM hr_source.people").fetchone()["n"]:
            raise ValueError("源表已有数据，拒绝覆盖；修改请显式 UPDATE")
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO hr_source.people VALUES(%s,%s)",
                [(r["person_id"], Jsonb(r)) for r in store.generate_rows()],
            )
            cur.executemany(
                "INSERT INTO hr_source.identities VALUES(%s,%s,%s)",
                [(p["id"], p["person_id"], p["role"]) for p in store.PERSONAS],
            )
            cur.execute("INSERT INTO hr_source.policy VALUES(true,%s)", (Jsonb(store.default_policy()),))
    print("已插入 300 名合成员工、5 条身份映射、5 种角色配置。")


def validate(rows, identities, policy):
    """只校验事实完整性，不用 Python 算 viewer；最终授权交给 OpenFGA。"""
    if not rows or len(rows) > 1000:
        raise ValueError("本课堂支持 1～1000 人；不允许静默截断")
    lookup = {r["person_id"]: r for r in rows}
    if len(lookup) != len(rows):
        raise ValueError("人员主键重复")
    numbers = [r.get("employee_no") for r in rows if r.get("employee_no")]
    if len(numbers) != len(set(numbers)):
        raise ValueError("工号重复")
    if len({i["person_id"] for i in identities}) != len(identities):
        raise ValueError("本课堂要求一个人员只绑定一个演示账号")
    for r in rows:
        if set(r) != set(FIELDS) or not re.fullmatch(r"P[0-9]+", r["person_id"]):
            raise ValueError("人员字段或主键不符合契约")
        for field, value in r.items():
            if value is not None and (
                type(value) is not int if field == "age" else not isinstance(value, str)
            ):
                raise ValueError("字段类型不符合契约：" + field)
        if r["dept_hrbp_id"] and r["dept_hrbp_id"] not in lookup:
            raise ValueError("HRBP 引用不存在")
        path, node = [], r["person_id"]
        while node is not None:
            if node in path or node not in lookup:
                raise ValueError("主管关系成环或引用不存在")
            path.append(node)
            node = lookup[node]["head_person_id"]
            if len(path) > 30:
                raise ValueError("管理深度超过课堂上限 30，拒绝部分结果")
    for identity in identities:
        if identity["person_id"] not in lookup or identity["role_key"] not in policy["roles"]:
            raise ValueError("身份引用不存在")
        if not re.fullmatch(r"[a-z_]+", identity["persona"]):
            raise ValueError("身份名格式错误")
    for role, rule in policy["roles"].items():
        if not re.fullmatch(r"[a-z_]+", role):
            raise ValueError("角色名格式错误")
        if set(rule) != {"reports", "hrbp", "inherit_hrbp", "details", "export", "field_groups"}:
            raise ValueError("角色开关字段不完整")
        if any(type(rule[k]) is not bool for k in ["reports", "hrbp", "inherit_hrbp", "details", "export"]):
            raise ValueError("角色开关必须是布尔值")
        if (
            not set(rule["field_groups"]) <= {"basic", "education", "employment", "contract"}
            or "basic" not in rule["field_groups"]
        ):
            raise ValueError("字段组不合法")
        if rule["inherit_hrbp"] and not rule["reports"]:
            raise ValueError("继承 HRBP 需要管理线开关")


def tuples(rows, identities, policy):
    """只导入直接关系，不把间接下属预展开写入 tuple；递归由模型负责。"""
    result = []

    def add(user, relation, obj):
        result.append({"user": user, "relation": relation, "object": obj})

    for r in rows:
        obj = "person:" + r["person_id"]
        add("user:" + r["person_id"], "owner", obj)
        add("company:main", "company", obj)
        for field, relation in [("head_person_id", "manager"), ("dept_hrbp_id", "hrbp_provider")]:
            if r[field]:
                add("person:" + r[field], relation, obj)
    for identity in identities:
        add("user:" + identity["person_id"], "member", "role:" + identity["role_key"])
    for role, rule in policy["roles"].items():
        for cap in CAPABILITIES:
            if cap in rule["field_groups"] or rule.get(cap) is True:
                add("role:" + role + "#member", cap, "company:main")
    # 同一员工若对应多个入口，tuple 仍只写一次；重复写在 FGA 中会报错。
    return [
        dict(zip(("user", "relation", "object"), k, strict=True))
        for k in sorted({(r["user"], r["relation"], r["object"]) for r in result})
    ]


def sync():
    with admin() as conn:
        # 串行发布，并冻结这次读取的源表。课堂规模小；生产改成一致快照+CDC 位点。
        conn.execute("SELECT pg_advisory_xact_lock(70310921)")
        conn.execute("LOCK TABLE hr_source.people,hr_source.identities,hr_source.policy IN SHARE MODE")
        revision = conn.execute("SELECT version FROM hr_control.revision").fetchone()["version"]
        source_rows = conn.execute(
            "SELECT person_id,record FROM hr_source.people ORDER BY person_id"
        ).fetchall()
        if any(r["person_id"] != r["record"].get("person_id") for r in source_rows):
            raise ValueError("源表主键与 JSON 人员主键不一致")
        rows = [r["record"] for r in source_rows]
        identities = conn.execute("SELECT * FROM hr_source.identities ORDER BY persona").fetchall()
        policy = conn.execute("SELECT config FROM hr_source.policy").fetchone()["config"]
        validate(rows, identities, policy)
        model = compile_model()
        data = tuples(rows, identities, policy)
        digest = hashlib.sha256(
            json.dumps([rows, identities, policy, model], sort_keys=True).encode()
        ).hexdigest()
        active = conn.execute(
            "SELECT p.* FROM hr_control.publications p JOIN hr_control.active a ON p.id=a.publication"
        ).fetchone()
        if active and active["metadata"]["digest"] == digest and active["source_revision"] == revision:
            print("数据、配置、模型均未变化，无需发布。")
            return active["id"]
        with fga_client.client(settings()) as client:
            store_id = fga_client.post(client, "/stores", {"name": "hr-" + uuid4().hex[:12]})["id"]
            model_id = fga_client.post(client, f"/stores/{store_id}/authorization-models", model)[
                "authorization_model_id"
            ]
            for start in range(0, len(data), 100):
                fga_client.post(
                    client,
                    f"/stores/{store_id}/write",
                    {"authorization_model_id": model_id, "writes": {"tuple_keys": data[start : start + 100]}},
                )
            publication = {"store_id": store_id, "model_id": model_id}
            # 发布前至少验证自有记录与未映射身份；详细名单由独立集成测试核对。
            for identity in identities:
                if not fga_client.batch(
                    client,
                    publication,
                    "user:" + identity["person_id"],
                    [("viewer", "person:" + identity["person_id"])],
                )[0]:
                    raise ValueError("发布自检失败：本人不可见")
            if any(
                fga_client.batch(
                    client,
                    publication,
                    "user:unknown",
                    [("viewer", "person:" + r["person_id"]) for r in rows],
                )
            ):
                raise ValueError("发布自检失败：未知用户可见")
        generation = uuid4().hex
        metadata = {
            "digest": digest,
            "as_of": store.AS_OF,
            "policy_version": policy["version"],
            "identities": identities,
            "edges": [{k: r[k] for k in ("person_id", "head_person_id", "dept_hrbp_id")} for r in rows],
            "tuple_count": len(data),
        }
        conn.execute(
            "INSERT INTO hr_control.publications(id,source_revision,store_id,model_id,metadata) VALUES(%s,%s,%s,%s,%s)",
            (generation, revision, store_id, model_id, Jsonb(metadata)),
        )
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO hr_data.people VALUES(%s,%s,%s)",
                [(generation, r["person_id"], Jsonb(r)) for r in rows],
            )
        conn.execute(
            "INSERT INTO hr_control.active VALUES(true,%s) ON CONFLICT(singleton) DO UPDATE SET publication=excluded.publication",
            (generation,),
        )
    private(
        LOCAL / "last-publication.json",
        json.dumps({"id": generation, **publication, "metadata": metadata}, ensure_ascii=False, indent=2),
    )
    private(LOCAL / "tuples.json", json.dumps(data, ensure_ascii=False, indent=2))
    print(f"已原子发布 {generation}，{len(rows)} 人，{len(data)} 条直接关系。")
    return generation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=["prepare", "init", "seed", "sync", "status", "watch", "check", "ready", "materials"],
    )
    parser.add_argument("--interval", type=int, default=10)
    parser.add_argument("--user", default="user:P0002")
    parser.add_argument("--relation", default="viewer")
    parser.add_argument("--object", default="person:P0005")
    args = parser.parse_args()
    if args.action == "ready":
        import httpx

        with fga_client.client(settings()) as client:
            for _ in range(40):
                try:
                    if client.get("/healthz").is_success:
                        print("OpenFGA HTTP 已就绪。")
                        return
                except httpx.HTTPError:
                    pass
                time.sleep(0.5)
        raise RuntimeError("OpenFGA 未就绪，请查看服务日志")
    if args.action == "watch":
        if args.interval < 5:
            parser.error("轮询间隔不得小于 5 秒")
        while True:
            try:
                sync()
            except Exception as exc:
                print("同步失败，继续拒绝未同步版本：", type(exc).__name__, flush=True)
            time.sleep(args.interval)
    elif args.action == "check":
        from backend.hr.openfga_source import publication

        pub = publication()
        with fga_client.client(settings()) as client:
            allowed = fga_client.batch(client, pub, args.user, [(args.relation, args.object)])[0]
        print(
            json.dumps(
                {
                    "user": args.user,
                    "relation": args.relation,
                    "object": args.object,
                    "allowed": allowed,
                    "store_id": pub["store_id"],
                    "model_id": pub["model_id"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.action == "status":
        with admin() as conn:
            print(
                json.dumps(
                    conn.execute(
                        "SELECT p.id,p.store_id,p.model_id,p.source_revision,r.version AS current_revision FROM hr_control.active a JOIN hr_control.publications p ON p.id=a.publication CROSS JOIN hr_control.revision r"
                    ).fetchall(),
                    indent=2,
                )
            )
    else:
        {"prepare": prepare, "init": initialize, "seed": seed, "sync": sync, "materials": materials}[
            args.action
        ]()


if __name__ == "__main__":
    main()
