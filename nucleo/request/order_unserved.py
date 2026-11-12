"""nucleo/request/order_unserved.py — the order the brief identified, left without its act, opens ITS row.

THE CLASS (diagnosed 2026-11-12, group A2). A task is born from the model's CALL, never from the ORDER the brief read:
when the model served «mándale un whatsapp a Raquel diciendo que llego tarde» with a view of the messaging card, or
«ponle el alias Raquel a Rakel Karó» with `manage_widget_alias`, nobody owned the order — the completion by verdict
(`direct_action.complete`) runs only when NOTHING acted, `ask_outside_door.claimed` only when no call was made, and
the mouth's `unserved` line says «not done» without doing it. The only reader that crossed model≠verdict on the same
card was a second model pass (`repair_of_a_view`), kept as a fallback.

THE MECHANISM, at the turn's close, read off verdicts already paid for and what its doors RAN — never his words:

  · the brief is SURE of an order and of its act (`verdicts.sure_order`: `request_type = order` and
    `screen_action = card:act`, both at the one act floor), the order owes no words (`wants_words` ≠ tell), the turn
    did not end asking, did not escalate and did not address a live worker;
  · the turn did not SERVE it (`served`): no door ran that act, nor an act of that card with one of the same
    declared effects beyond reading (a write for a write, a send for a send), and the model never called it itself
    — by `widget_data`, or through the dedicated tool that drives the card (`play_music` is the music card's door:
    its lane runs the act and no data-op records it) — a call it made is its door's: it ran, asked, or was vetoed on
    purpose (or its completion ran re-aimed to another card, `direct_action.reaimed`). The model's valid call is never
    overruled (2.73): an order that only READS is the turn's to serve, and an act that stays on the card yields to the
    model's call that RAN there; one that only LOOKED where the turn surely asks to act (`_beyond_looks`) owes its
    QUESTION, never a second act;
  · then the order opens ITS row — the turn's while that is open, a new one when the model's other act already
    ended it (an ended row is never re-opened). An act that LEAVES becomes a send task
    (`send_task_words.from_verdict`: the person his word names, the text the model quoted of his words — it runs, or
    asks the ONE slot it lacks on that row); when his words resolve no person of his, or the act declares no slots,
    a Brain Worker takes it on its row with the `message` playbook (`ask_outside_door.to_message_task`). An act of
    the CARD runs by the same completion the empty turn uses (`direct_action.complete`, a payload his words can fill
    honestly), else ONE `ASK_FACT` question through the one asker on the order's row, naming the facts the act
    still needs — never a worker for an app act.

What stays the model's: a question (`ask_outside_door.held` owns it), an order the brief doubts, an act the turn made
under another name with the same effect.
"""
from __future__ import annotations

from nucleo.request import base, ends_asking, event as _emit, model, note

#: The retained kind on the row's `ask` artefact: his answer fills a payload key of THIS act (`inline_ask.rerun`).
KIND = "act"


def identified(brief) -> tuple[str, str]:
    """`(card, act)` the brief surely ORDERS at the act floor and does not answer with words; ("", "") otherwise. An
    unreadable brief orders nothing: the close's reader, its one caller, says so and opens nothing."""
    from nucleo.turn import brief as _tb, verdicts
    target, _info = verdicts.to_act(brief, _tb.TARGET_KEY, "")
    wid, _sep, act = str(target or "").partition(":")
    if not (wid and act) or str(target) == "none" or not verdicts.sure_order(brief, wid, act):
        return "", ""
    words, _w = verdicts.read(brief, _tb.WORDS_KEY, None)
    return ("", "") if str(words or "") == "tell" else (wid, act)


def _ran(ops) -> list[tuple[str, str]]:
    """`(card, action)` the turn's doors ran: its data-ops (`(wid, action)`) and its card acts."""
    out: list[tuple[str, str]] = []
    for w, a in ops or ():
        card = base(w)
        if card and (card, str(a or "")) not in out:
            out.append((card, str(a or "")))
    from nucleo import canvas_focus
    return out + [(base(c), str(a)) for c, _k, a in canvas_focus.this_turn_acts() if (base(c), str(a)) not in out]


