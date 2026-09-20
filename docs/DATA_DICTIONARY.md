# 字段、指标与演示问题

由 `scripts/document_catalog.py` 从当前源码生成。修改 `schema.py` / `registry.py` 后重新生成，不手工维护第二份口径。

数据快照日：2026-09-11。每人一行；历史事件按当前部门分组，无任职/汇报线历史。

## 人员字段

| 字段 ID | 中文 | 权限组 | 定义 | 口语别名 | 不代表什么 |
|---|---|---|---|---|---|
| `people.person_id` | 人员ID | basic | 人员主键，非工号，员工唯一记录 | 人员主键、人员标识 | 以字段定义为准。 |
| `people.employee_no` | 工号 | basic | 字符串标识，保留前导零 | 员工编号、工号 | 以字段定义为准。 |
| `people.name` | 姓名 | basic | 展示姓名，重名时以工号区分 | 名字、员工姓名 | 以字段定义为准。 |
| `people.head_person_id` | 直接主管ID | basic | 管理关系，关联person_id，不是HRBP | 直属领导、汇报给、直接上级 | 不是部门归属，不沿HRBP服务边递归。 |
| `people.dept_master_id` | 部门主管ID | basic | 部门主管关联person_id，当前不单独授权 | 部门负责人 | 不能单独产生可见权限，暂只做关联字段。 |
| `people.dept_hrbp_id` | HRBP人员ID | basic | HRBP服务关系，允许指向本人 | 人力BP、服务HRBP、HR业务伙伴 | 不是管理线；HRBP服务的员工不会因此变成HRBP的管理下属。 |
| `people.dept_code` | 部门编码 | basic | 当前部门编码，无历史归属 |  | 以字段定义为准。 |
| `people.dept_cn_name` | 部门 | basic | 当前部门名称，历史事件也按当前部门分组 | 部门名称、组织、团队 | 不是入职或离职当时的部门；本数据不保留任职历史。 |
| `people.onboard_date` | 入职日期 | basic | 本次演示采用的入职日期，不等于任职开始日期 | 入司时间、入职时间、新入职 | 以字段定义为准。 |
| `people.termin_date` | 离职日期 | basic | 离职当天已不在职，空值表示未离职 | 离司时间、离职时间 | 以字段定义为准。 |
| `people.birth_date` | 出生日期 | basic | 计算快照日周岁的依据，缺失时年龄未知 | 生日 | 以字段定义为准。 |
| `people.age` | 年龄 | basic | 快照日的周岁，30至40含两个边界 | 周岁、岁数 | 不是系统时间计算的实岁，也不是平均司龄；以数据截止日和出生日期计算。 |
| `people.school_name` | 学校 | education | 宽表当前教育记录的院校，无完整多段教育历史 | 院校、毕业学校、母校 | 不是任意一段教育经历；985、211为演示院校字典标签，211包含985。 |
| `people.first_major` | 专业 | education | 当前教育记录第一专业 | 第一专业、所学专业 | 以字段定义为准。 |
| `people.diploma_code_desc` | 学历 | education | 高中及以下、专科、本科、硕士研究生、博士研究生；硕士及以上包括博士 | 文化程度、学历背景 | 不是学位；“硕士及以上”包含博士，“硕士”精确学历不包含博士。 |
| `people.degree_code_desc` | 学位 | education | 无学位、学士、硕士、博士；与学历分开 | 学位、博士学位 | 不是学历；学位和学历不能互相推断。 |
| `people.full_time_flag` | 是否全日制 | education | 是、否或未知 | 学习形式、全日制 | 以字段定义为准。 |
| `people.education_expired_date` | 毕业时间 | education | 演示假设等同教育结束日期，真实源待确认 | 毕业日期、教育结束时间 | 以字段定义为准。 |
| `people.hire_type_code_desc` | 招聘类型 | employment | 校园招聘或社会招聘；未知不判为校园招聘 | 校招、社招、招聘来源 | 以字段定义为准。 |
| `people.labour_type_code_desc` | 用工类型 | employment | 正式、外包、实习 | 外包、用工性质 | 以字段定义为准。 |
| `people.position_code_desc` | 岗位 | employment | 当前岗位名称，无前一岗位历史 | 职位、现岗位 | 以字段定义为准。 |
| `people.current_employment_start_date` | 当前任职开始日期 | employment | 仅当前任职开始，不表示完整调岗事件 | 当前任职时间、现岗位起始日 | 不是入职时间，也不能推出上一个岗位。 |
| `people.confirmation_date` | 转正日期 | employment | 实际已转正日期，不是预计日期 | 实际转正日 | 以字段定义为准。 |
| `people.formalize_flag` | 是否已转正 | employment | 是或否，需与转正日期一致 | 转正状态 | 以字段定义为准。 |
| `people.contract_type_code_desc` | 合同类型 | contract | 合同类型说明，独立字段权限组 | 合同性质 | 以字段定义为准。 |
| `people.contract_end_date` | 合同到期日期 | contract | 允许查询未来到期日期，空值不视为即将到期 | 合同截止日、合同到期时间 | 以字段定义为准。 |

