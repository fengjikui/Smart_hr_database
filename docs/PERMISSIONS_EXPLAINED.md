# 权限是怎样生效的：从人员关系到 Superset 查询

本文解释当前 **PostgreSQL + Superset** 方案，配合 [实操手册](HANDS_ON.md) 阅读。它回答“这些对象为什么要建、如何配合”，具体点击和执行步骤仍看手册。本文中的平台是 Superset，不是 Supabase。

以当前代码定义为依据：300 人合成宽表、26 个业务字段、5 种业务身份。文中“配置完成后”的效果是完整方案的行为，不表示当前课堂已经完成后续用户创建和真实权限验收。实际进度以 [学习记录](LEARNING_LOG.md) 为准。

建议先读第 1、2、6、7、8 节理解整体，再读视图结构。所有省略列、使用假设账号 ID 的 SQL 都是**讲解用简化结构，不是替换现有视图的部署脚本**。

## 1. 先把整条链路连起来

完整方案中，一个查询要同时满足几层条件：

```text
业务人员登录应用
  → 服务端确定对应的 Superset 业务账号
  → 账号的 Superset 角色允许访问某个 Dataset
  → Dataset 指向某个数据库连接和 PostgreSQL 视图
  → Superset 为查询附加当前登录人的 RLS 条件
  → 连接所用的 PostgreSQL 账号具有该视图的 SELECT 权限
  → 视图按人员关系、身份映射和业务策略提供候选记录
  → PostgreSQL 在 RLS 与业务筛选条件下计算结果
  → Agent 校验结果与权限状态，返回答案
```

这是逻辑职责顺序，不是 PostgreSQL 优化器承诺的物理执行顺序。

最重要的四句话：

1. **数据库账号限制能读取哪些业务对象。**公共账号不能直接读取原始人员表或合同出口。
2. **Superset 数据集访问权限制能查询哪个数据集。**有 RLS 不等于已获访问权。
3. **底层视图计算“哪些账号可以看哪些人”，RLS 从中选出当前登录账号的那部分。**两者缺一不可。
4. **业务筛选进一步缩小结果。**“查询平台研发部”不是授予该部门数据权限。

## 2. 三种角色、三种账号编号，分别是什么

### 三种“角色”

| 层次 | 本项目例子 | 配置位置 | 控制什么 |
|---|---|---|---|
| PostgreSQL 角色 | `v2_public_reader`、`v2_contract_reader` | PostgreSQL `CREATE ROLE` / `GRANT` | 连接数据库、使用 schema、读取特定视图 |
| Superset 平台角色 | `Gamma`、`V2_Data_public`、`V2_Data_contract` | Superset 角色页面 | 平台功能和数据集访问权 |
| 业务角色 | `manager`、`hrbp`、`hr_lead`、`employee`、`admin` | `v2_auth.role_policy` | 是否沿汇报线授权、是否看 HRBP 人群、字段组和应用功能 |

它们不会因为名字相似自动关联。例如，给用户添加 `V2_Role_manager`，不会自动在 PostgreSQL 中把他的 `role_key` 改为 `manager`。

### 三种编号

| 标识 | 示例 | 用途 |
|---|---|---|
| `person_id` | 王灏的 `P0004` | 人员主键；主管和 HRBP 关系指向它 |
| `employee_no` | 王灏的 `00000774` | 工号，按文本保留前导零；不是本方案关系连接键 |
| Superset 用户 ID | 假设为 `42` | 平台创建账号后分配，RLS 的 `current_user_id()` 返回它 |

此外，应用的 `persona_id=manager` 是演示身份键，Superset 的 `username=v2_manager` 是平台登录名。它们通过映射关联，不是同一个字段。

全文中的 `42`、`43` 均为讲解假设，不能照抄到实际映射表。

## 3. 两个数据库、三个业务 schema、四张表

同一个 PostgreSQL 实例中有两个职责不同的数据库：

| 数据库 | 保存的内容 | 谁主要使用 |
|---|---|---|
| `superset_meta` | 平台用户、角色、权限项、连接配置、数据集、RLS、图表等 | Superset 自身 |
| `hr_v2` | 人员事实、业务策略、身份映射、授权关系与查询出口 | 业务数据连接 |

