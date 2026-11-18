"""How a turn hands a send to its owner: it marks it, and at the turn's close the owner opens the draft and speaks.

Two ways in, and both only HAND OVER — neither resolves, asks or sends anything:
  · `claim` — the model called an act whose event type is a MESSAGE (`send_receipt.family == "send"`): the call does
    not run; its fields ride as a hint;
  · `from_brief` — the model made no such call, but the turn's reading is SURE he ordered a message sent.
`speak` runs once per turn, after the model's stream: the owner reads his words and the turn says the owner's line.
"""
from __future__ import annotations

from loguru import logger

KEY = "send_owner"


def _note(e: Exception) -> None:
    logger.debug(f"send.turn: {type(e).__name__}: {e}")


def is_message(wid: str, action: str, payload: dict | None = None) -> bool:
    """Is this act a message to somebody (its event type's family), as opposed to any other act that leaves?"""
    try:
        from nucleo.request import base
        from nucleo.request import send_receipt
        return bool(wid and action) and send_receipt.family(base(wid), action, payload or {}) == "send"
    except Exception as e:  # noqa: BLE001
        _note(e)
        return False


def claim(escalate_req: dict, text: str, wid: str, action: str, payload: dict | None, emit=None) -> bool:
    """The model's call of a message act: handed to the owner (True), never run by the turn. False for any other act."""
    if not is_message(wid, action, payload):
        return False
    hint = {**dict(payload or {}), "_act": str(action)}
    if KEY in escalate_req:          # several messages in one sentence: each is the owner's, one after the other
        escalate_req[KEY].setdefault("more", []).append(hint)
    else:
        escalate_req[KEY] = {"said": " ".join(str(text or "").split()), "hint": hint}
    if emit is not None:
        try:
            emit("brain", "📨 a message goes to its owner (nucleo/send)", text=f"{wid}:{action}", role="system",
                 extra={"cat": "flash", "id": wid, "action": action})
        except Exception as e:  # noqa: BLE001
            _note(e)
    return True


def from_brief(escalate_req: dict, text: str, brief) -> bool:
    """No message call this turn, but the reading is SURE he ordered a message sent: the same hand-over."""
    if KEY in escalate_req or brief is None:
        return False
    try:
        from nucleo.request import ask_outside_door
        wid, act = ask_outside_door._sure_leaving_act(brief)
        if not wid:
            wid, act = ask_outside_door._unserved_order(brief)
    except Exception as e:  # noqa: BLE001
        _note(e)
        return False
    if not is_message(wid, act):
        return False
    escalate_req[KEY] = {"said": " ".join(str(text or "").split()), "hint": {}, "by": "brief"}
    return True


async def speak(escalate_req: dict, spoken_text: str, send, speech, brain=None) -> str:
    """Open the draft for a handed-over send and say its line after what the turn said. Returns the turn's text."""
    o = escalate_req.get(KEY)
    if not isinstance(o, dict) or o.get("line") is not None:
        return spoken_text
    from nucleo.send import gate, owner
    last, before = gate._context(brain) if brain is not None else ("", [])
    o["line"] = ""
    try:
        o["line"] = await owner.intake(o.get("said") or "", o.get("hint") or {}, last_line=last, before=before[:-1],
                                       by=str(o.get("by") or "call"))
        from nucleo.send import draft
        if o["line"] and draft.current() is not None:   # the other messages of the same sentence wait their turn,
            for more in o.get("more") or ():            # each from its own call — never his whole sentence read again
                draft.queue(o.get("said") or "", more, "queued")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"send.turn: the owner did not open the draft — {e!r}")
        return spoken_text
    said = str(spoken_text or "").strip()
    from nucleo.send import draft as _d
    d = _d.current()
    # Our own question about the message stands and the draft adopts it — unless the owner's line is the confirmation:
    # a confirmation he never heard is never the one his yes answers.
    if not o["line"] or (o.get("quiet") and not (d is not None and d.asked == _d.CONFIRM)):
        return spoken_text
    send((" " if said else "") + speech.sanitize(o["line"], drop_metadata=False))
    owner.heard(o["line"])
    return f"{said} {o['line']}".strip()


