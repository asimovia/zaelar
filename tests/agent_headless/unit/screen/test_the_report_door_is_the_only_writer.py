"""A screen's document has ONE writer: its report door (V2-907 T4, `POST /api/screen/report`).

The door stores the document (`widgets/screen_doc.write`), hands the answers it carries to the order ledger
(`widgets/screen_orders.ack`) and emits `screen/report` only when the document moved or an order was answered. A
refused report (`n` back, a replaced mount, a malformed document) is refused whole, its answers too. No other product
code calls `screen_doc.write`: a structural scan over every product file keeps it so — by the AST (a call, or a
reference that could be called later, to `write` or the store `_DOCS`/`_GONE` through any name the module was bound
to) AND by the text (V2-907 A6: a file that names `screen_doc` together with `write` or `_DOCS` is named, so
`__import__`, `importlib` and a `getattr` alias cannot slip past the AST).

Disarm: a second writer in a temporary product module, in each bypass form → the scan names it → red.
"""
from __future__ import annotations

import ast
import asyncio
import json
import pathlib
import re
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[4]
DESK = "desktop:d-ava"


@pytest.fixture
def door(monkeypatch):
    from server import canvas_api
    from voice import screens
    from widgets import screen_doc, screen_orders
    screen_doc._reset_for_tests()
    screen_orders._reset_for_tests()
    monkeypatch.setattr(screens, "is_open", lambda dev: screens.clean(dev) == DESK)
    events: list = []
    monkeypatch.setattr(canvas_api, "emit", lambda kind, label, **kw: events.append((kind, label, kw)))

    def _post(body):
        r = asyncio.run(canvas_api.screen_report(body))
        return r.status_code, json.loads(r.body)
    yield _post, events, screen_doc, screen_orders
    screen_doc._reset_for_tests()
    screen_orders._reset_for_tests()


def _doc(*rows):
    return {"layout": "windows", "open": [{"id": i, "layer": n, "vis": v} for n, (i, v) in enumerate(rows)]}


def test_the_door_writes_the_document_and_takes_the_answers(door):
    post, events, sd, so = door
    seq = so.issue("show", "agenda", [DESK])
    code, ans = post({"dev": DESK, "mount": "k1", "n": 1, "doc": _doc(("agenda", "front")), "by": "engine",
                      "acks": [{"seq": seq, "ok": True, "why": "done"}]})
    assert code == 200 and ans == {"ok": True, "v": 1, "acks": 1}
    assert sd.front(DESK) == "agenda" and so.outcome(seq) == "confirmed"
    assert [(k, lab) for k, lab, _ in events] == [("screen", "report")]
    assert events[0][2]["extra"]["open"] == ["agenda"]
    code, ans = post({"dev": DESK, "mount": "k1", "n": 2, "doc": _doc(("agenda", "front"))})
    assert code == 200 and ans["v"] == 1 and len(events) == 1          # nothing moved: no event


def test_a_refused_report_is_refused_whole(door):
    post, events, sd, so = door
    post({"dev": DESK, "mount": "k1", "n": 5, "doc": _doc(("agenda", "front"))})
    seq = so.issue("close", "agenda", [DESK])
    code, ans = post({"dev": DESK, "mount": "k1", "n": 4, "doc": _doc(),
                      "acks": [{"seq": seq, "ok": True, "why": "done"}]})
    assert code == 409 and ans["error"] == "n_back" and so.outcome(seq) == "pending"
    code, ans = post({"dev": DESK, "mount": "k1", "n": 6, "doc": {"layout": "tablet", "open": []}})
    assert code == 400 and sd.open_ids(DESK) == ["agenda"]


#: The store's writer and its private state: no product module but the door may name them beside `screen_doc`.
_STORE = ("write", "_DOCS", "_GONE")
_TEXT = re.compile(r"\b(?:write|_DOCS|_GONE)\b")


def _writers() -> list[str]:
    """Every product module that reaches `screen_doc.write` or its store, through any name it bound the module or the
    function to (AST), or that names `screen_doc` beside `write` / `_DOCS` / `_GONE` anywhere in its text."""
    out = subprocess.run(["git", "ls-files", "-co", "--exclude-standard", "*.py"], cwd=ROOT, capture_output=True,
                         text=True).stdout.split()
    found = []
    for rel in out:
        if rel.startswith("tests/") or "/tests/" in rel or rel == "widgets/screen_doc.py" or not (ROOT / rel).exists():
            continue
        src = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        if "screen_doc" not in src:
            continue
        if _TEXT.search(src):
            found.append(rel)
        tree = ast.parse(src)
        mods, fns = {"screen_doc"}, set()
        for n in ast.walk(tree):
            if isinstance(n, ast.ImportFrom) and n.module == "widgets":
                mods |= {a.asname or a.name for a in n.names if a.name == "screen_doc"}
            if isinstance(n, ast.ImportFrom) and n.module == "widgets.screen_doc":
                fns |= {a.asname or a.name for a in n.names if a.name in _STORE}
            if isinstance(n, ast.Import):
                mods |= {a.asname or a.name for a in n.names if a.name == "widgets.screen_doc"}
        for n in ast.walk(tree):
            if (isinstance(n, ast.Attribute) and n.attr in _STORE and ast.unparse(n.value) in mods) or \
                    (isinstance(n, ast.Name) and n.id in fns):
                found.append(rel)
    return sorted(set(found))


def test_the_report_door_is_the_only_writer():
    assert _writers() == ["server/canvas_api.py"]


_BYPASSES = {
    "alias_call": "from widgets import screen_doc as sd\n\n\ndef sneak():\n    sd.write('x', 'm', 1, {})\n",
    "dunder_import": "def sneak():\n    __import__('widgets.screen_doc', fromlist=['x']).write('x', 'm', 1, {})\n",
    "bound_later": "from widgets import screen_doc\n\nw = screen_doc.write\n\n\ndef sneak():\n    w('x', 'm', 1, {})\n",
    "importlib": "import importlib\n\n\ndef sneak():\n    importlib.import_module('widgets.screen_doc').write('x', 'm', 1, {})\n",
    "the_store": "from widgets import screen_doc\n\n\ndef sneak():\n    screen_doc._DOCS['x'] = None\n",
    "getattr": "import importlib\n\nm = importlib.import_module('widgets.' + 'screen_doc')\nw = getattr(m, 'write')\n",
}


@pytest.mark.parametrize("form", sorted(_BYPASSES))
def test_disarmed_a_second_writer_is_named(form):
    tmp = ROOT / "widgets" / "_v907_disarm_writer.py"
    try:
        tmp.write_text(_BYPASSES[form], encoding="utf-8")
        assert tmp.exists()
        with pytest.raises(AssertionError):
            test_the_report_door_is_the_only_writer()
        assert "widgets/_v907_disarm_writer.py" in _writers()
    finally:
        tmp.unlink(missing_ok=True)
