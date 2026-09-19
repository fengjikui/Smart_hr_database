# Superset 权限验证实验

完整 V2 的 300 人迁移和 Agent 接入已独立放在 `v2/`，见 [逐步实施讲义](../../docs/V2_SUPERSET_IMPLEMENTATION_GUIDE.md)。原 12 人实验和课堂继续保留。

希望亲手填写配置，请从 [Superset 权限实操课](../../docs/SUPERSET_HANDS_ON_CLASSROOM.md) 开始。课堂代码在 `classroom/`，使用独立 `LEARN_*` 对象，准备后业务角色为空，规则留给学习者填写。

固定 Apache Superset 6.1.0、PostgreSQL 17.11。独立于现有3000/8000端口的HR演示。只使用12名明确标记的合成人员，不读取`infomations/`或真实业务数据库。

研究结论和OA接入设计见[集成调研](../../docs/SUPERSET_INTEGRATION_RESEARCH.md)。

## 启动

本机使用Colima的独立`hr-superset`环境。首次需要Docker CLI、Docker Compose和Colima；服务默认仅绑定本机。

```bash
# 在电脑负载、内存、系统热状态合适时启动；首次拉取镜像需要网络。
colima start --profile hr-superset --cpus 2 --memory 4 --disk 20 --vm-type vz --mount-type virtiofs --activate=false
bash integrations/superset/lab.sh up
bash integrations/superset/lab.sh status
bash integrations/superset/lab.sh validate
```

- Superset：`http://127.0.0.1:8088`。
- 人员看板：`http://127.0.0.1:8088/superset/dashboard/hr-permission-lab/`；分别用员工和HR主管账号打开同一地址，观察人员集合变化。
- 敏感字段看板：`http://127.0.0.1:8088/superset/dashboard/hr-private-lab/`；普通员工没有对应数据集权限。
- PostgreSQL：`127.0.0.1:55432`；业务库`hr_lab`、Superset元数据库`superset_meta`。
- 本地生成的登录信息：`.local/credentials.json`；操作系统文件权限600，未提交Git。
- 管理账号`lab_admin`用于查看/维护配置；它没有业务人员映射，不作为Agent查询账号。
- 如使用自己的Docker环境，给脚本设置`HR_LAB_DOCKER_HOST`。脚本不切换全局Docker context。
- 构建时若需要使用已有代理，可显式设置`HR_LAB_BUILD_PROXY`。本机首次构建使用`HR_LAB_BUILD_NETWORK=host HR_LAB_BUILD_PROXY=http://host.lima.internal:7890 bash integrations/superset/lab.sh up`，其中host网络仅用于虚拟机内的镜像构建，运行中的Superset/PostgreSQL仍使用Compose隔离网络与本机端口绑定。不修改系统代理。没有该代理时不要照抄地址。
- 停止容器：`bash integrations/superset/lab.sh stop`。再按需执行`colima stop --profile hr-superset`。不要用删除卷作为常规停止方式。

## 演示账号与人工预期

| 用户 | 角色 | 可见人员ID | 特别观察 |
| --- | --- | --- | --- |
| lab_ceo | 集团主管 | A B C D E F G H I J K X | 管理线全部层级 |
| lab_hr_lead | HR主管 | B C D E F G J | 继承下属C的HRBP服务范围 |
| lab_hrbp | HRBP | C D E F G J | 直接服务范围；不是全公司 |
| lab_manager | 部门主管 | D E F G H I | 包括跨部门的间接下属 |
| lab_employee | 员工 | E | 仅本人；不能读薪资 |
| lab_unmapped | 未映射用户 | 无 | 缺少身份映射时默认拒绝数据 |
| lab_sql_tester | 专门的边界探针 | 正常数据集仅E | 多授予SQL Lab和公共连接权限，专用于暴露未登记视图的边界 |

