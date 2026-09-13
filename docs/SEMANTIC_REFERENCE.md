# 语义定义完整清单

由 `scripts/document_semantics.py` 从 Git JSON 定义源生成。语义版本 `hr-semantics-1.0`；发布指纹 `351f466b41facfaec0047b2cdf65ce5cf041bd3a333bb7a3f35077c1f5457d87`。

包括 200 个字段、32 个指标定义（17个可执行、15个规划）。完整问题库见 [HR问题库](HR_QUESTION_BANK.md)，设计决策见 [语义层与查询图](SEMANTIC_ARCHITECTURE.md)。

字段存在与列出规划公式均不等于已开放查询。权限、白名单和计算实现仍由服务端控制；所有示例均为人工合成的格式或枚举，不扫描员工实际值。

## 字段：表ID.字段ID

### `dataset_meta` · 数据集元信息

数据集元信息；每个配置键一行

粒度：每个配置键一行。不表示：不是任意字段可以混连的宽表；连接必须遵守外键、人员权限与有效期，不能把一人多条事实当成员工人数。

| 字段唯一ID / 类型 | 名称与口语别名 | 表示什么 | 不表示什么 | 单位 / 示例值 / 可空 |
|---|---|---|---|---|
| `dataset_meta.key`<br>TEXT | 配置键<br>数据集元信息配置键、配置键字段、dataset_meta.key | 配置键 | 不是独立统计指标，也不能脱离数据集元信息的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `dataset_meta.value`<br>TEXT | 配置值<br>数据集元信息配置值、配置值字段、dataset_meta.value | 配置值 | 不是独立统计指标，也不能脱离数据集元信息的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |

### `legal_entities` · 法人主体

法人主体；每个主体一行

粒度：每个主体一行。不表示：不是任意字段可以混连的宽表；连接必须遵守外键、人员权限与有效期，不能把一人多条事实当成员工人数。

| 字段唯一ID / 类型 | 名称与口语别名 | 表示什么 | 不表示什么 | 单位 / 示例值 / 可空 |
|---|---|---|---|---|
| `legal_entities.id`<br>INTEGER | 记录主键<br>法人主体记录主键、记录主键字段、legal_entities.id | 法人主体的内部记录主键；在本表内唯一，关联关系见外键，不能充当业务统计人数的独立口径。 | 不是员工工号，也不是姓名；仅在本表主键空间唯一，不可跨表直接比较数值。 | None<br>[]<br>可空：False |
| `legal_entities.name`<br>TEXT | 名称<br>法人主体名称、名称字段、legal_entities.name | 法人主体的业务名称；用于人类可读展示和明确名称匹配，内部连接仍以ID为准。 | 不是独立统计指标，也不能脱离法人主体的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |

### `locations` · 办公地点

办公地点；每个地点一行

粒度：每个地点一行。不表示：不是任意字段可以混连的宽表；连接必须遵守外键、人员权限与有效期，不能把一人多条事实当成员工人数。

| 字段唯一ID / 类型 | 名称与口语别名 | 表示什么 | 不表示什么 | 单位 / 示例值 / 可空 |
|---|---|---|---|---|
| `locations.id`<br>INTEGER | 记录主键<br>办公地点记录主键、记录主键字段、locations.id | 办公地点的内部记录主键；在本表内唯一，关联关系见外键，不能充当业务统计人数的独立口径。 | 不是员工工号，也不是姓名；仅在本表主键空间唯一，不可跨表直接比较数值。 | None<br>[]<br>可空：False |
| `locations.name`<br>TEXT | 名称<br>办公地点名称、名称字段、locations.name | 办公地点的业务名称；用于人类可读展示和明确名称匹配，内部连接仍以ID为准。 | 不是独立统计指标，也不能脱离办公地点的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>["上海", "杭州"]<br>可空：False |
| `locations.timezone`<br>TEXT | 业务时区<br>办公地点业务时区、业务时区字段、locations.timezone | IANA时区 | 不是独立统计指标，也不能脱离办公地点的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>["Asia/Shanghai"]<br>可空：False |

### `departments` · 组织节点

组织节点；四级树，每个组织一行

粒度：四级树，每个组织一行。不表示：不是任意字段可以混连的宽表；连接必须遵守外键、人员权限与有效期，不能把一人多条事实当成员工人数。

| 字段唯一ID / 类型 | 名称与口语别名 | 表示什么 | 不表示什么 | 单位 / 示例值 / 可空 |
|---|---|---|---|---|
| `departments.id`<br>INTEGER | 记录主键<br>组织节点记录主键、记录主键字段、departments.id | 组织节点的内部记录主键；在本表内唯一，关联关系见外键，不能充当业务统计人数的独立口径。 | 不是员工工号，也不是姓名；仅在本表主键空间唯一，不可跨表直接比较数值。 | None<br>[]<br>可空：False |
| `departments.name`<br>TEXT | 名称<br>部门名称、组织名字、哪个部门、组织名称 | 组织节点的业务名称；用于人类可读展示和明确名称匹配，内部连接仍以ID为准。 | 不是独立统计指标，也不能脱离组织节点的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>["平台研发部", "产品研发事业部", "平台研发一组"]<br>可空：False |
| `departments.parent_id`<br>INTEGER | 父组织ID<br>组织节点父组织ID、父组织ID字段、departments.parent_id | 父组织；根节点为空 | 不是独立统计指标，也不能脱离组织节点的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：True |
| `departments.level`<br>INTEGER | 组织层级<br>组织节点组织层级、组织层级字段、departments.level | 公司1/事业部2/部门3/团队4 | 不是独立统计指标，也不能脱离组织节点的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[1, 2, 3, 4]<br>可空：False |
| `departments.division_id`<br>INTEGER | 所属事业部ID<br>组织节点所属事业部ID、所属事业部ID字段、departments.division_id | 所属事业部标识 | 不是独立统计指标，也不能脱离组织节点的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：True |

### `job_families` · 岗位序列

岗位序列；每个序列一行

粒度：每个序列一行。不表示：不是任意字段可以混连的宽表；连接必须遵守外键、人员权限与有效期，不能把一人多条事实当成员工人数。

| 字段唯一ID / 类型 | 名称与口语别名 | 表示什么 | 不表示什么 | 单位 / 示例值 / 可空 |
|---|---|---|---|---|
| `job_families.id`<br>INTEGER | 记录主键<br>岗位序列记录主键、记录主键字段、job_families.id | 岗位序列的内部记录主键；在本表内唯一，关联关系见外键，不能充当业务统计人数的独立口径。 | 不是员工工号，也不是姓名；仅在本表主键空间唯一，不可跨表直接比较数值。 | None<br>[]<br>可空：False |
| `job_families.name`<br>TEXT | 名称<br>岗位序列名称、名称字段、job_families.name | 岗位序列的业务名称；用于人类可读展示和明确名称匹配，内部连接仍以ID为准。 | 不是独立统计指标，也不能脱离岗位序列的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |

### `grades` · 职级及模拟薪资范围

职级及模拟薪资范围；每级一行

粒度：每级一行。不表示：不是任意字段可以混连的宽表；连接必须遵守外键、人员权限与有效期，不能把一人多条事实当成员工人数。

| 字段唯一ID / 类型 | 名称与口语别名 | 表示什么 | 不表示什么 | 单位 / 示例值 / 可空 |
|---|---|---|---|---|
| `grades.id`<br>INTEGER | 记录主键<br>职级及模拟薪资范围记录主键、记录主键字段、grades.id | 职级及模拟薪资范围的内部记录主键；在本表内唯一，关联关系见外键，不能充当业务统计人数的独立口径。 | 不是员工工号，也不是姓名；仅在本表主键空间唯一，不可跨表直接比较数值。 | None<br>[]<br>可空：False |
| `grades.name`<br>TEXT | 名称<br>职级及模拟薪资范围名称、名称字段、grades.name | 职级及模拟薪资范围的业务名称；用于人类可读展示和明确名称匹配，内部连接仍以ID为准。 | 不是独立统计指标，也不能脱离职级及模拟薪资范围的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `grades.salary_min`<br>INTEGER | 职级薪资下限<br>职级及模拟薪资范围职级薪资下限、职级薪资下限字段、grades.salary_min | 模拟月薪下限，元 | 不是独立统计指标，也不能脱离职级及模拟薪资范围的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `grades.salary_max`<br>INTEGER | 职级薪资上限<br>职级及模拟薪资范围职级薪资上限、职级薪资上限字段、grades.salary_max | 模拟月薪上限，元 | 不是独立统计指标，也不能脱离职级及模拟薪资范围的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |

### `positions` · 岗位字典

岗位字典；每个岗位一行

粒度：每个岗位一行。不表示：不是任意字段可以混连的宽表；连接必须遵守外键、人员权限与有效期，不能把一人多条事实当成员工人数。

| 字段唯一ID / 类型 | 名称与口语别名 | 表示什么 | 不表示什么 | 单位 / 示例值 / 可空 |
|---|---|---|---|---|
| `positions.id`<br>INTEGER | 记录主键<br>岗位字典记录主键、记录主键字段、positions.id | 岗位字典的内部记录主键；在本表内唯一，关联关系见外键，不能充当业务统计人数的独立口径。 | 不是员工工号，也不是姓名；仅在本表主键空间唯一，不可跨表直接比较数值。 | None<br>[]<br>可空：False |
| `positions.name`<br>TEXT | 名称<br>岗位字典名称、名称字段、positions.name | 岗位字典的业务名称；用于人类可读展示和明确名称匹配，内部连接仍以ID为准。 | 不是独立统计指标，也不能脱离岗位字典的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `positions.family_id`<br>INTEGER | 岗位序列ID<br>岗位字典岗位序列ID、岗位序列ID字段、positions.family_id | 岗位序列标识 | 不是独立统计指标，也不能脱离岗位字典的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `positions.is_manager`<br>INTEGER | 管理岗位标记<br>岗位字典管理岗位标记、管理岗位标记字段、positions.is_manager | 管理岗位标记0/1 | 不是独立统计指标，也不能脱离岗位字典的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |

### `schools` · 院校名称、别名与历史211/985标签

院校名称、别名与历史211/985标签；每校一行，不含员工数据

粒度：每校一行，不含员工数据。不表示：不是任意字段可以混连的宽表；连接必须遵守外键、人员权限与有效期，不能把一人多条事实当成员工人数。

| 字段唯一ID / 类型 | 名称与口语别名 | 表示什么 | 不表示什么 | 单位 / 示例值 / 可空 |
|---|---|---|---|---|
| `schools.id`<br>INTEGER | 记录主键<br>院校名称、别名与历史211/985标签记录主键、记录主键字段、schools.id | 院校名称、别名与历史211/985标签的内部记录主键；在本表内唯一，关联关系见外键，不能充当业务统计人数的独立口径。 | 不是员工工号，也不是姓名；仅在本表主键空间唯一，不可跨表直接比较数值。 | None<br>[]<br>可空：False |
| `schools.name`<br>TEXT | 名称<br>学校全称、院校名称、毕业学校名称 | 院校名称、别名与历史211/985标签的业务名称；用于人类可读展示和明确名称匹配，内部连接仍以ID为准。 | 不是独立统计指标，也不能脱离院校名称、别名与历史211/985标签的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>["清华大学", "北京大学", "澄川大学（模拟）"]<br>可空：False |
| `schools.aliases`<br>TEXT | 院校简称<br>院校名称、别名与历史211/985标签院校简称、院校简称字段、schools.aliases | 院校简称JSON数组，精确归一到院校ID | 不是独立统计指标，也不能脱离院校名称、别名与历史211/985标签的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `schools.is_985`<br>INTEGER | 985院校标签<br>985背景、985学校、是否985毕业 | 历史985项目院校标签0/1；为1时is_211必须为1 | 不是双一流、学校排名或个人能力标签；985与211重叠，不可相加计人数。 | None<br>[0, 1]<br>可空：False |
| `schools.is_211`<br>INTEGER | 211院校标签<br>211背景、211学校、是否211毕业 | 历史211项目院校标签0/1，包含985院校 | 不是211非985；该标记包含985学校，非211不自动说明学校质量。 | None<br>[0, 1]<br>可空：False |
| `schools.classification_basis`<br>TEXT | 院校分类依据<br>院校名称、别名与历史211/985标签院校分类依据、院校分类依据字段、schools.classification_basis | 标签分类依据；真实院校历史名单或虚构标记，不等于双一流 | 不是独立统计指标，也不能脱离院校名称、别名与历史211/985标签的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `schools.source_url`<br>TEXT | 院校标签来源<br>院校名称、别名与历史211/985标签院校标签来源、院校标签来源字段、schools.source_url | 教育部项目名单链接；虚构学校为synthetic标记 | 不是独立统计指标，也不能脱离院校名称、别名与历史211/985标签的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |

### `employees` · 人员基础档案

人员基础档案；每名员工一行

粒度：每名员工一行。不表示：不是任意字段可以混连的宽表；连接必须遵守外键、人员权限与有效期，不能把一人多条事实当成员工人数。

