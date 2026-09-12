# 当前数据库、完整字段及指标口径

由 `uv run python scripts/document_schema.py` 从实际 SQLite 结构、指标目录和 SQL 编译器生成，与系统“数据库与口径”页共用同一数据源。

当前为 **24 张业务表、8 个应用逻辑表/全文索引、188 个字段、17 个指标**。字段数按各表列数相加，同名关联键分别计数。
全部为合成数据；字段存在不代表 Agent 已支持该字段。FTS5 自动影子表不计入逻辑表。表内不附人员、私人资料或会话实际值。

## 存储位置与职责

| 层 | 位置 | 职责 |
|---|---|---|
| 业务库 | `data/hr.sqlite` | 员工、教育经历、院校、任职、组织、考勤等24张关系表；查询服务只读。 |
| 应用库 | `data/app.sqlite` | 身份、会话、指标、看板、审计、对话与逐节点调试记录；与业务库分离。 |
| 指标定义源 | `semantic/catalog.json` | Git版本化的名称、定义、来源、维度、责任人与敏感级别；发布到应用库metrics。 |
| 检索索引 | `app.sqlite.metric_search` | FTS5 trigram派生全文索引，用于指标搜索；当前问数直接注入全量已授权指标，没有向量检索。 |
| 公式实现 | `backend/hr/query.py` | 确定性SQL编译器实现口径和权限；下面的公式与示例SQL从实际编译结果提取。 |

## 数据集元信息

```json
{
  "as_of": "2026-09-11",
  "seed": "20260911",
  "size": "480",
  "calendar_start": "2026-01-01",
  "synthetic": "true",
  "calendar_policy": "演示日历：周一至周五为工作日，不套用法定节假日",
  "catalog_version": "hr-metrics-1.1",
  "data_version": "hr-data-2"
}
```

## 所有表与字段总览

| 库 / 表 | 用途与粒度 | 全部字段 |
|---|---|---|
| business / `dataset_meta` | 数据集元信息；每个配置键一行 | `key`, `value` |
| business / `legal_entities` | 法人主体；每个主体一行 | `id`, `name` |
| business / `locations` | 办公地点；每个地点一行 | `id`, `name`, `timezone` |
| business / `departments` | 组织节点；四级树，每个组织一行 | `id`, `name`, `parent_id`, `level`, `division_id` |
| business / `job_families` | 岗位序列；每个序列一行 | `id`, `name` |
| business / `grades` | 职级及模拟薪资范围；每级一行 | `id`, `name`, `salary_min`, `salary_max` |
| business / `positions` | 岗位字典；每个岗位一行 | `id`, `name`, `family_id`, `is_manager` |
| business / `schools` | 院校名称、别名与历史211/985标签；每校一行，不含员工数据 | `id`, `name`, `aliases`, `is_985`, `is_211`, `classification_basis`, `source_url` |
| business / `employees` | 人员基础档案；每名员工一行 | `id`, `employee_no`, `name`, `gender`, `birth_date`, `hire_date`, `termination_date`, `employment_type`, `entity_id`, `location_id`, `email`, `highest_education`, `highest_degree`, `graduation_school_id`, `major`, `graduation_date`, `education_mode` |
| business / `employee_education` | 已完成教育经历；每人每段经历一行，历史分析按事件日取已完成最高学历 | `id`, `employee_id`, `school_id`, `education_level`, `education_rank`, `degree`, `major`, `start_date`, `graduation_date`, `study_mode` |
| business / `employee_private` | 私人信息；每名员工一行，全部SIM标记且不开放查询 | `employee_id`, `phone`, `identity_document`, `bank_account` |
| business / `assignments` | 任职历史；每个人每段连续任职一行，左闭右开 | `id`, `employee_id`, `department_id`, `manager_id`, `position_id`, `grade_id`, `valid_from`, `valid_to` |
| business / `reporting_closure` | 当前管理关系闭包；每个祖先/后代对一行 | `ancestor_id`, `descendant_id`, `depth` |
| business / `work_calendar` | 演示工作日历；每天一行，未接正式节假日调休 | `day`, `is_workday`, `note` |
| business / `shift_policies` | 班次政策；每个政策版本一行 | `id`, `name`, `earliest_in`, `latest_in`, `earliest_out`, `required_work_minutes`, `lunch_minutes`, `version` |
| business / `attendance_daily` | 每日考勤事实；每人每个应工作日一行 | `id`, `employee_id`, `day`, `shift_id`, `status`, `check_in`, `check_out`, `work_minutes`, `late_minutes`, `early_minutes`, `late_departure_minutes` |
| business / `leave_requests` | 整日请假申请；每人每日最多一行 | `id`, `employee_id`, `day`, `leave_type`, `days`, `approval_status`, `approver_id` |
| business / `overtime_requests` | 加班申请；每人每日最多一行，与晚离岗分开 | `id`, `employee_id`, `day`, `minutes`, `day_type`, `approval_status`, `approver_id` |
| business / `compensation` | 基本月薪有效期记录；受限汇总来源 | `id`, `employee_id`, `valid_from`, `valid_to`, `monthly_base`, `currency` |
| business / `performance_reviews` | 绩效评价；每人每周期一行，尚未开放查询 | `id`, `employee_id`, `period`, `rating`, `reviewer_id` |
| business / `training_courses` | 培训课程；每门课一行，尚未开放查询 | `id`, `name`, `hours` |
| business / `training_enrollments` | 培训参加记录；每人每课程一行，尚未开放查询 | `employee_id`, `course_id`, `status`, `completed_at` |
| business / `recruitment_requisitions` | 招聘需求；每个需求一行，尚未开放查询 | `id`, `department_id`, `position_id`, `openings`, `status`, `opened_at` |
| business / `overtime_attendance` | 独立周末打卡事实；每人每周末出勤日一行，核验申请时长 | `id`, `employee_id`, `day`, `check_in`, `check_out`, `break_minutes`, `work_minutes` |
| application / `principals` | 演示主体及授权；每个演示身份一行 | `id`, `employee_id`, `role`, `label`, `title`, `scope_mode`, `scope_root`, `salary_aggregate`, `can_export`, `enabled`, `policy_version` |
| application / `sessions` | 会话；仅保存令牌摘要，不保存原令牌 | `token_hash`, `principal_id`, `csrf`, `expires_at` |
| application / `metrics` | 已发布指标目录；每个指标一行JSON定义 | `id`, `definition`, `version` |
| application / `metric_search` | 由指标目录派生的FTS5 trigram检索索引，可重建 | `id`, `content` |
| application / `dashboards` | 私人看板；存查询计划，不持久复制结果 | `id`, `owner_id`, `title`, `plan`, `catalog_version`, `created_at` |
| application / `audit_events` | 应用审计事件；不包含业务结果或个人证件 | `id`, `principal_id`, `action`, `outcome`, `metric_id`, `scope_count`, `policy_version`, `duration_ms`, `created_at` |
| application / `conversations` | 最小对话记录；用于同一身份的前次计划继承 | `id`, `principal_id`, `question`, `plan`, `outcome`, `created_at` |
| application / `debug_runs` | 逐节点调试记录；每次自然语言查询一行，按身份与授权快照隔离，最多保留50次 | `id`, `owner_id`, `grant_fingerprint`, `question`, `status`, `started_at`, `finished_at`, `duration_ms`, `payload` |

## 字段、键、索引与实际建表约束

日期为 YYYY-MM-DD，打卡为距午夜的分钟数。PK 后数字为复合主键内位置；NOT NULL 列是 PRAGMA 的实际声明，SQLite 主键语义另见原始 DDL。完整 CHECK、UNIQUE、外键与部分索引条件保留在 SQL 中。

### `dataset_meta`

数据集元信息；每个配置键一行。数据库：business。

当前合成行数：8。

| 字段 | 类型 | 声明约束 / 关联 | 含义 |
|---|---|---|---|
| `key` | TEXT | PK(1) | 配置键 |
| `value` | TEXT | NOT NULL | 配置值 |

```sql
CREATE TABLE dataset_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
```

| 索引 | 列 | 唯一 | 部分索引 | 来源 |
|---|---|---|---|---|
| `sqlite_autoindex_dataset_meta_1` | key | True | False | pk |

