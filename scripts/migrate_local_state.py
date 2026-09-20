"""目录整理后的本机状态迁移：复制历史与样本，不覆盖已有目标，不修改权限。

先停止应用再运行。SQLite 使用 backup API 读取完整事务快照；旧文件保留，
可用于回滚。Superset 仅复制本机清单和凭据，不连接或改写数据库/平台配置。
"""

import json
import os
import shutil
import sqlite3
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]


def migrate(project=PROJECT, data_dir=None):
    data = Path(data_dir) if data_dir is not None else project / "data"
    migrated = []
    for old, new in [("v2_people.sqlite", "people.sqlite"), ("v2_app.sqlite", "sessions.sqlite")]:
        source, target = data / old, data / new
        if not source.exists() or target.exists():
            continue
        staging = target.with_suffix(".migration.tmp")
        try:
            # 不直接复制可能启用了 WAL 的 SQLite 文件，避免漏掉尚未合并的事务。
            with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as before:
                with sqlite3.connect(staging) as after:
                    before.backup(after)
                    if after.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                        raise RuntimeError("迁移后的 SQLite 完整性检查失败")
            staging.chmod(0o600)
            staging.rename(target)
        finally:
            staging.unlink(missing_ok=True)
        migrated.append(new)

    local = project / "integrations/superset/.local"
    source, target = local / "v2", local / "application"
    if source.is_dir() and not target.exists():
        staging = local / ".application-migration"
        if staging.exists():
            raise RuntimeError("存在未完成的清单迁移，请先检查 .application-migration")
        try:
            # 复制整个清单目录以保留数据集 ID、业务用户 ID 和数据指纹。
            shutil.copytree(source, staging)
            staging.chmod(0o700)
            for path in staging.rglob("*"):
                path.chmod(0o700 if path.is_dir() else 0o600)
            staging.rename(target)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        migrated.append("superset/application")
    return migrated


if __name__ == "__main__":
    print(json.dumps({"migrated": migrate(data_dir=os.getenv("HR_DATA_DIR")),
                      "originals_preserved": True}, ensure_ascii=False))
