# Superset 6.1.0 官方 MCP 独立实验实操

本实验在 `codex/superset-mcp-integration` 分支开发，起点为包含交接文档的 `d2b3bc6`。请在本分支的**独立工作树根目录**执行以下宿主机命令。不要在课堂目录执行；不要合并本分支来“补齐”课堂进度。

交付状态、已知限制与逐项验证见 [验证报告](SUPERSET_MCP_VALIDATION.md)。本手册面向本机合成数据演示，不是生产 SSO 部署。

## 1. 先看清楚实际链路

实验中的 MCP 服务是独立进程，运行在单独容器，使用 Apache Superset 6.1.0 镜像内的官方工具。它和**实验 Web**共享实验 `superset_meta` 元数据库、业务连接和 `superset_config.py`；不连接课堂库。

```text
浏览器演示登录 → 应用服务端 session → 固定 persona/员工/角色映射
                                         │
                   ┌─────────────────────┴──────────────────────┐
                   │                                            │
            MCP 短期 JWT                                  REST 业务账号登录
                   │                                            │
      initialize → tools/list → list_datasets          context/人员/事件授权快照
                   │                                            │
         经权限过滤的目录（不接纳远端指令）                     受限 Plan 校验/编译
                   └─────────────────────┬──────────────────────┘
                                         │
                            Superset Chart Data REST API
                                         │
                    数据集鉴权 → 当前用户 Base RLS → PostgreSQL
                                         │
                            确定性摘要、核验、历史与节点调试
```

Agent 模式名是 `superset_mcp`，响应明确标注 `superset_mcp_catalog_rest_query`。它真实使用 MCP 目录能力作为权限与可用性前置检查。**20 种 Plan 的执行仍走受控 REST，不是全 MCP 问数。** MCP 一旦不可用，查询/核验/历史/导出均关闭，不会跳过 MCP 继续执行。

另有真实官方 `get_chart_data` 图表查询验证，它经过 Superset 内部 `ChartDataCommand` 和 PostgreSQL，既不是自建同名工具，也不是客户端偷偷调用 REST。它只验证已保存图表，未接管 Agent 的自由组合 Plan。

原因：`get_chart_data` 接收已保存图表 ID/缓存表单键及少量过滤参数，没有现有编译器所需的完整多 QueryObject 接口。创建或更新图表会增加写入能力，本实验禁止。实测将 `limit` 设为 1 时，返回 `row_count=1,total_rows=1`，不能用这些值证明有权查看的完整人数。原 REST 的独立总计、明细完整性和事件校验继续保留。

## 2. 隔离清单与启动前检查

| 对象 | 课堂/其他会话 | 本实验 |
|---|---|---|
| Compose 项目 | `hr-superset-lab`、`hr-openfga` | `hr-superset-mcp` |
| Superset Web | `127.0.0.1:8088` | `127.0.0.1:18088` |
| PostgreSQL | `55432`；OpenFGA 占 `55433` | `127.0.0.1:55434` |
| 官方 MCP | 无此实验服务 | `127.0.0.1:15008/mcp` |
| 应用 API / 前端 | `8000` / `3000` | `18000` / `13000` |
| Docker 网络 / 卷 | 课堂原网络/卷 | `hr-superset-mcp_default` / `hr-superset-mcp_postgres-data` |
| 私有状态 | 课堂 `.local` | `integrations/superset_mcp/.local/` |
| 应用 Cookie | `hr_session` | `hr_mcp_session` |
| 平台 Cookie | 课堂默认名 | `hr_superset_mcp_session` |

不同端口仍共享浏览器 Cookie 域，因此 Cookie 名也必须隔离。数据库名 `superset_meta` / `hr_v2` 在实验容器内部复用，但实例、账号密码、连接网络和存储卷均独立。Agent 不持有 PostgreSQL 管理凭据；管理连接仅用于自动建库和可逆测试。

1. 确认 Git 状态及工作树：

   ```bash
   git branch --show-current
   git status --short
   git worktree list
   ```

   预期位于独立分支。若从干净 checkout 开始，可先用 `git worktree add ../Smart_hr_database-mcp codex/superset-mcp-integration`，再进入新工作树。分支已在别处使用时不要强行复用。不要切换课堂目录分支，不覆盖课堂未提交文件。

