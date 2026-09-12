"""Education metadata and deterministic, completed education histories."""

import json
import random
from datetime import date, timedelta

MOE_985 = "https://www.moe.gov.cn/srcsite/A22/s7065/200612/t20061206_128833.html"
MOE_211 = "https://www.moe.gov.cn/srcsite/A22/s7065/200512/t20051223_82762.html"
SCHOOLS = [
    (1, "清华大学", ["清华"], 1, 1),
    (2, "北京大学", ["北大"], 1, 1),
    (3, "复旦大学", ["复旦"], 1, 1),
    (4, "上海交通大学", ["上交", "上海交大"], 1, 1),
    (5, "浙江大学", ["浙大"], 1, 1),
    (6, "同济大学", ["同济"], 1, 1),
    (7, "华东理工大学", ["华东理工", "华理"], 0, 1),
    (8, "上海大学", ["上大"], 0, 1),
    (9, "澄川大学（模拟）", ["澄川大学"], 0, 0),
    (10, "澄川职业学院（模拟）", ["澄川职业学院"], 0, 0),
    (11, "澄川中学（模拟）", ["澄川中学"], 0, 0),
]
LEVELS = {"高中及以下": 1, "专科": 2, "本科": 3, "硕士研究生": 4, "博士研究生": 5}
DEGREES = {1: "无学位", 2: "无学位", 3: "学士", 4: "硕士", 5: "博士"}
MIN_AGE = {1: 18, 2: 20, 3: 22, 4: 25, 5: 29}


def populate_education(db, seed):
    rng = random.Random(seed + 1729)
    for ident, name, aliases, is985, is211 in SCHOOLS:
        db.execute(
            "INSERT INTO schools VALUES (?,?,?,?,?,?,?)",
            (
                ident,
                name,
                json.dumps(aliases, ensure_ascii=False),
                is985,
                is211,
                "教育部历史工程名单；院校名称及别名为演示子集" if ident < 9 else "虚构院校，仅用于合成数据",
                MOE_985 if is985 else MOE_211 if is211 else "synthetic",
            ),
        )
    records = db.execute(
        "SELECT e.id,e.birth_date,e.hire_date,d.division_id FROM employees e JOIN assignments a ON a.employee_id=e.id AND a.valid_to IS NULL JOIN departments d ON d.id=a.department_id ORDER BY e.id"
    ).fetchall()
    eligible_doctors = []
    for eid, birth_text, hire_text, division in records:
        birth, hire = date.fromisoformat(birth_text), date.fromisoformat(hire_text)
        eligible = [rank for rank in range(1, 6) if birth.replace(year=birth.year + MIN_AGE[rank]) <= hire]
        highest = rng.choices(eligible, weights=[4, 12, 52, 26, 14 if division == 2 else 5][: len(eligible)])[
            0
        ]
        if (
            hire.month in (4, 5, 6)
            and hire.year
            == date.fromisoformat(dict(db.execute("SELECT key,value FROM dataset_meta"))["as_of"]).year
            and 5 in eligible
        ):
            eligible_doctors.append(eid)
            if len(eligible_doctors) <= 2:
                highest = 5
        major = (
            rng.choice(["计算机科学与技术", "软件工程", "信息管理"])
            if division == 2
            else rng.choice(["工商管理", "应用统计", "会计学", "市场营销"])
        )
        ranks = list(range(3, highest + 1)) if highest >= 3 else [highest]
        # All generated degrees were completed before hire, with ordered study periods.
        for rank in ranks:
            graduation = birth.replace(year=birth.year + MIN_AGE[rank])
            graduation = min(graduation, hire)
            start = graduation - timedelta(days=(4 if rank in (3, 5) else 3) * 365)
            school = rng.choice(list(range(1, 10))) if rank >= 3 else 10 if rank == 2 else 11
            # Keep a genuine overlap cohort for multi-school de-duplication regression.
            if eid % 17 == 0 and rank == 3:
                school = 1
            if eid % 17 == 0 and rank >= 4:
                school = 2
            mode = "全日制" if rng.random() < 0.92 else "非全日制"
            level = next(k for k, v in LEVELS.items() if v == rank)
            db.execute(
                "INSERT INTO employee_education(employee_id,school_id,education_level,education_rank,degree,major,start_date,graduation_date,study_mode) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    eid,
                    school,
                    level,
                    rank,
                    DEGREES[rank],
                    major,
                    start.isoformat(),
                    graduation.isoformat(),
                    mode,
                ),
            )
            if rank == highest:
                db.execute(
                    "UPDATE employees SET highest_education=?,highest_degree=?,graduation_school_id=?,major=?,graduation_date=?,education_mode=? WHERE id=?",
                    (level, DEGREES[rank], school, major, graduation.isoformat(), mode, eid),
                )


