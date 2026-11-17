"""The phone's card header names the WIDGET; only a widget that declares `"live_title": true` lends it its `data.title`.

2026-11-17, the operator's iPhone: the video widget's header read «Golden Gate Bridge: The Structure that …» — the
phone deck (`Deck.js::_applyTitle`) used `data.title` for EVERY widget, while the desktop host
(`desktop.js::_wantsLiveTitle`) does it only for the widgets whose content IS their identity (a document, a page, a
results sheet) and that say so in their manifest. A player's current item is not its name. `data.task` (what a widget
is working on) still names the card on the phone, as before. The flag outlives the catalog cache (`_meta` is dropped
on a delete and emptied by a failed refetch), and the «the header has your title» marker (`hostTitle`) is set on
the same condition as the desktop's, or a player would show its title nowhere.

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
const titleBody = %s, catalogBody = %s, markLine = %s, cases = %s, catalog = %s;
const applyTitle = new Function("w", "data", titleBody);
const AsyncFunction = (async () => {}).constructor;
const loadCatalog = new AsyncFunction(catalogBody);
const mark = new Function("w", "baseId", markLine);
(async () => {
  // The deck as it lives: the catalog read once (`_catalog`), then dropped by a delete or a new widget
  // (`_meta = null`), then a refetch that FAILS (`_meta = {}`) — the header must not forget a live_title.
  const deck = {_registry: null, _meta: null, _ids: null, _live: {}};
  globalThis.fetch = async () => ({json: async () => ({widgets: catalog})});
  await loadCatalog.call(deck);
  const out = {};
  for (const phase of ["read", "dropped", "failed"]) {
    if (phase === "dropped") deck._meta = null;
    if (phase === "failed") { deck._meta = null; globalThis.fetch = async () => { throw new Error("offline"); }; await loadCatalog.call(deck); }
    for (const [k, c] of Object.entries(cases)) {
      const w = {base: c.base, titleEl: {textContent: ""}, body: {dataset: {}}};
      applyTitle.call(Object.assign({}, deck, {_registry: c.reg || null}), w, c.data);
      mark.call(deck, w, c.base);
      out[phase + ":" + k] = [w.titleEl.textContent, w.body.dataset.hostTitle || ""];
    }
  }
  console.log(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
"""

_CATALOG = [{"id": "youtube", "name": "YouTube"}, {"id": "documento", "name": "Documento", "live_title": True},
            {"id": "navegador", "name": "Navegador", "live_title": True}, {"id": "results", "name": "Results", "live_title": True}]
_CASES = {
    "player": {"base": "youtube", "data": {"title": "Golden Gate Bridge: The Structure that Defined an Era"}},
    "player_named": {"base": "youtube", "reg": {"youtube": {"name": "Vídeos"}}, "data": {"title": "Golden Gate Bridge"}},
    "document": {"base": "documento", "data": {"title": "Informe trimestral"}},
    "task": {"base": "navegador", "data": {"task": "Buscando vuelos"}},
    "no_data": {"base": "results", "data": None},
}


def _method(src: str, head: str) -> str:
    m = re.search(r"\n  " + re.escape(head) + r" \{\n(.*?)\n  \}\n", src, re.S)
    assert m, f"Deck.js lost its {head} method"
    return m.group(1)


def _mark(src: str) -> str:
    line = next((ln for ln in src.splitlines() if "w.body.dataset.hostTitle" in ln), None)
    assert line, "Deck.js lost the hostTitle marker"
    return line.strip()


def _titles(src: str) -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required to run the deck's own methods")
    js = _RUN % (json.dumps(_method(src, "_applyTitle(w, data)")), json.dumps(_method(src, "async _catalog()")),
                 json.dumps(_mark(src)), json.dumps(_CASES), json.dumps(_CATALOG))
    out = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_the_phone_header_honours_live_title_like_the_desktop():
    got = _titles(_DECK.read_text(encoding="utf-8"))
    for phase in ("read", "dropped", "failed"):
        g = {k.split(":", 1)[1]: v for k, v in got.items() if k.startswith(phase + ":")}
        # with the catalog dropped the name falls back to the id, as it always has; never to the video
        assert g["player"] == ["YouTube" if phase == "read" else "youtube", ""], (phase, "a player's video is not its name")
        assert g["player_named"][0] == "Vídeos", (phase, "his own name for it (the registry) still wins")
        assert g["document"] == ["Informe trimestral", "1"], (phase, "a live_title card keeps its title in the header")
        assert g["task"][0] == "Buscando vuelos", (phase, "what a widget is working on still names the card")
        assert g["no_data"][0] in ("Results", "results")


def test_disarm_a_header_that_takes_every_title_is_caught():
    """The rule before 2026-11-17 (`data.title || data.task` for every widget) must read red here."""
    src = _DECK.read_text(encoding="utf-8")
    line = next(ln for ln in _method(src, "_applyTitle(w, data)").splitlines() if "const live" in ln)
    disarmed = src.replace(line, "    const live = data && (data.title || data.task);")
    assert _titles(disarmed)["read:player"][0] != "YouTube"


def test_disarm_a_live_title_read_from_the_dropped_catalog_is_caught():
    """Reading the flag from `_meta`, which a delete nulls and a failed refetch empties, loses the document's title."""
    src = _DECK.read_text(encoding="utf-8")
    line = next(ln for ln in _method(src, "_applyTitle(w, data)").splitlines() if "const live" in ln)
    disarmed = src.replace(line, "    const live = data && ((meta && meta.live_title && data.title) || data.task);")
    got = _titles(disarmed)
    assert got["read:document"][0] == "Informe trimestral" and got["dropped:document"][0] != "Informe trimestral"


def test_disarm_a_marker_set_for_every_card_is_caught():
    src = _DECK.read_text(encoding="utf-8")
    disarmed = src.replace(_mark(src), 'w.body.dataset.hostTitle = "1";')
    assert _titles(disarmed)["read:player"][1] == "1"