2. 检查本机与端口：

   ```bash
   uptime
   memory_pressure
   pmset -g therm
   lsof -nP -iTCP -sTCP:LISTEN
   ```

   Linux 主机相应使用 `free -m` 等可取得的指标。没有温度传感读数时只报告系统热状态。出现热压力/明显内存压力时停止本实验构建或推理，保留课堂服务。构建、测试和模型调用串行执行。

3. 选择 Docker 引擎：`lab.py` 默认连接已存在的 Colima `hr-superset` profile 的 socket；若使用其他引擎，先设置 `HR_DOCKER_HOST`。入口不修改全局 Docker context，也不启动/重配/停止已有虚拟机。确认引擎资源足够；本次复用了同一引擎，但服务、网络、卷完全隔离。

   ```bash
   uv run python integrations/superset_mcp/lab.py targets
   ```

   预期打印上表的项目、端口、卷和状态路径，不显示密码。首次 `up` 会检查三个服务端口冲突。若本机另有占用，应统一修改实验 `compose.yaml`、`lab.py` 及配置中的地址，再重测；不要停止未知进程。`55434` 是本次实测选定端口。

源码：`integrations/superset_mcp/lab.py` 的 `environment/targets/compose`，以及专用 `compose.yaml`。不要运行课堂的 `integrations/superset/services.sh up` 或课堂 `run.py setup`。

## 3. 首次安装：每一步都可检查

### 3.1 安装应用依赖并生成实验材料

在工作树根目录执行：

```bash
uv sync --frozen
uv run python integrations/superset_mcp/lab.py prepare
```

目的：创建新的随机密钥、确定性 300 人样本、五种业务身份和独立应用历史目录。已有密钥不覆盖。没有复制课堂数据、密码或手工配置。

预期生成：

- `.local/lab.env`：PG 管理、元数据库、Web 密钥、账号派生种子、MCP 独立密钥，权限 `0600`。
- `.local/mcp-signing.json`：Agent 服务端签名资料，`0600`。
- `.local/application/fixtures.json`：合成导入材料，单独只读挂载给容器。
- `.local/application/credentials.json`：独立业务密码，`0600`。
- `.local/app/`：本实验的样本和会话历史。

以上 `.local` 均位于 `integrations/superset_mcp/` 下，已被 Git 忽略，Docker 构建上下文也排除。整个私有目录为 `0700`。不要把文件内容贴到工单、模型消息或终端记录里。

失败排查：若存在实验 `manual-learning.json`，入口拒绝初始化；先了解标记用途，不删除标记绕过。课堂的学习标记不读写、不移除。对应源码：`lab.py:prepare`、复用的 `integrations/superset/export.py`。

### 3.2 构建带官方 MCP 依赖的隔离镜像

```bash
uv run python integrations/superset_mcp/lab.py build
```

镜像基础为 `apache/superset:6.1.0`。新增 `fastmcp==3.1.0`、`psycopg2-binary==2.9.11`，传递依赖受 `constraints.txt` 锁定。服务端 MCP SDK 实测 `1.30.0`；应用端 SDK 在 `uv.lock` 中固定为 `1.26.0`，二者已真实握手协商至 `2025-11-25`。

预期生成 `hr-superset-mcp:6.1.0-fastmcp3.1.0`。构建入口打印负载/内存/热状态；UV 安装并发为 1，下载并发为 2。失败时检查引擎网络和镜像获取，不进入课堂容器临时 pip 安装。对应源码：专用 `Dockerfile` / `constraints.txt`。

### 3.3 启动平台和 MCP，再初始化本实验业务

```bash
uv run python integrations/superset_mcp/lab.py up
uv run python integrations/superset_mcp/lab.py bootstrap
uv run python integrations/superset_mcp/lab.py health
uv run python integrations/superset_mcp/lab.py status
```

`init` 容器仅迁移实验平台库并初始化内置权限。`bootstrap` 在实验 Superset 容器内执行 `/mcp-lab/bootstrap.py`，复用 `/lab/setup.py` 的建库/视图/角色/RLS 逻辑，清单写回本实验的 `manifest.json`。

预期：300 人、5 个业务身份、5 个数据集、3 条 Base RLS；Web health 为 200，匿名 MCP 请求为 401。`init` 最后显示退出码 0 是正常状态；Web/MCP/PostgreSQL 应持续运行。`health` 只是进程和认证入口检查，不能替代下一步逐用户工具测试。

