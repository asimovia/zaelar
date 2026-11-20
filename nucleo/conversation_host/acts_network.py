"""The `Tools` port's acts on his NETWORK (INI-078 F2 step 7c, row 28), each to the door that already does it:

  connect    a cluster joined only after his yes, asked on the Clusters tab's ROW through the one asker
             (`consent_ask.ask_consent`, kind `cluster`); his yes runs `send_gate.confirmed_tag` → `cluster.connect`
  send       a message to a cluster he is in: `meshkore.dispatch_tag("cluster.send")` — the outbound guard, his consent
             rule for the channel (`send_gate`: it may hold it for his yes on the same tab, or refuse it) and the agreed
             cadence are the bridge's; what comes back is whether it left
  objective  the goal of a collaboration with one peer, written on its capsule (`capsule.patch`): declarative, an empty
             one clears it
  a2a        his friends' agents (V2-866): write, ask to connect, share or stop sharing an item — by NAME against his
             accepted relationships (`a2a_run`), a message crossing `consent.decide_act` with the contact as subject

What the network holds now (clusters and who is in them, his A2A contacts, what he shares, their latest messages) is no
act: it is the `network` topic of `read_state`, read when named (`network_facts`).
"""
from __future__ import annotations

import unicodedata

from conversation.ports import ToolResult


def _line(key: str, **kw) -> str:
    from nucleo.conversation_host.acts_life import _line as line
    return line(key, **kw)


def _clusters() -> list[dict]:
    from connectors import meshkore
    return list(meshkore.get_manager().clusters() or ())


def _asked_on_the_tab() -> bool:
    from nucleo.request import consent_ask
    from widgets import confirm
    return consent_ask.open_for_widget(confirm.NATIVE_CLUSTERS) is not None


def _connect(args: dict) -> ToolResult:
    cid, token = str(args.get("cluster_id") or "").strip(), str(args.get("token") or "").strip()
    vis = str(args.get("vis") or "").strip().lower()
    vis = vis if vis in ("public", "private") else ("public" if cid and not token else "")
    if not cid or not (token or vis == "public"):
        return ToolResult("failed", {"reason": "needs the cluster id, and its token when private"})
    name = str(args.get("name") or "").strip() or "meshcore"
    payload = {"name": name, "cluster_id": cid, "token": token, "handle": str(args.get("handle") or "").strip() or None}
    if vis == "public":
        payload["vis"] = "public"
    if bool(args.get("code")):              # his grant of code travels with the connection (`store.set_perms`)
        payload["perms"] = {"workers": True, "code": True, "repo": str(args.get("repo") or "").strip() or None}
    from nucleo.request import consent_ask
    from widgets import confirm
    question = _line("cluster_connect_confirm", name=name, cid=cid[:10])
    op = {"action": "connect_cluster", "payload": payload}
    row, _ask = consent_ask.ask_consent(confirm.NATIVE_CLUSTERS, "cluster", {}, question, text=question,
                                        kind="cluster", op=op)
    if not row:                             # no row could open: the tab's in-memory gate holds it, as before
        confirm.request("data", confirm.NATIVE_CLUSTERS, question, op=op, notify_ui=True)
    return ToolResult("ok", {"asked": question, "waits_for": "his yes", "cluster": name})


async def _send(args: dict) -> ToolResult:
    from connectors import meshkore
    text = str(args.get("text") or "").strip()
    if not text:
        return ToolResult("failed", {"reason": "no_text"})
    name = str(args.get("cluster") or "").strip()
    if not name:
        live = [c["name"] for c in _clusters() if c.get("connected")]
        if len(live) != 1:
            return ToolResult("failed", {"reason": "which cluster" if live else "no cluster connected",
                                         "connected": live})
        name = live[0]
    to = str(args.get("to") or "").strip()
    data = {"text": text, **({"to": to} if to else {})}
    sent = await meshkore.dispatch_tag("cluster.send", {"name": name, "data": data})
    if sent:
        return ToolResult("ok", {"sent_to": name, "peer": to or "everyone", "text": sent})
    if _asked_on_the_tab():
        return ToolResult("ok", {"asked": "his yes on the Clusters tab before it leaves", "cluster": name})
    return ToolResult("failed", {"reason": "not sent: his rule refused it, the outbound guard blocked it, or the "
                                           "cluster is not wired", "cluster": name})


def _objective(args: dict) -> ToolResult:
    cluster, peer = str(args.get("cluster") or "").strip(), str(args.get("peer") or "").strip()
    if not cluster or not peer:
        return ToolResult("failed", {"reason": "which cluster and which peer"})
    from connectors.meshkore import capsule
    objective = str(args.get("objective") or "").strip()
    capsule.patch(cluster, peer, objective=objective)
    return ToolResult("ok", {"cluster": cluster, "peer": peer, "objective": objective or None})


# ── A2A: his friends' agents ──────────────────────────────────────────────────────────────────────────────────────
SEND_CLASS = "messaging.send_new@a2a"


def _n(s: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", str(s or "").lower())
                   if not unicodedata.combining(ch)).strip()


def peer(agent, who: str):
    """The accepted relationship whose name matches (exact, then a unique prefix)."""
    rows = [r for r in agent.rels.all() if r.status == "accepted"]
    w = _n(who)
    exact = [r for r in rows if _n(r.name) == w]
    if exact:
        return exact[0]
    pre = [r for r in rows if w and _n(r.name).startswith(w)]
    return pre[0] if len(pre) == 1 else None


