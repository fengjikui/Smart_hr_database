# 测试、验证与交付

测试只针对当前应用，不运行已退役的工作台或独立实验。所有报告由当前运行生成在 `reports/`，目录被 Git 忽略；CI 上传执行报告。

## 1. 日常回归

```bash
uv run ruff check backend tests scripts integrations/superset
npm test
npm run typecheck
npm run lint
npm run docs:check
```

`tests/conftest.py` 显式使用离线后端，各测试把应用状态放到临时目录；Superset 单元测试使用受控替身。不会误用本机业务凭据或污染演示对话。

| 测试文件 | 负责验证 |
|---|---|
| test_auth.py | 管理线/HRBP 范围、字段依赖、策略变更、异常关系 |
| test_queries.py | 20 个固定计划、独立 Python 参考、时间/分母/分页 |
| test_graph.py | LangGraph 路由、模型修正、条件绑定、多轮、历史和超时 |
| test_api.py | 会话、CSRF、越权、导出、统一 HTTP 安全边界 |
| test_superset_query.py | 表达式编译、固定数据集、在线禁止读取本地全量人员 |
| test_superset_source.py | 身份映射、出口快照、上游故障、完整性和拒绝回退 |
| test_migration.py | 历史与凭据迁移、重复执行不覆盖、文件权限 |

`evaluation/cases.json` 是 20 个业务问题，`plans.json` 是人工预期计划，`golden.json` 是基准结果，`paraphrases.json` 是口语变体。生产规划器不读取预期计划或基准答案。

## 2. 真实 Superset / PostgreSQL 回归

先确保平台已安装，清单与凭据存在于 `.local/application`。以下按顺序运行，避免撤权测试和日常查询并发。

```bash
uv run python integrations/superset/run.py verify-storage
npm run test:superset
npm run test:revocation
```

- 存储核验检查导入内容指纹、300 人/26 字段、数据库账号物理列权限、数据集/用户/角色/RLS。
- 集成核验用真实业务账号执行 20 个预期 Plan，与独立 BFS/逐人计算对照，覆盖 HTTP 查询、核验、导出、关系、跨用户历史和异常拒绝。在线分支读取本地人员 SQLite 会直接使测试失败。
- 撤权测试临时修改本项目拥有的策略/角色/RLS，检查历史失效及请求拒绝，最后恢复。测试中断时先读 `integrations/superset/.local/application/probe-recovery.json` 并按脚本恢复，再继续演示。

在线“独立核验”以用户已授权快照作为输入，证明计算一致；授权范围本身是否正确，需要上面的离线 BFS 对照，不能混为同一个结论。

## 3. 模型和性能

```bash
npm run test:model -- --cases HR-01 --output reports/model-smoke.json
npm run test:paraphrases
npm run test:performance
```

模型验证逐题串行，使用独立应用状态，真实调用 LM Studio。报告分别记录原始候选、规则补齐、最终计划和结果；不把修正后的正确答案当作原始模型已正确。

`test:performance` 明确使用离线 SQLite，不推理，只测试本机 300 人样本上的权限、SQL、摘要和分页。这个结果不能代表生产 PostgreSQL 容量。

本机进行模型推理或生产构建前后检查 `uptime`、`memory_pressure`、`pmset -g therm`，保持单任务/保守并发；没有传感器读数时不报告具体温度。

## 4. 前端和 CI

```bash
npm run build
# 已启动应用时，执行通过同源代理的 HTTP 冒烟：
uv run python scripts/smoke_http.py
```

页面检查覆盖 `/`、`/debug`、身份切换、表格、调试记录和旧书签重定向。`scripts/ci-smoke.sh` 在独立临时数据目录以离线模式启动前后端，结束后只清理自身进程和状态。

- `.github/workflows/ci.yml`：类型、lint、Python、文档、构建和 HTTP 冒烟。
- `.github/workflows/superset.yml`：临时 Docker 平台，从零初始化、存储校验、真实查询和撤权恢复。
- `.github/workflows/release.yml`：手动打包当前源码。上线环境与正式认证需另行配置。

本地通过不等于远端 CI 已通过。每次交付以实际执行结果为准，不保留过期成功报告作为当前依据。
