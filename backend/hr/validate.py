import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from . import config

CHECKS = [
    (
        "每人恰好一条当前任职",
        "SELECT COUNT(*) FROM employees e WHERE (SELECT COUNT(*) FROM assignments a WHERE a.employee_id=e.id AND a.valid_to IS NULL)<>1",
    ),
    (
        "任职历史无重叠",
        "SELECT COUNT(*) FROM assignments a JOIN assignments b ON a.employee_id=b.employee_id AND a.id<b.id AND a.valid_from<COALESCE(b.valid_to,'9999-12-31') AND b.valid_from<COALESCE(a.valid_to,'9999-12-31')",
    ),
    (
        "任职从入职日开始且历史连续",
        "SELECT COUNT(*) FROM employees e WHERE (SELECT MIN(valid_from) FROM assignments WHERE employee_id=e.id)<>e.hire_date OR EXISTS(SELECT 1 FROM assignments a WHERE a.employee_id=e.id AND a.valid_to IS NOT NULL AND NOT EXISTS(SELECT 1 FROM assignments b WHERE b.employee_id=e.id AND b.valid_from=a.valid_to))",
    ),
    (
        "全部人员可从公司负责人到达",
        "SELECT COUNT(*) FROM employees e WHERE NOT EXISTS(SELECT 1 FROM reporting_closure c WHERE c.ancestor_id=1 AND c.descendant_id=e.id)",
    ),
    (
        "汇报关系闭包与当前任职一致",
        "SELECT COUNT(*) FROM assignments a WHERE a.valid_to IS NULL AND a.manager_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM reporting_closure c WHERE c.ancestor_id=a.manager_id AND c.descendant_id=a.employee_id AND c.depth=1)",
    ),
    (
        "闭包自关联深度为零",
        "SELECT COUNT(*) FROM reporting_closure WHERE (ancestor_id=descendant_id AND depth<>0) OR (ancestor_id<>descendant_id AND depth=0)",
    ),
    (
        "组织层级正确",
        "SELECT COUNT(*) FROM departments d JOIN departments p ON d.parent_id=p.id WHERE d.level<>p.level+1",
    ),
    (
        "只在入职至离职前的工作日生成考勤",
        "SELECT COUNT(*) FROM attendance_daily a JOIN employees e ON e.id=a.employee_id JOIN work_calendar c ON c.day=a.day WHERE c.is_workday<>1 OR a.day<e.hire_date OR (e.termination_date IS NOT NULL AND a.day>=e.termination_date)",
    ),
    (
        "考勤覆盖全部应出勤人日",
        "SELECT COUNT(*) FROM employees e CROSS JOIN work_calendar c WHERE c.is_workday=1 AND e.hire_date<=c.day AND (e.termination_date IS NULL OR e.termination_date>c.day) AND NOT EXISTS(SELECT 1 FROM attendance_daily a WHERE a.employee_id=e.id AND a.day=c.day)",
    ),
    (
        "迟到分钟与09:30阈值一致",
        "SELECT COUNT(*) FROM attendance_daily WHERE late_minutes<>MAX(0,COALESCE(check_in,570)-570)",
    ),
    (
        "有效在岗时长正确",
        "SELECT COUNT(*) FROM attendance_daily WHERE work_minutes<>CASE WHEN check_in IS NOT NULL AND check_out IS NOT NULL THEN MAX(0,check_out-check_in-60) ELSE 0 END",
    ),
    (
        "晚离岗与弹性应离岗时间一致",
        "SELECT COUNT(*) FROM attendance_daily WHERE late_departure_minutes<>CASE WHEN check_in IS NOT NULL AND check_out IS NOT NULL THEN MAX(0,check_out-MAX(1080,check_in+540)) ELSE 0 END",
    ),
    (
        "早退分钟正确",
        "SELECT COUNT(*) FROM attendance_daily WHERE early_minutes<>CASE WHEN check_in IS NOT NULL AND check_out IS NOT NULL THEN MAX(0,MAX(1080,check_in+540)-check_out) ELSE 0 END",
    ),
    (
        "正常与远程打卡完整且不晚于22:00",
        "SELECT COUNT(*) FROM attendance_daily WHERE (status IN ('正常','远程') AND (check_in IS NULL OR check_out IS NULL)) OR check_out>1320 OR work_minutes>840",
    ),
    (
        "请假与打卡互斥且关联已批准申请",
        "SELECT COUNT(*) FROM attendance_daily a WHERE status='请假' AND (check_in IS NOT NULL OR check_out IS NOT NULL OR NOT EXISTS(SELECT 1 FROM leave_requests l WHERE l.employee_id=a.employee_id AND l.day=a.day AND l.approval_status='已批准'))",
    ),
    (
        "加班申请不超过可观察晚离岗时长",
        "SELECT COUNT(*) FROM overtime_requests o LEFT JOIN attendance_daily a ON a.employee_id=o.employee_id AND a.day=o.day WHERE o.day_type='工作日' AND (a.id IS NULL OR o.minutes>a.late_departure_minutes)",
    ),
    (
        "离职后无请假或加班",
        "SELECT COUNT(*) FROM employees e WHERE EXISTS(SELECT 1 FROM leave_requests l WHERE l.employee_id=e.id AND l.day>=e.termination_date) OR EXISTS(SELECT 1 FROM overtime_requests o WHERE o.employee_id=e.id AND o.day>=e.termination_date)",
    ),
    (
        "薪资在职级模拟范围内",
        "SELECT COUNT(*) FROM compensation c JOIN assignments a ON a.employee_id=c.employee_id AND a.valid_to IS NULL JOIN grades g ON g.id=a.grade_id WHERE c.monthly_base<g.salary_min OR c.monthly_base>g.salary_max",
    ),
    (
        "个人敏感信息全部使用SIM标记",
        "SELECT COUNT(*) FROM employee_private WHERE phone NOT LIKE 'SIM-%' OR identity_document NOT LIKE 'SIM-%' OR bank_account NOT LIKE 'SIM-%'",
    ),
    (
        "教育经历与当前最高学历快照一致",
        "SELECT COUNT(*) FROM employees e WHERE NOT EXISTS(SELECT 1 FROM employee_education q WHERE q.employee_id=e.id AND q.education_level=e.highest_education AND q.degree=e.highest_degree AND q.school_id=e.graduation_school_id AND q.graduation_date=e.graduation_date AND q.major=e.major AND q.study_mode=e.education_mode AND NOT EXISTS(SELECT 1 FROM employee_education h WHERE h.employee_id=e.id AND h.education_rank>q.education_rank))",
    ),
    (
        "学历层级与学位对应",
        "SELECT COUNT(*) FROM employee_education WHERE education_level<>CASE education_rank WHEN 1 THEN '高中及以下' WHEN 2 THEN '专科' WHEN 3 THEN '本科' WHEN 4 THEN '硕士研究生' WHEN 5 THEN '博士研究生' END OR degree<>CASE education_rank WHEN 3 THEN '学士' WHEN 4 THEN '硕士' WHEN 5 THEN '博士' ELSE '无学位' END",
    ),
    (
        "合成教育经历在入职前完成且日期合理",
        "SELECT COUNT(*) FROM employee_education q JOIN employees e ON e.id=q.employee_id WHERE q.graduation_date>e.hire_date OR q.start_date<date(e.birth_date,'+14 years') OR q.start_date>=q.graduation_date",
    ),
    (
        "教育经历不重叠",
        "SELECT COUNT(*) FROM employee_education a JOIN employee_education b ON a.employee_id=b.employee_id AND a.education_rank<b.education_rank WHERE a.graduation_date>b.start_date",
    ),
    (
        "院校985标签不重复计入211并保留来源",
        "SELECT COUNT(*) FROM schools WHERE is_985>is_211 OR source_url=''",
    ),
    (
        "周末打卡只出现在在职周六周日",
        "SELECT COUNT(*) FROM overtime_attendance a JOIN employees e ON e.id=a.employee_id JOIN work_calendar c ON c.day=a.day WHERE c.is_workday<>0 OR strftime('%w',a.day) NOT IN ('0','6') OR a.day<e.hire_date OR (e.termination_date IS NOT NULL AND a.day>=e.termination_date)",
    ),
    (
        "周末净工时与休息一致",
        "SELECT COUNT(*) FROM overtime_attendance WHERE work_minutes<>check_out-check_in-break_minutes OR check_out>1320 OR work_minutes<=0",
    ),
    (
        "周末加班申请不超过独立打卡净时长",
        "SELECT COUNT(*) FROM overtime_requests o LEFT JOIN overtime_attendance a ON a.employee_id=o.employee_id AND a.day=o.day WHERE o.day_type='周末' AND (a.id IS NULL OR o.minutes>a.work_minutes)",
    ),
    (
        "加班日期类别与日历一致",
        "SELECT COUNT(*) FROM overtime_requests o LEFT JOIN work_calendar c ON c.day=o.day WHERE c.day IS NULL OR (o.day_type='工作日' AND c.is_workday<>1) OR (o.day_type='周末' AND (c.is_workday<>0 OR strftime('%w',o.day) NOT IN ('0','6')))",
    ),
    ("邮箱使用保留示例域名", "SELECT COUNT(*) FROM employees WHERE email NOT LIKE '%@chengchuan.example'"),
]