| 字段唯一ID / 类型 | 名称与口语别名 | 表示什么 | 不表示什么 | 单位 / 示例值 / 可空 |
|---|---|---|---|---|
| `employees.id`<br>INTEGER | 记录主键<br>员工内部编号、人员主键、员工ID | 人员基础档案的内部记录主键；在本表内唯一，关联关系见外键，不能充当业务统计人数的独立口径。 | 不是员工工号，也不是姓名；仅在本表主键空间唯一，不可跨表直接比较数值。 | None<br>[]<br>可空：False |
| `employees.employee_no`<br>TEXT | 员工工号<br>工号、员工编号、人员工号 | 稳定工号（CC前缀） | 不是员工表数值主键，不是姓名；同名员工应以工号消歧，SQL连接仍使用内部ID。 | None<br>["CC00052"]<br>可空：False |
| `employees.name`<br>TEXT | 名称<br>人员基础档案名称、名称字段、employees.name | 人员基础档案的业务名称；用于人类可读展示和明确名称匹配，内部连接仍以ID为准。 | 不是独立统计指标，也不能脱离人员基础档案的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `employees.gender`<br>TEXT | 性别<br>人员基础档案性别、性别字段、employees.gender | 模拟性别，未开放查询条件 | 不是可开放的自然语言筛选字段，不能忽略用户提出的性别条件后返回全体结果。 | None<br>[]<br>可空：False |
| `employees.birth_date`<br>TEXT | 出生日期<br>人员基础档案出生日期、出生日期字段、employees.birth_date | 模拟出生日期，未开放查询条件 | 不是入职日、司龄或年龄现值；年龄分析尚未开放。 | 日期<br>[]<br>可空：False |
| `employees.hire_date`<br>TEXT | 入职日期<br>入司时间、报到日期、什么时候来的、入职时间 | 最近入职日期 | 不是试用转正日期、调岗日期或招聘需求创建日；当前只建模最近一次入职，未完整建模多次返聘。 | 日期<br>["2026-04-01"]<br>可空：False |
| `employees.termination_date`<br>TEXT | 离职日期<br>离司日期、最后在职后的第一天、什么时候走的 | 离职日期；当日不计在职，空表示未离职 | 不是提交辞呈日期或最后打卡日期；离职当天已经不在在职人数中，归属取前一天。 | 日期<br>["2026-08-15", null]<br>可空：True |
| `employees.employment_type`<br>TEXT | 用工类型<br>人员基础档案用工类型、用工类型字段、employees.employment_type | 正式/实习/外包 | 不是独立统计指标，也不能脱离人员基础档案的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>["正式", "实习", "外包"]<br>可空：False |
| `employees.entity_id`<br>INTEGER | 法人主体ID<br>人员基础档案法人主体ID、法人主体ID字段、employees.entity_id | 法人主体标识 | 不是独立统计指标，也不能脱离人员基础档案的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `employees.location_id`<br>INTEGER | 办公地点ID<br>人员基础档案办公地点ID、办公地点ID字段、employees.location_id | 地点标识 | 不是独立统计指标，也不能脱离人员基础档案的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `employees.email`<br>TEXT | 工作邮箱<br>人员基础档案工作邮箱、工作邮箱字段、employees.email | 保留示例域名邮箱 | 不是独立统计指标，也不能脱离人员基础档案的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `employees.highest_education`<br>TEXT | 最高已完成学历<br>最高学历、学历背景、文化程度、读到什么学历 | 当前最高已完成学历快照；未知/高中及以下/专科/本科/硕士研究生/博士研究生 | 不是任意一次教育经历，不是最高学位，也不是当前在读学历；历史查询不能直接使用当前快照。 | None<br>["本科", "硕士研究生", "博士研究生", "未知"]<br>可空：False |
| `employees.highest_degree`<br>TEXT | 最高已取得学位<br>最高学位、取得的学位、硕士还是博士 | 当前最高已完成教育经历对应学位快照；未知/无学位/学士/硕士/博士 | 不是学历层级，不是博士后身份或在读资格；无学位与未知不同，历史查询需查教育经历。 | None<br>["学士", "硕士", "博士", "未知"]<br>可空：False |
| `employees.graduation_school_id`<br>INTEGER | 最高学历院校ID<br>人员基础档案最高学历院校ID、最高学历院校ID字段、employees.graduation_school_id | 当前最高已完成教育经历毕业院校标识 | 不是曾经就读过的所有学校；仅代表最高已完成教育经历对应的学校。 | None<br>[]<br>可空：True |
| `employees.major`<br>TEXT | 所学专业<br>人员基础档案所学专业、所学专业字段、employees.major | 所学专业；演示未开放按专业筛选 | 不是独立统计指标，也不能脱离人员基础档案的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>["计算机科学与技术", "人力资源管理"]<br>可空：True |
| `employees.graduation_date`<br>TEXT | 毕业日期<br>人员基础档案毕业日期、毕业日期字段、employees.graduation_date | 毕业日期；只有不晚于统计日的已完成经历参与查询 | 不是入学时间、预计毕业时间或证书核验时间；早于等于业务统计日才视为已完成。 | 日期<br>["2022-06-30"]<br>可空：True |
| `employees.education_mode`<br>TEXT | 最高学历学习形式<br>人员基础档案最高学历学习形式、最高学历学习形式字段、employees.education_mode | 当前最高教育经历学习形式快照；未知/全日制/非全日制 | 不是独立统计指标，也不能脱离人员基础档案的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>["全日制", "非全日制", "未知"]<br>可空：False |

### `employee_education` · 已完成教育经历

已完成教育经历；每人每段经历一行，历史分析按事件日取已完成最高学历

粒度：每人每段经历一行，历史分析按事件日取已完成最高学历。不表示：不是任意字段可以混连的宽表；连接必须遵守外键、人员权限与有效期，不能把一人多条事实当成员工人数。

| 字段唯一ID / 类型 | 名称与口语别名 | 表示什么 | 不表示什么 | 单位 / 示例值 / 可空 |
|---|---|---|---|---|
| `employee_education.id`<br>INTEGER | 记录主键<br>已完成教育经历记录主键、记录主键字段、employee_education.id | 已完成教育经历的内部记录主键；在本表内唯一，关联关系见外键，不能充当业务统计人数的独立口径。 | 不是员工工号，也不是姓名；仅在本表主键空间唯一，不可跨表直接比较数值。 | None<br>[]<br>可空：False |
| `employee_education.employee_id`<br>INTEGER | 员工内部ID<br>已完成教育经历员工内部ID、员工内部ID字段、employee_education.employee_id | 员工标识 | 不是对外员工工号，也不是职位或组织ID；必须关联employees.id，不能关联employees.employee_no。 | None<br>[]<br>可空：False |
| `employee_education.school_id`<br>INTEGER | 毕业院校ID<br>毕业院校、毕业学校、哪所学校毕业、母校 | 该段教育经历的毕业院校标识 | 不是学校文字名称，也不是员工主键；需要连接schools.id；同一员工可能多条学校经历。 | None<br>[]<br>可空：False |
| `employee_education.education_level`<br>TEXT | 教育经历学历<br>学历、本科硕士博士学历、教育层次 | 学历层级名称，与education_rank对应 | 不是学位证书，也不包含未毕业的在读经历；高中/专科无学位不等于教育背景缺失。 | None<br>["本科", "硕士研究生", "博士研究生"]<br>可空：False |
| `employee_education.education_rank`<br>INTEGER | 学历排序层级<br>已完成教育经历学历排序层级、学历排序层级字段、employee_education.education_rank | 学历排序：高中及以下1/专科2/本科3/硕士研究生4/博士研究生5 | 不是成绩、学校排名或员工评价分；只能用来比较学历层级，不可拿来计算教育质量平均分。 | None<br>[1, 2, 3, 4, 5]<br>可空：False |
| `employee_education.degree`<br>TEXT | 教育经历学位<br>学位、拿到什么学位、毕业时学位 | 已取得学位：无学位/学士/硕士/博士；不同于学历 | 不是学历、学校名或博士后；硕士学位精确匹配不会自动包括博士，除非问题明确改为硕士及以上学历。 | None<br>["学士", "硕士", "博士", "无学位"]<br>可空：False |
| `employee_education.major`<br>TEXT | 所学专业<br>已完成教育经历所学专业、所学专业字段、employee_education.major | 所学专业；演示未开放按专业筛选 | 不是独立统计指标，也不能脱离已完成教育经历的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>["计算机科学与技术", "人力资源管理"]<br>可空：False |
| `employee_education.start_date`<br>TEXT | 入学日期<br>已完成教育经历入学日期、入学日期字段、employee_education.start_date | 教育经历开始日期 | 不是独立统计指标，也不能脱离已完成教育经历的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | 日期<br>["2018-09-01"]<br>可空：False |
| `employee_education.graduation_date`<br>TEXT | 毕业日期<br>已完成教育经历毕业日期、毕业日期字段、employee_education.graduation_date | 毕业日期；只有不晚于统计日的已完成经历参与查询 | 不是入学时间、预计毕业时间或证书核验时间；早于等于业务统计日才视为已完成。 | 日期<br>["2022-06-30"]<br>可空：False |
| `employee_education.study_mode`<br>TEXT | 教育经历学习形式<br>已完成教育经历教育经历学习形式、教育经历学习形式字段、employee_education.study_mode | 该段教育经历学习形式：全日制/非全日制 | 不是独立统计指标，也不能脱离已完成教育经历的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>["全日制", "非全日制"]<br>可空：False |

### `employee_private` · 私人信息

私人信息；每名员工一行，全部SIM标记且不开放查询

粒度：每名员工一行，全部SIM标记且不开放查询。不表示：不是任意字段可以混连的宽表；连接必须遵守外键、人员权限与有效期，不能把一人多条事实当成员工人数。

| 字段唯一ID / 类型 | 名称与口语别名 | 表示什么 | 不表示什么 | 单位 / 示例值 / 可空 |
|---|---|---|---|---|
| `employee_private.employee_id`<br>INTEGER | 员工内部ID<br>私人信息员工内部ID、员工内部ID字段、employee_private.employee_id | 员工标识 | 不是对外员工工号，也不是职位或组织ID；必须关联employees.id，不能关联employees.employee_no。 | None<br>[]<br>可空：False |
| `employee_private.phone`<br>TEXT | 私人电话<br>私人信息私人电话、私人电话字段、employee_private.phone | SIM模拟电话标记 | 不是独立统计指标，也不能脱离私人信息的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `employee_private.identity_document`<br>TEXT | 证件号码<br>私人信息证件号码、证件号码字段、employee_private.identity_document | SIM模拟证件标记 | 不是独立统计指标，也不能脱离私人信息的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `employee_private.bank_account`<br>TEXT | 银行账号<br>私人信息银行账号、银行账号字段、employee_private.bank_account | SIM模拟银行账户标记 | 不是独立统计指标，也不能脱离私人信息的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |

### `assignments` · 任职历史

任职历史；每个人每段连续任职一行，左闭右开

粒度：每个人每段连续任职一行，左闭右开。不表示：不是任意字段可以混连的宽表；连接必须遵守外键、人员权限与有效期，不能把一人多条事实当成员工人数。

| 字段唯一ID / 类型 | 名称与口语别名 | 表示什么 | 不表示什么 | 单位 / 示例值 / 可空 |
|---|---|---|---|---|
| `assignments.id`<br>INTEGER | 记录主键<br>任职历史记录主键、记录主键字段、assignments.id | 任职历史的内部记录主键；在本表内唯一，关联关系见外键，不能充当业务统计人数的独立口径。 | 不是员工工号，也不是姓名；仅在本表主键空间唯一，不可跨表直接比较数值。 | None<br>[]<br>可空：False |
| `assignments.employee_id`<br>INTEGER | 员工内部ID<br>任职历史员工内部ID、员工内部ID字段、assignments.employee_id | 员工标识 | 不是对外员工工号，也不是职位或组织ID；必须关联employees.id，不能关联employees.employee_no。 | None<br>[]<br>可空：False |
| `assignments.department_id`<br>INTEGER | 任职组织ID<br>所在部门、归属组织、在哪个团队、部门ID | 任职或需求所属组织 | 不是直属主管ID；可能指公司、事业部、部门或团队节点，不能假定全部都是三级部门。 | None<br>[]<br>可空：False |
| `assignments.manager_id`<br>INTEGER | 直属上级员工ID<br>直属主管、直接领导、汇报给谁 | 直属上级员工标识 | 不是所有上级，也不是部门父节点；仅表达这一段任职的直属人员关系。 | None<br>[]<br>可空：True |
| `assignments.position_id`<br>INTEGER | 岗位ID<br>任职历史岗位ID、岗位ID字段、assignments.position_id | 岗位标识 | 不是独立统计指标，也不能脱离任职历史的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `assignments.grade_id`<br>INTEGER | 职级ID<br>任职历史职级ID、职级ID字段、assignments.grade_id | 职级标识 | 不是独立统计指标，也不能脱离任职历史的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `assignments.valid_from`<br>TEXT | 生效日期<br>任职历史生效日期、生效日期字段、assignments.valid_from | 生效日期，包含当天 | 不是员工入职日期；调岗会产生新的生效记录，开始当天包含在该段有效期内。 | 日期<br>["2026-07-01"]<br>可空：False |
| `assignments.valid_to`<br>TEXT | 失效日期<br>任职历史失效日期、失效日期字段、assignments.valid_to | 结束日期，不包含当天；空表示当前 | 不是离职事实日期；边界当天不属于旧记录，空值表示该段没有结束日期。 | 日期<br>["2026-07-01", null]<br>可空：True |

### `reporting_closure` · 当前管理关系闭包

当前管理关系闭包；每个祖先/后代对一行

粒度：每个祖先/后代对一行。不表示：不是任意字段可以混连的宽表；连接必须遵守外键、人员权限与有效期，不能把一人多条事实当成员工人数。

| 字段唯一ID / 类型 | 名称与口语别名 | 表示什么 | 不表示什么 | 单位 / 示例值 / 可空 |
|---|---|---|---|---|
| `reporting_closure.ancestor_id`<br>INTEGER | 上级员工ID<br>当前管理关系闭包上级员工ID、上级员工ID字段、reporting_closure.ancestor_id | 管理链祖先员工标识 | 不是独立统计指标，也不能脱离当前管理关系闭包的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `reporting_closure.descendant_id`<br>INTEGER | 下级员工ID<br>当前管理关系闭包下级员工ID、下级员工ID字段、reporting_closure.descendant_id | 管理链后代员工标识 | 不是独立统计指标，也不能脱离当前管理关系闭包的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `reporting_closure.depth`<br>INTEGER | 汇报链距离<br>直属或间接、下属层级、管理链几层 | 0本人/1直属/2及以上间接 | 不是组织树层级、职级或年龄；0为本人，1为直属，2及以上为间接下属。 | None<br>[0, 1, 2]<br>可空：False |

### `work_calendar` · 演示工作日历

演示工作日历；每天一行，未接正式节假日调休

粒度：每天一行，未接正式节假日调休。不表示：不是任意字段可以混连的宽表；连接必须遵守外键、人员权限与有效期，不能把一人多条事实当成员工人数。

| 字段唯一ID / 类型 | 名称与口语别名 | 表示什么 | 不表示什么 | 单位 / 示例值 / 可空 |
|---|---|---|---|---|
| `work_calendar.day`<br>TEXT | 业务发生日期<br>演示工作日历业务发生日期、业务发生日期字段、work_calendar.day | 业务日期YYYY-MM-DD | 不是独立统计指标，也不能脱离演示工作日历的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | 日期<br>["2026-09-11"]<br>可空：False |
| `work_calendar.is_workday`<br>INTEGER | 是否应出勤日<br>演示工作日历是否应出勤日、是否应出勤日字段、work_calendar.is_workday | 应工作日标记0/1 | 不是独立统计指标，也不能脱离演示工作日历的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[0, 1]<br>可空：False |
| `work_calendar.note`<br>TEXT | 备注与模拟日历说明<br>演示工作日历备注与模拟日历说明、备注与模拟日历说明字段、work_calendar.note | 备注与模拟日历说明 | 不是独立统计指标，也不能脱离演示工作日历的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |

### `shift_policies` · 班次政策

班次政策；每个政策版本一行

粒度：每个政策版本一行。不表示：不是任意字段可以混连的宽表；连接必须遵守外键、人员权限与有效期，不能把一人多条事实当成员工人数。

