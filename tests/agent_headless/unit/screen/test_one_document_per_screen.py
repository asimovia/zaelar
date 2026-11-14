"""One document per screen, written by its report and judged when read (V2-907 T1, `widgets/screen_doc.py`).

Each screen (`dev`) keeps its OWN document: a desktop and a phone never share a picture. Within a mount `n` only goes
forward (a late report never overwrites a newer one); a new mount's report replaces the old mount, which never speaks
again; `v` moves only when the content does. A screen that never reported, or is no longer open, is UNKNOWN (`None`),
never an empty screen — and an empty report is an empty screen, never unknown. What a report took off the screen is
kept in `closed` for `CLOSED_S`.

Disarm: drop the `n` check in `write` → red.
"""
from __future__ import annotations

import pathlib
import shutil

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[4]
PHONE, DESK = "mobile:p-ava", "desktop:d-ava"


@pytest.fixture
def sd(monkeypatch):
    from voice import screens
    from widgets import screen_doc
    screen_doc._reset_for_tests()
    live = {PHONE, DESK}
    monkeypatch.setattr(screens, "is_open", lambda dev: screens.clean(dev) in live)
    monkeypatch.setattr(screens, "current", lambda: DESK)
    screen_doc._live = live                     # the test closes a screen by removing it
    yield screen_doc
    screen_doc._reset_for_tests()


def _deck(*rows, front="", home=None):
    return {"layout": "deck", "front": front, "home": home or {"shown": not front, "holds": ["greeting", "next_events"]},
            "panel": "", "open": [{"id": i, "layer": n, "vis": v} for n, (i, v) in enumerate(rows)]}


def _win(*rows):
    return {"layout": "windows", "open": [{"id": i, "layer": n, "vis": v} for n, (i, v) in enumerate(rows)]}


def test_two_screens_keep_two_documents(sd):
    assert sd.write(PHONE, "m1", 1, _deck(("musica", "front"), ("agenda", "behind"), front="musica")) == (True, "")
    assert sd.write(DESK, "k1", 1, _win(("youtube", "front"), ("agenda", "visible"))) == (True, "")
    assert sd.front(PHONE) == "musica" and sd.front(DESK) == "youtube"
    assert sd.open_ids(PHONE) == ["musica", "agenda"] and sd.vis("agenda", PHONE) == "behind"
    assert sd.vis("agenda", DESK) == "visible" and sd.vis("musica", DESK) == ""
    assert sd.read().dev == DESK                                # no dev → the screen of the turn
    assert sorted(sd.screens_of("agenda")) == sorted([PHONE, DESK]) and sd.screens_of("musica") == [PHONE]


def test_n_going_back_is_refused(sd):
    assert sd.write(PHONE, "m1", 5, _deck(("musica", "front"), front="musica"))[0]
    assert sd.write(PHONE, "m1", 4, _deck()) == (False, "n_back")
    assert sd.write(PHONE, "m1", 5, _deck()) == (False, "n_back")
    assert sd.front(PHONE) == "musica"                          # the newer report stands
    assert sd.write(PHONE, "m1", 6, _deck())[0] and sd.front(PHONE) == ""


def test_a_new_mount_replaces_and_the_old_never_speaks_again(sd):
    sd.write(PHONE, "m1", 9, _deck(("musica", "front"), front="musica"))
    assert sd.write(PHONE, "m2", 1, _deck(("agenda", "front"), front="agenda")) == (True, "")   # n restarts
    assert sd.read(PHONE).mount == "m2" and sd.open_ids(PHONE) == ["agenda"]
    assert sd.write(PHONE, "m1", 10, _deck()) == (False, "replaced")


def test_unknown_is_not_empty(sd):
    assert sd.read(PHONE) is None and sd.open_ids(PHONE) is None and sd.front(PHONE) is None
    assert sd.vis("musica", PHONE) is None
    sd.write(PHONE, "m1", 1, _deck())
    assert sd.open_ids(PHONE) == [] and sd.front(PHONE) == "" and sd.vis("musica", PHONE) == ""
    assert sd.read(PHONE).home == {"shown": True, "holds": ["greeting", "next_events"]}
    sd._live.discard(PHONE)                                     # the screen is gone: unknown again, at READ time
    assert sd.read(PHONE) is None and sd.screens_of("musica") == []



def test_a_host_still_restoring_is_unknown_and_closes_nothing(sd):
    """V2-907 A1: a reload's first report, sent while the host brings its saved apps back, says `unknown`."""
    sd.write(DESK, "k1", 4, _win(("youtube", "front"), ("agenda", "visible")))
    assert sd.write(DESK, "k2", 1, {"layout": "windows", "unknown": True}) == (True, "")
    assert sd.read(DESK) is None and sd.open_ids(DESK) is None and sd.screens_of("youtube") == []
    assert sd.write(DESK, "k1", 5, _win()) == (False, "replaced")       # the new mount is registered
    assert sd.write(DESK, "k2", 2, _win(("youtube", "front"), ("agenda", "visible")))[0]
    d = sd.read(DESK)
    assert [r["id"] for r in d.open] == ["youtube", "agenda"] and d.closed == ()

