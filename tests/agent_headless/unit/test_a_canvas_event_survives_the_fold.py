"""No canvas event vanishes while the canvas leaves fold into the door (V2-826 §2b, refactor2710-04).

Every literal (kind, label) the canvas door, its arbiter, the turn it reads and the canvas leaves emit is frozen here;
a show or close a caller hands to `nucleo.acts.canvas.apply("<op>", …)` counts as the ("widget", "<op>") the door emits
for it. A pair may move between these files or into the door, never vanish; one retired on purpose leaves this set in
the same commit, with the reason. Measured 2026-10-28 on the branch after T-02 (every writer crosses the door).
"""
from __future__ import annotations

import ast
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]
FILES = ["nucleo/acts/canvas.py", "nucleo/acts/canvas_arbiter.py", "nucleo/acts/canvas_turn.py",
         "nucleo/canvas_focus.py", "nucleo/canvas_closes.py", "nucleo/surfaces.py",
         # moved out of the old turn (INI-078 F2 step 8, T7): read where they live now
         "nucleo/acts/bulk_close.py", "nucleo/acts/visibility.py", "nucleo/acts/show_target.py", "nucleo/acts/close_words.py"]

FROZEN = {
    # INI-078 L1: the old turn's canvas lanes (nucleo/flash) and the word licences went with it; their events left this set.
    # V2-851 F2 retired `card_commission.after_show` (the promise repair over a shown card) with its three events:
    # «a question does not write», «opened the card and promised more», «a web address nobody said».
    ('brain', '🧷 bulk close: sparing would close nothing — everything closes'),
    ('brain', '🧷 bulk close: the app in use stays'),
    ('widget', 'close'),
    ('widget', 'show'),
    ('widget', '🚫 presentación suprimida'),
}


def _pairs(sources: dict[str, str]) -> set:
    pairs = set()
    for rel, text in sources.items():
        for n in ast.walk(ast.parse(text)):
            if not isinstance(n, ast.Call) or not n.args or not isinstance(n.args[0], ast.Constant):
                continue
            name = n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
            if name == "apply" and rel != "nucleo/acts/canvas.py":
                pairs.add(("widget", n.args[0].value))
            elif name in ("emit", "_emit", "_say") and len(n.args) > 1 and isinstance(n.args[1], ast.Constant):
                pairs.add((n.args[0].value, n.args[1].value))
    return pairs


def _now() -> set:
    return _pairs({f: (ENGINE / f).read_text(encoding="utf-8") for f in FILES if (ENGINE / f).exists()})


def test_no_frozen_canvas_event_vanishes():
    gone = sorted(FROZEN - _now(), key=str)
    assert not gone, f"a canvas event stopped being emitted: {gone}"


def test_disarm_a_dropped_event_is_named():
    pairs = _pairs({"nucleo/x.py": 'from nucleo.acts import canvas\ncanvas.apply("close", "agenda", src="flash")\n'})
    assert pairs == {("widget", "close")}
    assert ("widget", "close") in FROZEN and ("widget", "close") not in (_now() - {("widget", "close")})
