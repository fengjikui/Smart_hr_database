# 数据与字段字典

由 `scripts/document_schema.py` 从实际建库结构和指标源生成。
日期为YYYY-MM-DD；业务按Asia/Shanghai。字段存在不等于开放查询权限。主键/空值以实际DDL约束为准。

## 业务库 `hr.sqlite`

### `dataset_meta`

数据集元信息；每个配置键一行

| 字段 | 类型 | 约束/关联 | 含义 |
|---|---|---|---|
| `key` | TEXT | PK(1) | 配置键 |
| `value` | TEXT | NOT NULL | 配置值 |

### `legal_entities`

法人主体；每个主体一行

| 字段 | 类型 | 约束/关联 | 含义 |
|---|---|---|---|
| `id` | INTEGER | PK(1) | 记录标识 |
| `name` | TEXT | NOT NULL | 业务名称 |

### `locations`

办公地点；每个地点一行

| 字段 | 类型 | 约束/关联 | 含义 |
|---|---|---|---|
| `id` | INTEGER | PK(1) | 记录标识 |
| `name` | TEXT | NOT NULL | 业务名称 |
| `timezone` | TEXT | NOT NULL | IANA时区 |

### `departments`

组织节点；四级树，每个组织一行

| 字段 | 类型 | 约束/关联 | 含义 |
|---|---|---|---|
| `id` | INTEGER | PK(1) | 记录标识 |
| `name` | TEXT | NOT NULL | 业务名称 |
| `parent_id` | INTEGER | → departments.id | 父组织；根节点为空 |
| `level` | INTEGER | NOT NULL | 公司1/事业部2/部门3/团队4 |
| `division_id` | INTEGER | → departments.id | 所属事业部标识 |

### `job_families`

岗位序列；每个序列一行

| 字段 | 类型 | 约束/关联 | 含义 |
|---|---|---|---|
| `id` | INTEGER | PK(1) | 记录标识 |
| `name` | TEXT | NOT NULL | 业务名称 |

### `grades`

职级及模拟薪资范围；每级一行

| 字段 | 类型 | 约束/关联 | 含义 |
|---|---|---|---|
| `id` | INTEGER | PK(1) | 记录标识 |
| `name` | TEXT | NOT NULL | 业务名称 |
| `salary_min` | INTEGER | NOT NULL | 模拟月薪下限，元 |
| `salary_max` | INTEGER | NOT NULL | 模拟月薪上限，元 |

### `positions`

岗位字典；每个岗位一行

| 字段 | 类型 | 约束/关联 | 含义 |
|---|---|---|---|
| `id` | INTEGER | PK(1) | 记录标识 |
| `name` | TEXT | NOT NULL | 业务名称 |
| `family_id` | INTEGER | NOT NULL, → job_families.id | 岗位序列标识 |
| `is_manager` | INTEGER | NOT NULL | 管理岗位标记0/1 |

### `employees`

人员基础档案；每名员工一行

| 字段 | 类型 | 约束/关联 | 含义 |
|---|---|---|---|
| `id` | INTEGER | PK(1) | 记录标识 |
| `employee_no` | TEXT | NOT NULL | 稳定工号（CC前缀） |
| `name` | TEXT | NOT NULL | 业务名称 |
| `gender` | TEXT | NOT NULL | 模拟性别，未开放查询条件 |
| `birth_date` | TEXT | NOT NULL | 模拟出生日期，未开放查询条件 |
| `hire_date` | TEXT | NOT NULL | 最近入职日期 |
| `termination_date` | TEXT | — | 离职日期；当日不计在职，空表示未离职 |
| `employment_type` | TEXT | NOT NULL | 正式/实习/外包 |
| `entity_id` | INTEGER | NOT NULL, → legal_entities.id | 法人主体标识 |
| `location_id` | INTEGER | NOT NULL, → locations.id | 地点标识 |
| `email` | TEXT | NOT NULL | 保留示例域名邮箱 |

### `employee_private`

私人信息；每名员工一行，全部SIM标记且不开放查询

| 字段 | 类型 | 约束/关联 | 含义 |
|---|---|---|---|
| `employee_id` | INTEGER | PK(1), → employees.id | 员工标识 |
| `phone` | TEXT | NOT NULL | SIM模拟电话标记 |
| `identity_document` | TEXT | NOT NULL | SIM模拟证件标记 |
| `bank_account` | TEXT | NOT NULL | SIM模拟银行账户标记 |

