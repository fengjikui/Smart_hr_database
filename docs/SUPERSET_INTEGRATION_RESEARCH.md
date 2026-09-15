# Superset 集成：权限可行性、查询路径与 OA 身份

研究日期：2026-09-15。代码核对固定到 Apache Superset `6.1.0`，不是滚动更新的 `master`。截至研究时，GitHub 官方发布列表和 PyPI 的最新正式版本均为6.1.0。内网实际版本尚待确认。本文讨论方案；本机实测结果另见实验目录，不能把方案描述当成已完成生产接入。

## 判断

**可以用 Superset 承担受控查询的角色、数据集和行级过滤，但不能把它当成通用数据库权限代理。** 对现有系统最适合的第一条路线是：保留问题理解、语义目录和类型化查询计划，以用户身份调用 Superset 图表数据 REST API，由 Superset 注入 RLS，由 PostgreSQL 视图和数据库授权限制可读字段。先验证这一条路，再决定是否开放 SQL Lab 或 MCP 的自由SQL工具。

业务授权规则不会因为更换组件而消失。Superset 解决通用权限管理和执行挂接；“谁管理谁、哪个HRBP服务谁、管理者是否继承服务范围”仍需我们明确，并通过数据库对象或经过评审的授权服务表达。把Python循环改为PostgreSQL递归视图是实现位置的改变，可靠性仍来自可解释规则、权限反例、版本管理、评审与回归验证。

