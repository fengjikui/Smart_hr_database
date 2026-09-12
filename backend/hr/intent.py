"""Ground explicit constraints so a model cannot silently drop requested filters."""

import re

from fastapi import HTTPException

from .db import business
from .education import school_directory
from .models import QueryPlan


def explicit_constraints(question):
    q = question
    values = {}
    notes = []
    if "直属" in q and "间接" in q:
        values.update(relation="subordinates", dimension="relation")
    elif "直属" in q:
        values["relation"] = "direct"
    elif "间接" in q:
        values["relation"] = "indirect"
    elif re.search(
        r"(?:我(?:本人|自己)?的?|本人(?:的)?)(?:本月|上月|今天|今年|上季度|本季度|近30天)?的?(?:考勤|迟到|请假|加班|学历|学位|毕业院校|教育背景)",
        q,
    ):
        values["relation"] = "self"
    if re.search(r"工作日|周一.*周五", q) and "加班" in q:
        raise HTTPException(
            422, detail="当前开放全部已批准加班和周末加班，工作日单独汇总尚未开放；没有忽略工作日条件。"
        )
    if re.search(r"博士后|双一流", q):
        raise HTTPException(
            422,
            detail="博士后不是学历/学位，双一流与211/985也不是同一标签；当前请使用已取得学历、学位及211/985条件。",
        )
    # Lexical constraints are grounded in the local school directory, never employee rows.
    with business() as db:
        schools = school_directory(db)
        orgs = [row[0] for row in db.execute("SELECT name FROM departments") if row[0] in q]
    if len(orgs) > 1:
        raise HTTPException(
            422, detail="当前每次支持一个明确组织及其下级范围，请拆分多个组织或选择共同上级。"
        )
    if orgs:
        values["department"] = orgs[0]
    matches = [
        school for school in schools if any(name in q for name in [school["name"], *school["aliases"]])
    ]
    if matches:
        values["schools"] = [school["name"] for school in matches]
        values["education_scope"] = "highest" if re.search(r"最高|最终", q) else "any_completed"
        notes.append("院校名称按字典归一，多校OR去重；学校条件匹配同一条已完成教育经历")
        if len(matches) > 1 and re.search(r"分别|同时|都毕业|均毕业", q):
            raise HTTPException(
                422, detail="当前多校查询支持合并去重人数；逐校分别统计或要求同时毕业于多校，请拆成单校问题。"
            )
    remaining = q
    for school in schools:
        for name in sorted([school["name"], *school["aliases"]], key=len, reverse=True):
            remaining = remaining.replace(name, "")
    if re.search(r"[\u4e00-\u9fff]{2,}(?:大学|学院)", remaining):
        raise HTTPException(
            422, detail="问题包含尚未收录的院校，请使用院校字典中的名称；系统没有忽略学校条件。"
        )
    if "985" in q and "211" in q:
        values["school_tier"] = "211非985" if re.search(r"非985|不含985|排除985", q) else "985或211"
        if re.search(r"分别", q):
            raise HTTPException(422, detail="211包含985。请分别提问211或985的占比，或查询二者合并去重占比。")
    elif "985" in q:
        values["school_tier"] = "985"
    elif "211" in q:
        values["school_tier"] = "211"
    elif "双非" in q:
        values["school_tier"] = "双非"
    if values.get("school_tier"):
        values["education_scope"] = "any_completed" if re.search(r"任一|任何|曾经", q) else "highest"
    if "硕士" in q and "博士" in q:
        raise HTTPException(
            422, detail="请分别查询硕士或博士；合并人群可提问‘硕士及以上’，避免混淆精确学位与学历范围。"
        )
    if re.search(r"硕士(?:研究生)?(?:学历)?(?:及以上|以上)", q) or (
        "研究生" in q and not re.search("硕士|博士", q)
    ):
        values.update(minimum_education="硕士研究生", education_level=None, degree=None)
    elif re.search(r"本科(?:学历)?(?:及以上|以上)", q):
        values.update(minimum_education="本科", education_level=None, degree=None)
    elif "博士" in q:
        values.update(degree="博士", education_level=None, minimum_education=None)
    elif "硕士" in q:
        values.update(degree="硕士", education_level=None, minimum_education=None)
    elif "本科" in q:
        values.update(education_level="本科", degree=None, minimum_education=None)
    elif "专科" in q or "大专" in q:
        values.update(education_level="专科", degree=None, minimum_education=None)
    if "schools" not in values and any(
        key in values for key in ("degree", "minimum_education", "education_level")
    ):
        values.setdefault(
            "education_scope", "any_completed" if re.search(r"任一|任何|曾经", q) else "highest"
        )
    ratio = bool(re.search(r"比例|占比|百分比|百分之", q))
    education_requested = any(
        k in values for k in ("schools", "school_tier", "degree", "education_level", "minimum_education")
    )
    if education_requested and re.search(r"薪|工资", q):
        raise HTTPException(403, detail="薪酬汇总不支持按学历、学位或学校筛选。")
    if ratio and education_requested:
        values.update(
            kind="metric",
            metric="education_ratio",
            cohort="hires"
            if "入职" in q and "离职" not in q
            else "departures"
            if "离职" in q and "入职" not in q
            else "active",
        )
    elif re.search(r"入离职|入职.{0,10}离职|离职.{0,10}入职|净增", q):
        if re.search(r"名单|明细|哪些人", q):
            raise HTTPException(
                422, detail="请分别查询入职人员名单或离职人员名单；合并入离职目前提供汇总统计。"
            )
        values.update(kind="metric", metric="workforce_changes", cohort="active")
    elif re.search(r"周末|双休日|周六.*周日", q) and "加班" in q:
        values.update(kind="metric", metric="weekend_overtime_hours", cohort="active")
    elif education_requested and not re.search(r"加班|考勤|工时|在岗|请假|司龄|迟到|早退|出勤", q):
        metric = "hires" if "入职" in q else "departures" if "离职" in q else "headcount"
        values.update(metric=metric, cohort="active")
        if re.search(r"名单|明细|哪些人|列出.*员工", q):
            values["kind"] = "people"
        elif re.search(r"人数|多少|数量|几个", q):
            values["kind"] = "metric"
    if re.search(r"各部门|按部门", q):
        values["dimension"] = "department"
    elif re.search(r"各事业部|按事业部", q):
        values["dimension"] = "division"
    elif re.search(r"各团队|按团队", q):
        values["dimension"] = "team"
    elif re.search(r"按(?:最高)?学历", q):
        values["dimension"] = "education"
    elif re.search(r"按(?:最高)?学位", q):
        values["dimension"] = "degree"
    elif re.search(r"按(?:最高学历)?毕业(?:院校|学校)|按学校", q):
        values["dimension"] = "school"
        values["education_scope"] = "highest"
    time_dimensions = [
        key
        for pattern, key in [
            (r"每月|按月|各月|[和及、]月份", "month"),
            (r"每天|每日|按天", "day"),
            (r"每季度|按季度", "quarter"),
        ]
        if re.search(pattern, q)
    ]
    if time_dimensions:
        if values.get("dimension") or len(time_dimensions) > 1:
            raise HTTPException(422, detail="目前每次只支持一个分组维度。请先选择组织分组或时间趋势。")
        values["dimension"] = time_dimensions[0]
    for pattern, period in [
        (r"上季度|上一季度", "last_quarter"),
        (r"本季度|这季度", "this_quarter"),
        (r"今年|本年度", "this_year"),
        (r"去年|上一年", "last_year"),
        (r"上周", "last_week"),
        (r"本周|这周", "this_week"),
        (r"上个月|上月", "last_month"),
        (r"本月|这个月", "this_month"),
    ]:
        if re.search(pattern, q):
            values.update(period=period, start_date=None, end_date=None)
            break
    if (
        "period" not in values
        and education_requested
        and values.get("metric") in ("headcount", "education_ratio")
        and values.get("cohort", "active") == "active"
        and not re.search(r"\d{4}|季度|去年|上月|上周|近", q)
    ):
        values.update(period="as_of", start_date=None, end_date=None)
    if "period" not in values and values.get("metric") == "weekend_overtime_hours":
        values.update(period="this_month", start_date=None, end_date=None)
    return values, notes


def enforce(plan, question, constraints):
    if plan.kind in ("clarify", "refuse"):
        return plan, []
    before = plan.model_dump()
    after = {**before, **constraints}
    if after["kind"] != "metric":
        after["dimension"] = "none"
    corrected = QueryPlan.model_validate(after)
    return corrected, [
        {"field": key, "model_value": before.get(key), "executed_value": value}
        for key, value in corrected.model_dump().items()
        if before.get(key) != value
    ]
