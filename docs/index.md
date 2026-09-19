# 项目文档导航

更新日期：2026-09-20。仓库同存原版 HR、V2 宽表问数和独立权限实验。旧文档中的“已实现”与数据数量要结合版本阅读，不能直接套用到 V2 Superset 模式。

## 建议从这里开始

1. [整个项目代码目录与执行逻辑](PROJECT_CODE_GUIDE.md)：主导读，包含目录、调用链、前后端、数据、权限、API、开发和测试。
2. [V2 PostgreSQL 与 Superset 实施讲义](V2_SUPERSET_IMPLEMENTATION_GUIDE.md)：逐步重现完整 V2 数据导入与账号/角色/RLS 配置。
3. [Superset 手工权限课堂](SUPERSET_HANDS_ON_CLASSROOM.md)：从订单小样本手填规则，帮助理解过滤条件如何生效。

前端入口是 `app/`，后端主入口是 `backend/hr/api.py`；V2 业务代码在 `backend/hr/v2/`。当前使用 React/Vinext、FastAPI、LangGraph 和本地 LM Studio。完整项目说明见 [README](../README.md)。

## V2 宽表项目

| 文档 | 阅读目的 |
|---|---|
| [规划](DEMO_V2_PLAN.md) | 当时确定的范围、题目与阶段目标 |
| [实现记录](DEMO_V2_IMPLEMENTATION.md) | 原 V2 实现与约束；Superset 后续变化看最新接入讲义 |
| [现场演示路线](DEMO_V2_WALKTHROUGH.md) | 问数、核验、多轮、关系演示顺序 |
| [验收设计](DEMO_V2_ACCEPTANCE.md) | 如何定义要验证的结果 |
| [验证报告](DEMO_V2_VALIDATION.md) | 既有 V2 测试记录及边界 |
| [真实源数据契约](REAL_SOURCE_CONTRACT.md) | 宽表、主键、关联和业务假设 |
| [真实源字段对照](REAL_SOURCE_FIELDS.md) | 中英文源字段映射与解释 |

## 权限框架与集成

| 文档 | 阅读目的 |
|---|---|
| [Superset / OpenFGA 学习指南](SUPERSET_OPENFGA_STUDY_GUIDE.md) | 框架能力、配置、同步、适配边界与官方出处 |
| [Superset 初步调研](SUPERSET_INTEGRATION_RESEARCH.md) | 早期方案分析；实施状态以接入讲义和代码为准 |
| [Superset 实验环境](../integrations/superset/README.md) | 本机容器、实验用户、运行与验证 |
| [完整 V2 集成脚本说明](../integrations/superset/v2/README.md) | 导入、脚本职责、配置对象、Agent 对接契约 |
| [OpenFGA 独立实验](../integrations/openfga/README.md) | 官方引擎、模型/元组、发布、测试、五分钟演示 |

## 原版 HR、多表与语义定义

| 文档 | 阅读目的 |
|---|---|
| [产品需求](PRODUCT_REQUIREMENTS.md) | 原始目标、用户、功能边界 |
| [原版架构](ARCHITECTURE.md) | 原版组件、流程与技术选择 |
| [原版实施记录](IMPLEMENTATION.md) | 原版阶段性实现情况 |
| [数据模型](DATA_MODEL.md) | 多表合成数据、考勤和业务假设 |
| [字段字典](DATA_DICTIONARY.md) / [机器可读字典](data-dictionary.json) | 数据库表、字段、约束和指标 |
| [教育分析](EDUCATION_ANALYTICS.md) | 原版教育经历与院校统计 |
| [语义架构](SEMANTIC_ARCHITECTURE.md) | JSON→SQLite 语义发布、检索、LangGraph |
| [完整语义参考](SEMANTIC_REFERENCE.md) | 原版字段/指标定义、别名、正反含义 |
| [HR 问题库](HR_QUESTION_BANK.md) | 已支持、规划、需要澄清的问题；不全是 V2 可执行题 |
| [节点调试说明](DEBUGGING.md) | 原版调试采集、错误与权限；V2 独立页见源码导读 |
| [权限与安全](SECURITY.md) | 原版权限矩阵与安全边界 |
| [现场演示脚本](DEMO_SCRIPT.md) | 原版多表工作台演示 |

## 开发、验证与后续接入

| 文档 | 阅读目的 |
|---|---|
| [测试说明](TESTING.md) | 原版验证方法与历史证据 |
| [运行维护](OPERATIONS.md) | 模型、端口、故障、备份与发布 |
| [上线接入清单](PRODUCTION_ROADMAP.md) | 真实业务、认证、同步、审批与运维待办 |
| [产品背景](../PRODUCT.md) / [视觉背景](../DESIGN.md) | 初始产品与界面约定 |

新源码导读集中承载 API 清单、目录说明、数据模型概览、组件职责、跨系统关系和开发指引，避免再生成多份重复架构文档。`project-scan-report.json` 记录本次扫描范围与校验情况，不是系统运行配置；注释变更的核对结果见 [验证记录](../reports/project-code-guide-validation.json)。