官方明确说 Superset 不是数据库防火墙，要求数据库账号遵循最小权限。见[6.1.0安全文档](https://superset.apache.org/admin-docs/6.1.0/security/)。

## 能配置哪些权限

| 需求 | 合适的实现 | 不能误解的地方 |
| --- | --- | --- |
| 登录、用户与角色 | Superset/FAB认证及用户角色管理 | 演示身份选择器不是企业认证 |
| 数据集、图表、看板访问 | Gamma加业务角色，配置数据集访问 | 不给普通问数用户Admin、Alpha或全库访问 |
| 员工仅本人、主管看全部层级下属 | PostgreSQL关系视图＋Superset动态RLS | Superset没有理解公司组织树的现成复选框 |
| HRBP服务对象、主管继承下属服务范围 | 配置关系数据、角色规则＋递归视图 | 不是“能看见某人，就能继承此人的所有权限” |
| 不同角色看到不同字段 | 分级数据库视图、分别使用最小权限数据库账号、绑定不同数据集 | 从列选择器里隐藏字段不构成列权限；不能让公共连接仍可读取原始敏感表 |
| 授权内聚合、明细、导出 | 受控数据集查询与角色操作权限 | 导出、样本、图表、SQL工具要分别验收 |
| 撤权与关系调整 | 更新授权配置并使会话/缓存/历史版本失效 | 用户ID缓存隔离不等于关系变更后自动失效 |
| 任意SQL都无法越权 | 优先数据库原生RLS/数据库角色等硬边界，再叠加入口限制 | 不能仅以一条Superset RLS配置作保证 |

角色不仅控制列：它也能决定能访问哪些数据集、适用哪些行过滤、能否运行SQL或管理对象。多角色的资源许可通常会扩大可访问对象；Superset多条RLS的合并则有独立规则：同一非空group key内用OR，不同组以及未分组条件之间用AND。配置前应明确“取并集”还是“取交集”，不要把业务角色叠加直接当成人员范围叠加。规则实现见[权限管理器](https://github.com/apache/superset/blob/6.1.0/superset/security/manager.py)。

## 现有 HR 权限属于什么策略

可以描述为 **RBAC（角色能力）＋ReBAC（关系决定人员范围）**，必要时再加ABAC（在职状态、业务区域、数据敏感等级等属性）。这是常见的组合思路，但我们这条HR继承规则需要业务确认，不能称为所有公司通用标准。

定义当前用户为u：

- 本人集合：`{u}`。
- 管理范围：根据`head_person_id`反向递归取得直属与间接下属。
- 直接HRBP服务范围：`dept_hrbp_id = u.person_id`的人员。
- 继承服务范围：用户的管理线下属中，作为HRBP所服务的人员。
- 最终人员集合：角色启用的上述来源取并集并去重；字段与操作权限单独限制。

HRBP服务边只用来增加被服务人员，不作为新的管理递归入口。举例：HRBP服务主管J，但J的下属K归另一个HRBP服务，则K不会仅因为“J能看K”自动进入这个HRBP的范围。

现有实现可从`backend/hr/v2/auth.py`的`grants()`读起：角色配置来自`RolePolicy`，管理链检查环和孤儿，`inherited`只在管理线下属中寻找HRBP。新的实验用同一规则构造小型反例，并用PostgreSQL递归视图表达，便于逐行解释。

## Superset 内部如何起作用

1. 请求先通过认证，生成当前Superset用户，取得其角色和数据集访问权限。
2. 查询一个数据集时，权限管理器找出适用的RLS：Regular匹配所列角色；Base作用于所列豁免角色之外的用户。
3. 使用可信的当前用户宏渲染动态条件，再把RLS条件加入SQL。聚合在过滤后的人群上计算。
4. Superset使用数据连接的数据库账号执行SQL。数据库最后决定该账号能否读取对应表、视图和列。

实验中的Base过滤器没有豁免角色，配置为：

```sql
person_id IN (
  SELECT target_id FROM authz.visible_people
  WHERE superset_user_id = {{ current_user_id() }}
)
```

`current_user_id()`是**Superset自己的用户主键**，不是OA的person_id。实验通过`authz.identity_map`显式映射；未映射时没有匹配行，返回空集合。映射和角色只能由受信任的管理流程维护，不能由问题文本或前端参数覆盖。

`authz.role_policy`控制是否展开管理线、HRBP和继承；`authz.management_closure`用递归CTE表达组织关系；`authz.person_access`保留来源；`authz.visible_people`去重。检测到管理环时整个授权视图返回空集合。孤儿关系由外键拒绝。生产版还应有可见的数据质量告警，不能只有“零结果”。

动态Jinja不是给模型任意执行的模板语言。开启模板后，要限制数据集/模板编辑者；普通问数用户只调用预先配置的数据集。原理见[SQL模板实现](https://github.com/apache/superset/blob/6.1.0/superset/jinja_context.py)和[Sqla数据集模型](https://github.com/apache/superset/blob/6.1.0/superset/connectors/sqla/models.py)。

## REST、SQL Lab、MCP的区别

| 路径 | 接收的东西 | 6.1.0需要关注的行为 | 本系统建议 |
| --- | --- | --- | --- |
| 图表数据REST API | 数据集ID、字段、已批准指标、过滤与分组 | 按数据集权限和RLS生成查询 | 首选集成入口，最接近现有类型化Plan |
| SQL Lab REST API | SQL字符串 | `RLS_IN_SQLLAB`默认False，必须显式开启并验证SQL形态 | 不向普通问数账号开放 |
| MCP `get_chart_data`等 | MCP工具参数 | 身份认证＋工具RBAC＋具体工具数据访问逻辑 | 适合后续Agent工具，但需逐工具白名单 |
| MCP `execute_sql` | SQL字符串 | 调用`Database.execute()`，其SQLExecutor会应用RLS，不依赖SQL Lab的同一个开关 | 不因为有MCP协议就认为任意SQL安全 |
| 直接连接PostgreSQL | 数据库协议和SQL | 数据库自身的账号、授权、RLS决定结果 | Superset不会拦截这条独立连接 |

源码依据：[SQL Lab执行器](https://github.com/apache/superset/blob/6.1.0/superset/sql_lab.py)、[默认开关](https://github.com/apache/superset/blob/6.1.0/superset/config.py)、[MCP SQL工具](https://github.com/apache/superset/blob/6.1.0/superset/mcp_service/sql_lab/tool/execute_sql.py)、[统一SQLExecutor](https://github.com/apache/superset/blob/6.1.0/superset/sql/execution/executor.py)。

**RLS绑定的是Superset登记的数据集。** 对底层数据库中另一个可读、但未登记或未正确关联RLS的视图，不能假定它自动继承过滤。SQL解析、表别名、CTE、JOIN和子查询的覆盖都需测试。实验专门提供`unregistered_probe`和一个独立SQL探针账号，用来演示这一边界；它不是应开放给业务用户的生产配置。

Superset是Web分析平台，不是实现PostgreSQL协议的数据库。我们的执行器不能只把数据库连接串改成Superset地址；需要REST或MCP适配层。MCP主要改变工具发现与调用方式，权限强弱取决于认证主体和工具实现。

MCP生产接入需要认证和真实用户映射，不使用固定Admin开发身份。以官方固定版本配置为准，不能把Next文档中新增的选项直接当成6.1.0已具备功能。参见[MCP部署文档](https://superset.apache.org/admin-docs/6.1.0/configuration/mcp-server/)与[6.1.0认证源码](https://github.com/apache/superset/blob/6.1.0/superset/mcp_service/auth.py)。

## 与现有 LangGraph 查询流程如何结合

建议流程：`OA登录 → 服务端身份映射 → 读取该身份可用的语义目录 → 模型生成Plan → 确定性计划校验 → 以对应Superset用户调用图表数据API → Superset RLS → PostgreSQL列级视图 → 结果组织、核验和历史`。

现有系统已经不是完全自由的NL2SQL：模型生成受约束计划，我们按白名单编译SQL。保留这点有价值。接Superset时，Plan中的字段和指标映射到批准的数据集与指标，不允许模型自己指定任意数据库ID、数据集ID、角色或用户。

详细口径、口语别名、字段“是什么/不是什么”仍可由现有语义目录维护。把批准的数据集、字段说明和指标同步到Superset，设定一个发布源及版本，避免两套口径独立修改。节点调试新增“Superset请求/有效用户/数据集/过滤后结果”，但不记录访问令牌。

不能让所有OA用户共用一个Superset Admin token再只在问题里带person_id。此时Superset看到的是同一个管理员，动态RLS无法区分真实提问者。

后续真正切换执行器时，历史记录和查询缓存的授权指纹也要改为引用新的角色、数据集、关系和政策版本，不能继续只看旧SQLite模拟库的指纹。

## OA 在其中的作用

OA解决“你是谁以及登录是否仍有效”；它不自动完成HR数据授权。最低需要以下链路：

1. 后端完成授权码交换与回调校验，通过可信userinfo或经过验证的ID token取得身份。不能直接相信浏览器传来的person_id。
2. 明确OA的person ID是否就是人员表的person_id。若只有工号，保留前导零并按`employee_no`唯一映射；找不到或多重匹配时拒绝建立授权上下文。
3. 从人员主数据补充部门与当前汇报关系；从经批准的角色配置获得HR、主管、员工和导出等能力。不能仅凭部门名称或职务名称猜角色。
4. 为Superset建立同一人的用户映射和角色。可让OA/统一IdP同时为两个应用提供SSO；或由后端通过明确配置的身份桥接方式获得受限、短时效的Superset调用身份。OA令牌不会天然被Superset接受。
5. 每次访问检查登录有效性和授权版本，处理调岗、离职、撤权、登出以及缓存失效。

如果不接Superset：替换现有演示登录，保留现有`principal → grants → allowed_fields → query`结构是可行的；但还必须去掉公开的身份切换接口、接入真实数据、补齐会话失效和角色治理。不是把OA的ID塞进前端后其余完全不用改。

本地OA参考材料还有一处需纠正：Starlette `SessionMiddleware`的Cookie是签名的，内容可被客户端读取，并非加密存储（见[官方会话中间件说明](https://starlette.dev/middleware/#sessionmiddleware)）。不要据此把access/refresh token放入前端可读Cookie；建议Cookie只存不透明会话ID，令牌放服务端。OA示例中的`expires_in`单位和时间戳含义也必须以实际响应契约确认，不能推广成OAuth通用规则。

## 数据库原生权限作为更强边界时

若未来要允许自由SQL，可以在PostgreSQL落实原生RLS和列授权，再把Superset当上层消费工具。数据库`current_user`默认是连接池账号，不是OA用户；必须设计可信的身份传递、数据库角色切换与连接池复位。

特别不能把可被同一个SQL调用者任意`SET`的自定义session变量当作不可伪造身份。超级用户、BYPASSRLS角色以及通常情况下的表owner会绕过原生RLS；要验证实际执行账号、FORCE RLS和视图owner/invoker语义。参见[PostgreSQL行安全](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)、[视图安全属性](https://www.postgresql.org/docs/current/sql-createview.html)。实验当前主要证明Superset数据集RLS＋数据库列隔离，不把它宣称成已实现数据库原生行安全。

## 本机实验与后续沟通

实验配置、合成关系样例、SQL对象及真实接口验证脚本放在`integrations/superset/`。Superset元数据库与HR业务库分开，公共/敏感数据使用不同数据库只读账号；本地密码在忽略目录生成，不提交Git。查询缓存关闭，先验证撤权效果。当前HR演示的端口和数据不改变。

需要向主管、OA负责人、HR业务与DBA确认：

1. 内网Superset镜像标签、启用的功能开关、登录方式，以及是否允许增加数据集与RLS配置。
2. 主管期待的是看板/受控查询的权限，还是任何用户自写SQL都不能越权。
3. Superset是否允许普通人员编辑数据集、运行SQL Lab、导出；哪些字段只是可看、可聚合，哪些可下载。
4. HR继承规则是否正式成立，跨部门HRBP服务是否继续展开下属；多角色权限取并集还是交集。
5. OA身份字段与person_id的对应关系、userinfo响应样例、是否支持OIDC/JWKS、回调登记和登出机制。
6. 角色由OA组、HR配置还是安全审批产生；部门/关系变更的同步频率和撤权时效要求。
7. 数据规模、并发和高频查询：大规模时要评估带索引的闭包/授权表或物化视图，不能把12人样例等同于生产性能证明。

推荐先交付可重复的权限验收证据，再做一个可切换执行适配器。我们需要验证的是“配置正确且负面用例过关”，不是仅凭项目归属或代码来源作安全判断。
