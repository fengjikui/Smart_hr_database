import hashlib
import json
import random
import sqlite3
from contextlib import contextmanager
from datetime import date, timedelta
from threading import RLock

from .. import config
from .schema import FIELDS, LEVELS, SCHOOLS

AS_OF = "2026-09-11"
DATA_VERSION = "v2-minimal-1"
LOCK = RLock()
PERSONAS = [
    {"id": "hr_lead", "person_id": "P0002", "name": "王承哲", "role": "hr_lead", "label": "HR主管 · 王承哲"},
    {"id": "hrbp", "person_id": "P0003", "name": "姜姜", "role": "hrbp", "label": "HRBP · 姜姜"},
    {"id": "manager", "person_id": "P0004", "name": "王灏", "role": "manager", "label": "部门主管 · 王灏"},
    {"id": "employee", "person_id": "P0005", "name": "冯基魁", "role": "employee", "label": "员工 · 冯基魁"},
    {
        "id": "admin",
        "person_id": "P0001",
        "name": "演示配置管理员",
        "role": "admin",
        "label": "配置管理员 · 集团管理线",
    },
]


def directory():
    return config.APP_DB.parent


@contextmanager
def connection(kind="app", readonly=False):
    path = directory() / ("v2_people.sqlite" if kind == "people" else "v2_app.sqlite")
    db = sqlite3.connect(f"file:{path}?mode=ro" if readonly else str(path), uri=readonly, timeout=5)
    db.row_factory = sqlite3.Row
    if readonly:
        db.execute("PRAGMA query_only=ON")
    try:
        yield db
        if not readonly:
            db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def default_policy():
    roles = {}
    for role in ["hr_lead", "hrbp", "manager", "employee", "admin"]:
        roles[role] = {
            "reports": role != "employee",
            "hrbp": role in ("hr_lead", "hrbp", "admin"),
            "inherit_hrbp": role in ("hr_lead", "hrbp", "admin"),
            "field_groups": ["basic", "education", "employment"]
            + (["contract"] if role in ("hr_lead", "hrbp", "admin") else []),
            "details": True,
            "export": role in ("hr_lead", "hrbp", "admin"),
        }
    return {"version": 1, "assumption": True, "roles": roles}


