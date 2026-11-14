"""`A2AAgent`: one owner's end of the network — the single door the engine (and the CLI, and the lab) uses.

Everything here is code: discover, propose, request, accept, grant, query, reply, live share. No model call (I3).
Inbound text is DATA (I1): it lands in `inbox` with trust="contact" and is handed to `on_message` as a card; it never
reaches a prompt from here. Every step emits exactly one row (I10, `events.OPS`).
"""
from __future__ import annotations

import json
import secrets
import time
from pathlib import Path
from typing import Callable

from . import events
from .envelope import Envelope, EnvelopeError
from .grants import Grants, JsonGrantStore, contact_audience
from .identity import Identity, short
from .items import ItemRegistry, default_items
from .relationships import IllegalTransition, Relationships
from .store import JsonDoc, default_state_dir
from .transport.base import TransportError

PROPOSE_EVERY_S = 30 * 86400
DEFAULT_ON_ACCEPT = (("messages", ("append",)),)        # D7: messages only, everything else is a grant

Asker = Callable[[dict], object]


class A2AAgent:
    def __init__(self, me: Identity, mailbox, directory=None, live=None, *, state_dir: Path | None = None,
                 items: ItemRegistry | None = None, grant_store=None, clock=time.time, asker: Asker | None = None,
                 on_message: Callable[[dict], None] | None = None, scan_outbound: Callable[[str], str | None] = None,
                 policy=None, groups=None, display_name: str = ""):
        self.me, self.mailbox, self.directory, self.live = me, mailbox, directory, live
        self.clock = clock
        self.state_dir = Path(state_dir or default_state_dir())
        self.rels = Relationships(self.state_dir, clock=clock)
        self.items = items or default_items()
        self.grants = Grants(grant_store or JsonGrantStore(self.state_dir), self.items, clock=clock,
                             groups=groups, policy=policy)
        self.asker = asker or (lambda card: None)          # None = pending: the owner answers later
        self.on_message = on_message
        self.scan_outbound = scan_outbound
        self.display_name = display_name
        self._doc = JsonDoc(self.state_dir / "a2a_state.json",
                            {"inbox": [], "answers": {}, "proposed": {}, "never": [], "out_shares": {},
                             "in_shares": {}, "shared_with_me": {}, "published": []})
        self.empty_pulls: list[float] = []

    # ── helpers ───────────────────────────────────────────────────────────────────────────────────────────────
    @property
    def state(self) -> dict:
        return self._doc.data

    def _save(self):
        self._doc.save()

    def emit(self, op: str, **kw):
        r = kw.pop("r", None)
        if r is not None:
            kw.setdefault("peer", r.did)
            kw.setdefault("rel", r.rel)
            kw.setdefault("cid", r.contact_id)
            kw.setdefault("name", r.name)
        return events.emit(op, me=self.me.did, **kw)

    def _rel_for(self, who: str):
        r = self.rels.get(who) if who.startswith("did:key:") else self.rels.by_contact(who)
        if r is None:
            raise KeyError(f"no relationship with {who!r}")
        return r

    def _send(self, r, kind: str, body: dict, trace: str = "") -> bool:
        try:
            wire = Envelope(kind=kind, frm=self.me.did, to=r.did, body=body, ts=int(self.clock())).seal(self.me)
            self.mailbox.post(r.did, wire)
        except (TransportError, EnvelopeError) as e:
            self.emit("send_failed", r=r, dir="out", ok=False, trace=trace,
                      status=getattr(e, "status", getattr(e, "reason", "")), envelope_kind=kind)
            return False
        self.rels.touch_out(r.did)
        return True

    # ── status ────────────────────────────────────────────────────────────────────────────────────────────────
    def status(self) -> dict:
        return {"did": self.me.did, "cursor": self.rels.cursor,
                "relationships": [{"rel": r.rel, "cid": r.contact_id, "name": r.name, "status": r.status,
                                   "peer": short(r.did), "matched_by": r.matched_by,
                                   "grants": [{"item": g.item, "verbs": g.verbs, "expires_at": g.expires_at}
                                              for g in self.grants.for_audience(contact_audience(r.contact_id))]}
                                  for r in self.rels.all()],
                "inbox": len(self.state["inbox"]), "shared_with_me": self.state["shared_with_me"]}

    # ── discovery (D10: a match proposes, the owner's yes sends) ───────────────────────────────────────────────
    def publish_hashes(self, emails=(), phones=(), default_cc: str = "") -> int:
        from .discovery import hashes_for
        hs = list(hashes_for(emails, phones, default_cc))[:16]
        n = self.directory.publish(hs)
        self.state["published"] = hs
        self._save()
        self.emit("publish", hashes=len(hs))
        return n

    def discover(self, contacts: list[dict], trigger: str = "daily", default_cc: str = "") -> list[dict]:
        """`contacts` = [{cid, name, emails[], phones[]}]. Looks up their hashes; each NEW mutual match becomes one
        entry of ONE proposal card; the owner's answer per contact (ask | not_now | never) decides the request."""
        from .discovery import hashes_for
        t0 = time.monotonic()
        index: dict[str, tuple[dict, str]] = {}
        for c in contacts:
            for h, how in hashes_for(c.get("emails", ()), c.get("phones", ()), default_cc).items():
                index[h] = (c, how)
        try:
            found = self.directory.lookup(list(index)) if index else []
        except TransportError as e:
            self.emit("discover", ok=False, trigger=trigger, hashes=len(index), matches=0)
            return []
        now = self.clock()
        fresh: list[dict] = []
        for m in found:
            c, how = index.get(m.get("hash"), (None, ""))
            did = m.get("did", "")
            if not c or not did or did == self.me.did:
                continue
            r = self.rels.get(did)
            if r and r.status in ("outgoing", "accepted", "incoming"):
                continue
            if c["cid"] in self.state["never"] or now - self.state["proposed"].get(c["cid"], 0) < PROPOSE_EVERY_S:
                continue
            if any(f["cid"] == c["cid"] for f in fresh):
                continue
            fresh.append({"cid": c["cid"], "name": c.get("name", ""), "did": did, "agent_id": m.get("agent_id", ""),
                          "matched_by": how})
        self.emit("discover", trigger=trigger, hashes=len(index), matches=len(fresh),
                  matched_by=sorted({f["matched_by"] for f in fresh}), ms=(time.monotonic() - t0) * 1000)
        if not fresh:
            return []
        for f in fresh:
            self.state["proposed"][f["cid"]] = now
            events.name_contact(f["cid"], f["name"])
            self.emit("propose", cid=f["cid"], peer=f["did"], name=f["name"], matched_by=f["matched_by"],
                      batch=len(fresh), trace=trigger)
        self._save()
        answer = self.asker({"type": "propose", "matches": [{k: f[k] for k in ("cid", "name", "matched_by")}
                                                             for f in fresh]})
        for f in fresh:
            a = answer.get(f["cid"]) if isinstance(answer, dict) else answer
            if a is None:
                continue
            self.emit("propose_answer", cid=f["cid"], peer=f["did"], answer=str(a))
            if a == "ask":
                self.connect(f["did"], contact_id=f["cid"], name=f["name"], matched_by=f["matched_by"],
                             agent_id=f["agent_id"], trace="propose")
            elif a == "never":
                self.state["never"].append(f["cid"])
                self._save()
        return fresh

    # ── handshake ─────────────────────────────────────────────────────────────────────────────────────────────
    def connect(self, did: str, contact_id: str = "", name: str = "", matched_by: str = "", agent_id: str = "",
                note: str = "", trace: str = "owner") -> str:
        """The owner's yes (or his own order). Returns the relationship status after the call."""
        r0 = self.rels.get(did)
        rel_id = r0.rel if r0 else secrets.token_hex(6)
        r, crossing = self.rels.outgoing(did, contact_id=contact_id or (r0.contact_id if r0 else ""),
                                         name=name or (r0.name if r0 else ""), matched_by=matched_by,
                                         agent_id=agent_id, rel=rel_id)
        events.name_contact(r.contact_id, r.name)
        if crossing:
            self._on_accepted(r, crossing=True)
            self._send(r, "connect.accept", {"rel": r.rel, "name": self.display_name}, trace=trace)
            self.emit("accept", r=r, dir="out", crossing=True, scopes=["messages"], trace=trace)
            return r.status
        self.emit("request", r=r, dir="out", matched_by=matched_by, crossing=False, excerpt=note, trace=trace)
        self._send(r, "connect.request", {"rel": r.rel, "name": self.display_name, "note": note[:280],
                                          "matched_by": matched_by}, trace=trace)
        return r.status

    def connect_contact(self, contact: dict, trace: str = "owner") -> str:
        """The owner asks to connect with one of his contacts (`{cid, name, emails, phones}`): its hashes are looked
        up and the request goes to the matched agent. `no_match` when that person has no agent on the network."""
        from .discovery import hashes_for
        hs = hashes_for(contact.get("emails", ()), contact.get("phones", ()), "")
        found = self.directory.lookup(list(hs)) if hs and self.directory else []
        m = next((m for m in found if m.get("did") and m.get("did") != self.me.did), None)
        if m is None:
            return "no_match"
        return self.connect(m["did"], contact_id=str(contact.get("cid") or ""), name=str(contact.get("name") or ""),
                            matched_by=hs.get(m.get("hash"), ""), agent_id=m.get("agent_id", ""), trace=trace)

    def _on_accepted(self, r, crossing: bool = False):
        if not r.contact_id:
            r.contact_id = "a2a:" + short(r.did)
            self.rels.put(r)
        for item, verbs in DEFAULT_ON_ACCEPT:
            self.grants.grant(item, contact_audience(r.contact_id), verbs)

    def accept(self, who: str, contact_id: str = "", name: str = "") -> str:
        r = self.rels.accept(self._rel_for(who).did)
        if contact_id or name:
            r.contact_id, r.name = contact_id or r.contact_id, name or r.name
            self.rels.put(r)
        self._on_accepted(r)
        r = self.rels.get(r.did)
        events.name_contact(r.contact_id, r.name)
        self._send(r, "connect.accept", {"rel": r.rel, "name": self.display_name})
        self.emit("accept", r=r, dir="out", crossing=False, scopes=["messages"])
        return r.status

    def decline(self, who: str) -> str:
        r = self.rels.decline(self._rel_for(who).did)
        self._send(r, "connect.decline", {"rel": r.rel})
        self.emit("decline", r=r, dir="out", declined_until=r.declined_until)
        return r.status

    def disconnect(self, who: str) -> str:
        r = self._rel_for(who)
        for g in self.grants.revoke_all(contact_audience(r.contact_id)):
            self._close_shares(r, g.item)
        self._send(r, "connect.revoke", {"rel": r.rel})
        r = self.rels.revoke(r.did)
        self.emit("disconnect", r=r, dir="out")
        return r.status

    # ── grants (generic items) ────────────────────────────────────────────────────────────────────────────────
    def grant(self, who: str, item: str, verbs=("see",), ttl_s: int = 0, how: str = "settings"):
        r = self._rel_for(who)
        if r.status != "accepted":
            raise IllegalTransition("grants exist only after accept (I2)")
        exp = self.clock() + ttl_s if ttl_s else 0.0
        g = self.grants.grant(item, contact_audience(r.contact_id), verbs, expires_at=exp)
        self.emit("grant", r=r, item=item, verbs=g.verbs, audience="contact", expires_at=exp, how=how)
        self._send(r, "grant.notice", {"item": item, "verbs": g.verbs, "expires_at": exp})
        return g

    def revoke(self, who: str, item: str) -> int:
        r = self._rel_for(who)
        gone = self.grants.revoke(item, contact_audience(r.contact_id))
        self._close_shares(r, item)
        self.emit("revoke", r=r, item=item, audience="contact")
        if gone and r.status == "accepted":
            self._send(r, "grant.revoked", {"item": item})
        return len(gone)

    # ── messages ──────────────────────────────────────────────────────────────────────────────────────────────
    def send(self, who: str, text: str) -> bool:
        r = self._rel_for(who)
        if r.status != "accepted":
            raise IllegalTransition("messages only after accept (I2)")
        reason = self.scan_outbound(text) if self.scan_outbound else None
        if reason:
            self.emit("msg_blocked", r=r, dir="out", ok=False, reason=reason)
            return False
        ok = self._send(r, "msg.text", {"text": text})
        if ok:
            self.emit("msg", r=r, dir="out", len=len(text), shown="sent", excerpt=text)
        return ok

    # ── queries ───────────────────────────────────────────────────────────────────────────────────────────────
    def ask(self, who: str, item: str, projection: str = "default", args: dict | None = None) -> str:
        r = self._rel_for(who)
        if r.status != "accepted":
            raise IllegalTransition("queries only after accept (I2)")
        qid = secrets.token_hex(6)
        self.state["answers"][qid] = {"status": "pending", "item": item, "cid": r.contact_id}
        self._save()
        self.emit("query", r=r, dir="out", item=item, projection=projection, args=sorted((args or {}).keys()))
        self._send(r, "query", {"qid": qid, "item": item, "projection": projection, "args": args or {}})
        return qid

    def answer(self, qid: str) -> dict:
        return self.state["answers"].get(qid, {"status": "unknown"})

    # ── live share ────────────────────────────────────────────────────────────────────────────────────────────
    def live_open(self, who: str, item: str = "activity.live", ttl_s: int = 7200, ring: int = 500) -> str:
        """The owner's act IS the grant: a temporary `subscribe` on the item for this contact, ending with the share."""
        r = self._rel_for(who)
        if r.status != "accepted":
            raise IllegalTransition("live share only after accept (I2)")
        it = self.items.get(item)
        self.grants.grant(item, contact_audience(r.contact_id), ("subscribe",), expires_at=self.clock() + ttl_s)
        s = self.live.open(r.did, ttl_s=ttl_s, ring=ring)
        self.state["out_shares"][s.share_id] = {"did": r.did, "cid": r.contact_id, "item": item,
                                               "push": s.push_token, "expires_at": s.expires_at}
        self._save()
        self.emit("live_open", r=r, dir="out", item=item, share=s.share_id[:8], ttl_s=ttl_s)
        self._send(r, "live.offer", {"share_id": s.share_id, "item": item, "schema": it.schema,
                                     "expires_at": s.expires_at})
        return s.share_id

    def live_push(self, share_id: str, sample: dict) -> int | None:
        sh = self.state["out_shares"].get(share_id)
        if not sh:
            return None
        r = self.rels.get(sh["did"])
        if not self.grants.allowed(sh["cid"], sh["item"], "subscribe").allowed:
            self._close_shares(r, sh["item"])
            return None
        sealed = self.me.seal(sh["did"], json.dumps(sample, separators=(",", ":")).encode(), salt=share_id)
        try:
            seq = self.live.push(share_id, sh["push"], {"sealed": sealed})
        except TransportError as e:
            self.emit("live_sample", r=r, dir="out", ok=False, share=share_id[:8], seq=0)
            if e.status == 404:
                self.state["out_shares"].pop(share_id, None)
                self._save()
            return None
        self.emit("live_sample", r=r, dir="out", share=share_id[:8], seq=seq)
        return seq

    def _close_shares(self, r, item: str):
        for sid, sh in list(self.state["out_shares"].items()):
            if sh["did"] == r.did and (item == "*" or sh["item"] == item or ":" in item):
                try:
                    self.live.close(sid, sh["push"])
                except (TransportError, AttributeError):
                    pass
                self.state["out_shares"].pop(sid, None)
                self._save()
                self.emit("live_close", r=r, dir="out", share=sid[:8])
                if r.status == "accepted":
                    self._send(r, "live.closed", {"share_id": sid})

    def live_read(self, share_id: str, after: int | None = None) -> dict:
        sh = self.state["in_shares"].get(share_id)
        if not sh:
            return {"samples": [], "closed": True}
        r = self.rels.get(sh["did"])
        try:
            if not sh.get("read"):
                for inc in self.live.incoming():
                    if inc.share_id == share_id:
                        sh["read"] = inc.read_token
                self._save()
            if not sh.get("read"):
                raise TransportError(404, "not offered by the network")
            page = self.live.read(share_id, sh["read"], after=sh.get("cursor", 0) if after is None else after)
        except TransportError as e:
            if e.status in (404, 410):
                sh["closed"] = True
                self._save()
                self.emit("live_read", r=r, dir="in", share=share_id[:8], n=0, closed=True)
                return {"samples": [], "closed": True}
            raise
        out = []
        for s in page.get("samples", []):
            try:
                body = json.loads(self.me.open(sh["did"], s["body"]["sealed"], salt=share_id))
            except Exception:
                continue
            out.append({"seq": s["seq"], "ts": s.get("ts"), "body": body})
        sh["cursor"] = page.get("cursor", sh.get("cursor", 0))
        self._save()
        self.emit("live_read", r=r, dir="in", share=share_id[:8], n=len(out), closed=bool(page.get("closed")))
        return {"samples": out, "closed": bool(page.get("closed")), "item": sh["item"]}

    # ── pull ──────────────────────────────────────────────────────────────────────────────────────────────────
    def pull(self, reason: str = "idle") -> int:
        from .handlers import dispatch
        t0 = time.monotonic()
        start = self.rels.cursor
        try:
            mail = self.mailbox.pull(after=start)
        except TransportError as e:
            self.emit("pull", ok=False, n=0, cursor_from=start, cursor_to=start, reason=reason, status=e.status)
            return 0
        ms = (time.monotonic() - t0) * 1000
        if not mail:
            self.empty_pulls.append(ms)
            return 0
        for m in mail:
            try:
                dispatch(self, m)
            except Exception as e:                       # I6: one event, the cadence goes on
                self.emit("error", ok=False, where="dispatch", exc_class=type(e).__name__)
            self.rels.set_cursor(m.seq)
        try:
            self.mailbox.ack(self.rels.cursor)
        except TransportError:
            pass
        self.emit("pull", n=len(mail), cursor_from=start, cursor_to=self.rels.cursor, reason=reason, ms=ms)
        return len(mail)

    def sharing(self, who: str | None = None) -> list[dict]:
        """What the owner shares, per accepted contact: `[{cid, name, items:[{item, verbs, expires_at}], recent}]` —
        «¿qué estoy compartiendo?» is read from the grants and the event log, never from a model."""
        out = []
        for r in self.rels.all():
            if r.status != "accepted" or (who and who not in (r.did, r.contact_id)):
                continue
            items = [{"item": g.item, "verbs": list(g.verbs), "expires_at": g.expires_at}
                     for g in self.grants.for_audience(contact_audience(r.contact_id))]
            last = [{"op": e["op"], "dir": e.get("dir", ""), "ts": e.get("ts")}
                    for e in events.recent(r.contact_id, 5)]
            out.append({"cid": r.contact_id, "name": r.name, "items": items, "recent": last})
        return out

    def inbox(self, who: str | None = None) -> list[dict]:
        rows = self.state["inbox"]
        if who is None:
            return list(rows)
        r = self._rel_for(who)
        return [m for m in rows if m["rel"] == r.rel]
