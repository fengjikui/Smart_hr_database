# 从零手工重建：实操路线

## 这次怎么学

一次只做一个小步骤：**操作位置 → 输入内容 → 预期结果 → 你反馈结果 → 再继续**。不会要求你先读懂全部代码，也不把整套初始化脚本当成一次手工练习。

本手册按实际进度补充。问题、回答和错误处理记录在 [学习记录](LEARNING_LOG.md)。[完整实施讲义](SUPERSET_SETUP.md) 是参考答案，不是现在需要一次执行的任务清单。

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

| 阶段 | 你亲手做什么 | 如何判断学会了 | 对照代码 |
|---|---|---|---|
| 1. 建库 | 连接维护数据库，创建 `hr_v2` | 能说清实例、数据库、schema 的区别 | `integrations/superset/setup.py:prepare_database` |
| 2. 建结构 | 创建 schema 和 26 字段人员表 | 查询表结构，解释主键与工号 | `backend/hr/schema.py`、`setup.py` |
| 3. 插数据 | 先插少量人物，再手动导入完整合成样本 | 验证人数、主键、主管关系与数据指纹 | `backend/hr/store.py:generate_rows`、`integrations/superset/export.py` |
| 4. 理解授权表 | 建策略表、身份映射、快照表；先填少量配置 | 说明登录用户 ID 如何对应 `person_id` | `integrations/superset/schema.sql` |
| 5. 递归汇报线 | 分段执行递归 SQL，再建立授权视图 | 手工核对本人、直接/间接下属、HRBP；构造环与孤儿反例 | `management_closure`、`graph_health`、`visible_people` |
| 6. 数据库隔离 | 建受控视图与两个只读数据库账号 | 普通连接不能读取原始表；基础连接不能读取合同字段 | `setup.py:create_people_views`、`schema.sql` |
| 7. Superset 连接 | 手工新增两个连接，登记五个数据集 | 能预览指定数据集，解释数据库连接与数据集的区别 | `setup.py:prepare_superset` |
| 8. 用户与 RLS | 分次创建账号、角色、三条 Base RLS，填真实用户 ID | 切换业务账号验证；未映射用户看不到数据 | 同上；完整配置参考实施讲义 |
| 9. 接入 Agent | 记录新对象 ID、填写本机清单与账号映射 | 业务身份通过 Chart Data API 查询；不借用管理员 | `backend/hr/superset_source.py`、`superset_query.py` |
| 10. 走通问数 | 先结构化查询，再自然语言与多轮对话 | 在节点页对应模型输入、计划、权限、执行、结果 | `backend/hr/graph.py`、`service.py` |
| 11. 验收 | 撤权、字段拒绝、越权、20 题和回归 | 不只证明能查，还证明不该查时拒绝 | `scripts/validate_superset.py`、`validate_revocation.py` |

每一阶段会补充可复制的命令和页面操作，并在你实际完成后记录结果。现在还没有为后续阶段标记“完成”。

## 第 1 步：亲手创建数据库

**操作位置：电脑的终端，不是 Superset 的 SQL Lab。**

Superset 当前没有这套业务连接；建库属于 PostgreSQL 管理操作。我们使用已运行容器里的 `psql`，无需额外安装数据库客户端。

先执行下面这条终端命令。它只打开连接，不创建业务数据：

```bash
DOCKER_HOST=unix://$HOME/.colima/hr-superset/docker.sock docker exec -it hr-superset-lab-postgres-1 psql -U postgres -d postgres
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

## 学习期间的启动约束

本机标记文件 `integrations/superset/.local/application/manual-learning.json` 表示正在手工学习。现在工作台已停止，Superset 仍可从 <http://127.0.0.1:8088/> 登录。

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
