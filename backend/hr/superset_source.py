"""当前 Superset 身份与授权数据入口。

模型和浏览器都不能传入 Superset 账号、数据库 ID 或访问令牌。
后端从已经验证的应用会话选择固定业务账号，通过 Chart Data API 查询。
这里没有 PostgreSQL 管理连接，也没有 SQLite 失败回退路径。
"""

import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path

import httpx
from fastapi import HTTPException

from . import config
from .schema import FIELDS

MAX_ROWS = 1000
MAX_EVENT_ROWS = 2 * MAX_ROWS
META_COLUMNS = ["_viewer_id", "_depth", "_reports", "_hrbp", "_inherited", "_origins"]


def enabled():
    """默认通过 Superset 查询；离线样本须显式设置 sqlite，拼写错误拒绝执行。"""
    backend = os.getenv("HR_QUERY_BACKEND", "superset")
    if backend not in {"sqlite", "superset", "superset_mcp", "openfga"}:
        raise HTTPException(503, "未知 查询后端；拒绝自动回退")
    return backend in {"superset", "superset_mcp"}


def local_dir():
    return Path(os.getenv("HR_SUPERSET_DIR", config.PROJECT / "integrations/superset/.local/application"))


def read_local(name):
    if (local_dir() / "manual-learning.json").exists():
        raise HTTPException(503, "正在手工重建 Superset，请按实操手册完成配置后再接入 Agent")
    try:
        return json.loads((local_dir() / name).read_text())
    except (OSError, ValueError) as exc:
        raise HTTPException(503, "当前 Superset 尚未准备完成，请先运行集成初始化") from exc


def manifest():
    # manifest 是部署/手工绑定生成的对象地址簿（账号、数据集 ID），不是授权结果。
    # 每次访问是否允许仍由 Superset 的当前配置与 PostgreSQL 视图决定。
    return read_local("manifest.json")


def identity(p):
    """交叉核对 persona、员工主键和业务角色；清单是后端受控映射，不是用户输入。"""
    # p 由服务端会话决定；禁止使用前端临时指定的用户名去获取别人的 token。
    subject = manifest().get("principals", {}).get(p["id"])
    if not subject or subject["person_id"] != p["person_id"] or subject["role"] != p["role"]:
        raise HTTPException(403, "当前身份没有匹配的 Superset 业务账号")
    if subject["username"] == "v2_setup_admin":
        raise HTTPException(403, "配置管理员不能作为 Agent 执行身份")
    return subject


def checked_response(response):
    """把上游拒绝/故障转换为安全的 API 错误；错误结果不能伪装成零行。"""
    if response.status_code in (401, 403):
        raise HTTPException(403, "Superset 拒绝当前身份访问；请检查用户与数据集权限")
    if response.status_code >= 400:
        # 不把连接串、上游堆栈或其他内部配置带到模型/浏览器。
        raise HTTPException(502, "Superset 查询失败，未回退到本地数据")
    try:
        return response.json()
    except ValueError as exc:
        raise HTTPException(502, "Superset 返回了无效响应") from exc


@contextmanager
def session(p):
    """每次服务端访问使用明确的业务身份；令牌只在本次 HTTP 会话内保存。"""
    subject = identity(p)
    credentials = read_local("credentials.json")
    password = credentials.get(subject["username"])
    if not isinstance(password, str):
        raise HTTPException(503, "缺少当前业务账号的本机凭据")
    url = os.getenv("HR_SUPERSET_URL", "http://127.0.0.1:8088").rstrip("/")
    try:
        with httpx.Client(base_url=url, trust_env=False, timeout=30) as client:
            # ① 用当前 persona 对应的业务账号登录，不能用技术管理员统一代查。
            # provider=db 表示本演示使用 Superset 本地账号，生产 SSO 需另行接入。
            login = checked_response(client.post("/api/v1/security/login", json={
                "username": subject["username"], "password": password, "provider": "db", "refresh": False,
            }))
            client.headers["Authorization"] = "Bearer " + login["access_token"]
            # ② Bearer token 表示身份；CSRF token 防护提交请求，二者职责不同。
            # 使用同一个客户端保留服务端会话 cookie，然后再提交 Chart Data POST。
            csrf = checked_response(client.get("/api/v1/security/csrf_token/"))
            client.headers["X-CSRFToken"] = csrf["result"]
            yield client
    except httpx.HTTPError as exc:
        raise HTTPException(503, "Superset 暂不可用，已停止查询；不会回退到 SQLite") from exc


