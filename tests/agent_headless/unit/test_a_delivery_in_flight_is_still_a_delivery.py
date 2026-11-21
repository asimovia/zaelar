"""A delivery that has ALREADY HAPPENED does not stop being one because the task is still running (V2-222, second face).

Measured in round 7 of `cheapest-monitor` (2026-08-23). The worker wrote three candidates—Dell, LG, and
MSI—in the task sheet and reported the step

    «Comparativa entregada en pantalla (hoja de resultados con los 3 finalistas)»

and for FIVE turns the agent replied “I’m still waiting,” “I’m still working on it,” “as soon as I have
something I’ll put it in front of you.” The judge flagged it as [high]: “the results were ALREADY available
when zaelar said it was still waiting.” But the prompt gave it no other way out, through TWO compounding paths:

1. The note was cut to exactly 60 characters, splitting a word: what arrived was “…results sheet with the”.
   It was cut exactly where it said that there WERE results and how many. A cut that ends cleanly reads like
   a complete sentence, so the model did not even have a hint that something was missing.
2. The block contained a prohibition (“DO NOT … say it is done”) and an instruction for the EMPTY case
   (“YOU STILL DON’T KNOW”), and NOTHING for the middle case: something already delivered while the task was
   still in progress. Without a branch authorizing it, the model resolved the collision through the only side
   the block allowed.

It is the same lesson that `dispatch.recently_ended_sessions` recorded for the first face: it was not
disobedience, but a contradiction—and no wording of either half alone fixes it.
"""
from __future__ import annotations

import pytest

from nucleo import dispatch
from nucleo.turn.prompt import live_tasks
from nucleo.turn.prompt import live_state as P

# V2-878 §2 — the running-errands block is FACTS ONLY now. The tests here that asserted the wording of its imperative
# paragraph (an order to tell, to deny, not to repeat) went with it; what each face reports stays tested as a fact.

_NOTA = "Comparativa entregada en pantalla (hoja de resultados con los 3 finalistas)"


@pytest.fixture(autouse=True)
def _clean():
    dispatch._SESSIONS.clear()
    dispatch._ENDED_SESSIONS.clear()
    yield
    dispatch._SESSIONS.clear()
    dispatch._ENDED_SESSIONS.clear()


def _viva(note: str = _NOTA):
    r = dispatch.SessionRecord(task_id="w1", goal="Buscar un monitor bueno para trabajar", kind="generic")
    r.status = "running"
    r.note = note
    dispatch._SESSIONS["w1"] = r
    return r


def test_y_ese_era_el_agujero_el_recorte_viejo_se_comia_justo_esa_parte():
    """Sensitivity test for the one above: with the 60-character cut, the sentence died at “with the”."""
    assert _NOTA[:60] == "Comparativa entregada en pantalla (hoja de resultados con lo"
    assert "finalistas" not in _NOTA[:60]


def test_una_nota_larga_se_corta_por_PALABRA_y_lo_dice():
    largo = "Comparativa entregada en pantalla " + "con muchisimos detalles adicionales " * 6
    out = live_tasks._short_note(largo)
    assert out.endswith("…"), "un recorte que acaba limpio se lee como una frase entera"
    assert not out.rstrip("…").endswith(" ")
    # It does not split a word in half: the last segment before the ellipsis is a word from the original.
    assert out.rstrip("…").split()[-1] in largo.split()


def test_una_nota_corta_no_se_toca():
    assert live_tasks._short_note("Comparativa entregada") == "Comparativa entregada"
    assert not live_tasks._short_note("Comparativa entregada").endswith("…")