| 字段唯一ID / 类型 | 名称与口语别名 | 表示什么 | 不表示什么 | 单位 / 示例值 / 可空 |
|---|---|---|---|---|
| `shift_policies.id`<br>INTEGER | 记录主键<br>班次政策记录主键、记录主键字段、shift_policies.id | 班次政策的内部记录主键；在本表内唯一，关联关系见外键，不能充当业务统计人数的独立口径。 | 不是员工工号，也不是姓名；仅在本表主键空间唯一，不可跨表直接比较数值。 | None<br>[]<br>可空：False |
| `shift_policies.name`<br>TEXT | 名称<br>班次政策名称、名称字段、shift_policies.name | 班次政策的业务名称；用于人类可读展示和明确名称匹配，内部连接仍以ID为准。 | 不是独立统计指标，也不能脱离班次政策的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `shift_policies.earliest_in`<br>INTEGER | 弹性最早到岗<br>班次政策弹性最早到岗、弹性最早到岗字段、shift_policies.earliest_in | 弹性到岗起点；距午夜分钟 | 不是独立统计指标，也不能脱离班次政策的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | 分钟<br>[]<br>可空：False |
| `shift_policies.latest_in`<br>INTEGER | 弹性最晚到岗<br>班次政策弹性最晚到岗、弹性最晚到岗字段、shift_policies.latest_in | 迟到阈值；距午夜分钟 | 不是独立统计指标，也不能脱离班次政策的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | 分钟<br>[]<br>可空：False |
| `shift_policies.earliest_out`<br>INTEGER | 最早应离岗<br>班次政策最早应离岗、最早应离岗字段、shift_policies.earliest_out | 最早应离岗；距午夜分钟 | 不是独立统计指标，也不能脱离班次政策的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | 分钟<br>[]<br>可空：False |
| `shift_policies.required_work_minutes`<br>INTEGER | 要求净工作分钟<br>班次政策要求净工作分钟、要求净工作分钟字段、shift_policies.required_work_minutes | 要求净工作分钟 | 不是独立统计指标，也不能脱离班次政策的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | 分钟<br>[]<br>可空：False |
| `shift_policies.lunch_minutes`<br>INTEGER | 午休分钟<br>班次政策午休分钟、午休分钟字段、shift_policies.lunch_minutes | 午休分钟 | 不是独立统计指标，也不能脱离班次政策的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | 分钟<br>[60]<br>可空：False |
| `shift_policies.version`<br>TEXT | 定义版本<br>班次政策定义版本、定义版本字段、shift_policies.version | 定义版本 | 不是独立统计指标，也不能脱离班次政策的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |

### `attendance_daily` · 每日考勤事实

每日考勤事实；每人每个应工作日一行

粒度：每人每个应工作日一行。不表示：不是任意字段可以混连的宽表；连接必须遵守外键、人员权限与有效期，不能把一人多条事实当成员工人数。

| 字段唯一ID / 类型 | 名称与口语别名 | 表示什么 | 不表示什么 | 单位 / 示例值 / 可空 |
|---|---|---|---|---|
| `attendance_daily.id`<br>INTEGER | 记录主键<br>每日考勤事实记录主键、记录主键字段、attendance_daily.id | 每日考勤事实的内部记录主键；在本表内唯一，关联关系见外键，不能充当业务统计人数的独立口径。 | 不是员工工号，也不是姓名；仅在本表主键空间唯一，不可跨表直接比较数值。 | None<br>[]<br>可空：False |
| `attendance_daily.employee_id`<br>INTEGER | 员工内部ID<br>每日考勤事实员工内部ID、员工内部ID字段、attendance_daily.employee_id | 员工标识 | 不是对外员工工号，也不是职位或组织ID；必须关联employees.id，不能关联employees.employee_no。 | None<br>[]<br>可空：False |
| `attendance_daily.day`<br>TEXT | 业务发生日期<br>每日考勤事实业务发生日期、业务发生日期字段、attendance_daily.day | 业务日期YYYY-MM-DD | 不是独立统计指标，也不能脱离每日考勤事实的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | 日期<br>["2026-09-11"]<br>可空：False |
| `attendance_daily.shift_id`<br>INTEGER | 班次政策ID<br>每日考勤事实班次政策ID、班次政策ID字段、attendance_daily.shift_id | 班次政策标识 | 不是独立统计指标，也不能脱离每日考勤事实的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `attendance_daily.status`<br>TEXT | 记录业务状态<br>每日考勤事实记录业务状态、记录业务状态字段、attendance_daily.status | 应出勤日考勤结果：正常/远程/请假/缺勤/缺卡。正常或远程用于完成出勤；缺勤、缺卡属于异常。 | 不是独立统计指标，也不能脱离每日考勤事实的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>["正常", "远程", "请假", "缺勤", "缺卡"]<br>可空：False |
| `attendance_daily.check_in`<br>INTEGER | 上班打卡分钟<br>上班打卡、几点来的、到岗时间 | 到岗时刻；距午夜分钟，缺卡可空 | 不是小时数或字符串时刻；底层是距业务日午夜的分钟。没有打卡必须保留空值，不用0代替。 | 分钟<br>[480, 570, null]<br>可空：True |
| `attendance_daily.check_out`<br>INTEGER | 下班打卡分钟<br>下班打卡、几点走的、离岗时间 | 离岗时刻；距午夜分钟，缺卡可空 | 不是已批准加班结束时间；晚于18点不一定等于加班，缺卡时为空。 | 分钟<br>[1080, 1110, 1320, null]<br>可空：True |
| `attendance_daily.work_minutes`<br>INTEGER | 净在岗分钟<br>实际在岗分钟、扣休息后的工时、净工时 | 工作日完整打卡间隔减午休60分钟后的净在岗分钟；缺卡不产生完整工时样本。 | 不是合同工时、工资结算工时或加班审批工时；必须按所在表的休息扣除规则理解。 | 分钟<br>[480, 510]<br>可空：False |
| `attendance_daily.late_minutes`<br>INTEGER | 迟到分钟<br>每日考勤事实迟到分钟、迟到分钟字段、attendance_daily.late_minutes | 超过09:30的分钟数 | 不是当天是否异常的布尔值；大于0才计一次迟到人次，不能直接累加为迟到人数。 | 分钟<br>[0, 1, 15]<br>可空：False |
| `attendance_daily.early_minutes`<br>INTEGER | 早退分钟<br>每日考勤事实早退分钟、早退分钟字段、attendance_daily.early_minutes | 早于个人应离岗的分钟数 | 不是独立统计指标，也不能脱离每日考勤事实的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | 分钟<br>[0, 30]<br>可空：False |
| `attendance_daily.late_departure_minutes`<br>INTEGER | 晚离岗分钟<br>晚走分钟、晚下班多久、超出应离岗时间 | 超过个人应离岗的分钟数，不等于批准加班 | 不是已批准加班，也不直接代表法定加班；需要与个人应离岗时刻比较，不能统一只减18:00。 | 分钟<br>[0, 60]<br>可空：False |

### `leave_requests` · 整日请假申请

整日请假申请；每人每日最多一行

粒度：每人每日最多一行。不表示：不是任意字段可以混连的宽表；连接必须遵守外键、人员权限与有效期，不能把一人多条事实当成员工人数。

| 字段唯一ID / 类型 | 名称与口语别名 | 表示什么 | 不表示什么 | 单位 / 示例值 / 可空 |
|---|---|---|---|---|
| `leave_requests.id`<br>INTEGER | 记录主键<br>整日请假申请记录主键、记录主键字段、leave_requests.id | 整日请假申请的内部记录主键；在本表内唯一，关联关系见外键，不能充当业务统计人数的独立口径。 | 不是员工工号，也不是姓名；仅在本表主键空间唯一，不可跨表直接比较数值。 | None<br>[]<br>可空：False |
| `leave_requests.employee_id`<br>INTEGER | 员工内部ID<br>整日请假申请员工内部ID、员工内部ID字段、leave_requests.employee_id | 员工标识 | 不是对外员工工号，也不是职位或组织ID；必须关联employees.id，不能关联employees.employee_no。 | None<br>[]<br>可空：False |
| `leave_requests.day`<br>TEXT | 业务发生日期<br>整日请假申请业务发生日期、业务发生日期字段、leave_requests.day | 业务日期YYYY-MM-DD | 不是独立统计指标，也不能脱离整日请假申请的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | 日期<br>["2026-09-11"]<br>可空：False |
| `leave_requests.leave_type`<br>TEXT | 请假类别<br>整日请假申请请假类别、请假类别字段、leave_requests.leave_type | 模拟假别 | 不是独立统计指标，也不能脱离整日请假申请的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `leave_requests.days`<br>REAL | 请假天数<br>整日请假申请请假天数、请假天数字段、leave_requests.days | 请假天数；当前仅整日 | 不是独立统计指标，也不能脱离整日请假申请的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[1.0]<br>可空：False |
| `leave_requests.approval_status`<br>TEXT | 审批状态<br>请假批了吗、请假审批结果、休假审核状态 | 已批准/待审批/已拒绝 | 不是员工在离职状态，也不是打卡状态；待审批和已拒绝都不能计入已批准指标。 | None<br>["已批准", "待审批", "已拒绝"]<br>可空：False |
| `leave_requests.approver_id`<br>INTEGER | 审批人ID<br>整日请假申请审批人ID、审批人ID字段、leave_requests.approver_id | 审批人员工标识 | 不是独立统计指标，也不能脱离整日请假申请的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：True |

### `overtime_requests` · 加班申请

加班申请；每人每日最多一行，与晚离岗分开

粒度：每人每日最多一行，与晚离岗分开。不表示：不是任意字段可以混连的宽表；连接必须遵守外键、人员权限与有效期，不能把一人多条事实当成员工人数。

| 字段唯一ID / 类型 | 名称与口语别名 | 表示什么 | 不表示什么 | 单位 / 示例值 / 可空 |
|---|---|---|---|---|
| `overtime_requests.id`<br>INTEGER | 记录主键<br>加班申请记录主键、记录主键字段、overtime_requests.id | 加班申请的内部记录主键；在本表内唯一，关联关系见外键，不能充当业务统计人数的独立口径。 | 不是员工工号，也不是姓名；仅在本表主键空间唯一，不可跨表直接比较数值。 | None<br>[]<br>可空：False |
| `overtime_requests.employee_id`<br>INTEGER | 员工内部ID<br>加班申请员工内部ID、员工内部ID字段、overtime_requests.employee_id | 员工标识 | 不是对外员工工号，也不是职位或组织ID；必须关联employees.id，不能关联employees.employee_no。 | None<br>[]<br>可空：False |
| `overtime_requests.day`<br>TEXT | 业务发生日期<br>加班申请业务发生日期、业务发生日期字段、overtime_requests.day | 业务日期YYYY-MM-DD | 不是独立统计指标，也不能脱离加班申请的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | 日期<br>["2026-09-11"]<br>可空：False |
| `overtime_requests.minutes`<br>INTEGER | 申请加班分钟<br>申请加班时长、审批单上的分钟、申报加班分钟 | 申请加班分钟 | 不是小时；申请时长不等于实际在岗或已批准时长，必须结合approval_status和日期过滤。 | 分钟<br>[60, 120]<br>可空：False |
| `overtime_requests.day_type`<br>TEXT | 加班日期类别<br>加班申请加班日期类别、加班日期类别字段、overtime_requests.day_type | 加班日期类型：工作日/周末；与演示日历一致 | 不是独立统计指标，也不能脱离加班申请的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>["工作日", "周末"]<br>可空：False |
| `overtime_requests.approval_status`<br>TEXT | 审批状态<br>加班批了吗、加班审核状态、加班审批结果 | 已批准/待审批/已拒绝 | 不是员工在离职状态，也不是打卡状态；待审批和已拒绝都不能计入已批准指标。 | None<br>["已批准", "待审批", "已拒绝"]<br>可空：False |
| `overtime_requests.approver_id`<br>INTEGER | 审批人ID<br>加班申请审批人ID、审批人ID字段、overtime_requests.approver_id | 审批人员工标识 | 不是独立统计指标，也不能脱离加班申请的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：True |

### `compensation` · 基本月薪有效期记录

基本月薪有效期记录；受限汇总来源

粒度：受限汇总来源。不表示：不是任意字段可以混连的宽表；连接必须遵守外键、人员权限与有效期，不能把一人多条事实当成员工人数。

| 字段唯一ID / 类型 | 名称与口语别名 | 表示什么 | 不表示什么 | 单位 / 示例值 / 可空 |
|---|---|---|---|---|
| `compensation.id`<br>INTEGER | 记录主键<br>基本月薪有效期记录记录主键、记录主键字段、compensation.id | 基本月薪有效期记录的内部记录主键；在本表内唯一，关联关系见外键，不能充当业务统计人数的独立口径。 | 不是员工工号，也不是姓名；仅在本表主键空间唯一，不可跨表直接比较数值。 | None<br>[]<br>可空：False |
| `compensation.employee_id`<br>INTEGER | 员工内部ID<br>基本月薪有效期记录员工内部ID、员工内部ID字段、compensation.employee_id | 员工标识 | 不是对外员工工号，也不是职位或组织ID；必须关联employees.id，不能关联employees.employee_no。 | None<br>[]<br>可空：False |
| `compensation.valid_from`<br>TEXT | 生效日期<br>基本月薪有效期记录生效日期、生效日期字段、compensation.valid_from | 生效日期，包含当天 | 不是员工入职日期；调岗会产生新的生效记录，开始当天包含在该段有效期内。 | 日期<br>[]<br>可空：False |
| `compensation.valid_to`<br>TEXT | 失效日期<br>基本月薪有效期记录失效日期、失效日期字段、compensation.valid_to | 结束日期，不包含当天；空表示当前 | 不是离职事实日期；边界当天不属于旧记录，空值表示该段没有结束日期。 | 日期<br>[]<br>可空：True |
| `compensation.monthly_base`<br>INTEGER | 基本月薪<br>基本工资、月基本薪资、税前固定基本月薪 | 模拟基本月薪金额，元 | 不是实发工资、到手收入或薪酬总包，不包含奖金、社保、公积金、补贴；禁止返回个人金额。 | 元/月<br>[]<br>可空：False |
| `compensation.currency`<br>TEXT | 币种<br>基本月薪有效期记录币种、币种字段、compensation.currency | 币种CNY | 不是独立统计指标，也不能脱离基本月薪有效期记录的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |

### `performance_reviews` · 绩效评价

绩效评价；每人每周期一行，尚未开放查询

粒度：每人每周期一行，尚未开放查询。不表示：不是任意字段可以混连的宽表；连接必须遵守外键、人员权限与有效期，不能把一人多条事实当成员工人数。

| 字段唯一ID / 类型 | 名称与口语别名 | 表示什么 | 不表示什么 | 单位 / 示例值 / 可空 |
|---|---|---|---|---|
| `performance_reviews.id`<br>INTEGER | 记录主键<br>绩效评价记录主键、记录主键字段、performance_reviews.id | 绩效评价的内部记录主键；在本表内唯一，关联关系见外键，不能充当业务统计人数的独立口径。 | 不是员工工号，也不是姓名；仅在本表主键空间唯一，不可跨表直接比较数值。 | None<br>[]<br>可空：False |
| `performance_reviews.employee_id`<br>INTEGER | 员工内部ID<br>绩效评价员工内部ID、员工内部ID字段、performance_reviews.employee_id | 员工标识 | 不是对外员工工号，也不是职位或组织ID；必须关联employees.id，不能关联employees.employee_no。 | None<br>[]<br>可空：False |
| `performance_reviews.period`<br>TEXT | 绩效周期<br>绩效评价绩效周期、绩效周期字段、performance_reviews.period | 评价周期 | 不是独立统计指标，也不能脱离绩效评价的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `performance_reviews.rating`<br>TEXT | 绩效等级<br>绩效评价绩效等级、绩效等级字段、performance_reviews.rating | 卓越/优秀/达标/待提升 | 不是独立统计指标，也不能脱离绩效评价的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `performance_reviews.reviewer_id`<br>INTEGER | 评价人ID<br>绩效评价评价人ID、评价人ID字段、performance_reviews.reviewer_id | 评价人员工标识 | 不是独立统计指标，也不能脱离绩效评价的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：True |