### `legal_entities`

法人主体；每个主体一行。数据库：business。

当前合成行数：2。

| 字段 | 类型 | 声明约束 / 关联 | 含义 |
|---|---|---|---|
| `id` | INTEGER | PK(1) | 记录标识 |
| `name` | TEXT | NOT NULL | 业务名称 |

```sql
CREATE TABLE legal_entities (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
```

### `locations`

办公地点；每个地点一行。数据库：business。

当前合成行数：3。

| 字段 | 类型 | 声明约束 / 关联 | 含义 |
|---|---|---|---|
| `id` | INTEGER | PK(1) | 记录标识 |
| `name` | TEXT | NOT NULL | 业务名称 |
| `timezone` | TEXT | NOT NULL | IANA时区 |

```sql
CREATE TABLE locations (id INTEGER PRIMARY KEY, name TEXT NOT NULL, timezone TEXT NOT NULL);
```

### `departments`

组织节点；四级树，每个组织一行。数据库：business。

当前合成行数：51。

| 字段 | 类型 | 声明约束 / 关联 | 含义 |
|---|---|---|---|
| `id` | INTEGER | PK(1) | 记录标识 |
| `name` | TEXT | NOT NULL | 业务名称 |
| `parent_id` | INTEGER | → departments.id | 父组织；根节点为空 |
| `level` | INTEGER | NOT NULL | 公司1/事业部2/部门3/团队4 |
| `division_id` | INTEGER | → departments.id | 所属事业部标识 |

```sql
CREATE TABLE departments (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, parent_id INTEGER REFERENCES departments(id), level INTEGER NOT NULL CHECK(level BETWEEN 1 AND 4), division_id INTEGER REFERENCES departments(id));
```

| 索引 | 列 | 唯一 | 部分索引 | 来源 |
|---|---|---|---|---|
| `sqlite_autoindex_departments_1` | name | True | False | u |

### `job_families`

岗位序列；每个序列一行。数据库：business。

当前合成行数：7。

| 字段 | 类型 | 声明约束 / 关联 | 含义 |
|---|---|---|---|
| `id` | INTEGER | PK(1) | 记录标识 |
| `name` | TEXT | NOT NULL | 业务名称 |

```sql
CREATE TABLE job_families (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
```

| 索引 | 列 | 唯一 | 部分索引 | 来源 |
|---|---|---|---|---|
| `sqlite_autoindex_job_families_1` | name | True | False | u |

### `grades`

职级及模拟薪资范围；每级一行。数据库：business。

当前合成行数：9。

| 字段 | 类型 | 声明约束 / 关联 | 含义 |
|---|---|---|---|
| `id` | INTEGER | PK(1) | 记录标识 |
| `name` | TEXT | NOT NULL | 业务名称 |
| `salary_min` | INTEGER | NOT NULL | 模拟月薪下限，元 |
| `salary_max` | INTEGER | NOT NULL | 模拟月薪上限，元 |

```sql
CREATE TABLE grades (id INTEGER PRIMARY KEY, name TEXT NOT NULL, salary_min INTEGER NOT NULL, salary_max INTEGER NOT NULL CHECK(salary_max>=salary_min));
```

### `positions`

岗位字典；每个岗位一行。数据库：business。

当前合成行数：10。

| 字段 | 类型 | 声明约束 / 关联 | 含义 |
|---|---|---|---|
| `id` | INTEGER | PK(1) | 记录标识 |
| `name` | TEXT | NOT NULL | 业务名称 |
| `family_id` | INTEGER | NOT NULL; → job_families.id | 岗位序列标识 |
| `is_manager` | INTEGER | NOT NULL | 管理岗位标记0/1 |

```sql
CREATE TABLE positions (id INTEGER PRIMARY KEY, name TEXT NOT NULL, family_id INTEGER NOT NULL REFERENCES job_families(id), is_manager INTEGER NOT NULL CHECK(is_manager IN (0,1)));
```

### `schools`

院校名称、别名与历史211/985标签；每校一行，不含员工数据。数据库：business。

当前合成行数：11。

| 字段 | 类型 | 声明约束 / 关联 | 含义 |
|---|---|---|---|
| `id` | INTEGER | PK(1) | 记录标识 |
| `name` | TEXT | NOT NULL | 业务名称 |
| `aliases` | TEXT | NOT NULL | 院校简称JSON数组，精确归一到院校ID |
| `is_985` | INTEGER | NOT NULL | 历史985项目院校标签0/1；为1时is_211必须为1 |
| `is_211` | INTEGER | NOT NULL | 历史211项目院校标签0/1，包含985院校 |
| `classification_basis` | TEXT | NOT NULL | 标签分类依据；真实院校历史名单或虚构标记，不等于双一流 |
| `source_url` | TEXT | NOT NULL | 教育部项目名单链接；虚构学校为synthetic标记 |

```sql
CREATE TABLE schools (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, aliases TEXT NOT NULL, is_985 INTEGER NOT NULL CHECK(is_985 IN (0,1)), is_211 INTEGER NOT NULL CHECK(is_211 IN (0,1)), classification_basis TEXT NOT NULL, source_url TEXT NOT NULL, CHECK(is_985<=is_211));
```

| 索引 | 列 | 唯一 | 部分索引 | 来源 |
|---|---|---|---|---|
| `sqlite_autoindex_schools_1` | name | True | False | u |

### `employees`

人员基础档案；每名员工一行。数据库：business。

当前合成行数：480。

| 字段 | 类型 | 声明约束 / 关联 | 含义 |
|---|---|---|---|
| `id` | INTEGER | PK(1) | 记录标识 |
| `employee_no` | TEXT | NOT NULL | 稳定工号（CC前缀） |
| `name` | TEXT | NOT NULL | 业务名称 |
| `gender` | TEXT | NOT NULL | 模拟性别，未开放查询条件 |
| `birth_date` | TEXT | NOT NULL | 模拟出生日期，未开放查询条件 |
| `hire_date` | TEXT | NOT NULL | 最近入职日期 |
| `termination_date` | TEXT | — | 离职日期；当日不计在职，空表示未离职 |
| `employment_type` | TEXT | NOT NULL | 正式/实习/外包 |
| `entity_id` | INTEGER | NOT NULL; → legal_entities.id | 法人主体标识 |
| `location_id` | INTEGER | NOT NULL; → locations.id | 地点标识 |
| `email` | TEXT | NOT NULL | 保留示例域名邮箱 |
| `highest_education` | TEXT | NOT NULL; DEFAULT '未知' | 当前最高已完成学历快照；未知/高中及以下/专科/本科/硕士研究生/博士研究生 |
| `highest_degree` | TEXT | NOT NULL; DEFAULT '未知' | 当前最高已完成教育经历对应学位快照；未知/无学位/学士/硕士/博士 |
| `graduation_school_id` | INTEGER | → schools.id | 当前最高已完成教育经历毕业院校标识 |
| `major` | TEXT | — | 所学专业；演示未开放按专业筛选 |
| `graduation_date` | TEXT | — | 毕业日期；只有不晚于统计日的已完成经历参与查询 |
| `education_mode` | TEXT | NOT NULL; DEFAULT '未知' | 当前最高教育经历学习形式快照；未知/全日制/非全日制 |

```sql
CREATE TABLE employees (id INTEGER PRIMARY KEY, employee_no TEXT NOT NULL UNIQUE, name TEXT NOT NULL, gender TEXT NOT NULL CHECK(gender IN ('女','男')), birth_date TEXT NOT NULL, hire_date TEXT NOT NULL, termination_date TEXT, employment_type TEXT NOT NULL CHECK(employment_type IN ('正式','实习','外包')), entity_id INTEGER NOT NULL REFERENCES legal_entities(id), location_id INTEGER NOT NULL REFERENCES locations(id), email TEXT NOT NULL UNIQUE, highest_education TEXT NOT NULL DEFAULT '未知' CHECK(highest_education IN ('未知','高中及以下','专科','本科','硕士研究生','博士研究生')), highest_degree TEXT NOT NULL DEFAULT '未知' CHECK(highest_degree IN ('未知','无学位','学士','硕士','博士')), graduation_school_id INTEGER REFERENCES schools(id), major TEXT, graduation_date TEXT, education_mode TEXT NOT NULL DEFAULT '未知' CHECK(education_mode IN ('未知','全日制','非全日制')), CHECK(termination_date IS NULL OR termination_date>=hire_date));
```