def validate(path: Path = config.BUSINESS_DB):
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    results = []
    integrity = db.execute("PRAGMA integrity_check").fetchall()
    results.append(
        {
            "name": "SQLite 文件完整性",
            "passed": integrity == [("ok",)],
            "violations": 0 if integrity == [("ok",)] else len(integrity),
        }
    )
    fk = db.execute("PRAGMA foreign_key_check").fetchall()
    results.append({"name": "所有外键有效", "passed": not fk, "violations": len(fk)})
    for name, sql in CHECKS:
        count = db.execute(sql).fetchone()[0]
        results.append({"name": name, "passed": count == 0, "violations": count})
    # Independently traverse all manager chains, not just the precomputed closure.
    managers = dict(db.execute("SELECT employee_id,manager_id FROM assignments WHERE valid_to IS NULL"))
    expected = set()
    cycles = 0
    for eid in managers:
        seen = set()
        node = eid
        depth = 0
        while node:
            if node in seen:
                cycles += 1
                break
            seen.add(node)
            expected.add((node, eid, depth))
            node = managers.get(node)
            depth += 1
    actual = set(db.execute("SELECT ancestor_id,descendant_id,depth FROM reporting_closure"))
    results.append(
        {
            "name": "独立遍历验证汇报闭包且无环",
            "passed": not cycles and expected == actual,
            "violations": cycles + len(expected ^ actual),
        }
    )
    tables = [
        r[0]
        for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    ]
    counts = {t: db.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables}
    meta = dict(db.execute("SELECT key,value FROM dataset_meta"))
    active = db.execute(
        "SELECT COUNT(*) FROM employees WHERE hire_date<=? AND (termination_date IS NULL OR termination_date>?)",
        (meta["as_of"], meta["as_of"]),
    ).fetchone()[0]
    db.close()
    return {
        "passed": all(r["passed"] for r in results),
        "checks": results,
        "counts": counts,
        "active_employees": active,
        "total_employees": counts["employees"],
        "as_of": meta["as_of"],
        "seed": int(meta["seed"]),
        "generated_at": datetime.now(UTC).isoformat(),
        "synthetic": True,
    }


if __name__ == "__main__":
    report = validate()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["passed"] else 1)
