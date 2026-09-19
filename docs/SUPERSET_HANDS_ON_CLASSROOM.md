# Superset 权限实操课：从生成数据到亲手填写规则

日期：2026-09-19。环境：本机 Superset 6.1.0、PostgreSQL 17.11。全部是合成数据。

今天的学习方式是：**一次只改一个配置，先预测结果，再查询，看执行 SQL，最后解释是谁让规则生效。** 不需要一次读完整篇；每完成一课，可以回到对话里让我检查和解释。

## 0. 已替你准备什么，哪些留给你做

已准备：12 名模拟员工、12 笔订单、12 条薪资、组织与服务关系、两个只读数据库连接、四个数据集及表格看板、一个管理员和七个学习账号。

**留给你亲手做：给角色授予数据集访问权、创建和修改 RLS 条件、组合规则、观察查询结果。** 初始业务角色为空，没有课堂 RLS。验收脚本会短暂应用规则测试，然后恢复空白。

这里只操作 `LEARN_*` 角色、连接和看板，以及 `learn_*` 数据库 schema；不要修改已有 `HR_LAB_*`、`hr`、`authz`、`analytics` 对象。

| 项目 | 入口／位置 |
|---|---|
| Superset 登录 | [打开本机 Superset](http://127.0.0.1:8088/) |
| 订单看板 | [LEARN · 01 订单与区域](http://127.0.0.1:8088/superset/dashboard/learn-orders/) |
| 人员看板 | [LEARN · 02 人员与汇报线](http://127.0.0.1:8088/superset/dashboard/learn-people/) |
| 薪资看板 | [LEARN · 03 敏感薪资](http://127.0.0.1:8088/superset/dashboard/learn-payroll/) |
| 完整模拟电话看板 | [LEARN · 04 完整模拟电话](http://127.0.0.1:8088/superset/dashboard/learn-orders-private/) |
| 登录资料，仅在本机 | `integrations/superset/.local/classroom/credentials.json` |
| 实际数据集 ID、权限名称 | `integrations/superset/.local/classroom/manifest.json` |
| 完整模拟数据，可阅读 | `integrations/superset/.local/classroom/generated-data.json` |

密码不写进本文，不提交 Git。上述链接要求本机服务正在运行，服务启动方法沿用 `integrations/superset/README.md`。本课堂准备过程没有重启已有服务。

### 账号怎么使用

| 账号 | 对应人员 | 业务角色 | 练习用途 |
|---|---|---|---|
| `learn_admin` | 管理员，不代表业务人员 | Admin | 手填权限配置、查看完整合成数据 |
| `learn_east` | E | LEARN_East | 华东订单、本人订单 |
| `learn_west` | I | LEARN_West | 华西订单、反例比较 |
| `learn_manager` | D | LEARN_Manager | 多区域、跨部门汇报线 |
| `learn_hrbp` | C | LEARN_HRBP | 直接 HRBP 服务范围 |
| `learn_hrlead` | B | LEARN_HRLead | 下属 HRBP 服务范围继承 |
| `learn_finance` | X | LEARN_Finance | 单独授予敏感字段入口 |
| `learn_unmapped` | 没有人员映射 | LEARN_Unmapped | 验证动态身份映射缺失时返回空范围 |

所有非管理员还拥有 `Gamma` 和空的 `LEARN_Reader`。`LEARN_Reader` 是我们创建的课堂角色；`Gamma` 是 Superset 自带角色。**不要修改 Gamma 本身。**

财务资格是这个教学账号明确获得的角色，不由 X 的岗位名称推断。管理员用于配置；效果验收使用对应普通账号，不能始终以管理员身份看结果。

同一个浏览器中的两个标签页通常共用登录状态，不是两个独立用户。可以用两个浏览器／不同配置文件，也可以管理员改配置后退出，再登录普通账号。命令行观察工具使用独立 HTTP 会话，不改变浏览器登录状态。

## 1. 第一站：亲自看懂数据从哪里来

### 1.1 生成代码按这个顺序读

文件：`integrations/superset/classroom/generate.py`。

1. `PERSON_FACTS`：手工列出 12 个人及其直属主管、HRBP，保证有可解释的正例和反例。
2. `generate()` 的第一个循环：生成固定工号、学历、模拟薪资。工号是保留前导零的字符串。
3. 第二个循环：给 E、G、I、K 四人各生成三笔订单，确定区域和金额。
4. `EXPECTED`：人工列出的标准答案，不使用待测 SQL 算法来生成答案。
5. `main()`：把生成结果保存为 JSON；**这一步不会连接数据库，也不会改变权限。**

自己重复生成的命令，在项目根目录执行：

```bash
python3 integrations/superset/classroom/run.py generate
```

生成器没有随机数，没有读取真实数据，没有使用当前日期，所以结果可重复。订单日期固定为 2026 年 9 月 1～12 日。

### 1.2 先手算订单

| 订单 | 负责人 | 区域 | 金额 | 分类 |
|---|---|---|---:|---|
| O001 | E | EAST | 1,000 | PUBLIC |
| O002 | E | EAST | 2,000 | PUBLIC |
| O003 | E | EAST | 3,000 | RESTRICTED |
| O004 | G | EAST | 4,000 | PUBLIC |
| O005 | G | EAST | 5,000 | PUBLIC |
| O006 | G | EAST | 6,000 | RESTRICTED |
| O007 | I | WEST | 7,000 | PUBLIC |
| O008 | I | WEST | 8,000 | PUBLIC |
| O009 | I | WEST | 9,000 | RESTRICTED |
| O010 | K | NORTH | 10,000 | PUBLIC |
| O011 | K | NORTH | 11,000 | PUBLIC |
| O012 | K | NORTH | 12,000 | RESTRICTED |

标准答案：总共 12 笔、78,000 元；华东 6 笔、21,000 元；华西 3 笔、24,000 元；华北 3 笔、33,000 元。E 自己只有 3 笔、6,000 元。

`PUBLIC/RESTRICTED` 是业务分类标签，不是 Superset 的内置安全开关。**只有我们配置相应条件，它才会参与限制。**

### 1.3 再读数据分层

文件：`integrations/superset/classroom/schema.sql`，SQL 内有逐段注释。

| 层 | 对象 | 用途 |
|---|---|---|
| 原始业务事实 | `learn_data.people/orders/payroll` | 保存员工、完整订单和薪资 |
| 授权辅助数据 | `learn_auth.identity_map` | Superset 用户 ID 到人员 ID 的映射 |
| 授权辅助数据 | `learn_auth.user_regions` | 一个用户可拥有多个区域 |
| 授权辅助数据 | `learn_auth.role_policy` | 是否启用管理线、HRBP、继承 |
| 计算规则 | `learn_auth.management_closure/visible_people` | 递归求出可以查看的人员 |
| 公共查询出口 | `learn_api.orders/people` | 普通列；订单电话已脱敏 |
| 敏感查询出口 | `learn_api.payroll/orders_private` | 薪资或完整模拟电话 |

公共数据库账号不能读取原始业务表、薪资出口或完整电话出口。视图中的 `security_barrier=true` **不自动产生行权限**。

所有电话都是 `000` 开头的非真实号码，形态仅为演示；例如完整模拟值 `00000000001` 对应 `000****0001`。

### 1.4 数据如何被写入数据库和 Superset

文件：`integrations/superset/classroom/setup.py`。

```text
generate() 产生 Python 字典
→ prepare_database() 用参数化 INSERT 写入 PostgreSQL
→ prepare_superset() 创建账号、空角色、连接、数据集、图表和看板
→ run.py 保存本地入口清单
```

准备命令：

```bash
python3 integrations/superset/classroom/run.py setup
```

通常只在首次准备时执行。重复执行不会清空手填 RLS、已有用户角色、已存在业务记录，但会重新应用课堂 SQL 视图定义，并补齐缺失对象；因此不是“重置课堂”的命令。

如果以后要练习从零写入，建议另建新的实验命名空间，由我带着操作，不要删除原项目数据库卷。

**这一站先回答：为什么华东 6 笔，而 E 本人只有 3 笔？这两种条件表达的权限相同吗？**

## 2. 统一的观察工具：避免把页面提示误当查询结果

浏览器看表格最直观；下面命令可以同时看到当前身份、HTTP 状态、明细、行数、金额合计和实际 SQL。

```bash
uv run python integrations/superset/classroom/run.py inspect --user learn_east --dataset orders
```

它只查询，不创建权限。可替换账号或数据集：`orders`、`people`、`payroll`、`orders_private`。

- HTTP 403：没有该数据集访问权；**不等于查询成功后 0 行**。
- HTTP 200 且 0 行：查询成功，但没有符合权限和业务条件的记录。
- SQL 错误、服务异常：工具明确报错，不伪装成 0 行。

课堂结果只有 12 行，工具的 100 行限额不会截断本样本。以后大数据不能按“当前页行数”宣称全量人数。

若在图表界面找不到查看 SQL 的菜单，就用这个工具观察返回的实际 SQL。管理员在 SQL Lab 查询时，使用 `LEARN_public` 和下面的只读 SQL 可以看业务全量：

```sql
SELECT region, count(*) AS order_count, sum(amount) AS amount_total
FROM learn_api.orders
GROUP BY region
ORDER BY region;
```

管理员与普通用户的结果本来就可能不同，不要拿管理员的全量查询证明普通用户已受限。

## 3. 第 1 课：角色与数据集访问权

**目标：知道“能不能查这张表”和“能看到哪些行”是两层。**

### 改之前

用 `learn_east` 打开订单看板，或者运行观察命令。预期没有权限，REST 为 403。看板可能从列表中不可见，直接链接也不能加载其数据。

### 你亲手填写

1. 用 `learn_admin` 登录。
2. 打开 [经典角色列表](http://127.0.0.1:8088/roles/list/)，在 LEARN_Reader 那一行点击铅笔 **Edit**。本机菜单 Settings → 用户权限 → 角色列表进入的是新版页面；今天优先使用这个经典入口。
3. 确认编辑的名称是 **LEARN_Reader**，不要编辑 Gamma。
4. 在“权限”输入框中搜索 `LEARN_public`，选中订单数据集对应的 **datasource access** 权限。
5. 只选 `learn_api.orders` 对应项，不选数据库级访问、所有数据源访问、SQL Lab 或管理员权限。
6. 保存。

权限项的准确名称与动态数据集 ID 已写入本机 `manifest.json` 的 `datasets.orders.permission`。界面通常形如 `datasource access on [LEARN_public].[orders](id:...)`，以本机实际文字为准。

本机界面注意：2026-09-19 实测，新版 `/roles/` 的权限搜索调用接口时返回 `Filter column ... not allowed to filter`，界面显示 No data。这不代表数据集权限不存在。经典 `/roles/list/` 使用同一套角色权限，已验证搜索与保存可用；没有改动 Superset 源码。

### 改之后

再以 `learn_east` 查询：应看到 12 笔、78,000 元。`learn_west` 也看到 12 笔，因为他们共享 `LEARN_Reader`，现在还没有行权限。

**为什么生效：** Superset 检查用户角色是否拥有该数据集访问权。这里还没有区域筛选。

**回退：** 从 LEARN_Reader 移除刚加的那个数据集权限，查询又应为 403。重新加上，为下一课准备。

## 4. 第 2 课：最简单的固定区域行权限

前提：完成第 1 课，LEARN_Reader 可以访问订单数据集。

打开 [Row Level Security](http://127.0.0.1:8088/rowlevelsecurity/list/)（Settings → 用户权限 → Row Level Security），点击 **+ Rule** 新增一条规则：

| 表单项 | 亲手填写 |
|---|---|
| Rule Name | `LEARN_01_east` |
| Filter Type | `Regular` |
| Tables / Datasets | `LEARN_public` 下的 `learn_api.orders` |
| Roles | `LEARN_East` |
| Group Key | 留空 |
| Clause | 见下面一行 |

```sql
region = 'EAST'
```

**不要写完整 SELECT，也不要在开头写 WHERE。** Clause 填的是条件片段。

Datasets 和 Roles 是选择器：输入关键词后，要点击下拉列表中的已有对象。不要只输入文字就保存，也不要创建同名文字标签。保存成功后对话框会关闭、列表出现新规则。

保存后：

| 查看人 | 预期 |
|---|---|
| learn_east | O001～O006，6 笔、21,000 元 |
| learn_west | 仍为 12 笔、78,000 元 |

为什么华西账号还看全部？因为 Regular 规则只对匹配的 LEARN_East 角色应用。**创建一条限制某角色的规则，不等于所有角色自动默认拒绝。**

运行观察命令，找实际 SQL 中的 `region = 'EAST'`。它是 Superset 在查询时加入的，源订单表没有被删除记录。

可选：把 Clause 改为 `region = 'WEST'`。即便角色名称仍叫 LEARN_East，结果也变成 3 笔华西订单。这说明真正生效的是配置条件，角色名字本身没有魔法。观察后改回 EAST。

## 5. 第 3 课：多条件 AND / OR，防止误配扩大范围

保留上一课的规则，再新增：

| 表单项 | 填写 |
|---|---|
| Name | `LEARN_02_public` |
| Filter Type | `Regular` |
| Tables | 同一订单数据集 |
| Roles | `LEARN_East` |
| Group Key | 留空 |
| Clause | `classification = 'PUBLIC'` |

两个 Group Key 都为空时，各自形成一组，条件按 AND 合并：

```sql
region = 'EAST' AND classification = 'PUBLIC'
```

预期：O001、O002、O004、O005，**4 笔，12,000 元**。

再把两条规则的 Group Key 都填成 `learn_union`，它们在同组内按 OR 合并：

```sql
region = 'EAST' OR classification = 'PUBLIC'
```

预期变为 **10 笔，57,000 元**，只排除 O009、O012。它允许非华东的普通订单进入范围，因此未必符合真实政策。

**这课要理解：** “多了一条规则”不必然更严格，关键看组合方式。完成后删除这两条 LEARN 规则，再继续下一课；不要让它们悄悄与后续条件叠加。

## 6. 第 4 课：本人订单与动态身份

先确保订单数据集上没有上一课的两条规则。

新建 RLS：

| 表单项 | 填写 |
|---|---|
| Name | `LEARN_03_owner` |
| Filter Type | `Base` |
| Tables | 订单数据集 |
| Roles | 留空，表示本课不设置豁免角色 |
| Group Key | 留空 |
| Clause | 下面的子查询条件 |

```sql
owner_id IN (
  SELECT person_id
  FROM learn_auth.identity_map
  WHERE superset_user_id = {{ current_user_id() }}
)
```

预期：learn_east 看到 O001～O003，共 3 笔、6,000 元；learn_west 看到 O007～O009，共 3 笔、24,000 元；learn_unmapped 查询成功但 0 行。

拆开解释：Superset 从可信登录上下文得到自己的用户 ID；我们的映射表把它转为员工 ID；数据库把订单 `owner_id` 与该员工 ID 匹配。

**不要把用户 ID 抄成 E，也不要让提问文本提供这个 ID。** `current_user_id()` 与人员 `person_id` 是不同系统的主键。无身份映射就没有匹配记录。

本机已开启 `ENABLE_TEMPLATE_PROCESSING`。Jinja 模板只由受信任管理员维护，不能给模型任意编辑执行。管理员本人没有课堂人员映射，因此在同样受该 Base 规则约束的查询上可能看到空结果；效果判断仍用普通账号。

Base 的 Roles 是**豁免角色**，与 Regular 的“应用角色”不同。如果误把 LEARN_East 放入 Base 的 Roles，可能让它绕过本条条件。

## 7. 第 5 课：属性／多区域授权

编辑上一条规则，改名为 `LEARN_04_regions`，保持 Base、同一数据集、Roles 留空，Clause 改成：

```sql
region IN (
  SELECT region
  FROM learn_auth.user_regions
  WHERE superset_user_id = {{ current_user_id() }}
)
```

| 账号 | 授权区域 | 预期订单数 | 金额 |
|---|---|---:|---:|
| learn_east | EAST | 6 | 21,000 |
| learn_west | WEST | 3 | 24,000 |
| learn_manager | EAST、WEST | 9 | 45,000 |
| learn_finance | 三个区域 | 12 | 78,000 |
| learn_unmapped | 无映射 | 0 | 0 |

这一条规则适用于很多人，不必为每个人写一份 SQL 条件。人员负责区域变化时，更新授权区域表即可；这张表如何同步属于企业接入工作，当前课堂是我们准备的固定事实。

注意：这里的“属性授权”由区域映射表和 RLS 共同实现，并不是 Superset 自动从岗位名称推导区域。

## 8. 第 6 课：列禁止与脱敏

先用 learn_east 看订单，`phone_masked` 显示部分字符。这个处理发生在 PostgreSQL 的 `learn_api.orders` 视图中，Superset 只拿到已经脱敏的列。

再观察：

```bash
uv run python integrations/superset/classroom/run.py inspect --user learn_east --dataset payroll
uv run python integrations/superset/classroom/run.py inspect --user learn_east --dataset orders_private
```

预期两个入口都被拒绝。

用管理员编辑 **LEARN_Finance**，仅增加 `LEARN_private` 下 `payroll` 与 `orders_private` 两个数据集的 datasource access 权限。

learn_finance 随后能查 12 条模拟薪资及完整模拟电话，learn_east 仍然不能。这一课的敏感数据集暂未配置行过滤，所以财务看到全部 12 条；这是为了单独观察列／数据集边界，**不代表财务在真实企业中默认可以读全公司薪资**。

三层作用分别是：

1. Superset 数据集权限决定能否访问这个敏感出口。
2. 公共数据库账号本身无权读取敏感视图和原始表。
3. 脱敏视图从源头不提供完整电话。

仅在图表设置里隐藏一列，不等于禁止查询者使用该列。为了简洁，本课用两个数据出口演示；不是宣称 Superset 有一个适用于任意 SQL 的通用列权限复选框。

**独立数据集不会自动继承另一个数据集的 RLS。** 如果敏感出口也需要按区域限制，需要给它配置对应 RLS，并验证条件里的字段确实存在。

## 9. 第 7 课：直属、间接下属与 HRBP

### 9.1 先授权人员数据集

管理员编辑 **LEARN_Reader**，在原有 orders 权限之外，再增加 `LEARN_public` 的 `people` 数据集访问权。没有人员 RLS 时，普通账号可以看到 12 人，这是前后对照状态。

新建 RLS：

| 表单项 | 填写 |
|---|---|
| Name | `LEARN_05_people_scope` |
| Filter Type | `Base` |
| Tables | 仅 `LEARN_public` 下的 `people` |
| Roles / Group Key | 都留空 |
| Clause | 如下 |

```sql
person_id IN (
  SELECT target_id
  FROM learn_auth.visible_people
  WHERE superset_user_id = {{ current_user_id() }}
)
```

### 9.2 查精确名单，不能只看数量

| 账号 | 预期人员 |
|---|---|
| learn_east | E |
| learn_manager | D、E、F、G、H、I，共 6 人 |
| learn_hrbp | C、D、E、F、G、J，共 6 人 |
| learn_hrlead | B、C、D、E、F、G、J，共 7 人 |
| learn_unmapped | 空 |

主管 D 的六人范围包含本人；H/I 属于战略客户部但在 D 汇报线下，因此跨部门可见。再加 `department = '华东销售部'` 的业务筛选，范围应变为 D/E/F/G 四人。

HRBP C 服务 J，但 K 的 HRBP 是 X，因此 C 和 B 都不能仅因为能看 J 而看到 K。

### 9.3 回到代码找真正的递归

打开 `schema.sql`，顺着这条链读：

```text
people.manager_id → management_closure → visible_people → RLS 条件 → 最终查询
```

`management_closure` 中的 `WITH RECURSIVE` 由 PostgreSQL 执行；`visible_people` 将本人、主管、HRBP 和继承来源取并集；Superset 把当前用户对应的范围加入查询。

所以这课要说清：**配置入口在 Superset；汇报关系的业务规则在我们定义的 SQL 视图里；实际递归由数据库引擎执行。** Superset 自己并不认识 `manager_id` 的业务含义。

## 10. 第 8 课：默认拒绝、撤权与错误排查

默认拒绝有不同层次：初始空数据集权限得到 403；动态 Base 范围找不到身份映射得到 0 行。要明确是哪一层在拒绝。

撤权练习可以直接移除 LEARN_Reader 的订单权限，再运行 learn_east 订单查询，应返回 403。加回权限则恢复当前 RLS 限定的范围。本实验禁用了结果缓存，方便观察；生产需要明确缓存隔离和撤权时效。

不要把某条 Base `1 = 0` 和普通允许条件放在不同组里，期待“允许条件覆盖拒绝”。它们可能按 AND 组合，结果一直为空。需要明确规则合并语义。

| 现象 | 先查什么 |
|---|---|
| 一开始就没有看板 | 当前账号、LEARN_Reader 数据集权限；不要先怀疑 RLS |
| 加了区域条件仍看到 12 行 | 是否使用普通账号、规则绑定数据集、Regular 角色是否匹配 |
| 总是 0 行 | 是否残留上一课规则、AND/OR 是否正确、Base 豁免是否填反、身份是否有映射 |
| SQL 报错 | Clause 不要写 WHERE；字符串用单引号；字段与 schema 名正确 |
| 华东账号看到了华西普通订单 | 检查两条规则是否被设为同一 Group Key，变成 OR |
| 管理员和普通用户结果不同 | 检查实际登录身份；不要认为管理员结果可代表普通用户 |
| 换标签页仍是同一用户 | 浏览器标签共用 Cookie，使用登出／独立浏览器或命令行会话 |
| 敏感订单不受公共订单 RLS 限制 | 两个是独立数据集，必须分别配置和验证 |
| 程序提示已有课堂配置，拒绝验收 | 这是保护你的练习；用 inspect，不要运行 verify-preparation |

SQL Lab 是另一条执行路径。当前学习用户没有 SQL Lab 权限；不要为了方便临时授予数据库全访问。本项目旧实验已证明：未登记为受限数据集但底层可读的对象，不能假定自动受到另一数据集的行过滤保护。

## 11. 每课记录一张小卡片

可以把下面模板复制到自己的笔记：

```text
今天修改的对象：
修改前的身份与结果：
我填写的权限／Clause：
我预测的新结果：
实际查询得到的名单／数量／金额：
实际 SQL 中增加了什么：
规则由哪个组件执行：
删除／撤回配置后的结果：
仍然不明白的问题：
```

记录中只写课堂合成信息，不复制账号密码。每一步能解释“为什么”后再进入下一课，比一次贴上完整最终策略更有学习价值。

## 12. 备课代码、测试与资料出处

| 文件 | 阅读目的 |
|---|---|
| `integrations/superset/classroom/generate.py` | 数据如何产生；包含中文教学注释和人工标准答案 |
| `integrations/superset/classroom/schema.sql` | 业务表、授权辅助表、递归视图、列出口、只读账号授权 |
| `integrations/superset/classroom/setup.py` | 如何把数据和空权限角色写入真实环境 |
| `integrations/superset/classroom/run.py` | 宿主机准备、只读观察和备课验收入口 |
| `integrations/superset/classroom/test_data.py` | 可重复数据、引用、组织环和金额校验 |
| `integrations/superset/classroom/verify.py` | 真实 REST 和数据库正反例；结束恢复空配置 |

生成器单元测试：

```bash
uv run pytest integrations/superset/classroom/test_data.py -q
```

只有在空课堂准备阶段才执行的集成验收：

```bash
python3 integrations/superset/classroom/run.py verify-preparation
```

它会临时授予课堂权限、创建测试规则并查询，最终恢复空配置。检测到已有学生角色权限或已绑定课堂数据集的 RLS 时会拒绝运行；日常学习只用 `inspect`。

本机备课结果：2 项生成器测试、31 项真实接口和数据库检查通过；另在浏览器实际保存角色权限和一条区域规则，验证 403 → 12 行 → 6 行 → 撤回后 403。测试规则和授权已撤回。详见 [验收记录](../reports/superset-classroom-local.json)。CI 已加入课堂准备和验证步骤，本次新增 CI 步骤尚未在远端执行。

官方依据：

- [Superset 6.1.0 Security](https://superset.apache.org/admin-docs/6.1.0/security/)：角色、数据集访问、Regular/Base、Group Key 和权限边界。
- [Superset 6.1.0 SQL Templating](https://superset.apache.org/admin-docs/6.1.0/configuration/sql-templating/)：当前用户宏与受信任模板编辑。
- 本项目既有 `docs/SUPERSET_OPENFGA_STUDY_GUIDE.md`：概念和选型解释。本文负责带你一步一步填实际配置。

初始全量可见的阶段仅用于本机合成课堂的前后对照。生产系统不能先开放真实数据再慢慢补齐规则，也不能用这套模拟身份替代企业登录。
