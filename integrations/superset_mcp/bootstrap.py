"""容器内仅初始化本实验：复用确定性建库逻辑，覆盖环境地址和保护标记位置。"""
import sys
from pathlib import Path

sys.path.insert(0, '/lab')
import setup  # noqa: E402
from initialization_guard import require_automatic_setup  # noqa: E402
from superset.app import create_app  # noqa: E402

# 此入口只由实验 Compose 执行；原 setup 的数据集/RLS/角色策略保持一致。
setup.LOCAL = Path('/mcp-lab/.local/application')
setup.BASE_URL = 'http://127.0.0.1:18088'
require_automatic_setup(setup.LOCAL, setup.read_fixture)
with create_app().app_context():
    setup.prepare_superset()
