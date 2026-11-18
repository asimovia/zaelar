"""nucleo/request/send_errand.py — «send a message to X» is ONE Brain Worker task, owned end to end (V2-931).

Measured on his engine (2026-11-17, build 153): a send had no owner. About twenty-three decision points on the happy
path — Flash's inline call kept on a row with re-derived slots, a show guard that swapped it for a show, five places
that could give birth to a send row, an exit door that judged every slot against the words of ONE turn, a supersede
that cancelled the waiting question, and a binder that read his «sí» as `none` — asked him again and again and sent
nothing. Every fix had added a lane; none had removed one.

Now there is one path, and he hears three lines — the ask, «sending», «sent / failed, and why»:

  · the turn — any wording, any language, the model's call or the reading of the order — hands his words to ONE
    worker task with the `message` playbook (`hand_over`, `start`, `context`). Flash never runs a send, never asks
    about one and never says it went; its one line is «I'll get the message ready»;
  · the worker (Claude Code with an Anthropic model, `on_claude`) finds the person in his contacts (asking him until
    it is the right one), writes his words as a DRAFT into the card — her conversation opens with the text in its box
    — and calls the send. It says nothing itself;
  · the exit door asks ONE confirmation (`exit_gate.gate`): «the message for <her> is ready — shall I send it?»,
    spoken as it is and on screen. The act is retained on the task's row;
  · what he says next reaches the task through the switchboard (`nucleo/switchboard`, before Flash runs). A plain yes
    — in any wording, or the screen's button — runs the retained act at once: no session is resumed, he hears «OK,
    sending it». A plain no ends it. Anything else resumes the worker with his words (it confirms with
    `bridge act confirm_send`, rewrites the draft, or cancels);
  · the engine follows the queued order to the connector's own receipt (`nucleo/request/send_receipt`) and says the
    final line from it; the task's row ends with that verdict.
"""
from __future__ import annotations

from loguru import logger

#: The playbook a send task follows (`nucleo/workers/prompts/playbook.MESSAGE`).
PLAYBOOK = "message"


def _note(e: Exception) -> None:
    logger.debug(f"send_errand: {type(e).__name__}: {e}")


# ── the turn hands it over ──────────────────────────────────────────────────────────────────────────────────────
def hand_over(escalate_req: dict, text: str, wid: str = "", action: str = "", payload: dict | None = None,
              emit=None) -> None:
    """The turn's ONE hand-off: his words become the turn's commission and the model's call (when there was one)
    rides as a hint for the worker — never as a decision. The launch at the turn's close reads it (`context`)."""
    if escalate_req.get("v") is None:
        escalate_req["v"] = text
    escalate_req["leaves"] = True          # no «the turn already acted» guard may annul it
    if wid and action and not escalate_req.get("send"):
        escalate_req["send"] = {"widget": str(wid), "action": str(action), "payload": dict(payload or {})}
    escalate_req.setdefault("send", {}).setdefault("text", " ".join(str(text or "").split()))
    if emit is not None:
        try:
            emit("brain", "📨 a send is one worker task — the turn hands it over", text=f"{wid}:{action}".strip(":"),
                 role="system", extra={"cat": "flash", "id": wid, "action": action})
        except Exception as e:  # noqa: BLE001
            _note(e)


def _leaving_call(calls) -> dict:
    """The model's first `widget_data` call this turn whose act leaves the machine, as a hint; {} when none."""
    from widgets import effects
    from nucleo.request import base
    for c in calls or ():
        a = c.get("args") if isinstance(c, dict) and isinstance(c.get("args"), dict) else None
        if a and c.get("name") == "widget_data" and a.get("widget_id") and a.get("action") \
                and effects.leaves(base(a["widget_id"]), str(a["action"])):
            return {"widget": base(a["widget_id"]), "action": str(a["action"]),
                    "payload": dict(a.get("payload") or {}) if isinstance(a.get("payload"), dict) else {}}
    return {}


def kept(escalate_req: dict, worker_acted: dict, *, brief=None, calls=()) -> None:
    """A send leaves the turn as its ONE commission. A commission routed by a sure verdict (its calls held, never run)
    is a send when the model's held call or the brief's sure act leaves the machine; and a send the turn handed over
    is the commission whatever cleared the slot since (a close backstop, a narrower call). A turn whose words reached
    a live worker is that worker's."""
    if escalate_req.get("v") is not None and "send" not in escalate_req:
        hint = {}
        try:
            hint = _leaving_call(calls)
            if not hint and brief is not None:
                from nucleo.request import ask_outside_door
                wid, act = ask_outside_door._sure_leaving_act(brief)
                hint = {"widget": wid, "action": act, "payload": {}} if wid else {}
        except Exception as e:  # noqa: BLE001
            _note(e)
        if hint:
            escalate_req["send"] = {**hint, "text": " ".join(str(escalate_req["v"]).split())}
    send = (escalate_req or {}).get("send")
    if isinstance(send, dict) and escalate_req.get("v") is None and not (worker_acted or {}).get("v") \
            and send.get("text"):
        escalate_req["v"] = send["text"]


def context(escalate_req: dict) -> dict:
    """What the launch adds to a send's escalation: its playbook and the model's call as a hint."""
    if "send" not in (escalate_req or {}):
        return {}
    return {"playbook": PLAYBOOK, "send": dict(escalate_req.get("send") or {})}


