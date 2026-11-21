"""What a confirmation question LEAVES behind: one live question per act, and one line when he answers it.

His rule (2026-11-18), for ANY act that asks — a send, a deletion, a write: there is ONE live confirmation question
per act. When the terms of what is being confirmed change (the text, the recipient, «one file» → «three files») the
question before it is void: it is SUPERSEDED (its card is retracted and no yes can reach it any more). And when he
answers, the question does not just vanish: it becomes one line of the conversation's RECORD, in the system's own
colour — «Ricard confirms that the message is sent» / «…does not confirm it».

A question's identity is its act and its terms (`terms_of`); the row keeps one question at a time (`asker.ask`), so a
new one over the same row replaces the one before, and this module says so (`superseded`) and writes the record line
(`resolved`). The line is worded by a model from the fact (`nucleo/wording`), never a fixed sentence; the language's
own line is the last resort.
"""
from __future__ import annotations

import hashlib
import json

from loguru import logger

#: The observer kind both events travel by: {task_id, ask_id, outcome: yes · no · superseded, text (the record line)}.
EV = "ask_resolved"
YES, NO, SUPERSEDED = "yes", "no", "superseded"

RECORD = (
    "You write ONE line for the RECORD of a conversation between a person and his assistant, in {language}. It is not "
    "speech and it is not addressed to anyone: it states, in the third person, what the person decided. Start with "
    "his name as given. One short clause, no quotes, no preamble, no full stop needed. Say exactly what the fact "
    "states: what he confirmed or did not confirm, in a few words taken from the question — never tasks, processes "
    "or inner workings. The examples show the shape, do not copy them. Reply with the line only."
)
FACTS = {YES: "{name} CONFIRMED what he was asked. The question was: «{question}»",
         NO: "{name} did NOT confirm what he was asked; it is not done. The question was: «{question}»"}
KEYS = {YES: "ask_confirmed", NO: "ask_refused"}