def _same_effect(card: str, act: str, other: str) -> bool:
    """Do two acts of one card share a declared effect beyond reading or mounting (a write, a send, a start)?"""
    from widgets import effects
    beyond = {effects.DATA_READ, effects.PRESENT_MOUNT}
    return bool((effects.of(card, act) - beyond) & (effects.of(card, other) - beyond))


def served(wid: str, act: str, ops=(), model_calls=()) -> bool:
    """Did the turn serve `wid:act`? A door ran it, or ran an act of that card with the same declared effect, or the
    model CALLED it itself — by `widget_data`, or through the tool that drives that card (`acts/media.CARD_OF_TOOL`,
    the one ownership declaration) — then its door owns it, whatever became of the call; and the model's valid call is
    never overruled (node 2.73, measured live: the two last rules, stated in this module's docstring)."""
    from nucleo.acts.media import CARD_OF_TOOL
    from widgets import effects
    card, ran = base(wid), _ran(ops)
    if __import__("nucleo.flash.direct_action", fromlist=["x"]).reaimed(card, act) or any(   # re-aimed, or ran here
            c == card and (a == act or _same_effect(card, act, a)) for c, a in ran):
        return True
    calls = [c for c in model_calls or () if isinstance(c, dict) and isinstance(c.get("args"), dict)]
    called = [(base(c["args"].get("widget_id")), str(c["args"].get("action") or "")) for c in calls
              if c.get("name") == "widget_data"]
    if (card, act) in called or card in (CARD_OF_TOOL.get(c.get("name")) for c in calls):
        return True
    if not effects.of(card, act) - {effects.DATA_READ, effects.PRESENT_MOUNT}:
        return bool(ran or model_calls)          # a view he ordered, and the turn showed or did something: its choice
    return not effects.leaves(card, act) and any(c == card and (c, a) in ran for c, a in called)


def _beyond_looks(brief, wid: str, act: str, model_calls) -> list:
    """The model's calls without the LOOKS at the order's card where the turn surely asks to ACT there (the reading the
    call's own door makes, `data_ops.a_view_where_the_verdict_acts`, with `wants_words = act` at the ACT floor). A look
    is no serving call — and it RAN and stands (2.73): no act of the verdict runs beside it. What the order still owes
    is its QUESTION, the facts the act needs, on its row; an act that needs none owes nothing."""
    from nucleo.flash import data_ops
    from nucleo.turn import brief as _tb, verdicts
    wants, card = str(verdicts.to_act(brief, _tb.WORDS_KEY, "")[0] or ""), base(wid)
    return [c for c in model_calls or () if not (isinstance(c, dict) and isinstance(a := c.get("args"), dict)
            and base(a.get("widget_id")) == card
            and data_ops.a_view_where_the_verdict_acts(card, str(a.get("action") or ""), act, wants))]


def open_the_order(brief, *, said: str, reply: str, ops=(), model_calls=(), escalate_req=None, worker_acted=None,
                   emit=None, present=None, apply_widget_data=None) -> dict:
    """The close's reader: the sure order the turn served with another tool opens its row. Returns `{row, how, widget,
    act}` — `how` ∈ run · asked · worker · completed — or {} when the order was served, doubted, or is a question's.
    Never raises; never runs a model."""
    try:
        esc, wa = escalate_req or {}, worker_acted or {}
        text = " ".join(str(said or "").split())
        if not text or esc.get("send_task") or esc.get("v") is not None or wa.get("v") or ends_asking(reply):
            return {}
        from nucleo.turn import reply as _reply
        if _reply.asked():
            return {}                                      # the turn ended on a question through a door
        wid, act = identified(brief)
        if not wid or served(wid, act, ops, rest := _beyond_looks(brief, wid, act, model_calls)):
            return {}
        from widgets import effects
        model.past_an_ended_row()                          # the model's other act ended the turn's row: ITS row is new
        if effects.leaves(base(wid), act):
            got = _leaving(brief, wid, act, text, reply, emit)
        else:
            got = _of_the_card(brief, wid, act, text, reply, emit, present, apply_widget_data, len(rest) != len(model_calls or ()))
        if got:
            _emit(emit, "🚪 the order the brief identified was served with another tool → its row",
                  f"{wid}:{act} · {got['how']}", {"cat": "flash", "task_id": got.get("row", ""), "widget": wid,
                                                 "act": act, "how": got["how"], "ran": _ran(ops)})
        return got
    except Exception as e:  # noqa: BLE001 — never takes the turn down; the model's words stand
        note(e)
        return {}