# ── 3. THIRD face: the sheet has 35 candidates and this block said “queued” ───────────────────────────
# Measured in `search-secondhand-monitor__es` (2026-08-23 23:24), reading the system prompt for turns 4 and
# 5 IN FULL. The BROWSER block said, in the same prompt:
#
#     “… IT ALREADY HAS RESULTS. ‘Search for a second-hand monitor…’ ALREADY FOUND SOMETHING: it is not blocked or
#      waiting; it has results in the sheet. GIVE THEM TO IT this turn”
#
# and THIS block, a few lines above:
#
#     “BACKGROUND TASKS IN PROGRESS (… DO NOT restart or say it is done): ‘Search for a monitor…’—queued
#      (23s elapsed) … the answer is that YOU STILL DON’T KNOW”
#
# Two records describing ONE task and contradicting each other. The turn replied “I’ll let you know as soon as I
# have results” twice, with 35 real listings with names and prices in the sheet, and the round was scored as
# [high] disobedience ×3. It was not: a prompt that argues with itself has no obedient answer.
#
# The data existed and was propagated: `pending_summaries()` publishes `kept` (what the worker reports with
# `hbnote considered --kept N`) and it is the SAME signal that the browser block reads from V2-200. This
# block never looked at it, so it stuck with the phase—which the worker had not updated since the task entered the queue.


def _con_candidatos(kept: int = 35):
    r = dispatch.SessionRecord(task_id="w2", goal="Buscar un monitor de segunda mano de al menos 27 pulgadas",
                               kind="web")
    r.status = "running"
    r.phase = "en cola"          # the MEASURED phase: the worker never updated it
    r.note = ""
    r.kept = kept
    dispatch._SESSIONS["w2"] = r
    return r


# ── 4. “found” is NOT “on screen”—the face says what the signal says ────────────────────────────────────
# Measured in `search-secondhand-monitor__es` (2026-08-24 01:47), in the round that PASSED. Turn 6 said
#
#     “I have results ON SCREEN now, Marc. …the MSI MAG at €70, …”
#
# at 130 s, and the first row of the sheet was written at 142. Twelve seconds of a false claim about what the
# operator had in front of them—and the judge flagged it as [high] “unsupported claim,” which is how it looks from outside.
#
# It did NOT invent the names: we had given them to it in a note (V2-223, `offered: 6 rows`). The false part
# was the LOCATION. And we told it the location in two ways, both written today:
#
#   · this block’s bit, which I finalized that same night by saying “they are in the sheet”
#   · the browser face, whose imperative said “it has results in the sheet. GIVE THEM TO IT”
#
# The worker writes `kept` with `hbnote considered --kept N` to report its SCOPE: it says how many it has
# found, never where they are. It is related to V2-209 (“Here it is” over an empty card) and V2-176 (“Done.”
# over a task that had just started): a phrase of OURS is where a false claim slips in without anyone writing it.


# ── 4. THE SYMMETRICAL FACE: a setback is also reported (V2-348) ─────────────────────────────────────
#
# Measured in `search-buy-used-car`, round 8 (2026-08-26, ES set). coches.net served an error page after the
# landing page; the worker diagnosed it, reported it as a progress note, and switched to AutoScout24 on its own—all good. The note
# that reached that turn’s prompt said, literally:
#
#     «coches.net caído tras portada (página de error)»
#
# and the turn replied: “It is still alive with a recent signal: it is entering the marketplace and making progress. It
# has not found any cars yet, but it is not stuck.” Not a word about the failed site—just when the operator had asked
# “did you restart it from scratch in the end, or is it still stuck?” The judge flagged it [medium]: “It hid from the
# user that the main site had failed… The user deserved to know that coches.net did not work.”
#
# And it was NOT disobedience; for the third time, the same pattern: the block had a branch for STUCK, a branch for NO
# reported note, and a branch for DELIVERED/ALREADY FOUND. None for a note bringing BAD news. The asymmetry lived in
# the prompt—only good news carried a “report it” instruction—so the model described the half named by the block and
# summarized the other as “it is making progress.” The branch goes INSIDE the same imperative as the one above,
# not in a standalone sentence: two orders in a paragraph come down to a coin toss.
_NOTA_FALLO = "coches.net caído tras portada (página de error)"
