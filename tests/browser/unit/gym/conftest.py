"""V2-900 — every gym test runs on its own store: never the operator's workouts."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _own_store(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    yield tmp_path
