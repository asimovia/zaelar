"""nucleo/workers/exit_gate.py — a worker act that LEAVES the machine crosses ONE door (V2-851 F2, V2-931).

`worker_api.worker_act` asks it before executing; the retained act his yes runs crosses it again
(`worker_api_answer`). Each leaving act is declared once in `EXITS`, never chosen by name:

  · `widget_data` on a card whose act leaves (`gate`): the card's own refusal first, then ONE confirmation — sending a
    message needs his yes — unless an errand's mandate covers the channel;
  · `mesh_serve` (`mesh`): the errand text to a third-party agent — outbound scan, the consent class, the taint.

`taint_question` is the rule the browser's submit reads too (`widgets/navegador/click_gate.py`): while the session has
consumed a stranger's text since its last confirmed act, an exit asks unless a mandate covers it.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from loguru import logger

from nucleo.workers.exit_risk import _short, asks_by_itself, family, klass, own_question, ready_question  # noqa: F401 — the door's readers


@dataclass(frozen=True)
class Exit:
    payload: dict           # the call as it may run (his word put back in place of a swapped recipient)
    question: str = ""      # non-empty: ask him first (the worker's ordinary CONFIRM)
    refused: str = ""       # non-empty: vetoed, said to the worker
    released: bool = False  # his order over a held row he has seen is the yes (CRIT-C9): no consent question
    event: str = ""         # the EVENT TYPE this exit is (`messaging.send_new@whatsapp`, `errand.mesh_serve@mesh`)
    subject: str = ""       # the contact id the act reaches, when it reaches exactly one person (V2-857 phase 2)
    slots: dict = field(default_factory=dict)   # {declared slot: its source} — recorded on the exit's event
    why: str = ""           # what released it, for the record («harmless by its declared type»)

    @property
    def verdict(self) -> str:
        return "refused" if self.refused else "ask" if self.question else "released" if self.released else "pass"


@dataclass(frozen=True)
class ExitSpec:
    """One bridge act that LEAVES the machine, declared once (V2-857 phase 5): the door it crosses (`body`) and how its
    event is read — a fixed type with its channel (`mesh_serve`), or the card's own class (`widget_data`, read off the
    manifest and its `consent_scope` hook, so a messaging act is `messaging.send_new@<channel>`)."""
    action: str
    body: str               # the name of this module's door, `(rec, payload) -> Exit`, read at call time
    event: str = ""         # fixed event type, or "" when the card's declared class is the type
    channel: str = ""       # fixed channel for a fixed event


def leave(rec, action: str, payload: dict | None) -> Exit | None:
    """THE exit door of a worker's act (V2-857 phase 5): None when the act does not leave the machine (undeclared
    here), else the Exit of its declared door, with the act's EVENT TYPE and SUBJECT read from the call and ONE
    `task` event recording the verdict. The bridge asks this and nothing by action name; the retained act his yes
    runs crosses it again (`worker_api_answer.answer`)."""
    spec = next((s for s in EXITS if s.action == str(action or "")), None)
    if spec is None:
        return None
    p = dict(payload or {})
    ex = globals()[spec.body](rec, p)
    event, subject, who, channel = _event_of(spec, ex.payload if ex.payload else p)
    ex = Exit(ex.payload, ex.question, ex.refused, ex.released, event=event, subject=subject, slots=ex.slots,
              why=ex.why)
    _emit(f"🚪 exit door: {ex.verdict}", f"{event or action} → {', '.join(who) or channel or '?'}"[:200],
          {"id": str(getattr(rec, "task_id", "")), "exit": action, "event": event, "channel": channel,
           "subject": subject, "who": who[:3], "verdict": ex.verdict, "slots": dict(ex.slots),
           "why": (ex.refused or ex.question or ex.why or ("his order over the row" if ex.released else ""))[:160]})
    return ex


async def cross(rec, action: str, payload: dict | None) -> "Exit | None":
    """`leave` for its callers (all on the loop): an act that leaves has its doors — `send`, `portal` — asked into the
    task's reading and awaited OFF the loop, up to Jev's own timeout (CRIT-K2b R1: what is irreversible waits)."""
    from nucleo import jev, on_his_behalf as _ob
    from nucleo.turn import brief as _tb, brief_doors
    wid, act, _inner = _ob._resolve(payload or {}) if str(action or "") == "widget_data" else ("", "", None)
    if wid and act and leaves(wid, act) and (turn := _tb.revived(getattr(rec, "reading", None))) is not None:
        await asyncio.gather(*(brief_doors.landed(turn, d, jev._timeout_s() + 1.0) for d in ("send", "portal")))
    if wid and act and leaves(wid, act) and asks_by_itself(wid, act, _inner):
        # a go-ahead he gave WITH the order — or in an answer on this row — is read once, off the loop (V2-931)
        from nucleo.events import vocabulary as _evoc
        t = _evoc.of(klass(wid, act, _inner))
        await asyncio.to_thread(__import__("nucleo.switchboard.act", fromlist=["x"]).read_his_go_ahead, rec,
                                t.what if t else "")
    return leave(rec, action, payload)


def _event_of(spec: "ExitSpec", payload: dict) -> tuple[str, str, list[str], str]:
    """`(event type with its channel, subject, who, channel)` of this exit, from declared data only: the card's class
    (its manifest, refined by its `consent_scope` hook) or the spec's fixed type; the recipient the call names and
    the one person it means (`directory.subject_id`). Unreadable parts are empty, never guessed."""
    from nucleo import consent
    try:
        if spec.event:
            return consent.act_key(spec.event, spec.channel), "", [], spec.channel
        from nucleo import on_his_behalf as _ob
        from nucleo.acts import frontend as _fe
        from widgets import directory, runtime
        wid, act, inner = _ob._resolve(payload or {})
        man = runtime.get(wid) or {}
        sp = (man.get("actions") or {}).get(act)
        from rules import split_key
        cls, ch = split_key(_fe._policy_key(wid, act, sp if isinstance(sp, dict) else {}, inner) if wid and act else "")
        channel = ch or str(inner.get("platform") or inner.get("channel") or "")
        who = _ob.who_of(wid, act, inner) if wid and act else []
        subject = directory.subject_id(who[0], channel) if len(who) == 1 else ""
        return consent.act_key(cls, channel) if cls else "", subject, who, channel
    except Exception as e:  # noqa: BLE001 — the record names what it could read; the door's verdict stands
        logger.debug(f"exit_gate: the exit's event could not be read ({e!r})")
        return (spec.event, "", [], spec.channel)


def _emit(label: str, text: str, extra: dict) -> None:
    try:
        from voice.observer import emit
        emit("task", label, text=text, role="system", extra=extra)
    except Exception as e:  # noqa: BLE001 — the trace never stops the gate
        logger.debug(f"exit_gate: event not emitted ({e!r})")


def leaves(wid: str, act: str) -> bool:
    """Does this declared action leave the machine (`external.send`)? Unreadable → it leaves (it asks)."""
    try:
        from widgets import effects as _fx
        return bool(_fx.carries(wid, act, _fx.EXTERNAL_SEND))
    except Exception as e:  # noqa: BLE001
        logger.debug(f"exit_gate: effects unread for {wid}:{act} ({e!r})")
        return True


def under_mandate(rec, kind: str, channel: str = "") -> bool:
    """Does the session's mandate cover this exit? `message` reads the errand rule itself (`mandate.covers`); any
    other kind must be named in `may`. No mandate → no."""
    m = getattr(rec, "mandate", None)
    if not isinstance(m, dict) or not m:
        return False
    from nucleo.errands.mandate import acts, covers
    if kind == "message":
        return covers({"mandate": m}, channel)
    return kind in acts(m.get("may")) or kind in [str(x) for x in (m.get("may") or [])]


def taint_question(rec, kind: str, action: str, target: str, channel: str = "") -> str:
    """'' when this exit may go; else the question for him — the session read a stranger's text since his last yes."""
    from nucleo.workers import taint
    if not taint.tainted(rec) or under_mandate(rec, kind, channel):
        return ""
    _emit("🛑 sale fuera tras leer texto de terceros — se le pregunta", f"{action} → {target}",
          {"id": str(getattr(rec, "task_id", "")), "exit": kind, "action": action, "target": target[:120]})
    try:
        from i18n import langs as _lg
        return _lg.current_language().worker_confirm_tainted.format(action=action, target=target or "?")
    except Exception:  # noqa: BLE001
        return f"{action} → {target}?"


