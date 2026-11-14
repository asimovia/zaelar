"""The turn's A2A tools (V2-866 F3 item 8): send · connect · grant · read — schemas and bodies.

Offered ONLY while A2A is on and at least one relationship is accepted (`router._SITUATIONAL`, state, never words):
with nobody accepted the four schemas are not in the prompt at all, so the feature costs zero tokens until it is used.
Every body reaches the running agent through `a2a.runtime()` and resolves the person by NAME against the accepted
relationships (`a2a_connect` against the contacts directory) — a name the model invents finds nobody and says so.
«¿qué estoy compartiendo?» is `a2a_read` with `what=sharing`: grants + the event log, read by code."""
from __future__ import annotations

from loguru import logger

import unicodedata

NAMES = ("a2a_send", "a2a_connect", "a2a_grant", "a2a_read")


def _fn(name: str, desc: str, props: dict, required: list[str]) -> dict:
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
        "type": "object", "properties": props, "required": required}}}


_WHO = {"type": "string", "description": "The person's name as he says it (one of your A2A contacts)."}
SCHEMAS: list[dict] = [
    _fn("a2a_send", "Write to a FRIEND'S AGENT over the A2A network (a contact already connected): 'dile a Marta por "
        "su agente que…'. Not WhatsApp/email (reply_message) and not a MeshKore cluster (cluster_send).",
        {"to": _WHO, "text": {"type": "string", "description": "The message, written naturally."}}, ["to", "text"]),
    _fn("a2a_connect", "Ask to connect your agent with a contact's agent ('conecta con el agente de Marta'). The "
        "request is only sent; the other person accepts on their side.", {"to": _WHO}, ["to"]),
    _fn("a2a_grant", "Share (or stop sharing) one of his items with a connected contact: 'comparte mi agenda con "
        "Marta' → item calendar; 'deja de compartir…' → stop=true. Items: calendar (free/busy only), agenda.list, "
        "activity.history, activity.live.",
        {"to": _WHO, "item": {"type": "string"}, "stop": {"type": "boolean"},
         "hours": {"type": "number", "description": "Only if he says for how long."}}, ["to", "item"]),
    _fn("a2a_read", "Read the A2A network: what=sharing ('¿qué estoy compartiendo?', optionally with one person), "
        "what=inbox (messages from friends' agents), what=status (who is connected).",
        {"what": {"type": "string", "enum": ["sharing", "inbox", "status"]}, "to": _WHO}, ["what"]),
]


def live() -> bool:
    """The state gate: A2A running and ≥1 accepted relationship."""
    try:
        import a2a
        return bool(a2a.accepted())
    except Exception as exc:                                       # noqa: BLE001
        logger.debug("a2a: nucleo/flash/tools_a2a.py:live failed: {!r}", exc)
        return False