### `training_courses` · 培训课程

培训课程；每门课一行，尚未开放查询

粒度：每门课一行，尚未开放查询。不表示：不是任意字段可以混连的宽表；连接必须遵守外键、人员权限与有效期，不能把一人多条事实当成员工人数。

| 字段唯一ID / 类型 | 名称与口语别名 | 表示什么 | 不表示什么 | 单位 / 示例值 / 可空 |
|---|---|---|---|---|
| `training_courses.id`<br>INTEGER | 记录主键<br>培训课程记录主键、记录主键字段、training_courses.id | 培训课程的内部记录主键；在本表内唯一，关联关系见外键，不能充当业务统计人数的独立口径。 | 不是员工工号，也不是姓名；仅在本表主键空间唯一，不可跨表直接比较数值。 | None<br>[]<br>可空：False |
| `training_courses.name`<br>TEXT | 名称<br>培训课程名称、名称字段、training_courses.name | 培训课程的业务名称；用于人类可读展示和明确名称匹配，内部连接仍以ID为准。 | 不是独立统计指标，也不能脱离培训课程的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `training_courses.hours`<br>REAL | 培训学时<br>培训课程培训学时、培训学时字段、training_courses.hours | 课程时长，小时 | 不是独立统计指标，也不能脱离培训课程的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |

### `training_enrollments` · 培训参加记录

培训参加记录；每人每课程一行，尚未开放查询

粒度：每人每课程一行，尚未开放查询。不表示：不是任意字段可以混连的宽表；连接必须遵守外键、人员权限与有效期，不能把一人多条事实当成员工人数。

| 字段唯一ID / 类型 | 名称与口语别名 | 表示什么 | 不表示什么 | 单位 / 示例值 / 可空 |
|---|---|---|---|---|
| `training_enrollments.employee_id`<br>INTEGER | 员工内部ID<br>培训参加记录员工内部ID、员工内部ID字段、training_enrollments.employee_id | 员工标识 | 不是对外员工工号，也不是职位或组织ID；必须关联employees.id，不能关联employees.employee_no。 | None<br>[]<br>可空：False |
| `training_enrollments.course_id`<br>INTEGER | 培训课程ID<br>培训参加记录培训课程ID、培训课程ID字段、training_enrollments.course_id | 课程标识 | 不是独立统计指标，也不能脱离培训参加记录的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `training_enrollments.status`<br>TEXT | 记录业务状态<br>培训参加记录记录业务状态、记录业务状态字段、training_enrollments.status | 业务状态；取值由对应表约束与生成器定义 | 不是独立统计指标，也不能脱离培训参加记录的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `training_enrollments.completed_at`<br>TEXT | 培训完成日期<br>培训参加记录培训完成日期、培训完成日期字段、training_enrollments.completed_at | 完成日期，可空 | 不是独立统计指标，也不能脱离培训参加记录的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：True |

### `recruitment_requisitions` · 招聘需求

招聘需求；每个需求一行，尚未开放查询

粒度：每个需求一行，尚未开放查询。不表示：不是任意字段可以混连的宽表；连接必须遵守外键、人员权限与有效期，不能把一人多条事实当成员工人数。

| 字段唯一ID / 类型 | 名称与口语别名 | 表示什么 | 不表示什么 | 单位 / 示例值 / 可空 |
|---|---|---|---|---|
| `recruitment_requisitions.id`<br>INTEGER | 记录主键<br>招聘需求记录主键、记录主键字段、recruitment_requisitions.id | 招聘需求的内部记录主键；在本表内唯一，关联关系见外键，不能充当业务统计人数的独立口径。 | 不是员工工号，也不是姓名；仅在本表主键空间唯一，不可跨表直接比较数值。 | None<br>[]<br>可空：False |
| `recruitment_requisitions.department_id`<br>INTEGER | 任职组织ID<br>招聘需求任职组织ID、任职组织ID字段、recruitment_requisitions.department_id | 任职或需求所属组织 | 不是直属主管ID；可能指公司、事业部、部门或团队节点，不能假定全部都是三级部门。 | None<br>[]<br>可空：False |
| `recruitment_requisitions.position_id`<br>INTEGER | 岗位ID<br>招聘需求岗位ID、岗位ID字段、recruitment_requisitions.position_id | 岗位标识 | 不是独立统计指标，也不能脱离招聘需求的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `recruitment_requisitions.openings`<br>INTEGER | 招聘编制名额<br>招聘需求招聘编制名额、招聘编制名额字段、recruitment_requisitions.openings | 招聘名额 | 不是独立统计指标，也不能脱离招聘需求的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `recruitment_requisitions.status`<br>TEXT | 记录业务状态<br>招聘需求记录业务状态、记录业务状态字段、recruitment_requisitions.status | 业务状态；取值由对应表约束与生成器定义 | 不是独立统计指标，也不能脱离招聘需求的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `recruitment_requisitions.opened_at`<br>TEXT | 招聘需求创建日<br>招聘需求招聘需求创建日、招聘需求创建日字段、recruitment_requisitions.opened_at | 需求创建日期 | 不是独立统计指标，也不能脱离招聘需求的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |

### `overtime_attendance` · 独立周末打卡事实

独立周末打卡事实；每人每周末出勤日一行，核验申请时长

粒度：每人每周末出勤日一行，核验申请时长。不表示：不是任意字段可以混连的宽表；连接必须遵守外键、人员权限与有效期，不能把一人多条事实当成员工人数。

| 字段唯一ID / 类型 | 名称与口语别名 | 表示什么 | 不表示什么 | 单位 / 示例值 / 可空 |
|---|---|---|---|---|
| `overtime_attendance.id`<br>INTEGER | 记录主键<br>独立周末打卡事实记录主键、记录主键字段、overtime_attendance.id | 独立周末打卡事实的内部记录主键；在本表内唯一，关联关系见外键，不能充当业务统计人数的独立口径。 | 不是员工工号，也不是姓名；仅在本表主键空间唯一，不可跨表直接比较数值。 | None<br>[]<br>可空：False |
| `overtime_attendance.employee_id`<br>INTEGER | 员工内部ID<br>独立周末打卡事实员工内部ID、员工内部ID字段、overtime_attendance.employee_id | 员工标识 | 不是对外员工工号，也不是职位或组织ID；必须关联employees.id，不能关联employees.employee_no。 | None<br>[]<br>可空：False |
| `overtime_attendance.day`<br>TEXT | 业务发生日期<br>独立周末打卡事实业务发生日期、业务发生日期字段、overtime_attendance.day | 业务日期YYYY-MM-DD | 不是独立统计指标，也不能脱离独立周末打卡事实的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | 日期<br>["2026-09-11"]<br>可空：False |
| `overtime_attendance.check_in`<br>INTEGER | 上班打卡分钟<br>独立周末打卡事实上班打卡分钟、上班打卡分钟字段、overtime_attendance.check_in | 到岗时刻；距午夜分钟，缺卡可空 | 不是小时数或字符串时刻；底层是距业务日午夜的分钟。没有打卡必须保留空值，不用0代替。 | 分钟<br>[480, 570, null]<br>可空：False |
| `overtime_attendance.check_out`<br>INTEGER | 下班打卡分钟<br>独立周末打卡事实下班打卡分钟、下班打卡分钟字段、overtime_attendance.check_out | 离岗时刻；距午夜分钟，缺卡可空 | 不是已批准加班结束时间；晚于18点不一定等于加班，缺卡时为空。 | 分钟<br>[1080, 1110, 1320, null]<br>可空：False |
| `overtime_attendance.break_minutes`<br>INTEGER | 休息分钟<br>独立周末打卡事实休息分钟、休息分钟字段、overtime_attendance.break_minutes | 周末打卡区间内扣除的休息分钟 | 不是独立统计指标，也不能脱离独立周末打卡事实的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | 分钟<br>[0, 60]<br>可空：False |
| `overtime_attendance.work_minutes`<br>INTEGER | 净在岗分钟<br>独立周末打卡事实净在岗分钟、净在岗分钟字段、overtime_attendance.work_minutes | 周末打卡净在岗分钟=check_out-check_in-break_minutes；独立于工作日午休政策，用于核对周末加班申请上限。 | 不是合同工时、工资结算工时或加班审批工时；必须按所在表的休息扣除规则理解。 | 分钟<br>[480, 510]<br>可空：False |

### `principals` · 演示主体及授权

演示主体及授权；每个演示身份一行

粒度：每个演示身份一行。不表示：不是任意字段可以混连的宽表；连接必须遵守外键、人员权限与有效期，不能把一人多条事实当成员工人数。

| 字段唯一ID / 类型 | 名称与口语别名 | 表示什么 | 不表示什么 | 单位 / 示例值 / 可空 |
|---|---|---|---|---|
| `principals.id`<br>TEXT | 记录主键<br>演示主体及授权记录主键、记录主键字段、principals.id | 演示主体及授权的内部记录主键；在本表内唯一，关联关系见外键，不能充当业务统计人数的独立口径。 | 不是员工工号，也不是姓名；仅在本表主键空间唯一，不可跨表直接比较数值。 | None<br>[]<br>可空：False |
| `principals.employee_id`<br>INTEGER | 员工内部ID<br>演示主体及授权员工内部ID、员工内部ID字段、principals.employee_id | 员工标识 | 不是对外员工工号，也不是职位或组织ID；必须关联employees.id，不能关联employees.employee_no。 | None<br>[]<br>可空：False |
| `principals.role`<br>TEXT | 角色类型<br>演示主体及授权角色类型、角色类型字段、principals.role | 角色类型 | 不是独立统计指标，也不能脱离演示主体及授权的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `principals.label`<br>TEXT | 身份显示名称<br>演示主体及授权身份显示名称、身份显示名称字段、principals.label | 身份显示名称 | 不是独立统计指标，也不能脱离演示主体及授权的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `principals.title`<br>TEXT | 显示标题<br>演示主体及授权显示标题、显示标题字段、principals.title | 显示标题 | 不是独立统计指标，也不能脱离演示主体及授权的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `principals.scope_mode`<br>TEXT | reports/organization/self<br>演示主体及授权reports/organization/self、reports/organization/self字段、principals.scope_mode | reports/organization/self | 不是独立统计指标，也不能脱离演示主体及授权的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `principals.scope_root`<br>INTEGER | 授权根：员工或组织ID，取决于scope_mode<br>演示主体及授权授权根：员工或组织ID，取决于scope_mode、授权根：员工或组织ID，取决于scope_mode字段、principals.scope_root | 授权根：员工或组织ID，取决于scope_mode | 不是独立统计指标，也不能脱离演示主体及授权的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `principals.salary_aggregate`<br>INTEGER | 薪酬受限聚合能力0/1<br>演示主体及授权薪酬受限聚合能力0/1、薪酬受限聚合能力0/1字段、principals.salary_aggregate | 薪酬受限聚合能力0/1 | 不是独立统计指标，也不能脱离演示主体及授权的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `principals.can_export`<br>INTEGER | 导出能力0/1，仍受指标和范围限制<br>演示主体及授权导出能力0/1，仍受指标和范围限制、导出能力0/1，仍受指标和范围限制字段、principals.can_export | 导出能力0/1，仍受指标和范围限制 | 不是独立统计指标，也不能脱离演示主体及授权的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `principals.enabled`<br>INTEGER | 账号启用0/1<br>演示主体及授权账号启用0/1、账号启用0/1字段、principals.enabled | 账号启用0/1 | 不是独立统计指标，也不能脱离演示主体及授权的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `principals.policy_version`<br>INTEGER | 权限策略版本<br>演示主体及授权权限策略版本、权限策略版本字段、principals.policy_version | 权限策略版本 | 不是独立统计指标，也不能脱离演示主体及授权的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |

### `sessions` · 会话

会话；仅保存令牌摘要，不保存原令牌

粒度：仅保存令牌摘要，不保存原令牌。不表示：不是任意字段可以混连的宽表；连接必须遵守外键、人员权限与有效期，不能把一人多条事实当成员工人数。

| 字段唯一ID / 类型 | 名称与口语别名 | 表示什么 | 不表示什么 | 单位 / 示例值 / 可空 |
|---|---|---|---|---|
| `sessions.token_hash`<br>TEXT | 会话令牌SHA-256摘要<br>会话会话令牌SHA-256摘要、会话令牌SHA-256摘要字段、sessions.token_hash | 会话令牌SHA-256摘要 | 不是独立统计指标，也不能脱离会话的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `sessions.principal_id`<br>TEXT | 应用身份标识<br>会话应用身份标识、应用身份标识字段、sessions.principal_id | 应用身份标识 | 不是独立统计指标，也不能脱离会话的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `sessions.csrf`<br>TEXT | 会话CSRF校验值<br>会话会话CSRF校验值、会话CSRF校验值字段、sessions.csrf | 会话CSRF校验值 | 不是独立统计指标，也不能脱离会话的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `sessions.expires_at`<br>REAL | 到期Unix时间戳秒<br>会话到期Unix时间戳秒、到期Unix时间戳秒字段、sessions.expires_at | 到期Unix时间戳秒 | 不是独立统计指标，也不能脱离会话的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |

### `metrics` · 已发布指标目录

已发布指标目录；每个指标一行JSON定义

粒度：每个指标一行JSON定义。不表示：不是任意字段可以混连的宽表；连接必须遵守外键、人员权限与有效期，不能把一人多条事实当成员工人数。

| 字段唯一ID / 类型 | 名称与口语别名 | 表示什么 | 不表示什么 | 单位 / 示例值 / 可空 |
|---|---|---|---|---|
| `metrics.id`<br>TEXT | 记录主键<br>已发布指标目录记录主键、记录主键字段、metrics.id | 已发布指标目录的内部记录主键；在本表内唯一，关联关系见外键，不能充当业务统计人数的独立口径。 | 不是员工工号，也不是姓名；仅在本表主键空间唯一，不可跨表直接比较数值。 | None<br>[]<br>可空：False |
| `metrics.definition`<br>TEXT | 指标JSON定义<br>已发布指标目录指标JSON定义、指标JSON定义字段、metrics.definition | 指标JSON定义 | 不是独立统计指标，也不能脱离已发布指标目录的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `metrics.version`<br>TEXT | 定义版本<br>已发布指标目录定义版本、定义版本字段、metrics.version | 定义版本 | 不是独立统计指标，也不能脱离已发布指标目录的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |

### `metric_search` · 由指标目录派生的FTS5 trigram检索索引，可重建

由指标目录派生的FTS5 trigram检索索引，可重建

粒度：由指标目录派生的FTS5 trigram检索索引，可重建。不表示：不是任意字段可以混连的宽表；连接必须遵守外键、人员权限与有效期，不能把一人多条事实当成员工人数。

