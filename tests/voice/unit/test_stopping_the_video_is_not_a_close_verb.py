"""V2-753 — «Páralo, y vuelve al inicio»: the right call, eaten five times by a verb table.

MEASURED, live session 46dcfcb4 (2026-09-22, 22:0x). The operator had opened the video card, searched
for Boeing 747 videos and played the third result. Everything worked. Then:

    «Uf, me he equivocado. Páralo, y vuelve al inicio.»

The model answered with the CORRECT call. `youtube:close` is declared as «lo detiene de verdad y lo
quita del reproductor», which is both halves of that order. The V2-635 data-op guard read the
sentence, found no verb from `_CLOSE_VERB_RE` — «parar» is not a close verb and must never be one —
called it context-bleed and ATE it. Then again. And again. Five `🛡️ data-op close ignorada` in ninety
seconds, under a voice that kept saying «lo paro y vuelvo al inicio» over a video that never stopped:

    +3053.7  zaelar   «Vale… lo paro y vuelvo al inicio.»          ← no widget/action in the turn
    +3067.2  🗣       «Pero veo que es incapaz de pararlo.»
    +3070.7  🗣       «Y tampoco vuelves al inicio a ver el catálogo.»
    +3077.9  zaelar   «perdona, Paco. Lo corto y te dejo el catálogo a la vista.»  ← nothing again

He had reported the same failure in the previous session. THREE independent defects were stacked on
that one order, and each is pinned below.

## 1 · The question's own answer was decapitated at 90 characters

`turn_brief.target_question` cut every declared `desc` at 90 chars. `youtube:show_tab` declares:

    «CAMBIA de pantalla dentro del reproductor SIN tocar lo que está sonando. 'inicio' es el
     catálogo/dashboard donde están los resultados… es lo que responde a «vuelve al catálogo», «a la
     página de inicio», «enséñame otra vez la lista para cambiar»…»

V2-742 wrote that second sentence INTO the manifest so the decision could find the action. The cut
fell at «'inicio' es el ca». Measured against the real API over his own words:

    «vuelve al catálogo»                          90 chars → none 0.77   ·  200 → show_tab 0.96
    «y tampoco vuelves al inicio a ver el catálogo» 90 → show_tab 0.32   ·  200 → show_tab 0.83
    pause 1.00 · next 0.94 · search 0.99 · volume_up 1.00 — unmoved in both

A description is product data and the right place to repair a routing miss (V2-726 §4-bis) — but only
the part of it that ARRIVES can decide anything.

## 2 · «vuelve al inicio» is ambiguous, and the manifest did nothing to help

`restart` said «reinicia el vídeo desde el principio», so «Páralo, y vuelve al inicio» came back as
`youtube:restart` — a verdict that would have RESTARTED the video he had just asked to stop. With the
two descriptions sharpened (restart says it keeps playing; close says it PARA), the same sentence
comes back `youtube:close` at 0.93, and «ponlo otra vez desde el principio» stays `restart` at 0.99.

## 3 · A grammar decided a route, alone, and the fix already existed one branch over

The canvas [[close]] guard has consulted a second reader since V2-635 (`show_target.close_has_order`:
grammar first, a confident Jev second). The DATA-OP close guard never got the escape hatch — the same
rule installed on one of two branches, and the un-repaired one is the branch that fires on a real
player. And then it cascaded: the empty promise tripped the promise backstop, which FORCED a
`claude_code` worker that drove a headless browser for four minutes to stop a video, over a brief
that had answered `escalate_or_inline = handle_inline` at 1.00. He had to say «yo no te he pedido que
hagas nada… páralo inmediatamente».

Deterministic here on purpose — the live half is the numbers above. What this pins is the RULE and
its WIRING.

Run: .venv/bin/pytest tests/voice/unit/test_stopping_the_video_is_not_a_close_verb.py
"""
from __future__ import annotations


import json
import pathlib
import threading



_ENGINE = pathlib.Path(__file__).resolve().parents[3]

#: His sentence, verbatim from the transcript. A paraphrase would be a test of a test.
HIS_WORDS = "Páralo, y vuelve al al inicio."


def _brief(answers: dict, *, open_ids=("youtube",)):
    """A brief handle in the REAL shape `jev.ask_many` returns — the same builder node 2.68 uses.

    Built rather than mocked: what is under test is `turn_brief.read`'s own path through it, and a
    double with a convenient shape would pass with the reader disconnected.
    """
    ev = threading.Event()
    ev.set()                    # `jev.peek` returns None on an unset event: an unset one tests nothing
    return {"event": ev, "turn_id": "t-1", "open_ids": list(open_ids),
            "result": {k: {"choice": c, "confidence": f} for k, (c, f) in answers.items()}}


# ── 1 · THE QUESTION CARRIES THE SENTENCE THAT MAKES AN ACTION ROUTABLE ───────────────────────────

# ── 2 · THE TWO DESCRIPTIONS THAT MADE «vuelve al inicio» MEAN THE WRONG THING ────────────────────

def test_close_declares_that_it_STOPS_and_restart_declares_that_it_does_not():
    """The repair lives in the widget's own declaration (V2-726 §4-bis), so it reaches every reader
    — the decision model, the prompt catalogue and the probe — instead of one of them."""
    acts = json.loads((_ENGINE / "widgets/youtube/manifest.json").read_text(encoding="utf-8"))["actions"]
    close, restart = acts["close"]["desc"].lower(), acts["restart"]["desc"].lower()
    # V2-755 — the anchor was the literal «PARA» and that literal is what swallowed «Vale, para el
    # vídeo»: `close` opened with «PARA el vídeo de verdad», `pause` was declared in four words, and
    # the bare verb belonged to nobody (`none` 0.65, live session 665e666a). The competitor now is
    # `pause`, so this pins the CLAIM instead: close says it stops for real AND leaves the card empty,
    # which is the half `pause` does not do. His compound order still measures `close` 0.89.
    assert "deja de sonar" in close and "sin vídeo" in close, "close has to SAY that it stops it for real"
    assert "párralo y vuelve al inicio" in close, "…and V2-753's own sentence stays declared"
    assert "sigue sonando" in restart or "sigue reproduci" in restart, (
        "restart has to say it KEEPS PLAYING — «reinicia el vídeo desde el principio» is what made "
        "«Páralo, y vuelve al inicio» come back as `restart`")
    # V2-754 — and it must NOT say «inicio» at all. The first repair wrote «vuelve al inicio DEL VÍDEO»
    # into it to split it from `show_tab`, and «vuelve al inicio del widget de vídeo» then came back as
    # `restart` at 0.99 (session 3afe34a8): the word he uses for the card's home screen cannot live in
    # the description of the action that rewinds the video.
    assert "inicio" not in restart, "«inicio» is the card's home screen in his mouth, not the video's second 0"


# ── 3 · THE GRAMMAR PROPOSES; THE PAID VERDICT DECIDES ────────────────────────────────────────────

# ── 4 · THE SEAM — a verdict nobody reads is what V2-750 already paid for ─────────────────────────

#: The other half of the same session (+3053.7), in English this time: no close verb, the verdict reads the close.
HIS_WORDS_EN = "Ugh, wrong one. Stop it and go back to the start."


#: The sentence the pure-show gate ate a close on (`gate_shadow · pure-show`, +3073.7) — it has «ver» in it.
PURE_SHOW = "Y tampoco vuelves al inicio a ver el catálogo"