### `assignments`

任职历史；每个人每段连续任职一行，左闭右开

| 字段 | 类型 | 约束/关联 | 含义 |
|---|---|---|---|
| `id` | INTEGER | PK(1) | 记录标识 |
| `employee_id` | INTEGER | NOT NULL, → employees.id | 员工标识 |
| `department_id` | INTEGER | NOT NULL, → departments.id | 任职或需求所属组织 |
| `manager_id` | INTEGER | → employees.id | 直属上级员工标识 |
| `position_id` | INTEGER | NOT NULL, → positions.id | 岗位标识 |
| `grade_id` | INTEGER | NOT NULL, → grades.id | 职级标识 |
| `valid_from` | TEXT | NOT NULL | 生效日期，包含当天 |
| `valid_to` | TEXT | — | 结束日期，不包含当天；空表示当前 |

### `reporting_closure`

当前管理关系闭包；每个祖先/后代对一行

| 字段 | 类型 | 约束/关联 | 含义 |
|---|---|---|---|
| `ancestor_id` | INTEGER | PK(1), NOT NULL, → employees.id | 管理链祖先员工标识 |
| `descendant_id` | INTEGER | PK(2), NOT NULL, → employees.id | 管理链后代员工标识 |
| `depth` | INTEGER | NOT NULL | 0本人/1直属/2及以上间接 |

### `work_calendar`

演示工作日历；每天一行，未接正式节假日调休

| 字段 | 类型 | 约束/关联 | 含义 |
|---|---|---|---|
| `day` | TEXT | PK(1) | 业务日期YYYY-MM-DD |
| `is_workday` | INTEGER | NOT NULL | 应工作日标记0/1 |
| `note` | TEXT | NOT NULL | 备注与模拟日历说明 |

### `shift_policies`

班次政策；每个政策版本一行

| 字段 | 类型 | 约束/关联 | 含义 |
|---|---|---|---|
| `id` | INTEGER | PK(1) | 记录标识 |
| `name` | TEXT | NOT NULL | 业务名称 |
| `earliest_in` | INTEGER | NOT NULL | 弹性到岗起点；距午夜分钟 |
| `latest_in` | INTEGER | NOT NULL | 迟到阈值；距午夜分钟 |
| `earliest_out` | INTEGER | NOT NULL | 最早应离岗；距午夜分钟 |
| `required_work_minutes` | INTEGER | NOT NULL | 要求净工作分钟 |
| `lunch_minutes` | INTEGER | NOT NULL | 午休分钟 |
| `version` | TEXT | NOT NULL | 定义版本 |

### `attendance_daily`

每日考勤事实；每人每个应工作日一行

| 字段 | 类型 | 约束/关联 | 含义 |
|---|---|---|---|
| `id` | INTEGER | PK(1) | 记录标识 |
| `employee_id` | INTEGER | NOT NULL, → employees.id | 员工标识 |
| `day` | TEXT | NOT NULL, → work_calendar.day | 业务日期YYYY-MM-DD |
| `shift_id` | INTEGER | NOT NULL, → shift_policies.id | 班次政策标识 |
| `status` | TEXT | NOT NULL | 业务状态；取值由对应表约束与生成器定义 |
| `check_in` | INTEGER | — | 到岗时刻；距午夜分钟，缺卡可空 |
| `check_out` | INTEGER | — | 离岗时刻；距午夜分钟，缺卡可空 |
| `work_minutes` | INTEGER | NOT NULL | 扣除午休后的净在岗分钟 |
| `late_minutes` | INTEGER | NOT NULL | 超过09:30的分钟数 |
| `early_minutes` | INTEGER | NOT NULL | 早于个人应离岗的分钟数 |
| `late_departure_minutes` | INTEGER | NOT NULL | 超过个人应离岗的分钟数，不等于批准加班 |

### `leave_requests`

整日请假申请；每人每日最多一行

| 字段 | 类型 | 约束/关联 | 含义 |
|---|---|---|---|
| `id` | INTEGER | PK(1) | 记录标识 |
| `employee_id` | INTEGER | NOT NULL, → employees.id | 员工标识 |
| `day` | TEXT | NOT NULL | 业务日期YYYY-MM-DD |
| `leave_type` | TEXT | NOT NULL | 模拟假别 |
| `days` | REAL | NOT NULL | 请假天数；当前仅整日 |
| `approval_status` | TEXT | NOT NULL | 已批准/待审批/已拒绝 |
| `approver_id` | INTEGER | → employees.id | 审批人员工标识 |

