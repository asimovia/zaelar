"""V2-259 F3 — “close the results” with two open is a QUESTION, not a guess.

Literal operator request: “if there are 2 results widgets and the user says ‘close the results’, the command
should generate a question: which of the 2 searches should I close, the car search or the plumber search?”.

This is an ambiguity along a DIFFERENT AXIS from the one already handled by `runtime.identify()`. That one decides WHICH PIECE
(“results” → `results`) and asks when there is no name or alias match (V2-082); this one comes later, with the
piece already clear, and what is unknown is WHICH OF ITS CARDS. It could not exist before: the only instantiated piece
was the browser, and its cards close on their own when the task ends. Since V2-259 the operator has two boxes
in front of them with the same name.

What is being established:

  · with one, closing remains closing — a spurious question on every close would be worse than the bug this
    removes, so uncertainty always falls back to the usual behavior;
  · with two, the question names the ERRANDS and not the ids (“results::t1 or results::t2?” is not a question,
    it is a dump);
  · a question that distinguishes nothing is not a question either: two untitled sheets cannot end up with “which
    one should I close, “Results” or “Results”?”;
  · and the rule lives ONCE, even though this close is emitted from three different places.
"""
from pathlib import Path

import pytest

from widgets import instances, store
from widgets.results import data as sheet


@pytest.fixture(autouse=True)
def _spanish(monkeypatch):
    """These cases measure the SPANISH question; since demo pass 62 (S1) it is in the agent's language, which the
    suite must not take from the operator's live settings."""
    from i18n import langs
    monkeypatch.setattr(langs, "current_language", lambda: langs.spec("es"))

ENGINE = Path(__file__).resolve().parents[4]
#: The VOICE channel's code, which since the 2026-09-02 ratchet pass lives in TWO files: the turn itself in
#: `nucleo.py` and the deterministic widget-intent readers (`_close_target`, `_widget_fallback`…) in
#: `widget_intent.py`. These guards ask about the channel, not about a file, so they read both — a source guard
#: pinned to one path stops guarding the moment the code is extracted, and does it by going GREEN, not red.
_VOICE_SRC = ("voice/engine/llm/providers/nucleo.py", "voice/engine/llm/providers/widget_intent.py",
              "nucleo/flash/tool_executor_widget.py", "nucleo/flash/tool_executor.py",
              "nucleo/flash/tool_executor_calls.py", "nucleo/flash/tool_executor_widget_calls.py",
              "nucleo/flash/post_stream.py", "nucleo/flash/post_stream_acts.py",
              "nucleo/flash/post_stream_lanes.py", "nucleo/flash/post_stream_settle.py", "voice/engine/llm/providers/turn_prompt.py",
              "nucleo/turn/pipeline_close.py", "voice/engine/llm/providers/turn_tools.py",
              "nucleo/turn/pipeline_admit.py", "nucleo/turn/pipeline_failure.py",
              "voice/engine/llm/providers/turn_fragment.py")   # V2-778 F1-10: they left the provider

class _Voice:
    """Reads as one source: `.read_text()` concatenates the channel's files."""

    @staticmethod
    def read_text(encoding: str = "utf-8", errors: str = "strict") -> str:
        return "\n".join((ENGINE / rel).read_text(encoding=encoding, errors=errors) for rel in _VOICE_SRC)


VOICE = _Voice()


