"""容器跨 UID 的学习保护：不为了检查标记而放宽整个凭据目录权限。"""

import json


def require_automatic_setup(local, read_fixture):
    try:
        (local / "manual-learning.json").stat()
        blocked = True
    except FileNotFoundError:
        blocked = False
    except PermissionError:
        # Linux bind mount 保留宿主机 0700；容器只能读取独立挂载的合成样本。
        # 缺失/错误标志也拒绝，不能把“看不见目录”当作没有学习标记。
        try:
            blocked = read_fixture().get("manual_learning") is not False
        except (OSError, ValueError, TypeError):
            blocked = True
    if blocked:
        raise SystemExit("正在手工学习或无法确认初始化许可；请按 docs/HANDS_ON.md 操作。")


def stamp_fixture_guard(local):
    """重置之前同步阻止容器初始化；样本已单文件挂载，原位写入保持挂载有效。"""
    target = local / "fixtures.json"
    value = json.loads(target.read_text())
    value["manual_learning"] = True
    target.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
