"""The contact card's A2A buttons (V2-866 F3 item 7): connect / accept / decline / grant / revoke for ONE contact.

`internal` in the manifest: the card's buttons call them, the model never does (voice goes through the turn's own
`a2a_*` tools, offered only while a relationship exists). Each reaches the running agent through `a2a.runtime()`;
while A2A is off every one answers `a2a_off` and touches nothing."""
from __future__ import annotations

def _contact_row(c: dict) -> dict:
    from . import model
    return {"cid": str(c["id"]), "name": str(c.get("name") or ""), "emails": model.values(c, "emails"),
            "phones": model.values(c, "phones")}


def _a_a2a(action, payload, q, db, contacts, now) -> dict:
    import a2a
    agent = a2a.runtime()
    if agent is None:
        return {"ok": False, "error": "a2a_off"}
    from . import data as _d                                # lazy: `data` imports this module for its table
    c = _d._find(db, payload.get("contactId"))
    if not c:
        return {"ok": False, "error": "unknown_contact"}
    cid = str(c["id"])
    try:
        if action == "a2a_request":
            status = agent.connect_contact(_contact_row(c), trace="contact_card")
        elif action == "a2a_accept":
            status = agent.accept(cid)
        elif action == "a2a_decline":
            status = agent.decline(cid)
        elif action == "a2a_grant":
            g = agent.grant(cid, str(payload.get("item") or ""), tuple(payload.get("verbs") or ("see",)),
                            ttl_s=int(payload.get("ttl_s") or 0), how="contact_card")
            status = "granted:" + g.item
        else:                                               # a2a_revoke
            status = f"revoked:{agent.revoke(cid, str(payload.get('item') or ''))}"
    except Exception as e:                                  # noqa: BLE001 — the card says why, the store is untouched
        return {"ok": False, "error": type(e).__name__}
    return {"ok": True, "result": {"status": status, "a2a": a2a.contact_block(cid)}}


ACTIONS = {k: _a_a2a for k in ("a2a_request", "a2a_accept", "a2a_decline", "a2a_grant", "a2a_revoke")}
WRITES = ("add_contact", "update_contact", "set_channel", "add_phone", "add_email")


def after(action: str, payload: dict, out: dict) -> dict:
    """After any action: a contact write publishes `contact.saved` (the A2A jobs debounce one lookup), and a contact
    in the result carries its `a2a` block. Never raises: the write already happened."""
    try:
        contact = (out.get("result") or {}).get("contact") if isinstance(out, dict) else None
        cid = str((contact or {}).get("id") or payload.get("contactId") or "")
        if action in WRITES and out.get("ok") and cid:
            import bus
            bus.emit_sync("contact.saved", {"cid": cid})
        if isinstance(contact, dict) and cid:
            import a2a
            block = a2a.contact_block(cid)
            if block:
                contact["a2a"] = block
    except Exception:                                       # noqa: BLE001
        pass
    return out
