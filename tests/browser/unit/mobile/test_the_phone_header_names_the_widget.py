"""The phone's card header names the WIDGET; only a widget that declares `"live_title": true` lends it its `data.title`.

2026-11-17, the operator's iPhone: the video widget's header read «Golden Gate Bridge: The Structure that …» — the
phone deck (`Deck.js::_applyTitle`) used `data.title` for EVERY widget, while the desktop host
(`desktop.js::_wantsLiveTitle`) does it only for the widgets whose content IS their identity (a document, a page, a
results sheet) and that say so in their manifest. A player's current item is not its name. `data.task` (what a widget
is working on) still names the card on the phone, as before.

The method is read out of the shipped `Deck.js` and run in Node against stand-in cards — the source of truth, not a copy.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

_ENGINE = Path(__file__).resolve().parents[4]
_DECK = _ENGINE / "frontend" / "mobile" / "app" / "shell" / "Deck.js"

_RUN = """
const body = %s;
const apply = new Function("w", "data", body);
const out = {};
for (const [k, c] of Object.entries(%s)) {
  const w = {base: c.base, titleEl: {textContent: ""}};
  apply.call({_registry: c.reg || null, _meta: c.meta || null}, w, c.data);
  out[k] = w.titleEl.textContent;
}
console.log(JSON.stringify(out));
"""

_CASES = {
    "player": {"base": "youtube", "meta": {"youtube": {"name": "YouTube"}},
               "data": {"title": "Golden Gate Bridge: The Structure that Defined an Era"}},
    "player_named": {"base": "youtube", "reg": {"youtube": {"name": "Vídeos"}}, "meta": {"youtube": {"name": "YouTube"}},
                     "data": {"title": "Golden Gate Bridge"}},
    "document": {"base": "documento", "meta": {"documento": {"name": "Documento", "live_title": True}},
                 "data": {"title": "Informe trimestral"}},
    "task": {"base": "navegador", "meta": {"navegador": {"name": "Navegador"}}, "data": {"task": "Buscando vuelos"}},
    "no_data": {"base": "results", "meta": {"results": {"name": "Results", "live_title": True}}, "data": None},
}


def _body(src: str) -> str:
    m = re.search(r"\n  _applyTitle\(w, data\) \{\n(.*?)\n  \}\n", src, re.S)
    assert m, "Deck.js lost its _applyTitle(w, data) method"
    return m.group(1)


def _titles(src: str) -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required to run the deck's own method")
    out = subprocess.run([node, "-e", _RUN % (json.dumps(_body(src)), json.dumps(_CASES))],
                         capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_the_phone_header_honours_live_title_like_the_desktop():
    got = _titles(_DECK.read_text(encoding="utf-8"))
    assert got["player"] == "YouTube", "a player's current video is not the widget's name"
    assert got["player_named"] == "Vídeos", "his own name for it (the registry) still wins over the catalogue's"
    assert got["document"] == "Informe trimestral", "a widget that opts in keeps its live title"
    assert got["task"] == "Buscando vuelos", "what a widget is working on still names the card"
    assert got["no_data"] == "Results"


def test_disarm_a_header_that_takes_every_title_is_caught():
    """The rule before 2026-11-17 (`data.title || data.task` for every widget) must read red here."""
    src = _DECK.read_text(encoding="utf-8")
    body = _body(src)
    line = next(ln for ln in body.splitlines() if "const live" in ln)
    disarmed = src.replace(line, "    const live = data && (data.title || data.task);")
    assert _titles(disarmed)["player"] != "YouTube"
