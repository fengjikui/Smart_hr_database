# OpenFGA 从零实操：一次只完成一小步

这份手册沿用之前的节奏：**先知道在哪操作，再复制少量内容，最后核对结果。**
不用一次学完。概念不清时停在当前步骤，把报错和步骤号发来即可；不要把密码一起贴出来。

本分支的助手已自动建好独立演示并验证，你的手工进度还没有开始。Superset 学习仍停留在原记录，
不会因这个方案而被重置。想真正重建 OpenFGA，可以使用空的新环境，或先备份后另行讨论重置范围；
本手册没有在现有演示上直接删库的命令。已存在的对象先只读查看，不重复 CREATE/INSERT。

| 想了解什么 | 从哪里读 |
|---|---|
| 模型、数据和 tuple 是什么 | 第 1～3、10～14 步 |
| 数据库如何创建和导入 | 第 4～9 步 |
| OpenFGA 实际如何作判断 | 第 15～19 步 |
| 如何接入原问数 Agent | 第 20～24 步 |
| 调岗、撤权、同步和历史 | 第 25～31 步 |
| 完整验收与代码阅读 | 第 32～35 步 |

详细职责与限制见 [方案设计](OPENFGA_DESIGN.md)，操作反馈记在 [学习记录](OPENFGA_LEARNING_LOG.md)。

## 第 1 步：先区分三个系统

今天会接触：

- PostgreSQL：保存人员事实和发布快照，也执行统计 SQL。
- OpenFGA：回答某个 user 对某个 object 是否拥有某种 relation。
- 原问数 Agent：识别当前账号、理解问题、请求授权、构造并执行查询、组织答案。

**OpenFGA 不保存一份完整人员花名册，也不负责执行 SQL。** 它保存授权模型和关系。
当前方案不需要为每位员工建立 Superset 用户；但仍需要应用账号映射。

## 第 2 步：认识四个词

以“王灏能否查看冯基魁”为例：

| 词 | 例子 | 含义 |
|---|---|---|
| user | user:P0004 | 发起权限判断的人，稳定人员主键 |
| object | person:P0005 | 被查询的员工记录 |
| relation | viewer | 要判断的权限关系 |
| tuple | person:P0005#manager@person:P0004 | 已知的直接关系事实 |

`#`、`@` 是文档里方便阅读的记法。实际 API 用 user/relation/object 三个 JSON 字段。
user 不一定是登录用户名：这里取 person_id，避免工号、姓名变化影响关系标识。

## 第 3 步：认识本次目录和端口

在电脑终端进入仓库：

```bash
cd /Users/fengjikui/Documents/dev-coding/codex_build/Smart_hr_database
```

主要目录 `integrations/openfga`，后端适配在 `backend/hr/openfga_source.py` 和 `openfga_query.py`。
OpenFGA 为 `127.0.0.1:8089`，其 PostgreSQL 为 `127.0.0.1:55433`。
原 Superset 的 8088/55432 保留。

`.local` 放本机密码、发布清单和应用历史，Git 忽略。它不是应该上传的代码目录。

## 第 4 步：生成本机材料

首次安装依赖后执行：

```bash
npm ci
uv sync --frozen
uv run python -m integrations.openfga.run prepare
```

预期提示“本机凭据与模型材料就绪”。这一步只生成文件，没有创建员工或权限关系。

- `.local/lab.env`：给容器读取的连接参数。
- `.local/admin.json`：初始化和同步用的管理连接。
- `.local/runtime.json`：问数后端的只读 PostgreSQL 连接及本地 FGA 密钥。
- `.local/model.json`：官方转换器从 model.fga 生成的 API 模型。

密码随机生成并限制文件权限，重复 prepare 保留现有密码。不要贴出这几个凭据文件。

## 第 5 步：启动引擎

```bash
npm run openfga:up
```

预期 PostgreSQL、OpenFGA 运行，迁移容器正常退出，最后提示 OpenFGA HTTP 已就绪。

