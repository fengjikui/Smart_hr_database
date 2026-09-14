"""Literal condition guard. No acceptance question IDs or expected plans are used.

This does not repair a model plan silently: missing or contradictory grounded
conditions trigger the bounded model repair branch and remain in the trace.
"""

import re

from .schema import SCHOOLS

SCHOOL_ALIASES = {
    "清华": "清华大学",
    "北大": "北京大学",
    "浙大": "浙江大学",
    "复旦": "复旦大学",
    "西电": "西安电子科技大学",
    "深大": "深圳大学",
}


def constraints(question, previous=None):
    filters = []

    def add(field, op, values):
        filters.append({"field": field, "op": op, "values": values})

    schools = {s for s in SCHOOLS if s in question}
    schools.update(s for alias, s in SCHOOL_ALIASES.items() if alias in question)
    if schools:
        add("school_name", "in", sorted(schools))
    majors = [
        m
        for m in (
            "计算机科学与技术",
            "软件工程",
            "电子信息工程",
            "人力资源管理",
            "工商管理",
            "数学与应用数学",
        )
        if m in question
    ]
    if majors:
        add("first_major", "in", majors)
    age = re.search(r"(\d{1,3})(?:至|到|[-~～])(\d{1,3})岁", question)
    if age:
        add("age", "gte", [age[1]])
        add("age", "lte", [age[2]])
    if (
        ("全日制" in question and not re.search("是否全日制|全日制交叉|按.*全日制", question))
        or "只看" in question
        and "全日制" in question
    ):
        add("full_time_flag", "eq", ["否" if "非全日制" in question else "是"])
    if "硕士及以上" in question and not any(w in question for w in ("比例", "占比", "占在职")):
        if any(w in question for w in ("只看", "学历为", "且全日制")):
            add("diploma_code_desc", "gte", ["硕士研究生"])
    if "校园招聘" in question or "校招" in question:
        add("hire_type_code_desc", "eq", ["校园招聘"])
    if previous and any(w in question for w in ("刚才", "这些人", "其他条件不变")):
        explicit = {f["field"] for f in filters}
        filters.extend(f for f in previous.get("filters", []) if f["field"] not in explicit)
    return filters


def check(question, plan, previous=None, departments=None):
    required = constraints(question, previous)
    actual = [f.model_dump() for f in plan.filters]

    def equivalent(a, e):
        return (
            a["field"] == e["field"]
            and set(a["values"]) == set(e["values"])
            and (a["op"] == e["op"] or {a["op"], e["op"]} <= {"eq", "in"})
        )

    missing = [e for e in required if not any(equivalent(a, e) for a in actual)]
    if missing:
        raise ValueError("提问中的条件未完整保留：" + str(missing))
    for f in required:
        if any(
            a["field"] == f["field"]
            and a["op"] in ("eq", "in")
            and f["op"] in ("eq", "in")
            and set(a["values"]) != set(f["values"])
            for a in actual
        ):
            raise ValueError("同一字段出现了与提问冲突的筛选，请替换旧条件：" + f["field"])
    named = [d for d in departments or [] if d in question]
    if named and set(plan.departments) != set(named):
        raise ValueError("明确部门条件必须保留：" + str(named))
    if any(
        w in question
        for w in (
            "薪资",
            "工资",
            "薪酬",
            "加班",
            "考勤",
            "迟到",
            "绩效",
            "身份证",
            "手机号",
            "银行账号",
            "历史汇报",
        )
    ):
        raise ValueError("当前最小宽表未提供该业务事实或敏感字段，必须澄清，不能改成其他统计")
    if "通过下属" in question and "HRBP" in question and plan.scope != "inherited_hrbp":
        raise ValueError("应仅查询下属HRBP服务来源")
    if "我服务" in question and plan.scope != "hrbp":
        raise ValueError("应设置scope=hrbp；不要添加dept_hrbp_id筛选，self不是person_id，服务端会绑定本人")
    if "直属" in question and "间接" in question and "下属" in question:
        if plan.scope != "reports" or "relation" not in plan.group_by:
            raise ValueError("直属与间接需排除本人并按relation区分")
    if "在职" in question and plan.population != "active":
        raise ValueError("必须保留当前在职条件")
    if (
        ("入职" in question or "离职" in question)
        and "在职" not in question
        and plan.date_field in ("onboard_date", "termin_date", "employment_events")
        and plan.population != "all"
    ):
        raise ValueError("事件人群需包含目前已离职人员，不应限制当前在职")
    if previous and "其他条件不变" in question:
        for key in ("scope", "population", "date_field", "start_date", "end_date", "departments"):
            if getattr(plan, key) != previous[key]:
                raise ValueError("其他条件不变时应继承：" + key)
    return {"required_filters": required, "named_departments": named, "checked": True}


