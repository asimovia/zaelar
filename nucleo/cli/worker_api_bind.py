"""nucleo/cli/worker_api_bind.py — which waiting task does an utterance answer? A verdict of the turn's brief (V2-851 §3a).

While tasks wait for his answer, the brief carries ONE more declared question — «does this message answer one of the
open questions?» — whose choices are the open questions by `ask_id`, plus `none`. Read asymmetrically
(`nucleo/turn/verdicts`):

  · an `ask_id` binds at the act floor (A7) when the verdict binds ALONE, at the LICENCE when the model answered (K2);
  · `none` at or above the VETO (0.85) binds nothing — it was a new request, a correction, a comment;
  · any other verdict is a doubt, and a doubt is ASKED: ASK_WHICH among the waiting tasks (an `ask` naming them) —
    with two or more waiting, `several` is the reader's own way to say the answer fits more than one;
  · no verdict at all (brief off, in flight, failed) binds only what the model itself routed (`answer_worker`), and
    only when one task waits — with several it is asked;
  · with SEVERAL waiting a pick binds only by IDENTITY (CRIT-K2b R6, V2-893 L4), never by its bar: the row that asked
    him since his last turn, a row our «which?» named (`circuit.asked_last`, by id), or a candidate no other waiting
    row declares — «sí» to two yes/no rows is asked, whatever the bar.

Never by length, never by a word list, never «the oldest». A screen answer needs none of this: it carries its
`ask_id` (`POST /api/tasks/{id}/answer`).
"""
from __future__ import annotations

KEY = "answers_open_question"
NONE = "none"
#: The declared doubt, offered when two or more questions wait: his answer fits more than one of them (battery C3,
#: 2026-11-05: «the first one» with two questions each offering a first candidate bound to the newest at 0.86 — no
#: choice let the reader say «either»). Chosen at or above the licence, it is ASKED, never bound.
SEVERAL = "several"
#: How many open questions ride in the brief (the choices of one question).
MAX_ASKS = 6

ANSWER, ASK_WHICH, NOTHING = "answer", "ask_which", "nothing"
#: The row is identified (our «which?» named it) but his words pick none of ITS candidates by identity: its own question
#: is put to him again — that makes it the row that asked — never a «sí»/«no» guessed for him (L4 audit P1-C).
REASK = "reask"

#: The doubt we last asked (ASK_WHICH): his words that fitted several tasks, kept so the turn that names the task
#: passes THOSE words on, not «the first one». One doubt at a time; it expires.
_DOUBT: dict = {"text": "", "at": 0.0}
DOUBT_TTL_S = 300.0

INSTRUCTIONS = ("The assistant's background tasks have asked the operator questions and are WAITING for his answer "
                "(each choice names one question by its id). Does the operator's message, in any wording or language, "
                "ANSWER one of those questions — give the information or the decision it asked for? Pick that "
                "question's id. Answer 'none' when it answers none of them: a new request, a correction of something "
                "else, a counter-question, a comment, or a message about something else.")


#: A choice that names one CANDIDATE of a question: `<ask_id>#<index>` — the door declared the candidates, so the
#: verdict picks among them (V2-851: «which Raquel» is the brief's reading, never a match of his words).
PICK = "#"


def _choices(a: dict) -> dict:
    q = str(a.get("question") or "")[:200]
    title = f" (task «{str(a.get('title') or '')[:80]}»)" if a.get("title") else ""
    cands = [str(c) for c in (a.get("candidates") or [])]
    if not cands:
        return {str(a["ask_id"]): f"it answers «{q}»{title}"}
    return {f"{a['ask_id']}{PICK}{i}": f"it answers «{q}»{title} choosing «{c[:80]}»" for i, c in enumerate(cands)}


def question(open_asks, last_reply: str = "") -> dict:
    """The brief's question, built from the open questions (`worker_api.open_asks()`); {} when nothing waits. A
    question whose door named its candidates offers one choice per candidate."""
    asks = list(open_asks or [])[:MAX_ASKS]
    if not asks:
        return {}
    criteria: dict = {}
    for a in asks:
        criteria.update(_choices(a))
    if len(asks) > 1:
        criteria[SEVERAL] = ("it fits more than one of these questions equally — what it gives (a position, a yes or "
                             "no, a value) is something more than one of them asks for, so which one it answers "
                             "cannot be told")
    criteria[NONE] = "it answers none of these questions"
    lr = (last_reply or "").strip()
    return {"instructions": INSTRUCTIONS + (f" [Our previous reply: {lr[:200]}]" if lr else ""), "criteria": criteria}


