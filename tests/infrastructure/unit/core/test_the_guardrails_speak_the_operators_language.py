"""V2-677 · node 3.40 — the guardrails in the operator's language, and a system note is not an order.

Every case here is a sentence the operator actually said, or a sentence the engine actually produced, on
2026-09-11 in two English sessions (`e896f596` 23:16-23:20 and `366787ed` 23:23-23:26). His own reading was
«va mejor en castellano… no sé si hay algún problema idiomático en los prompts, los guardarraíles, las
reglas», and the measurements below say he was right about the mechanism as well as the symptom.

The unifying defect: every grammar guard in this codebase is bilingual by declaration and monolingual in
practice. The Spanish side is written with open suffixes and catches the whole conjugation; the English
side was a list of BARE STEMS, so it missed the forms an operator actually speaks.
"""
from __future__ import annotations



import pytest


# ── D · A SYSTEM NOTE IS NOT AN ORDER — the kickoff that spawned a worker ─────────────────────────────────
# The single most expensive finding of the session. At 23:16:36 `looks_like_modify_widget` fired on the
# FIRST TURN's composed prompt and escalated the greeting to a real `claude_code` worker, which ran for
# fifty seconds and came back with a Spanish greeting into an English conversation.
#
# The three words that satisfied the guard were ALL OURS: «añade» from «añade en una frase lo que sigue»,
# «fondo» from «La tarea de fondo…», and «panel» from «Lo tienes en el panel de estado».
#
# 2026-11-12 (group A, CRIT-C16, node 2.1728): the guard itself went — no word reader opens an errand at the close
# any more, so the composed turn has nothing left to fool. What this section keeps is the rule the incident taught,
# where it is still read: `router.operator_words` strips our notes before any reader sees his words.
_KICKOFF = ("Es el primer turno. Salúdame en 1-2 frases, cálido y breve; si por tu MEMORIA ya sabes mi "
            "nombre, úsalo y NO preguntes quién soy; si no, preséntate en una línea y pregúntame el "
            "nombre. Luego para.")
_MEASURED_TURN = _KICKOFF + (
    "\n\n[SISTEMA] Avisos pendientes — SOLO cuando hayas atendido y contestado lo que te ha pedido "
    "arriba, y después de eso, añade en una frase lo que sigue; nunca abras con ello ni le hagas esperar "
    "su respuesta:\n"
    "[SISTEMA] Brain worker · Tarea sin completar: Esa tarea no ha podido completarse por un fallo del "
    "proveedor. Lo tienes en el panel de estado.\n"
    "[SISTEMA] La tarea de fondo «Create a chart/graph showing the evolution of Bitcoin's price over the» "
    "ha MUERTO sin resultado y no se va a reintentar sola.")


# ── F · Everything the operator HEARS is in his language, including the workers ───────────
def test_every_worker_prompt_carries_the_language_of_the_delivery():
    """The GENERIC worker prompt named the language NOWHERE, while every block in it is Spanish.
    Measured: a worker's delivery came back «¡Hola, Richard! Qué gusto tenerte aquí» in English session."""
    from nucleo.workers import prompts as dp

    block_en = _with_language("en", dp.worker_language_block)
    assert "English" in block_en and "A PROPÓSITO" in block_en
    block_es = _with_language("es", dp.worker_language_block)
    assert "Español" in block_es and "A PROPÓSITO" not in block_es, (
        "a Spanish operator must not be told his own instructions are in the wrong language")
    generic = _with_language("en", lambda: dp._build_prompt("do a thing", "", True))
    assert "IDIOMA DE LA ENTREGA" in generic


def _with_language(code, fn):
    """Call `fn` with the active language forced — the table reads it from the environment."""
    import os
    import i18n.langs as L
    old = os.environ.get("ZAELAR_LANGUAGE")
    os.environ["ZAELAR_LANGUAGE"] = code
    try:
        L.lock(code) if hasattr(L, "lock") else None
        return fn()
    finally:
        if old is None:
            os.environ.pop("ZAELAR_LANGUAGE", None)
        else:
            os.environ["ZAELAR_LANGUAGE"] = old
        if hasattr(L, "lock") and old:
            L.lock(old)


