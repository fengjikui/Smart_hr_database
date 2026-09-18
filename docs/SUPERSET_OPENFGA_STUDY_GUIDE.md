# Superset 与 OpenFGA：企业智能问数权限学习指南

编写及资料核对日期：2026-09-18。建议学习时间：90～120 分钟。

适用对象：需要向主管、业务负责人或技术同事解释方案，并准备承担权限配置工作的开发人员。

本文以“企业已有多个数据库或数据湖，不能修改原业务系统的写入程序，我们开发 Agent 来查询数据”为背景。HR 汇报线只是用于讲清关系权限的例子；同样的分析可以用于销售区域、项目成员、客户归属等场景。

**本文的核心判断：Superset 是带权限管理的分析平台；OpenFGA 是独立的授权判断引擎。两者都能参与实现数据权限，但承担的工作不同。选择成熟框架可以复用机制，不能替代业务规则、正确集成和测试。**

## 0. 怎么用这篇文档学习

### 0.1 学习路线

| 顺序 | 建议时间 | 阅读内容 | 学完应该能做什么 |
|---|---:|---|---|
| 第一轮 | 15 分钟 | 第 1～3 节 | 讲清身份、规则、关系、权限执行，以及两款产品的区别 |
| 第二轮 | 20 分钟 | 第 4 节 | 解释 Superset 如何控制表、行、列，为什么自由 SQL 要单独评估 |
| 第三轮 | 25 分钟 | 第 5 节 | 读懂 OpenFGA 模型、关系元组与一次权限检查 |
| 第四轮 | 15 分钟 | 第 6～8 节 | 回答同步、Agent 接入、性能和撤权问题 |
| 第五轮 | 10 分钟 | 第 9～10 节 | 解释谁负责配置，并给出有条件的选型建议 |
| 第六轮 | 20 分钟 | 第 11～12 节 | 做自测或演示，练习向别人讲解 |

合计约 105 分钟。如果只有 60 分钟，先读第 1～3 节、4.3～4.6、5.2～5.5、7.1、10、12 节；其余作为查阅材料。

