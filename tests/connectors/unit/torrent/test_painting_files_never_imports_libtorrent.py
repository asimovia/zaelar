"""INI-042 #34 — painting Files asks «is the torrent client there?» without importing libtorrent on the caller.

`import libtorrent` costs ~2 s cold and Archivos asked on the engine's loop thread (2.2 s frozen, hosted account).
Now the answer before the real import is whether the wheel is INSTALLED (`find_spec`, nothing executed) and the
import runs in a background thread; once it has run, its result is the answer. Where the operator's switch is off
(a hosted account) the wheel is not even looked for.
"""
from __future__ import annotations

import sys
import threading

import pytest

from connectors.torrent import service, session


@pytest.fixture
def fresh(monkeypatch):
    for name, value in (("_lt_mod", None), ("_lt_tried", False), ("_lt_warming", None), ("_import_error", "")):
        monkeypatch.setattr(session, name, value)
    imported_on = []
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def watching(name, *a, **kw):
        if name == "libtorrent":
            imported_on.append(threading.current_thread() is threading.main_thread())
            raise ImportError("not in this test")       # never load the real wheel in a unit test
        return real_import(name, *a, **kw)

    monkeypatch.setattr("builtins.__import__", watching)
    monkeypatch.delitem(sys.modules, "libtorrent", raising=False)
    return imported_on


def test_an_installed_wheel_reads_available_without_importing_it_here(fresh, monkeypatch):
    monkeypatch.setattr("importlib.util.find_spec", lambda name, *a: object() if name == "libtorrent" else None)
    assert session.available() is True
    t = session._lt_warming
    assert t is not None and t.daemon
    t.join(5)
    assert fresh == [False]                         # imported once, and only off the caller's thread
    assert session.available() is False             # the real import's result answers from then on
    assert "not in this test" in session.import_error()


def test_a_missing_wheel_is_off_and_says_why_without_an_import(fresh, monkeypatch):
    monkeypatch.setattr("importlib.util.find_spec", lambda name, *a: None)
    assert session.available() is False
    assert "libtorrent" in session.import_error()
    assert fresh == [] and session._lt_warming is None


def test_a_switched_off_client_never_looks_for_the_wheel(monkeypatch):
    monkeypatch.setenv("ZAELAR_USER_ID", "u-test")
    monkeypatch.delenv("ZAELAR_TORRENT_IN_CLOUD", raising=False)
    monkeypatch.setattr(session, "available", lambda: pytest.fail("looked for the wheel with the client off"))
    assert service.available() is False