```bash
bash integrations/openfga/services.sh status
```

`migrate` 的 `Exited (0)` 是完成表结构升级，不是服务崩溃。
此时 OpenFGA 的内部数据库已准备好，**业务 hr_openfga 数据库尚需下一步创建**。
首次运行下载镜像可能较慢。本机默认复用已存在的 Docker 引擎，不会停止 Superset 容器。
Linux 设置 `HR_DOCKER_HOST=unix:///var/run/docker.sock`，不要照抄 Mac socket。

## 第 6 步：查看创建数据库的代码

打开 `integrations/openfga/run.py`，找到 initialize。第一段连接 `postgres`，检查库是否存在，执行：

```sql
CREATE DATABASE hr_openfga;
```

这里 `postgres` 是管理连接时进入的数据库，`hr_openfga` 是新业务库。
`autocommit=True` 是因为 CREATE DATABASE 不能放在普通事务块中。

准备好后执行：

```bash
npm run openfga:init
```

预期创建成功。若提示“业务结构已存在；未覆盖”，说明助手已经建好，可以继续查看。
这条命令同时执行 schema.sql、创建受控视图并设置本机只读密码。

### 如果希望像上次一样逐条手写建库

可以跳过 `openfga:init` 与第9步 `openfga:seed`，改走这条手工路径。**两种路径选一种，不能对同一个已建库重复执行。** 当前助手已建好的环境只阅读这些材料即可；需要重置时另行确认具体库。

先只生成材料：

```bash
uv run python -m integrations.openfga.run materials
```

材料目录 `integrations/openfga/.local/learning`：

1. `01_database.sql`：一条 CREATE DATABASE。
2. `02_schema.sql`：schema、源表、变更触发器、发布表、只读角色与 RLS。
3. `03_view.sql`：26字段的 CASE 遮蔽视图，和视图所有者/查询授权。
4. `04_reader.sql`：本机只读登录密码；私有文件，禁止分享。
5. `05_seed.sql`：300条人员 INSERT、5条映射和1份策略。

空的新环境里，先按第7步设置当前电脑的 Docker 连接，再在电脑终端按顺序执行：

```bash
docker exec -i hr-openfga-postgres-1 psql -U postgres -d postgres -v ON_ERROR_STOP=1 < integrations/openfga/.local/learning/01_database.sql
docker exec -i hr-openfga-postgres-1 psql -U postgres -d hr_openfga -v ON_ERROR_STOP=1 < integrations/openfga/.local/learning/02_schema.sql
docker exec -i hr-openfga-postgres-1 psql -U postgres -d hr_openfga -v ON_ERROR_STOP=1 < integrations/openfga/.local/learning/03_view.sql
docker exec -i hr-openfga-postgres-1 psql -U postgres -d hr_openfga -v ON_ERROR_STOP=1 < integrations/openfga/.local/learning/04_reader.sql
docker exec -i hr-openfga-postgres-1 psql -U postgres -d hr_openfga -v ON_ERROR_STOP=1 < integrations/openfga/.local/learning/05_seed.sql
```

`< 文件` 是电脑终端把文件内容送给容器内 psql，文件不需要复制进容器。这里没有 `-t`，因为输入来自文件。
ON_ERROR_STOP 遇错停止，BEGIN/COMMIT 把相关步骤组成事务。也可以打开文件逐段复制到 psql 学习，
每次执行后用 `\d`/SELECT 核对。03视图的长段可以按一列一列读：

```sql
CASE WHEN ... ? 'contract'
     THEN record->>'contract_end_date'
END AS contract_end_date
```

`?` 是 JSONB 包含检查；授权字段组里有 contract 才返回值，省略 ELSE 就返回 NULL。
每个字段使用同样模式。实际完整定义复用自动初始化的 `view_statement()`，不维护第二份权限SQL。

## 第 7 步：连接并看 schema