快速跳转：[Superset 实现](#4-用-superset-实现具体怎么做) · [OpenFGA 实现](#5-用-openfga-实现具体怎么做) · [数据同步](#6-不改原业务程序如何同步关系与身份) · [Agent 接入](#7-接入智能-agent-时权限应该放在哪里) · [自测](#115-十道自测题) · [讲解稿](#12-练习向别人讲清楚) · [出处](#13-出处与后续阅读索引)

### 0.2 证据如何区分

- **官方能力**：正文链接到官方文档或固定版本源码，第 13 节集中提供阅读索引。
- **本项目实现**：来自仓库中的独立 Superset、OpenFGA 实验，不代表所有产品默认如此。
- **接入建议**：为你们场景提出的工程设计，还需要结合真实基础设施验证。
- **教学例子**：用于解释概念，明确标注简化之处，不应直接当作生产规则。

Superset 实验固定为 **6.1.0**，PostgreSQL 为 **17.11**；OpenFGA 实验为 **1.20.0**，官方 CLI 为 **0.7.20**。这不是“它们永远是最新版本”的声明。Superset 正文尽量引用 6.1.0 文档；OpenFGA 官方文档为滚动更新，部署时还要对照固定版本实际支持的接口和配置。

本文读取并核对了既有代码和测试报告。既有报告分别生成于 2026-09-15、2026-09-16；不能把本文日期当成所有实验重新运行的日期，也不据此承诺本地服务当前正在运行。

## 1. 先把我们要解决的问题说准确

### 1.1 目标不是只有“判断能不能打开一个页面”

用户提出：

> 统计我负责区域今年各产品线的销售额，并列出金额最大的十个客户。

系统必须同时回答：

1. 用户身份是否真实、当前是否有效？
2. 他能不能查询销售数据？
3. 他负责哪些区域或客户，哪些记录应进入统计？
4. 他能不能读取客户名称、手机号、合同金额？
5. 他是否只能看汇总，能否看明细、导出？
6. 修改组织关系后，旧授权、旧缓存、历史结果什么时候失效？

其中第 3 点是行范围，第 4 点是字段使用范围，第 5 点是操作与使用方式。它们不能合并成一个“有查询权限”的布尔开关。

### 1.2 企业常见的权限组合

以下为教学归纳，不是你们公司已经确认的政策。

| 模型或限制 | 例子 | 规则需要依赖的数据 |
|---|---|---|
| RBAC：按角色 | 财务分析师可查询收款表 | 用户属于哪些经过批准的角色 |
| ABAC：按属性 | 华东销售只能查华东客户 | 用户区域、记录区域、有效状态 |
| ReBAC：按关系 | 项目成员查看项目；主管查看下属 | 项目成员关系、汇报关系、服务关系 |
| 库、表级授权 | 允许财务库的发票表，禁止薪资表 | 数据资源目录与授权列表 |
| 列级禁止 | 普通分析师不能使用身份证号 | 字段分类与允许的使用方式 |
| 列脱敏 | 可以看到部分手机号，不能看到完整号码 | 脱敏规则、用户身份 |
| 聚合限制 | 可以查薪资均值，不能查个人薪资 | 批准指标、最小分组人数等规则 |
| 时间与例外授权 | 审计人员在一周内获得特定访问权 | 审批记录、有效时间、例外范围 |

它们经常叠加。例如：“已在职的华东销售主管，可以看管理范围内的订单，但客户手机脱敏，只能导出批准字段”。

**职位高不等于所有数据都能看。** 职位只是可能参与授权的一个属性；是否能看薪资、医疗等信息，应由相应数据负责人确认。

### 1.3 不能改原业务程序，不代表不能增加查询侧控制

可以保留原来的入职、调岗、订单写入程序，在查询侧增加受控入口。但必须确认拥有哪种接入条件：

| 条件 | 可以考虑的路径 |
|---|---|
| 企业已经有数据权限平台和统一查询入口 | 优先复用现有身份、策略与执行边界 |
| DBA 允许建立专用只读账号、视图或数据库策略 | 可以在数据库侧建立更直接的执行约束 |
| 允许部署统一查询引擎，但不能修改源数据库结构 | 评估查询引擎的权限插件与数据连接器 |
| 只有源库读取权限 | 可由受控后端执行授权；责任集中在后端，不能宣称源库本身已受保护 |

其他系统独立直连源库时，不会自动受到我们 Agent 的权限规则约束。要保护全公司的所有访问路径，需要企业统一治理访问入口，而不仅是接好一个 Agent。

## 2. 一个权限系统至少有四项工作

| 工作 | 回答的问题 | 例子 |
|---|---|---|
| 身份认证 Authentication | 你是谁？ | 企业 SSO 确认当前登录人为用户 1003 |
| 策略管理 Policy Administration | 应该允许什么？ | 配置主管可以查看管理链下属 |
| 授权判断 Authorization Decision | 这次请求允许吗？ | 用户 1003 是否能查看员工 2008 |
| 权限执行 Enforcement | 如何确保只交付允许的数据？ | 在数据库查询中限制范围、拒绝敏感列 |

人员关系、角色、账号状态是这些判断的输入，通常来自身份平台、业务主数据或经过审批的授权配置。

OpenFGA 的基本工作是：使用授权模型和关系元组，对“用户—关系—对象”进行判断。它的输入不是任意 SQL，输出也不是自动改写后的 SQL。[F1：OpenFGA Concepts](https://openfga.dev/docs/concepts)

Superset 则把用户、角色和数据集权限结合在分析产品里，在相应查询路径上执行数据集行过滤；它依赖底层数据库连接执行实际 SQL。[S1：Superset 6.1.0 Security](https://superset.apache.org/admin-docs/6.1.0/security/)

**两种方案都需要可信身份。** 浏览器传来的 `person_id`、用户在问题中声称的岗位、模型生成的角色名称，都不能直接作为授权依据。

## 3. 能力对照：不要把它们当成同一种产品

下表结合官方能力与本项目实现作工程归纳，详细机制在后文展开。

| 关注点 | Superset | OpenFGA |
|---|---|---|
| 产品定位 | 数据探索、图表、看板、SQL 分析平台 | 独立的细粒度授权服务 |
| 自带展示能力 | 有图表、看板、筛选等分析界面 | 不提供企业问数、报表产品 |
| 用户和权限管理界面 | 有角色、数据集、RLS 等管理界面 | 有开发建模工具；企业业务配置界面通常需另建或集成 |
| 库、表访问 | 管理分析平台中的数据库、数据集访问 | 可把库表建模为资源，但需接入系统执行判断 |
| 行范围 | 数据集 RLS 条件进入查询 | 对资源作 Check/BatchCheck，或查询授权对象集合；SQL 限制由接入层处理 |
| 列禁止、脱敏 | 可结合受限视图、专用连接和数据集；仅隐藏展示列不足以保护数据 | 可定义查看敏感字段等动作；实际删列、遮罩和禁止使用由接入层处理 |
| 递归关系 | 通常由数据库 SQL、授权表或外部服务表达 | 可以在授权模型中声明关系继承，由引擎求值 |
| 任意业务数据同步 | 不自动理解入职、汇报线等业务含义 | 不自动从企业数据库发现并同步业务关系 |
| 大范围统计 | 由底层数据库完成过滤、关联、聚合 | 需解决授权集合与数据库统计如何结合 |
| 多个应用共用同一授权服务 | 不是它的主要产品定位 | 是适合考虑的使用方式 |
| 自动保护所有直连 SQL | 不会 | 不会 |
| 采用后是否无需自研 | 仍需配置、映射、接入、测试 | 仍需模型、同步、执行层、管理流程、测试 |

官方基础阅读：[S1](https://superset.apache.org/admin-docs/6.1.0/security/)、[F1](https://openfga.dev/docs/concepts)、[F5：授权查询 API](https://openfga.dev/docs/interacting/relationship-queries)。

两句话的差别：

- Superset 路线：**在已有分析平台的受控查询过程中应用权限。**
- OpenFGA 路线：**由独立引擎计算权限，查询系统接收并执行结果。**

## 4. 用 Superset 实现：具体怎么做

### 4.1 数据和配置分别放哪里

以本项目独立实验为例：

| 内容 | 存放位置 | 谁维护 |
|---|---|---|
| 员工、学历、主管、HRBP 等事实 | PostgreSQL 业务表 `hr.people` | 原业务系统或数据平台 |
| 登录用户与业务人员映射 | `authz.identity_map` | 可信身份接入流程 |
| 管理线、HRBP、继承开关 | `authz.role_policy` | 权限管理员按业务批准配置 |
| 递归规则及授权集合 | `authz.management_closure` 等 SQL 视图 | 开发或数据工程人员 |
| 数据连接、数据集、角色、RLS 条件 | Superset 元数据库 | Superset 管理员 |
| 指标解释、字段别名 | Agent 语义目录，可与平台目录联动 | 业务与数据治理人员 |

我们没有修改 Superset 源码来加入这些规则；配置脚本使用它已有的数据集、角色和 RLS 机制。SQL 视图是我们编写的业务授权规则。

实现位置：`integrations/superset/schema.sql`、`bootstrap.py`、`superset_config.py`。可对照 [P1：当前实验说明与代码](https://github.com/fengjikui/Smart_hr_database/tree/0a738ed0410be6303e8b8b46a7027ab23230bd1d/integrations/superset)。

### 4.2 第一步：定义安全的数据出口

教学例子：同一员工表中既有姓名、学历，又有薪资。

建立两个数据库视图：

```sql
-- 需要有权限的管理员创建；不要求改动原业务写入程序。
CREATE VIEW analytics.people_public AS
SELECT person_id, name, department, education, school
FROM hr.people;

CREATE VIEW analytics.people_private AS
SELECT person_id, name, department, education, school, salary
FROM hr.people;
```

再为公共连接和敏感连接配置不同的数据库账号：前者只能读取公共出口，后者在授权后读取敏感出口。需要检查并移除通过其他角色、原表或其他视图获得的间接访问权。`CREATE VIEW` 本身不等于完成授权隔离。

在 Superset 中分别登记对应数据集，把访问权赋给批准的业务角色。普通用户不获得任意数据库访问、管理权限或自由 SQL 权限。

这里保护的是“这个入口能读哪些列”。两种视图仍然需要正确的行范围规则。只有数据集里不展示薪资、但底层连接仍能被普通用户用于自由查询薪资时，不能算列权限已经完整落实。

本项目使用上述“数据库出口＋连接账号＋数据集授权”的组合，具体 `GRANT` 和视图定义见 [P1](https://github.com/fengjikui/Smart_hr_database/blob/0a738ed0410be6303e8b8b46a7027ab23230bd1d/integrations/superset/schema.sql)。

### 4.3 第二步：配置谁能看到哪些行

简单规则可以是：

```sql
region_code = 'EAST'
```

动态人员范围则可以引用一个已定义的授权视图。本项目配置为：

```sql
person_id IN (
  SELECT target_id
  FROM authz.visible_people
  WHERE superset_user_id = {{ current_user_id() }}
)
```

逐项解释：

- `person_id`：当前被查询人员的主键。
- `target_id`：该登录用户有权查看的人员。
- `current_user_id()`：Superset 已认证用户的内部 ID，不是天然等于 HR 的 `person_id`。
- `authz.visible_people`：由我们定义的数据库对象，提供用户与可见人员的映射。

用户身份应来自认证上下文，不能改为读取模型提供的“用户 ID”。动态 Jinja 模板要由受信任的配置人员维护，不让模型或普通查询者自由编辑。[S2：6.1.0 SQL Templating](https://superset.apache.org/admin-docs/6.1.0/configuration/sql-templating/)

在 6.1.0 管理界面中，可以从 Security 下的 Row Level Security 配置名称、数据集、规则类型、角色和条件。本项目以 **Base、无豁免角色** 绑定公共和敏感数据集；这是当前实验策略，不意味着管理员丧失了修改策略的管理能力。

需要区分几项语义：Regular 对匹配角色应用；Base 对豁免角色之外的用户应用；同一非空 group key 中的过滤器按 OR 合并，不同组按 AND 合并。因此，“有两个角色”不自动等于“两个行范围取并集”。[S1：RLS 配置语义](https://superset.apache.org/admin-docs/6.1.0/security/#row-level-security)

例如，同时要求区域匹配和在职，应采用交集；允许查看销售部门或市场部门，可能采用同组并集。生产时要明确：允许规则、禁止规则、例外授权怎么组合，不能依靠管理员的直觉操作。

### 4.4 第三步：汇报线在哪里计算

Superset 不知道你们公司的 `head_person_id` 是主管字段。要先把这种业务关系表达出来。

以下是独立的简化教学 SQL，只处理“本人和管理下属”，不包括 HRBP、角色开关及账号状态。`$1` 是由受信任后端绑定的查看人 ID：

```sql
WITH RECURSIVE visible(person_id) AS (
  SELECT person_id FROM hr.people WHERE person_id = $1
  UNION
  SELECT p.person_id
  FROM hr.people p
  JOIN visible v ON p.head_person_id = v.person_id
)
SELECT p.person_id, p.name, p.department
FROM hr.people p
JOIN visible v USING (person_id);
```

这里用 `UNION` 对单一 ID 去重，避免关系有环时无限重复；但“查询能终止”不等于“有环的组织数据应该被接受”。正式流程仍应校验数据质量。

本项目采用更完整的视图链：

```text
人员事实＋角色开关＋身份映射
    → management_closure：管理线展开，记录环
    → person_access：合并本人、管理线、HRBP、继承来源
    → visible_people：按查看人和目标人员去重
    → Superset RLS 条件：限制当前查询范围
```

数据库负责递归算法执行，我们负责定义正确的 SQL。**SQL 也是声明式配置的一种表达，不是“用了 SQL 就不可靠”。** 差别在于后续维护者是否能理解、评审和测试这份规则，以及规则是否分散在多个系统里。

当前视图实现对整个样本中的管理环采取拒绝返回授权集合的处理，适合演示明确暴露问题；生产时还需决定故障隔离范围与告警方式。它每次可能展开大量管理关系，不应直接当作大规模最佳实现。[P1：SQL 实现](https://github.com/fengjikui/Smart_hr_database/blob/0a738ed0410be6303e8b8b46a7027ab23230bd1d/integrations/superset/schema.sql)

### 4.5 第四步：Agent 如何调用 Superset

有两个不同的目标，需要明确选择。

**路径 A：受控数据集查询。**

```text
企业登录 → 服务端身份映射
        → Agent 生成受约束查询计划
        → 校验数据集、字段、指标和过滤条件
        → 用对应的 Superset 身份调用图表数据 API
        → RLS → 数据库执行 → 结果返回 Agent
```

图表数据接口接收数据集、维度、指标等请求结构，不是把任何 SQL 字符串原样执行。下面是本项目调用方式的缩小版，`42` 仅为假设数据集 ID：

```json
{
  "datasource": {"id": 42, "type": "table"},
  "result_format": "json",
  "result_type": "full",
  "queries": [{
    "columns": ["person_id", "name", "department"],
    "metrics": [],
    "filters": [],
    "row_limit": 100,
    "orderby": [],
    "extras": {}
  }]
}
```

对应 `POST /api/v1/chart/data`；实际 ID、可用字段、认证、CSRF 和接口结构按部署版本处理。当前实验通过真实接口调用验证，不是伪造返回数据。[P1：validate.py](https://github.com/fengjikui/Smart_hr_database/blob/0a738ed0410be6303e8b8b46a7027ab23230bd1d/integrations/superset/validate.py)

**路径 B：让模型生成自由 SQL。**

这与路径 A 不是同一难度。需要验证 SQL Lab 或选定执行接口的权限覆盖，以及 CTE、JOIN、子查询、未登记表、函数等边界。实验显式开启 `RLS_IN_SQLLAB`，但这不会自动把数据库里的所有对象都纳入 RLS。[S3：6.1.0 配置源码](https://github.com/apache/superset/blob/6.1.0/superset/config.py)

如果最终必须支持广泛自由 SQL，我建议把强制保护更多放在数据库或统一查询引擎中；Superset 可以继续作为分析界面。不要把“模型已经被提示只写安全 SQL”当作授权机制。

两个必须避免的接法：

- 所有人共用一个 Admin token，只在问题里附上业务用户 ID。Superset 实际看到的仍是管理员。
- Agent 直接连接数据库，却以为旁边部署了 Superset 就能受到其权限限制。

OA 或 SSO 的令牌也不会自动成为 Superset 的有效调用令牌，需要部署支持的认证集成和可靠用户映射。MCP 改变工具调用形式，不自动解决身份与权限问题。

### 4.6 Superset 做到了什么，还没做到什么

Superset 为我们提供了分析界面、角色和数据集管理、RLS 应用位置；可复用价值是真实的。但官方明确把它与数据库防火墙区分开，要求数据库最小权限等底层控制。[S1：SQL 执行边界](https://superset.apache.org/admin-docs/6.1.0/security/#sql-execution-security-considerations)

项目中的一个关键反例：专门增加 SQL Lab 权限的测试账号，可以查询底层可读、但未登记为受限数据集的 `analytics.unregistered_probe`，得到 12 人；它的正常数据集查询只应看到员工 E。这个反例说明数据集保护有覆盖边界，**不是说生产应该保留这个绕行入口**。[P2：27 项既有实验记录](https://github.com/fengjikui/Smart_hr_database/blob/0a738ed0410be6303e8b8b46a7027ab23230bd1d/reports/superset-permissions-local.json)

我们仍需负责：业务 SQL 规则、用户映射、列出口、账号权限、接口选择、配置发布、缓存撤权、测试与审计。当前实验没有实现数据库原生行安全策略。

**停下来复述：** Superset 中的 RLS 是怎么知道“当前用户”的？谁算出了间接下属？为什么同库另一个可读视图可能成为绕行路径？

## 5. 用 OpenFGA 实现：具体怎么做

### 5.1 两类配置不是同一个文件

| 内容 | 例子 | 保存方式 |
|---|---|---|
| 授权模型 | “允许本人或管理链上级查看” | 可以用 `.fga` 文件管理，再通过 API 发布模型 |
| 关系元组 | “D 是 E 的主管” | 通过 API 写入 OpenFGA 的关系存储 |

模型变化相对少，关系变化可能很多。把几十万条业务关系塞进一个人工维护的 `.fga` 文件，不是这里的设计。

`user:D` 表示请求访问的用户；`employee:D` 表示作为数据资源的员工 D。两者通过 `owner` 关系关联。元组中的 `user` 字段还可以放资源，例如 `employee:D`；字段名称不代表只能存自然人账号。[F1](https://openfga.dev/docs/concepts)

### 5.2 先读懂一个完整、最小的模型

下面是独立的教学模型，**仅用于解释本人和汇报线**；它没有账号有效性、管理角色开关、HRBP 或敏感字段规则，不能直接替换现有演示的完整模型。

```fga
model
  schema 1.1

type user

type employee
  relations
    define owner: [user]
    define manager: [employee]
    define direct_manager: owner from manager
    define management_chain: direct_manager or management_chain from manager
    define view_basic: owner or management_chain
```

逐行解释：

| 配置 | 含义 |
|---|---|
| `owner: [user]` | 哪个用户对应这条员工资源 |
| `manager: [employee]` | 这名员工的直属主管是哪条员工资源 |
| `owner from manager` | 先找到直属主管，再找到主管对应的用户 |
| `direct_manager or management_chain from manager` | 直属主管，或者直属主管的管理链上级 |
| `owner or management_chain` | 员工本人或管理链上级有权查看 |

其中 `or` 表示授权来源取并集；`and` 可表达多个条件必须同时满足。我们定义业务含义，引擎执行模型求值。[F2：建模设计原则](https://openfga.dev/docs/best-practices/modeling-design-principles)

### 5.3 再写入实际关系

设王五管理李四，李四管理张三，对应稳定 ID 分别为 A、B、C：

| 元组的 user | relation | object | 读法 |
|---|---|---|---|
| `user:A` | `owner` | `employee:A` | 账号 A 对应员工 A |
| `user:B` | `owner` | `employee:B` | 账号 B 对应员工 B |
| `user:C` | `owner` | `employee:C` | 账号 C 对应员工 C |
| `employee:A` | `manager` | `employee:B` | A 是 B 的主管 |
| `employee:B` | `manager` | `employee:C` | B 是 C 的主管 |

注意方向：元组 `(employee:B, manager, employee:C)` 表示“B 是 C 的主管”。如果画成“员工指向其主管”的图，则应画为 `C → B → A`。两种表示不能混读。

下面是关系写入请求体；假设已经创建 Store 并发布上述教学模型：

```json
{
  "writes": {
    "tuple_keys": [
      {"user": "user:A", "relation": "owner", "object": "employee:A"},
      {"user": "user:B", "relation": "owner", "object": "employee:B"},
      {"user": "user:C", "relation": "owner", "object": "employee:C"},
      {"user": "employee:A", "relation": "manager", "object": "employee:B"},
      {"user": "employee:B", "relation": "manager", "object": "employee:C"}
    ]
  }
}
```

发送到 `POST /stores/{store_id}/write`。真实环境还要使用受保护的管理调用身份。API 与 SDK 的参数包装不完全相同，上例是 HTTP JSON 请求体。[F3：写入与删除关系](https://openfga.dev/docs/getting-started/update-tuples)

我们不必额外写入“A 是 C 的间接主管”；它由模型推导。

### 5.4 发起一次权限检查

```json
{
  "authorization_model_id": "实际发布得到的模型ID",
  "tuple_key": {
    "user": "user:A",
    "relation": "view_basic",
    "object": "employee:C"
  },
  "consistency": "HIGHER_CONSISTENCY"
}
```

发送到 `POST /stores/{store_id}/check`。在上述教学事实下，检查 A 查看 C 的 `allowed` 为 `true`；检查 C 查看 A 则为 `false`。[F4：Check 接口](https://openfga.dev/docs/getting-started/perform-check)

这里有两个重要的工程边界：

1. 引擎返回的是授权结论，不是员工姓名、薪资或 SQL 结果。
2. `HIGHER_CONSISTENCY` 控制 OpenFGA 查询自身存储时的缓存使用；它不会让尚未从 HR 数据库同步过来的变更凭空出现。[F8：一致性选项](https://openfga.dev/docs/interacting/consistency)

### 5.5 当前项目如何增加角色、HRBP、字段权限

实际模型比教学版多了一层资格与能力判断：

```text
管理来源 = 管理链关系 ∩ 已启用管理查看能力
HRBP 来源 = 直接服务关系 ∩ 已启用 HRBP 能力
继承来源 = 下属 HRBP 服务关系 ∩ 已启用继承能力

基本可见 = (本人 ∪ 管理来源 ∪ HRBP 来源 ∪ 继承来源)
           ∩ 访问者账号有效

敏感字段可见 = 基本可见 ∩ 敏感字段能力
允许导出     = 基本可见 ∩ 导出能力
```

实际 DSL 的末尾是：

```text
define report_grant: management_chain and reports_capability
define hrbp_grant: direct_hrbp and hrbp_capability
define inherited_hrbp_grant: inherited_hrbp and inherit_capability
define candidate: owner or report_grant or hrbp_grant or inherited_hrbp_grant
define view_basic: candidate and active_user
define view_private: view_basic and private_capability
define can_export: view_basic and export_capability
```

这里的 `active_user` 约束的是**访问者**。某员工离职后，他的账号不能查询，不代表其他有权限人员必须看不到那条离职员工记录。这是两条不同政策。

HRBP 还有一个容易出错的地方：HRBP C 服务主管 J，不自动等于 C 能查看 J 的全部下属。管理链递归与 HRBP 服务关系需要分开建模，否则可能把“能查看某人”错误传播成“能查看这个人有权查看的所有人”。

对应 [P3：实际 model.fga](https://github.com/fengjikui/Smart_hr_database/blob/0a738ed0410be6303e8b8b46a7027ab23230bd1d/integrations/openfga/model.fga)。

**两个实验存在一个刻意保留的语义差异：** Superset 实验的继承 HRBP 要同时启用 `reports` 和 `inherit_hrbp`；OpenFGA 实验把管理查看与 HRBP 继承做成独立开关。默认样本的主要结果相同，不表示任意开关组合都完全等价。以后对比框架性能前，应先统一业务政策。

### 5.6 一条实际查询如何执行

当前 OpenFGA 演示的后端做这些工作：

1. 读取演示查看人和候选人员；真实上线时应替换为可信登录身份。
2. 向真实 OpenFGA Server 发送 BatchCheck，检查多个目标和动作。
3. 只保留 `view_basic` 允许的记录。
4. 对没有 `view_private` 的记录不返回薪资值。
5. 导出时重新检查 `can_export`，不允许就拒绝。
6. 判断失败、返回不完整时停止查询，不换成无权限限制的路径。

本地演示会检查全部合成候选人员，并使用内存数据形成结果；它尚未把任意模型 SQL 接到企业数据库。当前参数中的每批 50 项是实验的批处理选择，不是在声明 OpenFGA 所有版本的固定上限。[P3：core.py](https://github.com/fengjikui/Smart_hr_database/blob/0a738ed0410be6303e8b8b46a7027ab23230bd1d/integrations/openfga/core.py)

OpenFGA 不会自动把 `salary` 替换成 `NULL`；这是后端根据引擎决定进行的执行动作。同样，若未来禁止某字段参与过滤、关联或排序，也需要执行层检查，不能只把返回值涂黑。

### 5.7 可配置到什么程度

| 改动 | 可以怎么做 |
|---|---|
| 更换某人的主管或 HRBP | 修改事实关系，写入、删除相应元组 |
| 某岗位对应另一个角色 | 修改岗位角色映射，并同步能力元组 |
| 某角色关闭导出 | 修改角色能力并发布关系变化 |
| 所有主管改为只看直属下属 | 发布新的规则模型，并运行正反例测试 |
| 新增项目成员、区域或时间条件 | 设计新模型或条件，增加同步映射和测试 |
| 让 HR 通过中文下拉框配置 | 由产品提供受控业务表单，映射到允许的模型和关系操作 |

OpenFGA 支持条件机制，可以表达部分属性与时间相关策略，但不会自动查询外部业务库来补齐任意条件所需的数据。[F10：Conditions](https://openfga.dev/docs/modeling/conditions)

授权模型按版本发布，不是在原模型上随意覆盖。调用时明确指定模型 ID，能避免新模型未经业务切换就被意外使用。模型版本固定也不等于关系数据成为同一份历史快照，关系变更仍需独立管理。[F9：不可变模型](https://openfga.dev/docs/getting-started/immutable-models)

本项目为方便隔离和恢复，每次发布创建新的 Store、模型和完整样本关系，再切换指针。这是几十人演示的实现，不建议把“每次员工调岗都全量新建 Store”当成生产同步方式。

### 5.8 从 HR 推广到通用库表列权限

OpenFGA 的资源类型可以由我们定义，不限于员工。下面是另一份独立教学模型，表达“用户必须既能查询所属表，又拥有这列的读取资格”。它不替换 5.2 的员工模型，也不能直接粘贴到当前 HR 实验的模型编辑器中，因为该界面要求保留 HR 接口需要的类型。

```fga
model
  schema 1.1

type user

type group
  relations
    define member: [user]

type table
  relations
    define reader: [user, group#member]
    define can_query: reader

type column
  relations
    define parent: [table]
    define reader: [user, group#member]
    define can_read: reader and can_query from parent
```

为财务分析组授权时，可以写入：

| user | relation | object |
|---|---|---|
| `user:alice` | `member` | `group:finance` |
| `group:finance#member` | `reader` | `table:finance.invoice` |
| `table:finance.invoice` | `parent` | `column:finance.invoice.amount` |
| `group:finance#member` | `reader` | `column:finance.invoice.amount` |

于是 Alice 对这张表的 `can_query`、对金额列的 `can_read` 都允许。对没有列级授权的字段，不能仅凭表可查就自动读取。

这说明 OpenFGA 可以表达表列资格，但字段发现、元组维护、SQL 字段解析和真正的查询限制仍由接入层完成。若再增加“只能看华东发票”，还要单独建模行范围；不能把 `table#can_query` 理解成整表每一行都允许。

资源应选择稳定、合适的粒度。比如亿级订单都按项目继承权限时，可以评估项目级授权，再由可信订单—项目关联约束 SQL；不必一开始就假设每个单元格都要同步成权限对象。粒度过粗又可能丢掉例外政策，所以要用具体业务反例验证。

**停下来复述：** `.fga` 文件和人员关系分别是什么？谁执行递归？谁把不允许的员工和字段从实际结果中去掉？

## 6. 不改原业务程序，如何同步关系与身份

### 6.1 同步输入输出契约

授权主数据仍可留在原系统。OpenFGA 只保存判断需要的关系；姓名、教育经历、订单金额等搜索与统计数据留在业务库。官方也建议把用于筛选、排序和关联的数据保留在业务数据库。[F7：Source of Truth](https://openfga.dev/docs/best-practices/source-of-truth)

假设收到如下**教学变更事件格式**，它不是所有 CDC 产品的固定协议：

```json
{
  "event_id": "event-000108",
  "source_position": "源系统可恢复的位置标识",
  "operation": "update",
  "before": {"person_id": "C", "manager_id": "B"},
  "after": {"person_id": "C", "manager_id": "D"}
}
```

同步程序输出：

```json
{
  "deletes": {
    "tuple_keys": [
      {"user": "employee:B", "relation": "manager", "object": "employee:C"}
    ]
  },
  "writes": {
    "tuple_keys": [
      {"user": "employee:D", "relation": "manager", "object": "employee:C"}
    ]
  }
}
```

OpenFGA 支持在一次 Write 请求中提交增删；请求大小和错误行为应按固定部署版本处理。这个请求不构成“源业务数据库＋OpenFGA”的跨系统事务。[F3](https://openfga.dev/docs/getting-started/update-tuples)

除了关系变更，还需记录事件处理状态、成功位置、失败原因和重试次数。API 成功后再推进已处理位置；重试要避免旧事件覆盖新关系，并处理重复写入或重复删除。

### 6.2 变更从哪里来

| 方式 | 是否要改业务程序 | 主要条件与代价 |
|---|---|---|
| 定时读取完整快照并比较 | 不用 | 需要读权限；读量随规模增长，有轮询延迟 |
| 按可靠更新时间增量读取 | 通常不用 | 需保证所有变化都更新时间；物理删除还要有删除记录或额外对账 |
| 数据库 CDC | 通常不用 | 需要管理员配置、日志读取权限和运维监控 |
| 原系统已有业务事件 | 已有接口则可直接接；否则需对方开发 | 语义清楚，但依赖事件契约与可靠投递 |
| 数据库触发器写变更表 | 不改业务程序，但要修改数据库对象 | 需管理员评审，对写入路径有影响 |

PostgreSQL 的逻辑解码能够从 WAL 提取变更。它需要处理消费位置、重复消息、复制槽积压等问题，不是“开个监听端口就完成可靠同步”。[D1：逻辑解码](https://www.postgresql.org/docs/current/logicaldecoding-explanation.html)

首次导入要衔接全量快照和增量起点：不能简单“先读完整表，过十分钟再开始监听”，否则中间变化可能丢失。采用支持一致性快照与增量衔接的工具或明确实现这一过程。

### 6.3 同步最容易漏掉的业务信息

- 字段是否表示正式生效的主管，还是待审批、未来生效的主管？
- 宽表每天刷新一次，是否已经比业务系统落后一天？
- 人员离职后记录删除，还是保留但禁用账号？
- 兼岗、虚线汇报、代理负责人、服务多个部门如何表达？
- 姓名不是唯一键；工号前导零不能丢；不同系统 ID 需要明确映射。
- 如果只有加工宽表，源表 CDC 不一定直接给出“加工结果变化”，可能仍需订阅宽表产出或重新计算映射。

这些问题无需阅读所有业务程序源码，但需要数据负责人确认语义。

### 6.4 “权限立即生效”要说清是哪一个时刻

```text
源系统变更提交
→ 数据进入查询宽表（如果有加工过程）
→ 同步程序读取并更新关系
→ 权限引擎按新关系判断
→ 查询缓存、历史结果和在途请求处理撤权
```

总撤权时间取决于整条链路。更高一致性的 OpenFGA Check 只能处理其中一部分。

对敏感权限，可以制定：同步延迟超过阈值时拒绝相关查询、禁止敏感导出、优先处理禁用账号等规则。这是需要与业务确认的设计，不是 OpenFGA 默认自动提供的完整流程。

Superset 若直接通过实时 SQL 读取源关系表，可省去这份 OpenFGA 关系副本；但 Superset 自身角色、身份映射、物化授权表或缓存仍可能需要同步、刷新。两条路线都不能把撤权延迟视为不存在。

## 7. 接入智能 Agent 时，权限应该放在哪里

### 7.1 建议的通用流程

```text
用户登录
   ↓
后端获得可信身份、账号状态、授权上下文
   ↓
只向模型提供允许使用的目录、字段描述和必要上下文
   ↓
模型生成查询意图、受约束计划，或待检查的 SQL
   ↓
受控执行层：验证对象、字段、操作与查询范围
   ↓
数据库／查询引擎强制执行行范围和字段规则
   ↓
对已授权数据做统计，形成结果
   ↓
自然语言解释、可视化、历史和导出继续受同一权限约束
```

这是接入建议，不是声称两套独立实验已与主 Agent 完成集成。现在原 HR 问数主系统、Superset 实验、OpenFGA 实验仍是分开的。

模型可以帮助识别“今年”“我负责的区域”等业务意图，但不能决定自己使用什么角色、绕过哪些字段或把管理员身份当作查询参数。

### 7.2 表权限、行权限、列权限怎样共同生效

假设销售分析师能看自己的区域订单，不能使用完整手机号：

1. **表级**：订单表允许，薪资表拒绝。
2. **行级**：仅允许区域内的订单进入查询。
3. **列级**：完整手机号不能被选择、拼接、过滤、关联、排序或通过函数变换泄露，除非政策明确允许某种用法。
4. **聚合**：销售总额在授权记录内计算，不先算全公司总额再隐藏部分结果。
5. **结果使用**：导出、查看历史、打开缓存看板时重新确认有效权限。

例如，只隐藏 `salary` 的输出却允许：

```sql
SELECT name FROM employees WHERE salary > 100000;
```

用户仍可利用查询条件推断薪资。列权限的定义应说明它是否可参与计算与筛选，而不只是“返回时显示不显示”。

### 7.3 OpenFGA 判断如何落到 SQL

对于较小且完整取得的授权 ID 集合，后端可将其作为参数表、受控临时表等，与业务查询关联：

```sql
-- 概念示例：authorized_people 是后端建立、用户不可修改的完整授权范围。
SELECT e.department, count(*)
FROM employees e
WHERE EXISTS (
  SELECT 1 FROM authorized_people a WHERE a.person_id = e.person_id
)
GROUP BY e.department;
```

这个范围不是由模型填写的。若使用临时表或连接池，还需保证请求隔离、事务边界和清理，避免上一个用户的范围遗留给下一个用户。

权限范围很大时，不能机械地生成数十万项 `IN (...)`。可以评估经过版本管理的授权映射表、按资源边界收缩候选集、统一查询引擎或数据库策略。把关系计算结果物化到数据库是新增架构工作，**不是 OpenFGA 自带的任意 SQL 下推功能**。

如果先查询业务候选再逐项 Check，完整统计必须检查全部相关候选；只取前 100 条再过滤不能回答“总共多少人”。分页、排序和总数也需要专门设计。[F6：Search With Permissions](https://openfga.dev/docs/interacting/search-with-permissions)

### 7.4 真正的执行边界

数据库原生 RLS 与 Superset 数据集 RLS 不同：前者在数据库处理表访问时执行，后者在 Superset 相关路径构造查询时应用。

原生 RLS 也要正确配置执行身份。PostgreSQL 的超级用户、`BYPASSRLS` 角色和通常情况下的表所有者有特殊绕过语义；连接池账号也不天然等于当前业务用户。[D2：PostgreSQL 行安全](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)

不要让任意模型 SQL 可以修改一个 session 变量，再把那个变量当成不可伪造的用户身份。若要用身份上下文传递，必须设计它的可信设置者、可修改范围、SQL 能力限制和连接复位。

对多源自由查询，值得评估已有统一查询引擎的策略插件。例如 Trino 的 Ranger 集成支持库、模式、表、列授权，以及行过滤、列脱敏和审计。但它依赖相应入口、连接器与配置，不是安装 Ranger 后所有数据库直连自动受到控制。[D3：Trino Ranger 集成](https://trino.io/docs/current/security/ranger-access-control.html)

## 8. 性能怎么判断，哪些说法不能轻信

### 8.1 不要拿单条 Check 与全公司统计直接比较

| 工作负载 | Superset 路线的主要成本 | OpenFGA 路线的主要成本 |
|---|---|---|
| 查一名员工是否可见 | 接口、权限条件和数据库查询 | Check、关系遍历与实际数据读取 |
| 展示一页授权明细 | 数据库范围过滤、排序与分页 | 候选查询＋批量 Check，或取得范围后分页 |
| 全公司部门人数统计 | 数据库过滤、关联、分组 | 获取完整授权范围＋数据库过滤和分组 |
| 主管调岗 | 实时视图重算或物化范围更新 | 关系同步、增删元组和相关缓存处理 |
| HRBP 多层继承 | SQL 关系展开与索引 | 模型复杂度、关系扇出、交集计算 |

Superset 不负责替数据库完成大规模计算，OpenFGA 也不是数据仓库。比较的是完整架构，而不是两个产品名字。

### 8.2 OpenFGA 的规模注意点

官方列举了先搜索再 Check、取得授权对象再搜索等不同组合，选择取决于候选量、授权对象量和可见比例。模型越复杂、关系展开越多，成本也可能越大。[F6](https://openfga.dev/docs/interacting/search-with-permissions)

`ListObjects` 不是无限制的“全库可见 ID 导出器”。其结果受配置的数量、截止时间等限制；流式接口也有时限。生产配置文档还列出关系解析深度和并发限制。取得部分 ID 后不能冒充完整人员范围。[F11：生产运行建议](https://openfga.dev/docs/best-practices/running-in-production)、[F5](https://openfga.dev/docs/interacting/relationship-queries)

本项目只有 12 人的初始样本，输入上限为 50 人，后端检查候选与多个权限动作。48 项测试通过证明的是这些案例的功能，不是几十万人员的性能证明。

### 8.3 Superset 路线的规模注意点

本项目 SQL 会计算管理闭包。链很长时，“所有祖先—后代对”的数量可能远大于员工数量。可以评估按当前用户展开、索引、预计算授权表等，但物化又引入刷新与撤权延迟。

SQL 计划、数据分布、底层引擎、网络与结果缓存都会影响性能。直接在数据库做大范围关联和聚合往往更贴近这类工作负载，但需要实测，不能据此宣称 Superset 一定更快。

### 8.4 建议的性能验收设计

以下是测试设计示例，不是已经完成的测试：

| 维度 | 建议覆盖 |
|---|---|
| 人员／资源规模 | 先按真实规模，再测试增长后的规模；如 5 千、5 万、50 万资源 |
| 关系形态 | 深层管理链、主管大量直属、跨部门服务、多角色组合 |
| 权限占比 | 用户只看极少对象、看一半、看绝大多数 |
| 查询类型 | 单项 Check、明细分页、完整计数、分组汇总、导出 |
| 并发与缓存 | 冷缓存、热缓存；逐步增加并发，不只测一次 |
| 时延 | 端到端 P50/P95/P99、超时率、拒绝与错误是否区分 |
| 同步 | 正常延迟、批量调岗、暂停后追赶、撤权到真正不可读的耗时 |
| 资源 | 数据库扫描量、CPU、内存、网络请求数、服务错误率 |

两套方案必须使用相同数据、相同授权语义和相同查询范围。总耗时要包含授权、SQL、结果传输，不能只比较某个中间接口。

本机做性能实验时应先检查负载、可用内存及可取得的热状态，保守增加并发；较大规模测试优先安排独立环境。

## 9. 谁制定、谁配置、谁负责

### 9.1 建议的职责划分

| 角色 | 核心责任 | 不应独自承担什么 |
|---|---|---|
| 业务数据负责人 | 确认允许人群、字段、用途、例外 | 不必独自判断递归 SQL 或引擎集成是否安全 |
| 数据治理／安全团队 | 数据分级、跨域访问、审计与统一原则 | 不应脱离业务臆测所有具体授权 |
| 权限管理员／数据平台人员 | 在批准范围内配置、发布、撤销和检查 | 不应自行扩大业务访问资格 |
| DBA／查询平台管理员 | 账号、视图、执行入口、性能、数据库保护 | 不因技术上能授权就自动成为业务审批人 |
| Agent 开发者 | 可信身份接入、语义与查询执行、结果保护 | 不应让模型替代授权判断 |

组织可以集中管理，也可以把数据域的管理委托给业务侧，并保留统一底线。平台官方治理建议也区分集中、分布与混合模式。[D4：数据治理组织模式](https://docs.databricks.com/aws/en/lakehouse-architecture/data-governance/best-practices)

你可以承担技术配置者，但需要业务确认的规则、预期结果和审批人。否则“主管觉得应该能看”与“HR 认为不能看”会变成无法仅靠技术解决的冲突。

### 9.2 可视化配置应该长什么样

建议让业务管理员操作的内容：用户组、数据资源、允许动作、区域／部门范围、敏感字段模板、期限、例外理由。

建议由技术人员维护的内容：新关系类型、复杂递归、SQL 谓词模板、模型语法、身份映射契约、执行适配器。

不要让 HR 直接手写任意 SQL，也不必要求 HR 理解所有 DSL。可以把经验证的复杂规则包装成“管理范围：本人／直属／全部层级”等选项。

**可视化是编辑方式，不是可靠性证明。** 配置必须有默认拒绝、修改差异、正反例预览、受限发布权、审计和版本管理。界面和 Git 管理的配置文件可以并存。

### 9.3 一条可复用的政策记录

下面是建议的政策台账格式，不是 Superset 或 OpenFGA 原生配置语法：

```yaml
policy_id: sales_east_orders_read
owner: 销售数据负责人
subjects: 华东销售分析组
resources: sales.orders
actions: [query]
row_rule: 订单区域属于访问者已批准区域
columns: 订单号、日期、产品、金额、客户脱敏手机号
denied_usage: 完整手机号参与筛选、关联或导出
validity: 持续有效，成员变化后按撤权时限更新
positive_case: 华东成员查询华东订单允许
negative_case: 华东成员查询华南订单拒绝
```

先把这样的业务政策说清，再翻译为 Superset RLS、SQL 视图或 OpenFGA 模型，比一开始就讨论某行代码更容易达成一致。

## 10. 对我们项目的选择建议

### 10.1 根据交付目标选，而不是先认定某个框架

| 当下目标 | 更值得优先验证的路线 | 必须说明的边界 |
|---|---|---|
| 演示成熟引擎能配置汇报线、HRBP、调岗撤权 | 保留当前 OpenFGA 独立实验 | 它是关系授权能力证明，未完成通用 SQL 数据权限 |
| 快速交付受控数据集查询和分析看板 | Superset＋受限数据库出口 | 复杂关系仍需表达；自由 SQL 不等于受控图表查询 |
| 多个业务应用共用同一关系授权逻辑 | OpenFGA＋可靠同步＋各系统执行层 | 所有入口要正确集成，不能只接其中一个 |
| 全公司、多数据源、模型生成复杂 SQL | 先调查现有数据平台；评估查询引擎／数据库执行策略 | 重点是库表行列规则统一执行、身份、连接器与规模 |

这不是立刻把当前项目迁移到另一套技术的建议。现有实验用于学习和展示很有价值，下一步应拿真实基础条件验证最终选型。

### 10.2 两者能不能组合

可以，但组合意味着新增工程成本。例如：OpenFGA 管关系权限，服务把完整授权范围以受控方式交给查询层，Superset负责报表展示。

此时需要统一身份、配置版本、缓存和撤权。若一边维护 OpenFGA 规则，一边又独立手写一份 Superset 递归 SQL，两者容易产生不同结果。不能把“两个成熟产品叠加”直接等同于“更可靠”。

### 10.3 现在最需要确认的六件事

1. 源数据库、数据湖及统一查询引擎分别是什么，版本与规模是多少？
2. 是否已有 SSO、用户组、数据目录、审批平台和行列权限？
3. 我们能否创建只读账号、视图、策略、CDC，或只能查询现有宽表？
4. 最终查询是批准的数据集和指标，还是必须允许广泛的复杂 SQL？
5. 哪些字段禁止明细、允许聚合或需要脱敏；谁批准这些规则？
6. 撤权时限、并发、查询响应时间、导出量和审计保留要求是什么？

回答完这些，再决定 OpenFGA、Superset 是否承担核心角色，或者主要复用企业已有平台。

## 11. 动手学习、自测与验收

### 11.1 用现有两套实验看相同业务结果

先读各目录 README 的启动说明，确认本机负载允许，不要为阅读文档同时启动所有服务。

| 实验 | 页面（服务启动后） | 说明文件 |
|---|---|---|
| OpenFGA | `http://127.0.0.1:8091/` | `integrations/openfga/README.md` |
| Superset | `http://127.0.0.1:8088/` | `integrations/superset/README.md` |

凭据在本地忽略目录中生成，不写入本学习文档。不要把两个实验的管理接口开放给真实业务用户。

基于恢复初始配置后的合成样本，观察以下预期：

| 情景 | 预期 |
|---|---|
| 员工 E | 只能看到 E |
| 主管 D | 看到 D/E/F/G/H/I，共 6 人 |
| D 再限定“可信与 AI 实验室” | 看到 D/E/F/G，共 4 人 |
| HRBP C | 看到 C/D/E/F/G/J，共 6 人 |
| HR 负责人 B | 看到 B/C/D/E/F/G/J，共 7 人 |
| C 或 B 查询 K | 拒绝；不能通过已服务主管 J 间接扩大范围 |

“D 管理 6 人范围”包含 D 本人，以及其跨部门管理对象；不是“D 所在部门共有 6 人”。部门条件和授权范围要取交集。

这些预期来自两套实验的合成事实和人工预期集合，不是企业真实名单。证据：[P1](https://github.com/fengjikui/Smart_hr_database/tree/0a738ed0410be6303e8b8b46a7027ab23230bd1d/integrations/superset)、[P3](https://github.com/fengjikui/Smart_hr_database/tree/0a738ed0410be6303e8b8b46a7027ab23230bd1d/integrations/openfga)。

### 11.2 OpenFGA 练习：用配置证明能力

1. 恢复初始样本，查看主管 D 的 6 人范围。
2. 把管理规则切换为“仅直属”，发布，预期 D/E/F/H，共 4 人。
3. 恢复，再把 G 的主管从 F 改成 H，预期 F 失去 G、H 获得 G；D 仍为 6 人。
4. 恢复，关闭 HR 负责人的 HRBP 继承能力，预期 B 从 7 人变为 B/C 两人。
5. 查看真实 BatchCheck 请求与响应，说出是谁作出 `allowed` 判断。
6. 结束恢复初始样本，避免下一次演示从未知状态开始。

理解点：调岗修改关系；查看层级修改规则；敏感字段和导出修改动作能力。三类变化不能混成一种配置。

### 11.3 Superset 练习：追踪一个行过滤条件

1. 用员工身份和 HR 负责人身份打开同一人员看板，比较 1 人和 7 人。
2. 用实验管理身份找到相应数据集及 RLS 配置，读懂 `current_user_id()`。
3. 打开 `schema.sql`，从 `visible_people` 追到 `person_access` 和 `management_closure`。
4. 检查公共与敏感数据集分别使用哪个连接、数据库账号和视图。
5. 阅读未登记视图反例的测试代码，解释为何正常看板受限不代表所有 SQL 入口受限。

上述观察需在合成实验环境中做。不要直接在生产系统复制增加 SQL 权限的边界探针账号。

### 11.4 功能测试应该验什么

| 测试 | 预期及原因 |
|---|---|
| 未登录、身份映射缺失 | 不建立业务授权上下文；不能默认成管理员 |
| 普通员工访问别人 | 除明确授权外拒绝 |
| 跨部门管理 | 按真实政策判断，不把部门筛选误当全部权限 |
| HRBP 服务主管 | 不自动递归扩张到主管所有下属 |
| 禁止字段放在 WHERE、JOIN 或表达式中 | 按字段使用政策拒绝或执行批准的安全处理 |
| 行过滤后的统计 | 人数、比例分母与完整授权范围一致 |
| 重复服务来源 | 同一人员不重复计数 |
| JOIN 一对多 | 指标明确按人、按订单还是按明细计数 |
| 调岗、离职、权限关闭 | 旧授权按时撤销，新的正常授权符合规则 |
| 引擎或同步失败 | 明确错误或限制访问，不退回全量数据 |
| 多角色与规则冲突 | 按已经批准的并交集和禁止优先级执行 |
| 缓存、历史、导出、调试 | 不能成为绕过当前权限的第二入口 |
| 查询限额或授权集合截断 | 明确不能给出完整统计，不悄悄返回部分总数 |

测试预期最好是人工审核的小样本名单，不要只用与被测程序同一套算法生成“标准答案”。

现有报告：Superset 27 项、OpenFGA 48 项通过。它们覆盖各自演示范围，不代表此表中所有企业级要求均已实现。[P2](https://github.com/fengjikui/Smart_hr_database/blob/0a738ed0410be6303e8b8b46a7027ab23230bd1d/reports/superset-permissions-local.json)、[P4](https://github.com/fengjikui/Smart_hr_database/blob/0a738ed0410be6303e8b8b46a7027ab23230bd1d/reports/openfga-permissions-local.json)

### 11.5 十道自测题

先不看答案，用自己的话回答：

1. Superset 和 OpenFGA 各自是什么产品？
2. “不能改入职程序”是否意味着无法同步人员关系？
3. OpenFGA 的模型文件与关系元组有什么区别？
4. 为什么获得 `allowed=true` 仍不等于 SQL 已经被保护？
5. 为什么模型提示词中的“只能看本部门”不能作为权限保证？
6. 为什么给 Superset 所有请求使用同一个 Admin token 有问题？
7. 为什么“手机号不显示”与“手机号不能被使用”不同？
8. 为什么只 Check 前一页员工不能计算授权范围总人数？
9. `HIGHER_CONSISTENCY` 是否保证刚发生的业务调岗已经生效？
10. 业务负责人和权限管理员分别应该对什么负责？

参考答案：

1. 前者是分析平台，后者是授权判断服务；两者都需集成才能形成完整数据保护。
2. 不意味着。可以使用 CDC 或轮询等，但要有权限并确认字段及生效语义。
3. 模型表达通用规则，元组表达具体关系事实；关系不靠人工塞进模型文件维护。
4. 后端、数据库或查询引擎还必须限制实际数据访问。
5. 模型输出不能替代确定性的服务端执行约束，且用户可改变提问方式。
6. Superset 识别到的是同一个管理员，不能靠问题文本建立真实用户隔离。
7. WHERE、排序、函数和关联也能暴露或推断字段信息。
8. 未检查的记录可能仍符合条件，分页候选并非完整授权集合。
9. 不保证；它无法解决尚未完成的上游同步。
10. 业务方确认资格与用途，管理员按批准政策配置和维护，开发及平台团队保证正确执行。

## 12. 练习向别人讲清楚

### 12.1 一分钟说明

> 我们要解决的是：用户通过智能问数查询企业数据时，只能访问被授权的表、行、列。权限不能依赖模型自觉遵守。
>
> Superset 是分析平台，可以配置角色、数据集和行过滤，也能提供看板。复杂的汇报关系可以用数据库 SQL 或授权表表达，但它不会自动保护所有数据库访问。
>
> OpenFGA 是独立的权限引擎。我们配置规则、同步人员关系，由它计算谁能看谁；后端再把这个结果落实到查询、字段和导出。
>
> 我们已经分别验证了小规模演示。最终选型需要结合现有数据平台、是否要自由 SQL、行列策略、同步时效和数据规模。

### 12.2 五分钟说明顺序

| 时间 | 讲什么 | 举什么例子 |
|---|---|---|
| 第 1 分钟 | 业务目标和权限粒度 | 可以看订单表，不等于可以看全部区域和全部字段 |
| 第 2 分钟 | Superset 的路径 | 登录身份→数据集→RLS→数据库统计 |
| 第 3 分钟 | OpenFGA 的路径 | A 管 B，B 管 C；模型让 A 可以看 C |
| 第 4 分钟 | 必须由我们做的集成 | 同步关系、真实身份、SQL 执行、缓存撤权 |
| 第 5 分钟 | 当前证据与下一步 | 展示允许和拒绝；确认现有平台和性能验收条件 |

### 12.3 常见追问的稳妥回答

**“用了成熟框架，是不是就没有自写逻辑了？”**

不是。成熟框架提供通用机制，我们仍需写明业务规则和系统接入。减少的是自己实现一套授权求值机制或分析平台的工作，不能省略业务确认与测试。

**“Superset 做不了汇报线吗？”**

可以组合数据库递归 SQL 与 RLS 做到；OpenFGA 则能直接用关系模型表达递归。差别是规则表达位置、管理方式和复用边界。

**“为什么还要写同步程序？”**

如果组织关系的事实来源在企业数据库，OpenFGA 需要收到这些关系的变化。同步程序负责事实准确及时，引擎负责按事实求权。

**“谁更快？”**

单资源判断和大范围统计不是同一种工作。必须比较同一业务规则下的整条链路；当前几十人的演示没有证明生产性能。

**“可以全让业务人员点界面吗？”**

已有规则模板下的人员、角色和范围配置可以。新增复杂政策通常仍需技术建模、评审和测试，业务负责人负责确认含义。

**“怎么证明它可靠？”**

展示明确的规则、真实引擎请求、人工预期名单、越权反例、变更后撤权和故障拒绝；再补上真实规模和全部访问路径的验收。项目知名度不能单独证明我们的配置正确。

**“现在能不能直接全公司用？”**

目前完成的是独立的框架能力实验。真实 SSO、主数据同步、行列执行边界、管理审批、撤权时限和规模测试尚需接入与验收。

## 13. 出处与后续阅读索引

以下均为官方资料或本项目固定提交的代码、报告。核对日期为 2026-09-18；滚动文档后续可能变化。本文没有使用社区帖子作为产品能力的主要依据。

### Superset

| 编号 | 来源 | 建议关注 |
|---|---|---|
| S1 | [Superset 6.1.0 Security Configurations](https://superset.apache.org/admin-docs/6.1.0/security/) | Roles、RLS、SQL Execution Security Considerations；优先读相关段落 |
| S2 | [Superset 6.1.0 SQL Templating](https://superset.apache.org/admin-docs/6.1.0/configuration/sql-templating/) | 当前用户宏、模板的信任边界与缓存 |
| S3 | [Superset 6.1.0 config.py](https://github.com/apache/superset/blob/6.1.0/superset/config.py) | 查找 `RLS_IN_SQLLAB`、`ENABLE_TEMPLATE_PROCESSING`；以实际版本为准 |
| S4 | [Superset 6.1.0 security/manager.py](https://github.com/apache/superset/blob/6.1.0/superset/security/manager.py) | 深入研究数据集和 RLS 判断时的源码入口，不要求第一轮读完 |

### OpenFGA

| 编号 | 来源 | 建议关注 |
|---|---|---|
| F1 | [Concepts](https://openfga.dev/docs/concepts) | Type、Model、Tuple、User、Object |
| F2 | [Authorization Model Design Principles](https://openfga.dev/docs/best-practices/modeling-design-principles) | 如何按业务资源和关系建模 |
| F3 | [Update Relationship Tuples](https://openfga.dev/docs/getting-started/update-tuples) | 写入、删除、同次请求中的增删；注意 SDK 与 HTTP 区别 |
| F4 | [Perform a Check](https://openfga.dev/docs/getting-started/perform-check) | 用户、关系、对象三个输入 |
| F5 | [Relationship Queries](https://openfga.dev/docs/interacting/relationship-queries) | Check、BatchCheck、Read、Expand、ListObjects 的区别 |
| F6 | [Search With Permissions](https://openfga.dev/docs/interacting/search-with-permissions) | 搜索、排序、分页与授权结合的取舍 |
| F7 | [Source of Truth](https://openfga.dev/docs/best-practices/source-of-truth) | 哪些事实留在业务库，哪些放权限系统 |
| F8 | [Query Consistency Modes](https://openfga.dev/docs/interacting/consistency) | 缓存、一致性及性能权衡 |
| F9 | [Immutable Authorization Models](https://openfga.dev/docs/getting-started/immutable-models) | 模型版本与明确指定模型 ID |
| F10 | [Conditions](https://openfga.dev/docs/modeling/conditions) | 条件关系与部分 ABAC 场景 |
| F11 | [Running OpenFGA in Production](https://openfga.dev/docs/best-practices/running-in-production) | 深度、并发、结果数、超时等运行限制 |

### 数据平台与同步背景

| 编号 | 来源 | 建议关注 |
|---|---|---|
| D1 | [PostgreSQL Logical Decoding](https://www.postgresql.org/docs/current/logicaldecoding-explanation.html) | WAL、复制槽、一致快照与重放 |
| D2 | [PostgreSQL Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html) | 原生行安全与绕过角色的区别 |
| D3 | [Trino Ranger Access Control](https://trino.io/docs/current/security/ranger-access-control.html) | 统一查询入口中的库表列授权、行过滤、脱敏 |
| D4 | [Databricks Governance Best Practices](https://docs.databricks.com/aws/en/lakehouse-architecture/data-governance/best-practices) | 集中、分布、混合治理的组织责任示例；不是要求采购该平台 |

### 本项目证据

以下链接固定到提交 `0a738ed0410be6303e8b8b46a7027ab23230bd1d`，不会因后续分支变化而改变指向内容。

| 编号 | 来源 | 能证明什么 |
|---|---|---|
| P1 | [Superset 实验目录](https://github.com/fengjikui/Smart_hr_database/tree/0a738ed0410be6303e8b8b46a7027ab23230bd1d/integrations/superset) | SQL 规则、RLS 配置、连接与接口验证如何实现 |
| P2 | [Superset 本地实验报告](https://github.com/fengjikui/Smart_hr_database/blob/0a738ed0410be6303e8b8b46a7027ab23230bd1d/reports/superset-permissions-local.json) | 2026-09-15 的 27 项合成样本测试结果 |
| P3 | [OpenFGA 实验目录](https://github.com/fengjikui/Smart_hr_database/tree/0a738ed0410be6303e8b8b46a7027ab23230bd1d/integrations/openfga) | 官方引擎、模型、元组映射、执行层和演示界面 |
| P4 | [OpenFGA 本地实验报告](https://github.com/fengjikui/Smart_hr_database/blob/0a738ed0410be6303e8b8b46a7027ab23230bd1d/reports/openfga-permissions-local.json) | 2026-09-16 的 48 项合成样本测试结果 |

这些报告不证明真实企业数据口径已确认，也不证明系统达到生产规模或已完成企业安全验收。
