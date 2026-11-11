"""One «yes» answers ONE question — the precedence between the three confirmation gates.

THREE THINGS CAN BE WAITING for the same word, and they are not variants of each other:

  · the WIDGET gate (`widgets.confirm`) — a deletion or an irreversible data-op is held.
  · the TASK gate (`nucleo.dispatch`, V2-126) — an irreversible errand was stopped before running.
  · the BROWSER gate (`widgets.navegador.tasks`, V2-202) — a click is blocked INSIDE the page, right now.

They can be open at the same time, and a bare «sí» does not say which one it means. So the answer goes to
exactly one, in that order, and the others stay waiting. That is not a style choice: two of the three arm
something irreversible, so an answer counted twice authorises a payment nobody authorised.

WHY THIS IS A MODULE. Both channels had their own copy of the precedence and one of them drifted. In
`voice/engine/llm/providers/nucleo.py` the browser gate was guarded by `had_pending_confirm` — the WIDGET
gate — instead of by whether the TASK gate had just resolved, so with a task and a click both pending a
single spoken «sí» released BOTH. The comment above that very block said «solo si el sí no ha resuelto ya
otra cosa», which is what kept anyone from looking: a comment asserting the invariant, and no test.
`nucleo/flash/probe.py` had it right. Measured 2026-08-24; zero tests covered the precedence in either
channel.

The decision is returned, never acted on: the caller does the talking and the emitting, because those are
the parts that genuinely differ between a channel with a mouth and one without.
"""
from __future__ import annotations

from dataclasses import dataclass

# The order IS the contract. Nearest-to-irreversible first: a held click is executing right now, a stopped
# task is about to, a widget op is the mildest — but the widget gate goes first because it is the one the
# model was told about in this turn's live state (`confirm.pending_line`), so it is what the operator was
# most likely answering.
GATES = ("widget", "task", "browser")


@dataclass
class Answered:
    """Which gate took the answer, and what it returned. `gate == ""` means nobody did."""
    gate: str = ""
    yes: bool = False
    result: object = None
    #: V2-873 — his reply carried a yes/no word and answered nothing waiting: the request still waiting, to be SAID
    waiting: str = ""

    def __bool__(self) -> bool:
        return bool(self.gate)


def resolve(text: str, *, widget=None, task=None, browser=None) -> Answered:
    """Give the operator's reply to the FIRST gate that is both open and able to read it.

    Each argument is a pair `(is_open, resolve)` or None when that gate does not apply to this caller. Both
    halves are callables so that nothing is asked — or resolved — once an earlier gate has taken the answer:
    the whole point is that the second gate never sees the word.

    A gate that raises is skipped, not fatal. Losing one confirmation is bad; letting an exception in the
    browser gate take down the turn that was resolving a payment is worse.
    """
    for name, pair in (("widget", widget), ("task", task), ("browser", browser)):
        if not pair:
            continue
        is_open, do_resolve = pair
        try:
            if not is_open():
                continue
            got = do_resolve(text)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(got, dict) and "still_waiting" in got:
            return Answered(waiting=str(got["still_waiting"] or ""))
        if got is None or got is False:
            # Open but the reply was not a yes/no it could read («¿y cuánto cuestan?»). It stays waiting, and
            # the answer does NOT fall through to the next gate: an ambiguous word is not an authorisation.
            return Answered()
        return Answered(gate=name, yes=_is_yes(got), result=got)
    return Answered()


def _is_yes(got) -> bool:
    """Each gate reports its yes/no differently; this is the one place that knows how."""
    if isinstance(got, dict):
        return bool(got.get("ok"))
    if isinstance(got, str):
        return got == "yes"
    return bool(got)


# ── HOW to reach each gate — which is the same everywhere, so it lives here ─────────────────────────────────
#
# The channels differ in the MOUTH (one speaks the acknowledgement, the other returns an action name), never in
# how a gate is asked. Keeping these adapters in the callers is what let the precedence drift in the first
# place, and it costs the caller a lazy import per gate on top.


def _widget_gate(brief=None):
    def _open():
        from widgets import confirm as _c
        return bool(_c.pending())

    def _do(text):
        from widgets import confirm as _c
        return _c.answers_pending(text, brief)      # the verdict on both channels (audit V2-783 P0-3)
    return (_open, _do)


def _task_gate(brief=None):
    def _open():
        from nucleo import dispatch as _d
        return bool(_d.parked_errands())

    def _do(text):
        from nucleo import dispatch as _d
        from nucleo.request import consent_ask as _ca
        words = operator_words(text)
        named = _named_parked(words)
        p = _d.pending_confirm(named) or {}
        if not p:
            return None          # several parked and his words name none: the brief's pick over their rows decides
        tid = str(p.get("task_id") or "")
        if _the_binding_reads_it(brief, p):
            # its row's question is answered by the brief's pick (`bind_the_answer`), not here — and when the brief read
            # his turn as an ANSWER that answered none of the waiting questions, the errand keeps waiting and he is TOLD
            # (V2-873: «yes, and close the video» left it waiting in silence, and he believed he had answered)
            return {"still_waiting": str(p.get("request") or "")} if _answered_none(brief) else None
        # With no pick, only a reply that IS one of the row's two declared answers decides (V2-878 §4b: the yes/no word
        # tables went — a longer reply is the brief's to read, never a word inside it).
        v = _ca.declared_answer(words, _row_options(p))
        if named and v is None and not _names_another_errand(words, tid):
            # He is talking about THIS errand: what he adds travels with the «yes» (`resolve_confirm`), and the clock
            # restarts — an errand he keeps talking about has not been left unanswered (three-tasks-at-once ES,
            # 2026-10-11: the game expired while he was asking for coins in it). A sentence that ALSO talks about
            # another errand is not folded in while it waits (EN 2026-10-11 02:58: «…btw for the monitor it has to be
            # at least 27 inches» folded into the game made the next sentence about the monitors «name» the game).
            _d.absorb_refinement(tid, words)
        return _d.resolve_confirm(v == "yes", tid) if v else None
    return (_open, _do)