## 指标

所有指标先与当前授权范围取交集。零分母返回空值，比例分母含未知，平均数排除未知；四舍五入保留两位小数。

| ID | 名称 | 单位 | 依赖字段 | 口径 |
|---|---|---|---|---|
| `metric.count` | 人数 | 人 | person_id | 符合当前人群与筛选条件的去重员工人数 |
| `metric.hires` | 入职人数 | 人 | onboard_date | 期间入职人数，不要求现在仍在职 |
| `metric.departures` | 离职人数 | 人 | termin_date | 期间离职人数 |
| `metric.net_change` | 净增人数 | 人 | onboard_date, termin_date | 期间入职减离职 |
| `metric.masters_count` | 硕士及以上人数 | 人 | diploma_code_desc | 当前学历为硕士研究生或博士研究生人数 |
| `metric.masters_ratio` | 硕士及以上占比 | % | diploma_code_desc | 硕士及以上人数/同组全部人群；未知学历计入分母 |
| `metric.doctors_count` | 博士学位人数 | 人 | degree_code_desc, education_expired_date | 当前已取得博士学位人数 |
| `metric.school_985_count` | 985人数 | 人 | school_name | 当前教育院校在演示985字典中的人数 |
| `metric.school_211_count` | 211人数 | 人 | school_name | 当前教育院校在演示211字典中的人数，包含985 |
| `metric.school_985_ratio` | 985占比 | % | school_name | 985人数/同组全部人群，未知院校仍计入分母 |
| `metric.school_211_ratio` | 211占比 | % | school_name | 211人数/同组全部人群，不能与985相加 |
| `metric.outsource_count` | 外包人数 | 人 | labour_type_code_desc | 用工类型为外包人数 |
| `metric.outsource_ratio` | 外包占比 | % | labour_type_code_desc | 外包人数/同组全部人群 |
| `metric.avg_age` | 平均年龄 | 岁 | birth_date, age | 快照日有效周岁平均值，未知不入平均，另给有效样本数 |
| `metric.avg_confirmation_days` | 平均转正用时 | 天 | confirmation_date, onboard_date | 有效转正日期减入职日期的平均天数 |

## 20 个演示问题

对应 `evaluation/cases.json`；预期计划在 `plans.json`，独立基准在 `golden.json`。

- **HR-01**：我的直属和间接下属按部门分别有多少在职人员？同时给出合计。
- **HR-02**：我服务的各部门在职人数、硕士及以上人数和占比分别是多少？
- **HR-03**：我通过下属 HRBP 能查看哪些部门？每个部门有多少在职员工？
- **HR-04**：上周入职人员的工号、姓名、学校、专业、年龄和毕业时间分别是什么？按入职时间从新到旧排列。
- **HR-05**：过去15天，平台研发部和智能产品部分别入职、离职多少人，净增多少？
- **HR-06**：统计今年4月至7月各部门每个月的离职人数。
- **HR-07**：今年4月至7月，平台研发部和智能产品部每月的入职、离职及净增人数对比。
- **HR-08**：上季度入职的员工中，目前已取得博士学位的有多少？按部门统计。
- **HR-09**：平台研发部和智能产品部目前985、211毕业员工各有多少，占部门在职人数的比例分别是多少？
- **HR-10**：清华大学或北京大学毕业的在职员工，按部门分别有多少？
- **HR-11**：我能查看的在职员工，按学历和是否全日制交叉统计人数。
- **HR-12**：平台研发部30至40岁、第一专业为计算机科学与技术或软件工程的在职员工有哪些？列出姓名、专业、学历和年龄。
- **HR-13**：今年校园招聘入职、目前学历为硕士及以上且全日制的员工，列出姓名、部门、学校和入职日期。
- **HR-14**：各部门目前外包人员占在职人员的比例是多少？同时展示外包人数和在职总人数。
- **HR-15**：对比平台研发部和智能产品部的在职人数、平均年龄以及硕士及以上比例。
- **HR-16**：未来90天合同到期的在职员工有哪些？按到期日排序，列出姓名、部门、合同类型和到期日期。
- **HR-17**：今年已经转正的员工，各部门有多少人？从入职到转正平均经过多少天？
- **HR-18**：当前任职开始日期在过去30天内的在职员工有哪些？列出姓名、部门、岗位和当前任职开始日期。
- **HR-19**：在刚才清华或北大毕业的这些人中，只看硕士及以上、全日制员工，再按部门统计。
- **HR-20**：把学校改成浙江大学，其他条件不变，并列出姓名、部门、学校、学历和专业。
