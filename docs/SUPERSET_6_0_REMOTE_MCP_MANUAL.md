# Superset 6.0.0 远程服务器手动接入 MCP

本文面向：已有一台运行 Superset **6.0.0** 的 Linux 服务器，希望自己逐步安装、检查并接入 Agent。

**先确定版本边界：6.0.0 没有官方内置 MCP 服务。** 安装 `fastmcp`、添加 `MCP_*` 配置或者开放 5008 端口，都不会给该版本增加 `superset mcp run` 命令。官方 MCP scaffold 和 implementation 进入了 [6.1.0 变更记录](https://github.com/apache/superset/blob/6.1.0/CHANGELOG/6.1.0.md)。官网部分页面写的“Superset 5.0+”前置条件不能用来判断 6.0.0 安装包是否含有这个命令。

| 你的要求 | 可执行路线 |
|---|---|
| 保持现有 Superset 6.0.0 | 使用本文的独立 REST → MCP 适配服务；**自维护代码，不是 Apache 官方 Superset MCP** |
| 必须使用 Apache 官方 Superset MCP | 先升级到含该功能的版本；本文末尾说明升级边界，不能直接在 6.0.0 开启 |

本仓库此前的官方 MCP 实验使用 **6.1.0**，并加了每次调用绑定真实用户的部署适配层。其 172 个单测、185 项集成检查不能当作本文 6.0.0 路线的实测结果。

本文默认保留 6.0.0。操作采用独立 Python 虚拟环境和 **MCP stdio over SSH**：远程进程由 MCP 客户端按需启动，SSH 负责访问控制和传输加密。此路线不提供 `https://域名/mcp`，也不用开放 5008 端口。适用于能启动 `command/args` 的 MCP 客户端和你自己的 Agent；只接受公网 HTTP MCP 地址的客户端不能直接使用它。

## 1. 确认现状，只执行读取命令

先 SSH 登录服务器，后面标为“服务器”的命令都在这里执行。

```bash
ssh 你的Linux用户名@服务器地址
```

如果 Superset 在 Docker 里：

```bash
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}'
# 将下方容器名替换为上一条输出中的 Web 容器名。
docker exec 你的Superset容器名 python -c 'from importlib.metadata import version; print(version("apache-superset"))'
docker exec 你的Superset容器名 superset --help
```

如果 Superset 在虚拟环境里：

```bash
# 替换为现有 Superset 环境中的 Python / CLI 绝对路径。
/现有环境/bin/python -c 'from importlib.metadata import version; print(version("apache-superset"))'
/现有环境/bin/superset --help
```

预期：版本是 `6.0.0`，CLI 帮助没有 `mcp`。厂商二次打包或自行 backport 的安装包可能不同，以实际模块和命令为准。

确认服务器能够访问 Superset 的 HTTP 入口。例如 Web 已映射到本机 8088：

```bash
curl --fail --silent --show-error http://127.0.0.1:8088/health
```

预期：`OK`。如果没有本机映射，使用已有的 HTTPS 域名，例如 `https://bi.example.com/health`。不要为了本文改 Docker 端口或重建原有容器。服务器宿主机中的 `127.0.0.1` 指宿主机；容器内部的 `127.0.0.1` 才指该容器。

此兼容路线只调用 REST API，不访问 Superset 元数据库；不需要 `SQLALCHEMY_DATABASE_URI`、Web `SECRET_KEY`、数据库超级用户密码，也不执行 `superset db upgrade` 或 `superset init`。

## 2. 准备一个权限受限的 Superset 用户

在 Superset 管理页面完成以下操作，示例用户名为 `mcp_reader`：

1. 打开用户管理，新建一个专用于本次接入的用户，保存强密码。
2. 使用 `Gamma` 加一个自定义数据集角色，或沿用你已经验证过的只读业务角色。
3. 只给目标数据集的访问权限，以及本例 API 需要的 `can read on Dataset`、`can read on Chart`（界面显示形式可能略有差异）。
4. 不分配 Admin、Alpha、SQL Lab、全数据库或全数据源访问权限来排查问题。
5. 如需部门/员工行范围，给该用户的角色配置相应 RLS，并用该用户登录 Web 查看同一张图表。
6. 准备一张“小结果”已保存图表，查询行数在图表里限制为 100～500。记录一个允许访问的图表 ID，以及一个应当拒绝的图表 ID。后续测试要同时用到。

本例使用 `/api/v1/security/login` 的 `provider=db` 账号密码登录，适用于启用这类登录的实例。**如果当前是 OAuth/SSO-only 或仅 LDAP 登录，此段登录代码不是直接可用的方案；不要把全站 AUTH_TYPE 改成数据库登录。** 应使用你们现有的受信 API 登录/令牌获取方式改造 `login` 部分，再进行权限验收。

本例是**固定 Superset 身份**：能以该 Linux 账号启动适配服务的人，都使用 `mcp_reader` 的权限。它不会因为 Agent 对话中写了“我是张三”就切换身份，也不是企业多用户委托认证系统。不同权限范围应分别使用独立 Linux 账号/私有配置，或实现可信的逐用户身份传递。

参考：[Superset 6.0.0 权限说明](https://superset.apache.org/docs/6.0.0/security/)。

## 3. 建立独立目录和 Python 环境（服务器）

以下操作使用你自己的普通 Linux 账号，不使用 Superset 容器内的 Python 环境。

```bash
python3 --version
```

本例建议 Python 3.11 或 3.12；使用已安装且支持 MCP SDK 的 Python。Debian/Ubuntu 缺少 venv 时，可由管理员安装对应的 `python3-venv` 软件包。

```bash
umask 077
mkdir -p "$HOME/superset60-mcp"
chmod 700 "$HOME/superset60-mcp"
cd "$HOME/superset60-mcp"
python3 -m venv .venv
.venv/bin/python -m pip install 'mcp==1.26.0' 'httpx==0.28.1'
.venv/bin/python -m pip check
.venv/bin/python -m pip freeze > requirements.lock.txt
```

这里只安装独立适配器依赖，没有安装或升级 `apache-superset`。两项直接依赖固定版本，`requirements.lock.txt` 记录本次解析得到的全部版本。重新部署时使用这个文件；它不是跨操作系统通用的哈希锁文件。

## 4. 输入连接资料，生成私有配置（服务器）

在上一步目录执行。密码通过隐藏输入读取，不放进命令行、shell 历史或客户端配置。

```bash
.venv/bin/python - <<'PY'
import getpass
import json
import os
from pathlib import Path

path = Path('connection.json')
if path.exists():
    raise SystemExit('connection.json 已存在；请先人工核对，不自动覆盖。')
config = {
    'base_url': input('Superset URL [http://127.0.0.1:8088]: ').strip() or 'http://127.0.0.1:8088',
    'username': input('Superset 用户名 [mcp_reader]: ').strip() or 'mcp_reader',
    'password': getpass.getpass('Superset 密码（不显示）: '),
}
if not config['password']:
    raise SystemExit('密码不能为空')
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as stream:
    json.dump(config, stream)
print('已保存私有 connection.json；不输出密码。')
PY
```

`base_url` 填 Superset 的入口，不要填数据库地址，也不要加 `/api/v1`。带路径前缀的部署可以填 `https://example.com/superset`。跨主机地址使用 HTTPS；下面的代码只允许回环地址使用 HTTP。企业私有 CA 应安装到受信证书环境或显式配置 SSLContext，不能关闭证书验证。

## 5. 手工创建 MCP 适配代码（服务器）

完整复制下面代码块。代码仅暴露三个工具，不提供任意 URL、SQL、用户名或密码参数。

```bash
cat > server.py <<'PY'
"""Superset 6.0.0 REST 适配器；自维护示例，不是 Apache 官方 Superset MCP。"""
import json
import logging
import os
import stat
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

# stdio 的 stdout 专属于 MCP JSON-RPC；不要 print 启动提示或 HTTP 响应。
logging.getLogger('httpx').setLevel(logging.WARNING)
config_path = Path(__file__).resolve().with_name('connection.json')
info = config_path.stat()
if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
    raise RuntimeError('connection.json 必须由当前账号持有，权限设为 600')
config = json.loads(config_path.read_text())
base_url = config['base_url'].rstrip('/')
url = urlsplit(base_url)
if url.username or url.password or url.query or url.fragment or not url.hostname:
    raise RuntimeError('Superset URL 格式不正确')
if url.scheme != 'https' and not (
    url.scheme == 'http' and url.hostname in {'127.0.0.1', 'localhost', '::1'}
):
    raise RuntimeError('非回环地址必须使用 HTTPS')

mcp = FastMCP('Superset 6.0 REST adapter')
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False)
MAX_BYTES = 1024 * 1024


async def read_json(client, method, path, **kwargs):
    """流式限制响应大小；不将带 SQL/连接信息的服务端错误原文返给模型。"""
    async with client.stream(method, base_url + path, **kwargs) as response:
        if response.status_code == 202:
            raise RuntimeError('Superset 返回异步任务；本例未实现异步轮询')
        if response.status_code != 200:
            raise RuntimeError(f'Superset HTTP {response.status_code}；请核对账号和权限')
        body = bytearray()
        async for part in response.aiter_bytes():
            body.extend(part)
            if len(body) > MAX_BYTES:
                raise RuntimeError('响应超过 1 MiB；请缩小图表或分页')
        try:
            value = json.loads(body)
        except ValueError:
            raise RuntimeError('Superset 返回非 JSON；检查 URL/代理/登录方式') from None
        if not isinstance(value, dict):
            raise RuntimeError('Superset 返回格式不符合预期')
        return value


async def api_get(path, params=None):
    """每次调用重新登录，无共享 token/数据缓存；固定服务器配置中的身份。"""
    try:
        # 不接受代理环境注入；TLS 校验保持开启；不跟随到另一地址的重定向。
        async with httpx.AsyncClient(timeout=30, follow_redirects=False, trust_env=False) as client:
            login = await read_json(client, 'POST', '/api/v1/security/login', json={
                'username': config['username'], 'password': config['password'],
                'provider': 'db', 'refresh': False,
            })
            token = login.get('access_token')
            if not isinstance(token, str) or not token:
                raise RuntimeError('登录未返回 access_token')
            return await read_json(client, 'GET', path, params=params,
                                   headers={'Authorization': 'Bearer ' + token})
    except httpx.HTTPError:
        raise RuntimeError('Superset 网络/TLS/超时错误；检查服务地址和证书') from None


def page_query(page, page_size):
    if not 0 <= page <= 10000 or not 1 <= page_size <= 50:
        raise ValueError('page 必须为 0..10000，page_size 必须为 1..50')
    return {'q': f'(page:{page},page_size:{page_size})'}


@mcp.tool(annotations=READ_ONLY)
async def list_datasets(page: int = 0, page_size: int = 20) -> dict:
    """分页列出当前固定 Superset 用户有权发现的数据集；页码从 0 开始。"""
    data = await api_get('/api/v1/dataset/', page_query(page, page_size))
    fields = ('id', 'table_name', 'schema')
    return {'count': data.get('count'), 'page': page,
            'datasets': [{k: item.get(k) for k in fields} for item in data.get('result', [])]}


@mcp.tool(annotations=READ_ONLY)
async def list_charts(page: int = 0, page_size: int = 20) -> dict:
    """分页列出当前用户可发现的图表；发现图表不代表一定有权查询其数据源。"""
    data = await api_get('/api/v1/chart/', page_query(page, page_size))
    fields = ('id', 'slice_name', 'viz_type')
    return {'count': data.get('count'), 'page': page,
            'charts': [{k: item.get(k) for k in fields} for item in data.get('result', [])]}


@mcp.tool(annotations=READ_ONLY)
async def get_chart_data(chart_id: int) -> dict:
    """通过 Superset 查询已保存图表；每个结果最多展示 100 行，不代表业务总人数。"""
    if chart_id <= 0:
        raise ValueError('chart_id 必须为正整数')
    data = await api_get(f'/api/v1/chart/{chart_id}/data/',
                         {'format': 'json', 'type': 'full', 'force': 'true'})
    results = []
    for result in data.get('result', []):
        if result.get('error') or result.get('status') == 'failed':
            raise RuntimeError('图表查询失败；请在 Superset 中以同一用户检查')
        rows = result.get('data')
        if not isinstance(rows, list):
            raise RuntimeError('图表数据格式不符合预期')
        # 只返回列和数据；不把响应中的 SQL、堆栈、缓存键等额外内容交给模型。
        results.append({'columns': result.get('colnames', []), 'rows': rows[:100],
                        'returned_rows': min(len(rows), 100),
                        'adapter_truncated': len(rows) > 100})
    return {'chart_id': chart_id, 'results': results,
            'note': '图表自身可能有限行、过滤和聚合；returned_rows 不是业务总数。'}


if __name__ == '__main__':
    mcp.run(transport='stdio')
PY

.venv/bin/python -m py_compile server.py
```

预期：语法检查没有输出，也没有报错。

几点具体边界：

- 权限仍由 Superset 的 REST API 检查，适配器不直接连业务数据库，也不代替 RLS。
- 图表数据接口使用已保存的 query context；图表创建者应确保它适合当前账号、数据范围和查询成本。[6.0.0 官方接口源码](https://github.com/apache/superset/blob/6.0.0/superset/charts/data/api.py)
- `readOnlyHint` 是客户端提示，不是鉴权；实际限制来自仅注册以上三个只读业务工具，以及 Superset 账号权限。登录、审计日志和查询缓存仍可能写入系统状态。
- 100 行是适配器展示上限，1 MiB 是响应接收上限；都不能阻止上游先执行大查询。应在 Superset 中限制图表查询，先用小图验证。超大/复杂查询应结合平台查询超时、资源限制治理。
- 本例拒绝异步任务响应，没有绕过它改成 SQL Lab。开启 `GLOBAL_ASYNC_QUERIES` 的环境需要另实现受鉴权的任务轮询，或者先选择能同步返回的验证图表。

## 6. 创建启动入口（服务器）

```bash
cat > run.sh <<'SH'
#!/bin/sh
set -eu
cd "$(dirname "$0")"
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
exec ./.venv/bin/python ./server.py
SH
chmod 700 run.sh
```

可以执行 `./run.sh` 检查能否启动。它会等待读取 MCP 消息，终端不显示菜单属于正常情况；用 Ctrl+C 退出。**这不是完整连接测试**，下一步才会实际握手和调用工具。

不使用 `nohup`，不在 systemd 中后台启动 stdio 服务：该协议需要客户端持有进程的输入输出。客户端连接时启动进程，断开时关闭它。

## 7. 完整协议验证（服务器）

创建验证客户端，避免把只看到工具列表误当成取数成功：

```bash
cat > probe.py <<'PY'
import asyncio
import json
import sys
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    params = StdioServerParameters(command=str(Path(__file__).resolve().with_name('run.sh')))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            print('protocol:', init.protocolVersion)
            tools = await session.list_tools()
            print('tools:', [tool.name for tool in tools.tools])
            names = {tool.name for tool in tools.tools}
            assert names == {'list_datasets', 'list_charts', 'get_chart_data'}
            # 可以传入一个图表 ID；不传时只验证有权限的数据集目录。
            name = 'get_chart_data' if len(sys.argv) > 1 else 'list_datasets'
            args = {'chart_id': int(sys.argv[1])} if len(sys.argv) > 1 else {'page_size': 5}
            result = await session.call_tool(name, args)
            print(json.dumps(result.model_dump(mode='json'), ensure_ascii=False, indent=2))
            if result.isError:
                raise SystemExit(1)


asyncio.run(main())
PY

.venv/bin/python probe.py
```

预期输出：协商后的协议版本、三个工具名、该用户有权发现的数据集。空列表有可能只是未授权数据集，不能直接判断为程序损坏。

再取图表数据，将 `123` 换成你准备的**允许访问**的图表 ID：

```bash
.venv/bin/python probe.py 123
```

预期：`isError` 为 `false`，`results` 中有列名和实际数据。验证脚本会在当前终端展示业务数据，只在有权查看的终端执行，不把含敏感数据的输出贴到外部工单。

最后使用一个**禁止访问**的图表 ID，例如将 `456` 换成真实负例：

```bash
.venv/bin/python probe.py 456
```

预期：工具报错，常见 HTTP 403 或 404，退出码非零。不要为了让这一步“通过”把账号改成管理员。如果图表是公开数据源，或该用户因其他角色仍可访问，就不是有效的负例，需要先核对角色与数据集权限。

## 8. 在你自己的电脑上配置 SSH

此节在**你的电脑**执行，不在服务器执行。先用正常 SSH 登录确认服务器指纹，再配置密钥登录；不要关闭 host key 检查。

在 `~/.ssh/config` 添加一个独立别名，保留其他已有内容：

```sshconfig
Host superset-mcp-remote
    HostName 你的服务器IP或域名
    User 你的Linux用户名
    IdentityFile ~/.ssh/你的现有私钥文件
    IdentitiesOnly yes
    ServerAliveInterval 30
    ServerAliveCountMax 3
```

私钥有口令时先加入你已有的 ssh-agent。不要把私钥、Superset 密码或 REST token 放进模型消息。

检查无交互登录：

```bash
ssh -T -o BatchMode=yes superset-mcp-remote true
```

预期退出码 0。若有 shell 欢迎词出现在 stdout，应调整该账号的非交互 shell 初始化，让非交互会话不打印欢迎内容，否则会破坏 MCP stdio。不要给 SSH 加 `-t` 分配伪终端。

## 9. 配置 MCP 客户端 / Agent

对于支持标准 `mcpServers` + `command/args` 配置的客户端，增加以下条目；不要覆盖原来整个配置文件：

```json
{
  "mcpServers": {
    "superset60": {
      "command": "ssh",
      "args": [
        "-T",
        "-o", "BatchMode=yes",
        "superset-mcp-remote",
        "/home/你的Linux用户名/superset60-mcp/run.sh"
      ]
    }
  }
}
```

远程脚本路径要替换成步骤 3 的绝对路径，可在服务器目录执行 `pwd` 得到。建议目录名不含空格。Windows 本机需确保客户端能找到 OpenSSH `ssh.exe`；其他客户端如使用 TOML 或专用管理界面，要对应填写相同 command/args。

如果你自己的 Python Agent 使用官方 MCP SDK，连接部分为：

```python
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

params = StdioServerParameters(
    command="ssh",
    args=["-T", "-o", "BatchMode=yes", "superset-mcp-remote",
          "/home/你的Linux用户名/superset60-mcp/run.sh"],
)

# 放到 async 函数中，并在整个工具调用阶段保持两个上下文存活。
async def query_superset():
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            result = await session.call_tool("list_datasets", {"page_size": 5})
            return tools, result
```

后续将工具 schema 接入你现有 Agent 的工具选择逻辑。这里不需要给适配器配置大模型 API key。发现三个工具后，再让 Agent 查询允许的图表；如果 Agent 无法调用，先用第 7 步验证 Superset 侧，再排查客户端的 SSH 和 MCP 连接。

参考：[MCP Python SDK 1.26.0](https://github.com/modelcontextprotocol/python-sdk/blob/v1.26.0/README.md)。

## 10. 手工权限验收与日常维护

| 操作 | 应检查的结果 |
|---|---|
| 相同账号在 Web 和 MCP 查询同一图表 | 数据范围一致；考虑图表过滤、聚合和行限制 |
| 猜测其他图表 ID | 未获数据源权限时拒绝，不能返回越权数据 |
| 临时移除测试账号的数据集角色后再调用 | 新请求按最新角色拒绝；测试后只恢复你移除的测试配置 |
| 两个不同权限测试账号分别配置、分别启动 | RLS 结果应符合各自范围；不要同时改写同一个配置文件 |
| 停用测试账号或改密码 | 下一次需要重新登录的工具调用失败 |
| 指向不可达的 Superset（另建测试配置） | 工具失败，不切换管理员或绕过 Superset 直连数据库 |

测试权限撤销时使用专门测试账号，不修改现有课堂/生产用户。无法推断你远程实例的所有安全策略，因此这些检查必须在实际环境完成。

日常操作：

- 启动：客户端建立 MCP 连接时，通过 SSH 启动 `run.sh`。
- 停止：关闭该客户端的 MCP 连接。手动启动的终端用 Ctrl+C；不执行全局 `pkill python`。
- 改账号密码：人工修改私有 `connection.json`，保持权限 600；断开并重新连接，让新进程加载新配置。
- 升级适配器：先在另一个目录安装新依赖和验证，再切换客户端的脚本绝对路径；原 Superset 无需重启。
- 回退：删除客户端新增的 `superset60` 条目并断开连接；Superset 6.0.0 服务、元数据库和业务库都未因本路线升级或迁移。

## 11. 常见故障

| 现象 | 处理 |
|---|---|
| `No such command 'mcp'` | 6.0.0 的预期结果；运行本文 `run.sh`，不是 `superset mcp run` |
| `No module named mcp` | 确认启动入口用了新目录 `.venv/bin/python`，不是系统或 Superset 的 Python |
| HTTP 401 / 422 | 检查账号密码、是否启用 db 登录、SSO/WAF 和 token 策略；不打印 token |
| HTTP 403 / 404 | 先用同一 Superset 用户在 Web 验证数据集权限和图表可见性 |
| HTTP 400（图表调用） | 以有权编辑的账号重新打开并保存图表，确认有有效 query context；不要关闭 CSRF 或 RLS |
| HTTP 301 / 302 或非 JSON | 检查 HTTPS、路径前缀及代理，不盲目跟随到登录页 |
| HTTP 202 | 该实例返回异步任务，本例未实现轮询；不能把任务对象当查询结果 |
| 超过 1 MiB | 缩小图表结果或分页，不直接去掉限制 |
| MCP 握手失败 | 检查非交互 SSH 登录、远程绝对路径、shell stdout 欢迎词；确保没有分配 TTY |
| `Permission denied (publickey)` | 检查 SSH 用户、密钥、ssh-agent 和服务器授权；Superset 密码与 SSH 密钥是两回事 |
| 客户端只接受 URL | 该客户端不支持本 stdio 路线；需要额外的 HTTPS MCP 服务和鉴权设计 |

## 12. 如果你必须使用官方内置 MCP

需要先切换目标版本，不能保留官方原版 6.0.0 又直接启用内置 MCP。升级时执行的顺序应为：

1. 备份现有 Superset **元数据库**、部署配置、当前 `SECRET_KEY` 和自定义依赖，记录原镜像 digest/包版本；按你们的备份流程验证可恢复。
2. 将元数据库恢复到独立测试数据库，创建独立配置、缓存前缀/Redis 和服务端口。已有连接密文需要原 `SECRET_KEY` 才能解密；私密复制，不显示在终端或聊天中。测试环境禁用定时报表和外部通知，先连接测试业务库。
3. 安装固定的含 MCP 版本（本仓库验证基线为 6.1.0），保留业务驱动和自定义安全管理器的兼容依赖。
4. **只对升级测试副本**运行 `superset db upgrade` 和 `superset init`。6.1.0 有元数据库迁移，不让 6.0.0 Web 与 6.1.0 MCP 共用正在迁移的同一元数据库。
5. 在该版本环境确认 `superset mcp run --help` 存在，安装经兼容验证的 FastMCP 依赖，配置独立进程、认证、当前用户解析及最小权限。
6. 执行 JWT 正反例、真实工具调用、RLS、权限撤销等验收，再按维护窗口升级正式环境，或使用已隔离的升级环境进行评估。

官方入口形式是 `superset mcp run --host 127.0.0.1 --port 5008`，但命令存在不等于多用户鉴权正确。本仓库的 **6.1.0 + FastMCP 3.1.0** 实测曾遇到验签成功而工具没有绑定 Flask `g.user` 的问题，已在独立入口修复；不能只凭 `tools/list` 成功宣布可用于生产。

可查看：[本仓库 6.1.0 实验指南](SUPERSET_MCP_GUIDE.md)、[实际验证报告](SUPERSET_MCP_VALIDATION.md)、[Apache 6.1.0 官方部署文档](https://superset.apache.org/admin-docs/6.1.0/configuration/mcp-server/)、[官方升级说明](https://superset.apache.org/admin-docs/installation/upgrading-superset/)。

本文为手动操作文档，没有登录或修改你的远程服务器。已检查两个内嵌 Python 文件的语法，并将服务代码原样提取到临时目录，使用 MCP SDK 完成 initialize、tools/list、三个工具调用，以及非法分页/图表 ID、403、202、查询错误、超大响应、后续登录失败等 11 项模拟接口检查。测试临时进程和目录已清理。

这些检查只证明示例的协议与错误处理路径可运行，**没有在真实 Superset 6.0.0 实例上完成端到端测试**。你仍须按第 7、10 节完成远程实例的登录、取数和权限验证；原 6.1.0 实验结果不能替代这些验证。