失败排查：

- `up` 最多等 45 秒；若未就绪，用 `lab.py logs` 看 MCP 日志。
- 业务初始化失败时不要重复删除卷。核对实验 `fixtures.json` 和容器日志，再重跑幂等 `bootstrap`。它保留已有角色与 RLS 修改，不是重置命令。
- 日志含 `No authenticated user found`：检查是否误用原生 CLI 启动，见第 5 节。
- `DetachedInstanceError`：确认使用包含串行锁的实验启动入口，且只有一个 MCP worker。

精确容器命令是 Web 的 `gunicorn ... superset.app:create_app()` 和 MCP 的 `python /mcp-lab/server.py`。两者共享配置路径 `/mcp-lab/superset_config.py`。原生官方 CLI 帮助仍可用以下只读命令查看：

```bash
export DOCKER_HOST="${HR_DOCKER_HOST:-unix://$HOME/.colima/hr-superset/docker.sock}"
docker-compose -p hr-superset-mcp -f integrations/superset_mcp/compose.yaml exec -T mcp superset mcp run --help
```

使用 Docker Compose 插件的机器将 `docker-compose` 换为 `docker compose`；`lab.py` 会自动选择可用版本。

### 3.4 两种身份的完整真实协议调用

```bash
uv run python integrations/superset_mcp/lab.py run uv run python integrations/superset_mcp/probe.py --persona employee
uv run python integrations/superset_mcp/lab.py run uv run python integrations/superset_mcp/probe.py --persona hr_lead
```

顺序：服务端映射身份 → 签发短期 JWT → MCP `initialize` → SDK 发送 `notifications/initialized` → `tools/list` → `tools/call`。输出协议版本、官方工具名、授权目录、公共数据集列和图表结果摘要；不输出 token。

员工目录应只有 `context`、`people_public`、`events_public`；HR 主管还可看到两个合同出口。五种身份图表名单验证使用工号集合哈希，不只比较行数。员工直接猜合同 ID 也会被服务端拒绝，完整负例见第 7 节。

这里不要求用户复制 JWT 到 curl，更不把 REST token 当作 MCP token。`probe.py` 是命令行验证客户端；真正的 Agent 入口在下一步。

### 3.5 启动现有 Agent 页面

终端 A，启动独立 API：

```bash
uv run python integrations/superset_mcp/lab.py run uv run uvicorn backend.hr.api:app --host 127.0.0.1 --port 18000
```

终端 B，安装前端依赖并启动独立前端：

```bash
npm ci --no-audit --no-fund
uv run python integrations/superset_mcp/lab.py run npm run dev -- --port 13000 --hostname 127.0.0.1
```