前两个HR账号可读敏感数据集，其余普通业务角色只可读公共数据集。薪资授权仅是实验假设，不代表公司的正式薪酬权限政策。`lab_sql_tester`是刻意增加权限的测试身份，不能照搬到生产。J由C服务，但J的下属K由X服务，所以K不因J的关系进入C或B的服务范围。

## 配置在哪里

| 内容 | 位置 |
| --- | --- |
| 用户、业务角色开关、人员关系、人工预期集合 | `fixtures.json` |
| 管理线递归、授权来源并集、环检查 | `schema.sql` |
| Superset用户ID到HR person_id映射 | PostgreSQL `authz.identity_map` |
| 是否展开管理/HRBP/继承 | PostgreSQL `authz.role_policy` |
| 最终可见关系 | PostgreSQL `authz.visible_people` |
| 公共/敏感列边界 | PostgreSQL `analytics.people_public`、`analytics.people_private`及两个不同只读账号 |
| 用户与角色、数据连接、数据集、Base RLS | `bootstrap.py`生成后持久化在Superset元数据库，可以在Superset管理页面查看 |
| 功能开关与缓存 | `superset_config.py` |
| 真正接口验证 | `validate.py`，结果保存`.local/validation.json` |

Superset管理页面里，检查Security下的角色和Row Level Security；在Datasets里查看两个数据集。业务角色应保留Gamma作为功能基础，只添加对应的数据集访问权，不能直接改Superset内置角色。

配置生效方式有区别：`authz.role_policy`的管理线、HRBP和继承开关在查询时读取，修改后对下一次查询生效。`private_fields`是初始化时给Superset用户分配敏感数据集角色的依据，修改该字段本身不会即时撤销Superset中的既有角色；必须同步发布角色变更。生产系统应由一条受审计的发布流程统一维护这两处，不能让它们各自成为独立的权限事实来源。新增一种关系继承算法仍需要评审并修改SQL视图，不能理解为所有新规则都无须开发。

本实验的行范围映射是“一位用户对应一种业务策略”，Superset功能与数据集许可则组合多个角色。若同一人未来同时拥有多种独立业务身份，需要把授权映射扩展为多对多，并明确人员并集、字段许可与禁止规则的优先级；不能声称这份小样例已经实现所有多角色组合。

## 验证范围与限制

验证脚本读取真实REST API，不Mock Superset。覆盖各身份精确人员集合、受限字段、行过滤后的聚合、撤权与恢复、管理环、SQL Lab普通角色禁止执行，以及“已注册/未注册视图”反例。脚本只修改实验自己的关系/政策行，使用finally恢复；失败会抛错，不写出假成功报告。

目前配置关闭查询结果缓存，以免把旧授权结果带入撤权实验。生产时需要身份、授权版本与缓存失效机制的联合设计。

该实验不修改Superset源码，也不把Superset包装成数据库原生RLS。数据库本身在这里实施列/表访问边界；用户人员范围在Superset的数据集RLS中执行。拥有公共连接自由SQL权限的人，可能从未登记视图读到12人，这是测试需要证明的边界，不是验收后应该忽略的风险。

2026-09-15已完成本机ARM64部署及27项接口验收，Superset/PostgreSQL均健康；同一套测试也在GitHub CI通过。浏览器已实际登录员工和HR主管，确认分别显示1条和7条记录。[本机记录](../../reports/superset-permissions-local.json)、[CI记录](../../reports/superset-permissions-ci.json)、[页面记录](../../reports/superset-ui-smoke.json)。

已知接入行为：被禁止的自定义指标子查询在6.1.0返回HTTP 500，而不是统一的4xx业务错误。验证脚本同时检查拒绝原因和无结果，不能将任意500算作权限检查通过。REST客户端声明`Accept: application/json`，上层需要统一错误处理。界面使用官方菜单，显式登记en/zh以避免locale不在语言表中引起空白页；没有中文翻译资源时回退英文。

本实验不宣称完成OA真实登录、MCP传输鉴权、与现有LangGraph执行器切换或生产性能测试。
