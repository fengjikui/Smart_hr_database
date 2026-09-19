"""Deterministic synthetic company. No real personal data is imported."""

import argparse
import json
import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from . import config

# V1 多表合成公司，默认 480 人，包含任职历史、教育经历和考勤；不是 V2 的 300 人宽表。
# 固定随机种子与快照日用于复现，真实业务数据不经过这个生成器。
DIVISIONS = [
    ("产品研发事业部", ["平台研发部", "智能产品部", "质量工程部"]),
    ("客户增长事业部", ["品牌市场部", "企业销售部", "客户成功部"]),
    ("运营交付事业部", ["项目交付部", "服务运营部", "解决方案部"]),
    ("人力与组织中心", ["人才发展部", "人力运营部", "招聘配置部"]),
    ("财务与合规中心", ["财务管理部", "经营分析部", "合规风控部"]),
]
PERSONAS = [
    {
        "id": "ceo",
        "employee_id": 1,
        "role": "executive",
        "label": "林知远 · 总经理",
        "title": "公司负责人",
        "scope_mode": "reports",
        "scope_root": 1,
        "salary_aggregate": True,
        "can_export": True,
    },
    {
        "id": "rd",
        "employee_id": 2,
        "role": "manager",
        "label": "陈嘉宁 · 研发负责人",
        "title": "产品研发事业部负责人",
        "scope_mode": "reports",
        "scope_root": 2,
        "salary_aggregate": False,
        "can_export": False,
    },
    {
        "id": "team",
        "employee_id": 22,
        "role": "manager",
        "label": "周予安 · 平台一组主管",
        "title": "平台研发一组主管",
        "scope_mode": "reports",
        "scope_root": 22,
        "salary_aggregate": False,
        "can_export": False,
    },
    {
        "id": "hrbp",
        "employee_id": 5,
        "role": "hrbp",
        "label": "沈亦舒 · HRBP",
        "title": "研发业务 HRBP",
        "scope_mode": "organization",
        "scope_root": 2,
        "salary_aggregate": False,
        "can_export": True,
    },
    {
        "id": "employee",
        "employee_id": 52,
        "role": "employee",
        "label": "许明澈 · 员工",
        "title": "平台开发工程师",
        "scope_mode": "self",
        "scope_root": 52,
        "salary_aggregate": False,
        "can_export": False,
    },
]


def initialize_app(path: Path, reset=False):
    # 默认保留已有会话和看板；显式 reset 才重建应用状态，和重造业务事实分开控制。
    from .debug import ensure_schema

    if path.exists() and not reset:
        ensure_schema(path)
        return
    if path.exists():
        path.unlink()
    db = sqlite3.connect(path)
    db.executescript("""
    PRAGMA journal_mode=WAL;
    CREATE TABLE principals(id TEXT PRIMARY KEY, employee_id INTEGER NOT NULL, role TEXT NOT NULL, label TEXT NOT NULL, title TEXT NOT NULL, scope_mode TEXT NOT NULL, scope_root INTEGER NOT NULL, salary_aggregate INTEGER NOT NULL, can_export INTEGER NOT NULL, enabled INTEGER NOT NULL DEFAULT 1, policy_version INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE sessions(token_hash TEXT PRIMARY KEY, principal_id TEXT NOT NULL REFERENCES principals(id), csrf TEXT NOT NULL, expires_at REAL NOT NULL);
    CREATE TABLE metrics(id TEXT PRIMARY KEY, definition TEXT NOT NULL, version TEXT NOT NULL);
    CREATE VIRTUAL TABLE metric_search USING fts5(id UNINDEXED, content, tokenize='trigram');
    CREATE TABLE dashboards(id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES principals(id), title TEXT NOT NULL, plan TEXT NOT NULL, catalog_version TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE audit_events(id TEXT PRIMARY KEY, principal_id TEXT NOT NULL, action TEXT NOT NULL, outcome TEXT NOT NULL, metric_id TEXT, scope_count INTEGER, policy_version TEXT NOT NULL, duration_ms REAL NOT NULL, created_at TEXT NOT NULL);
    CREATE INDEX idx_audit_principal ON audit_events(principal_id,created_at);
    CREATE TABLE conversations(id TEXT PRIMARY KEY, principal_id TEXT NOT NULL, question TEXT NOT NULL, plan TEXT, outcome TEXT NOT NULL, created_at TEXT NOT NULL);
    """)
    for p in PERSONAS:
        keys = list(p)
        db.execute(
            f"INSERT INTO principals({','.join(keys)}) VALUES ({','.join('?' for _ in keys)})",
            [p[k] for k in keys],
        )
    catalog = json.loads(config.CATALOG_PATH.read_text())
    for m in catalog["metrics"]:
        db.execute(
            "INSERT INTO metrics VALUES (?,?,?)",
            (m["id"], json.dumps(m, ensure_ascii=False), catalog["version"]),
        )
        db.execute(
            "INSERT INTO metric_search VALUES (?,?)",
            (m["id"], " ".join([m["name"], m["description"], *m["aliases"]])),
        )
    db.commit()
    db.close()
    ensure_schema(path)


