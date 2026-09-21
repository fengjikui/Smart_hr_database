"""在临时数据库里执行手工 SQL，检查文档材料可运行，最后删除自建测试对象。"""

import json
import os

import psycopg
from psycopg import sql

from integrations.openfga import run


def main():
    run.materials()
    suffix = str(os.getpid())
    name, reader, owner = "fga_lesson_" + suffix, "fga_reader_" + suffix, "fga_owner_" + suffix
    pg = run.settings()["pg"]
    checks = []
    with psycopg.connect(**{**pg, "dbname": "postgres"}, autocommit=True) as maintenance:
        maintenance.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            with psycopg.connect(**{**pg, "dbname": name}, autocommit=True) as conn:
                for filename in ["02_schema.sql", "03_view.sql", "05_seed.sql"]:
                    text = (run.LOCAL / "learning" / filename).read_text()
                    text = "\n".join(line for line in text.splitlines() if not line.startswith("\\"))
                    text = (
                        text.replace("hr_openfga", name)
                        .replace("hr_fga_view_owner", owner)
                        .replace("hr_fga_reader", reader)
                    )
                    conn.execute(text)
                    checks.append("执行 " + filename)
                assert conn.execute("SELECT count(*) FROM hr_source.people").fetchone()[0] == 300
                checks.append("完整导入300人")
                conn.execute(
                    "INSERT INTO hr_control.publications VALUES('lesson',0,'store','model','{}',now())"
                )
                conn.execute(
                    "INSERT INTO hr_data.people SELECT 'lesson',person_id,record FROM hr_source.people"
                )
                conn.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(reader)))
                assert conn.execute("SELECT count(*) FROM hr_api.people").fetchone()[0] == 0
                checks.append("无上下文默认空")
                with conn.transaction():
                    for key, value in [
                        ("generation", "lesson"),
                        ("allowed_ids", '["P0005"]'),
                        ("groups", '["basic"]'),
                    ]:
                        conn.execute("SELECT set_config(%s,%s,true)", ("hr." + key, value))
                    rows = conn.execute("SELECT person_id,contract_end_date FROM hr_api.people").fetchall()
                    assert rows == [("P0005", None)]
                assert conn.execute("SELECT count(*) FROM hr_api.people").fetchone()[0] == 0
                checks.append("行列约束及事务结束自动清除")
        finally:
            maintenance.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
            for role in [reader, owner]:
                maintenance.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))
    from backend.hr.config import PROJECT

    target = PROJECT / "reports/openfga-materials.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(
        json.dumps(
            {"passed": True, "checks": checks, "temporary_objects_removed": True},
            ensure_ascii=False,
            indent=2,
        )
    )
    print(f"手工材料 {len(checks)} 项通过，临时对象已删除。")


if __name__ == "__main__":
    main()