### `overtime_requests`

加班申请；每人每日最多一行，与晚离岗分开

| 字段 | 类型 | 约束/关联 | 含义 |
|---|---|---|---|
| `id` | INTEGER | PK(1) | 记录标识 |
| `employee_id` | INTEGER | NOT NULL, → employees.id | 员工标识 |
| `day` | TEXT | NOT NULL | 业务日期YYYY-MM-DD |
| `minutes` | INTEGER | NOT NULL | 申请加班分钟 |
| `approval_status` | TEXT | NOT NULL | 已批准/待审批/已拒绝 |
| `approver_id` | INTEGER | → employees.id | 审批人员工标识 |

### `compensation`

基本月薪有效期记录；受限汇总来源

| 字段 | 类型 | 约束/关联 | 含义 |
|---|---|---|---|
| `id` | INTEGER | PK(1) | 记录标识 |
| `employee_id` | INTEGER | NOT NULL, → employees.id | 员工标识 |
| `valid_from` | TEXT | NOT NULL | 生效日期，包含当天 |
| `valid_to` | TEXT | — | 结束日期，不包含当天；空表示当前 |
| `monthly_base` | INTEGER | NOT NULL | 模拟基本月薪金额，元 |
| `currency` | TEXT | NOT NULL, 默认 'CNY' | 币种CNY |

### `performance_reviews`

绩效评价；每人每周期一行，尚未开放查询

| 字段 | 类型 | 约束/关联 | 含义 |
|---|---|---|---|
| `id` | INTEGER | PK(1) | 记录标识 |
| `employee_id` | INTEGER | NOT NULL, → employees.id | 员工标识 |
| `period` | TEXT | NOT NULL | 评价周期 |
| `rating` | TEXT | NOT NULL | 卓越/优秀/达标/待提升 |
| `reviewer_id` | INTEGER | → employees.id | 评价人员工标识 |

### `training_courses`

培训课程；每门课一行，尚未开放查询

| 字段 | 类型 | 约束/关联 | 含义 |
|---|---|---|---|
| `id` | INTEGER | PK(1) | 记录标识 |
| `name` | TEXT | NOT NULL | 业务名称 |
| `hours` | REAL | NOT NULL | 课程时长，小时 |

### `training_enrollments`

培训参加记录；每人每课程一行，尚未开放查询

| 字段 | 类型 | 约束/关联 | 含义 |
|---|---|---|---|
| `employee_id` | INTEGER | PK(1), NOT NULL, → employees.id | 员工标识 |
| `course_id` | INTEGER | PK(2), NOT NULL, → training_courses.id | 课程标识 |
| `status` | TEXT | NOT NULL | 业务状态；取值由对应表约束与生成器定义 |
| `completed_at` | TEXT | — | 完成日期，可空 |

### `recruitment_requisitions`

招聘需求；每个需求一行，尚未开放查询

| 字段 | 类型 | 约束/关联 | 含义 |
|---|---|---|---|
| `id` | INTEGER | PK(1) | 记录标识 |
| `department_id` | INTEGER | NOT NULL, → departments.id | 任职或需求所属组织 |
| `position_id` | INTEGER | NOT NULL, → positions.id | 岗位标识 |
| `openings` | INTEGER | NOT NULL | 招聘名额 |
| `status` | TEXT | NOT NULL | 业务状态；取值由对应表约束与生成器定义 |
| `opened_at` | TEXT | NOT NULL | 需求创建日期 |

## 应用库 `app.sqlite`

### `principals`

演示主体及授权；每个演示身份一行

| 字段 | 类型 | 约束/关联 | 含义 |
|---|---|---|---|
| `id` | TEXT | PK(1) | 记录标识 |
| `employee_id` | INTEGER | NOT NULL | 员工标识 |
| `role` | TEXT | NOT NULL | 角色类型 |
| `label` | TEXT | NOT NULL | 身份显示名称 |
| `title` | TEXT | NOT NULL | 显示标题 |
| `scope_mode` | TEXT | NOT NULL | reports/organization/self |
| `scope_root` | INTEGER | NOT NULL | 授权根：员工或组织ID，取决于scope_mode |
| `salary_aggregate` | INTEGER | NOT NULL | 薪酬受限聚合能力0/1 |
| `can_export` | INTEGER | NOT NULL | 导出能力0/1，仍受指标和范围限制 |
| `enabled` | INTEGER | NOT NULL, 默认 1 | 账号启用0/1 |
| `policy_version` | INTEGER | NOT NULL, 默认 1 | 权限策略版本 |