| 字段唯一ID / 类型 | 名称与口语别名 | 表示什么 | 不表示什么 | 单位 / 示例值 / 可空 |
|---|---|---|---|---|
| `metric_search.id`<br>FTS TEXT | 记录主键<br>由指标目录派生的FTS5 trigram检索索引，可重建记录主键、记录主键字段、metric_search.id | 由指标目录派生的FTS5 trigram检索索引，可重建的内部记录主键；在本表内唯一，关联关系见外键，不能充当业务统计人数的独立口径。 | 不是员工工号，也不是姓名；仅在本表主键空间唯一，不可跨表直接比较数值。 | None<br>[]<br>可空：True |
| `metric_search.content`<br>FTS TEXT | 派生检索文本<br>由指标目录派生的FTS5 trigram检索索引，可重建派生检索文本、派生检索文本字段、metric_search.content | 派生检索文本 | 不是独立统计指标，也不能脱离由指标目录派生的FTS5 trigram检索索引，可重建的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：True |

### `dashboards` · 私人看板

私人看板；存查询计划，不持久复制结果

粒度：存查询计划，不持久复制结果。不表示：不是任意字段可以混连的宽表；连接必须遵守外键、人员权限与有效期，不能把一人多条事实当成员工人数。

| 字段唯一ID / 类型 | 名称与口语别名 | 表示什么 | 不表示什么 | 单位 / 示例值 / 可空 |
|---|---|---|---|---|
| `dashboards.id`<br>TEXT | 记录主键<br>私人看板记录主键、记录主键字段、dashboards.id | 私人看板的内部记录主键；在本表内唯一，关联关系见外键，不能充当业务统计人数的独立口径。 | 不是员工工号，也不是姓名；仅在本表主键空间唯一，不可跨表直接比较数值。 | None<br>[]<br>可空：False |
| `dashboards.owner_id`<br>TEXT | 记录所属身份<br>私人看板记录所属身份、记录所属身份字段、dashboards.owner_id | 记录所属身份 | 不是独立统计指标，也不能脱离私人看板的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `dashboards.title`<br>TEXT | 显示标题<br>私人看板显示标题、显示标题字段、dashboards.title | 显示标题 | 不是独立统计指标，也不能脱离私人看板的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `dashboards.plan`<br>TEXT | 严格类型查询计划JSON<br>私人看板严格类型查询计划JSON、严格类型查询计划JSON字段、dashboards.plan | 严格类型查询计划JSON | 不是独立统计指标，也不能脱离私人看板的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `dashboards.catalog_version`<br>TEXT | 指标目录版本<br>私人看板指标目录版本、指标目录版本字段、dashboards.catalog_version | 指标目录版本 | 不是独立统计指标，也不能脱离私人看板的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `dashboards.created_at`<br>TEXT | 记录创建时间ISO格式<br>私人看板记录创建时间ISO格式、记录创建时间ISO格式字段、dashboards.created_at | 记录创建时间ISO格式 | 不是独立统计指标，也不能脱离私人看板的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |

### `audit_events` · 应用审计事件

应用审计事件；不包含业务结果或个人证件

粒度：不包含业务结果或个人证件。不表示：不是任意字段可以混连的宽表；连接必须遵守外键、人员权限与有效期，不能把一人多条事实当成员工人数。

| 字段唯一ID / 类型 | 名称与口语别名 | 表示什么 | 不表示什么 | 单位 / 示例值 / 可空 |
|---|---|---|---|---|
| `audit_events.id`<br>TEXT | 记录主键<br>应用审计事件记录主键、记录主键字段、audit_events.id | 应用审计事件的内部记录主键；在本表内唯一，关联关系见外键，不能充当业务统计人数的独立口径。 | 不是员工工号，也不是姓名；仅在本表主键空间唯一，不可跨表直接比较数值。 | None<br>[]<br>可空：False |
| `audit_events.principal_id`<br>TEXT | 应用身份标识<br>应用审计事件应用身份标识、应用身份标识字段、audit_events.principal_id | 应用身份标识 | 不是独立统计指标，也不能脱离应用审计事件的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `audit_events.action`<br>TEXT | 操作名称<br>应用审计事件操作名称、操作名称字段、audit_events.action | 操作名称 | 不是独立统计指标，也不能脱离应用审计事件的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `audit_events.outcome`<br>TEXT | 执行或授权结果<br>应用审计事件执行或授权结果、执行或授权结果字段、audit_events.outcome | 执行或授权结果 | 不是独立统计指标，也不能脱离应用审计事件的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `audit_events.metric_id`<br>TEXT | 指标标识<br>应用审计事件指标标识、指标标识字段、audit_events.metric_id | 指标标识 | 不是独立统计指标，也不能脱离应用审计事件的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：True |
| `audit_events.scope_count`<br>INTEGER | 该次授权候选人数（不等于在职人数）<br>应用审计事件该次授权候选人数（不等于在职人数）、该次授权候选人数（不等于在职人数）字段、audit_events.scope_count | 该次授权候选人数（不等于在职人数） | 不是独立统计指标，也不能脱离应用审计事件的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：True |
| `audit_events.policy_version`<br>TEXT | 权限策略版本<br>应用审计事件权限策略版本、权限策略版本字段、audit_events.policy_version | 权限策略版本 | 不是独立统计指标，也不能脱离应用审计事件的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `audit_events.duration_ms`<br>REAL | 操作时长毫秒<br>应用审计事件操作时长毫秒、操作时长毫秒字段、audit_events.duration_ms | 操作时长毫秒 | 不是独立统计指标，也不能脱离应用审计事件的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `audit_events.created_at`<br>TEXT | 记录创建时间ISO格式<br>应用审计事件记录创建时间ISO格式、记录创建时间ISO格式字段、audit_events.created_at | 记录创建时间ISO格式 | 不是独立统计指标，也不能脱离应用审计事件的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |

### `conversations` · 最小对话记录

最小对话记录；用于同一身份的前次计划继承

粒度：用于同一身份的前次计划继承。不表示：不是任意字段可以混连的宽表；连接必须遵守外键、人员权限与有效期，不能把一人多条事实当成员工人数。

| 字段唯一ID / 类型 | 名称与口语别名 | 表示什么 | 不表示什么 | 单位 / 示例值 / 可空 |
|---|---|---|---|---|
| `conversations.id`<br>TEXT | 记录主键<br>最小对话记录记录主键、记录主键字段、conversations.id | 最小对话记录的内部记录主键；在本表内唯一，关联关系见外键，不能充当业务统计人数的独立口径。 | 不是员工工号，也不是姓名；仅在本表主键空间唯一，不可跨表直接比较数值。 | None<br>[]<br>可空：False |
| `conversations.principal_id`<br>TEXT | 应用身份标识<br>最小对话记录应用身份标识、应用身份标识字段、conversations.principal_id | 应用身份标识 | 不是独立统计指标，也不能脱离最小对话记录的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `conversations.question`<br>TEXT | 用户问题<br>最小对话记录用户问题、用户问题字段、conversations.question | 用户问题；生产需制定脱敏及留存策略 | 不是独立统计指标，也不能脱离最小对话记录的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `conversations.plan`<br>TEXT | 严格类型查询计划JSON<br>最小对话记录严格类型查询计划JSON、严格类型查询计划JSON字段、conversations.plan | 严格类型查询计划JSON | 不是独立统计指标，也不能脱离最小对话记录的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：True |
| `conversations.outcome`<br>TEXT | 执行或授权结果<br>最小对话记录执行或授权结果、执行或授权结果字段、conversations.outcome | 执行或授权结果 | 不是独立统计指标，也不能脱离最小对话记录的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `conversations.created_at`<br>TEXT | 记录创建时间ISO格式<br>最小对话记录记录创建时间ISO格式、记录创建时间ISO格式字段、conversations.created_at | 记录创建时间ISO格式 | 不是独立统计指标，也不能脱离最小对话记录的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |

### `debug_runs` · 逐节点调试记录

逐节点调试记录；每次自然语言查询一行，按身份与授权快照隔离，最多保留50次

粒度：每次自然语言查询一行，按身份与授权快照隔离，最多保留50次。不表示：不是任意字段可以混连的宽表；连接必须遵守外键、人员权限与有效期，不能把一人多条事实当成员工人数。

| 字段唯一ID / 类型 | 名称与口语别名 | 表示什么 | 不表示什么 | 单位 / 示例值 / 可空 |
|---|---|---|---|---|
| `debug_runs.id`<br>TEXT | 记录主键<br>逐节点调试记录记录主键、记录主键字段、debug_runs.id | 逐节点调试记录的内部记录主键；在本表内唯一，关联关系见外键，不能充当业务统计人数的独立口径。 | 不是员工工号，也不是姓名；仅在本表主键空间唯一，不可跨表直接比较数值。 | None<br>[]<br>可空：False |
| `debug_runs.owner_id`<br>TEXT | 记录所属身份<br>逐节点调试记录记录所属身份、记录所属身份字段、debug_runs.owner_id | 记录所属身份 | 不是独立统计指标，也不能脱离逐节点调试记录的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `debug_runs.grant_fingerprint`<br>TEXT | 身份能力、授权人员集合及策略版本的SHA-256指纹<br>逐节点调试记录身份能力、授权人员集合及策略版本的SHA-256指纹、身份能力、授权人员集合及策略版本的SHA-256指纹字段、debug_runs.grant_fingerprint | 身份能力、授权人员集合及策略版本的SHA-256指纹；读取时重新核验 | 不是独立统计指标，也不能脱离逐节点调试记录的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `debug_runs.question`<br>TEXT | 用户问题<br>逐节点调试记录用户问题、用户问题字段、debug_runs.question | 用户问题；生产需制定脱敏及留存策略 | 不是独立统计指标，也不能脱离逐节点调试记录的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `debug_runs.status`<br>TEXT | 记录业务状态<br>逐节点调试记录记录业务状态、记录业务状态字段、debug_runs.status | 业务状态；取值由对应表约束与生成器定义 | 不是独立统计指标，也不能脱离逐节点调试记录的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `debug_runs.started_at`<br>TEXT | 执行开始时间UTC ISO格式<br>逐节点调试记录执行开始时间UTC ISO格式、执行开始时间UTC ISO格式字段、debug_runs.started_at | 执行开始时间UTC ISO格式 | 不是独立统计指标，也不能脱离逐节点调试记录的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `debug_runs.finished_at`<br>TEXT | 执行结束时间UTC ISO格式<br>逐节点调试记录执行结束时间UTC ISO格式、执行结束时间UTC ISO格式字段、debug_runs.finished_at | 执行结束时间UTC ISO格式；运行中为空 | 不是独立统计指标，也不能脱离逐节点调试记录的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：True |
| `debug_runs.duration_ms`<br>REAL | 操作时长毫秒<br>逐节点调试记录操作时长毫秒、操作时长毫秒字段、debug_runs.duration_ms | 操作时长毫秒 | 不是独立统计指标，也不能脱离逐节点调试记录的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |
| `debug_runs.payload`<br>TEXT | 已脱敏的逐节点输入、输出、耗时、错误及最终响应JSON<br>逐节点调试记录已脱敏的逐节点输入、输出、耗时、错误及最终响应JSON、已脱敏的逐节点输入、输出、耗时、错误及最终响应JSON字段、debug_runs.payload | 已脱敏的逐节点输入、输出、耗时、错误及最终响应JSON | 不是独立统计指标，也不能脱离逐节点调试记录的记录粒度解释；同名列在不同表中的业务含义不自动相同。 | None<br>[]<br>可空：False |

### `semantic_documents` · 语义条目

语义条目保存语义定义或可重建索引，不存储HR查询结果。

粒度：每个语义条目或配置键一行。不表示：不是业务事实表，不允许模型通过它扫描员工或会话数据。

| 字段唯一ID / 类型 | 名称与口语别名 | 表示什么 | 不表示什么 | 单位 / 示例值 / 可空 |
|---|---|---|---|---|
| `semantic_documents.id`<br>TEXT | 语义唯一ID<br>语义唯一ID、语义条目语义唯一ID、semantic_documents.id | field使用表ID.字段ID；metric使用metric:指标ID。不同种类不得重用标识。 | 不是实际员工值、数据库查询结果或模型可以修改的授权声明。 | None<br>[]<br>可空：False |
| `semantic_documents.kind`<br>TEXT | 条目类型<br>条目类型、语义条目条目类型、semantic_documents.kind | table/field/metric/question/relationship，决定详情结构与检索过滤。 | 不是实际员工值、数据库查询结果或模型可以修改的授权声明。 | None<br>[]<br>可空：False |
| `semantic_documents.table_id`<br>TEXT | 所属表ID<br>所属表ID、语义条目所属表ID、semantic_documents.table_id | 字段与表条目的所属表标识；指标和问题不强制只有一张表。 | 不是实际员工值、数据库查询结果或模型可以修改的授权声明。 | None<br>[]<br>可空：True |
| `semantic_documents.status`<br>TEXT | 可用状态<br>可用状态、语义条目可用状态、semantic_documents.status | available已支持、planned待建设、reference_only仅结构说明；不能把存在定义当作可执行授权。 | 不是实际员工值、数据库查询结果或模型可以修改的授权声明。 | None<br>[]<br>可空：False |
| `semantic_documents.visibility`<br>TEXT | 元数据可见范围<br>元数据可见范围、语义条目元数据可见范围、semantic_documents.visibility | internal通用内部描述、salary薪酬能力、governance仅治理身份；每次检索与读取都重新过滤。 | 不是实际员工值、数据库查询结果或模型可以修改的授权声明。 | None<br>[]<br>可空：False |
| `semantic_documents.version`<br>TEXT | 发布语义版本<br>发布语义版本、语义条目发布语义版本、semantic_documents.version | 对应Git语义定义的版本；具体变更另由发布摘要校验。 | 不是实际员工值、数据库查询结果或模型可以修改的授权声明。 | None<br>[]<br>可空：False |
| `semantic_documents.definition`<br>TEXT | 完整定义JSON<br>完整定义JSON、语义条目完整定义JSON、semantic_documents.definition | 保存经过校验的别名、正反定义、口径、示例、关系等；不是员工记录或执行结果。 | 不是实际员工值、数据库查询结果或模型可以修改的授权声明。 | None<br>[]<br>可空：False |

### `semantic_search` · 语义全文索引

语义全文索引保存语义定义或可重建索引，不存储HR查询结果。

粒度：每个语义条目或配置键一行。不表示：不是业务事实表，不允许模型通过它扫描员工或会话数据。

| 字段唯一ID / 类型 | 名称与口语别名 | 表示什么 | 不表示什么 | 单位 / 示例值 / 可空 |
|---|---|---|---|---|
| `semantic_search.id`<br>TEXT | 语义条目ID<br>语义条目ID、语义全文索引语义条目ID、semantic_search.id | 回指semantic_documents.id，仅用于检索定位；索引命中不赋予权限。 | 不是实际员工值、数据库查询结果或模型可以修改的授权声明。 | None<br>[]<br>可空：False |
| `semantic_search.title`<br>TEXT | 索引标题<br>索引标题、语义全文索引索引标题、semantic_search.title | 从条目名称派生；采用FTS5 trigram分词和BM25排序。 | 不是实际员工值、数据库查询结果或模型可以修改的授权声明。 | None<br>[]<br>可空：False |
| `semantic_search.content`<br>TEXT | 正向检索文本<br>正向检索文本、语义全文索引正向检索文本、semantic_search.content | 从名称、口语别名、含义派生；反例不作为正向别名，索引可从JSON重建。 | 不是实际员工值、数据库查询结果或模型可以修改的授权声明。 | None<br>[]<br>可空：False |