def generate_rows(seed=20260911, size=300):
    rng = random.Random(seed)
    snapshot = date.fromisoformat(AS_OF)
    anchors = [
        ("集团负责人（模拟）", "SIM0001", "集团管理层", None, "P0011"),
        ("王承哲", "00004915", "装备业务四部人力资源部", "P0001", "P0003"),
        ("姜姜", "00002545", "装备业务四部人力资源部", "P0002", "P0003"),
        ("王灏", "00000774", "可信与AI实验室", "P0007", "P0003"),
        ("冯基魁", "00031266", "可信与AI实验室", "P0004", "P0003"),
        ("赵天子", "00003046", "可信与AI实验室", "P0004", "P0003"),
        ("实验室上级（待确认）", "SIM0007", "集团管理层", "P0001", "P0011"),
        ("平台主管（模拟）", "SIM0008", "平台研发部", "P0004", "P0003"),
        ("产品主管（模拟）", "SIM0009", "智能产品部", "P0004", "P0003"),
        ("销售主管（模拟）", "SIM0010", "企业销售部", "P0001", "P0011"),
        ("其他HRBP（模拟）", "SIM0011", "其他人力资源部", "P0001", "P0011"),
    ]
    depts = ["平台研发部", "智能产品部", "可信与AI实验室", "装备业务四部人力资源部", "企业销售部"]
    managers = ["P0008", "P0009", "P0004", "P0002", "P0010"]
    dept_codes = {d: f"D{i:02}" for i, d in enumerate(dict.fromkeys([a[2] for a in anchors] + depts), 1)}
    output = []
    for i in range(1, size + 1):
        if i <= len(anchors):
            name, number, dept, manager, hrbp = anchors[i - 1]
        else:
            choice = (i - 12) % 5
            name, number = f"模拟员工{i:03}", f"SIM{i:05}"
            dept, manager = depts[choice], managers[choice]
            hrbp = "P0011" if choice == 4 else "P0003"
        birth = date(rng.randint(1975, 2003), rng.randint(1, 12), rng.randint(1, 28))
        hire = date(2023, 1, 1) + timedelta(days=rng.randint(0, 1345))
        hire = min(hire, snapshot)
        if i <= 11:
            hire = date(2018, 3, 1)
            birth = date(1980 + i % 10, 3, 5)
        if 27 <= i <= 29:
            hire = date(2026, 9, 1) + timedelta(days=i - 27)
        if 40 <= i <= 48:
            hire = date(2026, 4, 1) + timedelta(days=(i - 40) * 7)
        if 70 <= i <= 85:
            hire = date(2026, 7, 1) + timedelta(days=i - 70)
        termination = None
        if i > 30 and i % 17 == 0:
            hire = min(hire, date(2025, 10, 1))
            termination = date(2026, 1, 1) + timedelta(days=i % 250)
        level = rng.choices(list(LEVELS), [3, 8, 48, 30, 11])[0]
        if 40 <= i <= 48:
            level = "博士研究生"
        if 70 <= i <= 85:
            level = "硕士研究生" if i % 2 else "博士研究生"
        if 90 <= i <= 95:
            birth = date(2026 - [30, 40, 32][i % 3], 1, 1)
        rank = LEVELS[level]
        minimum_age = {1: 18, 2: 21, 3: 22, 4: 25, 5: 29}[rank]
        if hire.year - birth.year <= minimum_age:
            birth = birth.replace(year=hire.year - minimum_age - 1)
        grad = date(min(hire.year - 1, birth.year + {1: 18, 2: 21, 3: 22, 4: 25, 5: 29}[rank]), 6, 30)
        school = rng.choice(list(SCHOOLS))
        if i % 23 == 0:
            school = None
        if 90 <= i <= 95:
            school = "清华大学" if i % 2 else "北京大学"
        confirmed = hire + timedelta(days=90)
        job_start = min(
            termination - timedelta(days=1) if termination else snapshot, hire + timedelta(days=150)
        )
        if i % 9 == 0 and not termination:
            job_start = max(hire, snapshot - timedelta(days=i % 30))
        contract = snapshot + timedelta(days=(i * 7) % 240 - 50) if i % 19 else None
        row = {
            "person_id": f"P{i:04}",
            "employee_no": number,
            "name": name,
            "head_person_id": manager,
            "dept_master_id": manager,
            "dept_hrbp_id": hrbp,
            "dept_code": dept_codes[dept],
            "dept_cn_name": dept,
            "onboard_date": hire.isoformat(),
            "termin_date": termination.isoformat() if termination else None,
            "birth_date": birth.isoformat() if i % 47 else None,
            "age": snapshot.year - birth.year - ((snapshot.month, snapshot.day) < (birth.month, birth.day))
            if i % 47
            else None,
            "school_name": school,
            "first_major": rng.choice(["计算机科学与技术", "软件工程", "工商管理", "应用统计"]),
            "diploma_code_desc": level if i % 41 else None,
            "degree_code_desc": {1: "无学位", 2: "无学位", 3: "学士", 4: "硕士", 5: "博士"}[rank]
            if i % 41
            else None,
            "full_time_flag": "是" if 70 <= i <= 85 or rng.random() < 0.8 else "否",
            "education_expired_date": grad.isoformat(),
            "hire_type_code_desc": "校园招聘" if 70 <= i <= 85 or i % 3 == 0 else "社会招聘",
            "labour_type_code_desc": ["正式", "外包", "实习"][i % 7 if i % 7 < 3 else 0],
            "position_code_desc": "研发工程师" if "研发" in dept or "实验室" in dept else "业务专员",
            "current_employment_start_date": job_start.isoformat(),
            "confirmation_date": confirmed.isoformat()
            if confirmed <= snapshot and (not termination or confirmed < termination)
            else None,
            "formalize_flag": "是"
            if confirmed <= snapshot and (not termination or confirmed < termination)
            else "否",
            "contract_type_code_desc": "固定期限",
            "contract_end_date": contract.isoformat() if contract else None,
        }
        output.append(row)
    return output


def ensure():
    with LOCK:
        directory().mkdir(parents=True, exist_ok=True)
        if not (directory() / "v2_people.sqlite").exists():
            people = generate_rows()
            with connection("people") as db:
                ddl = ",".join(
                    f'"{f}" '
                    + ("INTEGER" if f == "age" else "TEXT")
                    + (" PRIMARY KEY" if f == "person_id" else "")
                    for f in FIELDS
                )
                db.execute(f"CREATE TABLE people({ddl})")
                db.executemany(
                    "INSERT INTO people VALUES (" + ",".join("?" for _ in FIELDS) + ")",
                    [[p[f] for f in FIELDS] for p in people],
                )
                db.execute("CREATE UNIQUE INDEX employee_number ON people(employee_no)")
                for f in ["head_person_id", "dept_hrbp_id", "dept_code", "onboard_date", "termin_date"]:
                    db.execute(f"CREATE INDEX idx_{f} ON people({f})")
                db.execute("CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
                db.executemany(
                    "INSERT INTO metadata VALUES (?,?)",
                    [("as_of", AS_OF), ("version", DATA_VERSION), ("seed", "20260911")],
                )
        with connection() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions(hash TEXT PRIMARY KEY,persona TEXT NOT NULL,csrf TEXT NOT NULL,expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,owner TEXT NOT NULL,fingerprint TEXT NOT NULL,question TEXT NOT NULL,parent_id TEXT,status TEXT NOT NULL,created_at TEXT NOT NULL,payload TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS run_owner ON runs(owner,created_at DESC);
            CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,actor TEXT NOT NULL,action TEXT NOT NULL,created_at TEXT NOT NULL,details TEXT NOT NULL);
            """)
            db.execute(
                "INSERT OR IGNORE INTO settings VALUES (?,?)", ("policy", json.dumps(default_policy()))
            )


def people():
    with connection("people", True) as db:
        return [dict(r) for r in db.execute("SELECT * FROM people ORDER BY person_id")]


def data_fingerprint():
    return hashlib.sha256(json.dumps(people(), ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def policy():
    with connection(readonly=True) as db:
        return json.loads(db.execute("SELECT value FROM settings WHERE key='policy'").fetchone()[0])