def test_v_moves_only_with_the_content_and_closed_is_kept(sd, monkeypatch):
    sd.write(DESK, "k1", 1, _win(("youtube", "front"), ("agenda", "behind")))
    sd.write(DESK, "k1", 2, _win(("youtube", "front"), ("agenda", "behind")))
    assert sd.read(DESK).v == 1
    sd.write(DESK, "k1", 3, _win(("youtube", "front")))
    d = sd.read(DESK)
    assert d.v == 2 and [c["id"] for c in d.closed] == ["agenda"]
    import time
    later = time.time() + sd.CLOSED_S + 1
    monkeypatch.setattr(time, "time", lambda: later)
    assert sd.read(DESK).closed == ()


@pytest.mark.parametrize("bad", [
    {"layout": "tablet", "open": []},
    {"layout": "windows", "open": [{"id": "a", "layer": 0, "vis": "front"}, {"id": "b", "layer": 1, "vis": "front"}]},
    {"layout": "windows", "open": [{"id": "a", "layer": 0, "vis": "shown"}]},
    {"layout": "deck", "open": [{"id": "a", "layer": 0, "vis": "visible"}]},
    {"layout": "deck", "front": "b", "open": [{"id": "a", "layer": 0, "vis": "front"}]},
    {"layout": "windows", "open": "a,b"},
])
def test_a_malformed_document_is_refused_whole(sd, bad):
    sd.write(DESK, "k1", 1, _win(("youtube", "front")))
    stored, why = sd.write(DESK, "k1", 2, bad)
    assert not stored and why and sd.open_ids(DESK) == ["youtube"]


def test_disarmed_n_check_turns_red(sd):
    """Disarm: the `n` check dropped from `write` — the n-going-back test must fail."""
    import importlib
    src = ROOT / "widgets" / "screen_doc.py"
    orig = src.read_text(encoding="utf-8")
    guard = "        if cur and cur.mount == mount and n <= cur.n:\n            return False, \"n_back\"\n"
    assert guard in orig, "the disarm no longer matches screen_doc.py"
    try:
        src.write_text(orig.replace(guard, ""), encoding="utf-8")
        shutil.rmtree(src.parent / "__pycache__", ignore_errors=True)
        assert guard not in src.read_text(encoding="utf-8")
        importlib.reload(sd)
        with pytest.raises(AssertionError):
            test_n_going_back_is_refused(sd)
    finally:
        src.write_text(orig, encoding="utf-8")
        shutil.rmtree(src.parent / "__pycache__", ignore_errors=True)
        importlib.reload(sd)


def _crowd(n: int, front_at: int) -> dict:
    return {"layout": "windows", "open": [{"id": f"results::c{i}", "layer": i, "vis": "front" if i == front_at else
                                           "min"} for i in range(n)]}


def test_a_crowd_of_windows_is_cut_to_the_top_and_says_so(sd):
    """V2-907 A7: more than MAX_OPEN windows keep the top MAX_OPEN by layer, the front always, and `truncated: n`."""
    n = sd.MAX_OPEN + 6
    assert sd.write(DESK, "k1", 1, _crowd(n, front_at=n - 1)) == (True, "")
    d = sd.read(DESK)
    ids = [r["id"] for r in d.open]
    assert len(ids) == sd.MAX_OPEN and d.truncated == 6 and d.front == f"results::c{n - 1}" and ids[-1] == d.front
    assert ids[:-1] == [f"results::c{i}" for i in range(sd.MAX_OPEN - 1)]
    assert sd.write(DESK, "k1", 2, _crowd(n, front_at=0))[0]           # the same crowd, another front
    d = sd.read(DESK)
    assert d.front == "results::c0" and d.closed == ()                 # an app only left out is never «closed»
    assert sd.drift(DESK, {"open_widgets": ["results"], "maximized_widget": "", "minimized_widgets": []}) == []
    assert sd.write(DESK, "k1", 3, _crowd(sd.MAX_ROWS + 1, front_at=0)) == (False, "open")   # past the hard bound


def test_disarmed_a_crowd_refused_whole_turns_red(sd):
    """Disarm: the crowd refused whole (the old bound) — the cut test must fail."""
    import importlib
    src = ROOT / "widgets" / "screen_doc.py"
    orig = src.read_text(encoding="utf-8")
    guard = "len(rows) > MAX_ROWS:"
    assert orig.count(guard) == 1, "the disarm no longer matches screen_doc.py"
    try:
        src.write_text(orig.replace(guard, "len(rows) > MAX_OPEN:"), encoding="utf-8")
        shutil.rmtree(src.parent / "__pycache__", ignore_errors=True)
        assert guard not in src.read_text(encoding="utf-8")
        importlib.reload(sd)
        with pytest.raises(AssertionError):
            test_a_crowd_of_windows_is_cut_to_the_top_and_says_so(sd)
    finally:
        src.write_text(orig, encoding="utf-8")
        shutil.rmtree(src.parent / "__pycache__", ignore_errors=True)
        importlib.reload(sd)
