# OpenFGA 花名册权限演示

本次交付目标：用简单合成数据证明团队能够配置、调用、测试成熟权限引擎，并解释权限随配置变化的结果。无需等待 HR 系统调研，也不把演示规则当成最终业务规则。

页面：http://127.0.0.1:8091

## 启动与停止

在仓库根目录运行（Python 依赖沿用项目的 uv.lock）：

```bash
uv sync --frozen
uv run python integrations/openfga/runtime.py up
uv run python integrations/openfga/runtime.py status
uv run pytest integrations/openfga/test_lab.py -q
uv run python integrations/openfga/runtime.py stop
```

首次启动下载 **OpenFGA 1.20.0** 与 **官方 fga CLI 0.7.20**，验证官方发布包的 SHA-256。运行 macOS/Linux、arm64/amd64 的官方二进制。没有容器或模型推理依赖，不占用现有 3000/8000/8088 服务。首次下载需要网络，下载后可离线演示。

使用 SQLite 保存引擎状态。HTTP 8090、gRPC 8092、演示页面 8091 均绑定 127.0.0.1；关闭 Playground 和 metrics。进程标识、日志、数据库、已下载程序、配置版本均存放于被 Git 忽略的 `.local/`。启动器不会停止其他项目的进程。不要把页面或引擎端口通过隧道公开。

本机只开 2 个 Go 逻辑处理器，Go 软内存目标 128 MiB。测试串行执行。该设置限制演示负载，不是生产性能配置。

## 5 分钟现场脚本

每轮演示先在“配置与人员变更”点击“恢复初始样本”。

| 操作 | 预期结果 | 要说明的能力 |
|---|---|---|
| 查看人切为员工 E | 1 人，仅本人 | 最小访问范围 |
| 切为主管 D | D/E/F/G/H/I，共 6 人 | 直属和间接下属；汇报线可以跨部门 |
| 叠加可信与AI实验室筛选 | D/E/F/G，共 4 人 | 部门筛选与授权范围取交集 |
| 切为 HRBP C | C/D/E/F/G/J，共 6 人 | 按 HRBP 服务关系授权 |
| 单人核验 C → K | 拒绝 | 看到服务主管 J，不会自动看到 J 的下属 K |
| 切为 HR 负责人 B | B/C/D/E/F/G/J，共 7 人 | 继承下属 HRBP 的服务对象 |
| 关闭 HR 负责人角色“继承 HRBP”，发布 | B 只见 B/C，共 2 人 | 通过配置改变权限 |
| 恢复初始样本，模型改为“管理线：仅直属”，发布 | D 只见 D/E/F/H，共 4 人 | 修改框架声明式规则，无需写遍历算法 |
| 恢复，D 岗位改为员工，发布 | D 只见本人 | 岗位到角色的配置映射 |
| 恢复，G 的主管从 F 改为 H，发布 | F 不再见 G；H 可见 G | 人员关系变更后的重新求权 |
| 恢复，D 设为离职，发布 | D 可见 0 人 | 在职资格控制；其他主管仍可能查看 D 的历史人员行 |
| 切为 D 查看模拟薪资、尝试导出 | 薪资不返回；导出拒绝 | 行范围、敏感字段、操作权限分别求交集 |
| 切为 B | 可见范围内的模拟薪资与导出可用 | 这是演示假设，不是企业实际薪酬制度 |

页面有“5 分钟演示步骤”，不用记住所有操作。任意配置可通过发布历史恢复；恢复生成一个新版本。结束时恢复初始样本，便于下一次从确定状态开始。

## 讲清楚：框架做什么，我们做什么

| 层次 | 文件/组件 | 职责 |
|---|---|---|
| 人员事实与角色配置 | `fixtures.json`、页面配置 | 人员、岗位、主管、HRBP、在职状态、岗位角色映射、角色能力开关 |
| 权限规则 | `model.fga` | 使用 OpenFGA 官方 DSL 表达管理线递归、服务关系、继承、交并集 |
| 语法解析 | 官方 fga CLI | 将 DSL 转为官方模型 JSON |
| 权限判断 | 真正运行的 OpenFGA Server | 接收模型和关系元组；执行 BatchCheck，给出 allowed 判断 |
| 集成与执行 | `core.py`、`server.py` | 校验事实、映射直接关系、调用框架、按结果过滤行和字段、限制导出 |
| 演示界面 | `static/` | 身份模拟、配置编辑、结果和真实请求响应展示 |

应用没有使用递归 SQL 或 Python 下属遍历来计算可见集合。`Configuration.validate_facts` 中遍历管理链只检查输入是否成环，不计算授权。`build_tuples` 只映射输入的直接关系与角色能力，不预先展开管理后代。

岗位映射当前是可配置的 `job_roles` 字典，不宣称具备完整 IGA 产品的属性规则编辑器。业务侧负责选择岗位、人员关系与开关；新增权限语义时由技术人员修改框架模型、补充业务期望测试。

## 模型如何阅读

```text
employee:G --manager--> employee:F --manager--> employee:D
employee:G --hrbp--> employee:C --manager--> employee:B
```

