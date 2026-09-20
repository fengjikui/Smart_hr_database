# 澄观 HR 智能查询

用自然语言查询授权范围内的人员、教育背景和入离职数据，并查看统计口径、结果表格、独立核验和逐节点调试。

仓库只维护一套应用：**React 工作台 → FastAPI / LangGraph → Superset → PostgreSQL**。默认使用 Superset 权限；SQLite 是显式选择的离线验证后端。样本为 300 人、26 个字段、15 个指标，数据截止日固定为 `2026-09-11`。

## 启动

依赖：Node.js 24、Python 3.13、uv，以及 Docker/Compose。模型在本机 LM Studio，默认兼容接口 `http://127.0.0.1:1234/v1`、模型标识 `hr-qwen`。

```bash
npm ci
uv sync --frozen
# 从之前的目录布局升级时执行；保留原文件，不覆盖已有目标。
npm run migrate
# 首次安装平台；已有正常运行的平台使用 npm run superset:setup。
npm run superset:up
npm run demo
```

默认 Docker socket 为本机 Colima 的 `~/.colima/hr-superset/docker.sock`。其他 Docker 环境须设置 `HR_DOCKER_HOST`，例如 Linux：`export HR_DOCKER_HOST=unix:///var/run/docker.sock`。启动器不会自行安装 Docker 或下载模型；LM Studio 需已安装对应模型。

- [工作台](http://127.0.0.1:3000/)：问数、自助核验、关系与权限、题单、历史、字段与口径。
- [节点调试](http://127.0.0.1:3000/debug)：每一步的输入、输出、SQL、结果与耗时。
- [Superset](http://127.0.0.1:8088/)：数据集、用户、角色和 RLS 配置。
- [API 文档](http://127.0.0.1:8000/api/docs)。

不连接 Superset 时可运行 `npm run demo:offline`，仍是同一套界面与指标。Superset 模式故障不会自动降级到离线模式。

## 文档从这里读

| 文档 | 内容 |
|---|---|
| [代码目录与整体逻辑](docs/PROJECT_CODE_GUIDE.md) | 文件职责、一次问数的完整过程、权限、前端状态和接口 |
| [字段与指标字典](docs/DATA_DICTIONARY.md) | 当前 26 字段、15 指标、别名、含义边界、20 个问题 |
| [Superset 实施讲义](docs/SUPERSET_SETUP.md) | 数据生成/导入、连接、7 个用户、8 个角色、3 条 RLS、Agent 接入 |
| [测试和交付](docs/TESTING.md) | 离线、真实权限、模型、页面验证及 CI |
| [安全边界](docs/SECURITY.md) | 已实现的控制、演示限制和生产接入要求 |

文档只描述当前代码；旧方案、旧实验、旧报告可从 Git 历史查阅。

## 日常命令

```bash
npm test                       # 隔离状态的单元/回归测试
npm run typecheck
npm run lint
npm run docs:check             # 字段/指标/题单文档与源码一致
npm run test:superset          # 真实平台查询/权限/20 个固定计划，无模型
npm run test:revocation        # 临时撤权、验证拒绝、finally 恢复
npm run test:model -- --cases HR-01
npm run build
```

## 配置与数据

环境变量应通过终端导出；`.env.example` 是示例，Python 与启动器不会自动读取 `.env`。

| 配置 | 默认值 / 说明 |
|---|---|
| `HR_QUERY_BACKEND` | `superset`；仅接受 `superset` 或 `sqlite` |
| `HR_SUPERSET_URL` | `http://127.0.0.1:8088` |
| `HR_SUPERSET_DIR` | `integrations/superset/.local/application` |
| `HR_DATA_DIR` | `data`，保存 `sessions.sqlite` 和 `people.sqlite` |
| `HR_BACKEND_URL` | `http://127.0.0.1:8000`，仅前端代理服务端使用 |
| `LM_STUDIO_URL` / `LM_STUDIO_MODEL` | 本机模型地址 / `hr-qwen` |
| `LM_STUDIO_TIMEOUT` | 单次模型请求 90 秒 |

目录迁移使用 SQLite backup API 复制历史和样本，且只在目标不存在时复制。更新后刷新页面重新选择演示身份即可；历史仍按所属身份及当前权限指纹读取。数据库已有对象 ID 和名称保持稳定，迁移不会重建用户、RLS 或 PostgreSQL 数据。

本系统是回环地址的合成数据演示。身份选择器不是企业 SSO；不能直接暴露到公网或拿演示规则代表已经确认的 HR 正式制度。
