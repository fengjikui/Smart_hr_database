# Superset 接入

当前平台的安装、数据导入、用户/角色/RLS 配置与 Agent 接入，统一见 [实施讲义](../../docs/SUPERSET_SETUP.md)。

在仓库根目录执行 `npm run superset:up` 启动平台并初始化当前数据；已有平台只需 `npm run superset:setup`。
`npm run superset:status` 只读盘点。配置与凭据保存在本机 `.local/application/`，不进入 Git。