Mac 当前环境电脑终端：

```bash
export DOCKER_HOST=unix:///Users/fengjikui/.colima/hr-superset/docker.sock
docker exec -it hr-openfga-postgres-1 psql -U postgres -d hr_openfga
```

容器内 psql 用本地连接，故没有额外 `-h`。电脑上的客户端连接则用 127.0.0.1:55433。
接下来所有标为 SQL 的块在这个 psql 中执行：

```sql
SELECT current_database(), current_user;
\dn
```

预期当前库 hr_openfga，用户 postgres；四个业务 schema：hr_source、hr_control、hr_data、hr_api。
Schema 通常译为“模式”，这里可理解为数据库内部的命名空间。

## 第 8 步：先看空表结构

```sql
\d hr_source.people
\d hr_source.identities
\d hr_source.policy
```

人员源表只有两个物理列：person_id 主键，record 是 JSONB，里面保存原应用的完整 26 字段。
这便于本次快照发布演示，不是要求生产数据库把宽表也变成 JSON。

identities 是应用身份到人员和角色的映射，没有 Superset ID。
policy 保存五种角色开关，后面同步为 FGA 关系；它仍然是业务规则的输入。

## 第 9 步：导入原来的 300 人

回到另一个电脑终端，执行一次：

```bash
npm run openfga:seed
```

若已导入，会明确拒绝覆盖。不要为消除这个提示随意删除源表。
在 psql 核对：

```sql
SELECT count(*) FROM hr_source.people;
SELECT * FROM hr_source.identities ORDER BY persona;
SELECT jsonb_pretty(config) FROM hr_source.policy;
```

预期 300 人、5 条身份映射、1 份配置，其中 roles 有5种角色。
数据生成函数仍是 `backend/hr/store.py:generate_rows`，随机种子固定，样本可重现。
seed 不调用 store.ensure，不会改动原应用的 SQLite 学习数据。

看熟悉的三个人：

```sql
SELECT person_id,
       record->>'name' AS 姓名,
       record->>'head_person_id' AS 直接主管,
       record->>'dept_hrbp_id' AS HRBP
FROM hr_source.people
WHERE person_id IN ('P0002','P0004','P0005')
ORDER BY person_id;
```

`->>` 从 JSON 取字段并返回文本；`AS` 为结果列取别名；IN 表示属于这个列表。
这还是管理员检查数据，不是最终员工权限查询。

## 第 10 步：读最简单的授权模型

打开 `integrations/openfga/model.fga`，先读：

```text
model
  schema 1.1

type user

type role
  relations
    define member: [user]
```

这不是 SQL，是 OpenFGA DSL（领域专用语言）。schema 1.1 是模型语言版本，与 PostgreSQL schema 无关。
`member: [user]` 表示角色可以直接包含用户。类型定义只说明允许存什么关系，尚未授予任何人权限。

## 第 11 步：看递归汇报线

只看 person 类型中的这三行：

```text
define owner: [user]
define manager: [person]
define supervisors: owner from manager or supervisors from manager
```

以 P0005 为对象：先找到它的 manager=P0004；P0004 的 owner 是 user:P0004，所以王灏是主管。
再沿 P0004 的 manager 往上检查 supervisors，得到更上层的主管。

它表达了递归关系，但**没有让 Python 预先把每位员工的所有上级都写一遍**。
同步仅保存直接主管边。环和不存在的主管在同步前拒绝。

## 第 12 步：为什么是交集

```text
define reports_access: supervisors and reports from company
```

有管理关系还不够，还要求这个用户所在角色具有 company 的 reports 能力。
`and` 是两个条件同时成立；`or` 是满足任一条件。

因此以后撤掉 manager 的 reports 能力，不用修改每个下属的主管关系，就能撤掉管理线查询权限。
这也是“事实关系”与“允许做什么”分开的原因。

## 第 13 步：理解 HRBP 两种来源