def _n(s: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", str(s or "").lower()) if not unicodedata.combining(ch)).strip()


def _peer(agent, who: str):
    """The accepted relationship whose name matches (exact, then a unique prefix)."""
    rows = [r for r in agent.rels.all() if r.status == "accepted"]
    w = _n(who)
    exact = [r for r in rows if _n(r.name) == w]
    if exact:
        return exact[0]
    pre = [r for r in rows if w and _n(r.name).startswith(w)]
    return pre[0] if len(pre) == 1 else None


SEND_CLASS = "messaging.send_new@a2a"


def _send_verdict(rel) -> str | None:
    """T583 · a message to a friend's agent crosses the ONE consent door (`consent.decide_act`), with the contact as
    the subject so his rule for that person outranks the channel's. His spoken order is the mandate (`his_yes`); his
    standing «never» refuses and his «ask» holds it unsent. None = it may leave. Unreadable → held (fail closed)."""
    from nucleo import consent
    try:
        cls, _, channel = SEND_CLASS.partition("@")
        v = consent.decide_act(cls, channel=channel, his_yes=True, subject=str(rel.contact_id or ""))
    except Exception:                                       # noqa: BLE001
        return "held"
    if not consent.asks(v):
        return None
    return "refused" if v.get("verdict") == consent.REFUSE else "held"


def run(name: str, args: dict, emit) -> dict:
    """One tool call → `{ok, ...}`; the line he hears is the model's, built from this result."""
    import a2a
    agent = a2a.runtime()
    if agent is None:
        return {"ok": False, "error": "a2a_off"}
    who = str(args.get("to") or "")
    try:
        if name == "a2a_read":
            what = str(args.get("what") or "status")
            r = _peer(agent, who) if who else None
            if what == "sharing":
                out = {"ok": True, "sharing": agent.sharing(r.did if r else None)}
            elif what == "inbox":
                rows = agent.inbox(r.did) if r else agent.inbox()
                out = {"ok": True, "inbox": [{"from": m.get("name"), "text": m.get("text"), "ts": m.get("ts"),
                                              "trust": "contact"} for m in rows[-10:]]}
            else:
                out = {"ok": True, "connected": [x.name for x in agent.rels.all() if x.status == "accepted"]}
        elif name == "a2a_connect":
            from widgets.contactos import data, model
            c = next((c for c in data.load_db().get("contacts") or [] if _n(c.get("name")) == _n(who)), None)
            if c is None:
                return {"ok": False, "error": "unknown_contact", "to": who}
            out = {"ok": True, "status": agent.connect_contact(
                {"cid": str(c["id"]), "name": c.get("name", ""), "emails": model.values(c, "emails"),
                 "phones": model.values(c, "phones")}, trace="voice")}
        else:
            r = _peer(agent, who)
            if r is None:
                return {"ok": False, "error": "not_connected", "to": who}
            if name == "a2a_send":
                held = _send_verdict(r)
                out = {"ok": False, "error": held} if held else {"ok": bool(agent.send(r.did, str(args.get("text") or "")))}
            elif args.get("stop"):
                out = {"ok": True, "revoked": agent.revoke(r.did, str(args.get("item") or ""))}
            else:
                ttl = int(float(args.get("hours") or 0) * 3600)
                g = agent.grant(r.did, str(args.get("item") or ""), ttl_s=ttl, how="voice")
                out = {"ok": True, "item": g.item, "verbs": list(g.verbs), "expires_at": g.expires_at}
    except Exception as e:                                  # noqa: BLE001 — told, never raised into the turn
        out = {"ok": False, "error": type(e).__name__}
    emit("brain", f"🤝 {name}", role="system", extra={"cat": "a2a", "ok": out.get("ok"), "error": out.get("error")})
    return out


def line(name: str, out: dict, args: dict, say) -> str:
    """The spoken line of a call, from the voice pack (`voice.a2a_*`) — code, not the model, reads the result out."""
    def t(key: str, **kw) -> str:
        try:
            return str(getattr(say, key)).format(**kw)
        except Exception as exc:                                   # noqa: BLE001
            logger.debug("a2a: nucleo/flash/tools_a2a.py:t failed: {!r}", exc)
            return ""
    who = str(args.get("to") or "")
    if not out.get("ok"):
        if out.get("error") in ("not_connected", "unknown_contact"):
            return t("a2a_not_connected", name=who)
        if out.get("error") in ("refused", "held"):
            return t(f"a2a_send_{out['error']}", name=who)
        return t("a2a_failed")
    if name == "a2a_send":
        return t("a2a_sent", name=who)
    if name == "a2a_connect":
        return t("a2a_no_agent", name=who) if out.get("status") == "no_match" else t("a2a_requested", name=who)
    if name == "a2a_grant":
        if "revoked" in out:
            return t("a2a_unshared", item=args.get("item", ""), name=who)
        return t("a2a_shared", item=out.get("item", ""), name=who)
    if "sharing" in out:
        rows = [r for r in out["sharing"] if r["items"]]
        if not rows:
            return t("a2a_sharing_none")
        return " ".join(t("a2a_sharing_line", name=r["name"], items=", ".join(i["item"] for i in r["items"]))
                        for r in rows)
    if "inbox" in out:
        if not out["inbox"]:
            return t("a2a_inbox_empty")
        return " ".join(t("a2a_inbox_line", name=m["from"], text=m["text"]) for m in out["inbox"][-3:])
    names = out.get("connected") or []
    return t("a2a_connected", names=", ".join(names)) if names else t("a2a_sharing_none")


def door(name: str):
    """The act door of one tool: run it, then the line is said by code (no second model trip)."""
    def run_door(args: dict, c) -> None:
        said = line(name, run(name, args, c.emit), args, c._say())
        if said:
            c.clarify["msg"] = said
    run_door.__name__ = name
    return run_door


DOORS = {n: door(n) for n in NAMES}