### `semantic_meta` · 语义发布元信息

语义发布元信息保存语义定义或可重建索引，不存储HR查询结果。

粒度：每个语义条目或配置键一行。不表示：不是业务事实表，不允许模型通过它扫描员工或会话数据。

| 字段唯一ID / 类型 | 名称与口语别名 | 表示什么 | 不表示什么 | 单位 / 示例值 / 可空 |
|---|---|---|---|---|
| `semantic_meta.key`<br>TEXT | 配置键<br>配置键、语义发布元信息配置键、semantic_meta.key | version/revision/documents等发布状态键。 | 不是实际员工值、数据库查询结果或模型可以修改的授权声明。 | None<br>[]<br>可空：False |
| `semantic_meta.value`<br>TEXT | 配置值<br>配置值、语义发布元信息配置值、semantic_meta.value | 语义版本、源文件SHA256摘要或条目数，不包含个人业务值。 | 不是实际员工值、数据库查询结果或模型可以修改的授权声明。 | None<br>[]<br>可空：False |

## 指标口径

### `metric:headcount` · 在职人数

状态：可执行；单位：人。

口语别名：人数、员工数、人员规模、下属、在岗多少人、我们有几个人、团队规模、现有员工数、多少号人、多少人、几个人、人员数量

- **表示什么**：在统计日已入职且尚未离职的去重员工数，包含正式、实习和外包。离职日不计在职。
- **不表示什么**：不是累计入职人数，不是考勤打卡人数，也不是编制数；明确问下属时不自动把本人当下属。
- **计算公式**：COUNT(DISTINCT employee_id) WHERE hire_date <= snapshot AND (termination_date IS NULL OR termination_date > snapshot)
- **粒度**：员工去重
- **时间口径**：统计日；月趋势按各月末、当前月截至数据日
- **纳入范围**：全部获准且在职的正式/实习/外包员工
- **排除范围**：离职日当天、未来入职、授权范围外员工
- **空值与除零**：比率/均值分母为0返回NULL；计数与合计无匹配返回0。
- **分组约束**：部门指三级部门含下属团队，公司及事业部直属人员单列；历史归属按事件时点。
- **权限规则**：先按当前身份取员工授权集合，所有事实再与该集合连接。检索命中不扩大权限；看板每次重算。
- **负责人**：HR 数据负责人（模拟）

依赖字段：`employees.id`、`employees.hire_date`、`employees.termination_date`、`assignments.department_id`、`assignments.valid_from`、`assignments.valid_to`

提问示例：按事业部统计本月在职人数

### `metric:hires` · 新入职人数

状态：可执行；单位：人。

口语别名：新增、入职、招聘入职、新来了多少人、招进来几个人、新同事数量、入司人数、报到了多少人、新来、新加入、新进员工

- **表示什么**：入职日期落在选定期间的去重员工数，组织按入职时任职关系归属。
- **不表示什么**：不是招聘需求、发offer人数、转正人数或内部调岗人数；期间入职后又离职仍计入。
- **计算公式**：COUNT(DISTINCT employee_id) WHERE hire_date BETWEEN period_start AND period_end
- **粒度**：员工去重
- **时间口径**：入职日落在期间；组织及教育取入职时点
- **纳入范围**：期间发生入职的授权员工
- **排除范围**：纯内部调动、录用未报到、期间外入职
- **空值与除零**：比率/均值分母为0返回NULL；计数与合计无匹配返回0。
- **分组约束**：部门指三级部门含下属团队，公司及事业部直属人员单列；历史归属按事件时点。
- **权限规则**：先按当前身份取员工授权集合，所有事实再与该集合连接。检索命中不扩大权限；看板每次重算。
- **负责人**：HR 数据负责人（模拟）

依赖字段：`employees.id`、`employees.hire_date`、`assignments.department_id`、`assignments.valid_from`、`assignments.valid_to`

提问示例：按事业部统计本月新入职人数

### `metric:departures` · 离职人数

状态：可执行；单位：人。

口语别名：离职、流失人数、走了多少人、离开公司人数、离司人数、流失了几个员工、离职了几位

- **表示什么**：离职日期落在选定期间的去重员工数，组织按离职日前一天归属。
- **不表示什么**：不是内部调动、提交辞呈或缺勤；不是全部历史离职人员。
- **计算公式**：COUNT(DISTINCT employee_id) WHERE termination_date BETWEEN period_start AND period_end
- **粒度**：员工去重
- **时间口径**：离职日落在期间；任职归属离职前一天
- **纳入范围**：期间已离职的授权员工
- **排除范围**：调岗、未生效离职、期间外离职
- **空值与除零**：比率/均值分母为0返回NULL；计数与合计无匹配返回0。
- **分组约束**：部门指三级部门含下属团队，公司及事业部直属人员单列；历史归属按事件时点。
- **权限规则**：先按当前身份取员工授权集合，所有事实再与该集合连接。检索命中不扩大权限；看板每次重算。
- **负责人**：HR 数据负责人（模拟）

依赖字段：`employees.id`、`employees.termination_date`、`assignments.department_id`、`assignments.valid_from`、`assignments.valid_to`

提问示例：按事业部统计本月离职人数

### `metric:turnover_rate` · 人员离职率

状态：可执行；单位：%。

口语别名：离职率、流失率、离司比例、人员流动率、离职占多少

- **表示什么**：期间离职人数 ÷ ((期初在职人数 + 期末在职人数) / 2) × 100。为演示统一口径，不进行年化。
- **不表示什么**：不是离职人数/期末人数，不是入离职总和占比，不自动年化；学历筛选也必须作用于各时点相同条件。
- **计算公式**：200 * 期间离职人数 / NULLIF(期初在职人数 + 期末在职人数, 0)
- **粒度**：授权员工的期间事件与期末快照
- **时间口径**：期初=开始日前一天，期末=结束日；离职按事件日
- **纳入范围**：统一授权范围的期初、期末和离职人群
- **排除范围**：未来事件、内部调动；分母0返回空值
- **空值与除零**：比率/均值分母为0返回NULL；计数与合计无匹配返回0。
- **分组约束**：部门指三级部门含下属团队，公司及事业部直属人员单列；历史归属按事件时点。
- **权限规则**：先按当前身份取员工授权集合，所有事实再与该集合连接。检索命中不扩大权限；看板每次重算。
- **负责人**：HR 数据负责人（模拟）

依赖字段：`employees.hire_date`、`employees.termination_date`、`assignments.department_id`

提问示例：按事业部统计本月人员离职率

### `metric:avg_tenure` · 平均司龄

状态：可执行；单位：年。

口语别名：司龄、工龄、平均工龄、平均在司多久、平均在公司几年、平均服务年限

- **表示什么**：统计日在职员工从最近入职日起至统计日的天数 / 365.25 的算术平均。
- **不表示什么**：不是员工累计社会工龄或年龄，不包括离职员工，也不合并多次返聘年限。
- **计算公式**：AVG((snapshot - hire_date).days / 365.25)
- **粒度**：员工去重
- **时间口径**：统计日在职快照
- **纳入范围**：当前获准在职员工
- **排除范围**：统计日已离职人员
- **空值与除零**：比率/均值分母为0返回NULL；计数与合计无匹配返回0。
- **分组约束**：部门指三级部门含下属团队，公司及事业部直属人员单列；历史归属按事件时点。
- **权限规则**：先按当前身份取员工授权集合，所有事实再与该集合连接。检索命中不扩大权限；看板每次重算。
- **负责人**：HR 数据负责人（模拟）

依赖字段：`employees.hire_date`、`employees.termination_date`

提问示例：按事业部统计本月平均司龄

### `metric:attendance_rate` · 出勤率

状态：可执行；单位：%。

口语别名：出勤、到岗率、正常出勤比例、该来的人来了多少、出勤完成率

- **表示什么**：正常或远程出勤人日 ÷ (应出勤人日 - 已批准整日请假人日) × 100。缺卡、缺勤不计完成出勤。
- **不表示什么**：不是打卡人数/在职人数；分母按人日计，不能把加班周末当应出勤日。
- **计算公式**：100 * 正常或远程人日 / NULLIF(应出勤人日 - 已批准整日请假人日, 0)
- **粒度**：员工×业务日期
- **时间口径**：考勤业务日落在期间
- **纳入范围**：周一至周五应出勤人日；正常和远程算完成
- **排除范围**：已批准整日请假从分母扣除；缺勤缺卡不算完成
- **空值与除零**：比率/均值分母为0返回NULL；计数与合计无匹配返回0。
- **分组约束**：部门指三级部门含下属团队，公司及事业部直属人员单列；历史归属按事件时点。
- **权限规则**：先按当前身份取员工授权集合，所有事实再与该集合连接。检索命中不扩大权限；看板每次重算。
- **负责人**：HR 数据负责人（模拟）

依赖字段：`attendance_daily.employee_id`、`attendance_daily.day`、`attendance_daily.status`、`leave_requests.approval_status`、`work_calendar.is_workday`

提问示例：按事业部统计本月出勤率

### `metric:late_count` · 迟到人次

状态：可执行；单位：人次。

口语别名：迟到、迟到次数、迟到了几次、迟到多少人次、来晚几次、迟到记录数量

- **表示什么**：工作日上班打卡晚于 09:30 的人日数。09:30 整不迟到。
- **不表示什么**：不是去重迟到人数，也不是迟到分钟之和；同一人不同日期分别计次。
- **计算公式**：COUNT(employee_id, day) WHERE late_minutes > 0
- **粒度**：员工×业务日期
- **时间口径**：工作日打卡日期；09:30整不迟到
- **纳入范围**：迟到分钟大于0的授权人日
- **排除范围**：09:30及之前上班打卡；缺卡不猜迟到
- **空值与除零**：比率/均值分母为0返回NULL；计数与合计无匹配返回0。
- **分组约束**：部门指三级部门含下属团队，公司及事业部直属人员单列；历史归属按事件时点。
- **权限规则**：先按当前身份取员工授权集合，所有事实再与该集合连接。检索命中不扩大权限；看板每次重算。
- **负责人**：HR 数据负责人（模拟）

依赖字段：`attendance_daily.employee_id`、`attendance_daily.day`、`attendance_daily.check_in`、`attendance_daily.late_minutes`、`shift_policies.latest_in`

提问示例：按事业部统计本月迟到人次

### `metric:late_rate` · 迟到率

状态：可执行；单位：%。

口语别名：迟到率、来晚比例、迟到占比、迟到频率

- **表示什么**：迟到人次 ÷ 有上班打卡的应出勤人次 × 100。远程同样按弹性规则统计。
- **不表示什么**：不是迟到员工人数/在职人数，不是迟到分钟/工时。
- **计算公式**：100 * 迟到人次 / NULLIF(有上班打卡的应出勤人次, 0)
- **粒度**：员工×业务日期
- **时间口径**：考勤业务日
- **纳入范围**：授权范围内有上班打卡的工作日人次
- **排除范围**：无上班打卡的样本不进入分母
- **空值与除零**：比率/均值分母为0返回NULL；计数与合计无匹配返回0。
- **分组约束**：部门指三级部门含下属团队，公司及事业部直属人员单列；历史归属按事件时点。
- **权限规则**：先按当前身份取员工授权集合，所有事实再与该集合连接。检索命中不扩大权限；看板每次重算。
- **负责人**：HR 数据负责人（模拟）

依赖字段：`attendance_daily.late_minutes`、`attendance_daily.check_in`、`attendance_daily.day`

提问示例：按事业部统计本月迟到率

### `metric:abnormal_count` · 考勤异常人次

状态：可执行；单位：人次。

口语别名：异常、缺卡、考勤异常、考勤出问题几次、异常打卡次数、异常考勤数量、出勤异常情况

- **表示什么**：迟到、早退、缺勤或缺卡任一条件成立的人日数，同一人同一天只计一次。
- **不表示什么**：不是四类异常数量相加；同一人同一天迟到又早退只计1次。
- **计算公式**：COUNT(employee_id, day) WHERE late_minutes>0 OR early_minutes>0 OR status IN (缺勤,缺卡)
- **粒度**：员工×业务日期
- **时间口径**：考勤业务日期
- **纳入范围**：至少命中一次迟到、早退、缺勤或缺卡的人日
- **排除范围**：正常、远程、已批准请假且无其他异常
- **空值与除零**：比率/均值分母为0返回NULL；计数与合计无匹配返回0。
- **分组约束**：部门指三级部门含下属团队，公司及事业部直属人员单列；历史归属按事件时点。
- **权限规则**：先按当前身份取员工授权集合，所有事实再与该集合连接。检索命中不扩大权限；看板每次重算。
- **负责人**：HR 数据负责人（模拟）

依赖字段：`attendance_daily.late_minutes`、`attendance_daily.early_minutes`、`attendance_daily.status`、`attendance_daily.day`

提问示例：按事业部统计本月考勤异常人次

### `metric:approved_overtime_hours` · 已批准加班时长

状态：可执行；单位：小时。

口语别名：加班、审批加班、加班时长、批下来的加班、加班总共多久、审核通过的加班小时、批准加班工时

- **表示什么**：选定期间工作日及周末已批准加班申请分钟数之和 / 60。工作日晚离岗与周末实际打卡分别校验；待审批和拒绝申请不计入。
- **不表示什么**：不是晚走时长，也不是待审批申请。包含工作日和周末，不能假定只统计周一到周五。
- **计算公式**：SUM(overtime_requests.minutes WHERE approval_status=已批准) / 60
- **粒度**：员工×业务日期
- **时间口径**：加班实际业务日，不是审批操作时间
- **纳入范围**：已批准加班申请；工作日+周末
- **排除范围**：待审批、已拒绝以及未提交申请的晚离岗
- **空值与除零**：比率/均值分母为0返回NULL；计数与合计无匹配返回0。
- **分组约束**：部门指三级部门含下属团队，公司及事业部直属人员单列；历史归属按事件时点。
- **权限规则**：先按当前身份取员工授权集合，所有事实再与该集合连接。检索命中不扩大权限；看板每次重算。
- **负责人**：HR 数据负责人（模拟）

依赖字段：`overtime_requests.minutes`、`overtime_requests.approval_status`、`overtime_requests.day`、`overtime_requests.day_type`

提问示例：按事业部统计本月已批准加班时长

### `metric:late_departure_hours` · 晚离岗时长

状态：可执行；单位：小时。

口语别名：晚下班、晚离岗、晚走、晚走了多久、晚下班时长、下班后多待了多久、超出应离岗时间

- **表示什么**：下班晚于个人应离岗时间的分钟数之和 / 60。应离岗时间为 max(18:00, 上班时间 + 9小时)，午休为1小时。该指标不是劳动报酬口径。
- **不表示什么**：不是已批准加班，更不直接决定加班费；不能统一用下班时刻减18点。
- **计算公式**：SUM(MAX(check_out - MAX(18:00, check_in+9小时), 0)) / 60
- **粒度**：员工×业务日期
- **时间口径**：工作日考勤业务日
- **纳入范围**：完整打卡且晚于个人应离岗时刻的分钟
- **排除范围**：缺卡、周末独立打卡以及不超过应离岗时刻的部分
- **空值与除零**：比率/均值分母为0返回NULL；计数与合计无匹配返回0。
- **分组约束**：部门指三级部门含下属团队，公司及事业部直属人员单列；历史归属按事件时点。
- **权限规则**：先按当前身份取员工授权集合，所有事实再与该集合连接。检索命中不扩大权限；看板每次重算。
- **负责人**：HR 数据负责人（模拟）

