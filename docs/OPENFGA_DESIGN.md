# OpenFGA 方案：实现、职责与边界

本方案沿用 300 人、26 字段和 20 道固定计划，新增可切换后端 `HR_QUERY_BACKEND=openfga`。
Superset 方案和学习标记保持原样；两种方案分别连接不同 PostgreSQL 容器、数据库和应用状态目录。
模型仍产生结构化 Plan，程序编译白名单 SQL。新增工作没有开放自由 SQL。

## 1. 先回答“换框架后什么改变了”

| 事项 | Superset 方案 | OpenFGA 方案 |
|---|---|---|
| 谁可以看到哪些员工 | SQL 视图计算关系，Superset RLS 选当前账号 | OpenFGA 模型递归判断每个人的 viewer |
| 角色配置 | PostgreSQL role_policy + Superset 角色 | 源策略配置 → company 能力与 role#member tuples |
| 当前登录身份 | 应用 persona → Superset 用户 | 应用 persona → person_id → user:Pxxxx |
| 列权限 | 两套出口/账号 + 应用字段检查 | FGA 字段组能力 + 应用依赖检查 + PG 视图列遮蔽 |
| 谁执行数据库查询 | Superset Chart Data API | 我们的白名单 PostgreSQL 执行器 |
| 业务平台账号 | Superset 用户与角色 | OpenFGA 没有业务登录账号；应用仍需身份系统 |
| 关系变更 | 当前视图读取底表 | 源表变更→待同步拒绝→新 store/快照整批发布 |
| 业务可视化配置台 | Superset 有平台管理页面 | 本轮是 DSL/SQL/CLI；没有假称已交付业务审批 GUI |

OpenFGA 接管关系授权判断，但不会替我们决定 HR 规则，也不会执行或拦截任意 SQL。
本方案仍需要可信的应用执行点、数据同步、身份映射和权限测试。

## 2. 文件地图

| 文件 | 主要职责 |
|---|---|
| integrations/openfga/model.fga | 唯一授权模型源码；关系、递归、角色能力组合 |
| integrations/openfga/transform.mjs | 调用 OpenFGA 官方 syntax-transformer 0.2.2 |
| integrations/openfga/model.py | 调用转换器；DSL 不合法时停止发布 |
| integrations/openfga/schema.sql | 演示源表、变更版本触发器、发布表、PG RLS |
| integrations/openfga/run.py | prepare/materials/init/seed/sync/status/check/watch |
| integrations/openfga/compose.yaml | 3 个服务：PG、迁移、OpenFGA；固定版本、资源上限 |
| backend/hr/fga_client.py | 带认证的 REST、固定 model ID、完整 BatchCheck 检查 |
| backend/hr/openfga_source.py | 当前主体映射、授权快照、字段/行范围、历史指纹 |
| backend/hr/openfga_query.py | PostgreSQL 方言；带事务授权上下文执行白名单查询 |
| backend/hr/auth.py | 统一授权入口，按后端选择 source |
| backend/hr/query.py | 共用校验、SQL 编译结构、结果格式 |
| backend/hr/service.py | 输出前重新鉴权；核验/历史/导出复用权限 |
| integrations/openfga/verify.py | 原种子的真实服务回归，模型使用固定替身 |
| integrations/openfga/verify_changes.py | 临时改动源表验证撤权与同步，finally 恢复 |
| integrations/openfga/verify_materials.py | 临时库中执行手工SQL材料，验证行列与事务边界 |
| tests/test_openfga.py | 缺项、错误响应、源数据异常等单元测试 |
| .github/workflows/openfga.yml | 新建真实服务并执行固定计划和变更回归 |

## 3. 模型如何表达业务规则

对象类型共四种：user、role、company、person。

- `person:P0005#owner@user:P0005`：员工自己的数据。
- `person:P0005#manager@person:P0004`：员工的直接主管。
- `person:P0005#hrbp_provider@person:P0003`：员工的 HRBP。
- `role:manager#member@user:P0004`：王灏具有 manager 角色。
- `company:main#reports@role:manager#member`：manager 角色具有查询管理线的能力。

只保存直接边。`supervisors: owner from manager or supervisors from manager` 找直接/间接主管。
`reports_access` 把这个关系与 reports 能力取交集。
HRBP 服务与继承下属 HRBP 服务各有独立关系，最后 viewer 取并集。
继承只沿“管理下属中的 HRBP”扩展，不把已服务员工的管理下属继续扩大为授权。

模型里的 `owner` 表示数据对应的员工本人，不是 PostgreSQL 表所有者。
`self` 是 FGA 保留字，不能作为关系名；课堂最初验证时已发现并改成 owner。

字段组和 details/export 也由 FGA Check 返回。角色策略 JSON 只是同步输入，运行时不能绕过
OpenFGA 直接读取 JSON 就说有权限。`admin` 仍是集团管理线业务身份，不代表引擎超级权限。

## 4. 请求如何走完

1. Cookie → 服务端 persona；浏览器不能传 FGA user/store/model 替代身份。
2. 读取 active 发布及源版本；若源版本变了而发布未跟上，返回 409。
3. 核对 persona/person_id/业务角色。缺失、变更或不匹配都拒绝。
4. 使用固定 store/model、HIGHER_CONSISTENCY，BatchCheck 当前公司能力和全部候选人员关系。
5. 每批 50 项，服务端批内并发限制为 5，读并发限制为 4。每项必须有布尔结果，无缺项/错误。
6. 得到 viewer 集合、各来源子集和字段组；路径/深度计算仅用于展示与范围收窄。
7. 用只读连接、参数化 `set_config(..., true)` 设置本事务 generation、allowed_ids、groups。
8. 模型只看到授权目录；生成 Plan 后完整检查输出、筛选、排序、指标依赖字段。
9. PostgreSQL RLS 先约束版本和 ID，安全屏障视图遮蔽未授权字段，白名单 SQL 做业务过滤聚合。
10. 返回/存历史前重新检查权限指纹；查询期间版本或授权变化则丢弃结果。