def gate(rec, payload: dict) -> Exit:
    """The exit door for one `widget_data` call of a worker (V2-931). A call that does not leave passes untouched.

    Whether he is asked is read off the RISK the act's event type declares, never off its name: a type declared
    harmless (a group created with people he named) runs on his order, said once; a message — his words reaching a
    person — and any act of no declared type needs his confirmation: ONE question, the act's own («the message is ready
    — shall I send it to <person>?»), unless an errand's mandate covers the channel. Nothing re-derives where the
    person or the words came from, nothing vetoes by his last turn's words: the worker owns the act and he confirms
    what is about to leave. The card's own refusal is said before any question, so he is never asked about an act that
    would not run. Measured 2026-11-18: «create a group with her called X» was asked three times, each time as «the
    message for her is written — shall I send it?»."""
    from nucleo import on_his_behalf as _ob
    wid, act, inner = _ob._resolve(payload or {})
    if not wid or not act or not leaves(wid, act):
        return Exit(payload)
    from widgets import contract as _contract     # an act that would refuse this call is said so before any question
    if (no := _contract.would_refuse(wid, act, inner)):
        why = str(no.get("message") or no.get("error") or "refused")
        _emit("🚫 the act would refuse this call — nothing is asked", f"{wid}:{act} · {why}"[:200],
              {"id": str(getattr(rec, "task_id", "")), "exit": f"{wid}:{act}", "error": str(no.get("error") or "")})
        return Exit(payload, refused=f"{wid}:{act} would be refused ({no.get('error') or 'refused'}): {why}")
    from nucleo.request import send_receipt as _sr     # this request already took this very act to its receipt
    if _sr.landed(str(getattr(rec, "uid", "") or ""), wid, act, inner):
        _emit("✅ the act already landed for this request — not asked, not run again", f"{wid}:{act}"[:200],
              {"id": str(getattr(rec, "task_id", "")), "exit": f"{wid}:{act}"})
        return Exit(payload, refused=f"{wid}:{act} is ALREADY DONE for this request: it ran and the service confirmed "
                                     "it. Do not repeat it and do not ask him about it — end now.")
    out = dict(payload or {})
    from nucleo.workers.prompts import playbook as _pbk
    if (named := _pbk.continues_as(rec, wid, act)):
        out["payload"] = inner = {**inner, "playbook": named}
    channel = str(inner.get("platform") or inner.get("channel") or "")
    mandated = under_mandate(rec, "message", channel)
    from connectors import exit as door           # the install's outbound switch, asked before any yes is asked for
    lane = door.MANDATE if mandated else door.WORKER
    if (held := door.check(f"{wid}:{act}", lane, inner)):
        return Exit(payload, refused=f"outbound is held on this install ({held}): nothing was sent and nothing will "
                                     "be. Tell him so in one line and end.")
    go = {**out, "payload": door.by(lane, out["payload"])}   # the act PASSES: its lane stamped by code, never asked
    if mandated:
        return Exit(go)
    cls = klass(wid, act, inner)
    if not asks_by_itself(wid, act, inner):      # harmless by its declared type: his order is the yes, said once
        try:
            from nucleo import consent
            if consent.class_policy(cls) == "never":
                return Exit(out, refused=f"his rule forbids it ({cls}): nothing was done")
        except Exception as e:  # noqa: BLE001
            logger.debug(f"exit_gate: his rule for {cls} unread ({e!r})")
        return Exit(go, released=True, why="harmless by its declared type — his order is the yes")
    from nucleo.acts import message as _msg      # ONE act, ONE question: a draft he was shown and then ORDERED sent
    if _msg.confirmed(wid, act, inner, None):     # was asked about when it was shown — his order is the yes (CRIT-C9)
        return Exit(go, released=True)
    from nucleo.switchboard import act as _sb     # …and a yes he gave while it was being prepared is that yes, once
    if _sb.took_early_yes(str(getattr(rec, "uid", "") or "")):
        return Exit(go, released=True)
    return Exit(out, question=ready_question(wid, act, inner, cls))