| 索引 | 列 | 唯一 | 部分索引 | 来源 |
|---|---|---|---|---|
| `sqlite_autoindex_employees_2` | email | True | False | u |
| `sqlite_autoindex_employees_1` | employee_no | True | False | u |

### `employee_education`

已完成教育经历；每人每段经历一行，历史分析按事件日取已完成最高学历。数据库：business。

当前合成行数：619。

| 字段 | 类型 | 声明约束 / 关联 | 含义 |
|---|---|---|---|
| `id` | INTEGER | PK(1) | 记录标识 |
| `employee_id` | INTEGER | NOT NULL; → employees.id | 员工标识 |
| `school_id` | INTEGER | NOT NULL; → schools.id | 该段教育经历的毕业院校标识 |
| `education_level` | TEXT | NOT NULL | 学历层级名称，与education_rank对应 |
| `education_rank` | INTEGER | NOT NULL | 学历排序：高中及以下1/专科2/本科3/硕士研究生4/博士研究生5 |
| `degree` | TEXT | NOT NULL | 已取得学位：无学位/学士/硕士/博士；不同于学历 |
| `major` | TEXT | NOT NULL | 所学专业；演示未开放按专业筛选 |
| `start_date` | TEXT | NOT NULL | 教育经历开始日期 |
| `graduation_date` | TEXT | NOT NULL | 毕业日期；只有不晚于统计日的已完成经历参与查询 |
| `study_mode` | TEXT | NOT NULL | 该段教育经历学习形式：全日制/非全日制 |

```sql
CREATE TABLE employee_education (id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL REFERENCES employees(id), school_id INTEGER NOT NULL REFERENCES schools(id), education_level TEXT NOT NULL, education_rank INTEGER NOT NULL CHECK(education_rank BETWEEN 1 AND 5), degree TEXT NOT NULL CHECK(degree IN ('无学位','学士','硕士','博士')), major TEXT NOT NULL, start_date TEXT NOT NULL, graduation_date TEXT NOT NULL, study_mode TEXT NOT NULL CHECK(study_mode IN ('全日制','非全日制')), CHECK(start_date<graduation_date), UNIQUE(employee_id,education_rank,graduation_date));
```

| 索引 | 列 | 唯一 | 部分索引 | 来源 |
|---|---|---|---|---|
| `idx_education_school` | school_id, employee_id | False | False | c |
| `idx_education_employee_date` | employee_id, graduation_date, education_rank | False | False | c |
| `sqlite_autoindex_employee_education_1` | employee_id, education_rank, graduation_date | True | False | u |

```sql
CREATE INDEX idx_education_school ON employee_education(school_id,employee_id);
CREATE INDEX idx_education_employee_date ON employee_education(employee_id,graduation_date,education_rank);
```

### `employee_private`

私人信息；每名员工一行，全部SIM标记且不开放查询。数据库：business。

当前合成行数：480。

| 字段 | 类型 | 声明约束 / 关联 | 含义 |
|---|---|---|---|
| `employee_id` | INTEGER | PK(1); → employees.id | 员工标识 |
| `phone` | TEXT | NOT NULL | SIM模拟电话标记 |
| `identity_document` | TEXT | NOT NULL | SIM模拟证件标记 |
| `bank_account` | TEXT | NOT NULL | SIM模拟银行账户标记 |

```sql
CREATE TABLE employee_private (employee_id INTEGER PRIMARY KEY REFERENCES employees(id), phone TEXT NOT NULL, identity_document TEXT NOT NULL, bank_account TEXT NOT NULL);
```

### `assignments`

任职历史；每个人每段连续任职一行，左闭右开。数据库：business。

当前合成行数：511。

| 字段 | 类型 | 声明约束 / 关联 | 含义 |
|---|---|---|---|
| `id` | INTEGER | PK(1) | 记录标识 |
| `employee_id` | INTEGER | NOT NULL; → employees.id | 员工标识 |
| `department_id` | INTEGER | NOT NULL; → departments.id | 任职或需求所属组织 |
| `manager_id` | INTEGER | → employees.id | 直属上级员工标识 |
| `position_id` | INTEGER | NOT NULL; → positions.id | 岗位标识 |
| `grade_id` | INTEGER | NOT NULL; → grades.id | 职级标识 |
| `valid_from` | TEXT | NOT NULL | 生效日期，包含当天 |
| `valid_to` | TEXT | — | 结束日期，不包含当天；空表示当前 |

```sql
CREATE TABLE assignments (id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL REFERENCES employees(id), department_id INTEGER NOT NULL REFERENCES departments(id), manager_id INTEGER REFERENCES employees(id), position_id INTEGER NOT NULL REFERENCES positions(id), grade_id INTEGER NOT NULL REFERENCES grades(id), valid_from TEXT NOT NULL, valid_to TEXT, CHECK(manager_id IS NULL OR manager_id<>employee_id), CHECK(valid_to IS NULL OR valid_to>valid_from), UNIQUE(employee_id,valid_from));
```

| 索引 | 列 | 唯一 | 部分索引 | 来源 |
|---|---|---|---|---|
| `idx_assignment_dept` | department_id, valid_from | False | False | c |
| `idx_assignment_asof` | employee_id, valid_from, valid_to | False | False | c |
| `uq_current_assignment` | employee_id | True | True | c |
| `sqlite_autoindex_assignments_1` | employee_id, valid_from | True | False | u |

```sql
CREATE INDEX idx_assignment_dept ON assignments(department_id,valid_from);
CREATE INDEX idx_assignment_asof ON assignments(employee_id,valid_from,valid_to);
CREATE UNIQUE INDEX uq_current_assignment ON assignments(employee_id) WHERE valid_to IS NULL;
```

### `reporting_closure`

当前管理关系闭包；每个祖先/后代对一行。数据库：business。

当前合成行数：2,321。

| 字段 | 类型 | 声明约束 / 关联 | 含义 |
|---|---|---|---|
| `ancestor_id` | INTEGER | PK(1); NOT NULL; → employees.id | 管理链祖先员工标识 |
| `descendant_id` | INTEGER | PK(2); NOT NULL; → employees.id | 管理链后代员工标识 |
| `depth` | INTEGER | NOT NULL | 0本人/1直属/2及以上间接 |

```sql
CREATE TABLE reporting_closure (ancestor_id INTEGER NOT NULL REFERENCES employees(id), descendant_id INTEGER NOT NULL REFERENCES employees(id), depth INTEGER NOT NULL CHECK(depth>=0), PRIMARY KEY(ancestor_id,descendant_id));
```

| 索引 | 列 | 唯一 | 部分索引 | 来源 |
|---|---|---|---|---|
| `idx_closure_desc` | descendant_id | False | False | c |
| `sqlite_autoindex_reporting_closure_1` | ancestor_id, descendant_id | True | False | pk |

```sql
CREATE INDEX idx_closure_desc ON reporting_closure(descendant_id);
```

### `work_calendar`

演示工作日历；每天一行，未接正式节假日调休。数据库：business。

当前合成行数：254。

| 字段 | 类型 | 声明约束 / 关联 | 含义 |
|---|---|---|---|
| `day` | TEXT | PK(1) | 业务日期YYYY-MM-DD |
| `is_workday` | INTEGER | NOT NULL | 应工作日标记0/1 |
| `note` | TEXT | NOT NULL | 备注与模拟日历说明 |

```sql
CREATE TABLE work_calendar (day TEXT PRIMARY KEY, is_workday INTEGER NOT NULL CHECK(is_workday IN (0,1)), note TEXT NOT NULL);
```

| 索引 | 列 | 唯一 | 部分索引 | 来源 |
|---|---|---|---|---|
| `sqlite_autoindex_work_calendar_1` | day | True | False | pk |

### `shift_policies`

班次政策；每个政策版本一行。数据库：business。

当前合成行数：1。

