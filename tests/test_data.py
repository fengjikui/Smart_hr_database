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