def mesh(rec, payload: dict) -> Exit:
    """`mesh_serve`: the errand's request leaves to an agent that SERVES it — a query to a provider, like a web search,
    never a message to a person (V2-852 T14, re-cut on the C13 replay). It passes the leave door: the outbound scan
    first (`scan_outbound`, the cluster's detector: a hard secret sends nothing, identity terms are redacted, so what
    leaves is the request, not his data); then the one consent rule for the class with his standing rules
    (`errand.mesh_serve`: «never» refuses, «ask» asks, «allow» runs it); then the
    taint, read on WHAT leaves (asked after untrusted reads when the request carries his data — the scan redacted —
    unless a mandate names `mesh`) (the session read untrusted content since its last confirmed act → he is asked). No recipient rule: the
    agent is a provider the worker chose for the task, as it chooses a site. Every outcome is a `consequence` event on
    door `mesh.serve`, so a send is never invisible. The text that may leave is handed back to the bridge.

    Measured (V2-852, the first live session): the worker sent the errand to two third-party agents found by the
    oracle; the class rule alone (`standard` below `ask_at`) ran it with no question and no event before it."""
    p = dict(payload or {})
    text = str(p.get("prompt") or p.get("errand") or "")
    agent = str(p.get("agent") or "").strip()
    tid = str(getattr(rec, "task_id", ""))
    from nucleo.workers.prompts import playbook as _pbk
    if (first := _pbk.checkpoint_one(rec)):
        return _mesh_outcome(p, agent, tid, "refused", refused=first)
    try:
        from connectors.meshkore import security
        safe, block = security.scan_outbound(text)
        # what leaves carries HIS data when the scan had to redact (identity terms) — or could not look at all
        carries_his = (not security.enabled()) or safe != text
    except Exception as e:  # noqa: BLE001 — a scan that could not run is not a licence to send
        return _mesh_outcome(p, agent, tid, "refused", refused=f"the outbound scan could not run "
                                                              f"({type(e).__name__}): nothing was sent")
    if block:
        _emit("🛑 texto de encargo con un secreto — no sale a la red", block, {"id": tid, "exit": "mesh"})
        return _mesh_outcome(p, agent, tid, "refused", refused=f"the errand text carries a {block}: nothing was sent "
                                                              f"to a third-party agent — write the request without it")
    p["prompt"] = safe
    from nucleo import consent
    allowed = consent.class_policy(consent.act_key("errand.mesh_serve", "mesh")) == "allow" \
        or under_mandate(rec, "mesh")
    v = consent.decide_act("errand.mesh_serve", channel="mesh", licensed=True, his_yes=allowed)
    if v.get("verdict") == consent.REFUSE:
        return _mesh_outcome(p, agent, tid, "refused",
                             refused=f"his rule forbids it: {v.get('why') or 'mesh'} — nothing was sent")
    target = agent or str(p.get("errand") or "")[:60]
    # the taint reads WHAT leaves: a request the scan found nothing of his in carries nothing a stranger's text could
    # have steered out of him — a search reads the web by its nature, and asking each query would stop every search
    q = taint_question(rec, "mesh", "mesh serve", target) if carries_his else ""
    if not q and consent.asks(v):
        try:
            from i18n import langs as _lg
            q = _lg.current_language().worker_confirm_on_behalf.format(action="mesh serve", who=target or "?")
        except Exception:  # noqa: BLE001
            q = f"mesh serve → {target}?"
    return _mesh_outcome(p, agent, tid, "ask" if q else "pass", question=q,
                         why="" if q else ("his rule or mandate allows it" if allowed else "a service request: scanned, untainted"))


def _mesh_outcome(p: dict, agent: str, tid: str, verdict: str, *, question: str = "", refused: str = "",
                  why: str = "") -> Exit:
    """The exit's one record: a `consequence` event (door `mesh.serve`) with its verdict, then the Exit itself."""
    try:
        from nucleo import consequence
        if not consequence.passes("mesh.serve", task_id=tid, agent=agent or "?", gate=verdict,
                                  why=(refused or why)[:160]) and not refused:
            refused = "this turn reaches no door (a dry run): nothing was sent"
    except Exception as e:  # noqa: BLE001 — the record never decides the exit
        logger.debug(f"exit_gate: mesh consequence not recorded ({e!r})")
    return Exit(p, question=question, refused=refused)


#: The bridge acts that LEAVE, declared once: the door each crosses and how its event type is read. An act not declared
#: here does not leave (`leave` returns None); a new leaving act declares itself here, never as a branch by its name.
EXITS: tuple[ExitSpec, ...] = (ExitSpec("widget_data", "gate"),
                              ExitSpec("mesh_serve", "mesh", event="errand.mesh_serve", channel="mesh"))
