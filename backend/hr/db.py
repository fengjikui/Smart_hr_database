import sqlite3
from contextlib import contextmanager
from pathlib import Path

from . import config


@contextmanager
def business(path: Path | None = None):
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