def start(said: str, *, wid: str = "", action: str = "", src: str = "send", emit=None) -> int:
    """A send the turn's close found with nothing launched for it (the brief read the order, no call was made): the
    same ONE task, launched now. Returns the worker id, or 0."""
    text = " ".join(str(said or "").split())
    if not text:
        return 0
    try:
        from nucleo.acts.errand import escalate_to_slowbrain
        hint = {"widget": wid, "action": action, "payload": {}} if wid and action else {}
        tid = int(escalate_to_slowbrain(text, context={"src": src, "kind": "generic", "surface": "voz", "said": text,
                                                       "playbook": PLAYBOOK, "send": hint}) or 0)
        if emit is not None:
            emit("brain", "📨 a send the turn did not hand over → its worker task", text=text[:160], role="system",
                 extra={"cat": "flash", "worker": tid, "src": src, "widget": wid, "action": action})
        return tid
    except Exception as e:  # noqa: BLE001
        _note(e)
        return 0


async def start_line(send) -> str:
    """The turn's ONE line for an act it handed over (`escalate_req["send"]`), worded for him: «I'll get the message
    ready» for a message; for any other act that leaves — a group, an invitation — the start of what he asked for,
    never «the message». "" when no line could be worded."""
    from nucleo import wording
    from nucleo.request import send_receipt
    s = send if isinstance(send, dict) else {}
    fam = send_receipt.family(str(s.get("widget") or ""), str(s.get("action") or ""),
                              s.get("payload") if isinstance(s.get("payload"), dict) else {}) if s.get("action") else "send"
    return await wording.said(wording.line(fam, "preparing"), about=str(s.get("text") or "")[:200])


def on_claude(task, env: dict) -> str:
    """A send's worker runs on Claude itself (the operator's decision, 2026-11-17): the spec's env carries the mark
    `claude_start` reads, and the model is that rung's. "" for any other task (the chain decides as always)."""
    if str((getattr(task, "context", None) or {}).get("playbook") or "") != PLAYBOOK:
        return ""
    from nucleo.workers.providers import claude_tier
    env[claude_tier.ANTHROPIC_MARK] = "anthropic"
    return str((claude_tier.tier() or {}).get("model") or "")


# ── the brief the worker reads ──────────────────────────────────────────────────────────────────────────────────
def _act_steps(wid: str, act: str) -> str:
    """The method for an act that leaves and is NOT a message, with the act's own declaration in it — what it does and
    its fields — so the worker calls it at once instead of reading the card to learn how. "" when undeclared."""
    from widgets import effects
    from nucleo.workers.prompts.catalog import words
    spec = (effects._manifest(wid).get("actions") or {}).get(act)
    tpl = str(words("leaving_act_steps") or "")
    if not (tpl and isinstance(spec, dict)):
        return ""
    fields = "; ".join(f"{k} = {v}" for k, v in (spec.get("payload") or {}).items()) or "-"
    for k, v in (("act", f"{wid}:{act}"), ("desc", str(spec.get("desc") or "")), ("fields", fields),
                 ("widget", wid), ("action", act)):
        tpl = tpl.replace("{" + k + "}", v)
    return tpl


def brief_block(context: dict | None) -> str:
    """The method for the worker, with the model's call as a hint: a message's steps (find her, write the draft, send
    it), or — when the act the turn read is declared as something else that leaves (a group) — that act's own steps.
    '' for a task that is not a send."""
    ctx = context or {}
    if "send" not in ctx and ctx.get("playbook") != PLAYBOOK:
        return ""
    hint = ctx.get("send") or {}
    from nucleo.workers.prompts.catalog import words
    wid, act = str(hint.get("widget") or ""), str(hint.get("action") or "")
    pay = hint.get("payload") if isinstance(hint.get("payload"), dict) else {}
    head = ""
    try:
        from nucleo.request import send_receipt
        if wid and act and send_receipt.family(wid, act, pay) != "send":
            head = _act_steps(wid, act)
    except Exception as e:  # noqa: BLE001 — unread: the message's steps, as before
        _note(e)
    head = head or str(words("send_errand_steps") or "")
    seen = ", ".join(f"{k}={str(v)[:120]!r}" for k, v in pay.items() if str(v or "").strip())
    if seen and (line := str(words("send_errand_hint") or "")):
        head += "\n" + line.format(call=f"{wid}:{act} {seen}")
    return head


# ── the worker's bridge: whom his word names ────────────────────────────────────────────────────────────────────
def find_contact(name: str) -> dict:
    """Bridge act `find_contact`: the rows of his contacts his word names — whole name, alias or first name — with
    their channels; when no row is named, the people his memory points at for that description («my sister»)."""
    q = " ".join(str(name or "").split())
    if not q:
        return {"ok": False, "error": "find_contact needs the name or description he used"}
    rows: list = []
    try:
        from widgets.contactos import data as _cd
        rows = list(_cd.people_named(q, limit=6) or [])
    except Exception as e:  # noqa: BLE001
        _note(e)
    if not rows:
        try:
            from nucleo.memory_agent import contacts as _mc
            rows = [{"name": w.get("name"), "contact_id": w.get("contact_id"),
                     "why": [x.get("text") for x in (w.get("evidence") or [])][:2]} for w in _mc.who(q)]
        except Exception as e:  # noqa: BLE001
            _note(e)
    return {"ok": True, "result": {"query": q, "people": rows,
                                   "note": ("one person → use that name; several → ask him which, naming them; "
                                            "none → ask him who it is")}}