def terms_of(entry: dict | None) -> str:
    """The identity of what a question asks him to confirm: its act and its terms (the retained call), as a short
    hash. Two questions with the same act and other terms are two questions. "" when it retains nothing."""
    retained = (entry or {}).get("retained") if isinstance((entry or {}).get("retained"), dict) else {}
    if not retained:
        return ""
    try:
        body = json.dumps(retained, sort_keys=True, ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001
        body = repr(retained)
    return hashlib.sha1(body.encode("utf-8")).hexdigest()[:12]


def _emit(label: str, text: str, **extra) -> None:
    try:
        from voice.observer import emit
        emit(EV, label, text=text, role="system", extra={"cat": "worker", **extra})
    except Exception as e:  # noqa: BLE001 — the record is lost, the decision stands
        logger.debug(f"ask_trace: not emitted — {e!r}")


def superseded(uid: str, old: dict | None, new: dict | None) -> bool:
    """A new question is about to replace `old` on row `uid`, still unanswered: say so. The screen retracts the old
    card when the new one arrives; an answer to the old id is refused by the answer door (it is no longer the row's).
    True when one was superseded."""
    old, new = old or {}, new or {}
    a, b = str(old.get("ask_id") or ""), str(new.get("ask_id") or "")
    if not (uid and a and a != b and old.get("state") in (None, "pending")):
        return False
    _emit("↩ question superseded — its terms changed" if terms_of(old) != terms_of(new) else "↩ question superseded",
          "", task_id=uid, ask_id=a, by=b, outcome=SUPERSEDED, terms=terms_of(old), new_terms=terms_of(new))
    return True


def _his_name() -> str:
    try:
        from memory import api as memory
        name = str((memory.state() or {}).get("operator_name") or "").strip()
        if name:
            return name.split()[0]
    except Exception as e:  # noqa: BLE001
        logger.debug(f"ask_trace: his name unread — {e!r}")
    from i18n import langs     # every shipped pack carries it (genesis voice.json): no constant of one language here
    return str(getattr(langs.current_language(), "operator_generic", "") or "")


async def resolved(uid: str, entry: dict | None, said: str) -> str:
    """He answered a confirmation question with a yes or a no: its ONE record line, worded from the fact, goes to the
    conversation (the wall paints it in the system's colour and keeps it in its place). Returns the line."""
    if said not in (YES, NO) or not uid:
        return ""
    try:
        from i18n import langs
        from nucleo import wording
        name = _his_name()
        question = " ".join(str((entry or {}).get("question") or "").split())[:300]
        plain = str(getattr(langs.current_language(), KEYS[said], "") or "").format(name=name)
        line = await wording.word_soon(FACTS[said].format(name=name, question=question), examples=(plain,),
                                       fallback=plain, system=RECORD)
        if line:
            _emit("✅ he confirmed" if said == YES else "✖ he did not confirm", line, task_id=uid,
                  ask_id=str((entry or {}).get("ask_id") or ""), outcome=said, terms=terms_of(entry))
            from nucleo.conversation_host import wall_notes
            wall_notes.record(line)                 # its line on the chat wall
        return line
    except Exception as e:  # noqa: BLE001
        logger.debug(f"ask_trace: the record line was not written — {e!r}")
        return ""


async def answered(answer, entry: dict | None, decision, corr_id: str, text: str, **kw) -> bool:
    """The answer door's wrapper: run `answer`, and when it took his yes or his no to a CONSENT question, leave the
    record line. What he said is read BEFORE the answer clears the question (`decision`, the door's own reader)."""
    from nucleo.circuit import asker
    e0 = dict(entry or {})
    said = decision(str(e0.get("question") or ""), text, kw.get("choice"), e0.get("options")) \
        if e0 and asker.kind_of(e0) == asker.KIND_CONSENT else None
    took = await answer(corr_id, text, **kw)
    if took:
        keep_answer(e0, text)
    if took and said in (YES, NO):
        resolved_soon(str(e0.get("uid") or ""), e0, said)
    if took and said == NO:              # what the request wrote where he reads it does not outlive his no
        __import__("nucleo.request.send_errand", fromlist=["x"]).withdraw(str(e0.get("uid") or ""))
    return took


#: The row slot of what he ANSWERED to the row's questions, in order — his words about the request, with the question.
ANSWERS = "his_answers"


def keep_answer(entry: dict | None, text: str) -> None:
    """His answer stays on the row with the question it answered: a later door of the same request reads what he
    already said (a «yes, go ahead» to the worker's own question is not asked again at the exit). Never raises."""
    try:
        uid, said = str((entry or {}).get("uid") or ""), " ".join(str(text or "").split())
        if not (uid and said):
            return
        from nucleo.circuit import ledger
        rows = list(ledger.store().artifact_get(uid, ANSWERS) or [])
        rows.append({"q": str((entry or {}).get("question") or "")[:200], "text": said[:400]})
        ledger.store().artifact_put(uid, ANSWERS, rows[-12:])
    except Exception as e:  # noqa: BLE001
        logger.debug(f"ask_trace: his answer not kept on the row — {e!r}")


def his_answers(uid: str) -> list[str]:
    """What he answered on this row, each with its question: «asked "…" he answered: …»."""
    try:
        from nucleo.circuit import ledger
        return [f'asked «{r.get("q")}» he answered: {r.get("text")}' for r in (ledger.store().artifact_get(uid, ANSWERS) or [])
                if str(r.get("text") or "").strip()]
    except Exception as e:  # noqa: BLE001
        logger.debug(f"ask_trace: his answers unread — {e!r}")
        return []


def resolved_soon(uid: str, entry: dict | None, said: str) -> None:
    """Schedule `resolved` on the running loop: the answer door never waits for a wording."""
    try:
        import asyncio
        task = asyncio.get_running_loop().create_task(resolved(uid, dict(entry or {}), said))
        _tasks.add(task)
        task.add_done_callback(_tasks.discard)
    except RuntimeError as e:
        logger.debug(f"ask_trace: no loop for the record line — {e!r}")


_tasks: set = set()