def send_verdict(rel) -> str | None:
    """A message to a friend's agent crosses the ONE consent door (`consent.decide_act`), the contact as the subject so
    his rule for that person outranks the channel's. His spoken order is the mandate (`his_yes`); his standing «never»
    refuses and his «ask» holds it unsent. None = it may leave. Unreadable → held (fail closed)."""
    from nucleo import consent
    try:
        cls, _, channel = SEND_CLASS.partition("@")
        v = consent.decide_act(cls, channel=channel, his_yes=True, subject=str(rel.contact_id or ""))
    except Exception:  # noqa: BLE001
        return "held"
    if not consent.asks(v):
        return None
    return "refused" if v.get("verdict") == consent.REFUSE else "held"


def _a2a_read(agent, who: str, what: str) -> dict:
    r = peer(agent, who) if who else None
    if what == "sharing":
        return {"ok": True, "sharing": agent.sharing(r.did if r else None)}
    if what == "inbox":
        rows = agent.inbox(r.did) if r else agent.inbox()
        return {"ok": True, "inbox": [{"from": m.get("name"), "text": m.get("text"), "ts": m.get("ts"),
                                       "trust": "contact"} for m in rows[-10:]]}
    return {"ok": True, "connected": [x.name for x in agent.rels.all() if x.status == "accepted"]}


def a2a_run(name: str, args: dict) -> dict:
    """One A2A act (`a2a_send` · `a2a_connect` · `a2a_grant`, and the old turn's `a2a_read`) → `{ok, ...}`."""
    import a2a
    agent = a2a.runtime()
    if agent is None:
        return {"ok": False, "error": "a2a_off"}
    who = str(args.get("to") or "")
    try:
        if name == "a2a_read":
            out = _a2a_read(agent, who, str(args.get("what") or "status"))
        elif name == "a2a_connect":
            from widgets.contactos import data, model
            c = next((c for c in data.load_db().get("contacts") or [] if _n(c.get("name")) == _n(who)), None)
            if c is None:
                return {"ok": False, "error": "unknown_contact", "to": who}
            out = {"ok": True, "status": agent.connect_contact(
                {"cid": str(c["id"]), "name": c.get("name", ""), "emails": model.values(c, "emails"),
                 "phones": model.values(c, "phones")}, trace="voice")}
        else:
            r = peer(agent, who)
            if r is None:
                return {"ok": False, "error": "not_connected", "to": who}
            if name == "a2a_send":
                held = send_verdict(r)
                out = {"ok": False, "error": held} if held else {"ok": bool(agent.send(r.did, str(args.get("text") or "")))}
            elif args.get("stop"):
                out = {"ok": True, "revoked": agent.revoke(r.did, str(args.get("item") or ""))}
            else:
                ttl = int(float(args.get("hours") or 0) * 3600)
                g = agent.grant(r.did, str(args.get("item") or ""), ttl_s=ttl, how="voice")
                out = {"ok": True, "item": g.item, "verbs": list(g.verbs), "expires_at": g.expires_at}
    except Exception as e:  # noqa: BLE001 — told, never raised into the turn
        out = {"ok": False, "error": type(e).__name__}
    from voice.observer import emit
    emit("brain", f"🤝 {name}", role="system", extra={"cat": "a2a", "ok": out.get("ok"), "error": out.get("error")})
    return out


def _a2a(name: str):
    def door(args: dict) -> ToolResult:
        out = a2a_run(name, args)
        return ToolResult("ok" if out.get("ok") else "failed", {k: v for k, v in out.items() if k != "ok"})
    return door


def network_facts() -> str:
    """The `network` topic: his clusters (connected or not, who is online), his A2A contacts, what he shares with them
    and their latest messages — facts, read when named."""
    lines = []
    try:
        for c in _clusters():
            online = ", ".join(c.get("online") or ())
            lines.append(f"cluster {c.get('name')}: {'connected' if c.get('connected') else 'disconnected'}"
                         + (f", online: {online}" if online else ""))
    except Exception as e:  # noqa: BLE001 — no cluster hub: nothing to say about clusters, and the log says why
        __import__("logging").getLogger("zaelar.conversation_host").debug(f"network: clusters unreadable ({e!r})")
    import a2a
    agent = a2a.runtime()
    if agent is not None:
        got = _a2a_read(agent, "", "status")
        lines.append("a2a contacts connected: " + (", ".join(got["connected"]) or "none"))
        for r in _a2a_read(agent, "", "sharing")["sharing"]:
            if r.get("items"):
                lines.append(f"sharing with {r['name']}: " + ", ".join(i["item"] for i in r["items"]))
        for m in _a2a_read(agent, "", "inbox")["inbox"][-3:]:
            lines.append(f"from {m['from']}'s agent: {str(m['text'] or '')[:160]}")
    else:
        lines.append("a2a: off")
    return "\n".join(lines)


DOORS = {"connect": _connect, "objective": _objective, **{n: _a2a(n) for n in ("a2a_send", "a2a_connect", "a2a_grant")}}


async def run(op: str, args: dict) -> ToolResult:
    import asyncio
    args = args if isinstance(args, dict) else {}
    if op == "send":
        return await _send(args)
    door = DOORS.get(op)
    if door is None:
        return ToolResult("rejected", {"reason": "unknown_door", "op": op})
    return await asyncio.to_thread(door, args)
