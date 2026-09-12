from backend.hr.db import business
from backend.hr.validate import validate


def test_all_data_invariants():
    report = validate()
    assert report["passed"], report["checks"]
    assert report["counts"]["attendance_daily"] > 60000
    assert report["counts"]["departments"] == 51


def test_flexible_shift_boundary():
    with business() as db:
        snapshot = db.execute("SELECT value FROM dataset_meta WHERE key='as_of'").fetchone()[0]
        row = db.execute(
            "SELECT * FROM attendance_daily WHERE employee_id=52 AND day=?", (snapshot,)
        ).fetchone()
        assert row["check_in"] == 570
        assert row["check_out"] == 1110
        assert row["late_minutes"] == 0
        assert row["early_minutes"] == 0
        assert row["late_departure_minutes"] == 0


def test_seed_is_reproducible_and_nonuniform(tmp_path):
    import hashlib

    from backend.hr.seed import generate

    first = tmp_path / "a"
    second = tmp_path / "b"
    generate(first, size=120, seed=42)
    generate(second, size=120, seed=42)
    assert (
        hashlib.sha256((first / "hr.sqlite").read_bytes()).digest()
        == hashlib.sha256((second / "hr.sqlite").read_bytes()).digest()
    )
    with business(first / "hr.sqlite") as db:
        counts = [
            r[0]
            for r in db.execute(
                "SELECT COUNT(*) FROM assignments a JOIN departments d ON d.id=a.department_id WHERE a.valid_to IS NULL AND d.division_id IS NOT NULL GROUP BY d.division_id"
            )
        ]
    assert len(set(counts)) > 1


def test_validator_detects_corrupt_business_rule(tmp_path):
    import sqlite3

    target = tmp_path / "corrupt.sqlite"
    with business() as source:
        dest = sqlite3.connect(target)
        source.backup(dest)
    dest.execute("UPDATE attendance_daily SET late_minutes=late_minutes+10 WHERE id=1")
    dest.commit()
    dest.close()
    report = validate(target)
    assert not report["passed"]
    assert any("迟到分钟" in c["name"] and not c["passed"] for c in report["checks"])


def test_upgrade_backs_up_both_databases_and_preserves_application(tmp_path, monkeypatch):
    import sqlite3

    from backend.hr import config
    from backend.hr.seed import generate, upgrade_demo_data

    generate(tmp_path, size=120, seed=42)
    with sqlite3.connect(tmp_path / "hr.sqlite") as db:
        db.execute("DELETE FROM dataset_meta WHERE key='data_version'")
    with sqlite3.connect(tmp_path / "app.sqlite") as db:
        db.execute(
            "INSERT INTO dashboards VALUES ('preserved','ceo','我的看板','{}','hr-metrics-1.0','2026-09-11')"
        )
    monkeypatch.setattr(config, "BUSINESS_DB", tmp_path / "hr.sqlite")
    monkeypatch.setattr(config, "APP_DB", tmp_path / "app.sqlite")
    upgrade_demo_data()
    assert len(list((tmp_path / "backups").glob("hr-before-*.sqlite"))) == 1
    assert len(list((tmp_path / "backups").glob("app-before-*.sqlite"))) == 1
    assert validate(tmp_path / "hr.sqlite")["passed"]
    with sqlite3.connect(tmp_path / "app.sqlite") as db:
        assert db.execute("SELECT title FROM dashboards WHERE id='preserved'").fetchone()[0] == "我的看板"
    assert upgrade_demo_data() is None
    assert len(list((tmp_path / "backups").glob("*.sqlite"))) == 2


def test_validator_rejects_invalid_education_and_weekend_hours(tmp_path):
    import sqlite3

    target = tmp_path / "invalid_education.sqlite"
    with business() as db:
        copy = sqlite3.connect(target)
        db.backup(copy)
    copy.execute("UPDATE employees SET highest_degree='未知' WHERE id=1")
    copy.execute(
        "UPDATE employee_education SET graduation_date='2030-09-11' WHERE id=(SELECT MAX(id) FROM employee_education WHERE employee_id=1)"
    )
    copy.execute(
        "UPDATE overtime_requests SET minutes=10000 WHERE id=(SELECT MIN(id) FROM overtime_requests WHERE day_type='周末')"
    )
    copy.commit()
    copy.close()
    report = validate(target)
    failed = [c["name"] for c in report["checks"] if not c["passed"]]
    assert any("快照" in x for x in failed)
    assert any("入职前" in x for x in failed)
    assert any("周末加班申请" in x for x in failed)