| 字段 | 类型 | 声明约束 / 关联 | 含义 |
|---|---|---|---|
| `id` | INTEGER | PK(1) | 记录标识 |
| `name` | TEXT | NOT NULL | 业务名称 |
| `earliest_in` | INTEGER | NOT NULL | 弹性到岗起点；距午夜分钟 |
| `latest_in` | INTEGER | NOT NULL | 迟到阈值；距午夜分钟 |
| `earliest_out` | INTEGER | NOT NULL | 最早应离岗；距午夜分钟 |
| `required_work_minutes` | INTEGER | NOT NULL | 要求净工作分钟 |
| `lunch_minutes` | INTEGER | NOT NULL | 午休分钟 |
| `version` | TEXT | NOT NULL | 定义版本 |

```sql
CREATE TABLE shift_policies (id INTEGER PRIMARY KEY, name TEXT NOT NULL, earliest_in INTEGER NOT NULL, latest_in INTEGER NOT NULL, earliest_out INTEGER NOT NULL, required_work_minutes INTEGER NOT NULL, lunch_minutes INTEGER NOT NULL, version TEXT NOT NULL);
```

### `attendance_daily`

每日考勤事实；每人每个应工作日一行。数据库：business。

当前合成行数：79,735。

| 字段 | 类型 | 声明约束 / 关联 | 含义 |
|---|---|---|---|
| `id` | INTEGER | PK(1) | 记录标识 |
| `employee_id` | INTEGER | NOT NULL; → employees.id | 员工标识 |
| `day` | TEXT | NOT NULL; → work_calendar.day | 业务日期YYYY-MM-DD |
| `shift_id` | INTEGER | NOT NULL; → shift_policies.id | 班次政策标识 |
| `status` | TEXT | NOT NULL | 业务状态；取值由对应表约束与生成器定义 |
| `check_in` | INTEGER | — | 到岗时刻；距午夜分钟，缺卡可空 |
| `check_out` | INTEGER | — | 离岗时刻；距午夜分钟，缺卡可空 |
| `work_minutes` | INTEGER | NOT NULL | 扣除午休后的净在岗分钟 |
| `late_minutes` | INTEGER | NOT NULL | 超过09:30的分钟数 |
| `early_minutes` | INTEGER | NOT NULL | 早于个人应离岗的分钟数 |
| `late_departure_minutes` | INTEGER | NOT NULL | 超过个人应离岗的分钟数，不等于批准加班 |

```sql
CREATE TABLE attendance_daily (id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL REFERENCES employees(id), day TEXT NOT NULL REFERENCES work_calendar(day), shift_id INTEGER NOT NULL REFERENCES shift_policies(id), status TEXT NOT NULL CHECK(status IN ('正常','远程','请假','缺勤','缺卡')), check_in INTEGER, check_out INTEGER, work_minutes INTEGER NOT NULL CHECK(work_minutes>=0), late_minutes INTEGER NOT NULL CHECK(late_minutes>=0), early_minutes INTEGER NOT NULL CHECK(early_minutes>=0), late_departure_minutes INTEGER NOT NULL CHECK(late_departure_minutes>=0), UNIQUE(employee_id,day), CHECK(check_in IS NULL OR check_out IS NULL OR check_out>=check_in));
```

| 索引 | 列 | 唯一 | 部分索引 | 来源 |
|---|---|---|---|---|
| `idx_attendance_day_employee` | day, employee_id | False | False | c |
| `sqlite_autoindex_attendance_daily_1` | employee_id, day | True | False | u |

```sql
CREATE INDEX idx_attendance_day_employee ON attendance_daily(day,employee_id);
```

### `leave_requests`

整日请假申请；每人每日最多一行。数据库：business。

当前合成行数：2,793。

| 字段 | 类型 | 声明约束 / 关联 | 含义 |
|---|---|---|---|
| `id` | INTEGER | PK(1) | 记录标识 |
| `employee_id` | INTEGER | NOT NULL; → employees.id | 员工标识 |
| `day` | TEXT | NOT NULL | 业务日期YYYY-MM-DD |
| `leave_type` | TEXT | NOT NULL | 模拟假别 |
| `days` | REAL | NOT NULL | 请假天数；当前仅整日 |
| `approval_status` | TEXT | NOT NULL | 已批准/待审批/已拒绝 |
| `approver_id` | INTEGER | → employees.id | 审批人员工标识 |

```sql
CREATE TABLE leave_requests (id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL REFERENCES employees(id), day TEXT NOT NULL, leave_type TEXT NOT NULL, days REAL NOT NULL CHECK(days>0 AND days<=1), approval_status TEXT NOT NULL CHECK(approval_status IN ('已批准','待审批','已拒绝')), approver_id INTEGER REFERENCES employees(id), UNIQUE(employee_id,day));
```

| 索引 | 列 | 唯一 | 部分索引 | 来源 |
|---|---|---|---|---|
| `sqlite_autoindex_leave_requests_1` | employee_id, day | True | False | u |

### `overtime_requests`

加班申请；每人每日最多一行，与晚离岗分开。数据库：business。

当前合成行数：12,042。

| 字段 | 类型 | 声明约束 / 关联 | 含义 |
|---|---|---|---|
| `id` | INTEGER | PK(1) | 记录标识 |
| `employee_id` | INTEGER | NOT NULL; → employees.id | 员工标识 |
| `day` | TEXT | NOT NULL | 业务日期YYYY-MM-DD |
| `minutes` | INTEGER | NOT NULL | 申请加班分钟 |
| `day_type` | TEXT | NOT NULL; DEFAULT '工作日' | 加班日期类型：工作日/周末；与演示日历一致 |
| `approval_status` | TEXT | NOT NULL | 已批准/待审批/已拒绝 |
| `approver_id` | INTEGER | → employees.id | 审批人员工标识 |

```sql
CREATE TABLE overtime_requests (id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL REFERENCES employees(id), day TEXT NOT NULL, minutes INTEGER NOT NULL CHECK(minutes>0), day_type TEXT NOT NULL DEFAULT '工作日' CHECK(day_type IN ('工作日','周末')), approval_status TEXT NOT NULL CHECK(approval_status IN ('已批准','待审批','已拒绝')), approver_id INTEGER REFERENCES employees(id), UNIQUE(employee_id,day));
```

| 索引 | 列 | 唯一 | 部分索引 | 来源 |
|---|---|---|---|---|
| `idx_overtime_day_type` | day_type, day, employee_id | False | False | c |
| `sqlite_autoindex_overtime_requests_1` | employee_id, day | True | False | u |

```sql
CREATE INDEX idx_overtime_day_type ON overtime_requests(day_type,day,employee_id);
```

### `compensation`

基本月薪有效期记录；受限汇总来源。数据库：business。

当前合成行数：480。

| 字段 | 类型 | 声明约束 / 关联 | 含义 |
|---|---|---|---|
| `id` | INTEGER | PK(1) | 记录标识 |
| `employee_id` | INTEGER | NOT NULL; → employees.id | 员工标识 |
| `valid_from` | TEXT | NOT NULL | 生效日期，包含当天 |
| `valid_to` | TEXT | — | 结束日期，不包含当天；空表示当前 |
| `monthly_base` | INTEGER | NOT NULL | 模拟基本月薪金额，元 |
| `currency` | TEXT | NOT NULL; DEFAULT 'CNY' | 币种CNY |

```sql
CREATE TABLE compensation (id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL REFERENCES employees(id), valid_from TEXT NOT NULL, valid_to TEXT, monthly_base INTEGER NOT NULL CHECK(monthly_base>=0), currency TEXT NOT NULL DEFAULT 'CNY', UNIQUE(employee_id,valid_from));
```

| 索引 | 列 | 唯一 | 部分索引 | 来源 |
|---|---|---|---|---|
| `sqlite_autoindex_compensation_1` | employee_id, valid_from | True | False | u |

### `performance_reviews`

绩效评价；每人每周期一行，尚未开放查询。数据库：business。

当前合成行数：459。

| 字段 | 类型 | 声明约束 / 关联 | 含义 |
|---|---|---|---|
| `id` | INTEGER | PK(1) | 记录标识 |
| `employee_id` | INTEGER | NOT NULL; → employees.id | 员工标识 |
| `period` | TEXT | NOT NULL | 评价周期 |
| `rating` | TEXT | NOT NULL | 卓越/优秀/达标/待提升 |
| `reviewer_id` | INTEGER | → employees.id | 评价人员工标识 |

