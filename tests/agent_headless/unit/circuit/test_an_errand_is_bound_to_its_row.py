"""An errand is bound to its durable row: its brief, its judge and its relaunch never read another errand's (V2-868).

Measured on the operator's console: «track my parcel by talking to the seller's bot daily» was the first errand after a
boot, task `1`. Its brief store key was `research_brief:1` in the memory KV, which survives restarts — and under that
key sat the PREVIOUS boot's first errand, a podcast research. The breadth judge read it, judged the parcel errand
against «8 episodes», relaunched it, and the relaunch reused that brief as «agreed»: podcast rows in a parcel sheet.

  · D1 — one door, `runtime_ids.errand_key`: the row id, else the boot-stamped task id; never the bare counter;
  · D2 — a brief is stamped with its owner; a judge refuses a stranger's and says so; no brief, no relaunch;
    a resume reuses a brief only when it is the resumed row's own.
"""
from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import pytest

from memory import db as memdb
from nucleo import runtime_ids
from nucleo.circuit import breadth
from nucleo.runtime_ids import errand_key
from nucleo.workers import brief as _brief  # noqa: F401 — first: brief ⇄ brief_store
from nucleo.workers import brief_store
from nucleo.workers.session import SessionRecord

PODCAST = {"goal": "find the stories of the podcast narrated by Elena", "round": 1,
           "breadth": {"min_candidates": 20}, "deliverable": {"widget": "results", "n_final": 8}}


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    memdb.reset_db()
    memdb.get_db()
    seen: list = []
    from voice import observer
    monkeypatch.setattr(observer, "emit", lambda kind, label, **kw: seen.append((kind, label, kw.get("extra") or {})))
    yield seen
    memdb.reset_db()


def _boot(monkeypatch, stamp: str) -> None:
    monkeypatch.setattr(runtime_ids, "_BOOT", stamp)


def _rec(tid: str, *, uid: str = "") -> SessionRecord:
    return SessionRecord(task_id=tid, goal="track my parcel with the seller's bot daily", kind="web", uid=uid,
                         sheet="results--parcel", status="done", ok=True)


# ── D1 · one key per errand ──────────────────────────────────────────────────────────────────────────────────
def test_the_key_is_the_row_else_the_boot_stamped_id(monkeypatch):
    _boot(monkeypatch, "aaa111")
    assert errand_key(_rec("1", uid="f00d01-3")) == "f00d01-3"
    assert errand_key(_rec("1")) == "aaa111-1" and errand_key("1") == "aaa111-1" and errand_key(1) == "aaa111-1"
    assert errand_key("f00d01-3") == "f00d01-3", "an id that is already durable is returned as it is"
    assert errand_key(None) == "" and errand_key("") == ""


def test_the_first_errand_of_a_new_boot_never_reads_the_previous_boots_brief(world, monkeypatch):
    _boot(monkeypatch, "aaa111")
    brief_store.save(_rec("1"), dict(PODCAST))               # boot A, errand 1: a podcast research
    _boot(monkeypatch, "bbb222")
    assert breadth.brief_of(_rec("1")) is None, "boot B's errand 1 is another errand"
    assert brief_store.load("1") is None


def test_a_relaunch_carrying_the_row_finds_its_own_brief(world, monkeypatch):
    _boot(monkeypatch, "aaa111")
    first = _rec("1", uid="aaa111-1")
    brief_store.save(first, dict(PODCAST))
    _boot(monkeypatch, "bbb222")                             # a restart in between: the row is the same errand
    assert breadth.brief_of(_rec("4", uid="aaa111-1"))["goal"] == PODCAST["goal"]


# ── D2 · a brief names its errand ───────────────────────────────────────────────────────────────────────────
def test_a_brief_is_stamped_with_its_owner(world):
    rec = _rec("2", uid="cafe01-2")
    brief_store.save(rec, dict(PODCAST))
    assert brief_store.load(rec)["errand"] == "cafe01-2"