def bind(brief, *, model_answered: bool = False, asks=None) -> tuple[str, list]:
    """`(ANSWER, [ask])` · `(ASK_WHICH, asks)` · `(NOTHING, [])` for this turn. Never raises. A bound ask chosen by
    one of its candidates carries `choice` (the candidate's index). A sure choice whose question is no longer open
    (answered this turn by the act itself) binds nothing."""
    try:
        if asks is None:
            from nucleo.cli import worker_api
            asks = worker_api.open_asks()
        asks = list(asks or [])[:MAX_ASKS]
        if not asks:
            return NOTHING, []
        from nucleo.turn import verdicts
        choice, info = verdicts.read(brief, KEY, None, min_confidence=0.0)
        conf, floor = float((info or {}).get("confidence") or 0), verdicts.LICENCE if model_answered else verdicts.act_floor()
        if (not info or conf < floor) and _screen_order(brief):   # V2-903 a5: a sure order on screen is not his answer
            return NOTHING, []
        if not info or choice is None:
            if not model_answered:
                return NOTHING, []
            return (ANSWER, asks) if len(asks) == 1 and not asks[0].get("candidates") else _which(asks)
        by_id = {str(a["ask_id"]): a for a in asks}
        ask_id, _, idx = str(choice).partition(PICK)
        if len(asks) > 1 and conf >= floor and (ask_id in by_id or str(choice) == SEVERAL):
            if (how := _identified(by_id.get(ask_id), idx, asks)) != ANSWER:
                return (how, [by_id[ask_id]]) if how == REASK else (how, asks)
            if (ident := _asking(asks)) is not None and ident is not by_id.get(ask_id):
                if not ident.get("candidates"):       # the row that asked: identity before any pick (P1-A)
                    return ANSWER, [ident]
                yn = __import__("nucleo.request.consent_ask", fromlist=["x"]).declared_answer((brief or {}).get("judged") or "")
                return (ANSWER, [{**ident, "choice": 0 if yn == "yes" else 1}]) if yn else (REASK, [ident])   # F3
        if ask_id in by_id and conf >= floor:
            a = by_id[ask_id]
            if not idx:
                return (ANSWER, [a]) if not a.get("candidates") else (REASK, [a])   # the row is picked: ITS question
            if idx.isdigit() and int(idx) < len(a.get("candidates") or []):
                return ANSWER, [{**a, "choice": int(idx)}]
        if str(choice) == NONE and conf >= verdicts.VETO:
            return NOTHING, []
        if str(choice) == SEVERAL:
            return ASK_WHICH, asks
        if str(choice) != NONE and ask_id not in by_id and conf >= floor:
            return NOTHING, []
        return ASK_WHICH, asks
    except Exception:  # noqa: BLE001 — a classifier may never break a turn; nothing is bound blind
        return NOTHING, []


def _asking(asks):
    """The row that asked him since our last reply ALONE among the rows still waiting (`circuit.asked_last`), or None."""
    from nucleo.circuit import asked_last
    return next((a for a in asks if asked_last.asked(a, asks)), None)


def _identified(ask, idx: str, asks):
    """ANSWER when the pick is identified by id, never by words: the row that asked (it rules over any pick — a pick of
    another row is asked), a row our «which?» named (the ROW: a candidate row is asked its own question again, REASK),
    or a declared candidate no other row declares while every other row declares its own (an open question takes any
    answer) — a yes/no candidate never identifies a row. ASK_WHICH otherwise."""
    from i18n import langs
    from nucleo.acts.message_names import fold
    from nucleo.circuit import asked_last
    if (ident := _asking(asks)) is not None:
        return ANSWER if ask is None or ask is ident else ASK_WHICH
    if ask is None:
        return ASK_WHICH
    cands = list(ask.get("candidates") or [])
    if asked_last.named_by_which(ask):
        return REASK if cands else ANSWER
    pick = fold(cands[int(idx)]) if idx.isdigit() and int(idx) < len(cands) else ""
    others = [o for o in asks if o is not ask]
    yes_no = {fold(str(x)) for s in langs.supported() for x in (s.answer_yes, s.answer_no) if x}   # any language
    unique = bool(pick) and pick not in yes_no and all(
        o.get("candidates") and pick not in {fold(c) for c in o["candidates"]} for o in others)
    return ANSWER if unique else ASK_WHICH


