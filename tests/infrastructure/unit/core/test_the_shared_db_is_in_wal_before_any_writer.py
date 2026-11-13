"""The shared `zaelar.db` is put in WAL once, on the main thread, before any writer thread (2026-11-13).

Every opener asks for WAL on connect. On a NEW file, three connections switching it at the same moment fail at once
with «database is locked» — SQLite's busy timeout does not cover the journal switch (measured: 218 of 400 three-way
opens). It surfaced as a red in the setup of whichever test came second in a fresh process (the product's observer and
bus writers had just started), and the same race is a product's first boot on an empty disk. The class fix: the switch
happens once, before any thread — `nucleo/workspace.db_wal()` at boot, and the suite's own db in `conftest.py`.

Disarm (measured 2026-11-13): without `db_wal()` first, the three-way opens fail in most trials.
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from nucleo import workspace

ENGINE = Path(__file__).resolve().parents[4]


def _three_at_once(path: Path) -> int:
    """Three connections, released together, each asking for WAL as every opener does. Returns how many failed."""
    gate, failed = threading.Barrier(3), []

    def opener() -> None:
        gate.wait()
        try:
            c = sqlite3.connect(str(path), timeout=5.0, check_same_thread=False)
            c.execute("PRAGMA journal_mode=WAL")
            c.close()
        except sqlite3.OperationalError as e:
            failed.append(e)
    threads = [threading.Thread(target=opener) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return len(failed)


def test_after_the_boot_switch_three_openers_at_once_never_fail(tmp_path, monkeypatch):
    failures = 0
    for i in range(40):
        monkeypatch.setenv("ZAELAR_DB", str(tmp_path / f"fresh-{i}.db"))
        p = workspace.db_wal()
        assert sqlite3.connect(str(p)).execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        failures += _three_at_once(p)
    assert failures == 0, f"{failures} opens failed on a db already in WAL"


def test_the_switch_runs_before_any_writer_can_start():
    main = (ENGINE / "server" / "__main__.py").read_text(encoding="utf-8")
    assert main.index("_workspace.db_wal()") < main.index("from server import app"), \
        "the body switches the db before importing the app (which starts the writers)"
    harness = (ENGINE / "conftest.py").read_text(encoding="utf-8")
    assert harness.index('_wal.execute("PRAGMA journal_mode=WAL")') < harness.index("A PURGED MODULE TABLE"), \
        "the suite's db is switched where ZAELAR_DB is pinned, before any test runs"
