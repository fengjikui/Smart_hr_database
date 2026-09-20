# 完整数据接入 PostgreSQL 与 Superset：实施与复现讲义

更新日期：2026-09-20。环境：Superset 6.1.0、PostgreSQL 17.11、LangGraph Agent。

代码目录已统一；本文出现的 `hr_v2`、`v2_*` 和 `V2_*` 是已有数据库及平台对象的持久化名称，继续复用原有 ID 和权限，不是另一套代码。首次安装平台请先在仓库根目录执行 `npm run superset:up`。

这份文档记录本项目实际实现的步骤。建议先读第 1～5 节，看懂数据、身份与权限；再读第 6～8 节理解 Agent 如何接入，最后按第 9 节手动验证。

## 1. 当前系统包含什么

当前应用的完整 **300 人、26 个业务字段**已迁入新的 PostgreSQL 数据库 `hr_v2`。五个演示身份和原业务权限策略也已导入。离线 SQLite 文件保留作独立回归参考，不再作为 Superset 模式的在线人员数据源。

应用会话、聊天历史和审计仍保存在应用 SQLite；这是应用状态，与人员业务数据分开。字段描述、指标口径仍由 Git 中的 Python 目录定义。当前宽表不包含考勤事实，也没有接入真实 HR 数据。

| 对象 | 新增数量 | 用途 |
|---|---:|---|
| PostgreSQL 业务数据库 | 1 | `hr_v2` |
| schema | 3 | 原始人员、授权辅助数据、查询出口 |
| PostgreSQL 只读连接账号 | 2 | 基础字段、合同字段分开 |
| Superset 数据库连接 | 2 | `V2_public`、`V2_contract` |
| Superset 注册数据集 | 5 | 人员 2 个、事件 2 个、身份上下文 1 个 |
| Superset 自定义角色 | 8 | 3 个数据访问角色、5 个业务标签角色 |
| Superset 用户 | 7 | 5 个业务用户、1 个未映射负例、1 个技术管理员 |
| Superset Base RLS | 3 | 公共人员/事件、合同人员/事件、身份上下文 |
| 人员表格看板 | 2 | 基础人员、含合同字段人员 |


## 2. 第一步：把当前应用 数据完整导出

在项目根目录执行：

```bash
uv run python integrations/superset/run.py export
```

实际调用 [export.py](../integrations/superset/export.py)：

1. 从 [store.py](../backend/hr/store.py) 的 `people()` 读取当前人员宽表，而不是另造一套相似数据。
2. 读取同文件的 `PERSONAS` 和 `policy()`，获得五个身份及当前业务策略。
3. 从 [schema.py](../backend/hr/schema.py) 读取字段 ID、字段组、描述。
4. 将全部人员、空值、字符串工号、快照日期、字段目录和策略写入导入快照。
5. 计算排序后的数据 SHA-256 指纹，导入和回归时用于核对内容。

输出在 `integrations/superset/.local/application/fixtures.json`。这是可阅读 JSON，不含密码，未提交 Git。工号 `00031266` 始终作为字符串，不能转换为整数。

容器通过单独的只读挂载 `/run/hr-input/fixtures.json` 读取样本，避免 Linux 宿主机与容器 UID 不一致时无法穿过私有目录。宿主机 `.local` 仍为私有目录，密码文件保持 0600；只有合成样本文件设为 0644 以供该挂载读取。

原模拟数据的生成函数是 `store.generate_rows()`：固定种子为 `20260911`，快照日为 `2026-09-11`；保留原固定人物关系、学校、入离职和合同样例。相对时间“今年”“上季度”仍以快照日解释。

### 26 个字段

| 字段组 | 字段 ID（完整 ID 前缀为 `people.`） |
|---|---|
| basic，12 个 | `person_id`, `employee_no`, `name`, `head_person_id`, `dept_master_id`, `dept_hrbp_id`, `dept_code`, `dept_cn_name`, `onboard_date`, `termin_date`, `birth_date`, `age` |
| education，6 个 | `school_name`, `first_major`, `diploma_code_desc`, `degree_code_desc`, `full_time_flag`, `education_expired_date` |
| employment，6 个 | `hire_type_code_desc`, `labour_type_code_desc`, `position_code_desc`, `current_employment_start_date`, `confirmation_date`, `formalize_flag` |
| contract，2 个 | `contract_type_code_desc`, `contract_end_date` |