依赖字段：`attendance_daily.check_in`、`attendance_daily.check_out`、`attendance_daily.late_departure_minutes`、`shift_policies.earliest_out`

提问示例：按事业部统计本月晚离岗时长

### `metric:avg_work_hours` · 平均有效在岗时长

状态：可执行；单位：小时/人日。

口语别名：工作时长、工时、在岗时长、平均每天干多久、平均净在岗工时、人均工作时长、平均有效工作时间

- **表示什么**：正常或远程且上下班打卡完整的净在岗分钟（打卡间隔减60分钟午休）÷ 完整打卡人日 ÷ 60。
- **不表示什么**：不是人均加班，不是企业支付工时，也不应把缺卡当0小时拉低均值。
- **计算公式**：SUM(完整打卡净在岗分钟) / NULLIF(正常或远程完整打卡人日,0) / 60
- **粒度**：员工×业务日期
- **时间口径**：期间工作日
- **纳入范围**：正常/远程且上下班打卡完整的人日
- **排除范围**：缺勤、请假、缺卡、周末加班事实
- **空值与除零**：比率/均值分母为0返回NULL；计数与合计无匹配返回0。
- **分组约束**：部门指三级部门含下属团队，公司及事业部直属人员单列；历史归属按事件时点。
- **权限规则**：先按当前身份取员工授权集合，所有事实再与该集合连接。检索命中不扩大权限；看板每次重算。
- **负责人**：HR 数据负责人（模拟）

依赖字段：`attendance_daily.work_minutes`、`attendance_daily.check_in`、`attendance_daily.check_out`、`attendance_daily.status`

提问示例：按事业部统计本月平均有效在岗时长

### `metric:leave_days` · 已批准请假天数

状态：可执行；单位：天。

口语别名：请假、休假、年假、休了多少天假、请假总天数、批下来的假期、批准休假天数

- **表示什么**：选定期间已批准整日请假天数。演示不包含半天、跨时区与跨午夜班次。
- **不表示什么**：不是剩余年假天数或申请单数；当前模拟每条整日申请1天，不支持半天小时假。
- **计算公式**：SUM(leave_requests.days WHERE approval_status=已批准)
- **粒度**：员工×业务日期
- **时间口径**：请假实际日期
- **纳入范围**：已批准整日请假申请
- **排除范围**：未审批、拒绝、半天与跨夜休假暂未建模
- **空值与除零**：比率/均值分母为0返回NULL；计数与合计无匹配返回0。
- **分组约束**：部门指三级部门含下属团队，公司及事业部直属人员单列；历史归属按事件时点。
- **权限规则**：先按当前身份取员工授权集合，所有事实再与该集合连接。检索命中不扩大权限；看板每次重算。
- **负责人**：HR 数据负责人（模拟）

依赖字段：`leave_requests.days`、`leave_requests.day`、`leave_requests.approval_status`

提问示例：按事业部统计本月已批准请假天数

### `metric:avg_salary` · 平均基本月薪

状态：可执行；单位：元/月。

口语别名：薪资、工资、薪酬、月薪、平均工资、平均基本工资、平均月基本薪资、基本薪资均值、月薪平均数

- **表示什么**：统计日在职员工有效基本月薪的算术平均，仅CNY，不含奖金和补贴。仅公司负责人获准汇总，少于5人的分组不显示；不开放任意人员过滤。
- **不表示什么**：不是到手工资、工资总额、总包或平均奖金；教育、人员、任意部门过滤与明细、导出均禁止。
- **计算公式**：AVG(统计日在职员工有效monthly_base)，小组及必要互补组抑制
- **粒度**：员工去重
- **时间口径**：仅当前快照，不开放历史差分
- **纳入范围**：获准范围内CNY有效基本月薪；分组至少5人且互补保护
- **排除范围**：个人金额、奖金津贴、其他币种、小样本及可反推组
- **空值与除零**：比率/均值分母为0返回NULL；计数与合计无匹配返回0。
- **分组约束**：部门指三级部门含下属团队，公司及事业部直属人员单列；历史归属按事件时点。
- **权限规则**：先按当前身份取员工授权集合，所有事实再与该集合连接。仅salary_aggregate能力；至少5人及互补抑制，禁止人员/学校/学历过滤、明细与导出。
- **负责人**：薪酬负责人（模拟）

依赖字段：`compensation.monthly_base`、`compensation.currency`、`compensation.valid_from`、`compensation.valid_to`、`employees.hire_date`、`employees.termination_date`

提问示例：按事业部统计本月平均基本月薪

### `metric:workforce_changes` · 入离职与净增人数

状态：可执行；单位：人。

口语别名：入离职、入职和离职、人员净增、净增人数、进出人数、来了多少走了多少、入离职统计、净增加几个人、增减员情况

- **表示什么**：同一期间分别统计入职人数、离职人数，净增=入职-离职；入职归属入职日组织，离职归属离职日前一日。部门包含下属团队，内部调动不计入离职。无事件的授权组织显示0。
- **不表示什么**：不是单一hires或departures，也不是内部调动总量；净增不自动等于某部门期末减期初人数，调岗可能改变存量。
- **计算公式**：入职=COUNT DISTINCT hire事件；离职=COUNT DISTINCT termination事件；净增=入职-离职
- **粒度**：授权员工的期间事件与期末快照
- **时间口径**：事件落在同一期间；入职当天归属，离职前一天归属
- **纳入范围**：期间入职与离职事件，允许同人两类事件各计一次
- **排除范围**：内部调岗、期间外事件
- **空值与除零**：比率/均值分母为0返回NULL；计数与合计无匹配返回0。
- **分组约束**：部门指三级部门含下属团队，公司及事业部直属人员单列；历史归属按事件时点。
- **权限规则**：先按当前身份取员工授权集合，所有事实再与该集合连接。检索命中不扩大权限；看板每次重算。
- **负责人**：HR 数据负责人（模拟）

依赖字段：`employees.hire_date`、`employees.termination_date`、`assignments.department_id`、`assignments.valid_from`、`assignments.valid_to`

提问示例：整个公司今年各部门入职和离职人数统计

### `metric:weekend_overtime_hours` · 周末已批准加班时长

状态：可执行；单位：小时。

口语别名：周末加班、周六周日加班、双休日加班、双休日加了多久、周六周日加班小时、休息周末加班总量、周末加班工时

- **表示什么**：选定期间周六/周日已批准加班申请分钟之和 / 60；以独立周末打卡净时长为申请上限，不含工作日晚离岗、待审批、拒绝。演示不含节假日调休。无事件的授权组织显示0。
- **不表示什么**：不是法定休息日加班或节假日加班；模拟日历未接调休。不是工作日晚离岗。
- **计算公式**：SUM(minutes WHERE approval_status=已批准 AND day_type=周末 AND weekday IN (周六,周日)) / 60
- **粒度**：员工×业务日期
- **时间口径**：自然周六或周日业务日，未指定时本月
- **纳入范围**：已批准且有独立周末净打卡工时校验的申请
- **排除范围**：工作日申请、待审批、已拒绝
- **空值与除零**：比率/均值分母为0返回NULL；计数与合计无匹配返回0。
- **分组约束**：部门指三级部门含下属团队，公司及事业部直属人员单列；历史归属按事件时点。
- **权限规则**：先按当前身份取员工授权集合，所有事实再与该集合连接。检索命中不扩大权限；看板每次重算。
- **负责人**：HR 数据负责人（模拟）

依赖字段：`overtime_requests.minutes`、`overtime_requests.approval_status`、`overtime_requests.day_type`、`overtime_attendance.work_minutes`、`overtime_attendance.day`

提问示例：本月各部门周末加班的总工时

### `metric:education_ratio` · 教育背景人员占比

状态：可执行；单位：%。

口语别名：学历占比、硕士比例、博士比例、985比例、211比例、毕业院校占比、名校背景比例、高学历占多少

- **表示什么**：满足学历、学位、学校或院校标签条件的去重人数÷同组全部授权人群×100。默认统计日在职人群及最高已完成教育经历；可指定期间入职或离职人群，教育按事件日取值。未知教育计入分母，分母0返回NULL，并列出分子与分母。
- **不表示什么**：不是各学历百分比相加；211包含985。硕士默认精确硕士学位；硕士及以上才包含博士。未知教育仍计分母。
- **计算公式**：100 * 满足教育条件的去重员工人数 / NULLIF(同组同权限完整人群去重人数, 0)
- **粒度**：员工去重
- **时间口径**：默认在职快照；入职/离职人群按期间事件及事件日教育
- **纳入范围**：分子应用教育条件；分母是同组全部授权在职或指定入离职人群
- **排除范围**：授权外员工；未来毕业经历不入分子；分母不得应用教育条件
- **空值与除零**：比率/均值分母为0返回NULL；计数与合计无匹配返回0。
- **分组约束**：部门指三级部门含下属团队，公司及事业部直属人员单列；历史归属按事件时点。
- **权限规则**：先按当前身份取员工授权集合，所有事实再与该集合连接。检索命中不扩大权限；看板每次重算。
- **负责人**：HR 数据负责人（模拟）

依赖字段：`employee_education.employee_id`、`employee_education.education_level`、`employee_education.education_rank`、`employee_education.degree`、`employee_education.graduation_date`、`employee_education.school_id`、`schools.is_985`、`schools.is_211`、`employees.hire_date`、`employees.termination_date`

提问示例：平台研发部硕士及以上学历员工的比例

### `metric:education_completeness_rate` · 教育信息完整率

状态：规划，禁止执行；单位：%。

口语别名：教育信息完整率、教育档案填全了吗、各部门学历资料完整率、多少员工没有完善教育信息

- **表示什么**：COUNT(在职且最高学历、学位、学校、毕业日已填写的员工)/COUNT(全部授权在职员工)*100
- **不表示什么**：完整率不是高学历比例；未知教育计入分母，不得通过丢弃未知值提高完整率。
- **计算公式**：COUNT(在职且最高学历、学位、学校、毕业日已填写的员工)/COUNT(全部授权在职员工)*100
- **粒度**：需按定义中的员工、任务或期间事件去重
- **时间口径**：使用问题明确的业务期间；快照类按截止日，批次类须满观察期。
- **纳入范围**：按公式明确的人群或有效业务事件；先应用当前授权。
- **排除范围**：完整率不是高学历比例；未知教育计入分母，不得通过丢弃未知值提高完整率。
- **空值与除零**：分母为0或必需事实缺失返回不可用，不猜测或返回虚构0。
- **权限规则**：未发布指标禁止执行；新领域需要明确授权能力。
- **尚需完成**：字段已具备，尚需实现完整性判定与指标编译
- **负责人**：HR及业务系统负责人（模拟，待企业确认）

依赖字段：`employees.highest_education`、`employees.highest_degree`、`employees.graduation_school_id`、`employees.graduation_date`

提问示例：教育档案填全了吗；各部门学历资料完整率；多少员工没有完善教育信息

### `metric:department_headcount_ratio` · 部门人员占比

状态：规划，禁止执行；单位：%。

口语别名：部门人员占比、各部门人数占整个授权范围多少、研发团队占比多大、我们的人都集中在哪些部门，各占多少

- **表示什么**：部门授权在职人数/同一身份全授权在职人数*100
- **不表示什么**：分母不是整个真实公司总人数，普通主管只能使用其授权范围作基数。
- **计算公式**：部门授权在职人数/同一身份全授权在职人数*100
- **粒度**：需按定义中的员工、任务或期间事件去重
- **时间口径**：使用问题明确的业务期间；快照类按截止日，批次类须满观察期。
- **纳入范围**：按公式明确的人群或有效业务事件；先应用当前授权。
- **排除范围**：分母不是整个真实公司总人数，普通主管只能使用其授权范围作基数。
- **空值与除零**：分母为0或必需事实缺失返回不可用，不猜测或返回虚构0。
- **权限规则**：未发布指标禁止执行；新领域需要明确授权能力。
- **尚需完成**：原始指标已具备，待实现跨分组占比及口径展示
- **负责人**：HR及业务系统负责人（模拟，待企业确认）

依赖字段：`employees.hire_date`、`employees.termination_date`、`assignments.department_id`

提问示例：各部门人数占整个授权范围多少；研发团队占比多大；我们的人都集中在哪些部门，各占多少

### `metric:absence_days` · 缺勤人日

状态：规划，禁止执行；单位：人日。

口语别名：缺勤人日、本月总共旷了多少天、各部门缺勤人日、上个月缺勤有多少人天

- **表示什么**：COUNT(授权应出勤人日 WHERE attendance_daily.status=缺勤)
- **不表示什么**：不是缺卡、请假或迟到；同一员工跨日缺勤分别计入。
- **计算公式**：COUNT(授权应出勤人日 WHERE attendance_daily.status=缺勤)
- **粒度**：需按定义中的员工、任务或期间事件去重
- **时间口径**：使用问题明确的业务期间；快照类按截止日，批次类须满观察期。
- **纳入范围**：按公式明确的人群或有效业务事件；先应用当前授权。
- **排除范围**：不是缺卡、请假或迟到；同一员工跨日缺勤分别计入。
- **空值与除零**：分母为0或必需事实缺失返回不可用，不猜测或返回虚构0。
- **权限规则**：未发布指标禁止执行；新领域需要明确授权能力。
- **尚需完成**：字段已具备，尚未开放独立缺勤指标
- **负责人**：HR及业务系统负责人（模拟，待企业确认）

依赖字段：`attendance_daily.status`、`attendance_daily.day`

提问示例：本月总共旷了多少天；各部门缺勤人日；上个月缺勤有多少人天

### `metric:early_leave_count` · 早退人次

状态：规划，禁止执行；单位：人次。

口语别名：早退人次、本月早退了几次、按部门统计早退人次、上周提早下班有几次异常

- **表示什么**：COUNT(授权人日 WHERE early_minutes>0)
- **不表示什么**：不是早退分钟总数，也不是去重员工人数；用个人应离岗时刻判断。
- **计算公式**：COUNT(授权人日 WHERE early_minutes>0)
- **粒度**：需按定义中的员工、任务或期间事件去重
- **时间口径**：使用问题明确的业务期间；快照类按截止日，批次类须满观察期。
- **纳入范围**：按公式明确的人群或有效业务事件；先应用当前授权。
- **排除范围**：不是早退分钟总数，也不是去重员工人数；用个人应离岗时刻判断。
- **空值与除零**：分母为0或必需事实缺失返回不可用，不猜测或返回虚构0。
- **权限规则**：未发布指标禁止执行；新领域需要明确授权能力。
- **尚需完成**：字段已具备，尚未开放独立早退指标
- **负责人**：HR及业务系统负责人（模拟，待企业确认）

依赖字段：`attendance_daily.early_minutes`、`attendance_daily.day`

提问示例：本月早退了几次；按部门统计早退人次；上周提早下班有几次异常

### `metric:avg_approved_overtime_hours` · 人均批准加班时长