```sql
CREATE TABLE performance_reviews (id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL REFERENCES employees(id), period TEXT NOT NULL, rating TEXT NOT NULL CHECK(rating IN ('卓越','优秀','达标','待提升')), reviewer_id INTEGER REFERENCES employees(id), UNIQUE(employee_id,period));
```

| 索引 | 列 | 唯一 | 部分索引 | 来源 |
|---|---|---|---|---|
| `sqlite_autoindex_performance_reviews_1` | employee_id, period | True | False | u |

### `training_courses`

培训课程；每门课一行，尚未开放查询。数据库：business。

当前合成行数：3。

| 字段 | 类型 | 声明约束 / 关联 | 含义 |
|---|---|---|---|
| `id` | INTEGER | PK(1) | 记录标识 |
| `name` | TEXT | NOT NULL | 业务名称 |
| `hours` | REAL | NOT NULL | 课程时长，小时 |

```sql
CREATE TABLE training_courses (id INTEGER PRIMARY KEY, name TEXT NOT NULL, hours REAL NOT NULL);
```

### `training_enrollments`

培训参加记录；每人每课程一行，尚未开放查询。数据库：business。

当前合成行数：960。

| 字段 | 类型 | 声明约束 / 关联 | 含义 |
|---|---|---|---|
| `employee_id` | INTEGER | PK(1); NOT NULL; → employees.id | 员工标识 |
| `course_id` | INTEGER | PK(2); NOT NULL; → training_courses.id | 课程标识 |
| `status` | TEXT | NOT NULL | 业务状态；取值由对应表约束与生成器定义 |
| `completed_at` | TEXT | — | 完成日期，可空 |

```sql
CREATE TABLE training_enrollments (employee_id INTEGER NOT NULL REFERENCES employees(id), course_id INTEGER NOT NULL REFERENCES training_courses(id), status TEXT NOT NULL, completed_at TEXT, PRIMARY KEY(employee_id,course_id));
```

| 索引 | 列 | 唯一 | 部分索引 | 来源 |
|---|---|---|---|---|
| `sqlite_autoindex_training_enrollments_1` | employee_id, course_id | True | False | pk |

### `recruitment_requisitions`

招聘需求；每个需求一行，尚未开放查询。数据库：business。

当前合成行数：15。

| 字段 | 类型 | 声明约束 / 关联 | 含义 |
|---|---|---|---|
| `id` | INTEGER | PK(1) | 记录标识 |
| `department_id` | INTEGER | NOT NULL; → departments.id | 任职或需求所属组织 |
| `position_id` | INTEGER | NOT NULL; → positions.id | 岗位标识 |
| `openings` | INTEGER | NOT NULL | 招聘名额 |
| `status` | TEXT | NOT NULL | 业务状态；取值由对应表约束与生成器定义 |
| `opened_at` | TEXT | NOT NULL | 需求创建日期 |

```sql
CREATE TABLE recruitment_requisitions (id INTEGER PRIMARY KEY, department_id INTEGER NOT NULL REFERENCES departments(id), position_id INTEGER NOT NULL REFERENCES positions(id), openings INTEGER NOT NULL CHECK(openings>0), status TEXT NOT NULL, opened_at TEXT NOT NULL);
```

### `overtime_attendance`

独立周末打卡事实；每人每周末出勤日一行，核验申请时长。数据库：business。

当前合成行数：965。

| 字段 | 类型 | 声明约束 / 关联 | 含义 |
|---|---|---|---|
| `id` | INTEGER | PK(1) | 记录标识 |
| `employee_id` | INTEGER | NOT NULL; → employees.id | 员工标识 |
| `day` | TEXT | NOT NULL; → work_calendar.day | 业务日期YYYY-MM-DD |
| `check_in` | INTEGER | NOT NULL | 到岗时刻；距午夜分钟，缺卡可空 |
| `check_out` | INTEGER | NOT NULL | 离岗时刻；距午夜分钟，缺卡可空 |
| `break_minutes` | INTEGER | NOT NULL | 周末打卡区间内扣除的休息分钟 |
| `work_minutes` | INTEGER | NOT NULL | 扣除午休后的净在岗分钟 |

```sql
CREATE TABLE overtime_attendance (id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL REFERENCES employees(id), day TEXT NOT NULL REFERENCES work_calendar(day), check_in INTEGER NOT NULL, check_out INTEGER NOT NULL, break_minutes INTEGER NOT NULL CHECK(break_minutes>=0), work_minutes INTEGER NOT NULL CHECK(work_minutes>0), CHECK(check_in>=0 AND check_out<=1320 AND check_out>check_in AND work_minutes=check_out-check_in-break_minutes), UNIQUE(employee_id,day));
```

| 索引 | 列 | 唯一 | 部分索引 | 来源 |
|---|---|---|---|---|
| `sqlite_autoindex_overtime_attendance_1` | employee_id, day | True | False | u |

### `principals`

演示主体及授权；每个演示身份一行。数据库：application。

| 字段 | 类型 | 声明约束 / 关联 | 含义 |
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
| `enabled` | INTEGER | NOT NULL; DEFAULT 1 | 账号启用0/1 |
| `policy_version` | INTEGER | NOT NULL; DEFAULT 1 | 权限策略版本 |

```sql
CREATE TABLE principals(id TEXT PRIMARY KEY, employee_id INTEGER NOT NULL, role TEXT NOT NULL, label TEXT NOT NULL, title TEXT NOT NULL, scope_mode TEXT NOT NULL, scope_root INTEGER NOT NULL, salary_aggregate INTEGER NOT NULL, can_export INTEGER NOT NULL, enabled INTEGER NOT NULL DEFAULT 1, policy_version INTEGER NOT NULL DEFAULT 1);
```

| 索引 | 列 | 唯一 | 部分索引 | 来源 |
|---|---|---|---|---|
| `sqlite_autoindex_principals_1` | id | True | False | pk |

### `sessions`

会话；仅保存令牌摘要，不保存原令牌。数据库：application。

| 字段 | 类型 | 声明约束 / 关联 | 含义 |
|---|---|---|---|
| `token_hash` | TEXT | PK(1) | 会话令牌SHA-256摘要 |
| `principal_id` | TEXT | NOT NULL; → principals.id | 应用身份标识 |
| `csrf` | TEXT | NOT NULL | 会话CSRF校验值 |
| `expires_at` | REAL | NOT NULL | 到期Unix时间戳秒 |

```sql
CREATE TABLE sessions(token_hash TEXT PRIMARY KEY, principal_id TEXT NOT NULL REFERENCES principals(id), csrf TEXT NOT NULL, expires_at REAL NOT NULL);
```

| 索引 | 列 | 唯一 | 部分索引 | 来源 |
|---|---|---|---|---|
| `sqlite_autoindex_sessions_1` | token_hash | True | False | pk |

### `metrics`

已发布指标目录；每个指标一行JSON定义。数据库：application。

| 字段 | 类型 | 声明约束 / 关联 | 含义 |
|---|---|---|---|
| `id` | TEXT | PK(1) | 记录标识 |
| `definition` | TEXT | NOT NULL | 指标JSON定义 |
| `version` | TEXT | NOT NULL | 定义版本 |

```sql
CREATE TABLE metrics(id TEXT PRIMARY KEY, definition TEXT NOT NULL, version TEXT NOT NULL);
```

| 索引 | 列 | 唯一 | 部分索引 | 来源 |
|---|---|---|---|---|
| `sqlite_autoindex_metrics_1` | id | True | False | pk |

### `metric_search`

由指标目录派生的FTS5 trigram检索索引，可重建。数据库：application。

| 字段 | 类型 | 声明约束 / 关联 | 含义 |
|---|---|---|---|
| `id` | FTS TEXT | — | 记录标识 |
| `content` | FTS TEXT | — | 派生检索文本 |

```sql
CREATE VIRTUAL TABLE metric_search USING fts5(id UNINDEXED, content, tokenize='trigram');
```

### `dashboards`

私人看板；存查询计划，不持久复制结果。数据库：application。