`employee:G` 是受保护的员工资源，`user:G` 是申请访问的人，两者由 `owner` 关系关联。

核心规则：

```text
define direct_manager: owner from manager
define management_chain: direct_manager or management_chain from manager
define direct_hrbp: owner from hrbp
define inherited_hrbp: management_chain from hrbp
```

第一条取直属主管所对应的用户；第二条递归取主管的主管；第三条只取直接 HRBP；第四条取该 HRBP 的管理上级。只有 `manager` 关系参加管理链递归，不能把所有可见关系都放到同一条递归链中。

`report_grant` 再与角色的管理权限开关取交集。`candidate` 合并本人、管理授权、HRBP 和继承授权；`view_basic` 还要求访问者在职；`view_private` 和 `can_export` 各自再检查字段或导出能力。

本演示的“管理线”“直接 HRBP”“继承 HRBP”是三个独立角色开关。继承 HRBP 根据真实管理关系判断，不要求同时打开“查看管理线”开关。这一点是明确的演示口径，可通过 DSL 调整。

## 配置发布与结果可信度

1. 检查人员 ID 唯一、引用存在、管理关系无环、岗位和角色映射完整。
2. 官方 CLI 解析 DSL；OpenFGA 校验模型与关系元组。
3. 在新的 OpenFGA Store 中写入模型和直接关系。旧配置继续服务。
4. 对全样本“每个查看人 × 每个目标 × 三个权限动作”做执行检查，有错误就拒绝发布。
5. 原子替换当前配置指针，使业务数据与模型、关系快照成套生效；旧版本用于回看和恢复。

执行检查只能证明模型能运行，不能证明业务规则正确。自动回归另用人工明确的预期 ID 集合验证授权和拒绝。

每次查询对全部样本做 BatchCheck，批次最多 50 项，使用明确模型 ID 和 `HIGHER_CONSISTENCY`。每个响应必须包含完整的布尔判断，任何缺失或引擎故障都导致整个查询失败。没有自写算法兜底，不把框架失败伪装成“0 人”。

页面上每个“授权来源”由对应关系的框架判断得出；它不是从人员名称推测的解释。调试区保留真实 HTTP 路径、输入、输出与耗时。导出重新执行当前权限检查，未经允许的模拟薪资不写入 CSV。

## 测试与范围

`test_lab.py` 连接真实引擎，每轮使用独立 Store 和临时目录，结束删除测试 Store，不改变页面的演示配置。覆盖全样本身份、跨部门交集、HRBP 不串权、字段与导出、模型切换、调岗、汇报与服务关系转移、离职、新员工、恢复版本、并发旧版本发布、非法关系、无效模型及引擎故障。故障注入项用于验证适配层拒绝不完整结果。

GitHub 工作流 `.github/workflows/openfga-lab.yml` 使用同样的固定版本及测试。它独立于原 HR 问数系统的回归。

2026-09-16 本地真实引擎回归：**48 项通过**，见 [逐项结果与源码哈希](../../reports/openfga-permissions-local.json)。浏览器实际切换身份、关闭继承并发布、修改 DSL 为仅直属并发布，结果分别符合 1/6/7 人、7→2 人、6→4 人，见 [浏览器记录](../../reports/openfga-ui-smoke.json)。此外通过 Python 静态检查、前端 lint 和项目类型检查。测试含一条第三方 Starlette/AnyIO 弃用提示，无测试失败。

这是最多 50 人的可复现框架学习与演示环境。没有接企业认证、权限配置审批、HR 主数据同步、多租户隔离或大规模 SQL 聚合。管理员页面和调试接口可以查看全部合成事实；身份选择器仅模拟业务查看人，不能作为真实用户认证使用。主 HR 问数系统与 Superset PoC 没有切换到这套引擎。

生产阶段需另行解决可信身份、管理面权限、配置审核、增量同步、撤权时限、数据库执行边界和规模性能。为演示隔离而每次发布一个 Store 的方式，不是生产推荐的增量更新策略；恢复旧版本可能恢复旧授权，也必须由受控管理员审批。

## 可复用资产与讲解措辞

可复用的是：关系建模、角色能力模型、框架调用适配、权限反例测试，以及配置变更验证方法。模拟人员、界面和示例薪酬口径可随真实业务替换。

建议现场表述：**“我们已使用成熟的 OpenFGA 引擎跑通汇报线及 HRBP 权限配置，并用明确的正反例验证了演示规则。后续可以沿用同样的方法增加规则；正式接入需要确认业务口径与系统边界。”**

不要把“采用成熟框架”描述成“整个企业权限已经获得安全认证”或“任何新规则都无需开发和验证”。

官方参考：

- [OpenFGA 项目与 CNCF 孵化](https://www.cncf.io/blog/2025/11/11/openfga-becomes-a-cncf-incubating-project/)
- [模型设计原则](https://openfga.dev/docs/best-practices/modeling-design-principles)
- [官方 CLI](https://openfga.dev/docs/getting-started/cli)
- [关系查询 API](https://openfga.dev/docs/interacting/relationship-queries)
- [大规模权限搜索的取舍](https://openfga.dev/docs/interacting/search-with-permissions)