# ── H · A generated widget is told about all THREE sizes and told the chrome is not its job ───────────────
def test_the_generator_teaches_three_sizes_and_the_host_contract():
    """The operator: «que por defecto les dé tres tamaños de pantalla que sean responsive y además que
    tengan estas funcionalidades para interactuar con el frontend, de maximizarse, minimizarse, etc.»
    The contract taught TWO (desk + phone); the third — maximized, filling the canvas — is the one he
    reached for, and the one a narrow-only layout strands a 400px column inside."""
    from widgets import generator
    c = generator._CONTRACT
    assert "THREE SIZES, ONE WIDGET" in c
    for token in ("PHONE", "DESK CARD", "MAXIMIZED", "auto-fit"):
        assert token in c, token
    # The chrome already exists for every widget; a widget drawing its own is a frame inside a frame.
    assert "CHROME IS THE HOST'S, NEVER YOURS" in c
    for control in ("close", "maximize", "minimize", "resize"):
        assert control in c
    guide = open("widgets/AGENTS.md", encoding="utf-8").read()
    assert "THREE SIZES, ONE WIDGET" in guide, "the guide and the injected contract must agree"


def test_the_host_really_does_give_every_card_those_controls():
    """The claim above is only honest if the desktop actually builds them for EVERY widget, unconditionally
    — which is what makes «I can't resize or maximize widgets» a false sentence rather than a limitation."""
    src = open("frontend/app/widgets/desktop.js", encoding="utf-8").read()
    i = src.index("const card=document.createElement(\"div\"); card.className=\"hb-win loading\"")
    # Bounded by the fresh block's own tail (`_watchSize`), not by a character count: V2-759 added the system
    # exit's double click to this block and a 4000-char window silently stopped reaching the handles.
    fresh = src[i:src.index("this._watchSize(card)", i)]
    for piece in ('className="hb-x"', 'className="hb-max"', "_addHandles(card)",
                  "_wireDrag(card)", "_wireResize(card"):
        assert piece in fresh, f"a fresh card stopped getting {piece}"


# ── I · Picking one of six pictures, in either language ───────────────────────────────────────────────────
# «Why don't you just show me the one with the graph?» → `select` answered «dime cuál: un número o parte del
# título» over six NEWS HEADLINES, none of which could match anything he might say. A bare digit resolved
# and every ordinal resolved to NOTHING — in both languages — which is the most natural way a person picks
# from a numbered row and the one way that failed.
_SHOT = [{"title": "Bitcoin (BTC) on Verge of Worst Month", "site": "cnews24.ru"},
         {"title": "Bitcoin declines following $1 trillion", "site": "x.com"},
         {"title": "CZ Sees Faster Bitcoin Price Recovery", "site": "coindesk.com"},
         {"title": "Bitcoin Price Chart USD", "site": "tradingview.com"}]


@pytest.mark.parametrize("said,want", [
    ("1", 0), ("3\u00ba", 2),                                   # what already worked
    ("the first one", 0), ("la primera", 0),
    ("el tercero", 2), ("the third", 2),
    ("the last one", 3), ("la \u00faltima", 3), ("el cuarto", 3),
])
def test_a_picture_is_picked_by_its_position_in_either_language(said, want):
    from widgets.imagenes import data as imgdata
    assert imgdata._resolve(_SHOT, said) == want, said


def test_picking_by_what_the_title_says_still_wins():
    """The counterweight: position is tried FIRST, but a real content word must still resolve."""
    from widgets.imagenes import data as imgdata
    assert imgdata._resolve(_SHOT, "chart") == 3
    assert imgdata._resolve(_SHOT, "Bitcoin declines") == 1
    assert imgdata._resolve(_SHOT, "something nobody said") is None


def test_position_is_resolved_from_the_one_table_that_holds_it():
    """A second ordinal table is how the two would come to disagree — so it is exported, not copied."""
    src = open("widgets/imagenes/data.py", encoding="utf-8").read()
    assert "refs.position_index" in src
    assert "primero" not in src, "the ordinals must not be re-listed here"