def _the_binding_reads_it(brief, p: dict) -> bool:
    """The parked errand waits on its ROW (`dispatch.confirm.make_durable` gave it an `ask_id`) and the turn's brief
    read the binding question over the open asks: then the brief's pick among the two DECLARED answers is the reader
    (CRIT-C13), and his words are read only when no pick came (V2-873: «vale cierra los resultados» — a «vale» that
    opens another order — was read here as the yes to «this moves money… shall I go on?» before the brief, which saw
    the question, could say it answered none)."""
    if brief is None or not str((p or {}).get("ask_id") or ""):
        return False
    try:
        from nucleo.cli import worker_api_bind as _bind
        from nucleo.turn import verdicts as _v
        choice, info = _v.read(brief, _bind.KEY, None, min_confidence=0.0)
        return bool(info) and choice is not None
    except Exception as e:  # noqa: BLE001 — unreadable: the words decide, as before
        from loguru import logger
        logger.debug(f"confirm_gates: binding verdict unreadable — {type(e).__name__}: {e}")
        return False


def _names_another_errand(words: str, parked: str) -> bool:
    """Does the sentence name any errand besides the parked one `parked`?"""
    try:
        from nucleo.turn import named_errand as _ne
        return any(e["id"] != parked for e in _ne.named(words))
    except Exception as e:  # noqa: BLE001
        from loguru import logger
        logger.debug(f"confirm_gates: errands unreadable — {type(e).__name__}: {e}")
        return True


def _named_parked(words: str) -> str:
    """The id of the PARKED errand his words name most, or "". Several errands can wait on him at once, and the
    newest is not necessarily the one he answers: «Sí, móntalo. Y ponle que salte más alto…» is the game's yes,
    whatever was parked after it (three-tasks-at-once ES, 2026-10-11 02:04)."""
    try:
        from nucleo.turn import named_errand as _ne
        parked = [e for e in _ne.known() if e["parked"]]
        top = _ne.strongest(words, parked) if parked else None
        return str(top["id"]) if top else ""
    except Exception as e:  # noqa: BLE001 — unreadable: the most recent ask answers, as before
        from loguru import logger
        logger.debug(f"confirm_gates: parked errands unreadable — {type(e).__name__}: {e}")
        return ""


def operator_words(text: str) -> str:
    """The turn without the `[SISTEMA]` notes glued in front: our notice's «sin tu OK» is not his vote."""
    from nucleo.acts import errand as _esc
    return _esc.strip_system_notes(text) if "[SISTEMA]" in (text or "") else (text or "")


def _answered_none(brief) -> bool:
    """The brief read his turn as an ANSWER (`request_type`) and its binding pick answered none of the waiting rows."""
    try:
        from nucleo.cli import worker_api_bind as _bind
        from nucleo.turn import brief as _tb, verdicts as _v
        kind, _info = _tb.read(brief, _tb.REQUEST_KEY, "")
        choice, info = _v.read(brief, _bind.KEY, None, min_confidence=0.0)
        return kind == "answer" and bool(info) and str(choice) == _bind.NONE
    except Exception as e:  # noqa: BLE001
        from loguru import logger
        logger.debug(f"confirm_gates: answer verdict unreadable — {type(e).__name__}: {e}")
        return False


def _row_options(p: dict):
    """The two answers the parked errand's row declared (`make_durable`), or None for his language's own."""
    try:
        from nucleo.circuit import asker
        return asker.artefact(str(p.get("uid") or "")).get("options") or None
    except Exception:  # noqa: BLE001
        return None


def _browser_gate():
    # No separate «is it open?»: `answer_from_turn` already decides that with the state it owns. Asking twice
    # would mean two reads of the same thing, and two reads can disagree.
    def _do(text):
        from widgets.navegador import tasks as _t
        return _t.answer_from_turn(text)
    return (lambda: True, _do)


def resolve_all(text: str, *, widget: bool = False, brief=None, say=None) -> Answered:
    """The standard resolution: every gate a channel can answer, IN ONE CALL — which is the invariant.

    One call is what makes «the second gate never sees the word» true by construction instead of by the caller
    remembering to guard it. Splitting this back into one call per gate is the defect, whatever goes in between.

    `widget=True` includes the widget gate. Voice handles that one earlier in its turn (it has to speak the
    acknowledgement and return), so by default it is left out rather than resolved twice. `brief` is the turn's
    verdict handle: the task gate yields to its binding pick over the rows. `say(line)`, when given,
    says a yes/no word that answered nothing (V2-873: the parked errand keeps waiting, and he is told).
    """
    ans = resolve(text, widget=_widget_gate(brief) if widget else None,
                  task=_task_gate(brief) if brief is not None else _task_gate(), browser=_browser_gate())
    if say is not None and not ans and ans.waiting:
        from i18n import langs as _langs
        if line := str(getattr(_langs.current_language(), "errand_still_waiting", "") or ""):
            say(line.format(request=ans.waiting[:120]))
    return ans