def test_a_strangers_brief_under_this_key_is_refused_and_said(world):
    from memory import api as memory
    memory.kv_set(brief_store._key("cafe01-5"), {**PODCAST, "errand": "dead00-5"})     # another owner's
    memory.kv_set(brief_store._key("cafe01-6"), dict(PODCAST))                          # no owner at all (legacy)
    for uid in ("cafe01-5", "cafe01-6"):
        world.clear()
        assert breadth.brief_of(_rec("9", uid=uid)) is None
        assert [(k, l, x.get("cat")) for k, l, x in world] == [("task", "🧭 brief of another errand ignored", "circuit")]


def test_with_no_brief_the_judge_never_relaunches(world):
    rec = _rec("1", uid="cafe01-7")
    rec.breadth = {"short": True, "judged": True, "enough": False, "target": {}, "progress": {}}   # a stale verdict
    assert asyncio.run(breadth.judge(rec)) is None
    assert rec.breadth is None and breadth.another_round(rec) == ""


def test_a_resume_reuses_a_brief_only_when_it_is_the_resumed_rows_own(world):
    from nucleo.dispatch import brief_door
    brief_store.save("cafe01-8", dict(PODCAST))
    how, b = asyncio.run(brief_door._compose_brief_how("seguimiento del pedido", "", False))
    assert how == "none"

    async def _no_compose(_req, _ctx):
        return None
    import nucleo.workers.brief as research
    orig = research.compose
    research.compose = _no_compose
    try:
        how, b = asyncio.run(brief_door._compose_brief_how("x", "", True, {"brief_task": "cafe01-8"}, errand="cafe01-8"))
        assert how == "reused" and b["goal"] == PODCAST["goal"]
        how, b = asyncio.run(brief_door._compose_brief_how("x", "", True, {"brief_task": "cafe01-8"}, errand="beef02-1"))
        assert how != "reused", "a relaunch of ANOTHER row never inherits this brief as its agreed criteria"
    finally:
        research.compose = orig


# ── the disarms: each guard above goes red without its line ─────────────────────────────────────────────────
def _disarmed(path: Path, old: str, new: str):
    orig = path.read_text(encoding="utf-8")
    assert old in orig, f"the disarm no longer matches {path.name}"
    path.write_text(orig.replace(old, new), encoding="utf-8")
    shutil.rmtree(path.parent / "__pycache__", ignore_errors=True)
    return orig


def _restore(path: Path, orig: str, module) -> None:
    import importlib
    path.write_text(orig, encoding="utf-8")
    shutil.rmtree(path.parent / "__pycache__", ignore_errors=True)
    importlib.reload(module)


def test_disarm_keyed_back_by_the_bare_task_id_the_second_boot_reads_the_first(world, monkeypatch):
    import importlib
    src = Path(runtime_ids.__file__)
    orig = _disarmed(src, 'return f"{boot_id()}-{tid}" if tid.isdigit() else tid', "return tid")
    try:
        importlib.reload(runtime_ids)
        importlib.reload(brief_store)
        _boot(monkeypatch, "aaa111")
        brief_store.save(_rec("1"), dict(PODCAST))
        _boot(monkeypatch, "bbb222")
        assert breadth.brief_of(_rec("1")) is not None, "disarmed, boot B's errand 1 reads boot A's podcast brief"
    finally:
        _restore(src, orig, runtime_ids)
        importlib.reload(brief_store)


def test_disarm_the_stamp_check_and_a_foreign_brief_is_judged(world):
    import importlib
    src = Path(brief_store.__file__)
    orig = _disarmed(src, 'if str(out.get("errand") or "") != owner:', "if False:")
    try:
        importlib.reload(brief_store)
        from memory import api as memory
        memory.kv_set(brief_store._key("cafe01-5"), {**PODCAST, "errand": "dead00-5"})
        assert breadth.brief_of(_rec("9", uid="cafe01-5")) is not None, "disarmed, a stranger's brief is judged"
    finally:
        _restore(src, orig, brief_store)