宽表一人一行，`person_id` 是主键，`employee_no` 是工号。`head_person_id` 与 `dept_hrbp_id` 关联人员主键。`dept_master_id` 保留作为业务字段，但不单独产生授权。

## 3. 第二步：创建 PostgreSQL 数据库并导入

```bash
uv run python integrations/superset/run.py setup
uv run python integrations/superset/run.py status
```

[run.py](../integrations/superset/run.py) 先导出，再定位本项目已运行的 Superset 容器，执行 [setup.py](../integrations/superset/setup.py)。它使用现有实验的 Docker socket，不修改全局 Docker context。

### 3.1 创建数据库

`setup.py` 的 `prepare_database()` 先连接 PostgreSQL 的维护库，检查并创建 `hr_v2` 和两个读取账号。创建数据库需要维护权限，但这种权限仅用于安装程序，Agent 运行时不拥有它。

数据库内部结构：

| schema | 主要对象 | 保存的内容 |
|---|---|---|
| `v2_data` | `people` | 完整 300 人宽表 |
| `v2_auth` | `identity_map` | Superset 用户 ID → persona → 人员 ID → 业务策略 |
| `v2_auth` | `role_policy` | 管理线、HRBP、继承、字段组、明细、导出开关及版本 |
| `v2_auth` | `snapshot` | 快照日、内容指纹、字段目录 |
| `v2_auth` | `management_closure` | 递归计算的管理关系、深度、路径 |
| `v2_auth` | `graph_health` | 管理环、无效主管/HRBP 引用检查 |
| `v2_auth` | `visible_people` | 每个查看人最终可见的人员及授权来源 |
| `v2_api` | 五个视图 | Superset 可查询的受控出口 |

### 3.2 导入宽表

字段定义由导出文件驱动，主键和工号索引在 PostgreSQL 创建。日期保留 ISO 文本，年龄为整数，便于与当前指标口径逐项核对。安装程序使用参数化批量写入，不把姓名、学校等拼入 SQL。

首次安装在事务中写入完整人员与策略。再次执行 `setup` 会保留已有业务数据、用户角色和 RLS 编辑，并重新应用代码里的视图定义。因此它不是权限重置命令，也不是一个可以无审查覆盖自定义视图的生产发布工具。

只有明确需要以当前应用 文件覆盖 PostgreSQL 人员和业务策略时才运行：

```bash
uv run python integrations/superset/run.py sync-data
```

该命令会重导业务快照及业务策略，但不替你覆盖 Superset 中的手动角色/RLS 配置。它不是 CDC，也没有实现真实 HR 库的持续同步。

### 3.3 哪些地方还需要自己写规则

递归和 HRBP 业务规则位于 [schema.sql](../integrations/superset/schema.sql)：

- 本人直接进入可见集合。
- 打开 `reports` 时，沿管理线查直属及全部间接下属。
- 打开 `hrbp` 时，加入本人直接服务的员工。
- 同时打开 `reports` 与 `inherit_hrbp` 时，加入管理线下属中的 HRBP 服务的员工。
- 对上述集合去重；不能从一个“已经可见的员工”任意继续扩张汇报线。
- 管理环、孤立主管或 HRBP 引用会令授权失败；Agent 显示关系异常，不能误报“没有人员”。

**Superset 不会自行理解“HRBP”“下属继承”的业务含义。** 这部分是我们写的 PostgreSQL 视图；递归由 PostgreSQL 引擎执行，身份和数据集行过滤由 Superset 执行。

## 4. 第三步：配置 Superset 数据源和数据集

“Superset 数据库连接名称”不等于“PostgreSQL 数据库名称”：

| Superset 中的连接名称 | PostgreSQL 数据库 | PostgreSQL 登录账号 |
|---|---|---|
| `V2_public` | `hr_v2` | `v2_public_reader` |
| `V2_contract` | `hr_v2` | `v2_contract_reader` |