def _chart(client, dataset_key, queries):
    """在已登录业务会话中查询固定数据集，检查每个 QueryObject 都返回成功结果。"""
    spec = manifest()["datasets"][dataset_key]
    # datasource 只包含已注册数据集 ID，模型不能换成任意数据库/临时 SQL。
    # force=True 要求重新取数，便于演示撤权效果；它本身不是权限检查开关。
    payload = {"datasource": {"id": spec["id"], "type": "table"}, "force": True,
               "result_format": "json", "result_type": "full", "queries": queries}
    # 此处是在线数据出口：Superset 验证数据集访问权、拼入当前用户 RLS，再
    # 使用数据集所绑定的 reader 连接发起 PostgreSQL 查询。上游失败就停止。
    response = checked_response(client.post("/api/v1/chart/data", json=payload))
    results = response.get("result")
    if not isinstance(results, list) or len(results) != len(queries):
        raise HTTPException(502, "Superset 查询结果结构不完整")
    for result in results:
        if result.get("error") or result.get("status") == "failed" or not isinstance(result.get("data"), list):
            raise HTTPException(502, "Superset 数据查询失败，不能将错误当作零行")
    return results


def chart(p, dataset_key, queries):
    """仅允许代码选择清单中的数据集。Superset 本身仍会校验其数据集权限。"""
    with session(p) as client:
        return _chart(client, dataset_key, queries)


def raw_query(columns, limit=MAX_ROWS):
    # raw 是“取明细、不做指标聚合”，不是允许提交 raw SQL；RLS 仍然生效。
    return {"columns": columns, "metrics": [], "filters": [], "row_limit": limit,
            "orderby": [], "extras": {}, "is_timeseries": False}


def counted_listing(client, dataset, columns, limit):
    """真实查询一个物理出口，同时证明它的访问权与结果完整性。

    不能只哈希 Superset 配置：角色、Base/Regular RLS 的组合可能分别作用在
    人员/事件出口。必须让同一个业务账号真正经过各出口的鉴权和 RLS。
    """
    counter = raw_query([])
    # 总数与明细都由同一登录会话查同一数据集；不能只拿前 1000 行就当全量。
    # 两个 QueryObject 不承诺同一事务快照，数量不一致时拒绝，外层另做指纹检查。
    counter["metrics"] = [{"expressionType": "SQL", "sqlExpression": "COUNT(*)", "label": "n"}]
    counts, listing = _chart(client, dataset, [counter, raw_query(columns, limit)])
    if len(counts["data"]) != 1:
        raise HTTPException(502, "Superset 未返回唯一的授权数量，拒绝不完整的权限快照")
    total = counts["data"][0].get("n")
    if type(total) is not int or total < 0:
        raise HTTPException(502, "Superset 返回了无效的授权数量")
    rows = listing["data"]
    if total > limit or len(rows) != total:
        raise HTTPException(413, "授权快照超过演示限额或返回不完整，拒绝按截断数据统计")
    return rows, listing.get("query")


def checked_scope(rows, subject, event=False):
    """只保留稳定、最小的授权键，避免额外披露业务字段。

    事件由 person_id + 日期 + 入/离职标记识别，同一人同日入离职也不会合并。
    数据顺序不是权限变化，排序之后再纳入指纹。
    """
    columns = ["person_id", "_viewer_id"]
    if event:
        columns += ["event_day", "is_hire", "is_exit"]
    if any(not isinstance(row, dict) or not set(columns) <= row.keys() for row in rows):
        raise HTTPException(502, "Superset 授权出口缺少完整的人员/事件标识")
    if any(row["_viewer_id"] != subject["user_id"] for row in rows):
        raise HTTPException(403, "数据集身份隔离异常，请检查 Superset Base RLS")
    if any(not isinstance(row["person_id"], str) for row in rows):
        raise HTTPException(502, "Superset 授权出口的人员标识无效")
    if event and any(not isinstance(row["event_day"], str)
                     or (row["is_hire"], row["is_exit"]) not in ((1, 0), (0, 1)) for row in rows):
        raise HTTPException(502, "Superset 授权出口的事件标识无效")
    values = sorted(tuple(row[column] for column in columns) for row in rows)
    if len(set(values)) != len(values):
        raise HTTPException(409, "授权数据出现重复人员或事件，已停止统计")
    return {"columns": columns, "rows": values}