def _message_call(calls) -> dict | None:
    """The first call of the turn — made or held by the verdict's gate — whose act is a message: its payload."""
    for c in calls or ():
        a = c.get("args") if isinstance(c, dict) and isinstance(c.get("args"), dict) else None
        if a and c.get("name") == "widget_data" and is_message(str(a.get("widget_id") or ""), str(a.get("action") or ""),
                                                               a.get("payload") if isinstance(a.get("payload"), dict) else {}):
            return dict(a.get("payload") or {}) if isinstance(a.get("payload"), dict) else {}
    return None


def _asked_about_a_message(brief, reply: str, said: str) -> bool:
    """The turn ended on OUR question about a message (who it is for, what to say) without reaching any door: the
    card the reading names is the messaging card with a message act read, or the question names the people his word
    reaches. Read off the verdicts and the directory, never off phrasing."""
    try:
        from nucleo.acts import message as _message
        from nucleo.request import ask_outside_door as _aod, ends_asking
        from nucleo.turn import verdicts
        which = _message.asked_which(reply, said)      # it named the people his word reaches, whatever its last mark
        if not (which or ends_asking(reply)):
            return False
        for wid, act in (_aod.named_act(brief), _aod._leans_out(brief)):
            if act and is_message(wid, act):
                return True
        wid, _i = verdicts.read(brief, "catalog_widget", None)
        wid = str(wid or "")
        if not wid or wid == "none":
            return False
        acts = [a for a in _aod.leaving_acts(wid) if is_message(wid, a)]
        return bool(acts) and (which or _aod._reads_an_act(brief, wid, acts))
    except Exception as e:  # noqa: BLE001
        _note(e)
        return False


def _ordered_on_the_messaging_card(brief) -> bool:
    """The reading is an ORDER that wants an act, on a card whose acts include a message — a lean, never a decision:
    the owner's read of his words decides whether it is a message to send (`owner.LEAN`)."""
    try:
        from nucleo.request import ask_outside_door as _aod
        from nucleo.turn import verdicts
        kind, info = verdicts.read(brief, "request_type", None)
        words, _w = verdicts.read(brief, "wants_words", None)
        wid, _i = verdicts.read(brief, "catalog_widget", None)
        wid = str(wid or "")
        if not (info and str(kind or "") == "order" and str(words or "") != "tell" and wid and wid != "none"):
            return False
        return any(is_message(wid, a) for a in _aod.leaving_acts(wid))
    except Exception as e:  # noqa: BLE001
        _note(e)
        return False


async def at_close(escalate_req: dict, said: str, brief, calls, spoken_text: str, send, speech, brain=None) -> bool:
    """The turn's close: every way a message order could still leave the turn — a call the verdict's gate held, the
    reading's sure act, a sure order nothing served, our own question about a message — is handed to the owner HERE,
    and nothing else at the close opens a row, a question or a worker for it. True when the send is the owner's."""
    if KEY in escalate_req:
        return True
    payload = _message_call([*(escalate_req.get("held_calls") or ()), *(calls or ())])
    by = "held call" if payload is not None else ""
    if not by and brief is not None and from_brief(escalate_req, said, brief):
        by = "brief"
    if not by and brief is not None and _asked_about_a_message(brief, spoken_text, said):
        by = "our question"
    if not by and brief is not None and _ordered_on_the_messaging_card(brief):
        by = "order"
    if not by:
        return False
    escalate_req.setdefault(KEY, {"said": " ".join(str(said or "").split()), "hint": payload or {}})
    escalate_req[KEY]["by"] = by
    escalate_req[KEY]["quiet"] = by == "our question"      # the turn's own question about it stands
    await speak(escalate_req, spoken_text, send, speech, brain)
    if escalate_req[KEY].get("line") == "" and by == owner_lean():
        escalate_req.pop(KEY, None)       # a lean the owner's read refused: the close goes on as for any other turn
        return False
    if escalate_req.get("v") is not None and by == "held call":
        escalate_req["v"] = None          # the verdict held the message call as its errand: the owner has it now
    escalate_req.pop("send", None)
    return True


def owner_lean() -> str:
    from nucleo.send import owner
    return owner.LEAN
