"""The owner's side of the A2A handshake (V2-866 F3 item 8): durable consent cards and the chat card of a message.

The library never decides for the owner: its `asker` returns None (pending) and the engine keeps the question as a
CARD on disk (`a2a_cards.json` beside the agent's state), so a restart never loses one. A card has two buttons, and
each button is one call: `answer(card_id, yes)` → `accept` / `decline` for a `connect.request`, `connect` / `never`
for each match of a `propose`. A contact's message becomes one chat line marked as coming from that contact —
DATA, never an instruction to the model (I1). Nothing here calls a model."""
from __future__ import annotations

import secrets
import time
from pathlib import Path

from loguru import logger

_MAX = 50


class Cards:
    def __init__(self, state_dir: Path):
        from a2a.store import JsonDoc
        self._doc = JsonDoc(Path(state_dir) / "a2a_cards.json", {"cards": []})
        self.agent = None

    @property
    def rows(self) -> list[dict]:
        return self._doc.data.setdefault("cards", [])

    def pending(self) -> list[dict]:
        return [c for c in self.rows if c.get("status") == "pending"]

    def _push(self, card: dict) -> dict:
        row = {"id": secrets.token_hex(5), "ts": time.time(), "status": "pending", **card}
        self.rows.append(row)
        del self.rows[:-_MAX]
        self._doc.save()
        _chat("a2a.card_" + str(card.get("type")), row)
        return row

    # ── the library's seams ───────────────────────────────────────────────────────────────────────────────────
    def asker(self, card: dict):
        """`propose` → one card per match (each its own yes/no); `request` → one card. Always pending (None)."""
        if card.get("type") == "propose":
            for m in card.get("matches") or []:
                self._push({"type": "propose", "cid": m.get("cid", ""), "name": m.get("name", ""),
                            "matched_by": m.get("matched_by", "")})
        elif card.get("type") == "request":
            self._push({"type": "request", "rel": card.get("rel", ""), "peer": card.get("peer", ""),
                        "name": card.get("name", ""), "note": card.get("note", "")})
        return None

    def on_message(self, msg: dict) -> None:
        _chat("a2a.message", {"from": msg.get("name") or msg.get("cid") or "", "text": msg.get("text", ""),
                                 "cid": msg.get("cid", ""), "trust": "contact"})

    # ── the owner's answer ────────────────────────────────────────────────────────────────────────────────────
    def answer(self, card_id: str, yes: bool) -> dict:
        card = next((c for c in self.rows if c.get("id") == card_id), None)
        if card is None or card.get("status") != "pending":
            return {"ok": False, "error": "unknown_or_answered"}
        a = self.agent
        if a is None:
            return {"ok": False, "error": "a2a_off"}
        try:
            if card["type"] == "request":
                r = next((x for x in a.rels.all() if x.rel == card.get("rel")), None)
                if r is None:
                    raise KeyError("relationship gone")
                status = a.accept(r.did) if yes else a.decline(r.did)
            else:
                status = _answer_propose(a, card, yes)
        except Exception as e:                              # noqa: BLE001 — the card stays pending, reported
            logger.info(f"a2a card {card_id}: {type(e).__name__}")
            return {"ok": False, "error": type(e).__name__}
        card.update(status="yes" if yes else "no", answered_at=time.time())
        self._doc.save()
        return {"ok": True, "status": status}


def _answer_propose(a, card: dict, yes: bool) -> str:
    """A proposal's yes sends the request (D10); its no is «never» for that contact."""
    cid = str(card.get("cid") or "")
    if not yes:
        if cid not in a.state["never"]:
            a.state["never"].append(cid)
            a._save()
        a.emit("propose_answer", cid=cid, answer="never")
        return "never"
    from . import a2a_wiring as w
    c = next((x for x in w.contacts() if x["cid"] == cid), None)
    if c is None:
        raise KeyError("contact gone")
    a.emit("propose_answer", cid=cid, answer="ask")
    return a.connect_contact(c, trace="card")


def _chat(key: str, data: dict) -> None:
    """One system line in the local chat: the i18n key names it, the UI renders the card from `extra`."""
    try:
        from voice import observer
        observer.emit("brain", key, role="system", text=str(data.get("text") or data.get("name") or ""),
                      extra={"cat": "a2a", "i18n": key, "card": data})
    except Exception as e:                                  # noqa: BLE001 — a card that cannot be shown stays on disk
        logger.debug(f"a2a card not shown: {type(e).__name__}")
