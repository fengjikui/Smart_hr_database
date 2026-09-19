# V2 完整数据迁移与 Superset 授权

这里操作独立 PostgreSQL 数据库 `hr_v2`，不覆盖此前课堂的 `hr_lab`、`LEARN_*`，也不重启服务。
宿主机先按 `../README.md` 启动既有 Superset 实验环境，再从仓库根目录运行：

```sh
uv run python integrations/superset/v2/run.py export
uv run python integrations/superset/v2/run.py setup
uv run python integrations/superset/v2/run.py status
uv run python integrations/superset/v2/run.py verify-storage
uv run python integrations/superset/v2/run.py export-connection-info
```

`export` 读取当前 V2 的 `store.people()`、`store.policy()`、字段目录和五个模拟身份，保留全部人员和字段、前导零、空值、快照日。
`setup` 自动先导出，再创建 PostgreSQL 表/视图、Superset 数据源/数据集、用户/角色/RLS/看板。
首次之外再次执行 `setup` 会保留既有 PostgreSQL 人员快照、业务策略及手动修改过的 Superset 授权。
只有显式运行 `uv run python integrations/superset/v2/run.py sync-data` 才以最新 V2 快照重导人员和业务策略；它依然不会重置 Superset 用户角色或 RLS。
如果变更合同字段组，应同时检查 Superset 合同数据集角色：脚本不会替你覆盖手动角色。

## 文件与职责

| 文件 | 执行地点 | 作用 |
|---|---|---|
| `export.py` | 宿主机 | 当前 V2 的完整快照与 SHA-256 数据指纹 |
| `run.py` | 宿主机 | 发现现有容器、保存仅本机凭据、执行安装和检查 |
| `schema.sql` | PostgreSQL | 角色策略、身份映射、递归管理线、HRBP 来源、全图校验 |
| `setup.py` | Superset 容器 | 建独立库、导入宽表、创建公开/合同视图、配置 Superset 对象 |
| `status.py` | Superset 容器 | 只读打印实际用户/角色/RLS/数据集及可见人数 |

本机输出均位于 `integrations/superset/.local/v2/`，已被项目 `.gitignore` 排除：

- `fixtures.json`：可审阅的导入快照，不含密码。
- `manifest.json`：实际数据集 ID、账号映射、数据指纹、看板入口，不含密码。
- `credentials.json`：平铺的 `username -> password` 映射，文件权限 0600，不输出明文。
- `database-credentials.json`：两个 PostgreSQL 只读账号及连接地址，权限 0600；Superset 容器用 `postgres:5432`，宿主机用 `127.0.0.1:55432`。`setup` 会生成；已安装环境可仅运行 `export-connection-info` 补充生成，不改变任何账号、数据库视图或 RLS。
- `storage-verification.json`：完整导入指纹、真实数据库拒绝、Superset 对象配置与旧课堂保留检查报告。`verify-storage` 全程只读。

## PostgreSQL 三层结构

- `v2_data.people`：完整 V2 宽表，日期保留 ISO 文本，年龄为整数。
- `v2_auth`：业务角色策略、登录身份映射、快照元信息及授权视图。
- `v2_api`：Superset 唯一可读出口；公共视图物理上不包含两个合同字段，合同视图额外检查业务字段组。

管理递归计算本人/直属/间接下属；HRBP 服务与继承服务各自计算再合并。任何主管环、主管孤儿、HRBP 孤儿都会使授权视图返回空集，且 `context.graph_valid=false`，Agent 应将其报告为授权数据异常而不是“查到 0 人”。

`v2_public_reader` 只能读取公共人员、公共事件、自身上下文视图；`v2_contract_reader` 只能读取合同人员和合同事件视图。它们不能读取宽表或授权配置表。两者默认只读并设 10 秒 SQL 超时。

注意：数据库视图为不同查看人分别计算候选行，并带 `_viewer_id`。**这些连接账号本身不代表某位最终用户**。Superset Base RLS 根据可信登录用户绑定 `_viewer_id`，负责最终的用户行隔离。因此不能把共享数据库账号给业务用户，也不能另开绕过 Superset 的任意 SQL 接口。

## Superset 对象清单

