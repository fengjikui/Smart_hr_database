from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MetricId = Literal['headcount','hires','departures','turnover_rate','avg_tenure','attendance_rate','late_count','late_rate','abnormal_count','approved_overtime_hours','late_departure_hours','avg_work_hours','leave_days','avg_salary']
Dimension = Literal['none','division','department','job_family','location','employment_type','relation','month','day']
Period = Literal['as_of','today','this_month','last_month','last_30_days','last_6_months','custom']
Relation = Literal['all','direct','indirect','subordinates','self']


class QueryPlan(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    kind: Literal['metric','people','attendance','clarify','refuse'] = 'metric'
    metric: MetricId = 'headcount'
    dimension: Dimension = 'none'
    period: Period = 'this_month'
    relation: Relation = 'all'
    department: str | None = Field(default=None,max_length=80)
    employee_name: str | None = Field(default=None,max_length=40)
    start_date: str | None = None
    end_date: str | None = None
    limit: int = Field(default=20,ge=1,le=100)
    message: str | None = Field(default=None,max_length=300)

    @model_validator(mode='after')
    def dates(self):
        for value in (self.start_date,self.end_date):
            if value:
                date.fromisoformat(value)
        if self.period=='custom' and (not self.start_date or not self.end_date):
            raise ValueError('自定义期间需要起止日期')
        if self.start_date and self.end_date and self.start_date>self.end_date:
            raise ValueError('开始日期不能晚于结束日期')
        if self.period!='custom' and (self.start_date or self.end_date):
            raise ValueError('明确日期必须使用 custom 期间')
        return self


class QuestionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    question: str = Field(min_length=2,max_length=600)
    previous_id: str | None = Field(default=None,max_length=80)


class DashboardRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=1,max_length=80)
    plan: QueryPlan


class PersonaRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    persona_id: str = Field(max_length=20)
