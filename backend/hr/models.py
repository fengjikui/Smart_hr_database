from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MetricId = Literal[
    "headcount",
    "hires",
    "departures",
    "turnover_rate",
    "avg_tenure",
    "attendance_rate",
    "late_count",
    "late_rate",
    "abnormal_count",
    "approved_overtime_hours",
    "late_departure_hours",
    "avg_work_hours",
    "leave_days",
    "avg_salary",
    "workforce_changes",
    "weekend_overtime_hours",
    "education_ratio",
]
Dimension = Literal[
    "none",
    "division",
    "department",
    "job_family",
    "location",
    "employment_type",
    "relation",
    "month",
    "day",
    "team",
    "education",
    "degree",
    "school",
    "quarter",
]
Period = Literal[
    "as_of",
    "today",
    "this_month",
    "last_month",
    "last_30_days",
    "last_6_months",
    "this_quarter",
    "last_quarter",
    "this_year",
    "last_year",
    "this_week",
    "last_week",
    "custom",
]
Relation = Literal["all", "direct", "indirect", "subordinates", "self"]


class QueryPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: Literal["metric", "people", "attendance", "clarify", "refuse"] = "metric"
    metric: MetricId = "headcount"
    dimension: Dimension = "none"
    period: Period = "this_month"
    relation: Relation = "all"
    department: str | None = Field(default=None, max_length=80)
    employee_name: str | None = Field(default=None, max_length=40)
    education_level: Literal["高中及以下", "专科", "本科", "硕士研究生", "博士研究生"] | None = None
    minimum_education: Literal["高中及以下", "专科", "本科", "硕士研究生", "博士研究生"] | None = None
    degree: Literal["无学位", "学士", "硕士", "博士"] | None = None
    schools: list[str] = Field(default_factory=list, max_length=5)
    school_tier: Literal["985", "211", "985或211", "211非985", "双非"] | None = None
    cohort: Literal["active", "hires", "departures"] = "active"
    education_scope: Literal["highest", "any_completed"] = "highest"
    start_date: str | None = None
    end_date: str | None = None
    limit: int = Field(default=20, ge=1, le=100)
    message: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def dates(self):
        if self.cohort != "active" and self.metric != "education_ratio":
            raise ValueError("人群基数仅用于教育背景占比")
        if self.education_level and self.minimum_education:
            raise ValueError("学历精确筛选与最低学历不能同时指定")
        if any(not name.strip() or len(name) > 80 for name in self.schools):
            raise ValueError("学校名称需为1–80字符")
        self.schools = list(dict.fromkeys(name.strip() for name in self.schools))
        for value in (self.start_date, self.end_date):
            if value:
                date.fromisoformat(value)
        if self.period == "custom" and (not self.start_date or not self.end_date):
            raise ValueError("自定义期间需要起止日期")
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("开始日期不能晚于结束日期")
        if self.period != "custom" and (self.start_date or self.end_date):
            raise ValueError("明确日期必须使用 custom 期间")
        return self


class QuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=2, max_length=600)
    previous_id: str | None = Field(default=None, max_length=80)


class MetadataRequest(BaseModel):
    """Model-only control message; never accepted by the SQL query endpoint."""

    model_config = ConfigDict(extra="forbid", strict=True)
    kind: Literal["inspect"]
    ids: list[str] = Field(default_factory=list, max_length=6)
    search: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def requested(self):
        if not self.ids and not self.search:
            raise ValueError("补充读取必须指定语义ID或检索词")
        if any(not x or len(x) > 120 for x in self.ids):
            raise ValueError("语义ID长度无效")
        return self


class DashboardRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=80)
    plan: QueryPlan


class PersonaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    persona_id: str = Field(max_length=20)
