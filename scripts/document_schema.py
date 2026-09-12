"""Regenerate the field dictionary from the actual SQLite schemas and semantic source."""

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLES = {
    "dataset_meta": "数据集元信息；每个配置键一行",
    "legal_entities": "法人主体；每个主体一行",
    "locations": "办公地点；每个地点一行",
    "departments": "组织节点；四级树，每个组织一行",
    "job_families": "岗位序列；每个序列一行",
    "grades": "职级及模拟薪资范围；每级一行",
    "positions": "岗位字典；每个岗位一行",
    "employees": "人员基础档案；每名员工一行",
    "employee_private": "私人信息；每名员工一行，全部SIM标记且不开放查询",
    "assignments": "任职历史；每个人每段连续任职一行，左闭右开",
    "reporting_closure": "当前管理关系闭包；每个祖先/后代对一行",
    "work_calendar": "演示工作日历；每天一行，未接正式节假日调休",
    "shift_policies": "班次政策；每个政策版本一行",
    "attendance_daily": "每日考勤事实；每人每个应工作日一行",
    "leave_requests": "整日请假申请；每人每日最多一行",
    "overtime_requests": "加班申请；每人每日最多一行，与晚离岗分开",
    "compensation": "基本月薪有效期记录；受限汇总来源",
    "performance_reviews": "绩效评价；每人每周期一行，尚未开放查询",
    "training_courses": "培训课程；每门课一行，尚未开放查询",
    "training_enrollments": "培训参加记录；每人每课程一行，尚未开放查询",
    "recruitment_requisitions": "招聘需求；每个需求一行，尚未开放查询",
    "principals": "演示主体及授权；每个演示身份一行",
    "sessions": "会话；仅保存令牌摘要，不保存原令牌",
    "metrics": "已发布指标目录；每个指标一行JSON定义",
    "metric_search": "由指标目录派生的FTS5 trigram检索索引，可重建",
    "dashboards": "私人看板；存查询计划，不持久复制结果",
    "audit_events": "应用审计事件；不包含业务结果或个人证件",
    "conversations": "最小对话记录；用于同一身份的前次计划继承",
}
FIELDS = {
    "id": "记录标识",
    "name": "业务名称",
    "key": "配置键",
    "value": "配置值",
    "employee_id": "员工标识",
    "employee_no": "稳定工号（CC前缀）",
    "gender": "模拟性别，未开放查询条件",
    "birth_date": "模拟出生日期，未开放查询条件",
    "hire_date": "最近入职日期",
    "termination_date": "离职日期；当日不计在职，空表示未离职",
    "employment_type": "正式/实习/外包",
    "entity_id": "法人主体标识",
    "location_id": "地点标识",
    "email": "保留示例域名邮箱",
    "phone": "SIM模拟电话标记",
    "identity_document": "SIM模拟证件标记",
    "bank_account": "SIM模拟银行账户标记",
    "parent_id": "父组织；根节点为空",
    "level": "公司1/事业部2/部门3/团队4",
    "division_id": "所属事业部标识",
    "family_id": "岗位序列标识",
    "is_manager": "管理岗位标记0/1",
    "salary_min": "模拟月薪下限，元",
    "salary_max": "模拟月薪上限，元",
    "department_id": "任职或需求所属组织",
    "manager_id": "直属上级员工标识",
    "position_id": "岗位标识",
    "grade_id": "职级标识",
    "valid_from": "生效日期，包含当天",
    "valid_to": "结束日期，不包含当天；空表示当前",
    "ancestor_id": "管理链祖先员工标识",
    "descendant_id": "管理链后代员工标识",
    "depth": "0本人/1直属/2及以上间接",
    "day": "业务日期YYYY-MM-DD",
    "is_workday": "应工作日标记0/1",
    "note": "备注与模拟日历说明",
    "timezone": "IANA时区",
    "earliest_in": "弹性到岗起点；距午夜分钟",
    "latest_in": "迟到阈值；距午夜分钟",
    "earliest_out": "最早应离岗；距午夜分钟",
    "required_work_minutes": "要求净工作分钟",
    "lunch_minutes": "午休分钟",
    "version": "定义版本",
    "shift_id": "班次政策标识",
    "status": "业务状态；取值由对应表约束与生成器定义",
    "check_in": "到岗时刻；距午夜分钟，缺卡可空",
    "check_out": "离岗时刻；距午夜分钟，缺卡可空",
    "work_minutes": "扣除午休后的净在岗分钟",
    "late_minutes": "超过09:30的分钟数",
    "early_minutes": "早于个人应离岗的分钟数",
    "late_departure_minutes": "超过个人应离岗的分钟数，不等于批准加班",
    "leave_type": "模拟假别",
    "days": "请假天数；当前仅整日",
    "approval_status": "已批准/待审批/已拒绝",
    "approver_id": "审批人员工标识",
    "minutes": "申请加班分钟",
    "monthly_base": "模拟基本月薪金额，元",
    "currency": "币种CNY",
    "period": "评价周期",
    "rating": "卓越/优秀/达标/待提升",
    "reviewer_id": "评价人员工标识",
    "hours": "课程时长，小时",
    "course_id": "课程标识",
    "completed_at": "完成日期，可空",
    "openings": "招聘名额",
    "opened_at": "需求创建日期",
    "role": "角色类型",
    "label": "身份显示名称",
    "title": "显示标题",
    "scope_mode": "reports/organization/self",
    "scope_root": "授权根：员工或组织ID，取决于scope_mode",
    "salary_aggregate": "薪酬受限聚合能力0/1",
    "can_export": "导出能力0/1，仍受指标和范围限制",
    "enabled": "账号启用0/1",
    "policy_version": "权限策略版本",
    "token_hash": "会话令牌SHA-256摘要",
    "principal_id": "应用身份标识",
    "csrf": "会话CSRF校验值",
    "expires_at": "到期Unix时间戳秒",
    "definition": "指标JSON定义",
    "content": "派生检索文本",
    "owner_id": "看板所属身份",
    "plan": "严格类型查询计划JSON",
    "catalog_version": "指标目录版本",
    "created_at": "记录创建时间ISO格式",
    "action": "操作名称",
    "outcome": "执行或授权结果",
    "metric_id": "指标标识",
    "scope_count": "该次授权候选人数（不等于在职人数）",
    "duration_ms": "操作时长毫秒",
    "question": "用户问题；生产需制定脱敏及留存策略",
}