def _leaving(brief, wid: str, act: str, said: str, reply: str, emit) -> dict:
    """An act that leaves: the send task from his words (run, or one slot asked on its row), else a worker on its row."""
    from nucleo.request import ask_outside_door, send_task_words
    from nucleo.turn import brief as _tb
    uid, how = send_task_words.from_verdict(wid, act, said, reply, reading=_tb.carried(brief) or None, emit=emit,
                                            on_missing="ask")
    if uid:
        return {"row": uid, "how": how, "widget": wid, "act": act}
    tid = ask_outside_door.to_message_task(wid, act, said, src="served_elsewhere", emit=emit)
    return {"row": "", "how": "worker", "worker": tid, "widget": wid, "act": act} if tid else {}


def _of_the_card(brief, wid: str, act: str, said: str, reply: str, emit, present, apply_widget_data, looked=False) -> dict:
    """An act of the card: the completion the empty turn uses — not beside a look that ran — else ONE fact question."""
    if not looked and present is not None and apply_widget_data is not None:
        from nucleo.flash import direct_action
        done = direct_action.complete(brief, operator_text=said, emit=emit or (lambda *a, **k: None), present=present,
                                      apply_widget_data=apply_widget_data, widget_id=wid, require_order=False,
                                      model_words=reply)
        if done:
            return {"row": "", "how": "completed", "widget": wid, "act": done}
    return _ask_the_facts(wid, act, said)


def needed(wid: str, act: str, payload: dict | None = None) -> list[str]:
    """The required payload keys of `wid:act` that `payload` leaves empty, in the manifest's order."""
    from nucleo.flash import payload_fill
    spec = payload_fill._payload_spec(wid, act)
    have = {k for k, v in (payload or {}).items() if str(v or "").strip()}
    return [str(k) for k, d in spec.items() if not payload_fill._optional(d) and k not in have]


def _ask_the_facts(wid: str, act: str, said: str) -> dict:
    """ONE `ASK_FACT` question on the order's row: the facts the act still needs; his answer fills the first on that
    row (`inline_ask.rerun` → the card's door, which asks again for the rest on the same row)."""
    keys = needed(wid, act)
    if not keys:
        return {}
    from nucleo import consent
    from nucleo.circuit import asker, ledger
    from nucleo.runtime_ids import next_seq
    from observability import identity
    row = model.opened(wid, act, text=said)
    if not row:
        return {}
    q = _facts_line(wid, keys)
    ask_id = f"{row}-q{next_seq('inline.ask')}"
    session = identity.session_id()
    entry = {"ask_id": ask_id, "corr_id": ask_id, "uid": row, "task_id": "", "inline": True, "action": act,
             "question": q, "answer": "", "result": None, "session": session, "consent": consent.ASK_FACT,
             "candidates": [], "options": [], "said": True,
             "retained": {"kind": KIND, "widget": wid, "action": act, "payload": {}, "slot": keys[0],
                          "needs": keys, "candidates": [], "text": said}}
    ledger.store().task_patch(row, session_id=session)
    asker.ask(row, entry)
    from nucleo.circuit import verdict as V
    from nucleo.turn import mouth
    mouth.say(q, verdict=V.ASKED.name, door=base(wid), key=ask_id)   # in the turn, or out of it when it has closed
    return {"row": row, "how": "asked", "widget": wid, "act": act, "ask_id": ask_id}


def _facts_line(wid: str, keys: list[str]) -> str:
    """The question for the facts an act of the card still needs, from the language table (`act_needs_facts`)."""
    facts = ", ".join(_spell(k) for k in keys)
    try:
        from i18n import langs
        from nucleo.flash import card_receipt
        tpl = str(getattr(langs.current_language(), "act_needs_facts", "") or "")
        if tpl:
            return tpl.format(card=card_receipt.card_name(base(wid)), facts=facts)
    except Exception as e:  # noqa: BLE001
        note(e)
    return f"{base(wid)}: {facts}?"


def _spell(key: str) -> str:
    """A payload key as words: `startTime` → «start time»."""
    import re
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", str(key or "")).replace("_", " ").lower()
