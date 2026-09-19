# V1 的两个 SQLite 连接边界：业务事实只读，应用状态可写且有提交/回滚。
# 只读连接不是完整的用户授权；人员范围、表白名单还需 security.py/query.py 执行。
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from . import config


@contextmanager
def business(path: Path | None = None):
    # URI 的 mode=ro 与 query_only 双重限制写入；测试可传临时路径，不必碰演示库。
    connection = sqlite3.connect(f"file:{path or config.BUSINESS_DB}?mode=ro", uri=True, timeout=3)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        yield connection
    finally:
        connection.close()


@contextmanager
def application(path: Path | None = None):
    # 会话、指标发布、看板计划、审计和调试记录写入应用库，不与业务事实混放。
    connection = sqlite3.connect(path or config.APP_DB, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def rows(connection, sql, parameters=()):
    return [dict(row) for row in connection.execute(sql, parameters).fetchall()]
