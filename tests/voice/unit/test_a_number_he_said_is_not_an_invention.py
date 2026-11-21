"""V2-756 — «ponme el vídeo número tres» · «bórrame los tres últimos» · «Para el vídeo», otra vez.

MEASURED, live session 74be8e9a (2026-09-23, 13:5x, engine 3.33+07bbe20a — the V2-755 build). What
V2-755 fixed held: «Vuelve al catálogo» → `show_tab` 0.96, obeyed; the errand harness opened a goal
and CLOSED it («✅ arnés: objetivo conseguido») instead of declaring the card empty forever. Five new
defects, each a different layer, each pinned below.

    +27.7  🗣  «Ahora quiero que me pongas el vídeo número tres»
           jev screen_action → youtube:play_result 0.95
           the model called play_video(action=list) — a fresh SEARCH of the same query
    +39.5  🗣  «Bueno, ponme el vídeo dos, QUE LOS HAS CAMBIADO.»     ← the band had renumbered
    +51.3  🗣  «¿Puedes, por favor, reproducir el video número dos?»   ← searched a third time
    +78.0  🗣  «Para el vídeo»
           jev screen_action → youtube:pause 0.95 · request_type answer 0.49 / comment 0.39
           nothing fired; the reply said «Ahí lo tienes reproduciéndose, Paco.»
    +90.4  🗣  «He dicho que pares el vídeo. Que no me has oído.»
    +128.6 🗣  «Pausa el vídeo. Vuelve al catálogo.»
           the model called widget_data(youtube, show_tab) with an EMPTY payload → `unknown_tab`
    +138.6 🗣  «¿Has ignorado la orden que te he dado?»
    +188.3 🗣  «Bórrame los tres últimos de la cola.»
           jev screen_action → youtube:remove 0.95 · the model sent item:"6" and ONE row went
           the reply said «quito el 4, el 5 y el 6 … y te dejo los tres primeros»
    +201.6 🗣  «Pero solo he visto que has borrado el número seis.»
    +241.0 🗣  «Eso es absurdo, no estás entendiendo la tarea.»

## 1 · A SEARCH is a question, and asking it twice must not change the answer

The band is what his numbers refer to. Re-running the same query re-fetched and renumbered it under
him — «que los has cambiado» is him reading the defect out loud. The same question over the same band
is now ANSWERED, not re-run: nothing renumbers, nothing is re-fetched, and the call says `unchanged`
so a channel can tell a real search from one that did nothing.

## 2 · «los tres últimos» had no way to be said

`remove` took one `item`. Its mirror `add_results` has taken «1,3» since V2-632; this one never did,
and one action per turn is the rule — so the model understood perfectly, said «quito el 4, el 5 y el
6», and deleted one row. Worse, the paid verdict with nothing better to reach for answered
`clear_list` at 0.56 over a *different* candidate set — the action that empties the WHOLE queue
(V2-742's pattern exactly). Measured with the failing turn's own 50 candidates, after declaring the
plural: «Bórrame los tres últimos de la cola» → `remove` **0.98**, «quita el cuatro y el cinco» →
`remove` **1.00**, and «vacía la cola entera» stays `clear_list` **0.94**.

## 3 · A number he SAID is not an invention

V2-741 refuses to invent a payload, and it is right. But «el vídeo número tres» over a numbered band
is not an invention, it is a reading — the same class as V2-754's declared alias, and it is what lets
the verdict complete a turn the model left empty on an action whose one key is an index.

## 4 · The model left a declared key empty and the widget threw the order away

`show_tab` with no `tab` → `unknown_tab`, over a sentence that names the face («al catálogo» IS
`inicio`, declared in the manifest). `fill_missing` only ever ADDS a key the call left empty, and only
from an alias or a said number. And one alias had to go: `player` was declared as «reproductor, el
vídeo» — on a VIDEO card «el vídeo» matches nearly every sentence, so it disambiguated nothing and
made «Pausa el vídeo. Vuelve al catálogo.» name two faces at once.

## 5 · An unsure reader was vetoing a near-certain one

The request-type gate required a confident `order`/`answer`. «Para el vídeo» is an order, and its
request type measured comment 0.45 — unsure — while the screen question answered `pause` 0.95. The
gate became a REFUSAL list for a while; since 2026-11-12 it is `direct_action.an_order`, read at the
ONE act floor (`verdicts.to_act`): the measurement that chose its kinds is in its docstring — every
ambient remark tested answers `none` 0.87-0.99 on the screen question.

Run: .venv/bin/pytest tests/voice/unit/test_a_number_he_said_is_not_an_invention.py
"""
from __future__ import annotations


import json
import pathlib
import threading

import pytest

from voice import observer as _obs
from widgets import store
from widgets.youtube import data as yt

_ENGINE = pathlib.Path(__file__).resolve().parents[3]
_MANIFEST = _ENGINE / "widgets/youtube/manifest.json"

#: His sentences, verbatim from the transcript. A paraphrase would be a test of a test.
HIS_THIRD = "Ahora quiero que me pongas el vídeo número tres"
HIS_LAST_THREE = "Bórrame los tres últimos de la cola."
HIS_CATALOG = "Pausa el vídeo. Vuelve al catálogo."


def _acts() -> dict:
    return json.loads(_MANIFEST.read_text(encoding="utf-8"))["actions"]


