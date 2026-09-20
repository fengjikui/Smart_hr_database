"""验证目录迁移保留对话历史、私有文件权限，且重复运行不会覆盖新数据。"""

import sqlite3

from scripts.migrate_local_state import migrate


def test_migration_preserves_history_and_is_idempotent(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    with sqlite3.connect(data / "v2_app.sqlite") as db:
        db.execute("CREATE TABLE runs(id TEXT, payload TEXT)")
        db.execute("INSERT INTO runs VALUES ('saved', 'history')")
    local = tmp_path / "integrations/superset/.local/v2"
    local.mkdir(parents=True)
    (local / "credentials.json").write_text('{"test": "local-only"}')
    assert migrate(tmp_path) == ["sessions.sqlite", "superset/application"]
    target = data / "sessions.sqlite"
    with sqlite3.connect(target) as db:
        assert db.execute("SELECT * FROM runs").fetchall() == [("saved", "history")]
        db.execute("INSERT INTO runs VALUES ('new', 'after migration')")
    credentials = local.parent / "application/credentials.json"
    assert credentials.read_bytes() == (local / "credentials.json").read_bytes()
    assert credentials.stat().st_mode & 0o777 == 0o600
    assert migrate(tmp_path) == []
    with sqlite3.connect(target) as db:
        assert db.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 2
    assert (data / "v2_app.sqlite").exists()


def test_empty_install_needs_no_migration(tmp_path):
    assert migrate(tmp_path) == []