def generate(
    directory: Path = config.DATA_DIR,
    seed: int = 20260911,
    size: int = 480,
    as_of: str = config.DEMO_DATE,
    reset_app=False,
):
    # 先写临时 hr.seed.sqlite，完成一致性校验后原子替换业务库；失败不发布半成品。
    if size < 100 or size > 10000:
        raise ValueError("员工数量应为 100–10000")
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "hr.sqlite"
    staging = directory / "hr.seed.sqlite"
    if staging.exists():
        staging.unlink()
    rng = random.Random(seed)
    snapshot = date.fromisoformat(as_of)
    first_day = snapshot.replace(month=1, day=1)
    db = sqlite3.connect(staging)
    db.executescript(Path(__file__).with_name("schema.sql").read_text())
    db.executemany(
        "INSERT INTO dataset_meta VALUES (?,?)",
        [
            ("as_of", as_of),
            ("seed", str(seed)),
            ("size", str(size)),
            ("calendar_start", first_day.isoformat()),
            ("synthetic", "true"),
            ("calendar_policy", "演示日历：周一至周五为工作日，不套用法定节假日"),
            ("catalog_version", config.CATALOG_VERSION),
            ("data_version", config.DATA_VERSION),
        ],
    )
    db.executemany(
        "INSERT INTO legal_entities VALUES (?,?)", [(1, "澄川科技（模拟）"), (2, "澄川数智（模拟）")]
    )
    db.executemany(
        "INSERT INTO locations VALUES (?,?,?)",
        [(1, "上海", "Asia/Shanghai"), (2, "杭州", "Asia/Shanghai"), (3, "深圳", "Asia/Shanghai")],
    )
    db.executemany(
        "INSERT INTO job_families VALUES (?,?)",
        list(enumerate(["管理", "研发", "产品", "销售", "运营", "人力", "财务"], 1)),
    )
    db.executemany(
        "INSERT INTO grades VALUES (?,?,?,?)",
        [(i, f"P{i}", 4000 + i * 2500, 9000 + i * 6000) for i in range(1, 10)],
    )
    job_names = [
        "总经理",
        "事业部负责人",
        "部门负责人",
        "团队主管",
        "开发工程师",
        "产品经理",
        "销售顾问",
        "交付顾问",
        "人力专员",
        "财务分析师",
    ]
    families = [1, 1, 1, 1, 2, 3, 4, 5, 6, 7]
    db.executemany(
        "INSERT INTO positions VALUES (?,?,?,?)",
        [(i, n, families[i - 1], int(i <= 4)) for i, n in enumerate(job_names, 1)],
    )
    db.execute("INSERT INTO departments VALUES (1,?,NULL,1,NULL)", ("澄川科技",))
    departments = {1: {"parent": None, "division": None, "level": 1}}
    for division, (name, _) in enumerate(DIVISIONS, 2):
        db.execute("INSERT INTO departments VALUES (?,?,1,2,?)", (division, name, division))
        departments[division] = {"parent": 1, "division": division, "level": 2}
    for division, (_, depts) in enumerate(DIVISIONS, 2):
        for offset, name in enumerate(depts):
            department = 7 + (division - 2) * 3 + offset
            db.execute("INSERT INTO departments VALUES (?,?,?,3,?)", (department, name, division, division))
            departments[department] = {"parent": division, "division": division, "level": 3}
            for t in range(2):
                team = 22 + (department - 7) * 2 + t
                team_name = name.removesuffix("部") + ("一组" if t == 0 else "二组")
                db.execute(
                    "INSERT INTO departments VALUES (?,?,?,4,?)", (team, team_name, department, division)
                )
                departments[team] = {"parent": department, "division": division, "level": 4}
    db.execute(
        "INSERT INTO shift_policies VALUES (1,?,480,570,1080,480,60,?)", ("弹性标准班", "attendance-1.0")
    )
    surname = list("赵钱孙李周吴郑王冯陈沈韩杨朱秦许何吕张孔曹严华金魏陶姜谢邹苏潘范彭鲁韦马方任袁柳")
    given = [
        "知远",
        "嘉宁",
        "予安",
        "亦舒",
        "明澈",
        "思齐",
        "书言",
        "清和",
        "若溪",
        "景行",
        "可欣",
        "一诺",
        "奕辰",
        "云舟",
        "雨桐",
        "望舒",
        "安然",
        "子墨",
        "星禾",
        "言蹊",
    ]
    special = {1: "林知远", 2: "陈嘉宁", 5: "沈亦舒", 22: "周予安", 52: "许明澈"}
    employee_records = []
    assignments = []
    manager_map = {}
    for eid in range(1, size + 1):
        dept = (
            eid
            if eid <= 51
            else 22
            if eid == 52
            else rng.choices(list(range(22, 52)), weights=[40] * 6 + [23] * 6 + [20] * 6 + [9] * 6 + [8] * 6)[
                0
            ]
        )
        manager = departments[dept]["parent"] if eid <= 51 else dept
        manager_map[eid] = manager
        division = departments[dept]["division"]
        hire = (
            date(2018, 1, 1) + timedelta(days=eid)
            if eid <= 51
            else snapshot - timedelta(days=rng.randint(0, 2100))
        )
        if eid > size - int(size * 0.045):
            hire = min(hire, snapshot - timedelta(days=180))
        termination = (
            snapshot - timedelta(days=rng.randint(3, 85))
            if eid > size - int(size * 0.045) and hire < snapshot - timedelta(days=120)
            else None
        )
        etype = rng.choices(["正式", "实习", "外包"], [90, 5, 5])[0] if eid > 51 else "正式"
        if etype == "实习":
            hire = max(hire, snapshot - timedelta(days=120))
            if termination and hire >= termination:
                hire = termination - timedelta(days=30)
        grade = (
            (9 if eid == 1 else 8 if eid <= 6 else 7 if eid <= 21 else 6)
            if eid <= 51
            else rng.choices([2, 3, 4, 5, 6], [8, 20, 36, 28, 8])[0]
        )
        position = (
            1
            if eid == 1
            else 2
            if eid <= 6
            else 3
            if eid <= 21
            else 4
            if eid <= 51
            else (
                5
                if division == 2
                else 7
                if division == 3
                else 8
                if division == 4
                else 9
                if division == 5
                else 10
            )
        )
        if eid > 51 and division == 2 and eid % 5 == 0:
            position = 6
        if etype == "实习":
            grade = 2
        name = special.get(eid, surname[(eid - 1) % len(surname)] + given[(eid // len(surname)) % len(given)])
        birth = date(
            1979 if eid <= 6 else 1985 if eid <= 51 else 1990 + rng.randint(0, 10),
            rng.randint(1, 12),
            rng.randint(1, 28),
        )
        db.execute(
            "INSERT INTO employees(id,employee_no,name,gender,birth_date,hire_date,termination_date,employment_type,entity_id,location_id,email) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                eid,
                f"CC{eid:05}",
                name,
                rng.choice(["女", "男"]),
                birth.isoformat(),
                hire.isoformat(),
                termination.isoformat() if termination else None,
                etype,
                1 if eid % 4 else 2,
                rng.choices([1, 2, 3], [65, 25, 10])[0],
                f"e{eid:05}@chengchuan.example",
            ),
        )
        db.execute(
            "INSERT INTO employee_private VALUES (?,?,?,?)",
            (eid, f"SIM-PHONE-{eid:05}", f"SIM-ID-{eid:05}", f"SIM-BANK-{eid:05}"),
        )
        transfer = snapshot - timedelta(days=45)
        old_dept = dept + 1 if dept % 2 == 0 else dept - 1
        if eid > 51 and eid % 13 == 0 and hire < transfer and (not termination or termination > transfer):
            assignments.append(
                (eid, old_dept, old_dept, position, grade, hire.isoformat(), transfer.isoformat())
            )
            assignments.append((eid, dept, manager, position, grade, transfer.isoformat(), None))
        else:
            assignments.append((eid, dept, manager, position, grade, hire.isoformat(), None))
        salary = rng.randrange(4000 + grade * 2500, 9000 + grade * 6000, 500)
        db.execute(
            "INSERT INTO compensation(employee_id,valid_from,monthly_base) VALUES (?,?,?)",
            (eid, hire.isoformat(), salary),
        )
        if hire < date(snapshot.year, 6, 30) and (
            not termination or termination >= date(snapshot.year, 6, 30)
        ):
            db.execute(
                "INSERT INTO performance_reviews(employee_id,period,rating,reviewer_id) VALUES (?,?,?,?)",
                (
                    eid,
                    f"{snapshot.year}-H1",
                    rng.choices(["卓越", "优秀", "达标", "待提升"], [10, 30, 55, 5])[0],
                    manager,
                ),
            )
        employee_records.append(
            {
                "id": eid,
                "hire": hire,
                "termination": termination,
                "manager": manager,
                "dept": dept,
                "position": position,
            }
        )
    db.executemany(
        "INSERT INTO assignments(employee_id,department_id,manager_id,position_id,grade_id,valid_from,valid_to) VALUES (?,?,?,?,?,?,?)",
        assignments,
    )
    from .education import populate_education

    populate_education(db, seed)
    for eid in manager_map:
        ancestor = eid
        depth = 0
        seen = set()
        while ancestor:
            if ancestor in seen:
                raise ValueError("汇报关系出现环")
            seen.add(ancestor)
            db.execute("INSERT INTO reporting_closure VALUES (?,?,?)", (ancestor, eid, depth))
            ancestor = manager_map.get(ancestor)
            depth += 1
    weekend_rng = random.Random(seed + 9973)
    weekend_overtime = []
    weekend_attendance = []
    attendance = []
    leave = []
    overtime = []
    day = first_day
    while day <= snapshot:
        workday = day.weekday() < 5
        db.execute(
            "INSERT INTO work_calendar VALUES (?,?,?)",
            (day.isoformat(), int(workday), "模拟工作日" if workday else "周末"),
        )
        if workday:
            for e in employee_records:
                if day < e["hire"] or (e["termination"] and day >= e["termination"]):
                    continue
                status = rng.choices(["正常", "远程", "请假", "缺勤", "缺卡"], [90.5, 4, 3.5, 0.7, 1.3])[0]
                if day == snapshot and e["id"] in (52, 53):
                    status = "正常"
                checkin = checkout = None
                work = late = early = after = 0
                if status == "请假":
                    leave.append(
                        (
                            e["id"],
                            day.isoformat(),
                            rng.choice(["年假", "事假", "病假"]),
                            1.0,
                            "已批准",
                            e["manager"],
                        )
                    )
                elif status in ("正常", "远程", "缺卡"):
                    checkin = rng.randint(480, 565)
                    if rng.random() < 0.045:
                        checkin = rng.randint(571, 610)
                    required_out = max(1080, checkin + 540)
                    checkout = (
                        required_out
                        + rng.choices(
                            [rng.randint(0, 25), rng.randint(30, 90), rng.randint(100, 180)], [78, 17, 5]
                        )[0]
                    )
                    checkout = min(1320, checkout)
                    if rng.random() < 0.012:
                        checkout = required_out - rng.randint(10, 80)
                    if day == snapshot and e["id"] == 52:
                        checkin, checkout = 570, 1110
                    if day == snapshot and e["id"] == 53:
                        checkin, checkout = 571, 1320
                    if status == "缺卡":
                        checkout = None
                    late = max(0, checkin - 570)
                    if checkout:
                        required_out = max(1080, checkin + 540)
                        work = max(0, checkout - checkin - 60)
                        early = max(0, required_out - checkout)
                        after = max(0, checkout - required_out)
                        if after >= 30 and rng.random() < 0.68:
                            overtime.append(
                                (
                                    e["id"],
                                    day.isoformat(),
                                    (after // 30) * 30,
                                    rng.choices(["已批准", "待审批", "已拒绝"], [84, 12, 4])[0],
                                    e["manager"],
                                )
                            )
                attendance.append(
                    (e["id"], day.isoformat(), 1, status, checkin, checkout, work, late, early, after)
                )
        else:
            for e in employee_records:
                if day < e["hire"] or (e["termination"] and day >= e["termination"]):
                    continue
                if weekend_rng.random() >= (0.035 if e["id"] > 51 else 0.01):
                    continue
                checkin = weekend_rng.choice([540, 570, 600, 780])
                span = weekend_rng.choice([180, 240, 360, 480, 540])
                checkout = min(1320, checkin + span)
                rest = 60 if checkin < 720 and checkout > 780 else 0
                net = checkout - checkin - rest
                approved_minutes = (net // 30) * 30
                weekend_attendance.append((e["id"], day.isoformat(), checkin, checkout, rest, net))
                weekend_overtime.append(
                    (
                        e["id"],
                        day.isoformat(),
                        approved_minutes,
                        "周末",
                        weekend_rng.choices(["已批准", "待审批", "已拒绝"], [82, 13, 5])[0],
                        e["manager"],
                    )
                )
        day += timedelta(days=1)
    db.executemany(
        "INSERT INTO attendance_daily(employee_id,day,shift_id,status,check_in,check_out,work_minutes,late_minutes,early_minutes,late_departure_minutes) VALUES (?,?,?,?,?,?,?,?,?,?)",
        attendance,
    )
    db.executemany(
        "INSERT INTO leave_requests(employee_id,day,leave_type,days,approval_status,approver_id) VALUES (?,?,?,?,?,?)",
        leave,
    )
    db.executemany(
        "INSERT INTO overtime_requests(employee_id,day,minutes,approval_status,approver_id) VALUES (?,?,?,?,?)",
        overtime,
    )
    db.executemany(
        "INSERT INTO overtime_attendance(employee_id,day,check_in,check_out,break_minutes,work_minutes) VALUES (?,?,?,?,?,?)",
        weekend_attendance,
    )
    db.executemany(
        "INSERT INTO overtime_requests(employee_id,day,minutes,day_type,approval_status,approver_id) VALUES (?,?,?,?,?,?)",
        weekend_overtime,
    )
    db.executemany(
        "INSERT INTO training_courses VALUES (?,?,?)",
        [(1, "信息安全与隐私保护", 2), (2, "新员工入职训练", 6), (3, "管理者沟通", 4)],
    )
    for e in employee_records:
        for course in [1, 2] if e["id"] > 51 else [1, 3]:
            done = rng.random() < 0.87
            db.execute(
                "INSERT INTO training_enrollments VALUES (?,?,?,?)",
                (
                    e["id"],
                    course,
                    "已完成" if done else "学习中",
                    min(snapshot, e["hire"] + timedelta(days=14)).isoformat() if done else None,
                ),
            )
    for dept in range(7, 22):
        db.execute(
            "INSERT INTO recruitment_requisitions(department_id,position_id,openings,status,opened_at) VALUES (?,?,?,?,?)",
            (
                dept,
                5 if dept < 10 else 7 if dept < 13 else 8 if dept < 16 else 9 if dept < 19 else 10,
                rng.randint(1, 4),
                "招聘中",
                (snapshot - timedelta(days=rng.randint(7, 60))).isoformat(),
            ),
        )
    db.commit()
    db.execute("ANALYZE")
    db.close()
    from .validate import validate

    report = validate(staging)
    if not report["passed"]:
        raise ValueError(json.dumps(report, ensure_ascii=False))
    staging.replace(target)
    initialize_app(directory / "app.sqlite", reset=reset_app)
    (directory / "validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


def upgrade_demo_data():
    # 名称中的 data_version/备份名 v2 指旧版样本格式升级，不是 backend/hr/v2 应用。
    # 仅自动升级 synthetic=true 的样本，升级前备份业务库与应用库。
    from datetime import UTC, datetime

    target = config.BUSINESS_DB
    if not target.exists():
        return generate()
    source = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
    try:
        meta = dict(source.execute("SELECT key,value FROM dataset_meta"))
        if meta.get("data_version") == config.DATA_VERSION:
            return None
        if meta.get("synthetic") != "true":
            raise RuntimeError("自动升级仅适用于本项目合成数据，真实业务库需显式迁移。")
        backup_dir = target.parent / "backups"
        backup_dir.mkdir(exist_ok=True)
        backup = sqlite3.connect(
            backup_dir / ("hr-before-v2-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f") + ".sqlite")
        )
        try:
            source.backup(backup)
        finally:
            backup.close()
        if config.APP_DB.exists():
            app_source = sqlite3.connect(f"file:{config.APP_DB}?mode=ro", uri=True)
            app_backup = sqlite3.connect(
                backup_dir / ("app-before-v2-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f") + ".sqlite")
            )
            try:
                app_source.backup(app_backup)
            finally:
                app_source.close()
                app_backup.close()
    finally:
        source.close()
    return generate(
        directory=target.parent, seed=int(meta["seed"]), size=int(meta["size"]), as_of=meta["as_of"]
    )


def main():
    parser = argparse.ArgumentParser(description="生成可复现 HR 合成数据，保留已有看板与会话")
    parser.add_argument("--seed", type=int, default=20260911)
    parser.add_argument("--size", type=int, default=480)
    parser.add_argument("--as-of", default=config.DEMO_DATE)
    parser.add_argument("--reset-app", action="store_true", help="仅显式使用时重置看板与会话")
    args = parser.parse_args()
    print(
        json.dumps(
            generate(seed=args.seed, size=args.size, as_of=args.as_of, reset_app=args.reset_app),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
