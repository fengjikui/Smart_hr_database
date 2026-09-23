# 从零手工重建：实操路线

需要先理解各步为什么这样配置，可配合阅读 [权限机制讲解](PERMISSIONS_EXPLAINED.md)。该文按对象依赖和实际查询过程组织，本手册按操作顺序组织。

## 从哪里继续

**当前交接点（2026-09-23）：第 28 步三条 RLS 已保存，类型、条件、数据集绑定及空豁免名单均已只读核对；现在开始第 29 步，先创建 `V2_Data_public` 角色。** 后续步骤按学习记录逐项确认，不因手册已写出而视为已完成。

| 想做什么               | 入口                          |
| ---------------------- | ----------------------------- |
| 继续当前操作           | [第 29 步：创建角色](#step-29) |
| 完整数据导入           | [第 22 步](#step-22)           |
| 视图与数据库只读账号   | [第 23 步](#step-23)           |
| Superset 连接和数据集  | [第 26 步](#step-26)           |
| RLS、角色、用户        | [第 28 步](#step-28)           |
| 身份映射与实际查询验证 | [第 31 步](#step-31)           |
| Agent 接入与启动       | [第 36 步](#step-36)           |
| 问数、节点和多轮       | [第 40 步](#step-40)           |
| 撤权和完整验收         | [第 43 步](#step-43)           |

每一节只要求你完成当前小步，不需要一次执行到底。不会操作的地方，带上步骤号和不含密码的报错回来问；[学习记录](LEARNING_LOG.md) 保留此前问答和待研究问题。

## 这次怎么学

一次只做一个小步骤：**操作位置 → 输入内容 → 预期结果 → 你反馈结果 → 再继续**。不会要求你先读懂全部代码，也不把整套初始化脚本当成一次手工练习。

本手册包含完整 45 步操作路线；已做与待做按学习记录区分。问题、回答和错误处理记录在 [学习记录](LEARNING_LOG.md)。[完整实施讲义](SUPERSET_SETUP.md) 是参考答案，不是现在需要一次执行的任务清单。

## 起点和范围

2026-09-20 已备份并清空当前 HR 演示：

- 删除 PostgreSQL `hr_v2`（含全部 schema、表、视图）及两个演示只读连接角色。
- 删除 Superset 中本项目的 2 个连接、5 个数据集、6 个业务/反例账号、8 个角色、3 条 RLS、2 个图表、2 个看板。
- 清空应用会话与历史，移除失效的 Agent 对象 ID 清单与业务账号凭据。
- 保留 Superset 平台、内置角色及技术管理员 `v2_setup_admin`；保留其他课堂的 `hr_lab`、`LEARN_*`、`HR_LAB_*` 配置。因此登录平台后还能看到其他课堂对象，它们不是本次重建内容。
- 保留 `data/people.sqlite` 和本机 `integrations/superset/.local/application/fixtures.json`，作为原有 300 人样本的**导入材料**；它们没有自动导入 PostgreSQL。

技术管理员用于配置，业务用户用于验证权限。不能拿技术管理员能看到的结果证明 RLS 正常。

`hr_v2`、`v2_*` 是现有集成约定的数据库对象名称，这次继续使用以便对上代码；代码目录仍只有一套。

## 路线图（这里只看顺序，不需要现在执行）

| 阶段             | 你亲手做什么                                     | 如何判断学会了                                      | 对照代码                                                                   |
| ---------------- | ------------------------------------------------ | --------------------------------------------------- | -------------------------------------------------------------------------- |
| 1. 建库          | 连接维护数据库，创建`hr_v2`                    | 能说清实例、数据库、schema 的区别                   | `integrations/superset/setup.py:prepare_database`                        |
| 2. 建结构        | 创建 schema 和 26 字段人员表                     | 查询表结构，解释主键与工号                          | `backend/hr/schema.py`、`setup.py`                                     |
| 3. 插数据        | 先插少量人物，再手动导入完整合成样本             | 验证人数、主键、主管关系与数据指纹                  | `backend/hr/store.py:generate_rows`、`integrations/superset/export.py` |
| 4. 理解授权表    | 建策略表、身份映射、快照表；先填少量配置         | 说明登录用户 ID 如何对应`person_id`               | `integrations/superset/schema.sql`                                       |
| 5. 递归汇报线    | 分段执行递归 SQL，再建立授权视图                 | 手工核对本人、直接/间接下属、HRBP；构造环与孤儿反例 | `management_closure`、`graph_health`、`visible_people`               |
| 6. 数据库隔离    | 建受控视图与两个只读数据库账号                   | 普通连接不能读取原始表；基础连接不能读取合同字段    | `setup.py:create_people_views`、`schema.sql`                           |
| 7. Superset 连接 | 手工新增两个连接，登记五个数据集                 | 能预览指定数据集，解释数据库连接与数据集的区别      | `setup.py:prepare_superset`                                              |
| 8. 用户与 RLS    | 分次创建账号、角色、三条 Base RLS，填真实用户 ID | 切换业务账号验证；未映射用户看不到数据              | 同上；完整配置参考实施讲义                                                 |
| 9. 接入 Agent    | 记录新对象 ID、填写本机清单与账号映射            | 业务身份通过 Chart Data API 查询；不借用管理员      | `backend/hr/superset_source.py`、`superset_query.py`                   |
| 10. 走通问数     | 先结构化查询，再自然语言与多轮对话               | 在节点页对应模型输入、计划、权限、执行、结果        | `backend/hr/graph.py`、`service.py`                                    |
| 11. 验收         | 撤权、字段拒绝、越权、20 题和回归                | 不只证明能查，还证明不该查时拒绝                    | `scripts/validate_superset.py`、`validate_revocation.py`               |

后续每一步已补齐可复制命令或页面操作；实际完成后再更新学习记录。未操作的步骤不标记“完成”。

<a id="step-1"></a>

## 第 1 步：亲手创建数据库

**操作位置：电脑的终端，不是 Superset 的 SQL Lab。**

Superset 当前没有这套业务连接；建库属于 PostgreSQL 管理操作。我们使用已运行容器里的 `psql`，无需额外安装数据库客户端。

先用 `docker context ls` 确认目标 Docker 引擎，再执行下面的终端命令。优先沿用已设置的连接地址，否则从当前 context 读取；这里只打开连接，不创建业务数据：

```bash
export HR_DOCKER_HOST="${HR_DOCKER_HOST:-${DOCKER_HOST:-$(docker context inspect --format '{{.Endpoints.docker.Host}}')}}"
export DOCKER_HOST="$HR_DOCKER_HOST"
docker exec -it hr-superset-lab-postgres-1 psql -U postgres -d postgres
```

看到 `postgres=#` 后，输入：

```sql
CREATE DATABASE hr_v2;
```

预期返回：

```text
CREATE DATABASE
```

到这里先停下，把结果发给我。此时你创建了一个数据库，但连接仍然停留在维护数据库 `postgres`；下一步才切换到 `hr_v2`，再创建 schema。数据库默认会自带 `public` schema，这不意味着我们的 HR 表已经建好了。

如果看到 `already exists` 或其他错误，记录完整报错，不要重复删除，也不要自行执行自动初始化。

<a id="step-2"></a>

## 第 2 步：切换并确认连接（已完成）

在 `psql` 中执行：

```sql
\c hr_v2
SELECT current_database(), current_user;
```

你已确认结果为 `hr_v2` 和 `postgres`。

<a id="step-3"></a>

## 第 3 步：创建第一个 schema（已完成）

仍在连接 `hr_v2` 的 `psql` 中执行：

```sql
CREATE SCHEMA v2_data;
```

返回 `CREATE SCHEMA` 后，用下面的 psql 命令检查：

```text
\dn v2_data
```

预期看到 Name 为 `v2_data`，Owner 为 `postgres`。确认结果后再继续。

schema 是数据库内部组织表、视图的命名空间，可以先类比为文件夹。这里的 `v2_data` 用于存放人员原始数据，后面人员表的完整名称是 `v2_data.people`；本步骤还没有建表，也没有完成权限控制。对应结构定义位于 `integrations/superset/schema.sql`，现在只手工执行这一条，不运行整个文件。

<a id="step-4"></a>

## 第 4 步：创建人员表（已完成）

仍在连接 `hr_v2` 的 `psql` 中执行下面一条建表语句。保留现有 26 个字段，避免之后接入程序时缺列；现在不需要记住每个字段。

```sql
CREATE TABLE v2_data.people (
    person_id text PRIMARY KEY,                      -- 人员ID
    employee_no text,                                -- 工号
    name text,                                       -- 姓名
    head_person_id text,                             -- 直接主管ID
    dept_master_id text,                             -- 部门主管ID
    dept_hrbp_id text,                               -- HRBP人员ID
    dept_code text,                                  -- 部门编码
    dept_cn_name text,                               -- 部门
    onboard_date text,                               -- 入职日期
    termin_date text,                                -- 离职日期
    birth_date text,                                 -- 出生日期
    age integer,                                     -- 年龄
    school_name text,                                -- 学校
    first_major text,                                -- 专业
    diploma_code_desc text,                          -- 学历
    degree_code_desc text,                           -- 学位
    full_time_flag text,                             -- 是否全日制
    education_expired_date text,                     -- 毕业时间
    hire_type_code_desc text,                        -- 招聘类型
    labour_type_code_desc text,                      -- 用工类型
    position_code_desc text,                         -- 岗位
    current_employment_start_date text,              -- 当前任职开始日期
    confirmation_date text,                          -- 转正日期
    formalize_flag text,                             -- 是否已转正
    contract_type_code_desc text,                    -- 合同类型
    contract_end_date text                           -- 合同到期日期
);
```

预期返回 `CREATE TABLE`。随后检查结构：

```text
\d v2_data.people
```

预期看到 26 个字段以及 `person_id` 的主键索引。此时只有空表，没有员工数据。反馈结果后再继续。

`v2_data.people` 表示 schema 为 `v2_data`、表名为 `people`。`PRIMARY KEY` 表示人员 ID 唯一且不能空；`text` 为文本，工号前导零得以保留；`integer` 为整数。日期字段暂时沿用当前演示的 `text` 类型，样本格式为 `YYYY-MM-DD`，并非 PostgreSQL `date` 类型。SQL 中的 `--` 是阅读注释，不会自动成为数据库字段说明；持久化字段说明将在后续用 `COMMENT ON COLUMN` 添加。

本语句与 `integrations/superset/setup.py` 的 `prepare_database()` 建表结构一致。工号唯一索引和其他查询索引后续补充，现在先不执行整个初始化脚本。

<a id="step-5"></a>

## 第 5 步：给工号添加唯一索引（已完成）

在当前 `psql` 中执行：

```sql
CREATE UNIQUE INDEX v2_employee_no
ON v2_data.people (employee_no);
```

预期返回 `CREATE INDEX`。再输入 `\d v2_data.people`，在底部 Indexes 中确认出现 `v2_employee_no`，类型为 UNIQUE；原来的人员主键也应保留。

人员 ID 是主键，工号是另一种业务标识。这个索引让数据库拒绝重复的非空工号；它没有将工号改成主键，也没有要求工号必填（当前仍允许 NULL）。对应现有 `setup.py` 的同名唯一索引。

反馈结果后再继续，暂不插入数据。

<a id="step-6"></a>

## 第 6 步：插入第一名员工（已完成）

先插入现有合成样本的顶层人物，只填写六个字段，其他字段暂为空：

```sql
INSERT INTO v2_data.people (
    person_id, employee_no, name,
    dept_code, dept_cn_name, head_person_id
) VALUES (
    'P0001', 'SIM0001', '集团负责人（模拟）',
    'D01', '集团管理层', NULL
);
```

预期返回 `INSERT 0 1`（成功插入一行）。然后查询：

```sql
SELECT person_id, employee_no, name, dept_cn_name, head_person_id
FROM v2_data.people
WHERE person_id = 'P0001';
```

预期返回一行，人物为“集团负责人（模拟）”；主管字段为空，表示此人的 `head_person_id` 为 SQL NULL。NULL 不加引号，不是字符串 `'NULL'`。

这只是学习阶段的部分记录。完整导入时将补齐/更新此行，不能直接重复 INSERT 同一主键。现在不要重复执行插入，也不要启动自动导入。实际结果反馈后再继续。

<a id="step-7"></a>

## 第 7 步：插入直属下属（已完成）

使用现有样本中的王承哲，建立第一条直接汇报关系：

```sql
INSERT INTO v2_data.people (
    person_id, employee_no, name,
    dept_code, dept_cn_name, head_person_id
) VALUES (
    'P0002', '00004915', '王承哲',
    'D02', '装备业务四部人力资源部', 'P0001'
);
```

预期返回 `INSERT 0 1`。再查询两个人的关系：

```sql
SELECT person_id, name, head_person_id
FROM v2_data.people
WHERE person_id IN ('P0001', 'P0002')
ORDER BY person_id;
```

预期两行：P0001 的主管为空；P0002 的主管为 P0001。`head_person_id` 记录主管的人员主键，不是工号。两人的部门不同也不影响这条汇报关系。

这一步只是录入关系，还没有让 Superset 根据关系控制访问。插入语句只执行一次；其他字段后续统一补齐。反馈结果后再继续。

<a id="step-8"></a>

## 第 8 步：显示员工和主管姓名（已完成）

这一步只查询，不插入或修改数据：

```sql
SELECT
    e.name AS 员工姓名,
    m.name AS 直接主管
FROM v2_data.people AS e
LEFT JOIN v2_data.people AS m
    ON e.head_person_id = m.person_id
WHERE e.person_id IN ('P0001', 'P0002')
ORDER BY e.person_id;
```

预期两行：集团负责人（模拟）的直接主管为空；王承哲的直接主管为集团负责人（模拟）。

`e` 代表作为员工读取的人员表，`m` 代表作为主管读取的同一张表，并没有复制或新建表。连接条件用员工的主管 ID 去匹配主管的人员 ID。LEFT JOIN 让没有主管的人员也保留在结果中。这仍然只是直属关系查询，不是递归，也不是权限配置。

反馈结果后再继续。

<a id="step-9"></a>

## 第 9 步：增加第三层人物（已完成）

按原样本插入姜姜，将直接主管设为王承哲 P0002：

```sql
INSERT INTO v2_data.people (
    person_id, employee_no, name,
    dept_code, dept_cn_name, head_person_id
) VALUES (
    'P0003', '00002545', '姜姜',
    'D02', '装备业务四部人力资源部', 'P0002'
);
```

预期返回 `INSERT 0 1`。然后检查：

```sql
SELECT person_id, name, head_person_id
FROM v2_data.people
WHERE person_id IN ('P0001', 'P0002', 'P0003')
ORDER BY person_id;
```

预期三行，主管 ID 依次为 NULL、P0001、P0002。现在有三层汇报链：集团负责人 → 王承哲 → 姜姜（箭头表示主管到下属）。姜姜是王承哲的直属下属，也是集团负责人的间接下属。后续用这组数据观察递归比只查一层多得到谁。

插入只执行一次，反馈结果后再继续。

<a id="step-10"></a>

## 第 10 步：查询直属及间接下属（原理已理解，执行结果待确认）

在当前 psql 执行只读查询：

```sql
WITH RECURSIVE team AS (
    -- 第一步：找到集团负责人的直属下属
    SELECT person_id, name, head_person_id
    FROM v2_data.people
    WHERE head_person_id = 'P0001'

    UNION

    -- 后续：继续找已找到人员的下属
    SELECT p.person_id, p.name, p.head_person_id
    FROM v2_data.people AS p
    JOIN team AS t ON p.head_person_id = t.person_id
)
SELECT person_id, name, head_person_id
FROM team
ORDER BY person_id;
```

预期两行：P0002 王承哲（主管 P0001），P0003 姜姜（主管 P0002）。第一部分先找到王承哲；递归部分从已找到的人继续向下，找到姜姜；再没有新下属时结束。这条语句本例只查下属，不包含集团负责人本人。

`team` 是这条查询内的结果名称，不会新建数据库表。此例 UNION 对完整行去重；它不代表组织数据合法，也不能代替后续正式授权视图中的环/孤儿检查。当前仍未配置 Superset 权限。

反馈结果后再继续。

<a id="step-11"></a>

## 第 11 步：创建授权 schema（已完成）

理解递归之后，开始为正式汇报线视图准备位置。仍在连接 hr_v2 的 psql 中执行：

```sql
CREATE SCHEMA v2_auth;
```

预期返回 CREATE SCHEMA，再检查：

```text
\dn v2_auth
```

预期 Name 为 v2_auth，Owner 为 postgres。v2_data 放人员事实；v2_auth 将放汇报线视图、身份映射和业务授权策略。这个分组本身不会自动实现行权限。

定义对应 integrations/superset/schema.sql。现在只创建这个 schema，下一步再建立正式汇报线视图。

<a id="step-12"></a>

## 第 12 步：建立可复用的汇报线视图（已完成）

schema 在 PostgreSQL 中通常译为“模式”，这里 v2_auth 就是一个模式（用于组织数据库对象的命名空间）。

在当前 psql 执行以下 SQL，与项目 schema.sql 中同名视图保持一致：

```sql
CREATE OR REPLACE VIEW v2_auth.management_closure AS
WITH RECURSIVE chain(root_id,target_id,depth,path,is_cycle) AS (
    SELECT person_id,person_id,0,ARRAY[person_id],false FROM v2_data.people
    UNION ALL
    SELECT c.root_id,p.person_id,c.depth+1,c.path||p.person_id,p.person_id=ANY(c.path)
    FROM chain c JOIN v2_data.people p ON p.head_person_id=c.target_id
    WHERE NOT c.is_cycle
)
SELECT * FROM chain;
```

预期返回 CREATE VIEW。接着查询：

```sql
SELECT target_id, depth
FROM v2_auth.management_closure
WHERE root_id = 'P0001'
ORDER BY depth, target_id;
```

预期三行：P0001 的 depth=0（本人），P0002 的 depth=1（直属下属），P0003 的 depth=2（间接下属）。

普通视图保存查询定义，之后可以通过视图名查询。正式定义对每个人建立一个起点：root_id 为起点人员，target_id 为沿汇报线找到的人，depth 为层级，path 为经过的人员 ID 数组，is_cycle 标记是否在路径中重复遇到某个人。成环行保留但不再向下扩展；后续 graph_health 用它拒绝异常关系授权，现在还没有完成权限控制。

ARRAY[person_id] 建立初始路径；path || person_id 将新人员加入路径；person_id = ANY(path) 检查是否已在路径中。这里使用 UNION ALL，并明确检查路径中的环，而不是依赖整行去重。

先确认建视图和三行结果，再继续下一小步。

### 第 12 步补充检查：观察完整路径（已完成）

创建视图成功后执行：

```sql
SELECT target_id, depth, path, is_cycle
FROM v2_auth.management_closure
WHERE root_id = 'P0001'
ORDER BY depth, target_id;
```

预期结果：

| target_id | depth | path                | is_cycle |
| --------- | ----: | ------------------- | -------- |
| P0001     |     0 | {P0001}             | f        |
| P0002     |     1 | {P0001,P0002}       | f        |
| P0003     |     2 | {P0001,P0002,P0003} | f        |

path 是从起点到目标经过的人员 ID 数组，psql 用花括号显示；f 是 false，表示这条路径没有重复经过某个人。此次核对仍是查询，不修改表或权限；收到实际输出后才标记完成。如果之前还未执行 CREATE VIEW，先完成本节建视图语句。

<a id="step-13"></a>

## 第 13 步：建立组织关系检查视图（已完成）

2026-09-21：你已确认汇报路径、层级和循环标记完全符合预期。接下来把三种异常汇总成一个检查结果，逻辑与 `integrations/superset/schema.sql` 中的 graph_health 一致：

```sql
CREATE OR REPLACE VIEW v2_auth.graph_health AS
SELECT NOT (
    -- 检查循环汇报
    EXISTS (
        SELECT 1 FROM v2_auth.management_closure
        WHERE is_cycle
    )
    -- 检查主管 ID 是否指向不存在的人
    OR EXISTS (
        SELECT 1 FROM v2_data.people AS p
        LEFT JOIN v2_data.people AS m ON m.person_id = p.head_person_id
        WHERE p.head_person_id IS NOT NULL AND m.person_id IS NULL
    )
    -- 检查 HRBP ID 是否指向不存在的人
    OR EXISTS (
        SELECT 1 FROM v2_data.people AS p
        LEFT JOIN v2_data.people AS h ON h.person_id = p.dept_hrbp_id
        WHERE p.dept_hrbp_id IS NOT NULL AND h.person_id IS NULL
    )
) AS graph_valid;
```

创建返回 `CREATE VIEW` 后执行：

```sql
SELECT * FROM v2_auth.graph_health;
```

预期一行，`graph_valid` 为 `t`（true）。EXISTS 表示是否存在满足条件的记录；三个异常条件用 OR 连接，任一命中即为异常，最外面的 NOT 把“存在异常”转换成“关系有效”。

没有填写主管或 HRBP（NULL）本身不算此处的孤儿引用；填写了 ID 却找不到对应人员才算。目前三人的 HRBP 都未填写，尚未验证实际 HRBP 服务范围。这也不检查教育、日期等业务字段是否完整。

本视图仅报告关系是否有效，并不自动阻止查询或写入。后续将该结果接入授权逻辑，使异常组织关系拒绝授权。先反馈当前查询结果，下一步再通过可回滚的小实验观察异常时的结果。

<a id="step-14"></a>

## 第 14 步：验证循环检测，再回滚（已完成）

已确认正常关系的 graph_valid=t。现在做一个完整的小实验，暂时让顶层负责人汇报给姜姜，形成循环，再撤销修改。请在同一个 psql 会话中将整段执行到最后再反馈，不要执行 COMMIT：

```sql
BEGIN;

-- 临时让集团负责人向姜姜汇报，形成循环
UPDATE v2_data.people
SET head_person_id = 'P0003'
WHERE person_id = 'P0001';

-- 预期为 f：检测到异常
SELECT * FROM v2_auth.graph_health;

-- 撤销刚才的修改
ROLLBACK;

-- 预期恢复为 t
SELECT * FROM v2_auth.graph_health;
```

预期 UPDATE 1，两次查询分别为 f、t。BEGIN 开启事务，ROLLBACK 撤销本事务修改；后一次 t 是恢复验证，不要省略。途中若报错，也先执行 ROLLBACK，再记录错误。

本步骤验证的是递归和关系检查对循环的识别能力；尚未证明 Superset 已经拒绝越权查询，用户/RLS 配置还未开始。实际结果反馈后再继续。

<a id="step-15"></a>

## 第 15 步：创建角色策略表（已完成）

关系检查验证完毕，现在创建保存业务角色配置的表，与 schema.sql 保持一致：

```sql
CREATE TABLE v2_auth.role_policy (
    role_key text PRIMARY KEY,      -- 角色标识
    reports boolean NOT NULL,      -- 是否可看管理线下属
    hrbp boolean NOT NULL,         -- 是否可看本人 HRBP 服务人员
    inherit_hrbp boolean NOT NULL, -- 是否继承下属 HRBP 的服务范围
    field_groups jsonb NOT NULL,   -- 允许的字段组
    details boolean NOT NULL,      -- 是否允许明细
    export boolean NOT NULL,       -- 是否允许导出
    version integer NOT NULL       -- 策略版本
);
```

预期 CREATE TABLE。检查结构：

```text
\d v2_auth.role_policy
```

预期八列，role_key 为主键。每行将描述一种业务角色的规则；boolean 为布尔值，jsonb 为 JSON 数据类型。本步先建空表，后续再填写。

这张表由我们编写的授权逻辑读取，并非 Superset 自带的角色表。创建它不会自动限制查询。inherit_hrbp 的正式生效还要求 reports 开启，表示继承管理线下属的 HRBP 服务范围，不是将 HRBP 服务关系当管理线递归。

反馈结果后再继续。

<a id="step-16"></a>

## 第 16 步：填写部门主管策略（已完成）

前提：已完成第 15 步 role_policy 建表；如果尚未执行，先完成该步骤。用户目前尚未单独反馈建表结果，不能把概念讨论记成操作成功。

先只添加一个角色，与本机原合成快照中的 manager 策略一致：

```sql
INSERT INTO v2_auth.role_policy (
    role_key, reports, hrbp, inherit_hrbp,
    field_groups, details, export, version
) VALUES (
    'manager', true, false, false,
    '["basic", "education", "employment"]'::jsonb,
    true, false, 1
);
```

预期 INSERT 0 1，再查询：

```sql
SELECT * FROM v2_auth.role_policy
WHERE role_key = 'manager';
```

预期一行：reports=t，hrbp=f，inherit_hrbp=f，字段组为 basic/education/employment，details=t，export=f，version=1。JSONB 显示时可能调整空格格式。

这表示允许使用管理线下属范围，不启用两种 HRBP 范围；允许基础、教育和任职字段组，以及查看明细，禁止应用导出。不包含 contract 合同字段组。`::jsonb` 将字符串解释成 JSONB；version 记录策略版本，但数字本身不自动执行撤权或刷新。

此时只是保存 manager 角色的业务配置，尚未分配给具体用户，也没有创建 Superset 角色/RLS。后续要把账号、人员与角色对应起来，再将策略接入受控查询路径。只插入一次，结果反馈后再继续。

<a id="step-17"></a>

## 第 17 步：创建身份映射表（已确认表存在）

先建立映射表结构，与 schema.sql 一致：

```sql
CREATE TABLE v2_auth.identity_map (
    superset_user_id integer PRIMARY KEY, -- Superset 用户 ID
    username text UNIQUE NOT NULL,       -- Superset 登录名
    persona_id text UNIQUE NOT NULL,     -- Agent 演示身份标识
    person_id text NOT NULL,             -- 对应员工的人员 ID
    role_key text NOT NULL               -- 对应业务策略的角色标识
);
```

返回 CREATE TABLE 后检查：

```text
\d v2_auth.identity_map
```

预期五列。superset_user_id 是 Superset 用户编号；person_id 是人员表里的人员主键；role_key 对应 role_policy 的配置，比如 manager。persona_id 是应用演示身份标识。它们属于不同系统中的标识，不能混用。

现在只建空表。创建 Superset 用户后才能填写真实用户 ID，不能猜 ID 或复用重置前的映射。当前代码通过关联查询匹配 person_id、role_key，表中没有为这两列声明外键；后续配套验证也必须检查映射是否正确。本次表结构面向演示身份，不是任意多角色模型。

反馈建表结果后再继续。

<a id="step-18"></a>

## 第 18 步：创建数据快照说明表（已确认表存在）

已只读确认 identity_map 表存在，snapshot 表尚不存在。现在只建结构：

```sql
CREATE TABLE v2_auth.snapshot (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    as_of text NOT NULL,                -- 数据截止日期
    data_fingerprint text NOT NULL,     -- 数据内容指纹
    data_version text NOT NULL,         -- 数据版本
    field_definitions jsonb NOT NULL    -- 字段定义
);
```

预期返回 CREATE TABLE，随后检查：

```text
\d v2_auth.snapshot
```

预期五列。此表保存数据的截止日期、内容指纹、版本和字段定义，不保存另一份人员数据，也不是历史任职表。

singleton 只能为 true（CHECK）且不能重复（PRIMARY KEY），因此表最多一行；不保证一定存在一行。先理解成“整份当前数据共用的一份说明”。后续完整导入时计算真实指纹并填写字段目录，不要临时编造指纹。as_of 当前设计仍为 ISO 日期文本，与已有代码保持一致。

本步对应 integrations/superset/schema.sql 同名表。反馈建表结果后继续。

<a id="step-19"></a>

## 第 19 步：创建受控查询出口 schema（已只读确认存在）

已只读确认 snapshot 表存在，v2_api schema 尚不存在。在当前 psql 执行：

```sql
CREATE SCHEMA v2_api;
```

预期 CREATE SCHEMA，再检查：

```text
\dn v2_api
```

预期名称 v2_api、Owner 为 postgres。三个 schema 的分工：v2_data 保存人员事实，v2_auth 保存授权辅助数据和关系视图，v2_api 保存供 Superset 查询的数据出口视图。这里 api 只是名字，不是在创建 HTTP 接口。

后续通过受控视图和数据库 GRANT 授予只读账号访问出口，避免直接开放原始人员表。本步仅创建命名空间，尚未建立隔离或授权。

反馈结果后继续。

<a id="step-20"></a>

## 第 20 步：创建可见人员视图（已完成，用户确认）

已只读确认 v2_api 存在、identity_map 为 0 行、visible_people 尚不存在。现在把前面准备的映射、策略、关系合并为授权人员集合。只执行本节这一段，不运行整个 schema.sql：

```sql
CREATE OR REPLACE VIEW v2_auth.visible_people AS
WITH origins AS (
    SELECT i.superset_user_id,i.person_id AS target_id,'self'::text AS kind,
           ARRAY[i.person_id] AS path,'本人'::text AS reason,0 AS priority
    FROM v2_auth.identity_map i
    JOIN v2_data.people p ON p.person_id=i.person_id
    JOIN v2_auth.role_policy r USING(role_key)
    UNION ALL
    SELECT i.superset_user_id,c.target_id,'reports',c.path,'管理线下属',1
    FROM v2_auth.identity_map i JOIN v2_auth.role_policy r USING(role_key)
    JOIN v2_auth.management_closure c ON c.root_id=i.person_id
    WHERE r.reports AND c.depth>0 AND NOT c.is_cycle
    UNION ALL
    SELECT i.superset_user_id,p.person_id,'hrbp',ARRAY[i.person_id,p.person_id],'本人 HRBP 服务',2
    FROM v2_auth.identity_map i JOIN v2_auth.role_policy r USING(role_key)
    JOIN v2_data.people p ON p.dept_hrbp_id=i.person_id
    WHERE r.hrbp
    UNION ALL
    SELECT i.superset_user_id,p.person_id,'inherited_hrbp',c.path||p.person_id,'继承下属 HRBP 服务',3
    FROM v2_auth.identity_map i JOIN v2_auth.role_policy r USING(role_key)
    JOIN v2_auth.management_closure c ON c.root_id=i.person_id
    JOIN v2_data.people p ON p.dept_hrbp_id=c.target_id
    WHERE r.reports AND r.inherit_hrbp AND c.depth>0 AND NOT c.is_cycle
), merged AS (
    SELECT superset_user_id,target_id,
           bool_or(kind='reports') AS reports,
           bool_or(kind='hrbp') AS hrbp,
           bool_or(kind='inherited_hrbp') AS inherited,
           jsonb_agg(jsonb_build_object('kind',kind,'path',path,'text',reason) ORDER BY priority)::text AS origins
    FROM origins GROUP BY superset_user_id,target_id
)
SELECT m.*, c.depth
FROM merged m JOIN v2_auth.identity_map i USING(superset_user_id)
LEFT JOIN v2_auth.management_closure c ON c.root_id=i.person_id AND c.target_id=m.target_id AND NOT c.is_cycle
CROSS JOIN v2_auth.graph_health h
WHERE h.graph_valid;
```

预期 CREATE VIEW。然后执行：

```sql
SELECT count(*) FROM v2_auth.visible_people;
```

当前预期为 0：identity_map 还没有绑定业务账号，所以没有可计算的账号授权范围。这不是“员工表没人”，也还不是 Superset RLS 验证。

本节代码与 integrations/superset/schema.sql 的同名定义一致。先理解整体分工，细节可逐段问：

| 部分                | 用途                                                   |
| ------------------- | ------------------------------------------------------ |
| self                | 有效映射和角色对应的本人                               |
| reports             | reports 开启时，加入管理线下属                         |
| hrbp                | hrbp 开启时，加入本人 HRBP 服务人员                    |
| inherited_hrbp      | reports 和 inherit_hrbp 开启时，继承下属 HRBP 服务人员 |
| merged              | 按账号与人员合并重复结果，保留权限来源                 |
| WHERE h.graph_valid | 组织关系检查失败时，不输出授权人员                     |

此视图会计算所有已映射账号的范围，不会自行选择当前登录者。后续 v2_api 出口及 Superset 的 RLS 才把请求限制到当前账号；不能把它当作已完成的权限系统。后续 Agent 还会检查 graph_valid，将异常报告为错误，不能把关系异常伪装成公司人数为零。

先执行并反馈结果，不要为看见非零结果而编造账号 ID。

<a id="step-21"></a>

## 第 21 步：创建账号上下文视图（当前步骤）

已确认 visible_people 创建成功，当前未映射账号时计数为 0。接下来把身份、策略、快照和关系检查组合为 Agent 所需的上下文，与 schema.sql 保持一致：

```sql
CREATE OR REPLACE VIEW v2_api.context WITH(security_barrier=true) AS
SELECT i.superset_user_id,i.persona_id,i.person_id,i.role_key,r.version AS policy_version,
       (to_jsonb(r)-'role_key'-'version')::text AS rules_json,
       s.as_of,s.data_fingerprint,h.graph_valid
FROM v2_auth.identity_map i JOIN v2_auth.role_policy r USING(role_key)
JOIN v2_data.people p ON p.person_id=i.person_id
CROSS JOIN v2_auth.snapshot s CROSS JOIN v2_auth.graph_health h;
```

预期返回 CREATE VIEW，再检查：

```sql
SELECT count(*) FROM v2_api.context;
```

当前预期 0，因为身份映射与快照说明尚未填入。这里的 CROSS JOIN snapshot 需要快照说明存在才能产生上下文；后续会补齐数据。

视图输出账号/员工/角色、策略版本、策略 JSON、数据截止日期、数据指纹及 graph_valid。to_jsonb(r) 把策略行转成 JSON；减去 role_key 和 version 后，将其他配置转为文本 rules_json。graph_valid 在这里作为输出列保留，不用 WHERE 过滤，因此配置齐全后，Agent 可以读到 false 并明确报告组织关系异常。

security_barrier=true 是安全屏障视图选项，约束某些外层条件下推的优化行为；它不自动选择当前账号，也不替代 RLS。后续需要在 Superset 为该数据集设置 superset_user_id = {{ current_user_id() }} 的过滤，并配置只读账号访问权限。

本步只创建视图，尚不开放数据集。反馈结果后继续。

## 后半程导航：按顺序做，一次只完成一小步

你已确认到第 20 步。第 21 步的 `context` 建视图语句已经给出，但尚未收到完成反馈。**离开前不用赶进度，回来从第 21 步检查开始。**后面这些步骤是完整操作指引，不表示已经替你执行。

| 小节                         | 学完能解释什么                                      |
| ---------------------------- | --------------------------------------------------- |
| 22～25：完整数据和数据库出口 | 数据如何导入，视图与只读账号各控制什么              |
| 26～31：Superset 配置        | 连接、数据集、角色、RLS、用户、身份映射各在哪里生效 |
| 32～35：亲眼验证权限         | 不同账号能看到什么，不能看到什么                    |
| 36～38：Agent 绑定与预检     | 实际用户/数据集 ID 如何接回代码，何时可以启动       |
| 39～43：问数、历史与撤权     | 问题怎样成为结果，权限变化时旧结果如何处理          |
| 44～45：验收与讲解           | 如何有证据地说明系统能力和边界                      |

本机仍保留手工学习标记。不要为了省事执行 `superset:setup`，否则就失去了亲手配置每个环节的过程。已有 `SUPERSET_SETUP.md` 描述完整自动化实现；本手册是实际操作顺序。

### 先准备终端（只需本次终端设置一次）

下面的 shell 命令在**电脑终端**执行，不是在 `hr_v2=#` 后输入。若仍停在 psql，先输入 `\q` 退出。SQL 则在 psql 执行；页面步骤在 Superset 中执行。

在终端打开项目根目录（包含 `package.json` 的目录），后续文件路径均相对于该目录。先用 `docker context ls` 确认目标引擎，再设置：

```bash
export HR_DOCKER_HOST="${HR_DOCKER_HOST:-${DOCKER_HOST:-$(docker context inspect --format '{{.Endpoints.docker.Host}}')}}"
export DOCKER_HOST="$HR_DOCKER_HOST"
```

`export` 让本终端后续 Docker 命令沿用同一引擎地址；换了终端需重新设置。`HR_DOCKER_HOST` 供项目脚本读取，`DOCKER_HOST` 供手工 Docker 命令读取，两者应指向同一引擎。容器名按实际部署调整。

以后需要回到 SQL 时执行：

```bash
docker exec -it hr-superset-lab-postgres-1 psql -U postgres -d hr_v2
```

<a id="step-22"></a>

## 第 22 步：从三条练习记录换成完整 300 人样本

**目标：**保留已学的结构，用完整样本继续配置。手抄 300 行没有学习价值，因此工具只生成供你审阅的 SQL，你亲手执行。

### 22.1 生成材料，不写数据库

电脑终端执行：

```bash
uv run python integrations/superset/learning.py prepare
```

它读取保留的 `fixtures.json`，验证指纹，生成本机文件：

| 文件（均在`integrations/superset/.local/application/` 下） | 用途                                             |
| ------------------------------------------------------------ | ------------------------------------------------ |
| `learning/22_import.sql`                                   | 完整人员、五种角色策略、快照说明、字段注释和索引 |
| `learning/23_views.sql`                                    | 两个人员出口与两个事件出口视图                   |
| `learning/24_access.sql`                                   | 两个 PostgreSQL 只读账号及权限，包含本机密码     |
| `credentials.json`                                         | 手工创建 Superset 用户时使用的登录密码           |
| `database-credentials.json`                                | 配置数据库连接时使用的数据库密码                 |

这些文件全部在 Git 忽略目录，SQL 为 0600，目录为 0700。不要把内容提交、发到聊天或截图展示密码。此命令不会创建 Superset 用户，不执行 SQL，不取消学习标记。

如果提示缺少 `fixtures.json`，先停止检查文件位置。正常本机已保留它；只有确实缺失时才使用 `uv run python integrations/superset/run.py export` 从现有离线样本导出，再重新生成材料。

### 22.2 阅读导入 SQL 的开头和末尾

在编辑器打开 `22_import.sql`。你只需理解这些骨架（以下仅为示意，不要执行；实际执行完整的 22_import.sql）：

```sql
BEGIN;
DELETE FROM v2_data.people;
-- INSERT ... VALUES (...)：这里实际含完整 300 人
DELETE FROM v2_auth.role_policy;
-- 写入五种角色策略和一条 snapshot
-- 添加字段注释、查询索引并检查关系合法性
COMMIT;
```

这次是**整份替换**，会覆盖前面三条不完整教学记录和手填的 manager 策略。它不动身份映射、Superset 用户或 RLS。BEGIN/COMMIT 保证一整批成功才提交；关系检查失败时，本次导入不应保留半份结果。

样本是原系统的合成数据，person_id 和工号不重新编号。日期为 `2026-09-11`，因此“今年”“上季度”以后都相对这个快照日解释。

### 22.3 手工执行材料

先做一份当前三人练习库的本机备份：

```bash
mkdir -p data/backups
chmod 700 data/backups
(umask 077; docker exec hr-superset-lab-postgres-1 pg_dump -U postgres -Fc hr_v2 > "data/backups/before-full-import-$(date +%Y%m%d-%H%M%S).dump")
```

把 SQL 复制到容器并执行：

```bash
docker cp integrations/superset/.local/application/learning/22_import.sql hr-superset-lab-postgres-1:/tmp/hr-22-import.sql
docker exec hr-superset-lab-postgres-1 psql -U postgres -d hr_v2 -v ON_ERROR_STOP=1 -f /tmp/hr-22-import.sql
```

`-f` 表示从文件执行；`ON_ERROR_STOP=1` 遇错停止。此命令使用独立连接，异常退出时未提交事务回滚。若你是在交互 psql 中用 `\i` 执行并报错，先 `ROLLBACK;`。

检查（psql）：

```sql
SELECT count(*) FROM v2_data.people;
SELECT role_key, reports, hrbp, inherit_hrbp, field_groups
FROM v2_auth.role_policy ORDER BY role_key;
SELECT as_of, data_version FROM v2_auth.snapshot;
SELECT * FROM v2_auth.graph_health;
```

预期：300 人、5 种角色、快照日 `2026-09-11`、`graph_valid=t`。工号仍为文本：

```sql
SELECT person_id, employee_no, name
FROM v2_data.people WHERE person_id = 'P0005';
```

应看到冯基魁的工号 `00031266`。完整样本的管理线比三人例子长；不要把前面“只含三个人”时的递归行数继续当作完整样本答案。

**代码对应：**`learning.py:import_sql` 生成可审阅材料；原自动过程对应 `setup.py:prepare_database`，完整事实来源仍是 `store.py` 和 `export.py`。

<a id="step-23"></a>

## 第 23 步：创建人员和事件查询出口

电脑终端执行：

```bash
docker cp integrations/superset/.local/application/learning/23_views.sql hr-superset-lab-postgres-1:/tmp/hr-23-views.sql
docker exec hr-superset-lab-postgres-1 psql -U postgres -d hr_v2 -v ON_ERROR_STOP=1 -f /tmp/hr-23-views.sql
```

生成器直接复用 `setup.py:create_people_views()` 的 SQL；不是另外手写一套与程序不同的视图。它把原函数的 execute 替换成“收集 SQL”，生成时没有执行建视图。

检查（psql）：

```text
\dv v2_api.*
\d v2_api.people_public
\d v2_api.people_contract
```

应有五个视图：context、people_public、people_contract、events_public、events_contract。context 是第 21 步已经创建的，当前文件新增其余四个。

### 较长 SQL 怎样读：先看人员出口

打开 `23_views.sql`，以 people_public 为例，按以下顺序找：

1. `FROM v2_data.people p JOIN v2_auth.visible_people g`：将“账号能看谁”与“这个人的业务字段”结合。
2. `g.superset_user_id AS _viewer_id`：在输出行标上这行属于哪个查看账号。
3. `p.person_id, p.employee_no, ...`：公共出口只选择 24 个业务字段，没有合同两列。
4. `CASE WHEN ... END AS relation`：把来源转成“本人、直属下属、间接下属、HRBP服务人员”的展示分类；多来源详细依据仍保存在 `_origins`。
5. `substring(...,1,7)`：从 ISO 日期文本得到 `2026-09` 这样的月份，供统计分组。

合同出口多选两列，还检查：

```sql
r.field_groups ? 'contract'
```

这里 `?` 是 PostgreSQL JSONB 运算符，在当前 JSON 数组中检查是否含有字符串 `contract`。它不是 Python 问号或占位符。

**重要：**同一员工可能对应多个 `_viewer_id`，所以这里还不是当前登录人的最终结果，不能直接 count 全视图当公司人数。后面 RLS 才会限制查看账号。

### 再看事件出口

事件视图用 UNION ALL 合并两类记录：

- 入职记录：`event_day=onboard_date`，`is_hire=1`，`is_exit=0`。
- 离职记录：`event_day=termin_date`，`is_hire=0`，`is_exit=1`。

这使一个日期范围内的入职和离职能一起分组统计。一个离职员工可能贡献两条事件，因此“事件行数”不是“员工人数”；统计入职可以 SUM(is_hire)，人员数量要按 person_id 去重。

现在没有账号映射，视图为空仍属预期。此时可以先检查列：

```sql
SELECT column_name
FROM information_schema.columns
WHERE table_schema='v2_api' AND table_name='people_public'
  AND column_name IN ('contract_type_code_desc','contract_end_date');
```

公共出口应返回 0 行；把表名换为 people_contract 应返回两行。

<a id="step-24"></a>

## 第 24 步：创建数据库只读账号并授予出口访问权

这一步配置的是 **PostgreSQL 账号**，不是 Superset 登录账号。打开私有的 `24_access.sql` 阅读，密码不要分享。

关键指令的作用：

| SQL                                             | 含义                                                          |
| ----------------------------------------------- | ------------------------------------------------------------- |
| CREATE ROLE ... LOGIN PASSWORD ...              | 创建能连接数据库的账号                                        |
| REVOKE ALL ON DATABASE hr_v2 FROM PUBLIC        | 撤回默认所有角色组在该库的权限；PUBLIC 不是我们 public 字段组 |
| GRANT CONNECT ON DATABASE ...                   | 允许连接这一个数据库                                          |
| GRANT USAGE ON SCHEMA v2_api ...                | 允许使用这个命名空间，仍需对象权限                            |
| GRANT SELECT ON 指定视图 ...                    | 允许读取明确列出的出口                                        |
| ALTER ROLE ... default_transaction_read_only=on | 默认事务只读；不是代替 GRANT 的安全边界                       |
| statement_timeout='10s'                         | 限制该账号的查询时长                                          |

电脑终端执行一次：

```bash
docker cp integrations/superset/.local/application/learning/24_access.sql hr-superset-lab-postgres-1:/tmp/hr-24-access.sql
docker exec hr-superset-lab-postgres-1 psql -U postgres -d hr_v2 -v ON_ERROR_STOP=1 -f /tmp/hr-24-access.sql
docker exec hr-superset-lab-postgres-1 rm -f /tmp/hr-24-access.sql
```

若提示角色已存在，不要盲目删角色；核对是否已经执行过。此文件用于首次手工创建，不是任意环境的重置程序。

检查（管理员 psql）：

```text
\du v2_*
\dp v2_api.*
```

预期两个 PostgreSQL 账号：v2_public_reader、v2_contract_reader。前者可查 public 人员/事件和 context，后者可查 contract 人员/事件。两者都没有原始表与授权配置表的 SELECT 权限。

<a id="step-25"></a>

## 第 25 步：亲自验证数据库边界

先退出管理员 psql：`\q`。在电脑终端启动公共只读账号会话：

```bash
docker exec -it hr-superset-lab-postgres-1 psql -h 127.0.0.1 -U v2_public_reader -d hr_v2 -W
```

提示输入密码时，使用私有 database-credentials.json 的 public 密码。这里 `127.0.0.1` 是**容器内** PostgreSQL，不是 Superset 连接表单中的宿主机地址。

先执行成功例子：

```sql
SELECT current_user;
SELECT person_id FROM v2_api.people_public LIMIT 1;
```

前者应为 v2_public_reader；后者当前 0 行，但不报权限错误。再分别执行三个失败例子：

```sql
SELECT * FROM v2_data.people LIMIT 1;
SELECT * FROM v2_auth.identity_map LIMIT 1;
SELECT * FROM v2_api.people_contract LIMIT 1;
```

预期 permission denied，可能针对 schema 或 view。不能把“表不存在”“密码错误”算作权限验证通过。这些语句逐条执行，保持自动提交，不包 BEGIN。

结束 `\q`。之后回管理员连接继续配置。**共享读账号本身不区分员工，只限制可访问对象；不要把其密码交给普通业务用户。**

<a id="step-26"></a>

## 第 26 步：在 Superset 添加两个数据库连接

**操作位置：Superset 浏览器，技术管理员 v2_setup_admin。**本机密码在 credentials.json。原课堂的 LEARN/HR Lab 对象仍在，别编辑它们。

进入 Settings → Database Connections → + Database，选择 PostgreSQL。创建下面两条：

| 表单项        | 第一条               | 第二条                 |
| ------------- | -------------------- | ---------------------- |
| Display name  | V2_public            | V2_contract            |
| Host          | postgres             | postgres               |
| Port          | 5432                 | 5432                   |
| Database name | hr_v2                | hr_v2                  |
| Username      | v2_public_reader     | v2_contract_reader     |
| Password      | 本机 public 连接密码 | 本机 contract 连接密码 |

因为连接由 Superset 容器发起，所以 Host 是同一 Compose 网络的服务名 postgres。不能填它自己的 127.0.0.1，也不使用电脑对外映射的 55432。

测试连接、保存。若界面使用 SQLAlchemy URI，格式为 `postgresql+psycopg2://用户名:密码@postgres:5432/hr_v2`；不要把真实连接串贴进公共文档。生成的十六进制密码无需特殊 URL 转义。

在连接向导最后一步或编辑连接的 Advanced 页面中核对（当前使用 Superset 6.1.0）：

- **SQL Lab**：取消勾选 `Expose database in SQL Lab`。关闭后，`Allow CREATE TABLE AS`（CTAS）、`Allow CREATE VIEW AS`（CVAS）、`Allow DDL and DML` 会被隐藏；不必为了寻找它们而开启 SQL Lab。
- 隐藏不等于清空原有设置。如果修改的是以前开启过这些功能的连接，还需核对保存配置中的 `allow_ctas`、`allow_cvas`、`allow_dml` 均为 `false`。本次新建公共连接已只读核对这三项为 `false`。
- **Performance**：展开此栏目，确认 `Asynchronous query execution` 未勾选；它不在 SQL Lab 栏目内。
- 点击向导底部 **Finish**（编辑页为保存按钮），才能保存最后修改的开关。表单已取消勾选不代表后台配置已经更新。

界面显示条件可对照 [Superset 6.1.0 官方 ExtraOptions 源码](https://github.com/apache/superset/blob/6.1.0/superset-frontend/src/features/databases/DatabaseModal/ExtraOptions.tsx)。两个连接都完成后，列表应出现两条连接；分步学习时先完成公共连接，再配置合同连接。

这一步只告诉 Superset“如何连接”，尚未向业务用户开放任何数据。

<a id="step-27"></a>

## 第 27 步：登记五个物理数据集

进入 Data → Datasets → + Dataset。每次选择已有连接、Schema `v2_api`、Table，再添加一个：

| 数据集/视图名   | 连接        |
| --------------- | ----------- |
| people_public   | V2_public   |
| events_public   | V2_public   |
| context         | V2_public   |
| people_contract | V2_contract |
| events_contract | V2_contract |

选择的是数据库已有视图，**不要改成自定义 SQL 的虚拟数据集**。保留原字段名和视图名，Agent 按这些名字识别出口。

添加后检查 columns：公共人员没有合同两列；合同人员有。人员、事件数据集有 `_viewer_id`，context 有 `superset_user_id`。它们是稍后 RLS 的过滤列，不能删掉。

电脑终端只读盘点：

```bash
uv run python integrations/superset/learning.py inventory
```

输出本次实际数据集 ID、列和 permission 名，并保存到 `.local/application/learning/inventory.json`。现在业务账号可能还没有，users 里只有技术管理员也正常。**不要照抄旧文档中的数字 ID。**

<a id="step-28"></a>

## 第 28 步：先配置三条 RLS

进入 Settings → Row Level Security，或 [http://127.0.0.1:8088/rowlevelsecurity/list/](http://127.0.0.1:8088/rowlevelsecurity/list/)，点新增。逐条创建：

| Name              | Datasets                         | Clause                                         |
| ----------------- | -------------------------------- | ---------------------------------------------- |
| V2_scope_public   | people_public、events_public     | `_viewer_id = {{ current_user_id() }}`       |
| V2_scope_contract | people_contract、events_contract | `_viewer_id = {{ current_user_id() }}`       |
| V2_context_scope  | context                          | `superset_user_id = {{ current_user_id() }}` |

三条的其他设置完全相同：**Filter Type=Base；Roles 留空；Group Key 留空**。保存后逐条打开复核数据集绑定，避免同名视图绑定到错误连接。

### 这句 Clause 怎样理解

以 `_viewer_id = {{ current_user_id() }}` 为例：

1. `_viewer_id` 是人员出口每行携带的“归属查看账号”。
2. 双花括号属于 Jinja 模板；Superset 从可信登录上下文取得当前用户内部 ID。
3. 假设登录账号 ID 为 42，最终条件就是 `_viewer_id = 42`。
4. Superset 把条件加到实际查询中，所以同一数据集在不同用户下返回不同范围。

不要填写 WHERE，也不要给模板加字符串引号，更不能让模型或浏览器自报这个 ID。

**Base 的 Roles 是豁免角色列表，不是需要限制的角色列表。**这里留空，避免给业务角色开豁免。Group Key 留空；本次不练习多规则 OR 组合。当前用户模板依赖配置中已启用的 ENABLE_TEMPLATE_PROCESSING，不需要你重新运行初始化。

目前只是保存了规则。真正是否执行，要在后面的普通业务账号查询中验证；管理员看到什么不能作为业务边界证据。

<a id="step-29"></a>

## 第 29 步：创建八个 Superset 自定义角色

打开 [http://127.0.0.1:8088/roles/list/](http://127.0.0.1:8088/roles/list/)（经典角色页）。每次 + 新建，填写名称、选择 Permissions、保存。

| 角色名           | 需要添加的权限                                        |
| ---------------- | ----------------------------------------------------- |
| V2_Data_public   | people_public、events_public 的 datasource_access     |
| V2_Data_contract | people_contract、events_contract 的 datasource_access |
| V2_Context       | context 的 datasource_access                          |
| V2_Role_hr_lead  | 不添加权限，仅业务标签                                |
| V2_Role_hrbp     | 同上                                                  |
| V2_Role_manager  | 同上                                                  |
| V2_Role_employee | 同上                                                  |
| V2_Role_admin    | 同上                                                  |

Permissions 搜索表名，选 `datasource access on ...`（后台名 datasource_access）；若出现多个同名结果，按第 27 步 inventory.json 中 permission 的完整名称核对连接和 ID。不要选择 database_access、all_datasource_access、all_database_access 或 SQL Lab 权限。

不要编辑内置 Gamma、Admin、Alpha。Gamma 提供基本界面能力，自定义数据角色提供具体数据集访问权，两者组合使用。最后五个标签角色不会自动改写 role_policy；策略由 identity_map.role_key 关联。

确认列表中恰好有这八个 V2_ 角色，再继续。

<a id="step-30"></a>

## 第 30 步：手工创建六个业务/反例账号

进入 Settings → Security → List Users（经典入口通常为 [http://127.0.0.1:8088/users/list/](http://127.0.0.1:8088/users/list/)），新增用户。技术管理员 v2_setup_admin 已保留，不再新建。

每个账号填写 Username、First name、Last name、Email、Active、Roles、Password、Confirm password。姓名可填表内显示名，Email 用 `用户名@example.invalid`，Active 勾选。Password 使用 prepare 生成的 credentials.json 中对应账号的值，Confirm password 填相同值。它是由本机随机种子稳定派生的专用密码，**不是统一共享密码**。

| Username    | 显示身份   | Roles                                                                |
| ----------- | ---------- | -------------------------------------------------------------------- |
| v2_hr_lead  | 王承哲     | Gamma、V2_Data_public、V2_Context、V2_Role_hr_lead、V2_Data_contract |
| v2_hrbp     | 姜姜       | Gamma、V2_Data_public、V2_Context、V2_Role_hrbp、V2_Data_contract    |
| v2_manager  | 王灏       | Gamma、V2_Data_public、V2_Context、V2_Role_manager                   |
| v2_employee | 冯基魁     | Gamma、V2_Data_public、V2_Context、V2_Role_employee                  |
| v2_admin    | 集团管理线 | Gamma、V2_Data_public、V2_Context、V2_Role_admin、V2_Data_contract   |
| v2_unmapped | 未映射反例 | Gamma、V2_Data_public、V2_Context                                    |

特别检查 v2_admin **没有** Superset Admin；它只是业务身份。业务用户也不能带 Alpha 或 sql_lab。

Superset 在保存用户时分配内部 ID。管理员填写的是用户名，不是内部 ID。再次运行只读 inventory，应该看到七个 v2_ 账号，包含保留的技术管理员。

如果你自行换了业务账号密码，须同时更新本机 credentials.json；初始化脚本不会猜到你在 UI 改了什么。本教程建议先使用准备好的密码，避免把认证失败误认为 RLS 错误。

<a id="step-31"></a>

## 第 31 步：把真实账号 ID 写入身份映射

电脑终端执行：

```bash
uv run python integrations/superset/learning.py mapping
```

它只读 Superset 的用户 ID，生成 `.local/application/learning/31_identity.sql`，**不会执行 INSERT**。打开文件，逐行核对：

| username    | persona_id | person_id | role_key |
| ----------- | ---------- | --------- | -------- |
| v2_hr_lead  | hr_lead    | P0002     | hr_lead  |
| v2_hrbp     | hrbp       | P0003     | hrbp     |
| v2_manager  | manager    | P0004     | manager  |
| v2_employee | employee   | P0005     | employee |
| v2_admin    | admin      | P0001     | admin    |

每行最前面的数字是本次新建 Superset 用户的真实 ID。不要给 v2_unmapped 或 v2_setup_admin 插入映射。未映射反例就是为了证明“有数据集访问权但没有业务映射”仍看不到人。

确认后亲手执行：

```bash
docker cp integrations/superset/.local/application/learning/31_identity.sql hr-superset-lab-postgres-1:/tmp/hr-31-identity.sql
docker exec hr-superset-lab-postgres-1 psql -U postgres -d hr_v2 -v ON_ERROR_STOP=1 -f /tmp/hr-31-identity.sql
```

此文件故意不静默覆盖旧映射，重复执行会报唯一键冲突；若已成功过，只查询，不重复 INSERT。

检查（psql）：

```sql
SELECT superset_user_id, username, person_id, role_key
FROM v2_auth.identity_map ORDER BY username;
SELECT count(*) FROM v2_api.context;
```

预期五条映射，context 五行。到这里，原先空的出口视图开始有候选数据；Superset RLS 会为每次业务请求选择其中属于当前账号的部分。

<a id="step-32"></a>

## 第 32 步：在数据库中核对授权人数

先使用管理员 psql 检查各账号的候选范围（**含离职**）：

```sql
SELECT i.username, count(v.target_id) AS visible_count
FROM v2_auth.identity_map i
LEFT JOIN v2_auth.visible_people v USING(superset_user_id)
GROUP BY i.username
ORDER BY i.username;
```

| username    | 预期候选人数 |
| ----------- | -----------: |
| v2_admin    |          300 |
| v2_employee |            1 |
| v2_hr_lead  |          239 |
| v2_hrbp     |          239 |
| v2_manager  |          179 |

这只是核对业务关系计算，还没证明 Superset 选对当前身份。所有数字都基于原固定样本；如果你改过人员或策略，先恢复再按这些数验收。

再核对在职口径：

```sql
SELECT i.username, count(*) AS active_count
FROM v2_api.people_public p
JOIN v2_auth.identity_map i ON i.superset_user_id=p._viewer_id
WHERE p.onboard_date <= '2026-09-11'
  AND (p.termin_date IS NULL OR p.termin_date > '2026-09-11')
GROUP BY i.username ORDER BY i.username;
```

预期 admin=284、employee=1、hr_lead=226、hrbp=226、manager=169。离职当天已不在职，所以条件是 `>`，不是 `>=`。ISO 格式文本日期在这份固定有效样本中按字典序比较；生产日期建模另行讨论。

<a id="step-33"></a>

## 第 33 步：手工建立两个表格图表和看板

以技术管理员在 Charts → + Chart 选择 people_public，图表类型 Table，Create。查询模式选 Raw records/原始记录，不做分组聚合。

Columns 选择：employee_no、name、dept_cn_name、diploma_code_desc、school_name、relation。Row limit 设 1000，Page length 20，Time range 选 No filter，移除额外筛选。运行并保存图表“当前 · 人员与汇报范围”，保存到同名新看板。进入看板点发布（Published），确保普通用户能访问。

管理员没有业务映射时，这个表格预览 0 行正常；不要为让管理员看到数据而删除 RLS。后面用业务账号验证。

用 people_contract 同样建立“当前 · 合同字段权限”，在上述列后再加 contract_type_code_desc、contract_end_date。发布到同名看板。

若看板 Properties 可设置 URL/Slug，分别填 v2-people-public、v2-people-contract，便于与旧书签一致；不支持设置也没关系，记录本次实际看板 URL，Agent 不依赖看板 slug。

<a id="step-34"></a>

## 第 34 步：切换普通账号，验证行权限

建议管理员保留一个浏览器窗口，业务账号使用另一个无痕窗口；换账号前明确退出，避免把管理员会话当作业务会话。

登录 v2_employee，打开公共人员看板：预期只有冯基魁一人。不要增加姓名/部门过滤来“做出一人效果”，必须由 RLS 自动限制。

登录 v2_manager：公共人员看板无在职过滤时预期 179 名候选人员。尝试在图表允许的界面增加/清除普通业务筛选，清除后也不应超出 179；业务筛选只能进一步缩小范围。

登录 v2_hr_lead、v2_hrbp：各 239；登录 v2_admin：300。登录 v2_unmapped：能访问公共数据集，但结果应为 0，因为它没有身份映射。

如果任何业务账号看到所有账号范围混在一起或同一工号重复多次，先停止，核对 RLS 数据集绑定、Base 类型、豁免角色和 `_viewer_id` 条件，不通过增加前端过滤掩盖。

<a id="step-35"></a>

## 第 35 步：验证合同列权限

以 v2_employee 或 v2_manager 登录，尝试访问合同图表（可用管理员记录的直达 URL）。预期拒绝访问/没有权限；看不到菜单只是辅助现象，直接 URL 也应被检查。

以 v2_hr_lead 登录合同看板，应能查询其授权范围的合同列。两项必须同时具备：

- Superset 角色授予合同数据集访问权。
- 业务策略 field_groups 包含 contract，合同视图才产生该账号的候选行。

公共人员视图本身没有合同列。只在前端隐藏列不构成安全措施。当前数据库实现的是“基础/合同两档”物理列隔离；更细的字段组由 Agent 校验，不能宣称 Superset 已为每个字段独立配置了列权限。

<a id="step-36"></a>

## 第 36 步：把实际配置绑定回 Agent

电脑终端执行：

```bash
uv run python integrations/superset/learning.py bind
```

它只读平台与数据库，检查五个数据集、五条身份映射、人员数量、快照元数据和关系有效性，再把本次真实 ID 写入私有 `manifest.json`。它不创建数据集、不加角色、不改 RLS，也不解除学习标记。

打开 manifest.json，先只看两个部分：

- `principals.manager`：把应用的 manager 身份对应到 v2_manager、实际用户 ID、P0004 和 manager 策略。
- `datasets.people_public`：记录本次数据集 ID、数据库连接 ID 与列。

打开 `backend/hr/superset_source.py`：`identity()` 使用 principals，`session()` 读取本机凭据获得业务账号 token，`_chart()` 使用 datasets 中的 ID。模型和浏览器不会自己选择数据库账号。

缺用户、错 person_id 或数据集绑定错误时，bind 会停止。按错误回到对应步骤修正；不要为了通过而随意复制旧 manifest。

<a id="step-37"></a>

## 第 37 步：验证存储和平台配置

学习标记仍保留，此时可以执行只读存储验证：

```bash
uv run python integrations/superset/run.py verify-storage
```

它会真实读取全量人员并重新计算指纹，使用两个数据库只读账号验证拒绝案例，再检查七账号、八角色、五数据集、三条 RLS。最后报告 `passed=true`，具体检查数量以当前程序为准。

这个命令不调用模型，不重建、不重置权限。报告保存在 `.local/application/storage-verification.json`。它与 bind 的区别是：bind 负责连接映射，verify-storage 检查数据和权限结构；仍要做下一步真实业务 API 测试。

如果 PostgreSQL 账号密码验证失败，核对手工创建时是否使用了 generated database-credentials.json。现有验证脚本按实验种子派生密码，不支持你随意更换读账号密码后仍不更新脚本配置。

<a id="step-38"></a>

## 第 38 步：通过检查后解除学习标记，并做真实 API 回归

只有第 34～37 步符合预期，才在电脑终端执行以下操作。保留标记文件备份，便于失败时恢复：

```bash
cp integrations/superset/.local/application/manual-learning.json integrations/superset/.local/application/learning/manual-learning.saved.json
rm integrations/superset/.local/application/manual-learning.json
npm run test:superset
```

此回归不要求启动 3000/8000，也不调用模型：它在临时应用状态目录中运行测试客户端，通过真实 Superset/PostgreSQL 验证身份隔离、查询及固定题目的计划。原报告中的数量不是你这次的完成证据，必须看新报告 `reports/superset-integration.json`。

失败时先恢复标记，按报错检查：

```bash
cp integrations/superset/.local/application/learning/manual-learning.saved.json integrations/superset/.local/application/manual-learning.json
```

修复后重新执行第 36、37 步，再移除标记重新验证。不要运行 setup 去覆盖手工配置。通过后才启动问数工作台。

<a id="step-39"></a>

## 第 39 步：启动 Agent，并确认真实后端

启动前确认本机负载和热状态正常；本教程不需要批量模型推理。LM Studio 使用已部署模型，兼容接口 `http://127.0.0.1:1234/v1`，模型标识 hr-qwen。

电脑终端执行：

```bash
npm run demo
```

保持终端运行，打开 [http://127.0.0.1:3000/](http://127.0.0.1:3000/)。端口已被占用时先确认是谁在用，不重复启动。不要切换 demo:offline 来掩盖 Superset 错误。

检查页面左下角“权限与模型状态”：应表明 Superset 权限、PostgreSQL 查询；选择业务身份后有对应的在职可见人数。此身份选择器只用于演示，不是生产 SSO。

<a id="step-40"></a>

## 第 40 步：先用一个简单问题走完整链路

在工作台选“部门主管 · 王灏”，提问：

> 我的全部授权范围有多少在职员工？

原样本预期 169。接着问：

> 可信与AI实验室有多少在职员工？

预期 57。第一题是全部授权范围，第二题还加了部门筛选；汇报线可以跨部门，这两个数不同是正常的。

如果模型生成澄清或错误条件，不要先归因于 RLS。打开节点调试，看 Plan 是否表达了你的问题；固定计划回归已通过但自然语言不对时，定位检索、模型或条件校验部分。

<a id="step-41"></a>

## 第 41 步：沿节点调试看清“问题到答案”

打开本次结果的节点调试入口（独立 `/debug?run=...` 页面）。一次只看一行：

| 节点/代码                    | 你需要看到的证据                                             |
| ---------------------------- | ------------------------------------------------------------ |
| routes.py / 应用会话         | 本轮 persona 是 manager，不是由问题文本指定                  |
| graph.authorize              | 当前身份、权限指纹，以及是否继承本人有效历史                 |
| graph.discover / registry.py | 允许字段和指标目录、部门候选、披露的定义                     |
| 模型生成计划                 | 原始模型输入、候选 JSON Plan，不是任意 SQL                   |
| 明确条件绑定（如出现）       | 程序是否修正了原始模型条件；不能把修正结果宣称为模型原生全对 |
| 结构、口径与字段权限校验     | 字段、范围、日期、问题条件是否通过                           |
| 重新鉴权与只读 SQL 执行      | 真实 SQL、结果、执行后端；应出现当前用户 RLS                 |
| 结果组织                     | 数字来自实际结果单元格，再按确定性模板组织说明               |
| service.save_run             | 当前用户和权限/数据指纹绑定的历史与 trace                    |

可以把整条流程读成：**问题→授权目录→模型 Plan→程序校验→Chart Data 请求→Superset 注入 RLS→PostgreSQL 查询→结果说明与历史。**

在真实 SQL 里找 `_viewer_id`，其值应是本次 v2_manager 的实际用户 ID；部门条件和在职日期条件是业务筛选，与该身份条件共同生效。不要照抄示例数字 ID。

注意：后台为了授权目录和独立核验还会请求受限快照，所以 trace 中可能有多条 source_queries。它们都走业务账号；最终统计仍由受 RLS 限制的 SQL 执行，不是先拿全公司数据再在 Python 过滤。

<a id="step-42"></a>

## 第 42 步：验证多轮、历史与自助核验

保持 manager 身份，完成第一题后追问：

> 那直属下属有多少人？

检查新 Plan 的 scope 是否为 direct，其他未修改口径是否继承。在历史里打开第一题继续追问，确认 previous_id 指向你选中的那次成功查询。

切换 employee 身份，历史列表应只属于 employee，不能看到 manager 的对话。回到 manager，执行“独立对账/核验”：它比较真实 SQL 结果与独立 Python 计算，结果应一致。

核验通过证明计算一致性，不自动证明模型理解了所有语言条件。仍要读结果上方的人群、部门、日期和口径。比如“硕士”与“硕士及以上”、“学历”与“学位”不同。

导出也使用当前身份重新校验。manager 的 export=false，应在应用中被禁用或拒绝；这不等于 Superset 原生图表下载菜单也被这一开关自动禁用。

<a id="step-43"></a>

## 第 43 步：亲手改一次策略，验证撤权和恢复

先保存一条 manager 的成功查询历史，并记住它的结果。管理员 psql 查询原值：

```sql
SELECT role_key,reports,version FROM v2_auth.role_policy WHERE role_key='manager';
```

原快照应 reports=t、version=1。执行并提交（不包未提交的 BEGIN，因为浏览器是另一个连接）：

```sql
UPDATE v2_auth.role_policy
SET reports=false, version=version+1
WHERE role_key='manager';
```

在浏览器 manager 身份重新询问全部授权范围在职人数，预期从 169 收缩到 1（本人）。旧历史/旧节点结果应失效，不能用旧缓存继续看被撤掉的范围。

试验后**恢复刚才记下的原值**。若原值确实为 t/1：

```sql
UPDATE v2_auth.role_policy SET reports=true, version=1 WHERE role_key='manager';
```

再问一次应恢复 169。这里恢复版本是为了还原固定课堂基线；生产权限版本一般单调递增，不能把本例当作生产版本策略。

第二个小实验在 Superset：记录 v2_manager 的角色列表，移除 V2_Data_public，保存。Agent 新请求应被拒绝，即使其数据库 reports 仍为 true；然后加回原角色，确认恢复。**一次只改一个因素，每次都恢复。**

也可用自动撤权回归：先停止自己的工作台（运行终端 Ctrl+C），保持 Superset/PostgreSQL 运行，串行执行 `npm run test:revocation`。脚本在 finally 中恢复；若被强制中断，恢复信息在 `.local/application/probe-recovery.json`，先检查恢复状态，不继续演示。

<a id="step-44"></a>

## 第 44 步：分层验收，记录实际结果

按顺序运行，避免并发修改权限或同时占用模型：

```bash
npm test
npm run docs:check
uv run python integrations/superset/run.py verify-storage
npm run test:superset
npm run test:revocation
npm run test:model -- --cases HR-01
```

最后一条只做一个真实模型案例，LM Studio 须正常运行；前面固定计划测试不消耗模型推理。根据本机负载逐条运行，不同时开多个推理或构建。

记录：运行日期、当前 Git 提交、通过/失败、报告路径、失败原因。UI 再检查身份切换、表格筛选、历史和节点调试。新报告以 reports 目录为准，不复用别人演示的截图作证据。

验收不能混成一句“都通过”：分别写清数据库权限、Superset 行过滤、Agent 计划权限、计算正确性、模型理解、多轮和历史失效。真实生产 SSO、动态同步和大规模性能尚未实现，不在本轮通过范围内。

<a id="step-45"></a>

## 第 45 步：用自己的话串起整个系统

现在尝试回答五个问题，答不清就回到对应步骤：

1. 为什么知道“王灏是谁”还不够，还需要 Superset 用户 ID 和身份映射？
2. reports 开关在哪里变成筛选条件？为什么只添加一个 V2_Role_manager 标签不够？
3. 哪个地方计算可见人员，哪个地方把请求限定为当前登录者？
4. 为什么共享数据库账号不能交给普通用户，即使它只读？
5. 为什么查询结果正确，还要分别验证模型理解、权限拒绝和旧历史失效？

最后用这个表做讲解提纲：

| 责任                        | 实际位置                                         |
| --------------------------- | ------------------------------------------------ |
| 业务事实及关系              | PostgreSQL people                                |
| 可配置的业务开关            | role_policy；角色绑定在 identity_map             |
| 递归和 HRBP 授权计算        | management_closure、visible_people 等 SQL 视图   |
| 当前用户行隔离              | Superset 数据集 Base RLS                         |
| 基础/合同列与数据库对象边界 | 不同出口视图、只读账号 GRANT、数据集角色         |
| 问题理解与口径              | LangGraph、字段指标目录、结构化 Plan 校验        |
| 结果与审计                  | SQL 真实结果、自然语言模板、本人历史和节点 trace |

生产动态数据、账号生命周期、OpenFGA 替代哪些部分，继续保留在学习记录 Q1～Q3。完成本轮后再讨论，会有具体对象和证据作为基础。

## 常见卡点：先定位，不用自动初始化“修好”

| 现象                              | 先检查                                                          |
| --------------------------------- | --------------------------------------------------------------- |
| psql 提示 relation does not exist | SELECT current_database()，检查 schema/视图名及是否执行前置步骤 |
| INSERT 主键/唯一键冲突            | 是否重复执行；先查询已有记录，不随意删用户或猜 ID               |
| 连接 postgres 失败                | Superset 容器用 postgres:5432，电脑客户端用 127.0.0.1:55432     |
| 设置了 schema USAGE 仍不能查询    | 还需具体视图的 SELECT 权限                                      |
| context 为 0 行                   | identity_map 是否匹配人员与策略，snapshot 是否恰好一行          |
| 所有人看到相同数据或重复人员      | RLS 是否选对数据集、Base 是否存在豁免、是否管理员会话           |
| HR 看不到合同字段                 | 数据集角色与策略 contract 两边都查；公共出口本来无合同列        |
| Agent 提示仍在手工重建            | 是否完成核验后才移除了正确目录的 manual-learning.json           |
| Agent 登录失败                    | credentials.json 与 UI 手填密码是否一致，账号是否 Active        |
| 业务策略变了但 Superset 标签没变  | 二者不是同一配置来源，标签不会自动同步业务策略                  |
| 数据库查询正常但问数失败          | 看模型连接、Plan 与条件校验；不要用管理员查询替代用户执行       |
| 子查询/SQL Lab 报拒绝             | 本方案不向业务用户开放自由 SQL，不通过放大权限解决              |

## 辅助工具说明与验证范围

`learning.py` 只生成本机材料/清单；`learning_inspect.py` 在已有容器内提取 SQL 和读取 ID，未调用 setup，不修改平台角色或数据库。生成视图直接复用现有函数，避免另造一套 SQL。bind 只核对映射和快照元数据，完整数据指纹、RLS 和权限结构仍以 verify-storage 与真实回归为准。

脚本源码带中文注释，可从 `learning.py:prepare`→`import_sql`→`mapping_sql`→`learning_inspect.py:binding` 阅读。它们是课堂辅助，不是生产账号开通或持续同步系统。

官方资料用于查概念，操作以本项目版本和实际页面为准：

- PostgreSQL 普通视图：[CREATE VIEW](https://www.postgresql.org/docs/17/sql-createview.html)。
- 递归、工作表和循环：[WITH Queries](https://www.postgresql.org/docs/17/queries-with.html)。
- JSONB 运算符：[JSON Functions and Operators](https://www.postgresql.org/docs/17/functions-json.html)。
- Superset 6.1.0 的角色与访问控制：[Security](https://superset.apache.org/admin-docs/6.1.0/security/)。
- 当前用户模板：[SQL Templating](https://superset.apache.org/admin-docs/6.1.0/configuration/sql-templating/)。

## 学习期间的启动约束

本机标记文件 `integrations/superset/.local/application/manual-learning.json` 表示正在手工学习。现在工作台已停止，Superset 仍可从 [http://127.0.0.1:8088/](http://127.0.0.1:8088/) 登录。

- `npm run superset:up`、`npm run superset:setup`、`sync-data` 和容器自动初始化会被阻止，避免一键补回所有对象。
- `npm run demo` / `demo:production` / `demo:offline` 也暂时阻止启动，避免拿离线数据或旧界面误认为重建已经成功。
- 如果只是重启了电脑，需要恢复**已有**平台容器，可执行 `bash integrations/superset/services.sh resume`。它只启动 PostgreSQL、Superset，不执行导入；它不能代替首次安装。
- 学到 Agent 接入时，再核对新用户 ID、数据集 ID、业务凭据、授权和快照，完成后移除标记。**现在不要删除标记，也不要复制备份中的旧 manifest 来猜 ID。**

## 权限和问数的主线

现有实现不是“全部规则都由 Superset 自动理解”。人员和汇报关系在 PostgreSQL，递归和可见人员集合在我们写的 SQL 视图里；Superset 管理用户、角色、数据集访问，并把 `current_user_id()` 对应的 RLS 条件加到受控数据集查询中。列隔离还依赖不同视图和数据库只读账号。

Agent 使用应用会话确定业务身份，读取授权上下文和字段目录，让模型产生结构化 `Plan`；程序校验计划后构造 Chart Data API 请求，Superset 执行受控查询。最后用真实结果生成说明、保存历史与节点记录。模型没有数据库管理密码，也不直接任意执行 SQL。完整过程将在第 9、10 阶段逐项观察。

## 备份与重置入口（现在不用执行）

本次完整备份位于本机 `data/backups/manual-learning-20260920-204631/`，Git 忽略且目录为私有权限。

包含 `hr_v2.dump`、`superset_meta.dump`、PostgreSQL 角色、平台密钥配置、本机应用映射/凭据、人员样本与会话 SQLite，以及 SHA-256 校验清单。数据库归档已通过 `pg_restore --list` 检查，SQLite 已通过完整性检查；尚未做异地完整恢复演练。

重置实现见 `integrations/superset/reset_learning.py`：先备份、核查，再在事务内删除白名单平台对象，最后删除业务库和只读账号。它是这次准备工作使用的工具，**不需要在每一课开始时重跑**。平台元数据库备份包含其他课堂配置，不应直接覆盖恢复；需要回退时先讨论恢复范围。
