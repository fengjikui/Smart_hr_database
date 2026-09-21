"""使用 OpenFGA 官方 DSL 转换器生成 API JSON；服务端再次验证模型。

model.fga 是唯一模型源码，不维护手写 JSON 副本。未知或无效 DSL 直接停止
发布。调用 Node 是因为本项目已使用 Node，转换器作为固定版本依赖安装。
"""

import json
import subprocess
from pathlib import Path


def compile_model(text=None):
    root = Path(__file__).resolve().parent
    process = subprocess.run(
        ["node", str(root / "transform.mjs")],
        input=text if text is not None else (root / "model.fga").read_text(),
        text=True,
        capture_output=True,
        timeout=15,
    )
    if process.returncode:
        raise ValueError("OpenFGA DSL 转换失败，请检查 model.fga：" + process.stderr[-1200:])
    return json.loads(process.stdout)