2 个连接：`V2_public`、`V2_contract`，都指向 `hr_v2`，使用不同 PostgreSQL 只读账号。

5 个数据集（均是物理视图，schema 为 `v2_api`）：

| 数据集 | 用途 |
|---|---|
| `people_public` | 24 个公开业务字段、授权来源、关系、月份 |
| `people_contract` | 26 个完整业务字段以及同样的辅助列 |
| `events_public` | 公开人员展开成入职/离职事件，附 `event_day/event_month/is_hire/is_exit` |
| `events_contract` | 含合同字段的事件出口 |
| `context` | 当前身份、业务规则、快照及图校验结果 |

3 条 Base RLS，角色列表全空，即不设业务豁免：

| 名称 | 数据集 | Clause |
|---|---|---|
| `V2_scope_public` | 公共人员、公共事件 | `_viewer_id = {{ current_user_id() }}` |
| `V2_scope_contract` | 合同人员、合同事件 | `_viewer_id = {{ current_user_id() }}` |
| `V2_context_scope` | 上下文 | `superset_user_id = {{ current_user_id() }}` |

8 个自定义角色：`V2_Data_public`、`V2_Data_contract`、`V2_Context`，以及 `V2_Role_hr_lead/hrbp/manager/employee/admin` 五个业务标签角色。业务标签本身不增加平台权限。前 3 个角色只获得对应数据集的 `datasource_access`，不授 `database_access`、`all_datasource_access`、SQL Lab 或配置管理权限。

7 个账号：

| 账号 | 用途 |
|---|---|
| `v2_hr_lead` | 王承哲，HR 主管 |
| `v2_hrbp` | 姜姜，HRBP |
| `v2_manager` | 王灏，部门主管 |
| `v2_employee` | 冯基魁，员工 |
| `v2_admin` | V2 集团管理线业务身份，**仅 Gamma，绝不是 Superset Admin** |
| `v2_unmapped` | 未映射负例，有公开数据集访问权但返回 0 行 |
| `v2_setup_admin` | 唯一配置管理员，不用于模拟业务结果 |

普通业务账号 = Gamma + 公共数据集角色 + 上下文角色 + 本人的业务标签；允许合同字段的身份另加合同角色。安装时按当前 V2 策略决定。

`role_policy.details/export` 是交给 Agent 执行的业务开关，不会自动改变 Superset 自带图表菜单。
本次数据集角色主要控制“哪些行、哪些字段可读”；若还要求 Superset UI 全面禁止下载或明细，
需要另行配置相应平台功能权限并补充 UI/API 测试，不能只修改这两个数据库布尔值。

人员看板 `/superset/dashboard/v2-people-public/` 和合同看板 `/superset/dashboard/v2-people-contract/` 已配置表格、搜索、分页。请换成业务账号观察，不能用超级管理员的返回结果证明普通用户权限。

## Agent 对接契约

Agent 从受信会话确定 persona，再在 `manifest.json.principals` 中找到独立 Superset 用户，以该用户登录，向 Superset Chart Data API 提交注册数据集的结构化查询。不能信任问题文本中的用户名或查看人 ID，不能用配置管理员代理所有用户。

先读取 `context` 验证身份和规则，检查 `graph_valid`；再根据所需字段选择公共或合同数据集。Superset 根据当前登录 ID 追加 RLS，PostgreSQL 完成授权人群与业务筛选后返回结果。`manifest.datasets[*].columns` 是真实注册列清单；后端必须对白名单之外的列和任意 SQL 表达式拒绝请求。

`_origins` 是原 V2 `auth.grants()` 兼容的 JSON 数组文本，含 `kind/path/text`；`_depth` 为到当前查看人的管理线深度，非管理下属可能为空。`relation` 按本人、直属下属、间接下属、HRBP服务人员顺序分类。查询完成后不再依赖原 SQLite 授权逻辑进行二次“放行”。

这套演示没有消除所有自写业务逻辑：**管理递归和 HRBP 规则在受审查的 PostgreSQL 视图中，Superset 提供成熟的登录、角色授权、数据集访问和 RLS 执行机制。** 导入、模型查询计划白名单、业务身份绑定和跨系统一致性仍需应用实现并测试。