def generate():
    lines = [
        "# 数据与字段字典",
        "",
        "由 `scripts/document_schema.py` 从实际建库结构和指标源生成。",
        "日期为YYYY-MM-DD；业务按Asia/Shanghai。字段存在不等于开放查询权限。主键/空值以实际DDL约束为准。",
        "",
    ]
    for filename, heading in [("hr.sqlite", "业务库"), ("app.sqlite", "应用库")]:
        lines += [f"## {heading} `{filename}`", ""]
        db = sqlite3.connect(f"file:{ROOT / 'data' / filename}?mode=ro", uri=True)
        names = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY rowid")]
        for name in names:
            if name not in TABLES:
                continue
            lines += [
                f"### `{name}`",
                "",
                TABLES[name],
                "",
                "| 字段 | 类型 | 约束/关联 | 含义 |",
                "|---|---|---|---|",
            ]
            foreign = {r[3]: f"{r[2]}.{r[4]}" for r in db.execute(f'PRAGMA foreign_key_list("{name}")')}
            for _, field, kind, required, default, pk in db.execute(f'PRAGMA table_info("{name}")'):
                constraints = []
                if pk:
                    constraints.append(f"PK({pk})")
                if required:
                    constraints.append("NOT NULL")
                if default is not None:
                    constraints.append(f"默认 {default}")
                if field in foreign:
                    constraints.append(f"→ {foreign[field]}")
                lines.append(
                    f"| `{field}` | {kind or 'FTS text'} | {', '.join(constraints) or '—'} | {FIELDS[field]} |"
                )
            lines.append("")
        db.close()
    source = json.loads((ROOT / "semantic/catalog.json").read_text())
    lines += [
        "## 指标目录",
        "",
        f"发布版本：`{source['version']}`。具体公式由 `backend/hr/query.py` 确定性实现，修改需同步定义与回归。",
        "",
    ]
    for metric in source["metrics"]:
        lines += [
            f"### {metric['name']} `{metric['id']}`",
            "",
            metric["description"],
            "",
            f"单位：{metric['unit']}；敏感等级：`{metric['sensitivity']}`；最小组规模：{metric['minimum_group_size']}。",
            f"支持分组：{', '.join(metric['dimensions'])}。来源：{', '.join(metric['source'])}。",
            f"责任人：{metric['owner']}；定义版本：{metric['version']}。",
            "",
        ]
    (ROOT / "docs/DATA_DICTIONARY.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    generate()
