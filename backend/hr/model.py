"""本机模型连接状态和单并发推理闸门；查询流程在 graph.py。"""

import asyncio

import httpx

from . import config

_gate = asyncio.Semaphore(1)


async def model_status():
    # 只读取 LM Studio 的已加载模型列表，不发起推理，不会修改模型加载状态。
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=3) as client:
            response = await client.get(f"{config.MODEL_URL}/models")
            response.raise_for_status()
            ids = [m["id"] for m in response.json().get("data", [])]
        return {
            "connected": config.MODEL_ID in ids,
            "model": config.MODEL_ID,
            "display_name": "Qwen3.8 · 27B",
            "provider": "LM Studio",
            "local": True,
            "message": "本地模型接口可用" if config.MODEL_ID in ids else "目标模型尚未加载",
        }
    except (httpx.HTTPError, ValueError, KeyError):
        return {
            "connected": False,
            "model": config.MODEL_ID,
            "display_name": "Qwen3.8 · 27B",
            "provider": "LM Studio",
            "local": True,
            "message": "LM Studio 服务未连接，请启动本地服务和模型。",
        }
