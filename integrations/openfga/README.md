# OpenFGA 权限方案

这是同一问数应用的独立权限后端，使用真实 OpenFGA 1.21.0 与 PostgreSQL 17.11。
不读取、重置或补齐 Superset 学习库。

- [逐步实操手册](../../docs/OPENFGA_HANDS_ON.md)：从概念、数据、模型、tuple 到 Agent 和撤权。
- [实现与安全边界](../../docs/OPENFGA_DESIGN.md)：职责、同步协议、代码地图、生产差距。
- [学习与验证记录](../../docs/OPENFGA_LEARNING_LOG.md)：助手完成的验证和你的手工进度分开记录。

在仓库根目录依次执行（首次安装）：

```bash
npm ci
uv sync --frozen
npm run openfga:up
npm run openfga:init
npm run openfga:seed
npm run openfga:sync
npm run test:openfga
npm run demo:openfga
```

`uv run python -m integrations.openfga.run materials` 可生成五份私有 SQL，按手册逐条建库/导入。

`seed` 拒绝覆盖已有数据，后续修改用 SQL，再 `sync`。`up` 只启动本方案服务，不自动导入人员和关系。

| 地址/对象 | 用途 |
|---|---|
| 127.0.0.1:8089 | OpenFGA HTTP API；须本机私有密钥 |
| 127.0.0.1:55433 | 独立 PostgreSQL |
| postgres 数据库 | OpenFGA 引擎自己的存储表，不手工编辑 |
| hr_openfga 数据库 | 演示源表、发布快照、受控查询出口 |
| .local/admin.json | 初始化/同步凭据；不进入应用 API |
| .local/runtime.json | 只读 PG 账号与本机 FGA 凭据 |
| .local/app | OpenFGA 模式独立会话/历史 |

OpenFGA 决策不能自动拦住所有数据库连接；应用和 PostgreSQL 出口仍是必要的执行边界。
本地预共享密钥具有管理能力，仅适用于该演示；正式环境必须分开管理和查询凭据/网络。
