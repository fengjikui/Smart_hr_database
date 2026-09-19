"""V2 字段、指标口径与请求协议的单一词汇表。

FIELDS/METRICS 为目录披露、权限依赖和两种编译器提供共同 ID；Plan 是模型
与页面提交的受限查询描述，不包含 SQL、数据库 ID、执行账号或授权人员集合。
结构校验在本文件，依赖身份的业务/权限校验在 query.validate。
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# 保留来源字段 ID；只纳入 20 个演示问题所需字段和部门主管关联字段。
# 每项依次为中文名称、权限字段组、定义；registry 再补口语别名与“不是”的说明。
FIELDS = {
    "person_id": ("人员ID", "basic", "人员主键，非工号，员工唯一记录"),
    "employee_no": ("工号", "basic", "字符串标识，保留前导零"),
    "name": ("姓名", "basic", "展示姓名，重名时以工号区分"),
    "head_person_id": ("直接主管ID", "basic", "管理关系，关联person_id，不是HRBP"),
    "dept_master_id": ("部门主管ID", "basic", "部门主管关联person_id，当前不单独授权"),
    "dept_hrbp_id": ("HRBP人员ID", "basic", "HRBP服务关系，允许指向本人"),
    "dept_code": ("部门编码", "basic", "当前部门编码，无历史归属"),
    "dept_cn_name": ("部门", "basic", "当前部门名称，历史事件也按当前部门分组"),
    "onboard_date": ("入职日期", "basic", "本次演示采用的入职日期，不等于任职开始日期"),
    "termin_date": ("离职日期", "basic", "离职当天已不在职，空值表示未离职"),
    "birth_date": ("出生日期", "basic", "计算快照日周岁的依据，缺失时年龄未知"),
    "age": ("年龄", "basic", "快照日的周岁，30至40含两个边界"),
    "school_name": ("学校", "education", "宽表当前教育记录的院校，无完整多段教育历史"),
    "first_major": ("专业", "education", "当前教育记录第一专业"),
    "diploma_code_desc": (
        "学历",
        "education",
        "高中及以下、专科、本科、硕士研究生、博士研究生；硕士及以上包括博士",
    ),
    "degree_code_desc": ("学位", "education", "无学位、学士、硕士、博士；与学历分开"),
    "full_time_flag": ("是否全日制", "education", "是、否或未知"),
    "education_expired_date": ("毕业时间", "education", "演示假设等同教育结束日期，真实源待确认"),
    "hire_type_code_desc": ("招聘类型", "employment", "校园招聘或社会招聘；未知不判为校园招聘"),
    "labour_type_code_desc": ("用工类型", "employment", "正式、外包、实习"),
    "position_code_desc": ("岗位", "employment", "当前岗位名称，无前一岗位历史"),
    "current_employment_start_date": ("当前任职开始日期", "employment", "仅当前任职开始，不表示完整调岗事件"),
    "confirmation_date": ("转正日期", "employment", "实际已转正日期，不是预计日期"),
    "formalize_flag": ("是否已转正", "employment", "是或否，需与转正日期一致"),
    "contract_type_code_desc": ("合同类型", "contract", "合同类型说明，独立字段权限组"),
    "contract_end_date": ("合同到期日期", "contract", "允许查询未来到期日期，空值不视为即将到期"),
}
# 学历排序和院校标签是明确的小型演示字典；不能把它当作实时、完整院校数据源。
LEVELS = {"高中及以下": 1, "专科": 2, "本科": 3, "硕士研究生": 4, "博士研究生": 5}
SCHOOLS = {
    "清华大学": (1, 1),
    "北京大学": (1, 1),
    "浙江大学": (1, 1),
    "复旦大学": (1, 1),
    "西安电子科技大学": (0, 1),
    "深圳大学": (0, 0),
    "南京工业大学": (0, 0),
}
# 每项依次为名称、单位、依赖字段、口径。依赖字段参与权限检查，不只是文档。
METRICS = {
    "count": ("人数", "人", ["person_id"], "符合当前人群与筛选条件的去重员工人数"),
    "hires": ("入职人数", "人", ["onboard_date"], "期间入职人数，不要求现在仍在职"),
    "departures": ("离职人数", "人", ["termin_date"], "期间离职人数"),
    "net_change": ("净增人数", "人", ["onboard_date", "termin_date"], "期间入职减离职"),
    "masters_count": ("硕士及以上人数", "人", ["diploma_code_desc"], "当前学历为硕士研究生或博士研究生人数"),
    "masters_ratio": (
        "硕士及以上占比",
        "%",
        ["diploma_code_desc"],
        "硕士及以上人数/同组全部人群；未知学历计入分母",
    ),
    "doctors_count": (
        "博士学位人数",
        "人",
        ["degree_code_desc", "education_expired_date"],
        "当前已取得博士学位人数",
    ),
    "school_985_count": ("985人数", "人", ["school_name"], "当前教育院校在演示985字典中的人数"),
    "school_211_count": ("211人数", "人", ["school_name"], "当前教育院校在演示211字典中的人数，包含985"),
    "school_985_ratio": ("985占比", "%", ["school_name"], "985人数/同组全部人群，未知院校仍计入分母"),
    "school_211_ratio": ("211占比", "%", ["school_name"], "211人数/同组全部人群，不能与985相加"),
    "outsource_count": ("外包人数", "人", ["labour_type_code_desc"], "用工类型为外包人数"),
    "outsource_ratio": ("外包占比", "%", ["labour_type_code_desc"], "外包人数/同组全部人群"),
    "avg_age": (
        "平均年龄",
        "岁",
        ["birth_date", "age"],
        "快照日有效周岁平均值，未知不入平均，另给有效样本数",
    ),
    "avg_confirmation_days": (
        "平均转正用时",
        "天",
        ["confirmation_date", "onboard_date"],
        "有效转正日期减入职日期的平均天数",
    ),
}
DIMENSIONS = {
    k: FIELDS[k][0]
    for k in (
        "dept_cn_name",
        "diploma_code_desc",
        "full_time_flag",
        "school_name",
        "labour_type_code_desc",
        "hire_type_code_desc",
        "position_code_desc",
    )
}
DIMENSIONS.update(
    relation="汇报关系",
    onboard_month="入职月份",
    termin_month="离职月份",
    event_month="事件月份",
    confirmation_month="转正月份",
)
DATE_FIELDS = (
    "onboard_date",
    "termin_date",
    "contract_end_date",
    "confirmation_date",
    "current_employment_start_date",
    "employment_events",
)
FieldName = Literal[*tuple(FIELDS)]
MetricName = Literal[*tuple(METRICS)]
DimensionName = Literal[*tuple(DIMENSIONS)]


# 拒绝额外字段和隐式类型转换，防止请求偷偷携带 sql 等协议外控制参数。
class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


# 筛选只支持少量明确操作；values 使用字符串，由字段专属校验/编译器解释类型。
class Filter(Strict):
    field: FieldName
    op: Literal["eq", "in", "gte", "lte", "contains", "not_null"] = "eq"
    values: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def valid(self):
        if self.op != "not_null" and not self.values:
            raise ValueError("筛选值不能为空")
        if self.op not in ("in", "not_null") and len(self.values) != 1:
            raise ValueError("该操作需要一个值")
        if any(len(v) > 100 for v in self.values):
            raise ValueError("筛选值过长")
        return self


class Order(Strict):
    field: str = Field(max_length=50)
    direction: Literal["asc", "desc"] = "asc"


# kind 同时覆盖执行计划与图控制动作：inspect 补读定义，clarify 请求澄清。
# scope 是问题想看的子范围，不是授权范围；服务端永远与真实授权取交集。
class Plan(Strict):
    kind: Literal["aggregate", "people", "clarify", "inspect"] = "aggregate"
    scope: Literal["all", "reports", "direct", "indirect", "hrbp", "inherited_hrbp", "self"] = "all"
    population: Literal["active", "all", "confirmed"] = "active"
    departments: list[str] = Field(default_factory=list, max_length=8)
    filters: list[Filter] = Field(default_factory=list, max_length=12)
    date_field: Literal[*DATE_FIELDS] | None = None
    start_date: str | None = None
    end_date: str | None = None
    group_by: list[DimensionName] = Field(default_factory=list, max_length=2)
    metrics: list[MetricName] = Field(default_factory=lambda: ["count"], min_length=1, max_length=5)
    columns: list[FieldName] = Field(
        default_factory=lambda: ["employee_no", "name", "dept_cn_name"], max_length=12
    )
    order_by: list[Order] = Field(default_factory=list, max_length=2)
    page: int = Field(default=1, ge=1, le=10000)
    page_size: int = Field(default=50, ge=1, le=200)
    message: str | None = Field(default=None, max_length=400)
    inspect_ids: list[str] = Field(default_factory=list, max_length=6)

    @model_validator(mode="after")
    def valid(self):
        # 此处只检查与具体用户无关的结构关系；日期上界、字段权限等在 query 中检查。
        for key in ("columns", "metrics", "group_by", "departments"):
            values = getattr(self, key)
            if len(set(values)) != len(values):
                raise ValueError(f"{key}不能重复")
        if self.kind == "people" and not self.columns:
            raise ValueError("明细至少选一个字段")
        if self.date_field and (not self.start_date or not self.end_date):
            raise ValueError("日期筛选需要起止日期")
        if not self.date_field and (self.start_date or self.end_date):
            raise ValueError("日期必须说明筛选字段")
        if self.start_date and self.end_date:
            start, end = date.fromisoformat(self.start_date), date.fromisoformat(self.end_date)
            if start > end or (end - start).days > 366:
                raise ValueError("期间顺序错误或跨度超过366天")
        if (
            any(x in self.metrics for x in ("hires", "departures", "net_change"))
            and not self.date_field
            and self.kind == "aggregate"
        ):
            raise ValueError("入离职指标需要期间")
        if any(len(d) > 80 or not d.strip() for d in self.departments):
            raise ValueError("部门名称无效")
        return self


# previous_id 只是历史引用，恢复时仍检查归属和当前授权，不信任前端传回旧结果。
class Question(Strict):
    question: str = Field(min_length=2, max_length=800)
    previous_id: str | None = Field(default=None, max_length=60)
