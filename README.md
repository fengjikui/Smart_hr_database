# 澄观 HR · 智能数据工作台

面向现场沟通的完整本地演示：自然语言问数、直属与间接下属权限、统一指标口径、图表与明细、个人看板、组织浏览及数据治理。使用本机 LM Studio 的 **Qwen3.8-27B-MLX**，数字由受控 SQL 计算。全部人员和业务记录均为合成数据。

## HR 演示 V2

**新演示入口：[http://127.0.0.1:3000/demo](http://127.0.0.1:3000/demo)**。面向 HR 的 300 人、26 字段最小宽表，支持多指标/多维度问数、Excel 风格筛选统计、逐人员独立对账、HRBP 向上继承、角色配置、多轮与历史恢复。

现场操作见 [V2演示脚本](docs/DEMO_V2_WALKTHROUGH.md)，测试证据见 [V2验收报告](docs/DEMO_V2_VALIDATION.md)，实现及边界见 [V2实现记录](docs/DEMO_V2_IMPLEMENTATION.md)。下文原版入口和多表考勤能力仍保留，与 V2 使用独立演示数据。

**学习整个代码库先读 [代码目录与执行逻辑导读](docs/PROJECT_CODE_GUIDE.md)**，它区分原版、V2 两种查询后端与独立权限实验，并串起一次提问的完整调用链。更多专题见 [文档导航](docs/index.md)。

当前分支的 V2 还支持 Superset/PostgreSQL：先按 [完整接入讲义](docs/V2_SUPERSET_IMPLEMENTATION_GUIDE.md) 初始化，再运行 `npm run demo:superset`，仍打开 `/demo`。普通 `npm run demo` 默认使用 SQLite；分支名不会自动决定运行后端。

## 原版现场启动与独立实验

独立的 **OpenFGA 花名册权限演示**：[http://127.0.0.1:8091](http://127.0.0.1:8091)。用 12 名合成员工演示成熟引擎的汇报线递归、HRBP 继承、角色配置、调岗撤权和真实请求响应。运行 `uv run python integrations/openfga/runtime.py up`。详见 [启动、5分钟讲解与权限模型](integrations/openfga/README.md)。该实验与下方 HR 问数主系统分开运行。

本机已安装依赖、生成数据并加载模型。双击根目录的 **`启动演示.command`**，或在终端执行：

```bash
npm run demo:production
```

打开 **http://127.0.0.1:3000/**。首次缺少构建时会自动构建；模型未加载时会使用本机已有的 `qwen3.8-27b-mlx` 加载为 `hr-qwen`。27B 模型需要足够的可用内存。启动器发现已有演示服务会退出，避免重复启动。终端 Ctrl+C 停止本次前后端，保留 LM Studio。

右上角切换公司负责人、研发负责人、团队主管、研发 HRBP、普通员工。公司负责人有459名当前在职人员可见，直属5名、间接453名，另有本人；研发负责人当前范围168名，直属3名、间接164名。所有数据以 **2026-09-11** 为演示截止日，“本月”“今天”都相对该日期。

建议从“我的直属和间接下属分别有多少人？”开始，再保存到看板、切换研发负责人、查看权限收缩。完整10分钟流程见 [现场演示脚本](docs/DEMO_SCRIPT.md)。

## 从干净检出安装

依赖：Node.js 24、npm、uv/Python 3.13；本机 LM Studio CLI `lms`，并已下载上述模型。Python 版本由 uv 管理。

```bash
npm ci
uv sync --frozen
uv run python -m backend.hr.seed
npm run build
npm run demo:production
```

开发模式使用 `npm run demo`。前端3000、后端8000、模型1234全部仅监听本机。启动器自动设置默认本地模型；若手动使用其他模型服务，请按 `.env.example` 导出环境变量，再分别运行 `npm run api` 与 `npm run dev`。`.env` 不会被后端自动加载。生产模式修改代码后先重新 `npm run build`。

## 原版已实现

- 24张业务表、480名模拟员工、51个组织节点、四级组织、79,735条考勤；另有独立应用库存身份、口径、看板、会话与审计。
- 17项正式定义的演示指标，涵盖人数、入离职、司龄、考勤、批准加班、晚离岗及受限薪酬汇总。
- 模型只生成严格类型的查询计划；服务器重新校验身份与范围，确定性编译参数化只读 SQL，结果不交给模型补写。
- 基础人员明细按汇报或HRBP组织范围授权；薪酬另授聚合能力，小样本及必要的互补分组隐藏；私人证件、银行账号不进入查询能力。
- 看板保存计划，每次打开或刷新以当前权限重新执行，撤权不会继续显示历史缓存。
- 八个实际可用页面、移动窄屏适配、查询忙碌/模型离线/空结果/拒绝状态、API限制与审计。

绩效、招聘、培训已有模拟关系表，用于讨论后续接入，**当前尚未开放自然语言查询**。一个问题支持一个指标和一个分组维度；年龄、性别、排名、同比、预测等条件明确拒绝或澄清。

## 原版数据结构与节点调试

左侧新增 **数据库与口径**（公司负责人身份）和 **节点调试**。数据库与口径页列出全部24张业务表、8个应用逻辑表/索引、3个语义逻辑表/索引、200个字段及17项指标，可展开类型、主外键、索引、完整DDL、计算公式和编译SQL。内容来自实际数据库和查询编译器。

节点调试展示真实链路的输入、输出、状态、耗时和错误，包括模型完整请求、结构化候选、计划校验、修正、权限集合、SQL和结果。问数回答下可直接打开本次运行，也可在调试页运行问题；每身份最近50次记录，授权变化后旧记录不可读。

完整枚举见 [数据与字段字典](docs/DATA_DICTIONARY.md)，机器可读版见 [data-dictionary.json](docs/data-dictionary.json)，使用方法和采集边界见 [节点调试](docs/DEBUGGING.md)。

## 验证和交付

```bash
uv run python -m backend.hr.validate   # 32项数据规则
uv run pytest -q                      # 数据、查询、权限、API回归
npm run typecheck
npm run lint
npm run build
npm run test:model                    # 需真实LM Studio，20个场景
npm run test:performance              # 本地查询服务基准
bash scripts/check.sh                # 安装锁定依赖并执行完整CI检查
npm run release                      # 干净Git版本检查、构建、打包源码
```

完整CI检查会临时启动3000/8000端口，执行前先停止已有演示。已启动生产演示时可运行 `uv run python scripts/smoke_http.py --model` 验证真实HTTP与模型链路。

原版 LangGraph 与语义库的验证证据及边界见 [语义架构](docs/SEMANTIC_ARCHITECTURE.md) 和 [测试说明](docs/TESTING.md)。`evaluate_model.py`自动隔离应用库；使用`--suite semantics`运行原版20个口语场景。GitHub CI 与发布工作流已提供；仓库可见性以 GitHub 实际设置为准，V2 的验证结果见上方专门报告。

## 文档索引

| 文档 | 内容 |
|---|---|
| [整个项目代码导读](docs/PROJECT_CODE_GUIDE.md) | 完整目录、V1/V2区别、模型到SQL调用链、权限边界、前端状态、API、测试与修改入口 |
| [V2 PostgreSQL 与 Superset 完整接入](docs/V2_SUPERSET_IMPLEMENTATION_GUIDE.md) | 300人完整迁移、用户/角色/RLS清单、Agent真实查询接入、逐步复现与权限验收 |
| [Superset 权限实操课](docs/SUPERSET_HANDS_ON_CLASSROOM.md) | 从12笔订单开始，手填角色、区域、本人、AND/OR、敏感字段与汇报线规则；含可复现数据和验收 |
| [Superset与OpenFGA学习指南](docs/SUPERSET_OPENFGA_STUDY_GUIDE.md) | 约105分钟学习路线、能力对照、配置与接入、同步和性能、官方出处、自测与讲解稿 |
| [产品需求](docs/PRODUCT_REQUIREMENTS.md) | 用户、功能边界、验收标准 |
| [语义层与LangGraph](docs/SEMANTIC_ARCHITECTURE.md) | 查询图、渐进式披露、JSON/关系库/向量方案取舍 |
| [完整语义定义](docs/SEMANTIC_REFERENCE.md) | 200字段和32指标的ID、别名、正反含义、公式与示例 |
| [160个HR问题](docs/HR_QUESTION_BANK.md) | 已支持、规划和需澄清问题 |
| [整体架构](docs/ARCHITECTURE.md) | Agent流程、语义层存储、开源方案取舍 |
| [数据模型与口径](docs/DATA_MODEL.md) | 合成规则、考勤假设、宽表迁移 |
| [字段字典](docs/DATA_DICTIONARY.md) | 业务及应用表、字段、约束、指标目录 |
| [节点调试](docs/DEBUGGING.md) | 每步输入输出、错误定位、留存与调试权限 |
| [权限与安全](docs/SECURITY.md) | 权限矩阵、执行边界、撤权、审计 |
| [Superset集成调研](docs/SUPERSET_INTEGRATION_RESEARCH.md) | 角色与行列权限、REST/MCP边界、OA身份映射 |
| [Superset权限实验](integrations/superset/README.md) | 独立PostgreSQL与Superset启动、演示账号、真实接口验收 |
| [OpenFGA权限演示](integrations/openfga/README.md) | 12人样本、可配置关系权限、官方引擎调用、调岗撤权及现场脚本 |
| [上线接入清单](docs/PRODUCTION_ROADMAP.md) | 应沟通的人、待获取材料、企业上线工作 |
| [运行与维护](docs/OPERATIONS.md) | 端口、模型故障、备份、发布与回滚 |
| [现场演示脚本](docs/DEMO_SCRIPT.md) | 10分钟演示与讨论顺序 |
| [测试说明](docs/TESTING.md) | 实际证据、测试范围、限制 |

## 生产边界

本版本用于**本机合成数据演示**。演示身份选择器有意允许切换身份，不是登录鉴权产品。SQLite模式由应用强制只读与授权；V2 Superset模式使用业务账号、数据集权限和RLS，业务关系规则仍由项目PostgreSQL视图实现。接入真实HR数据前需替换为企业SSO、正式授权管理及受控数据库执行边界，并完善HTTPS、集中审计与备份恢复，经HR和安全负责人验收。前端使用Sites脚手架的Vinext beta，正式技术选型应单独评审维护与兼容性；无需沿用演示框架。

源数据和模型文件均不提交Git。标准启动不会清空个人看板。合成数据重新生成是受控维护动作，不应在演示进行中执行。

## 原版教育背景与组织分析

员工档案新增最高学历、最高学位、毕业院校、专业、毕业日期、学习形式。独立教育经历表支持多校毕业去重，院校字典维护名称、简称和历史211/985标签。

可直接在智能问数输入“平台研发部现在有多少博士？”“上季度入职博士人数”“清华和北大毕业的员工数量”“平台研发部硕士毕业比例”“今年各部门入职和离职人数统计”“本月各部门周末加班总工时”。结果显示筛选条件，占比保留分子/分母，入离职展示双系列对比图；计划可以保存到看板。

完整默认口径、支持问题及接入字段见 [教育分析说明](docs/EDUCATION_ANALYTICS.md)。升级合成数据时先备份业务库，按原种子/人数/截止日重建；保留应用库，旧看板的“部门”分组迁为“团队”以保持原有具体任职组织分组语义。

## 原版语义知识库与渐进式查询

左侧“语义知识库”可搜索17个可执行指标、15个规划指标、200个字段和160个问题，查看口语别名、“表示什么／不表示什么”、时间和权限口径、依赖字段、示例及实际LangGraph查询图。数量按公司负责人身份统计，其他身份只显示可读定义。

定义在`semantic/*.json`经Git管理，发布到独立的`data/semantic.sqlite`。模型先看到相关定义和轻量指标索引，需要时通过`inspect`补充读取，最多两轮；SQL由原有受控编译器生成。节点调试记录检索、披露、补读与重新鉴权的实际输入输出。规划指标不会执行，暂不启用向量检索。