```text
define hrbp_access: owner from hrbp_provider and hrbp from company
define inherited_access: supervisors from hrbp_provider and inherit_hrbp from company and reports from company
```

第一行：我是这个员工的 HRBP，并且角色开启 HRBP 能力。
第二行：这个员工的 HRBP 在我的管理线下，并且我有继承 HRBP 和管理线两种能力。
例如王承哲管理姜姜，姜姜服务王灏，所以王承哲可以通过继承 HRBP 服务查看王灏。
这不表示王灏已经变成王承哲的管理下属。

最终：

```text
define viewer: owner or reports_access or hrbp_access or inherited_access
```

一个员工可能同时满足几种来源，结果仍只有一条记录。

## 第 14 步：理解字段组与角色配置

在 psql 中查看主管配置：

```sql
SELECT config->'roles'->'manager' FROM hr_source.policy;
```

`->` 返回 JSON，适合继续访问下一级；`->>` 返回文本。
预期 reports=true、hrbp=false、inherit_hrbp=false，字段组 basic/education/employment，export=false。

同步时产生类似关系：

```json
{"user":"user:P0004","relation":"member","object":"role:manager"}
{"user":"role:manager#member","relation":"reports","object":"company:main"}
{"user":"role:manager#member","relation":"education","object":"company:main"}
```

第二、三条的 user 是“该角色的成员集合”，不是一个人的名字。
这样配置一次角色能力，其成员就随之获得相应能力。

## 第 15 步：第一次同步发布

电脑终端：

```bash
npm run openfga:sync
```

首次预期：发布 300 人、1240 条直接关系；实际 store/model/发布 ID 是本次生成，不照抄文档中的旧 ID。
再次运行且数据未变，预期“无需发布”。

这一步依次：读取源表→校验→转换模型→新建 store→写模型和 tuple→自检→保存业务快照→切换 active。
不同子步骤不能在多个终端乱序执行。具体函数见 run.py:sync。

## 第 16 步：看这次发布的标识

```bash
uv run python -m integrations.openfga.run status
```

输出 id、store_id、model_id、source_revision、current_revision。
最后两个数相等表示源表和发布版本一致。

- store_id：OpenFGA 关系存储空间。
- model_id：不可变模型版本，查询明确指定它。
- id：我们应用的一次发布，绑定人员快照与前两个 ID。

`.local/tuples.json` 可以阅读写入的直接关系；`.local/last-publication.json` 保存发布说明。
这些文件是辅助材料；运行时以 PostgreSQL active 为准。

## 第 17 步：亲自做一次 Check

```bash
uv run python -m integrations.openfga.run check --user user:P0004 --relation viewer --object person:P0005
```

预期 allowed=true。再反过来：

```bash
uv run python -m integrations.openfga.run check --user user:P0005 --relation viewer --object person:P0004
```

预期 false。下属身份不因此拥有向上查看主管的权限。
命令直接请求真实 OpenFGA；不是用 Python 计算后打印一个布尔值。

## 第 18 步：分别核对授权来源

```bash
uv run python -m integrations.openfga.run check --user user:P0002 --relation reports_access --object person:P0004
uv run python -m integrations.openfga.run check --user user:P0002 --relation inherited_access --object person:P0004
uv run python -m integrations.openfga.run check --user user:P0002 --relation viewer --object person:P0004
```

预期依次 false、true、true。这是最适合向主管解释的例子：可见并不等于管理下属。
如果结果不同，先核对源关系和角色开关，不要先改 viewer 的定义让它“能通过”。

## 第 19 步：核对列和操作权限

```bash
uv run python -m integrations.openfga.run check --user user:P0004 --relation contract --object company:main
uv run python -m integrations.openfga.run check --user user:P0002 --relation contract --object company:main
uv run python -m integrations.openfga.run check --user user:P0004 --relation export --object company:main
```

预期 false、true、false。这里只证明权限决策，下一步还要看数据库与 Agent 怎样执行这个决定。