| 字段 | 类型 | 声明约束 / 关联 | 含义 |
|---|---|---|---|
| `id` | TEXT | PK(1) | 记录标识 |
| `owner_id` | TEXT | NOT NULL; → principals.id | 记录所属身份 |
| `title` | TEXT | NOT NULL | 显示标题 |
| `plan` | TEXT | NOT NULL | 严格类型查询计划JSON |
| `catalog_version` | TEXT | NOT NULL | 指标目录版本 |
| `created_at` | TEXT | NOT NULL | 记录创建时间ISO格式 |

```sql
CREATE TABLE dashboards(id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES principals(id), title TEXT NOT NULL, plan TEXT NOT NULL, catalog_version TEXT NOT NULL, created_at TEXT NOT NULL);
```

| 索引 | 列 | 唯一 | 部分索引 | 来源 |
|---|---|---|---|---|
| `sqlite_autoindex_dashboards_1` | id | True | False | pk |

### `audit_events`

应用审计事件；不包含业务结果或个人证件。数据库：application。

| 字段 | 类型 | 声明约束 / 关联 | 含义 |
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

```sql
CREATE TABLE audit_events(id TEXT PRIMARY KEY, principal_id TEXT NOT NULL, action TEXT NOT NULL, outcome TEXT NOT NULL, metric_id TEXT, scope_count INTEGER, policy_version TEXT NOT NULL, duration_ms REAL NOT NULL, created_at TEXT NOT NULL);
```

| 索引 | 列 | 唯一 | 部分索引 | 来源 |
|---|---|---|---|---|
| `idx_audit_principal` | principal_id, created_at | False | False | c |
| `sqlite_autoindex_audit_events_1` | id | True | False | pk |

```sql
CREATE INDEX idx_audit_principal ON audit_events(principal_id,created_at);
```

### `conversations`

最小对话记录；用于同一身份的前次计划继承。数据库：application。

| 字段 | 类型 | 声明约束 / 关联 | 含义 |
|---|---|---|---|
| `id` | TEXT | PK(1) | 记录标识 |
| `principal_id` | TEXT | NOT NULL | 应用身份标识 |
| `question` | TEXT | NOT NULL | 用户问题；生产需制定脱敏及留存策略 |
| `plan` | TEXT | — | 严格类型查询计划JSON |
| `outcome` | TEXT | NOT NULL | 执行或授权结果 |
| `created_at` | TEXT | NOT NULL | 记录创建时间ISO格式 |

```sql
CREATE TABLE conversations(id TEXT PRIMARY KEY, principal_id TEXT NOT NULL, question TEXT NOT NULL, plan TEXT, outcome TEXT NOT NULL, created_at TEXT NOT NULL);
```

| 索引 | 列 | 唯一 | 部分索引 | 来源 |
|---|---|---|---|---|
| `sqlite_autoindex_conversations_1` | id | True | False | pk |

### `debug_runs`

逐节点调试记录；每次自然语言查询一行，按身份与授权快照隔离，最多保留50次。数据库：application。

| 字段 | 类型 | 声明约束 / 关联 | 含义 |
|---|---|---|---|
| `id` | TEXT | PK(1) | 记录标识 |
| `owner_id` | TEXT | NOT NULL; → principals.id | 记录所属身份 |
| `grant_fingerprint` | TEXT | NOT NULL | 身份能力、授权人员集合及策略版本的SHA-256指纹；读取时重新核验 |
| `question` | TEXT | NOT NULL | 用户问题；生产需制定脱敏及留存策略 |
| `status` | TEXT | NOT NULL | 业务状态；取值由对应表约束与生成器定义 |
| `started_at` | TEXT | NOT NULL | 执行开始时间UTC ISO格式 |
| `finished_at` | TEXT | — | 执行结束时间UTC ISO格式；运行中为空 |
| `duration_ms` | REAL | NOT NULL; DEFAULT 0 | 操作时长毫秒 |
| `payload` | TEXT | NOT NULL | 已脱敏的逐节点输入、输出、耗时、错误及最终响应JSON |

```sql
CREATE TABLE debug_runs (
            id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES principals(id),
            grant_fingerprint TEXT NOT NULL, question TEXT NOT NULL, status TEXT NOT NULL,
            started_at TEXT NOT NULL, finished_at TEXT, duration_ms REAL NOT NULL DEFAULT 0,
            payload TEXT NOT NULL
        );
```

| 索引 | 列 | 唯一 | 部分索引 | 来源 |
|---|---|---|---|---|
| `idx_debug_owner` | owner_id, started_at | False | False | c |
| `sqlite_autoindex_debug_runs_1` | id | True | False | pk |

```sql
CREATE INDEX idx_debug_owner ON debug_runs(owner_id, started_at DESC);
```

## 已开放的17个指标

目录版本 `hr-metrics-1.1`；下列表达式从实际编译的 SQL 提取。表达式依赖同一 SQL 的授权集合、日期与任职 CTE，不能脱离这些条件执行。完整示例计划及 SQL 可在系统中展开，也保存在同目录 `data-dictionary.json` 中。

### 在职人数 `headcount`

在统计日已入职且尚未离职的去重员工数，包含正式、实习和外包。离职日不计在职。

- 单位：人；业务域：人员。
- 可分组：事业部 (`division`), 部门（含下属团队） (`department`), 团队/任职组织 (`team`), 岗位序列 (`job_family`), 工作地 (`location`), 用工类型 (`employment_type`), 汇报关系 (`relation`), 月份 (`month`), 最高学历 (`education`), 最高学位 (`degree`), 最高学历毕业院校 (`school`)；也可不分组，单次只支持一个分组维度。
- 数据来源：employees, assignments, employee_education, schools。
- 别名：人数, 员工数, 人员规模, 下属。
- 敏感级别：`internal`；最小组规模：1。
- 责任人：HR 数据负责人（模拟）；指标版本：1.1。
- 示例问题：按事业部统计本月在职人数

实际聚合表达式：

```sql
COUNT(DISTINCT e.id)
```

### 新入职人数 `hires`

入职日期落在选定期间的去重员工数，组织按入职时任职关系归属。

- 单位：人；业务域：人员。
- 可分组：事业部 (`division`), 部门（含下属团队） (`department`), 团队/任职组织 (`team`), 工作地 (`location`), 月份 (`month`), 季度 (`quarter`), 最高学历 (`education`), 最高学位 (`degree`), 最高学历毕业院校 (`school`)；也可不分组，单次只支持一个分组维度。
- 数据来源：employees, assignments, employee_education, schools。
- 别名：新增, 入职, 招聘入职。
- 敏感级别：`internal`；最小组规模：1。
- 责任人：HR 数据负责人（模拟）；指标版本：1.1。
- 示例问题：按事业部统计本月新入职人数

实际聚合表达式：

```sql
COUNT(DISTINCT e.id)
```

### 离职人数 `departures`

离职日期落在选定期间的去重员工数，组织按离职日前一天归属。

- 单位：人；业务域：人员。
- 可分组：事业部 (`division`), 部门（含下属团队） (`department`), 团队/任职组织 (`team`), 月份 (`month`), 季度 (`quarter`), 最高学历 (`education`), 最高学位 (`degree`), 最高学历毕业院校 (`school`)；也可不分组，单次只支持一个分组维度。
- 数据来源：employees, assignments, employee_education, schools。
- 别名：离职, 流失人数。
- 敏感级别：`internal`；最小组规模：1。
- 责任人：HR 数据负责人（模拟）；指标版本：1.1。
- 示例问题：按事业部统计本月离职人数

实际聚合表达式：

```sql
COUNT(DISTINCT e.id)
```

### 人员离职率 `turnover_rate`

期间离职人数 ÷ ((期初在职人数 + 期末在职人数) / 2) × 100。为演示统一口径，不进行年化。

- 单位：%；业务域：人员。
- 可分组：事业部 (`division`), 部门（含下属团队） (`department`), 团队/任职组织 (`team`)；也可不分组，单次只支持一个分组维度。
- 数据来源：employees, assignments。
- 别名：离职率, 流失率。
- 敏感级别：`internal`；最小组规模：1。
- 责任人：HR 数据负责人（模拟）；指标版本：1.1。
- 示例问题：按事业部统计本月人员离职率

实际聚合表达式：

