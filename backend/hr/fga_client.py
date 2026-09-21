"""OpenFGA REST 客户端：固定模型、强一致读偏好、逐项完整性检查。

不使用有数量/时间上限的 ListObjects 当作完整名单。课堂数据集有明确的
人员 ID 全集，因此逐批 BatchCheck；任何缺项或单项错误都拒绝整个查询。
"""

from contextlib import contextmanager

import httpx
from fastapi import HTTPException


@contextmanager
def client(settings):
    with httpx.Client(
        base_url=settings["fga_url"],
        trust_env=False,
        timeout=20,
        headers={"Authorization": "Bearer " + settings["fga_key"]},
    ) as connection:
        yield connection


def post(connection, path, body):
    try:
        response = connection.post(path, json=body)
        response.raise_for_status()
        value = response.json()
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(503, "OpenFGA 不可用或拒绝请求，未回退到其他权限后端") from exc


def batch(connection, publication, user, pairs):
    """pairs 是 (relation, object) 列表；保留顺序且每个结果必须是布尔值。"""
    result = []
    for start in range(0, len(pairs), 50):
        section = pairs[start : start + 50]
        checks = [
            {"correlation_id": str(i), "tuple_key": {"user": user, "relation": relation, "object": obj}}
            for i, (relation, obj) in enumerate(section)
        ]
        data = post(
            connection,
            f"/stores/{publication['store_id']}/batch-check",
            {
                "authorization_model_id": publication["model_id"],
                "checks": checks,
                "consistency": "HIGHER_CONSISTENCY",
            },
        ).get("result")
        if not isinstance(data, dict) or set(data) != {str(i) for i in range(len(section))}:
            raise HTTPException(503, "OpenFGA 授权结果不完整，拒绝部分结果")
        for i in range(len(section)):
            item = data[str(i)]
            if not isinstance(item, dict) or item.get("error") or type(item.get("allowed")) is not bool:
                raise HTTPException(503, "OpenFGA 单项鉴权失败，拒绝部分结果")
            result.append(item["allowed"])
    return result