## 第 20 步：看 PostgreSQL 的执行边界

psql 中：

```sql
\d+ hr_data.people
\dp hr_api.people
SELECT schemaname, tablename, policyname, qual
FROM pg_policies
WHERE schemaname='hr_data';
```

RLS 的 USING 条件主要检查：该行属于当前发布 generation，且 person_id 在授权名单内。
视图再按 groups 遮蔽字段。`current_setting` 读取当前数据库连接的配置项。

后端使用 `set_config('hr.allowed_ids', JSON名单, true)`；true 表示只在当前事务中有效。
事务结束便清除，防止连接复用时把上一人的范围带给下一人。

这些配置值由可信后端根据 OpenFGA 结果填写。普通用户不能获得只读账号，也不能执行任意 SQL；
掌握连接密码的人能伪造这些值，所以不能宣称数据库独立验证了 OpenFGA 签名。

## 第 21 步：运行一次完整权限回归

```bash
npm run test:openfga
```

它使用真实 FGA/PG，对五身份名单和20道固定计划与独立 Python 算法对账，并验证越权、历史等。
报告在 `reports/openfga-integration.json`。模型输出用固定替身，不能把这项测试称为真实模型理解测试。

原种子的预期人数：

| 身份 | 可见候选（含离职） | 在职 |
|---|---:|---:|
| 王承哲 | 239 | 226 |
| 姜姜 | 239 | 226 |
| 王灏 | 179 | 169 |
| 冯基魁 | 1 | 1 |
| 集团管理线 | 300 | 284 |

测试会临时创建自己的会话目录，不混入日常历史。

## 第 22 步：启动原问数工作台

先确认 LM Studio 已运行 hr-qwen。电脑终端：

```bash
npm run demo:openfga
```

打开 <http://127.0.0.1:3000/>。这个命令显式设置后端为 openfga，应用状态独立放在 `.local/app`。
因此不需要解除 Superset 的手工学习标记。其他后端的学习保护保持生效。

页面左下角应显示“OpenFGA 权限 · PostgreSQL 查询”。如果显示其他后端，先停下检查，不能用别的
实例结果充当本方案证据。端口已被占用时启动器会拒绝，不会自动杀掉既有进程。

## 第 23 步：先问两道容易核对的问题

切换“部门主管 · 王灏”，问：

> 我的全部授权范围有多少在职员工？

预期169。再问：

> 可信与AI实验室有多少在职员工？

原种子预期57。汇报线跨部门，第二个问题额外限制了部门。
固定计划正确不代表模型必然理解自然语言，出现偏差先看 Plan 的 scope、departments、population。

## 第 24 步：打开独立节点调试

在结果中打开节点调试，沿这条路径看：

问题→当前主体→授权字段和口径检索→模型 Plan→字段/条件校验→FGA重新鉴权→PG SQL→结果→历史。

在“重新鉴权与只读SQL执行”的 source_queries 中找：

- engine=OpenFGA BatchCheck。
- 当前 user、store_id、model_id、publication。
- candidate_count=300、check_count=1209、allowed_count。
- capabilities 中合同与导出等布尔值。

模型不决定 user，也拿不到密钥。页面展示的路径说明来自应用对关系边的解释，不是 FGA 的原生完整证明树。

## 第 25 步：多轮、核验和历史

在上一题后继续问“那直属下属呢”，检查 scope 是否变成 direct。
点击独立核验，对比 SQL 和独立 Python 结果；检查条件含义是否也符合原问题。

切换为员工身份，不能看到主管的旧历史。主管 export=false，在 Agent 导出应拒绝。
这些入口共用授权，不能为了历史、导出或调试绕过当前权限。

## 第 26 步：理解源数据变更信号

先查看当前版本：

```sql
SELECT * FROM hr_control.revision;
```

源 people/identities/policy 的 INSERT、UPDATE、DELETE、TRUNCATE 都会触发版本递增。
其他程序写这些表也会触发，不要求每个程序主动通知 Agent。