def reask(ask: dict) -> str:
    """Put the row's OWN question to him again (screen and voice), noted as the row that asked. Returns the line."""
    from nucleo.circuit import asked_last, asker
    from nucleo.cli import worker_api
    art, _DOUBT["text"] = asker.artefact(str(ask.get("task_id") or "")), ""   # its own question: no doubt rides it (F3)
    worker_api.emit_ask(task_id=str(ask.get("task_id") or ""), ask_id=str(ask["ask_id"]), text=str(ask.get("question") or ""),
                        options=art.get("options"), kind=asker.kind_of(art))
    asked_last.note(str(ask["ask_id"]))
    return str(ask.get("question") or "")


def _which(asks: list) -> tuple[str, list]:
    """V2-903 a5: «which of these tasks?» needs two — ONE waiting row is asked its own question again."""
    return (REASK, asks[:1]) if len(asks) == 1 else (ASK_WHICH, asks)


def _screen_order(brief) -> bool:
    """The brief reads a sure order on what is on screen (a canvas close/show, or a card's act): not an answer."""
    from nucleo.turn import brief as _tb, verdicts
    canvas, act = verdicts.sure(brief, _tb.CANVAS_KEY, verdicts.act_floor()), verdicts.sure(brief, _tb.TARGET_KEY, verdicts.act_floor())
    return canvas[1] in ("close", "show") or act[1] not in (None, "", "none")


def answers_one(brief, *, model_answered: bool = False, asks=None) -> bool:
    """His turn answers ONE of the waiting rows — identified or not: a pick or `several` at the floor. A turn that does
    is attended (bound, or asked which), never a new request (V2-854 F4)."""
    try:
        from nucleo.turn import verdicts
        choice, info = verdicts.read(brief, KEY, None, min_confidence=0.0)
        floor = verdicts.LICENCE if model_answered else verdicts.act_floor()
        ids = {str(a["ask_id"]) for a in (asks if asks is not None else __import__("nucleo.cli.worker_api",
                                                                              fromlist=["x"]).open_asks())}
        return bool(info) and float(info.get("confidence") or 0) >= floor and (
            str(choice) == SEVERAL or str(choice).partition(PICK)[0] in ids)
    except Exception as e:  # noqa: BLE001 — unread: not an answer, the turn goes on as a request
        __import__("loguru").logger.debug(f"worker_api_bind: answers_one unread — {e!r}")
        return False


def answer_text(text: str) -> str:
    """What the bound question receives: his words, preceded by the words our doubt was about when he is resolving it."""
    import time
    said = " ".join(str(text or "").split())
    prior, _DOUBT["text"] = _DOUBT["text"], ""
    if prior and time.time() - float(_DOUBT["at"]) <= DOUBT_TTL_S and prior != said:
        return f"{prior} — {said}"
    return said


def ask_which(asks, *, text: str = "") -> str:
    """Put the doubt to him: the `ask` event naming the waiting tasks (`among`), and the line Flash says."""
    import time
    _DOUBT.update(text=" ".join(str(text or "").split()), at=time.time())
    from nucleo.circuit import asked_last                   # his next turn picking one of THESE rows is identity
    asked_last.note("", among=[a["task_id"] for a in asks])
    from i18n import langs
    from nucleo.cli import worker_api
    from nucleo.runtime_ids import next_seq
    titles = ", ".join(f"«{str(a.get('title') or a.get('question') or '')[:60]}»" for a in asks)
    line = str(getattr(langs.current_language(), "answer_which_task", "") or "").format(among=titles)
    worker_api.emit_ask(task_id="", ask_id=f"which-{next_seq('worker_api.which')}", text=line,
                        among=[a["task_id"] for a in asks])
    return line