def school_directory(db):
    return [
        {**dict(row), "aliases": json.loads(row["aliases"])}
        for row in db.execute(
            "SELECT id,name,aliases,is_985,is_211,classification_basis,source_url FROM schools ORDER BY id"
        )
    ]


def has_filter(plan):
    return bool(
        plan.education_level or plan.minimum_education or plan.degree or plan.schools or plan.school_tier
    )


def latest_condition(alias, day):
    # Rank first, then graduation date and id break ties: exactly one record as of the event.
    return f"""{alias}.graduation_date<={day} AND NOT EXISTS (
        SELECT 1 FROM employee_education newer WHERE newer.employee_id={alias}.employee_id AND newer.graduation_date<={day}
        AND (newer.education_rank>{alias}.education_rank OR (newer.education_rank={alias}.education_rank AND (newer.graduation_date>{alias}.graduation_date OR (newer.graduation_date={alias}.graduation_date AND newer.id>{alias}.id)))))"""


def education_joins(day):
    return f"LEFT JOIN employee_education he ON he.employee_id=e.id AND {latest_condition('he', day)} LEFT JOIN schools hs ON hs.id=he.school_id"


def predicate(plan, db, params, day, *, detail=False):
    from fastapi import HTTPException

    if not has_filter(plan):
        return "1=1"
    clauses = ["q.employee_id=e.id", f"q.graduation_date<={day}"]
    if plan.education_scope == "highest":
        clauses.append(latest_condition("q", day))
    for key in ("education_level", "degree"):
        value = getattr(plan, key)
        if value:
            params["edu_" + key] = value
            clauses.append(f"q.{key}=:edu_{key}")
    if plan.minimum_education:
        params["edu_min_rank"] = LEVELS[plan.minimum_education]
        clauses.append("q.education_rank>=:edu_min_rank")
    if plan.schools:
        directory = school_directory(db)
        ids = []
        for name in plan.schools:
            found = [
                school["id"] for school in directory if name == school["name"] or name in school["aliases"]
            ]
            if len(found) != 1:
                raise HTTPException(422, detail=f"学校“{name}”尚未收录或名称不明确，请使用院校字典中的名称。")
            ids.extend(found)
        for i, ident in enumerate(sorted(set(ids))):
            params[f"edu_school{i}"] = ident
        clauses.append("q.school_id IN (" + ",".join(f":edu_school{i}" for i in range(len(set(ids)))) + ")")
    if plan.school_tier:
        clauses.append(
            {
                "985": "qs.is_985=1",
                "211": "qs.is_211=1",
                "985或211": "(qs.is_985=1 OR qs.is_211=1)",
                "211非985": "qs.is_211=1 AND qs.is_985=0",
                "双非": "qs.is_211=0 AND qs.is_985=0",
            }[plan.school_tier]
        )
    projection = (
        "group_concat(qs.name || ' · ' || q.education_level || ' · ' || q.graduation_date,'；')"
        if detail
        else "1"
    )
    return (
        ("(" if detail else "EXISTS (")
        + f"SELECT {projection} FROM employee_education q JOIN schools qs ON qs.id=q.school_id WHERE "
        + " AND ".join(clauses)
        + ")"
    )


def filter_description(plan):
    parts = []
    if plan.education_level:
        parts.append("学历=" + plan.education_level)
    if plan.minimum_education:
        parts.append("学历≥" + plan.minimum_education)
    if plan.degree:
        parts.append("学位=" + plan.degree)
    if plan.schools:
        parts.append("学校任一匹配：" + "、".join(plan.schools))
    if plan.school_tier:
        parts.append("院校标签=" + plan.school_tier)
    return (
        "最高已完成教育经历"
        if plan.education_scope == "highest"
        else "任一已完成教育经历（同一经历匹配全部条件，员工去重）"
    ) + ("；" + "；".join(parts) if parts else "")