这只是本独立演示库的能力。生产如果不允许装触发器，需要 CDC、版本号或轮询适配，不能把当前机制
理解成“无论接哪一个外部数据库都天然立即同步”。

## 第 27 步：撤掉管理线，观察同步前的拒绝

先记录原配置（原种子 reports=true、version=1）：

```sql
SELECT config->'roles'->'manager', config->>'version' FROM hr_source.policy;
```

仅原种子下执行：

```sql
UPDATE hr_source.policy
SET config = jsonb_set(
    jsonb_set(config, '{roles,manager,reports}', 'false'::jsonb),
    '{version}', '2'::jsonb
);
```

内层 jsonb_set 把 reports 改成布尔 false，外层把配置版本改成数字2。`::jsonb` 是类型转换。
这不是字符串 "false"。UPDATE 未带 WHERE 是因为本表 CHECK/主键约束保证至多一行。

psql 默认自动提交。若自己执行过 BEGIN，需 COMMIT，其他连接才能看见。
此时去查询，应提示源数据或身份变化、等待同步，而不是继续返回旧169人。

## 第 28 步：同步后只剩本人，再恢复

电脑终端：

```bash
npm run openfga:sync
```

主管新查询预期1人；旧历史不再可读。person 的主管边未修改，改变的是角色能力。

恢复原种子的配置：

```sql
UPDATE hr_source.policy
SET config = jsonb_set(
    jsonb_set(config, '{roles,manager,reports}', 'true'::jsonb),
    '{version}', '1'::jsonb
);
```

再 sync，预期恢复169人。版本还原仅为恢复固定课堂基线；生产权限版本应按发布协议递增。
如果你此前已经改过原值，请恢复你记录的原值，不照抄1。

## 第 29 步：调岗，观察事实关系变化

先记下 P0005 的原主管，应为P0004：

```sql
SELECT record->>'head_person_id' FROM hr_source.people WHERE person_id='P0005';
UPDATE hr_source.people
SET record=jsonb_set(record, '{head_person_id}', '"P0010"'::jsonb)
WHERE person_id='P0005';
```

这里 JSON 文本要包含双引号，所以写 `'"P0010"'::jsonb`。
同步后，王灏不再看到P0005；P0005作为本人仍能看自己的数据；HRBP可见性依业务关系单独判断。

恢复：

```sql
UPDATE hr_source.people
SET record=jsonb_set(record, '{head_person_id}', '"P0004"'::jsonb)
WHERE person_id='P0005';
```

再 sync。不要只改 OpenFGA 的 tuple 而不改源表，否则下一次同步会按源表覆盖你的临时实验。

## 第 30 步：新入职和停用账号怎么验证

自动实验包含新入职、调岗、撤权、删除账号映射和非法组织环，执行前先停止自己的工作台和 watch：

```bash
uv run python -m integrations.openfga.verify_changes
```

它会保存本机 `change-recovery.json`，在 finally 恢复源表并同步，正常完成后删除恢复文件。
这条命令确实会临时改动 OpenFGA 课堂库，不能跟人工修改同时进行；不会修改 Superset。
报告为 `reports/openfga-changes.json`。

若强制中断留下恢复文件，先检查内容确认它就是本次实验，再恢复：

```bash
uv run python - <<'PY'
import json
from integrations.openfga.run import LOCAL
from integrations.openfga.verify_changes import restore
path = LOCAL / 'change-recovery.json'
restore(json.loads(path.read_text()))
path.unlink()
print('已恢复源表并重新发布')
PY
```

别删除恢复文件来“消除报错”，那会失去要还原的数据。

新员工记录不等于账号已经开通。演示只提供五个固定 persona，新增人员可进入既有主管范围；
若要让新人自己登录，还需账号开通、身份映射和可信认证，不由 FGA 自动生成账号。

