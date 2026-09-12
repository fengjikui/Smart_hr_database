from backend.hr.db import business
from backend.hr.validate import validate


def test_all_data_invariants():
    report=validate()
    assert report['passed'],report['checks']
    assert report['counts']['attendance_daily']>60000
    assert report['counts']['departments']==51


def test_flexible_shift_boundary():
    with business() as db:
        snapshot=db.execute("SELECT value FROM dataset_meta WHERE key='as_of'").fetchone()[0]
        row=db.execute('SELECT * FROM attendance_daily WHERE employee_id=52 AND day=?',(snapshot,)).fetchone()
        assert row['check_in']==570
        assert row['check_out']==1110
        assert row['late_minutes']==0
        assert row['early_minutes']==0
        assert row['late_departure_minutes']==0