访问 [实验工作台](http://127.0.0.1:13000)，选择员工，提问“我能看到多少在职人员？”。再选择 HR 主管查询按部门在职人数。页面标记“MCP 目录 · REST 查询”；成功记录的节点调试应包含“官方 MCP 授权目录发现（查询仍走 REST）”、实际协议阶段及后续 SQL 执行。MCP 网络调用发生在授权快照刷新时；目录节点复用并展示这份证据，该节点自身的小耗时不是网络延迟，网络时间计入身份校验/执行前后鉴权。也可打开 [API 实操界面](http://127.0.0.1:18000/api/docs)。

LM Studio 复用**当前已经加载的** `hr-qwen`，本实验不会自动重启、卸载或换模型。`LM_STUDIO_URL` / `LM_STUDIO_MODEL` 可由服务端环境显式配置。自然语言测试前检查本机负载；模型不可用时可在 API 的 `/api/query` 使用受限 Plan 验证，但必须标为结构化计划测试。

排查：API `/api/health` 应显示混合路径。前端代理目标必须为实验 `18000`；Cookie 为 `hr_mcp_session`。返回 403 时先检查来源、CSRF 和业务权限；不要换管理员重试。前端服务端代理代码在 `app/api/[...path]/route.ts`，不会把上游凭据传给浏览器。

## 4. 已有实验的日常启停

已有数据卷时不要重新 `prepare/bootstrap` 当作日常恢复：

```bash
uv run python integrations/superset_mcp/lab.py start
uv run python integrations/superset_mcp/lab.py health
uv run python integrations/superset_mcp/lab.py status
uv run python integrations/superset_mcp/lab.py logs
```

配置或 Python 挂载源码变化后：

```bash
uv run python integrations/superset_mcp/lab.py restart
```

该命令只重启实验三个长驻容器，不执行业务初始化；API 在终端 A 用 Ctrl+C 后按原命令重开。镜像依赖变化时先 `build` 再 `up`，会重建实验容器；不是课堂恢复命令。

停止：前端/API 在各自启动终端 Ctrl+C，然后执行：

```bash
uv run python integrations/superset_mcp/lab.py stop
```

它保留实验卷和私有文件。不要运行全局 `docker system prune`、停止 Colima profile，或扫描并杀死所有 Python/Node 进程。

## 5. 官方版本差异与部署适配层

官方资料：[6.1.0 MCP 部署与认证](https://superset.apache.org/admin-docs/6.1.0/configuration/mcp-server/)、[6.1.0 AI 使用说明](https://superset.apache.org/user-docs/6.1.0/using-superset/using-ai-with-superset/)、[6.1.0 源码](https://github.com/apache/superset/tree/6.1.0)。以下将文档说明、源码观察和本机结果分开。

- 官方部署文档说明独立 MCP 进程、JWT 验证与用户名解析。本镜像的原生 `superset mcp run` 可握手、发现 24 个工具，但正确 JWT 调用目录仍失败。
- 镜像源码 `superset/mcp_service/server.py:run_server` 配置 JWTVerifier；`auth.py:get_user_from_request` 查 `g.user` 或开发用户名，原生路径没有把验签结果填入 `g.user`。不是密钥或用户不存在的问题。
- 实验 `server.py:PrincipalBinding` 使用官方 FastMCP 中间件接口，从已验证 token 的 `claims.sub` 查真实 Superset 用户，拒绝未知/停用用户；每次建立新的 Flask 请求上下文，再调用原官方工具。没有修改镜像内官方工具、DAO 或权限方法。
- 实际两个异步请求并行查询图表出现 `DetachedInstanceError`。实验将整个工具调用串行化，解决同进程 Flask-SQLAlchemy 2.5.1 会话生命周期冲突；等待加执行最多 20 秒。多进程、多节点、大规模并发尚未验证。
- 原生认证工厂可能捕获异常并返回 `None`。实验入口直接调用工厂并检查非空，配置错误时启动失败，不静默关闭认证。
- 部分图表写工具的装饰器使用读权限名称；不据此声称所有 mutate 工具天然安全。本部署服务端只允许 `list_datasets`、`get_dataset_info`、`get_chart_data` 三个已验工具，其余调用全部拒绝。完整 24 工具仍可发现；“显示”与“允许调用”分别看待。

因此这是“官方 MCP 工具 + 显式部署适配层”，不能称为原生 CLI 零适配多用户部署已经成功。

## 6. 身份、RLS 和接口边界

### 身份传递

`backend/hr/auth.py` 从有效应用 Cookie 恢复预定义 persona。`superset_source.identity` 交叉检查 persona ID、人员主键与角色，再选清单里的业务用户名，显式拒绝技术配置管理员。演示页面能够切换五种固定身份，这不是企业员工认证；生产须以可信 SSO 替换演示登录。

`superset_mcp.token_for` 使用独立秘密签发 HS256 JWT：`sub=业务用户名`、`iss=hr-mcp-lab`、`aud=superset-mcp`、`scope=mcp:read`，有效期 120 秒。密钥仅在后端私有文件与服务端配置中，模型/问题/Plan 无法指定用户、token 或数据源 ID。

REST 登录 JWT 使用另一套秘密和语义；实测它到 MCP 得到 401。`mcp:read` 只是准入 scope，并非通用写操作禁止机制。写入限制由部署白名单及 Superset FAB/RBAC 共同承担。

### 官方执行点

| 阶段 | 6.1.0 官方源码 | 检查位置 |
|---|---|---|
| 工具级权限 | [`auth.py`](https://github.com/apache/superset/blob/6.1.0/superset/mcp_service/auth.py) | `mcp_auth_hook` → `check_tool_permission`，检查当前 `g.user` 的 FAB 权限 |
| 目录按数据集过滤 | [`dataset.py`](https://github.com/apache/superset/blob/6.1.0/superset/daos/dataset.py)、[`mcp_core.py`](https://github.com/apache/superset/blob/6.1.0/superset/mcp_service/mcp_core.py) | `DatasetDAO.base_filter = DatasourceFilter`；列表与详情使用受过滤 DAO |
| 官方图表取数 | [`get_chart_data.py`](https://github.com/apache/superset/blob/6.1.0/superset/mcp_service/chart/tool/get_chart_data.py) | 检查图表的数据源权限，再 `ChartDataCommand.validate/run`；不调用 SQL Lab |
| 数据集授权 | [`get_data_command.py`](https://github.com/apache/superset/blob/6.1.0/superset/commands/chart/data/get_data_command.py)、[`query_context.py`](https://github.com/apache/superset/blob/6.1.0/superset/common/query_context.py) | validate → QueryContext.raise_for_access → security_manager.raise_for_access |
| RLS 拼装 | [`manager.py`](https://github.com/apache/superset/blob/6.1.0/superset/security/manager.py)、[`models.py`](https://github.com/apache/superset/blob/6.1.0/superset/connectors/sqla/models.py) | `get_rls_filters` 选择 Base/Regular 规则，`get_sqla_row_level_filters` 渲染当前用户并加入查询 |
| 自由 SQL | [`execute_sql.py`](https://github.com/apache/superset/blob/6.1.0/superset/mcp_service/sql_lab/tool/execute_sql.py) | SQL Lab 独立能力，需要 `can_execute_sql_query`；本实验业务用户不具备，部署层也禁用 |

本地 `schema.sql` 的权限视图先计算“查看人→可见人员”，Superset Base RLS 再把 `_viewer_id` 限制为 `{{ current_user_id() }}`。`context` 使用 `superset_user_id`。这不是 PostgreSQL 登录用户等于某员工，也不是 Python 拼入模型选择的查看人 ID。

### 目录与工具输出

Agent 仅调用 `list_datasets`，只请求 ID/表名，并与服务端清单匹配后输出固定出口名称。远端描述、SQL、owner、工具原始错误及请求头均不进入提示词。已注册字段/指标目录仍由原项目受限 schema 与当前授权字段生成；MCP 内容作为外部数据处理，不作为高优先级指令。

每次创建并销毁独立 MCP 客户端与短期 token，不跨身份缓存。客户端总超时 25 秒、响应最多 1 MiB（解析前限制）、不自动重试、不跟随重定向；目录超 100 项、计数/分页不完整时拒绝。SDK 的异常组不直接转发浏览器。

授权快照包含 MCP 目录及所有相关人员/事件出口的键。新查询、模型前后、存档、历史恢复、调试和导出都重新检查指纹；权限变化不继续复用旧结果。核验与**本次选中的出口**取交集，事件键精确到人员/日期/入离职类型，不能从较宽的人员快照重建已撤销事件。

## 7. 验证命令与结果判读

先静态/协议边界单测，再真实服务，再少量真实模型：

```bash
uv run ruff check backend tests scripts integrations
uv run pytest -q
uv run python scripts/document_catalog.py --check
npm run typecheck
npm run lint
uv run python integrations/superset_mcp/lab.py run uv run python integrations/superset_mcp/validate.py
```

`validate.py` 必须串行单独运行，期间不要操作实验权限或做演示。它使用真实 MCP/REST/PostgreSQL，20 个固定 Plan 来自 `evaluation/plans.json`；不会调用模型。应用历史放临时目录。报告位于 `reports/superset-mcp-validation.json`，恢复快照为实验 `.local/probe-recovery.json`。

验证包括：五种身份精确人员集合、目录与合同反例、自由 SQL/写操作拒绝、缺失/错误/过期 JWT、错误签名/issuer/audience/scope、REST token 不兼容、未知/未映射身份、两个独立会话交错、20 Plan 明细/聚合、平台角色权限撤销、事件/人员 RLS 收窄、身份删除、管理线策略/环/孤儿、新查询/核验/历史/调试/导出失效，以及 MCP 断开失败关闭。

真实模型验证另行执行（已加载模型且资源允许时）：

```bash
uv run python integrations/superset_mcp/lab.py run uv run python integrations/superset_mcp/model_smoke.py
```

报告 `reports/superset-mcp-model.json` 明确区分模型原始计划、确定性修正和执行结果。测试只覆盖所列问题，不据此声称 20 题都经过模型。

若验证中断，先恢复后再重测：

```bash
uv run python integrations/superset_mcp/lab.py run uv run python - <<'PY'
import json
from integrations.superset_mcp.lab import LOCAL
from integrations.superset_mcp.validate import remote, require_isolated
require_isolated()
state = json.loads((LOCAL / 'probe-recovery.json').read_text())
assert remote('restore', state)['restored']
assert remote('capture') == state
account_file = LOCAL / 'account-recovery.json'
if account_file.exists():
    account = json.loads(account_file.read_text())
    assert remote('restore', account, account=True)['restored']
    assert remote('capture', account=True) == account
print('实验权限与关系精确恢复。')
PY
```

只使用同一实验生成的恢复文件，不跨环境复制。恢复失败保留现场与恢复文件，不能靠重新 bootstrap 或删库掩盖。

## 8. 清理与回滚

- 仅停用 MCP Agent 路径：停止实验 API/前端；默认 `HR_QUERY_BACKEND` 仍为 `superset`。不要把实验路径的环境变量带回课堂 shell。`lab.py run` 只给自己的子进程设置变量。
- 保留数据停止：`lab.py stop`。分支不自动合并、发布。
- 需要完全删除本实验时，在确认不再需要实验记录后，执行显式命名的 `docker-compose -p hr-superset-mcp -f integrations/superset_mcp/compose.yaml down --volumes`。这是删除实验数据的操作，不是日常重启。
- `.local` 包含数据库对应秘密；保留卷时必须保留匹配密钥，不能随机再生成。完整重建需同时处理**本实验**卷和私有材料，不触及课堂路径。
- Git 回滚按实验分支提交进行；不对课堂目录执行 `reset/clean/checkout`，不覆盖学习文档。

## 9. 新配置速查

| 配置 | 默认/实验值 | 含义与秘密边界 |
|---|---|---|
| `HR_QUERY_BACKEND` | 默认 `superset`；实验 `superset_mcp` | 显式开启混合路径；拼写错误拒绝 |
| `HR_SUPERSET_URL` | 默认 8088；实验 18088 | 服务端 REST 地址 |
| `HR_SUPERSET_DIR` | 默认原集成目录；实验自己的 application | 服务端清单与业务密码；模型不可见 |
| `HR_SUPERSET_MCP_URL` | `http://127.0.0.1:15008/mcp` | 官方 MCP 地址；不由前端覆盖 |
| `HR_MCP_SIGNING_FILE` | 实验 `.local/mcp-signing.json` | 仅服务端读取，包含签名秘密 |
| `HR_DATA_DIR` | 实验 `.local/app` | 隔离样本、会话、历史 |
| `HR_SESSION_COOKIE` | 默认 `hr_session`；实验 `hr_mcp_session` | 同主机端口间防会话覆盖，无秘密 |
| `HR_EXTRA_ORIGINS` | 默认空；实验 13000/18000 回环地址 | 服务端来源白名单增量 |
| `HR_BACKEND_URL` | 默认 8000；实验 18000 | 前端服务端代理目标 |
| `HR_DOCKER_HOST` | 已有 Colima profile socket | Docker 引擎选择，不改变全局 context |
| `MCP_AUTH_ENABLED` / `MCP_RBAC_ENABLED` | 实验均为 `True` | 认证和工具权限检查 |
| `MCP_DEV_USERNAME` | `None` | 不允许固定开发身份兜底 |
| `MCP_JWT_*` / `MCP_REQUIRED_SCOPES` | 见第 6 节 | issuer/audience 非秘密；secret 仅在私有 env |
| `MCP_TOOL_SEARCH_CONFIG` | `enabled=False` | 展示完整工具注册表便于审计，调用另做白名单限制 |
| `MCP_CACHE_CONFIG` | `enabled=False` | 不跨身份缓存工具结果 |
| `MCP_SERVICE_URL` | 实验 Web 18088 | 官方部分链接生成提示；部分工具仍可能返回内部默认 URL，Agent 不使用该 URL |
| `SESSION_COOKIE_NAME` | `hr_superset_mcp_session` | 实验 Web Cookie；不覆盖课堂登录 |

资源限制：每个 Web/MCP 容器最多 0.75 CPU、768 MiB，PG 最多 0.5 CPU、384 MiB；Web 单 worker，MCP 单进程单工具执行。需要更大规模前应重新设计分页、授权版本与多进程隔离，不能直接增加并发。
