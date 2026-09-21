# Superset 接入

从零手工学习见 [实操路线](../../docs/HANDS_ON.md) 与 [学习记录](../../docs/LEARNING_LOG.md)。有 `manual-learning.json` 标记时禁止自动初始化；需要恢复已有平台进程使用 `bash integrations/superset/services.sh resume`。

当前平台的安装、数据导入、用户/角色/RLS 配置与 Agent 接入，统一见 [实施讲义](../../docs/SUPERSET_SETUP.md)。

在仓库根目录执行 `npm run superset:up` 启动平台并初始化当前数据；已有平台只需 `npm run superset:setup`。
`npm run superset:status` 只读盘点。配置与凭据保存在本机 `.local/application/`，不进入 Git。

手工教程使用 `uv run python integrations/superset/learning.py prepare` 生成待执行材料，
`inventory` 只读真实 ID，`mapping` 生成待执行身份映射 SQL，`bind` 核对已配置对象并写 Agent 清单。
这些命令不运行自动初始化、不修改数据库或平台权限，也不解除学习标记。具体执行顺序见实操手册第 22～38 步。