## 第 31 步：试用轮询同步

在单独电脑终端运行：

```bash
uv run python -m integrations.openfga.run watch --interval 10
```

它每10秒检查一次，无变化就不发布。按 Ctrl+C 停止。
源数据已经变动、同步尚未完成的窗口内会拒绝查询；这是当前方案选择的可解释行为。
它不是后台常驻生产服务，没有接入公司的 CDC。

不要同时运行 watch 和 verify_changes；课堂恢复事务也属于变更，会被另一个同步器观察到。

## 第 32 步：验证真实模型

确认本机负载合适、LM Studio 可用，串行执行一题：

```bash
HR_QUERY_BACKEND=openfga uv run python scripts/evaluate_model.py --cases HR-01 --output reports/openfga-model.json
```

这次才会调用真实模型。报告记录原始计划、最终计划和计算结果；不能只看到返回成功就认为理解正确。
不要同时开多个模型评测或构建。如果机器热压力升高，先暂停后续任务。

## 第 33 步：跑完整验收

原种子和角色恢复后，逐条执行：

```bash
npm test
npm run docs:check
npm run typecheck
npm run lint
npm run test:openfga
uv run python -m integrations.openfga.verify_changes
uv run python -m integrations.openfga.verify_materials
```

CI 的 OpenFGA 工作流会在干净环境执行初始化、导入、同步、两套真实服务回归。
本机测试报告与远端 CI 状态分开看。不能把助手以前跑过的报告当作你手工配置成功的证据。

## 第 34 步：按这个顺序看代码

1. model.fga：定义什么叫可见。
2. run.py:tuples：一条源数据转为什么关系。
3. run.py:sync：怎样发布一份完整模型/关系/数据。
4. openfga_source.py:snapshot：怎样确定主体、询问权限、核对完整结果。
5. openfga_query.py:execute：授权如何成为 SQL 的执行边界。
6. service.py:run_query/read_run：撤权后为什么旧结果不能继续读。

较长函数先按阶段读，不必逐行死记。要能回答“这一段输入是什么、输出是什么、谁信任它”。

## 第 35 步：用五句话讲给别人

- 人员表保存事实，授权模型定义这些事实什么时候构成查看权限。
- 同步程序把直接关系送进 OpenFGA，框架递归判断直接/间接关系。
- Agent 先认人和问权限，再把授权结果带进受控 PostgreSQL 查询。
- 权限变更要同步，当前方案在待同步期间拒绝旧授权，并使旧历史失效。
- 这是可演示、可验证的实现；生产 SSO、审批、外部库 CDC、海量性能还需要建设。

更完整的职责表、性能和安全限制见 [方案设计](OPENFGA_DESIGN.md)。

## 遇到问题先看这里

| 现象 | 先查什么 |
|---|---|
| 8089 访问失败 | services.sh status/logs；是否刚启动未 ready |
| FGA 返回401/403 | 本地密钥与容器配置是否一致；不要重新生成另一份密码替代 |
| source_revision 不等于 current_revision | 是否源表已更新；运行 sync 并看报错 |
| scope结果是0/缺人 | 是否拿管理员SQL当业务查询；模型、角色能力、身份映射分别查 |
| store/model查不到 | 使用当前 status 的 ID，不复制旧发布文件 |
| seed拒绝覆盖 | 表中已有数据，这是保护；改用查看，不重复导入 |
| 管理关系环/孤儿 | 修复源数据；不要降低校验让部分授权通过 |
| 字段在SQL中为NULL | 该字段组没有授权，视图正在遮蔽 |
| 原表permission denied | 只读业务账号不允许读取原表，符合预期 |
| 旧历史404 | 身份、发布或授权指纹变化；重新查询 |
| 固定计划通过但问答失败 | 检查模型连接、候选Plan和条件绑定，不先修改权限模型 |
| 手册命令与页面状态不同 | 记录步骤、命令和无敏感信息的错误，继续提问 |