### `sessions`

会话；仅保存令牌摘要，不保存原令牌

| 字段 | 类型 | 约束/关联 | 含义 |
|---|---|---|---|
| `token_hash` | TEXT | PK(1) | 会话令牌SHA-256摘要 |
| `principal_id` | TEXT | NOT NULL, → principals.id | 应用身份标识 |
| `csrf` | TEXT | NOT NULL | 会话CSRF校验值 |
| `expires_at` | REAL | NOT NULL | 到期Unix时间戳秒 |

### `metrics`

已发布指标目录；每个指标一行JSON定义

| 字段 | 类型 | 约束/关联 | 含义 |
|---|---|---|---|
| `id` | TEXT | PK(1) | 记录标识 |
| `definition` | TEXT | NOT NULL | 指标JSON定义 |
| `version` | TEXT | NOT NULL | 定义版本 |

### `metric_search`

由指标目录派生的FTS5 trigram检索索引，可重建

| 字段 | 类型 | 约束/关联 | 含义 |
|---|---|---|---|
| `id` | FTS text | — | 记录标识 |
| `content` | FTS text | — | 派生检索文本 |

### `dashboards`

私人看板；存查询计划，不持久复制结果

| 字段 | 类型 | 约束/关联 | 含义 |
|---|---|---|---|
| `id` | TEXT | PK(1) | 记录标识 |
| `owner_id` | TEXT | NOT NULL, → principals.id | 看板所属身份 |
| `title` | TEXT | NOT NULL | 显示标题 |
| `plan` | TEXT | NOT NULL | 严格类型查询计划JSON |
| `catalog_version` | TEXT | NOT NULL | 指标目录版本 |
| `created_at` | TEXT | NOT NULL | 记录创建时间ISO格式 |

### `audit_events`

应用审计事件；不包含业务结果或个人证件

| 字段 | 类型 | 约束/关联 | 含义 |
|---|---|---|---|
| `id` | TEXT | PK(1) | 记录标识 |
| `principal_id` | TEXT | NOT NULL | 应用身份标识 |
| `action` | TEXT | NOT NULL | 操作名称 |
| `outcome` | TEXT | NOT NULL | 执行或授权结果 |
| `metric_id` | TEXT | — | 指标标识 |
| `scope_count` | INTEGER | — | 该次授权候选人数（不等于在职人数） |
| `policy_version` | TEXT | NOT NULL | 权限策略版本 |
| `duration_ms` | REAL | NOT NULL | 操作时长毫秒 |
| `created_at` | TEXT | NOT NULL | 记录创建时间ISO格式 |

### `conversations`

最小对话记录；用于同一身份的前次计划继承

| 字段 | 类型 | 约束/关联 | 含义 |
|---|---|---|---|
| `id` | TEXT | PK(1) | 记录标识 |
| `principal_id` | TEXT | NOT NULL | 应用身份标识 |
| `question` | TEXT | NOT NULL | 用户问题；生产需制定脱敏及留存策略 |
| `plan` | TEXT | — | 严格类型查询计划JSON |
| `outcome` | TEXT | NOT NULL | 执行或授权结果 |
| `created_at` | TEXT | NOT NULL | 记录创建时间ISO格式 |

## 指标目录

发布版本：`hr-metrics-1.0`。具体公式由 `backend/hr/query.py` 确定性实现，修改需同步定义与回归。

### 在职人数 `headcount`

在统计日已入职且尚未离职的去重员工数，包含正式、实习和外包。离职日不计在职。

单位：人；敏感等级：`internal`；最小组规模：1。
支持分组：division, department, job_family, location, employment_type, relation, month。来源：employees, assignments。
责任人：HR 数据负责人（模拟）；定义版本：1.0。

### 新入职人数 `hires`

入职日期落在选定期间的去重员工数，组织按入职时任职关系归属。

单位：人；敏感等级：`internal`；最小组规模：1。
支持分组：division, department, location, month。来源：employees, assignments。
责任人：HR 数据负责人（模拟）；定义版本：1.0。