状态：规划，禁止执行；单位：小时/人。

口语别名：人均批准加班时长、各部门人均加班多久、今年人均批准加班小时、本月员工平均分摊多少加班工时

- **表示什么**：期间授权已批准加班总小时/期间至少有1个应出勤日的去重授权员工数
- **不表示什么**：不是仅对加班人员求平均，也不是月底在职人数作分母；期间离职但应出勤者仍进分母。
- **计算公式**：期间授权已批准加班总小时/期间至少有1个应出勤日的去重授权员工数
- **粒度**：需按定义中的员工、任务或期间事件去重
- **时间口径**：使用问题明确的业务期间；快照类按截止日，批次类须满观察期。
- **纳入范围**：按公式明确的人群或有效业务事件；先应用当前授权。
- **排除范围**：不是仅对加班人员求平均，也不是月底在职人数作分母；期间离职但应出勤者仍进分母。
- **空值与除零**：分母为0或必需事实缺失返回不可用，不猜测或返回虚构0。
- **权限规则**：未发布指标禁止执行；新领域需要明确授权能力。
- **尚需完成**：事实已有，待实现期间在职覆盖分母与新指标
- **负责人**：HR及业务系统负责人（模拟，待企业确认）

依赖字段：`overtime_requests.minutes`、`overtime_requests.approval_status`、`attendance_daily.employee_id`

提问示例：各部门人均加班多久；今年人均批准加班小时；本月员工平均分摊多少加班工时

### `metric:voluntary_turnover_rate` · 主动离职率

状态：规划，禁止执行；单位：%。

口语别名：主动离职率、今年主动辞职率多少、各部门主动离职占比、上季度主动走人的比例

- **表示什么**：期间主动离职人数/((期初在职+期末在职)/2)*100
- **不表示什么**：不包括辞退、退休、合同到期；不能从离职日期或模型推断原因。
- **计算公式**：期间主动离职人数/((期初在职+期末在职)/2)*100
- **粒度**：需按定义中的员工、任务或期间事件去重
- **时间口径**：使用问题明确的业务期间；快照类按截止日，批次类须满观察期。
- **纳入范围**：按公式明确的人群或有效业务事件；先应用当前授权。
- **排除范围**：不包括辞退、退休、合同到期；不能从离职日期或模型推断原因。
- **空值与除零**：分母为0或必需事实缺失返回不可用，不猜测或返回虚构0。
- **权限规则**：未发布指标禁止执行；新领域需要明确授权能力。
- **尚需完成**：缺少termination_reason与离职性质审核记录
- **负责人**：HR及业务系统负责人（模拟，待企业确认）

依赖字段：`employees.termination_date`

提问示例：今年主动辞职率多少；各部门主动离职占比；上季度主动走人的比例

### `metric:new_hire_retention_90d` · 新员工90天留存率

状态：规划，禁止执行；单位：%。

口语别名：新员工90天留存率、上季度新人90天留存怎么样、今年新员工三个月后留下多少比例、按入职月份看90天留存率

- **表示什么**：已满观察期入职人群中第90天仍在职人数/已满90天观察期入职人数*100
- **不表示什么**：未满观察期员工不得算作已留存；返聘与中断雇佣需按雇佣事件链处理。
- **计算公式**：已满观察期入职人群中第90天仍在职人数/已满90天观察期入职人数*100
- **粒度**：需按定义中的员工、任务或期间事件去重
- **时间口径**：使用问题明确的业务期间；快照类按截止日，批次类须满观察期。
- **纳入范围**：按公式明确的人群或有效业务事件；先应用当前授权。
- **排除范围**：未满观察期员工不得算作已留存；返聘与中断雇佣需按雇佣事件链处理。
- **空值与除零**：分母为0或必需事实缺失返回不可用，不猜测或返回虚构0。
- **权限规则**：未发布指标禁止执行；新领域需要明确授权能力。
- **尚需完成**：需雇佣事件链与满观察期人群编译，当前仅最近一次入职
- **负责人**：HR及业务系统负责人（模拟，待企业确认）

依赖字段：`employees.hire_date`、`employees.termination_date`

提问示例：上季度新人90天留存怎么样；今年新员工三个月后留下多少比例；按入职月份看90天留存率

### `metric:probation_conversion_rate` · 试用转正率

状态：规划，禁止执行；单位：%。

口语别名：试用转正率、本季度试用转正率、各部门新人转正比例、应当转正的人按时转正了吗

- **表示什么**：期间应完成试用员工中按时转正人数/期间应完成试用员工人数*100
- **不表示什么**：不是所有新人转正数/新人总数；尚未到期者排除，延期需按批准后的到期日。
- **计算公式**：期间应完成试用员工中按时转正人数/期间应完成试用员工人数*100
- **粒度**：需按定义中的员工、任务或期间事件去重
- **时间口径**：使用问题明确的业务期间；快照类按截止日，批次类须满观察期。
- **纳入范围**：按公式明确的人群或有效业务事件；先应用当前授权。
- **排除范围**：不是所有新人转正数/新人总数；尚未到期者排除，延期需按批准后的到期日。
- **空值与除零**：分母为0或必需事实缺失返回不可用，不猜测或返回虚构0。
- **权限规则**：未发布指标禁止执行；新领域需要明确授权能力。
- **尚需完成**：缺少probation_end、confirmation_date、试用状态及延期记录
- **负责人**：HR及业务系统负责人（模拟，待企业确认）

依赖字段：`employees.hire_date`

提问示例：本季度试用转正率；各部门新人转正比例；应当转正的人按时转正了吗

### `metric:time_to_fill` · 招聘需求填补周期

状态：规划，禁止执行；单位：天。

口语别名：招聘需求填补周期、一个岗位平均多久招满、各部门招聘补缺周期、本季度填满需求平均需要几天

- **表示什么**：已关闭招聘需求从批准开放到指定到岗填补事件的自然天数平均值
- **不表示什么**：不是面试周期，也不是offer发放到接受时间；多名额需求需统一首人或满编关闭定义。
- **计算公式**：已关闭招聘需求从批准开放到指定到岗填补事件的自然天数平均值
- **粒度**：需按定义中的员工、任务或期间事件去重
- **时间口径**：使用问题明确的业务期间；快照类按截止日，批次类须满观察期。
- **纳入范围**：按公式明确的人群或有效业务事件；先应用当前授权。
- **排除范围**：不是面试周期，也不是offer发放到接受时间；多名额需求需统一首人或满编关闭定义。
- **空值与除零**：分母为0或必需事实缺失返回不可用，不猜测或返回虚构0。
- **权限规则**：未发布指标禁止执行；新领域需要明确授权能力。
- **尚需完成**：缺少需求审批开放日、录用人员关联及关闭事件；默认满额关闭口径待HR确认
- **负责人**：HR及业务系统负责人（模拟，待企业确认）

依赖字段：`recruitment_requisitions.opened_at`、`recruitment_requisitions.openings`

提问示例：一个岗位平均多久招满；各部门招聘补缺周期；本季度填满需求平均需要几天

### `metric:offer_acceptance_rate` · Offer接受率

状态：规划，禁止执行；单位：%。

口语别名：Offer接受率、发出去的offer有多少被接受、各部门offer接受率、上季度发的offer接受比例

- **表示什么**：同一发出批次中明确接受offer数量/该批次有效且已到决策截止的offer数量*100
- **不表示什么**：未到决策截止的待答复offer暂不进入分母；取消或重复offer需独立排除规则。
- **计算公式**：同一发出批次中明确接受offer数量/该批次有效且已到决策截止的offer数量*100
- **粒度**：需按定义中的员工、任务或期间事件去重
- **时间口径**：使用问题明确的业务期间；快照类按截止日，批次类须满观察期。
- **纳入范围**：按公式明确的人群或有效业务事件；先应用当前授权。
- **排除范围**：未到决策截止的待答复offer暂不进入分母；取消或重复offer需独立排除规则。
- **空值与除零**：分母为0或必需事实缺失返回不可用，不猜测或返回虚构0。
- **权限规则**：未发布指标禁止执行；新领域需要明确授权能力。
- **尚需完成**：尚无offer事实、有效状态、发出/截止/接受时间
- **负责人**：HR及业务系统负责人（模拟，待企业确认）

依赖字段：

提问示例：发出去的offer有多少被接受；各部门offer接受率；上季度发的offer接受比例

### `metric:training_completion_rate` · 培训完成率

状态：规划，禁止执行；单位：%。

口语别名：培训完成率、各部门培训完成率、必修课有多少员工完成了、今年安排的培训完成比例

- **表示什么**：指定学习任务中截止日已完成人员数/应完成人员数*100
- **不表示什么**：不是课程报名总次数或培训时长；同人同课程任务去重，取消任务是否排除需记录状态。
- **计算公式**：指定学习任务中截止日已完成人员数/应完成人员数*100
- **粒度**：需按定义中的员工、任务或期间事件去重
- **时间口径**：使用问题明确的业务期间；快照类按截止日，批次类须满观察期。
- **纳入范围**：按公式明确的人群或有效业务事件；先应用当前授权。
- **排除范围**：不是课程报名总次数或培训时长；同人同课程任务去重，取消任务是否排除需记录状态。
- **空值与除零**：分母为0或必需事实缺失返回不可用，不猜测或返回虚构0。
- **权限规则**：未发布指标禁止执行；新领域需要明确授权能力。
- **尚需完成**：课程记录已有；缺少任务分派日、截止日及取消记录，未开放查询
- **负责人**：HR及业务系统负责人（模拟，待企业确认）

依赖字段：`training_enrollments.employee_id`、`training_enrollments.course_id`、`training_enrollments.status`、`training_enrollments.completed_at`

提问示例：各部门培训完成率；必修课有多少员工完成了；今年安排的培训完成比例

### `metric:performance_distribution` · 绩效等级分布

状态：规划，禁止执行；单位：%。

口语别名：绩效等级分布、上季度绩效等级分布、各部门优秀绩效人数比例、这个绩效周期有多少员工未评价

- **表示什么**：指定绩效周期中按有效最终评价等级分组的去重授权员工人数及比例
- **不表示什么**：不是绩效预测或模型评价；不能跨周期简单平均等级，缺少评价者需单列。
- **计算公式**：指定绩效周期中按有效最终评价等级分组的去重授权员工人数及比例
- **粒度**：需按定义中的员工、任务或期间事件去重
- **时间口径**：使用问题明确的业务期间；快照类按截止日，批次类须满观察期。
- **纳入范围**：按公式明确的人群或有效业务事件；先应用当前授权。
- **排除范围**：不是绩效预测或模型评价；不能跨周期简单平均等级，缺少评价者需单列。
- **空值与除零**：分母为0或必需事实缺失返回不可用，不猜测或返回虚构0。
- **权限规则**：未发布指标禁止执行；新领域需要明确授权能力。
- **尚需完成**：绩效表已有，需单独授权能力、终审版本与缺评人群定义
- **负责人**：HR及业务系统负责人（模拟，待企业确认）

依赖字段：`performance_reviews.employee_id`、`performance_reviews.period`、`performance_reviews.rating`

提问示例：上季度绩效等级分布；各部门优秀绩效人数比例；这个绩效周期有多少员工未评价

### `metric:annual_leave_balance` · 剩余年假天数

状态：规划，禁止执行；单位：天。

口语别名：剩余年假天数、大家还剩多少年假、各部门未休年假余额、我的今年年假还剩几天

- **表示什么**：截至统计日已确认权益+有效结转-已使用-已失效天数
- **不表示什么**：不是今年所有请假天数；非年假不扣，撤销申请需冲回；不得模型猜测法定权益。
- **计算公式**：截至统计日已确认权益+有效结转-已使用-已失效天数
- **粒度**：需按定义中的员工、任务或期间事件去重
- **时间口径**：使用问题明确的业务期间；快照类按截止日，批次类须满观察期。
- **纳入范围**：按公式明确的人群或有效业务事件；先应用当前授权。
- **排除范围**：不是今年所有请假天数；非年假不扣，撤销申请需冲回；不得模型猜测法定权益。
- **空值与除零**：分母为0或必需事实缺失返回不可用，不猜测或返回虚构0。
- **权限规则**：未发布指标禁止执行；新领域需要明确授权能力。
- **尚需完成**：缺少年假权益、结转、到期及撤销流水
- **负责人**：HR及业务系统负责人（模拟，待企业确认）

依赖字段：`leave_requests.leave_type`、`leave_requests.days`

提问示例：大家还剩多少年假；各部门未休年假余额；我的今年年假还剩几天

### `metric:payroll_net_total` · 实发工资总额

状态：规划，禁止执行；单位：元。

口语别名：实发工资总额、本月全公司实发工资总额、各事业部工资实际发了多少、这个月工资支付成本

- **表示什么**：指定已确认薪资期间工资发放流水的净支付金额合计
- **不表示什么**：不是基本月薪之和；需处理奖金补贴、税费扣款、币种和冲正，禁止从基本薪资猜实发。
- **计算公式**：指定已确认薪资期间工资发放流水的净支付金额合计
- **粒度**：需按定义中的员工、任务或期间事件去重
- **时间口径**：使用问题明确的业务期间；快照类按截止日，批次类须满观察期。
- **纳入范围**：按公式明确的人群或有效业务事件；先应用当前授权。
- **排除范围**：不是基本月薪之和；需处理奖金补贴、税费扣款、币种和冲正，禁止从基本薪资猜实发。
- **空值与除零**：分母为0或必需事实缺失返回不可用，不猜测或返回虚构0。
- **权限规则**：未发布指标禁止执行；新领域需要明确授权能力。
- **尚需完成**：缺少工资计算与发放事实、税费扣款和结算状态；需薪资专属授权
- **负责人**：HR及业务系统负责人（模拟，待企业确认）

依赖字段：`compensation.monthly_base`、`compensation.currency`

提问示例：本月全公司实发工资总额；各事业部工资实际发了多少；这个月工资支付成本

### `metric:vacancy_rate` · 编制空缺率

状态：规划，禁止执行；单位：%。

口语别名：编制空缺率、各部门缺编比例、今年还有多少岗位没补齐、当前编制空缺率

- **表示什么**：统计日已批准编制空缺数/统计日有效批准总编制数*100
- **不表示什么**：不是未关闭招聘申请数；重复需求、冻结编制和外包名额不能直接混算。
- **计算公式**：统计日已批准编制空缺数/统计日有效批准总编制数*100
- **粒度**：需按定义中的员工、任务或期间事件去重
- **时间口径**：使用问题明确的业务期间；快照类按截止日，批次类须满观察期。
- **纳入范围**：按公式明确的人群或有效业务事件；先应用当前授权。
- **排除范围**：不是未关闭招聘申请数；重复需求、冻结编制和外包名额不能直接混算。
- **空值与除零**：分母为0或必需事实缺失返回不可用，不猜测或返回虚构0。
- **权限规则**：未发布指标禁止执行；新领域需要明确授权能力。
- **尚需完成**：缺少有效期编制计划、编制占用关系与冻结状态
- **负责人**：HR及业务系统负责人（模拟，待企业确认）

依赖字段：`recruitment_requisitions.openings`

提问示例：各部门缺编比例；今年还有多少岗位没补齐；当前编制空缺率

