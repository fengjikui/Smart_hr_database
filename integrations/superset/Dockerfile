FROM apache/superset:6.1.0
# 固定平台版本保证教程界面/API 可复现；宿主机无需 pip 安装 Superset。
USER root
# 仅安装连接 PostgreSQL 的驱动；HR Agent 的 Python 依赖在项目自己的环境中。
RUN uv pip install --python /app/.venv/bin/python psycopg2-binary==2.9.11
# 安装完成后切回镜像自带非 root 账号运行服务。
USER superset