### 离职人数 `departures`

离职日期落在选定期间的去重员工数，组织按离职日前一天归属。

单位：人；敏感等级：`internal`；最小组规模：1。
支持分组：division, department, month。来源：employees, assignments。
责任人：HR 数据负责人（模拟）；定义版本：1.0。

### 人员离职率 `turnover_rate`

期间离职人数 ÷ ((期初在职人数 + 期末在职人数) / 2) × 100。为演示统一口径，不进行年化。

单位：%；敏感等级：`internal`；最小组规模：1。
支持分组：division, department。来源：employees, assignments。
责任人：HR 数据负责人（模拟）；定义版本：1.0。

### 平均司龄 `avg_tenure`

统计日在职员工从最近入职日起至统计日的天数 / 365.25 的算术平均。

单位：年；敏感等级：`internal`；最小组规模：1。
支持分组：division, department, job_family。来源：employees, assignments。
责任人：HR 数据负责人（模拟）；定义版本：1.0。

### 出勤率 `attendance_rate`

正常或远程出勤人日 ÷ (应出勤人日 - 已批准整日请假人日) × 100。缺卡、缺勤不计完成出勤。

单位：%；敏感等级：`internal`；最小组规模：1。
支持分组：division, department, day, month。来源：attendance_daily, assignments。
责任人：HR 数据负责人（模拟）；定义版本：1.0。

### 迟到人次 `late_count`

工作日上班打卡晚于 09:30 的人日数。09:30 整不迟到。

单位：人次；敏感等级：`internal`；最小组规模：1。
支持分组：division, department, day, month。来源：attendance_daily, assignments。
责任人：HR 数据负责人（模拟）；定义版本：1.0。

### 迟到率 `late_rate`

迟到人次 ÷ 有上班打卡的应出勤人次 × 100。远程同样按弹性规则统计。

单位：%；敏感等级：`internal`；最小组规模：1。
支持分组：division, department, day, month。来源：attendance_daily, assignments。
责任人：HR 数据负责人（模拟）；定义版本：1.0。

### 考勤异常人次 `abnormal_count`

迟到、早退、缺勤或缺卡任一条件成立的人日数，同一人同一天只计一次。

单位：人次；敏感等级：`internal`；最小组规模：1。
支持分组：division, department, day, month。来源：attendance_daily, assignments。
责任人：HR 数据负责人（模拟）；定义版本：1.0。

### 已批准加班时长 `approved_overtime_hours`

选定期间已批准加班申请的分钟数之和 / 60。晚离岗不会自动认定为加班。

单位：小时；敏感等级：`internal`；最小组规模：1。
支持分组：division, department, day, month。来源：overtime_requests, assignments。
责任人：HR 数据负责人（模拟）；定义版本：1.0。

### 晚离岗时长 `late_departure_hours`

下班晚于个人应离岗时间的分钟数之和 / 60。应离岗时间为 max(18:00, 上班时间 + 9小时)，午休为1小时。该指标不是劳动报酬口径。

单位：小时；敏感等级：`internal`；最小组规模：1。
支持分组：division, department, day, month。来源：attendance_daily, assignments。
责任人：HR 数据负责人（模拟）；定义版本：1.0。

### 平均有效在岗时长 `avg_work_hours`

正常或远程且上下班打卡完整的净在岗分钟（打卡间隔减60分钟午休）÷ 完整打卡人日 ÷ 60。

单位：小时/人日；敏感等级：`internal`；最小组规模：1。
支持分组：division, department, day, month。来源：attendance_daily, assignments。
责任人：HR 数据负责人（模拟）；定义版本：1.0。

### 已批准请假天数 `leave_days`

选定期间已批准整日请假天数。演示不包含半天、跨时区与跨午夜班次。

单位：天；敏感等级：`internal`；最小组规模：1。
支持分组：division, department, day, month。来源：leave_requests, assignments。
责任人：HR 数据负责人（模拟）；定义版本：1.0。

### 平均基本月薪 `avg_salary`

统计日在职员工有效基本月薪的算术平均，仅CNY，不含奖金和补贴。仅公司负责人获准汇总，少于5人的分组不显示；不开放任意人员过滤。

单位：元/月；敏感等级：`restricted_aggregate`；最小组规模：5。
支持分组：division。来源：compensation, employees, assignments。
责任人：薪酬负责人（模拟）；定义版本：1.0。