@pytest.fixture
def card(monkeypatch, tmp_path):
    """His state: six numbered results and six rows queued. NEVER the operator's real card."""
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    store.save(yt.WID, {
        "videoId": "", "pos": -1,
        "list": [{"videoId": f"V{i}", "title": f"vid {i}"} for i in range(1, 7)],
        "search_results": [{"videoId": f"R{i}", "title": f"res {i}"} for i in range(1, 7)],
        "search_query": "Apolo 11 documental"})


def _band(): return [r["title"] for r in (store.load(yt.WID) or {}).get("search_results") or []]
def _queue(): return [r["title"] for r in (store.load(yt.WID) or {}).get("list") or []]


# ── 1 · THE SAME QUESTION OVER THE SAME BAND DOES NOT MOVE HIS NUMBERS ────────────────────────────

# ── 2 · «BÓRRAME LOS TRES ÚLTIMOS» ────────────────────────────────────────────────────────────────

def test_remove_takes_several_and_deletes_every_one_of_them(card):
    r = yt.apply_action("remove", {"items": "4,5,6"})
    assert r["ok"] and r["count"] == 3
    assert _queue() == ["vid 1", "vid 2", "vid 3"], "he asked for three and three went"
    assert r["removed"] == ["vid 4", "vid 5", "vid 6"], "…and the ack names each one, in his order"


def test_removing_several_does_not_eat_the_wrong_rows(card):
    """Popping ascending shifts every later index by one — the classic. Highest first, or «4,5,6»
    silently deletes 4, 6 and whatever slid into place."""
    yt.apply_action("remove", {"items": "1,3,5"})
    assert _queue() == ["vid 2", "vid 4", "vid 6"]


def test_removing_several_keeps_what_is_playing_pointing_at_itself(card):
    store.save(yt.WID, {**(store.load(yt.WID) or {}), "videoId": "V5", "pos": 4})
    assert yt.apply_action("remove", {"items": "1,2"})["count"] == 4, "the two rows went"
    assert _queue()[(store.load(yt.WID) or {})["pos"]] == "vid 5", "«last played» still means vid 5"


def test_removing_ONE_is_untouched(card):
    """Today's path, bit for bit: `item` by number or by title still works."""
    assert yt.apply_action("remove", {"item": "2"})["ok"]
    assert _queue() == ["vid 1", "vid 3", "vid 4", "vid 5", "vid 6"]
    assert yt.apply_action("remove", {"item": "vid 4"})["ok"]
    assert _queue() == ["vid 1", "vid 3", "vid 5", "vid 6"]


# ── 3 · A NUMBER HE SAID ──────────────────────────────────────────────────────────────────────────

# ── 4 · THE KEY THE MODEL LEFT EMPTY ──────────────────────────────────────────────────────────────

def test_the_alias_that_matched_EVERY_sentence_is_gone():
    """`player` was «reproductor, el vídeo». On a video card «el vídeo» is in almost every sentence, so
    it disambiguated nothing and made his order name two faces at once."""
    tab = _acts()["show_tab"]["payload"]["tab"]
    assert "reproductor" in tab, "the face keeps the word that actually names it"
    assert "(reproductor, el vídeo)" not in tab


# ── 5 · THE GATE THAT LET AN UNSURE READER VETO A NEAR-CERTAIN ONE ────────────────────────────────

def _brief(answers: dict, *, open_ids=("youtube",)):
    ev = threading.Event(); ev.set()
    return {"event": ev, "turn_id": "t-1", "open_ids": list(open_ids),
            "result": {k: {"choice": c, "confidence": f} for k, (c, f) in answers.items()}}


# ── 6 · THE RECORD HAS TO SAY WHAT THE MODEL HAD IN FRONT OF IT ───────────────────────────────────

def test_the_prompt_excerpt_keeps_what_is_ON_SCREEN():
    """Third time this excerpt has cost a diagnosis (V2-195 lost the tail, V2-255 the memory). The
    on-screen band lives in the middle, and answering «did it know?» meant reconstructing the digest by
    hand against a store that had already moved on."""
    screen = ("items ahora (de lo ABIERTO — referéncialos por lenguaje natural):\n"
              "- youtube (contenido en pantalla):\n  1. Apolo 11\n  2. El Viaje a La Luna\n")
    out = _obs._prompt_excerpt("H" * 6000 + "relleno " * 600 + screen + "relleno " * 600 + "T" * 7000)
    assert "2. El Viaje a La Luna" in out, "the record cannot answer «did the model see the band?»"
    assert "OMITIDOS del centro" in out, "…and it still says what it dropped"


def test_a_short_prompt_is_still_returned_whole():
    assert _obs._prompt_excerpt("corto") == "corto"


def test_a_prompt_with_no_screen_block_behaves_exactly_as_before():
    out = _obs._prompt_excerpt("H" * 6000 + "x" * 4000 + "T" * 7000)
    assert "OMITIDOS del centro" in out and out.startswith("H") and out.endswith("T")


def test_the_screen_slice_is_BOUNDED():
    """This is the excerpt, not the prompt: a long screen is cut with its own marker rather than
    swallowing the budget the head and the tail are there to protect."""
    big = "items ahora (de lo ABIERTO" + "z" * 20_000
    out = _obs._prompt_excerpt("H" * 6000 + big + "T" * 7000)
    assert "pantalla recortada" in out and len(out) < 6000 + 7000 + _obs._ON_SCREEN_MAX + 500


# ── 7 · THE DISAGREEMENT THAT LEFT NO TRACE ───────────────────────────────────────────────────────