```sql
ROUND(200.0*SUM(f.exits)/NULLIF(SUM(f.opening)+SUM(f.closing),0),2)
```

### 平均司龄 `avg_tenure`

统计日在职员工从最近入职日起至统计日的天数 / 365.25 的算术平均。

- 单位：年；业务域：人员。
- 可分组：事业部 (`division`), 部门（含下属团队） (`department`), 团队/任职组织 (`team`), 岗位序列 (`job_family`), 最高学历 (`education`), 最高学位 (`degree`), 最高学历毕业院校 (`school`)；也可不分组，单次只支持一个分组维度。
- 数据来源：employees, assignments, employee_education, schools。
- 别名：司龄, 工龄。
- 敏感级别：`internal`；最小组规模：1。
- 责任人：HR 数据负责人（模拟）；指标版本：1.1。
- 示例问题：按事业部统计本月平均司龄

实际聚合表达式：

```sql
ROUND(AVG(f.amount),2)
```

### 出勤率 `attendance_rate`

正常或远程出勤人日 ÷ (应出勤人日 - 已批准整日请假人日) × 100。缺卡、缺勤不计完成出勤。

- 单位：%；业务域：考勤。
- 可分组：事业部 (`division`), 部门（含下属团队） (`department`), 团队/任职组织 (`team`), 日期 (`day`), 月份 (`month`), 季度 (`quarter`)；也可不分组，单次只支持一个分组维度。
- 数据来源：attendance_daily, assignments。
- 别名：出勤, 到岗率。
- 敏感级别：`internal`；最小组规模：1。
- 责任人：HR 数据负责人（模拟）；指标版本：1.1。
- 示例问题：按事业部统计本月出勤率

实际聚合表达式：

```sql
ROUND(100.0*SUM(CASE WHEN f.status IN ('正常','远程') THEN 1 ELSE 0 END)/NULLIF(SUM(CASE WHEN f.status<>'请假' THEN 1 ELSE 0 END),0),2)
```

### 迟到人次 `late_count`

工作日上班打卡晚于 09:30 的人日数。09:30 整不迟到。

- 单位：人次；业务域：考勤。
- 可分组：事业部 (`division`), 部门（含下属团队） (`department`), 团队/任职组织 (`team`), 日期 (`day`), 月份 (`month`), 季度 (`quarter`)；也可不分组，单次只支持一个分组维度。
- 数据来源：attendance_daily, assignments。
- 别名：迟到, 迟到次数。
- 敏感级别：`internal`；最小组规模：1。
- 责任人：HR 数据负责人（模拟）；指标版本：1.1。
- 示例问题：按事业部统计本月迟到人次

实际聚合表达式：

```sql
COALESCE(SUM(CASE WHEN f.late_minutes>0 THEN 1 ELSE 0 END),0)
```

### 迟到率 `late_rate`

迟到人次 ÷ 有上班打卡的应出勤人次 × 100。远程同样按弹性规则统计。

- 单位：%；业务域：考勤。
- 可分组：事业部 (`division`), 部门（含下属团队） (`department`), 团队/任职组织 (`team`), 日期 (`day`), 月份 (`month`), 季度 (`quarter`)；也可不分组，单次只支持一个分组维度。
- 数据来源：attendance_daily, assignments。
- 别名：迟到率。
- 敏感级别：`internal`；最小组规模：1。
- 责任人：HR 数据负责人（模拟）；指标版本：1.1。
- 示例问题：按事业部统计本月迟到率

实际聚合表达式：

```sql
ROUND(100.0*SUM(CASE WHEN f.late_minutes>0 THEN 1 ELSE 0 END)/NULLIF(COUNT(f.check_in),0),2)
```

### 考勤异常人次 `abnormal_count`

迟到、早退、缺勤或缺卡任一条件成立的人日数，同一人同一天只计一次。

- 单位：人次；业务域：考勤。
- 可分组：事业部 (`division`), 部门（含下属团队） (`department`), 团队/任职组织 (`team`), 日期 (`day`), 月份 (`month`), 季度 (`quarter`)；也可不分组，单次只支持一个分组维度。
- 数据来源：attendance_daily, assignments。
- 别名：异常, 缺卡, 考勤异常。
- 敏感级别：`internal`；最小组规模：1。
- 责任人：HR 数据负责人（模拟）；指标版本：1.1。
- 示例问题：按事业部统计本月考勤异常人次

实际聚合表达式：

```sql
COALESCE(SUM(CASE WHEN f.late_minutes>0 OR f.early_minutes>0 OR f.status IN ('缺勤','缺卡') THEN 1 ELSE 0 END),0)
```

### 已批准加班时长 `approved_overtime_hours`

选定期间工作日及周末已批准加班申请分钟数之和 / 60。工作日晚离岗与周末实际打卡分别校验；待审批和拒绝申请不计入。

- 单位：小时；业务域：考勤。
- 可分组：事业部 (`division`), 部门（含下属团队） (`department`), 团队/任职组织 (`team`), 日期 (`day`), 月份 (`month`), 季度 (`quarter`)；也可不分组，单次只支持一个分组维度。
- 数据来源：overtime_requests, assignments。
- 别名：加班, 审批加班, 加班时长。
- 敏感级别：`internal`；最小组规模：1。
- 责任人：HR 数据负责人（模拟）；指标版本：1.1。
- 示例问题：按事业部统计本月已批准加班时长

实际聚合表达式：

```sql
ROUND(COALESCE(SUM(f.amount),0),2)
```

### 晚离岗时长 `late_departure_hours`

下班晚于个人应离岗时间的分钟数之和 / 60。应离岗时间为 max(18:00, 上班时间 + 9小时)，午休为1小时。该指标不是劳动报酬口径。

- 单位：小时；业务域：考勤。
- 可分组：事业部 (`division`), 部门（含下属团队） (`department`), 团队/任职组织 (`team`), 日期 (`day`), 月份 (`month`), 季度 (`quarter`)；也可不分组，单次只支持一个分组维度。
- 数据来源：attendance_daily, assignments。
- 别名：晚下班, 晚离岗, 晚走。
- 敏感级别：`internal`；最小组规模：1。
- 责任人：HR 数据负责人（模拟）；指标版本：1.1。
- 示例问题：按事业部统计本月晚离岗时长

实际聚合表达式：

```sql
ROUND(COALESCE(SUM(f.late_departure_minutes),0)/60.0,2)
```

### 平均有效在岗时长 `avg_work_hours`

正常或远程且上下班打卡完整的净在岗分钟（打卡间隔减60分钟午休）÷ 完整打卡人日 ÷ 60。

- 单位：小时/人日；业务域：考勤。
- 可分组：事业部 (`division`), 部门（含下属团队） (`department`), 团队/任职组织 (`team`), 日期 (`day`), 月份 (`month`), 季度 (`quarter`)；也可不分组，单次只支持一个分组维度。
- 数据来源：attendance_daily, assignments。
- 别名：工作时长, 工时, 在岗时长。
- 敏感级别：`internal`；最小组规模：1。
- 责任人：HR 数据负责人（模拟）；指标版本：1.1。
- 示例问题：按事业部统计本月平均有效在岗时长

实际聚合表达式：

```sql
ROUND(AVG(CASE WHEN f.status IN ('正常','远程') AND f.check_in IS NOT NULL AND f.check_out IS NOT NULL THEN f.work_minutes/60.0 END),2)
```

### 已批准请假天数 `leave_days`

选定期间已批准整日请假天数。演示不包含半天、跨时区与跨午夜班次。

- 单位：天；业务域：考勤。
- 可分组：事业部 (`division`), 部门（含下属团队） (`department`), 团队/任职组织 (`team`), 日期 (`day`), 月份 (`month`), 季度 (`quarter`)；也可不分组，单次只支持一个分组维度。
- 数据来源：leave_requests, assignments。
- 别名：请假, 休假, 年假。
- 敏感级别：`internal`；最小组规模：1。
- 责任人：HR 数据负责人（模拟）；指标版本：1.1。
- 示例问题：按事业部统计本月已批准请假天数

实际聚合表达式：

```sql
ROUND(COALESCE(SUM(f.amount),0),2)
```

### 平均基本月薪 `avg_salary`

