"""单元测试使用显式离线后端，防止意外访问本机 Superset 或真实权限配置。"""

import pytest


@pytest.fixture(autouse=True)
def offline_backend(monkeypatch):
    monkeypatch.setenv("HR_QUERY_BACKEND", "sqlite")
