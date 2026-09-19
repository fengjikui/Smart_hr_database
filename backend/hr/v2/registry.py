"""版本化语义目录：为模型与页面组织字段说明、口语别名和指标口径。

基础词汇来自 schema，权限来自 auth；只披露当前用户可用的字段与指标。
当前目录规模小，采用代码版本管理与按需展开，没有向量库或外部知识库。
"""

from . import auth, store
from .schema import DIMENSIONS, FIELDS, METRICS

VERSION = "v2-semantics-1"
ALIASES = {
    "person_id": ["人员主键", "人员标识"],
    "employee_no": ["员工编号", "工号"],
    "name": ["名字", "员工姓名"],
    "head_person_id": ["直属领导", "汇报给", "直接上级"],
    "dept_hrbp_id": ["人力BP", "服务HRBP", "HR业务伙伴"],
    "dept_master_id": ["部门负责人"],
    "dept_cn_name": ["部门名称", "组织", "团队"],
    "onboard_date": ["入司时间", "入职时间", "新入职"],
    "termin_date": ["离司时间", "离职时间"],
    "birth_date": ["生日"],
    "age": ["周岁", "岁数"],
    "school_name": ["院校", "毕业学校", "母校"],
    "first_major": ["第一专业", "所学专业"],
    "diploma_code_desc": ["文化程度", "学历背景"],
    "degree_code_desc": ["学位", "博士学位"],
    "full_time_flag": ["学习形式", "全日制"],
    "education_expired_date": ["毕业日期", "教育结束时间"],
    "hire_type_code_desc": ["校招", "社招", "招聘来源"],
    "labour_type_code_desc": ["外包", "用工性质"],
    "position_code_desc": ["职位", "现岗位"],
    "current_employment_start_date": ["当前任职时间", "现岗位起始日"],
    "confirmation_date": ["实际转正日"],
    "formalize_flag": ["转正状态"],
    "contract_end_date": ["合同截止日", "合同到期时间"],
    "contract_type_code_desc": ["合同性质"],
}
NOTES = {
    "school_name": "不是任意一段教育经历；985、211为演示院校字典标签，211包含985。",
    "diploma_code_desc": "不是学位；“硕士及以上”包含博士，“硕士”精确学历不包含博士。",
    "degree_code_desc": "不是学历；学位和学历不能互相推断。",
    "age": "不是系统时间计算的实岁，也不是平均司龄；以数据截止日和出生日期计算。",
    "dept_cn_name": "不是入职或离职当时的部门；本数据不保留任职历史。",
    "current_employment_start_date": "不是入职时间，也不能推出上一个岗位。",
    "dept_hrbp_id": "不是管理线；HRBP服务的员工不会因此变成HRBP的管理下属。",
    "dept_master_id": "不能单独产生可见权限，暂只做关联字段。",
    "head_person_id": "不是部门归属，不沿HRBP服务边递归。",
}


def catalog(p):
    """生成本用户的目录快照；指标的全部依赖字段有权限时才允许出现在目录。"""
    allowed = auth.allowed_fields(p)
    fields = []
    for key, (label, group, description) in FIELDS.items():
        if key not in allowed:
            continue
        fields.append(
            {
                "id": "people." + key,
                "key": key,
                "table_id": "people",
                "label": label,
                "group": group,
                "aliases": ALIASES.get(key, [label]),
                "description": description,
                "not_meaning": NOTES.get(key, "不代表其他未提供的历史记录或业务事实。"),
                "type": "integer" if key == "age" else "date" if key.endswith("_date") else "string",
                "nullable": key not in ("person_id", "employee_no", "name"),
            }
        )
    metrics = [
        {
            "id": "metric." + key,
            "key": key,
            "label": v[0],
            "unit": v[1],
            "fields": ["people." + f for f in v[2]],
            "definition": v[3],
            "aliases": [v[0]],
            "null_rule": "比例分母含未知；平均数排除未知，零分母返回空值。",
            "rounding": "四舍五入保留2位小数",
            "scope_rule": "当前授权范围与问题条件取交集后计算",
        }
        for key, v in METRICS.items()
        if set(v[2]) <= allowed
    ]
    dims = {k: v for k, v in DIMENSIONS.items() if k not in FIELDS or k in allowed}
    # 候选值也可能泄露组织信息，因此部门来自授权人员，不从全量字典照搬。
    ids = set(auth.grants(p)["ids"])
    departments = sorted({r["dept_cn_name"] for r in auth.people(p) if r["person_id"] in ids})
    return {
        "version": VERSION,
        "fields": fields,
        "metrics": metrics,
        "dimensions": dims,
        "departments": departments,
        "as_of": store.AS_OF,
        "storage": "版本化Python目录保存字段与口径；应用SQLite保留会话、审计与历史。业务数据与授权以当前查询后端为准；26字段采用索引加按需披露，无向量库。",
    }


def disclose(p, ids):
    """模型 inspect 的受限补读入口；未知或未授权 ID 不会返回定义。"""
    c = catalog(p)
    lookup = {d["id"]: d for d in c["fields"] + c["metrics"]}
    return [lookup[i] for i in ids if i in lookup]