统计日在职员工有效基本月薪的算术平均，仅CNY，不含奖金和补贴。仅公司负责人获准汇总，少于5人的分组不显示；不开放任意人员过滤。

- 单位：元/月；业务域：薪酬。
- 可分组：事业部 (`division`)；也可不分组，单次只支持一个分组维度。
- 数据来源：compensation, employees, assignments。
- 别名：薪资, 工资, 薪酬, 月薪, 平均工资。
- 敏感级别：`restricted_aggregate`；最小组规模：5。
- 责任人：薪酬负责人（模拟）；指标版本：1.1。
- 示例问题：按事业部统计本月平均基本月薪

实际聚合表达式：

```sql
ROUND(AVG(f.amount),2)
```

### 入离职与净增人数 `workforce_changes`

同一期间分别统计入职人数、离职人数，净增=入职-离职；入职归属入职日组织，离职归属离职日前一日。部门包含下属团队，内部调动不计入离职。无事件的授权组织显示0。

- 单位：人；业务域：人员。
- 可分组：事业部 (`division`), 部门（含下属团队） (`department`), 团队/任职组织 (`team`), 月份 (`month`), 季度 (`quarter`), 最高学历 (`education`), 最高学位 (`degree`), 最高学历毕业院校 (`school`)；也可不分组，单次只支持一个分组维度。
- 数据来源：employees, assignments, employee_education, schools。
- 别名：入离职, 入职和离职, 人员净增, 净增人数。
- 敏感级别：`internal`；最小组规模：1。
- 责任人：HR 数据负责人（模拟）；指标版本：1.1。
- 示例问题：整个公司今年各部门入职和离职人数统计

实际聚合表达式：

```sql
COALESCE(SUM(f.hires),0)-COALESCE(SUM(f.departures),0)
```

### 周末已批准加班时长 `weekend_overtime_hours`

选定期间周六/周日已批准加班申请分钟之和 / 60；以独立周末打卡净时长为申请上限，不含工作日晚离岗、待审批、拒绝。演示不含节假日调休。无事件的授权组织显示0。

- 单位：小时；业务域：考勤。
- 可分组：事业部 (`division`), 部门（含下属团队） (`department`), 团队/任职组织 (`team`), 日期 (`day`), 月份 (`month`), 季度 (`quarter`)；也可不分组，单次只支持一个分组维度。
- 数据来源：overtime_requests, overtime_attendance, assignments。
- 别名：周末加班, 周六周日加班, 双休日加班。
- 敏感级别：`internal`；最小组规模：1。
- 责任人：HR 数据负责人（模拟）；指标版本：1.1。
- 示例问题：本月各部门周末加班的总工时

实际聚合表达式：

```sql
ROUND(COALESCE(SUM(f.amount),0),2)
```

### 教育背景人员占比 `education_ratio`

满足学历、学位、学校或院校标签条件的去重人数÷同组全部授权人群×100。默认统计日在职人群及最高已完成教育经历；可指定期间入职或离职人群，教育按事件日取值。未知教育计入分母，分母0返回NULL，并列出分子与分母。

- 单位：%；业务域：人员。
- 可分组：事业部 (`division`), 部门（含下属团队） (`department`), 团队/任职组织 (`team`)；也可不分组，单次只支持一个分组维度。
- 数据来源：employees, assignments, employee_education, schools。
- 别名：学历占比, 硕士比例, 博士比例, 985比例, 211比例, 毕业院校占比。
- 敏感级别：`internal`；最小组规模：1。
- 责任人：HR 数据负责人（模拟）；指标版本：1.1。
- 示例问题：平台研发部硕士及以上学历员工的比例

实际聚合表达式：

```sql
ROUND(100.0*COUNT(DISTINCT CASE WHEN EXISTS (SELECT 1 FROM employee_education q JOIN schools qs ON qs.id=q.school_id WHERE q.employee_id=e.id AND q.graduation_date<=f.attr_day AND q.graduation_date<=f.attr_day AND NOT EXISTS (
        SELECT 1 FROM employee_education newer WHERE newer.employee_id=q.employee_id AND newer.graduation_date<=f.attr_day
        AND (newer.education_rank>q.education_rank OR (newer.education_rank=q.education_rank AND (newer.graduation_date>q.graduation_date OR (newer.graduation_date=q.graduation_date AND newer.id>q.id))))) AND q.degree=:edu_degree) THEN e.id END)/NULLIF(COUNT(DISTINCT e.id),0),2)
```

## 共用业务口径与能力边界

### 数据范围

全部为可复现合成数据，演示时区Asia/Shanghai；今天/本月按数据截止日解释。

### 组织与授权

公司→事业部→部门→团队。当前管理闭包决定授权集合；本人depth=0、直属=1、间接>=2；HRBP用服务组织范围。

### 在职与历史归属

hire_date<=统计日，termination_date为空或>统计日。任职有效期[valid_from,valid_to)，历史分组按业务发生日任职。离职归属离职日前一天。

### 弹性班次

08:00–09:30到岗，09:30整不迟到。演示补充净工作480分钟、午休60分钟，应离岗=max(18:00,到岗+9小时)。

### 晚离岗与加班

晚离岗=max(下班-应离岗,0)；仅已批准申请计加班。两者分别建模，不自动等同。模拟打卡最晚22:00。

### 日历与请假

日历从演示当年1月1日至数据日；周一至周五为应出勤日，周末独立记录加班打卡和申请。未接法定节假日调休、半天假、跨夜班。正常/远程算完成出勤，缺卡与缺勤不算。

### 除零、空值与精度

比率分母为0返回NULL。人数为去重员工，人次为员工×日期。比例、均值与小时数按SQL保留2位；界面部分摘要显示1位。

### 查询边界

单维度，入职/离职/净增为预定义组合指标。明细1–100行；聚合最多400组；日期差不超过366天。支持已完成学历/学位/学校条件及入离职名单。未开放部门数量、年龄/性别/专业/学习形式筛选、自由多指标、多维度、排名、同比环比和预测。

### 历史趋势

人数月趋势统计月末，当前月截至数据日；入职按入职日，离职按离职日。没有事实的分组可能缺席，不补造历史记录。

### 教育背景与学校去重

学历与学位分开存储，历史问数按业务发生日已经完成的最高教育经历取值；硕士默认精确硕士学位，硕士及以上按学历层级包含博士。某校毕业默认匹配任一已完成经历，多校OR按员工去重；同一经历需同时满足学校与学位等条件。

### 教育占比的分子与分母

学历/学位/211或985占比默认最高已完成教育经历。分子为满足教育条件的去重员工，分母为同组织同权限的全部在职员工，含教育未知者；指定入职/离职人群时改用期间事件人群，学历仍按事件日判断。分母0返回NULL，保留分子分母。985与211合并使用OR，不能相加；双一流不是同一标签。

### 部门汇总与期间

各部门指三级部门并包含下属团队，公司及事业部直属人员单列；各团队保留具体任职组织。部门过滤按业务发生日任职归属，并与当前授权取交集。上季度为上一完整自然季度；今年从1月1日至数据截止日。内部调动不计入离职；入离职组合及周末加班为无事件的授权组织显示0。

### 周末加班

周六或周日且day_type=周末的已批准申请分钟之和/60。独立打卡验证申请不超净工时；待审批/已拒绝不计入，不用晚离岗冒充。批准加班总时长包含工作日与周末，周末指标仅子集；未指定期间默认本月。

### 薪酬保护

只开放当前全授权范围/事业部的基本月薪均值，仅CNY。小于5人及必要互补组隐藏；禁止人员筛选、历史差分、明细和导出。

## 表已建立，但尚未开放的能力

绩效评价、培训、招聘需求已有合成关系表，尚无对应问数指标；年龄、性别、专业与学习形式筛选未开放。私人电话、证件和银行账号不进入模型工具或查询白名单。基本月薪不是完整工资支付流水，目前没有奖金、补贴、扣款、社保、公积金、实发工资的计算与支付模型。

本机 SQLite 演示使用应用授权与只读 SQL 编译器。正式接入需验证真实宽表映射、HR 确认口径、企业 SSO 与数据库级行列防护。调试信息的记录范围和访问规则见 `docs/DEBUGGING.md`。