调试节点包含引擎、store/model、主体、检查数量、候选数、授权数、能力和真实 SQL。
不包含 PG 密码和 OpenFGA 密钥。OpenFGA Check 返回结论，页面解释路径是应用根据源边组合的，
不能把它称作引擎提供的完整推理证明。

## 5. 同步输入输出与一致性

输入：hr_source.people 的当前记录、identities、policy，和 model.fga。
输出：新 store、新 model ID、直接关系 tuple、新业务快照、active 指针和本机审计材料。

当前源表用 `person_id + record(jsonb)` 保存完整 26 字段，便于版本快照及手工修改；
`hr_api.people` 再投影为原应用使用的列。它是演示接入表，不要求生产宽表也改成 JSONB。

`sync` 按顺序：事务锁→源表 SHARE 锁→读取完整快照→检查主键/环/引用/配置→
官方 DSL 转换→创建新 store/model→分批写 tuple→发布自检→插入业务快照→提交 active。
该 SHARE 锁会短时阻塞写源表，适合课堂小样本，不应照搬到高写入量生产主库。

业务查询只看已发布版本，不会看到“tuple 写了一半、数据导了一半”。源表改动后触发版本递增，
尚未同步时明确拒绝查询；同步失败不切换 active，继续拒绝过期版本。
无变化时不会新建 store。旧发布/store 暂时保留作审计，没有自动 GC；失败的未激活 store 也可能留下，
后续需要管理员制定保留期与清理任务，不能无上限运行。

`watch --interval 10` 是前台轮询同步示例，不是生产 CDC。本地触发器能感知本库中任意系统写入，
无需每个业务程序配合发事件。但若生产只有 SELECT 权限且不能装触发器，这套即刻拒绝保证不能直接
成立；需由源系统提供可靠版本/CDC 位点，或接受并明确轮询的陈旧窗口。没有声称已自动接入真实业务库。

## 6. 数据库安全的准确边界

- 应用账号 hr_fga_reader 只读受控视图和发布元数据，不能 SELECT 源表或原始快照表。
- 视图归非登录、非超级用户 hr_fga_view_owner；该角色读底表受 ENABLE/FORCE RLS 限制。
- 没有事务授权上下文时，出口返回 0 行。合同等未授权字段为 NULL，业务 API 本身直接拒绝使用这些列。
- **GUC 不是防伪令牌**：掌握 reader 凭据的程序能自己设置 allowed_ids/groups。因此可信后端是执行边界，
  不能把 reader 账号给终端用户，也不能给模型开放原始 SQL 工具。PG RLS 这里是执行防遗漏，不是独立复核 FGA。
- 本地 OpenFGA 使用预共享密钥认证，运行配置也有该密钥。它不具备细分读写作用域；生产需管理服务与查询服务
  分网段/不同身份，通过只允许 Check 等接口的网关或受支持的授权机制隔离管理操作，并启用 TLS。
- 开放 API 仅监听宿主机回环地址；未开放 Playground。没有 SSO、多租户边界、业务审批界面或生产发布审批。

## 7. 性能与容量

本演示每份授权快照约 1209 次逻辑 Check（300 人×4 关系+9 能力），按 50 项合批。
选择 BatchCheck 是为了明确枚举完整结果，避免将 ListObjects 的结果上限/时间限制误当作全量。
查询/历史前后的强校验会重复请求，几百人可演示，但不能据此宣称能直接支撑全公司海量数据。

超过 1000 人、组织路径超过 30 层会明确拒绝，绝不只统计前 1000 人。正式扩容需测试 ListObjects/
授权索引方案、可信发布版本缓存、批量查询成本、撤权时效和数据库分页。缓存优化必须保留失效协议。
本机 PG/OpenFGA 分别限制 CPU 与内存，不进行并行模型推理。默认引擎 3 秒超时在冷启动大批鉴权中触发过；
现在请求超时 10 秒、HTTP 上游 15 秒、客户端 20 秒，超时仍是拒绝，不会悄悄少算人数。

## 8. 官方依据

以下是框架概念的来源；上面的表结构、发布流程和执行点是本项目设计，不能误归为 OpenFGA 自动提供。

- [OpenFGA Concepts](https://openfga.dev/docs/concepts)：模型、tuple、user/object/relation。
- [Parent-Child Objects](https://openfga.dev/docs/modeling/parent-child)：父子关系继承建模。
- [Immutable Authorization Models](https://openfga.dev/docs/getting-started/immutable-models)：固定模型版本。
- [Query Consistency](https://openfga.dev/docs/interacting/consistency)：HIGHER_CONSISTENCY 的含义及缓存边界。
- [Relationship Queries](https://openfga.dev/docs/interacting/relationship-queries)：Check/ListObjects 的职责及数量限制。
- [OpenFGA API 定义](https://github.com/openfga/api/blob/main/openfga/v1/openfga_service.proto)：BatchCheck 每项结果与错误。
- [官方语言转换器](https://github.com/openfga/language)：DSL 与 API JSON 的转换。
- [部署与认证配置](https://openfga.dev/docs/getting-started/setup-openfga/configure-openfga)：预共享密钥、TLS 和服务器配置。
- [PostgreSQL 行安全](https://www.postgresql.org/docs/17/ddl-rowsecurity.html)：RLS、表所有者和超级用户边界。
- [PostgreSQL 配置函数](https://www.postgresql.org/docs/17/functions-admin.html#FUNCTIONS-ADMIN-SET)：事务局部 set_config。