def snapshot(p, refresh=False):
    """读取本用户已授权的数据快照，供目录/关系/核验与撤权指纹使用。

    只在这一个请求的 principal 字典里复用；fingerprint(refresh=True) 会再查服务端。
    快照不承担最终查询授权，实际业务查询仍再次交给 Superset 执行 RLS。
    """
    if not refresh and p.get("_superset_snapshot") is not None:
        return p["_superset_snapshot"]
    subject = identity(p)
    # MCP 是显式实验路径；刷新权限时重新读取目录，撤销目录权限/服务断开即失败关闭。
    from . import superset_mcp
    mcp_catalog = superset_mcp.catalog(p) if superset_mcp.enabled() else None
    with session(p) as client:
        # ① 先通过 context 的 RLS 读本人策略，再决定人员出口与所需字段。
        # 要求恰好一行：零行可能未映射，多行可能配置错误，均不能猜测身份。
        context_columns = ["superset_user_id", "persona_id", "person_id", "role_key", "policy_version",
                           "rules_json", "as_of", "data_fingerprint", "graph_valid"]
        contexts = _chart(client, "context", [raw_query(context_columns, 2)])[0]
        if len(contexts["data"]) != 1:
            raise HTTPException(403, "Superset 身份映射缺失或不唯一，默认拒绝")
        context = contexts["data"][0]
        if (context["superset_user_id"] != subject["user_id"] or context["persona_id"] != p["id"]
                or context["person_id"] != p["person_id"] or context["role_key"] != p["role"]):
            raise HTTPException(403, "Superset 身份映射与当前会话不一致")
        if not context["graph_valid"]:
            raise HTTPException(409, "PostgreSQL 人员关系存在环或无效引用，已拒绝查询")
        from . import store

        if context["as_of"] != store.AS_OF:
            raise HTTPException(409, "语义快照日与 PostgreSQL 数据版本不一致")
        rules = json.loads(context["rules_json"]) if isinstance(context["rules_json"], str) else context["rules_json"]
        fields = {name for name, info in FIELDS.items() if info[1] in rules["field_groups"]}
        dataset = "people_contract" if "contract" in rules["field_groups"] else "people_public"
        columns = [f for f in FIELDS if f in fields] + META_COLUMNS
        # ② 读取已经过 RLS 的有限规模快照，供词汇候选、关系解释与核验使用。
        # 当前实现有意限制规模；未来扩大到全公司需分页/授权版本机制等优化。
        rows, listing_sql = counted_listing(client, dataset, columns, MAX_ROWS)
        scopes = {dataset: checked_scope(rows, subject)}
        source_queries = [contexts.get("query"), listing_sql]
        # 不能只查看合同人员快照：HR 的普通统计仍走 public，而入离职组合走
        # events。任何一个出口收窄或撤权，都必须使旧历史/调试/追问失效。
        # 这里只检查字段策略需要的出口；不尝试访问员工没有授权的合同出口。
        datasets = ["people_public", "events_public"]
        if "contract" in rules["field_groups"]:
            datasets += ["people_contract", "events_contract"]
        for key in datasets:
            if key == dataset:
                continue
            event = key.startswith("events_")
            keys = ["person_id", "_viewer_id"] + (["event_day", "is_hire", "is_exit"] if event else [])
            permission_rows, permission_sql = counted_listing(
                client, key, keys, MAX_EVENT_ROWS if event else MAX_ROWS)
            scopes[key] = checked_scope(permission_rows, subject, event)
            source_queries.append(permission_sql)
        # 清单中的实际数据集 ID 也属于身份边界，切换到另一个出口不可复用历史。
        for key, scope in scopes.items():
            scope["dataset_id"] = manifest()["datasets"][key]["id"]
    # ③ 将视图的授权列整理成上层 auth 统一格式；不在 Python 再遍历全公司授权。
    rows.sort(key=lambda row: row["person_id"])
    origins = {}
    for row in rows:
        value = row["_origins"]
        origins[row["person_id"]] = json.loads(value) if isinstance(value, str) else value
    grant = {"ids": [row["person_id"] for row in rows],
             "depths": {r["person_id"]: r["_depth"] for r in rows if r["_depth"] is not None},
             "reports": [r["person_id"] for r in rows if r["_reports"]],
             "hrbp": [r["person_id"] for r in rows if r["_hrbp"]],
             "inherited_hrbp": [r["person_id"] for r in rows if r["_inherited"]],
             "origins": origins, "policy_version": context["policy_version"]}
    # 指纹刻意不包含 SQL 文本或返回顺序，而使用真实授权内容与出口 ID。
    # 这不是生产级全库版本号；本机样本通过重复真实查询换取可直观看到的即时撤权。
    boundary = {"backend": "superset", "subject": subject,
                "context": context, "rows": rows, "query_scopes": scopes}
    if mcp_catalog is not None:
        boundary["mcp_catalog"] = mcp_catalog
    fingerprint = hashlib.sha256(json.dumps(boundary,
        sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    result = {"context": context, "rows": rows, "grant": grant, "rules": rules, "fields": fields,
              "fingerprint": fingerprint, "source_queries": source_queries, "mcp_catalog": mcp_catalog, "query_scopes": scopes}
    p["_superset_snapshot"] = result
    return result
