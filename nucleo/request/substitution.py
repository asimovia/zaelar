"""A send that enters in the PLACE of the model's own call — a verdict's substitution (CRIT-K2b R4, V2-893 L3) — is
born ASKING his consent on its row: a launch never runs an irreversible act directly, the yes lives on the task (rule 2).
The substituting reader marks the act it applies (`in_the_models_place`); the send task reads the mark when it is born
(`send_task.commission`) and waits on his yes instead of running. His yes runs it (`send_task_answer.answered`)."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar

_IN_ITS_PLACE: ContextVar = ContextVar("in_the_models_place", default=False)


@contextmanager
def in_the_models_place():
    tok = _IN_ITS_PLACE.set(True)
    try:
        yield
    finally:
        _IN_ITS_PLACE.reset(tok)


def active() -> bool:
    return bool(_IN_ITS_PLACE.get())


def ask_first(uid: str, art: dict, wid: str, action: str) -> str:
    """The row waits on his consent — the act's declared confirm question, else the language's generic one naming whom
    it reaches — instead of running. Returns the row."""
    from i18n import langs
    from nucleo import consent, on_his_behalf
    from nucleo.request import base, consent_ask, send_task
    pay = dict(art.get("payload") or {})
    q = consent_ask.question(base(wid), action, pay) or langs.current_language().data_confirm_generic.format(
        action=action, item=langs.current_language().data_confirm_item.format(
            item=on_his_behalf.shown_who(base(wid), action, pay) or base(wid)))
    send_task._question(uid, art, "consent", "", q, consent=consent.ASK_CONSENT)
    send_task._said_asked(wid, action, q)
    return uid
