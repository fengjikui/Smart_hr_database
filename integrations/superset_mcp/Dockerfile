FROM apache/superset:6.1.0
USER root
# 官方镜像包含 MCP 源码，但未装运行依赖；固定版本，绝不修改课堂容器。
# 仅一个构建步骤，uv 的下载/安装并发由环境限制。
ENV UV_CONCURRENT_DOWNLOADS=2 UV_CONCURRENT_INSTALLS=1 UV_CONCURRENT_BUILDS=1
COPY constraints.txt /tmp/mcp-constraints.txt
RUN uv pip install --constraint /tmp/mcp-constraints.txt --python /app/.venv/bin/python psycopg2-binary==2.9.11 fastmcp==3.1.0
USER superset