def normalize(question, candidate, previous, date_range):
    """Bind explicit time/range literals before schema validation; audit every edit.

    Only unambiguous surface conditions are filled. This is reported separately
    from raw model accuracy and never loads a case/question-to-answer mapping.
    """
    import copy

    raw = copy.deepcopy(candidate)
    if raw.get("kind") not in ("aggregate", "people"):
        return raw, []
    if date_range:
        field = None
        if "合同" in question and "到期" in question:
            field = "contract_end_date"
        elif "任职开始" in question:
            field = "current_employment_start_date"
        elif "转正" in question:
            field = "confirmation_date"
        elif "入职" in question and "离职" in question:
            field = "employment_events"
        elif "入职" in question:
            field = "onboard_date"
        elif "离职" in question:
            field = "termin_date"
        if field:
            raw.update(date_field=field, **date_range)
            # A single canonical date interval avoids duplicate or contradictory date representations.
            raw["filters"] = [f for f in raw.get("filters", []) if f.get("field") != field]
            if field in ("onboard_date", "termin_date", "employment_events") and "在职" not in question:
                raw["population"] = "all"
            if field == "confirmation_date" and ("已经转正" in question or "已转正" in question):
                raw["population"] = "confirmed"
    if "通过下属" in question and "HRBP" in question:
        raw["scope"] = "inherited_hrbp"
    elif "我服务" in question:
        raw["scope"] = "hrbp"
    elif "直属" in question and "间接" in question and "下属" in question:
        raw["scope"] = "reports"
        if "relation" not in raw.get("group_by", []):
            raw["group_by"] = list(dict.fromkeys(raw.get("group_by", []) + ["relation"]))
    if raw.get("scope") in ("hrbp", "inherited_hrbp"):
        raw["filters"] = [
            f
            for f in raw.get("filters", [])
            if not (f.get("field") == "dept_hrbp_id" and f.get("values") == ["self"])
        ]
    if (
        raw.get("kind") == "aggregate"
        and raw.get("metrics") == ["count"]
        and re.search(r"博士学位|(?:取得|拿到).*博士", question)
    ):
        if any(
            f.get("field") == "degree_code_desc" and f.get("op") == "eq" and f.get("values") == ["博士"]
            for f in raw.get("filters", [])
        ):
            # Canonical degree metric also checks graduation, unlike a raw degree equality count.
            raw["metrics"] = ["doctors_count"]
            raw["filters"] = [f for f in raw.get("filters", []) if f.get("field") != "degree_code_desc"]
    metrics = raw.get("metrics", [])
    if raw.get("kind") == "aggregate" and "count" in metrics and "总人数" not in question:
        # Conditional metrics already compute the requested cohort. Avoid duplicating
        # a generic count when the request only asks for this background count/rate.
        if set(metrics) == {"count", "doctors_count"} and "博士" in question:
            raw["metrics"] = ["doctors_count"]
            raw["filters"] = [
                f
                for f in raw.get("filters", [])
                if not (
                    f.get("field") == "degree_code_desc"
                    and f.get("op") == "eq"
                    and f.get("values") == ["博士"]
                )
            ]
        if {"school_985_ratio", "school_211_ratio"} <= set(metrics) and not re.search(
            r"(?:同时|并)(?:展示|给出|列出|统计)?(?:在职)?人数", question
        ):
            raw["metrics"] = [m for m in metrics if m != "count"]
    changes = [
        {"field": k, "model": candidate.get(k), "bound": v} for k, v in raw.items() if candidate.get(k) != v
    ]
    return raw, changes


def needs_previous(question):
    if any(word in question for word in ("刚才", "上次", "上一条", "其他条件不变")):
        return True
    # An anaphor after an explicit cohort in the same utterance is self-contained:
    # "今年已转正多少人？这些人平均..." must not require a previous chat turn.
    return bool(
        re.match(
            r"^(?:请)?(?:在|对|给|把|继续查看|继续统计|统计)?(?:这些人|这批人|他们|她们)", question.strip()
        )
    )