@pytest.fixture(autouse=True)
def _aislado(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    store._last_hash.clear()
    yield
    store._last_hash.clear()


# ── 1) with one, closing is closing ───────────────────────────────────────────────────────────────────────────

def test_one_card_closes_without_asking():
    r = instances.resolve_close("results", ["results::t1"])
    assert r["id"] == "results::t1" and not r["ask"]


def test_none_open_still_closes_like_it_always_did():
    """Closing a card that is no longer there is a harmless no-op, and this was always the behavior: the real
    purpose of that emit is to cancel the spurious escalation, not the card."""
    r = instances.resolve_close("results", [])
    assert r["id"] == "results" and not r["ask"]


def test_another_piece_is_not_ambiguous_just_because_results_has_two():
    r = instances.resolve_close("agenda", ["results::t1", "results::t2", "agenda"])
    assert r["id"] == "agenda" and not r["ask"]


def test_an_instance_named_out_loud_is_not_a_question():
    r = instances.resolve_close("results::t9", ["results::t1", "results::t2"])
    assert r["id"] == "results::t9" and not r["ask"]


# ── 2) with two, ask — naming the errands ─────────────────────────────────────────────────────────────────────

def test_two_cards_ask_which_one():
    sheet.apply_action("present", {"sheet": "t1", "title": "Fontaneros en Madrid centro",
                                   "items": [{"title": "Relatores"}]})
    sheet.apply_action("present", {"sheet": "t2", "title": "Coches de segunda mano",
                                   "items": [{"title": "Ibiza"}]})
    r = instances.resolve_close("results", ["results::t1", "results::t2"])
    assert r["id"] is None, "con dos abiertas, elegir una acierta la mitad de las veces y borra la otra mitad"
    assert "Fontaneros en Madrid centro" in r["ask"] and "Coches de segunda mano" in r["ask"]
    assert "results::" not in r["ask"], "la pregunta nombra los ENCARGOS; un id no es una pregunta"
    assert r["options"] == ["results::t1", "results::t2"]


def test_three_cards_read_as_a_list_and_not_as_a_dump():
    for n, t in enumerate(("Fontaneros", "Coches", "Hoteles"), 1):
        sheet.apply_action("present", {"sheet": f"t{n}", "title": t, "items": [{"title": "x"}]})
    ask = instances.resolve_close("results", [f"results::t{n}" for n in (1, 2, 3)])["ask"]
    assert ask.count("«") == 3 and " o «Hoteles»" in ask


def test_a_question_that_cannot_be_answered_is_not_a_question():
    """Two sheets with no errand behind them are both given the placeholder title “Results”. Asking ““Results” or
    “Results”?” forces the operator to answer something that distinguishes nothing — worse than not asking."""
    ask = instances.resolve_close("results", ["results::t1", "results::t2"])["ask"]
    # V2-812 T-06: told apart by their PLACE, never by their instance id.
    assert "t1" not in ask and "t2" not in ask
    assert ask.count("(n.º 1)") == 1 and ask.count("(n.º 2)") == 1


def test_colliding_titles_get_disambiguated_instead_of_repeated():
    for sid in ("t1", "t2"):
        sheet.apply_action("present", {"sheet": sid, "title": "Coches", "items": [{"title": "x"}]})
    ask = instances.resolve_close("results", ["results::t1", "results::t2"])["ask"]
    assert "Coches (n.º 1)" in ask and "Coches (n.º 2)" in ask      # V2-812 T-06: place, never id
    assert "t1" not in ask and "t2" not in ask


# ── 3) the rule lives ONCE ─────────────────────────────────────────────────────────────────────────────────────

def test_the_raw_instances_are_readable_because_the_state_normalizes_them_away():
    """`memory.state()['open_widgets']` stores the BASES, which is correct for what it does: the brain's state
    speaks about pieces. But this question is about CARDS, and normalization erases exactly that data there —
    the same collapse noted by V2-047 F9 and never closed out."""
    from server import voice_api
    voice_api.canvas_state._last_inst = None
    assert voice_api.open_instances() == [], "sin informe del canvas es «no lo sé», no una ambigüedad inventada"
    voice_api.canvas_state._last_inst = ["results::t1", "results::t2", "agenda"]
    assert instances.instances_of("results", voice_api.open_instances()) == ["results::t1", "results::t2"]


# ── V2-300: the MIRROR — “show it to me” does not open the bare box when the errand sheet is in front either ─
#
# Round 24 of `search-buy-guitar__es` (2026-08-24): the errand sheet (`results::58c1af-1`) OPEN with 20
# rows, the operator asks to see a result, the model shows `results` by itself, and the canvas opens the
# BARE box — “I’ll open it for you, although it is empty for now” with the deliverable beside it. The V2-209
# guard told the truth about the wrong box; what was missing was opening the correct one.

def test_showing_the_base_with_ONE_instance_open_resolves_to_the_instance():
    out = instances.resolve_show("results", ["results::58c1af-1", "agenda"])
    assert out["id"] == "results::58c1af-1" and not out["ask"]


def test_showing_with_TWO_instances_open_asks_naming_the_errands():
    out = instances.resolve_show("results", ["results::t1", "results::t2"])
    assert out["id"] is None and "¿cuál te enseño" in out["ask"]


def test_showing_with_NO_instance_open_keeps_the_base_as_always():
    """Sensitivity: with no errand sheets in front, the base is the only one there and opening it is the usual behavior."""
    out = instances.resolve_show("results", ["agenda"])
    assert out["id"] == "results" and not out["ask"]


def test_a_named_instance_passes_through_untouched():
    out = instances.resolve_show("results::t7", ["results::t1", "results::t7"])
    assert out["id"] == "results::t7" and not out["ask"]


# ── 5) «los dos» ANSWERS the question instead of restarting it (V2-530) ───────────────────────────────────────
#
# Measured 2026-08-31 (session `7cab1afd`): with two results sheets open the operator said «cierra los dos» and
# got the disambiguation question BACK, then said «cierra las dos» and got it again — the second time with the
# verb changed from «cierro» to «enseño». He had ANSWERED it. The question asks WHICH ONE and the answer was
# BOTH, an option the resolver had no way to express, so every rephrasing round-tripped into the same question.

def test_both_closes_every_card_instead_of_asking_again():
    r = instances.resolve_close("results", ["results::t1", "results::t2"], "Cierra los dos.")
    assert not r["ask"], "«los dos» IS the answer — asking again is the bug"
    assert r["ids"] == ["results::t1", "results::t2"]


@pytest.mark.parametrize("said", ["cierra las dos", "ciérralas ambas", "cierra todas", "close both of them"])
def test_the_other_natural_ways_of_saying_it(said):
    assert instances.wants_every(said), f"«{said}» quantifies over every app"


def test_but_a_plain_close_still_asks():
    """The counterweight. Without it, «answer both» is satisfied by never asking again — which throws away
    V2-259 F3 whole: closing the wrong search is exactly what the question exists to prevent."""
    r = instances.resolve_close("results", ["results::t1", "results::t2"], "ciérralo")
    assert r["ask"] and r["ids"] == []


def test_showing_answers_it_too():
    """The mirror. In the live session the follow-up was routed to SHOW, not close (the model changed the verb
    on its own), so fixing only the close half would have left the operator in the very same loop."""
    r = instances.resolve_show("results", ["results::t1", "results::t2"], "enséñame las dos")
    assert not r["ask"] and r["ids"] == ["results::t1", "results::t2"]


def test_ids_always_travels_so_a_caller_that_loops_it_is_right_in_every_case():
    """`ids` is the whole reason this does not need a second rule at each call site: a caller that iterates it
    handles one card, none, an already-disambiguated id and «both» with the same line. Reading `id` is what
    made two of the three closing paths miss the answer."""
    assert instances.resolve_close("results", ["results::t1"], "")["ids"] == ["results::t1"]
    assert instances.resolve_close("results::t7", [], "")["ids"] == ["results::t7"]
    assert instances.resolve_close("results", [], "")["ids"] == ["results"]


def test_an_open_sheet_is_named_by_its_own_title(monkeypatch):
    """V2-773 (demo v3, S1): «Show me the monitors» → «I don't have anything like that in your set of cards» —
    the worker's sheet was titled «27-inch 4K monitors under $400» and only aliases named cards."""
    from widgets import runtime
    monkeypatch.setattr(instances, "card_face", lambda wid: {"label": "27-inch 4K monitors under $400", "blank": False}
                        if wid == "results::x1" else {})
    assert runtime.identify_named("Show me the monitors", open_ids=["results::x1", "documento"]) == "results::x1"
    assert runtime.identify_named("Show me the monitor sheet", open_ids=["results::x1"]) == "results::x1", "singular too"
    assert runtime.identify_named("Show me the results", open_ids=["results::x1"]) == "results", "an alias still wins, and narrows later"
    assert runtime.identify_named("Show me the map", open_ids=["results::x1"]) != "results::x1", "a word not in the title names nothing"


def test_the_results_piece_lists_its_titled_sheets_most_recent_first(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.results import data as rd
    import time as _t
    store.save("results--a-1", {"title": "Three 27\" 4K monitors under $400", "items": [{"title": "x", "url": "https://a"}]})
    _t.sleep(0.02)
    store.save("results--b-1", {"title": "Resultados", "items": [{"title": "y", "url": "https://b"}]})   # untitled: names nothing
    _t.sleep(0.02)
    store.save("results--c-1", {"title": "Consulta seguro", "items": []})                                # empty: names nothing
    _t.sleep(0.02)
    store.save("results--d-1", {"title": "Five clear days with Anna", "items": [{"title": "z", "url": "https://d"}]})
    assert [r["id"] for r in rd.recent_faces()] == ["results::d-1", "results::a-1"]
    assert instances.recent_faces()[0]["label"] == "Five clear days with Anna"
