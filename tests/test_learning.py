"""手工教程生成器的关键边界：材料一致性、真实 ID 和 SQL 值转义。"""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def lesson(monkeypatch):
    # 加载材料生成器，测试临时目录/模拟 ID；不执行生成 SQL，不改课堂账号。
    monkeypatch.syspath_prepend(str(ROOT / "integrations/superset"))
    spec = importlib.util.spec_from_file_location("hr_learning", ROOT / "integrations/superset/learning.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_literals_keep_null_boolean_and_quotes(lesson):
    assert lesson.literal(None) == "NULL"
    assert lesson.literal(False) == "false"
    assert lesson.literal("O'Brien") == "'O''Brien'"
    assert lesson.literal("00031266") == "'00031266'"


def test_mapping_refuses_guessed_or_missing_user_id(lesson):
    fixture = {"personas": [{"id": "manager", "person_id": "P0004", "role": "manager"}]}
    with pytest.raises(ValueError, match="缺少业务用户"):
        lesson.mapping_sql(fixture, {"users": {}})
    with pytest.raises(ValueError, match="平台用户 ID 无效"):
        lesson.mapping_sql(fixture, {"users": {"v2_manager": {"id": "old-id"}}})
    text = lesson.mapping_sql(fixture, {"users": {"v2_manager": {"id": 87}}})
    assert "(87,'v2_manager','manager','P0004','manager')" in text
    assert "v2_setup_admin" not in text and "v2_unmapped" not in text


def test_fixture_tamper_rejected(lesson, tmp_path, monkeypatch):
    import json

    monkeypatch.setattr(lesson, "LOCAL", tmp_path)
    (tmp_path / "fixtures.json").write_text(json.dumps({"people": [], "data_fingerprint": "bad"}))
    with pytest.raises(ValueError, match="指纹不符"):
        lesson.load_fixture()


def test_private_sql_output(lesson, tmp_path, monkeypatch):
    monkeypatch.setattr(lesson, "OUTPUT", tmp_path / "private")
    path = lesson.write_sql("test.sql", "SELECT 1;")
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700


@pytest.mark.parametrize("flag,allowed", [(False, True), (True, False), (None, False), ("false", False)])
def test_container_guard_unreadable_private_directory(flag, allowed):
    from integrations.superset.initialization_guard import require_automatic_setup

    class PrivateDirectory:
        def __truediv__(self, name):
            return self

        def stat(self):
            raise PermissionError("private host directory")

    if allowed:
        require_automatic_setup(PrivateDirectory(), lambda: {"manual_learning": flag})
    else:
        with pytest.raises(SystemExit):
            require_automatic_setup(PrivateDirectory(), lambda: {"manual_learning": flag})


def test_visible_learning_marker_cannot_be_overridden(tmp_path):
    from integrations.superset.initialization_guard import require_automatic_setup

    (tmp_path / "manual-learning.json").write_text("{}")
    with pytest.raises(SystemExit):
        require_automatic_setup(tmp_path, lambda: {"manual_learning": False})