# ── J · His own words license what touches his screen (V2-678) ─────────────────────────────────────────────
# Measured live 2026-09-12 (session 352268b5): the grammar deciding what may touch his canvas read our own
# `[SISTEMA]` notes glued to the turn. Since V2-851 F5 no note is glued to a turn (the notes mailbox went), so what
# stays is that his own orders still license, and an order about another card never replays this one.

# ── K · The close-ALL door finally gets a grammar (V2-678) ────────────────────────────────────────────────
# The most destructive thing the operator can trigger by accident: it bypasses the attention gate, executes
# immediately, and there is no undo. It was also the ONLY close door with no grammar behind it.
# Measured live 2026-09-12 (session 352268b5), twice in six seconds — both wiped his canvas.
@pytest.mark.parametrize("said", [
    "Close also the agenda. And reposition all the widgets.",   # 10:59:45, verbatim
    "I said reposition widgets. Do not close the widgets.",     # 10:59:51, verbatim
    "Do not close the widgets.",
    "Don't close the widgets, just move them",
    "reposition all the widgets",
    "cierra el widget de música",                               # ONE named card is not a close-all
    "no cierres los widgets",
    "sal de pantalla completa",                                 # V2-600 stays
])
def test_these_never_wipe_the_canvas(said):
    import voice.attention as attention
    assert attention.hard_interrupt(said) != "close", said


@pytest.mark.parametrize("said", [
    "close everything", "close all the widgets", "cierra todos los widgets",
    "quita todas las tarjetas", "ciérralo todo", "limpia el escritorio",
])
def test_a_real_close_all_still_fires(said):
    """The counterweight — the guard errs toward not firing, it must not stop firing."""
    import voice.attention as attention
    assert attention.hard_interrupt(said) == "close", said


def test_the_client_lane_carries_the_same_rule():
    """V2-252/V2-555 said this decision existed twice; V2-776 F removed the client copy instead of keeping the two
    in step: the client lane closes nothing, so the negation/clause rule lives only on the engine."""
    # V2-807 T-05: the client lane is gone entirely (it opened from a verb table too).
    from pathlib import Path
    assert not Path("frontend/app/services/voiceCommands.js").exists(), "the client lane is back"


# ── L · A third party answers in the language we ASK in (V2-678) ─────────────────────────────────────────
# «Now playing 75 vídeos.» — measured twice in one minute (11:00:11, 11:00:34) in an English session. Not a
# string of ours: it is YouTube's own label, in Spanish, because the music provider sent a hardcoded
# `Accept-Language: es-ES` from a module that reads the operator's language two functions above for its own
# sentences. The cheapest half of «todo pasa por el idioma del operador» is one header.
def test_the_music_provider_asks_in_the_operators_language():
    from connectors.music import youtube_audio as ya
    assert _with_language("en", ya._accept_language).startswith("en-US")
    assert _with_language("es", ya._accept_language).startswith("es-ES")
    src = open("connectors/music/youtube_resolve.py", encoding="utf-8").read()   # the provider request lives here
    assert '"Accept-Language": "es-ES' not in src, "a hardcoded provider locale is back"


def test_a_region_is_never_invented():
    """«en» → «en-EN» is not a locale. Anything without a real region travels as the bare language tag."""
    from connectors.music import youtube_audio as ya
    assert "en-EN" not in _with_language("en", ya._accept_language)


@pytest.mark.parametrize("title,is_count", [
    ("75 vídeos", True), ("26 videos", True), ("8 canciones", True), ("12 songs", True),
    ("100 Happy Tunes Vol 5", False), ("Here Comes the Sun", False), ("Positive Vibes Only", False),
])
def test_a_bare_count_is_not_a_name(title, is_count):
    """He asked for the Beatles and heard a row count. A title that is only a number says nothing about
    what is playing, so the caller says what he ASKED for instead."""
    from connectors.music import youtube_audio as ya
    assert ya.is_a_count_not_a_name(title) is is_count, title