两条连接在容器内访问 `postgres:5432`，宿主机数据库端口是 `127.0.0.1:55432`。手动配置时，这两个地址不能混淆。

自动配置由 `setup.py` 中 `prepare_superset()` 完成，使用 Superset 自身 ORM 创建连接、数据集、图表与看板。DML、CTAS、CVAS 被关闭；业务用户没有 SQL Lab 或数据库全访问权限。只读账号只有必要视图的 SELECT 权限，并设置语句超时。

若你手动复现，可用技术管理员进入 **Settings → Database Connections → + Database**，选择 PostgreSQL，填写数据库和对应只读账号。两个 PostgreSQL 账号的连接参数保存于本机 `integrations/superset/.local/application/database-credentials.json`（0600）；这里的密码与 Superset 登录密码不同。安装程序直接完成了这一步，无需为了练习重复建立同名连接。若旧安装还没有这个文件，可运行下面命令，只导出本机连接资料，不修改数据库或权限：

```bash
uv run python integrations/superset/run.py export-connection-info
```

密码由实验环境的本机种子与账号名派生，仅写入被 Git 忽略的文件，不打印到终端。请在本机编辑器中查看，不复制到文档、聊天和 Git。

随后在 **Datasets → + Dataset** 选择连接、schema `v2_api` 和下面的视图：

| 数据集键 | 连接 | 内容 |
|---|---|---|
| `people_public` | V2_public | 24 个基础业务字段，不包含合同两列 |
| `people_contract` | V2_contract | 26 个业务字段 |
| `events_public` | V2_public | 人员展开为入职、离职事件，用于组合事件统计 |
| `events_contract` | V2_contract | 同上，保留合同字段 |
| `context` | V2_public | 当前用户的身份、规则、快照版本与图校验状态 |

人员和事件视图额外包含 `_viewer_id`、管理深度、授权来源标记及月份等辅助列。这些是授权/统计需要的列，不是原宽表新增了业务字段。一个人的入职和离职可能形成两条事件，不能把事件行数直接当作人数；人数指标使用人员去重。

合同视图还要求业务策略包含合同字段组；拥有合同策略和拥有合同数据集访问权缺一不可。基础视图在数据库物理列结构上没有合同两列，不能靠修改前端列选择将它们拿出来。

## 5. 第四步：创建用户、角色与 RLS

### 5.1 七个账号

| 账号 | 业务身份 | 初始合同字段 | 初始应用导出 |
|---|---|---|---|
| `v2_hr_lead` | 王承哲，HR 主管 | 是 | 是 |
| `v2_hrbp` | 姜姜，HRBP | 是 | 是 |
| `v2_manager` | 王灏，部门主管 | 否 | 否 |
| `v2_employee` | 冯基魁，员工 | 否 | 否 |
| `v2_admin` | 集团管理线，P0001 | 是 | 是 |
| `v2_unmapped` | 未映射测试账号 | 否 | 否 |
| `v2_setup_admin` | Superset 技术配置管理员 | 不作为业务身份验收 | 不作为业务身份验收 |

`v2_admin` 是业务账号，使用 **Gamma + 业务数据角色**，不是 Superset 的 Admin。技术配置管理员与它分开，Agent 不使用技术管理员的 token 查询。

本机凭据：`integrations/superset/.local/application/credentials.json`，权限为 0600，已排除在 Git 之外。身份映射及实际数据集 ID：同目录 `manifest.json`，没有密码。演示采用后端固定的账号映射；生产需要接入企业 SSO，这次没有实现真实单点登录。

**当前身份选择器是演示入口，不验证操作者确实是这名员工。** 本机操作者能通过选择器及 `/api/session` 切换五个 persona。会话绑定保证后续查询沿用已选身份，不能把它理解为已完成企业用户认证；上线前必须用可信登录身份替换这个入口。

### 5.2 八个自定义角色