`V2_public`、`V2_contract` 是 Superset 中保存的两个**连接名称**，不是另外创建的两个 PostgreSQL 数据库。

`hr_v2` 中三个 schema 可以理解为三类对象的命名空间：

| Schema | 职责 |
|---|---|
| `v2_data` | 原始业务事实 |
| `v2_auth` | 业务权限配置和关系计算 |
| `v2_api` | 提供给 Superset 注册的数据出口；这里的 API 是命名约定，不是 HTTP 服务 |

四张存储表如下：

| 表 | 一行代表什么 | 关键内容 |
|---|---|---|
| `v2_data.people` | 一名员工的当前记录 | `person_id`、`head_person_id`、`dept_hrbp_id`、部门、学历、入离职日期、合同等 |
| `v2_auth.role_policy` | 一种业务角色的规则 | `role_key`、`reports`、`hrbp`、`inherit_hrbp`、`field_groups`、`details`、`export`、`version` |
| `v2_auth.identity_map` | 一个 Superset 账号的业务身份绑定 | `superset_user_id`、`username`、`persona_id`、`person_id`、`role_key` |
| `v2_auth.snapshot` | 整份演示数据的快照说明，最多一行 | `as_of`、`data_fingerprint`、`data_version`、`field_definitions`；`singleton=true` 限制单行 |

`role_policy` 存“这个角色遵循什么规则”；`identity_map` 存“这个账号是谁、套用哪个角色”。两者都在 PostgreSQL，不是 Superset 自动从姓名、职位推断出来的。

当前初始化的业务策略是：

| role_key | 汇报线 reports | 本人 HRBP 范围 | 继承下属 HRBP 范围 | 合同字段组 | 应用明细 / 导出 |
|---|---|---|---|---|---|
| `employee` | 否 | 否 | 否 | 否 | 是 / 否 |
| `manager` | 是 | 否 | 否 | 否 | 是 / 否 |
| `hrbp` | 是 | 是 | 是 | 是 | 是 / 是 |
| `hr_lead` | 是 | 是 | 是 | 是 | 是 / 是 |
| `admin` | 是 | 是 | 是 | 是 | 是 / 是 |

所有角色都有本人范围和 basic、education、employment 字段组。这是 `store.default_policy()` 的**演示假设**，实际导入后的策略以业务库为准。`admin` 没有“跳过全部过滤”的特殊分支；集团管理线能看到广泛人群，是因为样本关系和策略，不是角色名拥有超级权限。

## 4. 八个视图及其依赖