| 角色 | 授予的能力 |
|---|---|
| `V2_Data_public` | 公共人员、公共事件两个数据集的 `datasource_access` |
| `V2_Data_contract` | 合同人员、合同事件两个数据集的 `datasource_access` |
| `V2_Context` | 身份上下文数据集的 `datasource_access` |
| `V2_Role_hr_lead` | 业务标签，不额外授平台权限 |
| `V2_Role_hrbp` | 同上 |
| `V2_Role_manager` | 同上 |
| `V2_Role_employee` | 同上 |
| `V2_Role_admin` | 同上 |

业务用户基础分配为 Gamma + V2_Data_public + V2_Context + 本人业务标签；合同身份再加 V2_Data_contract。另复用系统自带 Gamma 和 Admin，它们不计入八个新角色，也不修改其内置权限。

**业务标签不自动决定 PostgreSQL 的业务策略。** 当前 `identity_map.role_key` 才是策略绑定，角色中添加一个同名标签不会自动同步它。要变更策略，需更新映射/策略表；要变更数据集访问，需调整 Superset 角色。新增业务身份时必须成套配置并验证。

手动查看/编辑角色请用 [经典角色列表](http://127.0.0.1:8088/roles/list/)。本机新版角色页面的权限搜索有兼容问题，经典入口已实测可用。数据集访问权限的实际名称随 ID 改变，可从 manifest 中查找；以本机 manifest 中的 ID 为准。

### 5.3 三条 Base RLS

打开 [Row Level Security](http://127.0.0.1:8088/rowlevelsecurity/list/)，查看以下三条。Filter Type 全为 **Base**，Roles 和 Group Key 全部留空。

| 规则 | 绑定的数据集 | Clause |
|---|---|---|
| `V2_scope_public` | people_public、events_public | `_viewer_id = {{ current_user_id() }}` |
| `V2_scope_contract` | people_contract、events_contract | `_viewer_id = {{ current_user_id() }}` |
| `V2_context_scope` | context | `superset_user_id = {{ current_user_id() }}` |

Base 的 Roles 表示豁免角色，不是需要受限制的角色；本方案不给业务账号设置豁免。Clause 是 SQL 条件片段，不写完整 SELECT，也不加开头的 WHERE。

视图为每个查看人计算自己的候选人员行，`_viewer_id` 标记这行属于哪个查看人。Superset 将模板替换为当前登录用户 ID，并加入最终 SQL。因此同一个数据集以不同用户登录会返回不同结果。

数据库的共享读取账号本身不代表具体员工。绕开 Superset 直接使用这个共享账号查询，不能宣称仍有最终用户的行隔离。它只限制能够访问哪些视图和字段；业务用户行隔离依赖 Superset 的 RLS 执行路径。这也是不向普通用户提供数据库凭据或自由 SQL 接口的原因。

## 6. 第五步：把Agent 接到 Superset

启用新链路：

```bash
npm run demo
```

默认使用 `HR_QUERY_BACKEND=superset`，页面为 `/`，API 前缀为 `/api`。需要离线验证时显式运行 `npm run demo:offline`。

主要文件与调用顺序：

1. [routes.py](../backend/hr/routes.py)：读取应用会话与 CSRF，确定 persona；浏览器不能通过问题内容指定实际执行账号。
2. [auth.py](../backend/hr/auth.py)：在 Superset 模式调用新的授权入口；离线 Python 遍历只保留在 SQLite 基线模式和离线参考验证中。
3. [superset_source.py](../backend/hr/superset_source.py)：用服务端清单将 persona 对应到独立 Superset 用户；登录获得临时令牌，读取受 RLS 限制的 context 与人员快照。
4. [registry.py](../backend/hr/registry.py)：只给模型披露当前允许的字段、指标和部门候选。
5. [graph.py](../backend/hr/graph.py)：LangGraph 继续完成检索、模型计划、口径校验、执行、解释和历史保存。
6. [query.py](../backend/hr/query.py)：根据执行后端分派；Superset 模式交给 [superset_query.py](../backend/hr/superset_query.py)。
7. 新编译器把已校验 Plan 转成 Chart Data 请求中的字段、指标表达式、业务筛选与分组。**不把 Python 计算的授权人员 ID 清单作为最终授权 WHERE。**
8. `POST /api/v1/chart/data`：Superset 校验当前用户的数据集访问权，注入 RLS，生成 PostgreSQL SQL 并执行。
9. [service.py](../backend/hr/service.py)：返回数字摘要，保存查询与真实 SQL；结果返回和历史保存前重新检查授权指纹。

模型仍只生成白名单结构化 Plan，不生成任意 SQL。学校、日期等值由固定编译器安全编码，Superset 负责最终 SELECT/FROM/RLS/GROUP BY。没有创建临时任意 SQL 数据集，也没有用管理员 SQL Lab 代理业务查询。

### 6.1 统计到底在哪里执行

筛选、人数、比例分子/分母、平均数、入离职事件聚合都在 **PostgreSQL** 执行，SQL 由 Superset 生成并附带 RLS。没有先读全量人员再在 Python 中做访问控制。

Agent 仍负责页面分页、最终稳定排序、补齐零月份和自然语言整理。补齐月份使用的是已授权部门范围；合计由单独的受 RLS 限制的查询计算，不能将分组比例相加。

人员快照通过同一业务账号从 Superset 取回，供目录、关系说明、核验及权限变化指纹使用。它不取代最终查询的 Superset RLS。快照最多 1000 人，超出或返回不完整就拒绝，不能把截断数据当作全量。这是 300 人演示的规模边界，尚不是数据湖大规模查询架构。

历史校验不只检查主人员视图：它逐一读取该身份所需公共人员、公共事件出口；允许合同字段的身份还检查合同人员、合同事件出口。每个出口都经过真实数据集权限与 RLS，读取最小人员/事件标识，并核对返回数量。任何出口的可见集合变化都会改变指纹；所需出口访问权被撤销时，本演示保守地拒绝整个请求，不能继续使用旧历史。代价是每次重新鉴权增加查询次数，后续扩容应设计统一权限版本或可信事件失效机制。

### 6.2 怎么观察链路确实生效

在 `/` 左下角展开“权限与模型状态”，可见“Superset 权限 · PostgreSQL 查询”。结果和独立节点调试页包含真实 PostgreSQL SQL，例如普通员工查询中应出现：

```sql
FROM v2_api.people_public
WHERE (_viewer_id = 当前Superset用户ID)
  AND (...业务筛选条件...)
```

这是说明性示意，实际用户 ID 以本机 SQL 为准。`source_queries` 同时保留上下文、授权快照和聚合查询的 SQL，不保存访问令牌或数据库密码。

## 7. 当前应用的其他功能如何保持权限一致

| 功能 | Superset 模式的处理 |
|---|---|
| 左下角可见人数 | 当前用户 Superset 授权快照 |
| 部门候选、字段和指标目录 | 授权快照与字段组，不能从本地全量表列出部门 |
| 关系与来源路径 | PostgreSQL 已计算的授权来源；路径中未授权节点不补查姓名 |
| 自助核验、下钻 | 同一个 Plan 校验与 Superset 执行入口 |
| 在线独立对账 | PostgreSQL 查询结果对比本用户已授权快照上的独立 Python 计算 |
| 完整权限名单正确性 | 离线回归用原完整数据和独立 BFS 比较，结果不作为业务接口旁路返回 |
| 导出 | 先检查业务导出开关，再走 Superset，并在返回前重新检查指纹 |
| 历史、节点调试、多轮追问 | 绑定本人及当前授权/数据指纹，变化后拒绝旧结果 |
| 离线策略编辑 | Superset 模式停用，避免只改 SQLite 却误认为新链路生效 |
| Superset 故障 | 返回错误，绝不自动切回 SQLite |

应用的 `details/export` 开关限制本应用的明细和导出功能，目前不会自动禁用 Superset 原生图表明细或下载菜单，也不宣称能禁止用户复制已经被允许查看的数据。其他字段组的动态组合目前由 Agent 目录/计划校验处理；这次数据库物理列隔离重点实现基础字段与合同字段两档，不能说每个字段都已有独立数据库列策略。

## 8. 预期结果与验收方式

固定样本下：

| 身份 | 授权候选人员（含离职） | 当前在职 | 本人当前部门内在职 |
|---|---:|---:|---:|
| 王承哲 | 239 | 226 | 57 |
| 姜姜 | 239 | 226 | 57 |
| 王灏 | 179 | 169 | 57 |
| 冯基魁 | 1 | 1 | 1 |
| 集团管理线 | 300 | 284 | 2 |

王灏的 169 是当前全部授权范围内的在职人数，包括跨部门下属；只问“可信与 AI 实验室”时还要与当前部门取交集，因此是 57。权限范围与业务筛选不能混淆。

可复现的检查命令：

```bash
uv run python integrations/superset/run.py verify-storage
npm run test:superset
npm run test:revocation
```

当前执行结果写入 `reports/`，详细区分离线回归、真实平台验收与模型验收的方法见 [测试说明](TESTING.md)。不要用历史报告代替本次验证。

## 9. 你自己重做一遍，建议从这里开始

1. 阅读 `fixtures.json` 中任意两个人，找出 `head_person_id` 与 `dept_hrbp_id`；不要一开始阅读所有递归 SQL。
2. 用 `v2_setup_admin` 查看两个连接，确认它们都指向 `hr_v2`，但数据库读账号不同。
3. 查看五个数据集，重点比较公共人员与合同人员的列。
4. 查看 `v2_employee` 用户角色，找到数据集授权；再查看三条 Base RLS 中的当前用户模板。
5. 退出技术管理员，登录 `v2_employee` 打开[人员看板](http://127.0.0.1:8088/superset/dashboard/v2-people-public/)，应只见冯基魁。
6. 换成 `v2_manager`，查看授权候选人员；看板包含离职时应是 179 人，不要直接与 Agent 默认在职的 169 比较。
7. 在 Agent `/` 选择王灏，先问“我的全部授权范围有多少在职员工”，再问“可信与AI实验室有多少在职员工”，对比 169 与 57。
8. 打开节点调试，找到查询中的 RLS、部门条件、在职日期条件，分别解释三者的作用。
9. 最后才练习改变一条规则；修改前记录原值和预期结果，改后查询，再恢复。不要同时运行自动撤权脚本。

普通用户使用 Superset 看板/图表查询；技术管理员可以检查数据库配置。不要为了“查询方便”给普通用户添加 SQL Lab、数据库全访问、Alpha 或 Admin。

## 10. 配置分别保存在哪里

| 内容 | 权威保存位置 |
|---|---|
| 人员事实、管理关系、HRBP 对应 | PostgreSQL `hr_v2.v2_data.people` |
| 业务关系开关、应用明细/导出开关 | PostgreSQL `v2_auth.role_policy` |
| Superset 用户与人员映射 | PostgreSQL `v2_auth.identity_map` |
| 登录用户、用户角色、数据源、数据集、RLS | Superset 自己的元数据库 `superset_meta` |
| 字段说明、指标口径、模型可用结构 | Git 中的 `schema.py`、`registry.py` |
| 聊天历史、会话、审计 | 应用的 `data/sessions.sqlite` |
| 本地密码及动态 ID 清单 | 被 Git 忽略的 `.local/application/` |

初始化代码负责创建配置，运行时配置从数据库读取；修改代码不会自动等于修改已部署规则。业务规则变更应明确修改对象、审批人、版本和回归测试。当前演示没有实现生产级审批平台或自动同步闭环。

## 11. 官方依据与本项目负责的部分

- [Superset 6.1.0 Security](https://superset.apache.org/admin-docs/6.1.0/security/)：自带角色、数据集访问、行过滤与安全边界。我们使用 Gamma 加独立数据角色，并保留 Base RLS。
- [Superset 6.1.0 SQL Templating](https://superset.apache.org/admin-docs/6.1.0/configuration/sql-templating/)：当前用户模板。模型不能控制模板内容或执行身份。
- 本仓库实际实现与真实 REST/数据库测试：业务递归、身份绑定、指标编译、历史失效和接口一致性由项目代码负责，不能转述为 Superset 原生具备所有 HR 规则。

这次交付证明的是：完整人员样本可以通过可配置的 Superset 访问控制接入Agent，并保留原指标语义与查询功能。真实企业上线仍需确认正式业务规则、可信 SSO、权限发布/同步、连接与模板管理、负载容量和运维要求。