普通视图可理解为给查询起了一个名字：查询它时，数据库按定义访问底层对象。它不是已保存结果的实体表，也不是自动刷新的缓存。我们没有为这些对象创建物化视图。[PostgreSQL 17：CREATE VIEW](https://www.postgresql.org/docs/17/sql-createview.html)

下面列出直接依赖，前面的对象会进一步引用自己的底层依赖：

| 视图 | 直接依赖 | 结果含义 |
|---|---|---|
| `v2_auth.management_closure` | `people` | 每个起点人员到本人及下属的管理路径、深度、环标记 |
| `v2_auth.graph_health` | `people`、`management_closure` | 一行 `graph_valid`，检查管理环、主管孤儿、HRBP 孤儿 |
| `v2_auth.visible_people` | `people`、`identity_map`、`role_policy`、`management_closure`、`graph_health` | 每个查看账号可见的目标员工，以及授权理由 |
| `v2_api.context` | `identity_map`、`role_policy`、`people`、`snapshot`、`graph_health` | 每个账号的业务身份、策略和数据状态 |
| `v2_api.people_public` | `people`、`visible_people`、`identity_map`、`role_policy` | 每个查看账号可见员工的公共字段和关系辅助列 |
| `v2_api.people_contract` | 与 `people_public` 相同 | 包含合同字段，另要求查看人的业务策略允许 contract 字段组 |
| `v2_api.events_public` | `people_public` | 公共人员记录展开成入职、离职事件 |
| `v2_api.events_contract` | `people_contract` | 合同人员记录展开成入职、离职事件 |

这里一共是 **4 张表、8 个视图，其中 5 个视图在 `v2_api` 下供 Superset 使用**。不是整个方案只创建了五个视图。

主体依赖可以这样读：

```text
people → management_closure → graph_health
people + identity_map + role_policy + management_closure + graph_health
  → visible_people
  → 与 people、identity_map、role_policy 关联
  → people_public   → events_public
  → people_contract → events_contract

identity_map + role_policy + people + snapshot + graph_health → context
```

## 5. 把复杂 SQL 拆成几件简单的事

### 5.1 management_closure：把直属主管关系展开成管理链

原始人员表只存“我的直属主管是谁”。例如 A 管 B，B 管 C，要让 A 找到 C，就需要递归。

```sql
-- 简化结构，省略 path 和 is_cycle；实际代码保留环检测。
WITH RECURSIVE chain(root_id, target_id, depth) AS (
    SELECT person_id, person_id, 0
    FROM v2_data.people
    UNION ALL
    SELECT c.root_id, p.person_id, c.depth + 1
    FROM chain c
    JOIN v2_data.people p ON p.head_person_id = c.target_id
)
SELECT * FROM chain;
```

先让每个人成为一次起点，再逐层找下属。A 的相关结果为 `(A,A,0)`、`(A,B,1)`、`(A,C,2)`。`chain` 是递归 CTE 的名字，是这条 SQL 内部的查询结果，不是另外创建的表。

实际代码的 `path` 保存经过的人员，`p.person_id = ANY(c.path)` 检查是否再次遇到路径中的人。遇环那行保留 `is_cycle=true`，但不再从它向下展开，供健康检查发现错误。按“逐层”讲解便于理解，不应依赖未写 `ORDER BY` 的输出顺序。

### 5.2 graph_health：先确认人员关系可信

它检查三件事：是否存在管理环、非空主管 ID 是否找不到对应人员、非空 HRBP ID 是否找不到对应人员。

```text
graph_valid = 没有管理环 AND 没有主管孤儿 AND 没有 HRBP 孤儿
```

当前采取整图拒绝策略：异常时 `visible_people` 不返回授权记录。`context` 仍能为有效映射返回 `graph_valid=false`，Agent 检测后报错，不能把它解释成“公司没有人”。HRBP 指向本人不按管理环处理。

### 5.3 visible_people：四种授权来源合并成一份名单

```text
本人
UNION ALL 按策略允许的管理线下属
UNION ALL 按策略允许的本人 HRBP 服务人员
UNION ALL 按策略允许的下属 HRBP 服务人员
→ 按 (superset_user_id, target_id) 合并
→ 保留来源标记、理由路径和管理深度
→ 只在 graph_valid=true 时提供结果
```

`UNION ALL` 先保留全部理由。例如一个人既是某主管的下属，又在其 HRBP 服务范围内，会有多条来源；随后 `GROUP BY` 合并成一对“查看人—员工”，`bool_or` 表示是否有相应来源，`jsonb_agg` 保留解释路径。这样不会因多条理由重复统计同一员工。

这里说的“继承”是：先找到管理线下属，再看这些下属作为 HRBP 服务了谁。**不会把 HRBP 服务对象的下属继续当作自己的管理线扩展。**

示意结果：

| superset_user_id | target_id | reports | hrbp | inherited | depth |
|---|---|---|---|---|---|
| 42 | P0004 | false | false | false | 0 |
| 42 | P0005 | true | false | false | 1 |
| 43 | P0005 | false | true | false | NULL |

员工 P0005 同时被账号 42 和 43 看见，可以出现两行；唯一的组合是“查看账号 + 员工”。`depth` 是管理深度，不是 HRBP 服务距离，所以可以为 NULL。

### 5.4 people_public：给可见名单补上员工信息

```sql
-- 简化列清单；完整版本还关联身份/策略，附加关系与月份列。
SELECT g.superset_user_id AS _viewer_id,
       p.person_id, p.name, p.dept_cn_name, p.school_name
FROM v2_auth.visible_people g
JOIN v2_data.people p ON p.person_id = g.target_id;
```

`visible_people` 回答“谁能看谁”；这一步回答“把这些人的哪些信息提供出去”。公共人员视图有 **24 个业务字段**，不含两列合同字段；还附加 `_viewer_id`、`_depth`、关系来源和月份等辅助列，因此总列数大于 24。

**视图内尚未选择当前登录人。**它可以包含多个查看账号的候选记录，后面必须加 Superset RLS。

### 5.5 people_contract：多一组列，也多一个业务条件

它同样从人员事实和可见关系构造，不是 `SELECT * FROM people_public` 再补两列。它包含全部 26 个业务字段，包括：

- `contract_type_code_desc`：合同类型。
- `contract_end_date`：合同到期日期。

此外要求：

```sql
-- r 是查看人通过 identity_map.role_key 关联到的业务策略。
WHERE r.field_groups ? 'contract'
```

这里 `?` 是 PostgreSQL JSONB 的存在性运算符，用于检查字段组数组是否含 `contract`。检查的是**查看人的策略**，不是目标员工的岗位。

没有 contract 字段组的查看人，在这个出口没有相应候选行；不是返回同一行但把合同列变成 NULL。与此同时，还需要平台数据集访问角色和最终 RLS，不能只靠这个条件。

### 5.6 events_public / events_contract：将日期列转换成事件行

两者结构相同，分别使用对应人员出口：

```sql
-- 以公共事件为例，省略其他字段和月份列。
SELECT _viewer_id, person_id, onboard_date AS event_day,
       1 AS is_hire, 0 AS is_exit
FROM v2_api.people_public
WHERE onboard_date IS NOT NULL
UNION ALL
SELECT _viewer_id, person_id, termin_date AS event_day,
       0 AS is_hire, 1 AS is_exit
FROM v2_api.people_public
WHERE termin_date IS NOT NULL;
```

员工有入职和离职日期时贡献两条事件。于是按期间过滤 `event_day` 后，用 `SUM(is_hire)`、`SUM(is_exit)` 得到入职数和离职数；统计人员数则需要留意 `COUNT(DISTINCT person_id)`。

这是一层预定义业务模型，方便 Agent 统一查询“今年各部门入离职”。它不是权限引擎自行产生的，也不是完整任职历史。当前数据没有历史部门归属，事件依然按人员当前部门解释。

虽然 PostgreSQL 事件视图依赖人员视图，**Superset 给人员 Dataset 配置的 RLS 不会因此自动配置到事件 Dataset**。所以我们的规则显式同时绑定人员、事件两个数据集。

### 5.7 context：告诉 Agent“当前账号是谁、规则是什么”

```text
identity_map 中的账号、员工、业务角色
  JOIN role_policy 得到字段组、功能开关、策略版本
  JOIN people 确认映射人员存在
  CROSS JOIN snapshot 附上快照日与数据指纹
  CROSS JOIN graph_health 附上关系健康状态
```

`snapshot` 和 `graph_health` 是单行信息，附到各个映射账号上。最终由独立的 RLS 按 `superset_user_id` 留下当前账号这一行。

Agent 先读取它，检查身份、规则、数据截止日和关系状态，再决定字段目录及查询出口。它不是给模型自由读取全员权限配置的接口。

## 6. PostgreSQL 账号怎样限制可读对象

| PostgreSQL 角色 | 是否本项目创建 | 职责 |
|---|---|---|
| `postgres` | 使用容器已有管理账号 | 建库、建表、建视图、授权和管理检查；不作为业务在线查询账号 |
| `superset_meta` | 平台初始化时创建 | 拥有并维护 `superset_meta` 元数据库；不是 HR 查询连接账号 |
| `v2_public_reader` | 创建业务连接前创建 | 连接 `hr_v2`，读取三个公共出口 |
| `v2_contract_reader` | 创建业务连接前创建 | 连接 `hr_v2`，读取两个合同出口 |

两个 reader 在本方案中的业务对象授权：

| 对象 | public_reader | contract_reader |
|---|---|---|
| `v2_api.people_public` | SELECT | 不授予 |
| `v2_api.events_public` | SELECT | 不授予 |
| `v2_api.context` | SELECT | 不授予 |
| `v2_api.people_contract` | 不授予 | SELECT |
| `v2_api.events_contract` | 不授予 | SELECT |
| `v2_data.people` 和 `v2_auth` 的业务表/视图 | 不授予直接读取 | 不授予直接读取 |

合同账号并不是公共账号的“超级版本”。HR 要读 context 或进行普通统计，仍使用公共连接；需要合同字段时才使用合同连接。

授权的简化结构如下（密码创建步骤省略，不建议重复执行）：

```sql
REVOKE ALL ON DATABASE hr_v2 FROM PUBLIC;
GRANT CONNECT ON DATABASE hr_v2 TO v2_public_reader;
GRANT USAGE ON SCHEMA v2_api TO v2_public_reader;
GRANT SELECT ON v2_api.people_public, v2_api.events_public,
                v2_api.context TO v2_public_reader;
```

`CONNECT` 允许进入数据库，`USAGE` 允许使用命名空间，`SELECT` 允许读取指定对象。`REVOKE ... FROM PUBLIC` 撤的是所有角色共享的数据库级默认授权，不是删除用户、撤销所有对象权限或限制超级用户。

为什么没有原表权限还能读视图？当前视图没有设置 `security_invoker=true`，底层关系权限通常按视图所有者检查；调用账号仍须拥有视图的访问权。当前搭建代码由 `postgres` 创建视图。`security_barrier=true` 影响部分条件求值/优化边界，**不会识别最终用户，也不能替代 RLS**。[PostgreSQL 17 视图权限说明](https://www.postgresql.org/docs/17/sql-createview.html)

两个 reader 都是共享账号。直接拿 reader 凭据查询视图，可能看到属于多个 `_viewer_id` 的记录；数据库并不知道这次使用连接的是王灏还是姜姜。本方案没有通过 PostgreSQL `CREATE POLICY` 配置每员工原生行策略，最终登录人隔离依赖下面的 Superset RLS。

## 7. Superset 连接、Dataset、角色和 RLS 怎样配合

### 7.1 两个连接与五个 Dataset

| Superset 连接 | 目标数据库 / PostgreSQL 账号 | 注册 Dataset → 对应视图 |
|---|---|---|
| `V2_public` | `hr_v2` / `v2_public_reader` | `people_public`、`events_public`、`context` → `v2_api` 下同名视图 |
| `V2_contract` | `hr_v2` / `v2_contract_reader` | `people_contract`、`events_contract` → `v2_api` 下同名视图 |

连接保存“怎么连、用哪个账号”；Dataset 保存“通过哪个连接查询哪个对象，以及列/指标等元信息”。创建 Dataset 不复制人员数据，也不重新创建 PostgreSQL 视图。代码分别对应 `Database` 和 `SqlaTable` 模型。

本方案把已有 PostgreSQL 视图注册成物理 Dataset，而非自由 SQL 虚拟 Dataset。`public` 在这些名称中表示公共字段出口，不表示匿名用户或互联网公开访问，也不是 PostgreSQL 的 PUBLIC 授权集合。

### 7.2 八个自定义平台角色

| 平台角色 | 实际附加权限 |
|---|---|
| `V2_Data_public` | people_public、events_public 两个 Dataset 的 datasource_access |
| `V2_Data_contract` | people_contract、events_contract 两个 Dataset 的 datasource_access |
| `V2_Context` | context Dataset 的 datasource_access |
| `V2_Role_hr_lead` | 无，业务标签 |
| `V2_Role_hrbp` | 无，业务标签 |
| `V2_Role_manager` | 无，业务标签 |
| `V2_Role_employee` | 无，业务标签 |
| `V2_Role_admin` | 无，业务标签 |

前面三个是可组合的数据集权限包；后面五个便于看懂账号身份，**当前不会参与 PostgreSQL 的角色策略计算**。真正连接业务策略的是 `identity_map.role_key`。

普通业务账号还配内置 `Gamma`，提供基础平台使用能力，再配自定义角色获得具体数据集访问权；不编辑 Gamma 本身。不要把业务账号授为 Admin、Alpha 或授予整个数据库访问权来代替精确数据集授权。[Superset 6.1.0 内置角色与数据源权限](https://superset.apache.org/admin-docs/6.1.0/security/)

### 7.3 三条 RLS：从候选行中选当前账号

| RLS 名称 | 绑定 Dataset | Clause |
|---|---|---|
| `V2_scope_public` | people_public、events_public | `_viewer_id = {{ current_user_id() }}` |
| `V2_scope_contract` | people_contract、events_contract | `_viewer_id = {{ current_user_id() }}` |
| `V2_context_scope` | context | `superset_user_id = {{ current_user_id() }}` |

都设为 **Base，Roles 留空，Group Key 留空**。Regular 的 Roles 选择适用角色；Base 的 Roles 选择豁免角色。豁免只针对这一条规则，不是对所有过滤规则的通行证。多个角色/规则也不能简单概括成“权限全部相加”，应按实际匹配规则验证。[Superset 6.1.0 RLS 类型与组合规则](https://superset.apache.org/admin-docs/6.1.0/security/#filter-types)

`Clause` 是 SQL 条件片段，不写完整 SELECT 或 WHERE。双花括号是模板语法：`current_user_id()` 从 Superset 登录上下文取得平台用户 ID，随后过滤在数据库查询中执行；不是 PostgreSQL 的 `current_user`，后者在公共连接下只会标识共享 reader。[Superset 6.1.0 SQL 模板](https://superset.apache.org/admin-docs/6.1.0/configuration/sql-templating/)

这里没有给每个人写一条 RLS。所有普通业务账号复用同一模板，账号不同使 ID 不同，底层 `visible_people` 的对应名单也不同。技术管理员不是验证普通用户权限的身份。

## 8. 真实业务账号如何接上两套权限

完整初始化设计包含 7 个 Superset 账号：5 个演示业务账号、1 个未映射反例、1 个技术管理员。下面是目标配置，不是宣称当前课堂已经建完。

为缩短表格，公共组合表示 `Gamma + V2_Data_public + V2_Context`：

| 平台账号 | 员工 / 业务角色 | Superset 角色组合 |
|---|---|---|
| `v2_hr_lead` | 王承哲 P0002 / hr_lead | 公共组合 + V2_Role_hr_lead + V2_Data_contract |
| `v2_hrbp` | 姜姜 P0003 / hrbp | 公共组合 + V2_Role_hrbp + V2_Data_contract |
| `v2_manager` | 王灏 P0004 / manager | 公共组合 + V2_Role_manager |
| `v2_employee` | 冯基魁 P0005 / employee | 公共组合 + V2_Role_employee |
| `v2_admin` | 集团负责人 P0001 / admin | 公共组合 + V2_Role_admin + V2_Data_contract |
| `v2_unmapped` | 故意不写 identity_map | 公共组合 |
| `v2_setup_admin` | 配置用途，不绑定业务人员 | 内置 Admin |

特别注意：**`v2_admin` 不是 Superset 超级管理员；`v2_setup_admin` 才是平台配置账号。**

创建业务账号后，Superset 才分配真实内部 ID。假设王灏的 ID 为 42，再写这样一行映射：

| superset_user_id | username | persona_id | person_id | role_key |
|---|---|---|---|---|
| 42 | v2_manager | manager | P0004 | manager |

这一行同时完成两件事：让 RLS 的平台 ID 找到业务员工 P0004；让关系视图知道他使用 manager 策略。

平台用户的多角色列表保存在 Superset 元数据库；这张业务映射表暂时每账号只有一个 `role_key`。修改其中一边不会自动同步另一边。初始化对既有用户/映射主要保留，不是持续的人事同步服务。

`v2_unmapped` 用于证明：即使拥有公共数据集访问权，没有身份映射，也没有对应候选行。直接查询应返回空授权；Agent 读取 context 得不到唯一身份行时会明确拒绝继续。

## 9. 用王灏的一次查询串联整个机制

假设王灏已配置完整，平台 ID 为 42，问“可信与 AI 实验室有多少在职员工？”

1. **确定人**：应用会话确定 persona=manager，后端用受控清单找到 `v2_manager`。模型不提供账号、密码或 user ID。当前身份选择器仍是本地演示，生产要接可信认证。
2. **登录平台**：后端使用该业务账号登录 Superset，取得访问 token 和 CSRF token；不会用 `v2_setup_admin` 代查。
3. **读本人上下文**：查询 context，RLS 变为 `superset_user_id=42`。Agent 核对员工 P0004、角色 manager、关系健康状态及字段组。
4. **生成业务计划**：模型给出部门、在职人群、人数指标；代码校验字段依赖后选 `people_public`。这里不需要合同出口。
5. **检查数据集访问**：`V2_Data_public` 允许访问该 Dataset；RLS 再限定 `_viewer_id=42`。
6. **数据库执行**：通过 `V2_public` 使用 `v2_public_reader` 查询允许的视图，附上业务条件后统计。
7. **安全返回**：服务层检查执行前后授权/数据指纹，组织摘要，按身份及指纹保存历史。

第 6 步可以用下面的简化 SQL 理解，实际 SQL 由 Superset 编译：

```sql
SELECT COUNT(DISTINCT person_id) AS count
FROM v2_api.people_public
WHERE _viewer_id = 42                     -- Superset 的身份过滤
  AND dept_cn_name = '可信与AI实验室'       -- 问题里的业务条件
  AND onboard_date <= '2026-09-11'
  AND (termin_date IS NULL OR termin_date > '2026-09-11');
```

因此，不是“先把别人的数据发到浏览器再隐藏”，也不是“让模型自觉只看自己的范围”。数据库根据这些条件得出结果，前端收到的是查询结果。

如果他问一个不在可见范围内的部门，部门条件不会增加授权；交集可能为空。汇报线覆盖多个部门时，管理范围本身可以跨部门，因此“我能看谁”和“我这次想查哪个部门”必须分开。

## 10. 为什么合同查询需要多处同时成立

以普通业务账号查看合同列为例：

| 检查 | 不满足时会怎样 |
|---|---|
| Agent 字段依赖允许 contract | 应用拒绝该字段、筛选、排序或指标请求 |
| 平台账号有合同 Dataset 访问权 | Superset 拒绝访问数据集 |
| Dataset 使用合同 reader 连接 | 错用公共 reader 时，PostgreSQL 拒绝合同视图访问 |
| 查看人的 role_policy 含 contract | 合同视图中没有该查看人的候选记录 |
| RLS 绑定正确并选中本人 ID | 只保留当前查看人的记录，排除其他账号候选行 |

其中合同 RLS 缺失不是“默认多一层保护”，而是会失去这一层用户隔离，必须被配置检查发现。应用的 `_viewer_id` 校验只是补充，不能替代正确的平台配置。

公共视图的两列合同字段是真正未投影出去，而不是前端隐藏。对于 basic、education、employment 内更细的字段差异，当前主要由 Agent 的字段校验控制；尚未实现任意字段的完整平台可视化列权限产品。应用的 details/export 开关也不会自动关闭 Superset 原生明细和下载功能。

## 11. 哪一处变更会影响什么

| 操作 | 影响 | 不会自动完成的事 |
|---|---|---|
| 修改人员 head_person_id / dept_hrbp_id | 普通视图随后按新关系计算 | 当前样本没有外部系统同步接入，不会自动收到别的库的变化 |
| 修改 role_policy | 使用这个 role_key 的账号业务能力变化 | 不会自动增删平台数据集角色 |
| 修改 identity_map.role_key / person_id | 账号对应规则或人员变化 | Agent 清单若未同步，会因身份不一致拒绝，不会自动猜新绑定 |
| 增删平台数据集角色 | 改变允许查询的 Dataset | 不改底层汇报线，也不自动扩大可见人员 |
| 增加 V2_Role_* 标签 | 平台角色列表变化 | 不改 identity_map.role_key，不会凭标签得到 HRBP 范围 |
| 修改 RLS | 改变对应 Dataset 的行条件 | 不能弥补数据库对象授权过大或业务规则写错 |
| 删除账号映射 | 移除该账号对应候选授权 | 不等于删除 Superset 登录账号 |
| 更换连接 reader | 改变数据库可访问对象 | 不改变 Superset 当前登录用户的 ID |

当前不保存历史任职/汇报线；关系视图不是历史授权记录。同步、调岗生效时机、权限配置审批仍需业务明确。

## 12. 当前可靠性和性能应怎样解释

本方案把身份、数据集访问、行过滤和数据库对象授权分别放在明确位置，但复杂汇报线/HRBP 语义仍来自我们编写的 SQL 和业务配置。成熟平台负责通用能力，不会自动保证业务规则正确。

共享 reader 凭据不能给普通用户；用户也不能拥有修改连接、Dataset、RLS 的能力或不受控自由 SQL 入口。普通业务查询走既定 Dataset 的 Chart Data API。若任意开放另一条执行路径，需要单独确认该路径的身份和 RLS 行为，不能因“同样属于 Superset”就默认安全。

权限前后指纹检查可发现观察点之间的变化，但不是跨多个 HTTP/SQL 请求的原子事务。现在关闭结果缓存，并实际查询各必需出口检查撤权；快照只在请求内复用。这是便于演示验证的实现，不是已完成全公司高并发优化。

普通视图不等于每次必定全量计算，也不等于外层条件一定能下推到所有递归内部。尤其是递归关系和整图健康检查，必须看真实执行计划与规模测试。举例：3000 个使用者平均可见 100 人，关系规模约为 **30 万对**，不是 3 万。

我们已讨论的关系预计算、按小时刷新及事件失效属于后续优化方向，当前没有实现。刷新周期必须考虑撤权延迟，不能只以“关系变化少”作为缓存安全性的证明。

## 13. 如何确认自己理解并配置正确

按以下顺序排查，避免把不同层的问题混在一起：

1. **账号是谁**：当前 Superset 业务用户名和真实内部 ID 是否正确？有没有错误使用管理员？
2. **映射是否正确**：identity_map 中的 person_id、role_key 是否符合业务预期？
3. **策略与关系是否正确**：role_policy 与人员主管/HRBP 字段是否符合规则？graph_valid 是否为 true？
4. **出口是否正确**：五个 Dataset 是否绑定对应视图与两个 reader？公共视图是否缺少合同两列？
5. **平台访问权是否准确**：业务用户是否只有预期数据集权限，没有更宽角色？
6. **RLS 是否完整**：三条规则类型、数据集绑定、条件、豁免列表是否正确？事件 Dataset 不能遗漏。
7. **真实结果是否一致**：用普通业务账号查具体人员集合、部门统计和合同反例；不仅看返回行数，也对照 person_id。
8. **旁路是否受控**：历史、调试、核验、下钻和导出是否仍检查当前身份/权限？

相应代码入口：

| 问题 | 项目源码 |
|---|---|
| 原始样本、五种默认业务策略 | [store.py](../backend/hr/store.py)，`generate_rows()` / `default_policy()` |
| 权限表、递归、健康检查、可见名单、context | [schema.sql](../integrations/superset/schema.sql) |
| 两个 reader、人员/事件视图、平台对象 | [setup.py](../integrations/superset/setup.py)，`prepare_database()` / `create_people_views()` / `prepare_superset()` |
| 元数据库账号 | [init-postgres.sh](../integrations/superset/init-postgres.sh) |
| 手工真实 ID 盘点、映射 SQL、Agent 绑定 | [learning.py](../integrations/superset/learning.py)、[learning_inspect.py](../integrations/superset/learning_inspect.py) |
| 身份选择、上游登录、Chart Data、授权快照 | [superset_source.py](../backend/hr/superset_source.py)，`identity()` / `session()` / `_chart()` / `snapshot()` |
| 业务条件与指标编译 | [superset_query.py](../backend/hr/superset_query.py)，`Compiler` |
| 字段、历史与撤权 | [auth.py](../backend/hr/auth.py)、[service.py](../backend/hr/service.py) |
| 物理授权/平台配置检查 | [verify_storage.py](../integrations/superset/verify_storage.py) |
| 真实请求与独立对照、撤权测试 | [validate_superset.py](../scripts/validate_superset.py)、[validate_revocation.py](../scripts/validate_revocation.py) |

验证脚本有不同副作用：配置盘点和一般回归不替用户初始化；撤权测试会临时修改权限，不能在当前手工课堂中随意执行。文档阅读不需要运行任何重置或初始化命令。

## 14. 对外讲解时可以这样概括

> 我们先用人员数据、账号映射和业务策略，算出每个账号可见的人员集合，再用视图提供公共或合同字段。Superset 的角色决定账号能访问哪些数据集，RLS 将查询限定到当前登录账号的记录。底层数据库连接使用只读账号，只能读指定视图；Agent 只生成受限的业务查询计划，通过对应业务账号执行查询。汇报线等业务规则由我们配置和验证，通用的用户、角色、数据集访问及 RLS 执行由 Superset 承担。

配置点击顺序见 [第 26～31 步实操](HANDS_ON.md#step-26)，完整代码导读见 [项目代码说明](PROJECT_CODE_GUIDE.md)，生产差距见 [安全边界](SECURITY.md)。
