"""widgets/mensajeria/held.py — a send held for the operator's word is a ROW of this card, and so is a send for later.

The class this closes: a message he asked to review before it leaves («write it, show it to me, wait for my "send
it"») had no durable place to wait. It was shown in a document, the draft box of this card knew nothing about it,
and the later «send it» resolved to whatever reply draft happened to be the most recent — or to nothing — while the
voice said it had gone. A send he wants LATER («in ten hours») had no place either.

Both are rows here now, with the shapes this card already had:

  · a HELD draft is a draft (`drafts.py`), keyed by who it goes to when it opens a new conversation; it is what
    `send_draft` sends, named by its recipient (`contact`) or, unnamed, the most recent one;
  · a SCHEDULED send is an order in the outbound queue with `not_before` (`outbound.enqueue`), which the owner's
    own beat already holds until its time — visible in `sent` with `scheduled_for`, and removable with
    `cancel_send` until it leaves.

`held_row` is the hook the consent rule reads (`nucleo/flash/frontend.held_send_ordered`): a draft he has SEEN —
one that has been in front of him across at least one turn of his — is the row his explicit order to send it
confirms. Stdlib only, like everything this widget runs server-side.
"""
from __future__ import annotations

import logging
import re
import time
import unicodedata
from datetime import datetime

logger = logging.getLogger("zaelar.mensajeria.held")

#: The furthest ahead a send may be scheduled. A bound on a consequence, not a judgement: an order parked for
#: months is a forgotten order.
MAX_AHEAD_S = 30 * 86400


def _fold(v) -> str:
    t = unicodedata.normalize("NFKD", str(v or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c)).strip()


def when(payload: dict, now: float | None = None) -> tuple[float, str]:
    """`(epoch, "")` for a send asked for later, `(0.0, "")` for now, `(0.0, error)` when the time cannot be read.

    Two declared keys, both read as data: `at` (an ISO local date-time, «2026-10-26T11:30») and `in_minutes` (a
    number — «dentro de 10 horas» is 600). The model turns his words into one of them; nothing here reads words."""
    now = float(now if now is not None else time.time())
    at, mins = payload.get("at"), payload.get("in_minutes")
    if at in (None, "") and mins in (None, ""):
        return 0.0, ""
    try:
        ts = now + float(mins) * 60.0 if mins not in (None, "") else datetime.fromisoformat(str(at).strip()).timestamp()
    except (TypeError, ValueError):
        return 0.0, "bad_time"
    if ts <= now + 5:
        return 0.0, ""                      # a time already here is «now»
    if ts - now > MAX_AHEAD_S:
        return 0.0, "too_far"
    return ts, ""


def draft_for(db: dict, contact: str) -> str | None:
    """The key of the held draft that goes to `contact` (a name or an address he gave), or None."""
    want = _fold(contact)
    if not want:
        return None
    for k, d in sorted((db.get("drafts") or {}).items(), key=lambda kv: -(kv[1].get("at") or 0)):
        t = d.get("target") or {}
        names = [_fold(t.get("name")), _fold(t.get("to")), _fold(t.get("chatId"))]
        if any(n and (want in n or n in want) for n in names):
            return k
    return None


def held(db: dict) -> list[dict]:
    """Every draft waiting for his word, newest first: `{key, to, subject, text, at}`."""
    out = []
    for k, d in (db.get("drafts") or {}).items():
        t = d.get("target") or {}
        out.append({"key": k, "to": str(t.get("name") or t.get("to") or t.get("chatId") or ""),
                    "platform": str(t.get("platform") or ""), "subject": str(t.get("subject") or ""),
                    "text": str(d.get("text") or ""), "at": float(d.get("at") or 0), "new": bool(t.get("new"))})
    return sorted(out, key=lambda r: -r["at"])


def scheduled(db: dict, now: float | None = None) -> list[dict]:
    """The queued sends whose time has not come yet, soonest first."""
    now = float(now if now is not None else time.time())
    rows = [o for q in ("pending_send", "pending_reply") for o in (db.get(q) or [])
            if isinstance(o, dict) and o.get("scheduled") and float(o.get("not_before") or 0) > now]
    return sorted(rows, key=lambda o: float(o.get("not_before") or 0))


def cancel(db: dict, *, ref: str = "", contact: str = "", now: float | None = None) -> dict:
    """Take a scheduled send out of the queue before it leaves. Named by `ref` or by recipient; with neither, only
    when exactly ONE is scheduled — two would be a guess about which of his sends to stop."""
    rows = scheduled(db, now)
    if ref:
        rows = [o for o in rows if str(o.get("ref") or "") == str(ref)]
    elif contact:
        want = _fold(contact)
        rows = [o for o in rows if any(want and (want in _fold(o.get(f)) or _fold(o.get(f)) in want)
                                       for f in ("name", "to", "chatId") if _fold(o.get(f)))]
    elif len(rows) > 1:
        return {"ok": False, "error": "which_scheduled",
                "message": "Hay varios envíos programados: dime cuál cancelo.",
                "scheduled": [str(o.get("name") or o.get("to") or "") for o in rows]}
    if not rows:
        return {"ok": False, "error": "nothing_scheduled", "message": "No hay ningún envío programado que cancelar."}
    gone = {id(o) for o in rows}
    for q in ("pending_send", "pending_reply"):
        db[q] = [o for o in (db.get(q) or []) if id(o) not in gone]
    return {"ok": True, "cancelled": [str(o.get("name") or o.get("to") or "") for o in rows]}


def seen(draft: dict, his_turns_since) -> bool:
    """Has he had this draft in front of him? Structurally: a turn of his arrived AFTER it was written.

    `his_turns_since(ts)` returns his turns since `ts`. The turn that wrote the draft is not one of them (it came
    before the draft existed), so a «write it and send it» in one breath is never confirmed by itself."""
    at = float((draft or {}).get("at") or 0)
    if not at:
        return False
    try:
        return len(his_turns_since(at + 0.5) or []) > 0
    except Exception as e:  # noqa: BLE001 — unreadable turns: not seen, so the question stays
        logger.info(f"held: his turns unreadable ({e}) — the draft counts as not seen")
        return False


def prompt_lines(db: dict, now: float | None = None) -> list[str]:
    """What the brain reads about held and scheduled sends (product prompt data, in the agent's working language)."""
    now = float(now if now is not None else time.time())
    out = []
    for d in held(db)[:3]:
        subj = f" «{d['subject']}»" if d["subject"] else ""
        out.append(f"· BORRADOR esperando su OK para {d['to']}{subj}: «{d['text'][:120]}» — ya está escrito y lo ha "
                   f"visto en la tarjeta; se envía con send_draft (contact: {d['to']!r}), ahora o con `at`/`in_minutes` "
                   "para más tarde. Su orden explícita de mandarlo ES su confirmación. «Ábrelo / enséñamelo» = "
                   f"open_draft (contact: {d['to']!r}): ocupa la tarjeta entera para revisarlo.")
    for o in scheduled(db, now)[:3]:
        hhmm = datetime.fromtimestamp(float(o.get("not_before") or 0)).strftime("%d/%m %H:%M")
        out.append(f"· PROGRAMADO para el {hhmm} a {o.get('name') or o.get('to')}: «{str(o.get('text') or '')[:80]}» "
                   "(aún no ha salido; cancel_send lo cancela).")
    return out


def held_row(action: str, payload: dict, db: dict, his_turns_since) -> dict | None:
    """The consent hook: the held draft this call SENDS, when he has already seen it — else None."""
    if action != "send_draft":
        return None
    p = payload if isinstance(payload, dict) else {}
    k = draft_for(db, str(p.get("contact") or "")) if p.get("contact") else None
    if str(p.get("key") or "") in (db.get("drafts") or {}):
        k = str(p["key"])
    d = ((db.get("drafts") or {}).get(k) if k else None) or db.get("draft") or None
    return d if d and seen(d, his_turns_since) else None


# ── V2-807 T-09 · one outbound message has ONE body: a version of a held draft written anywhere lands on its row ────

#: How much of the shorter text the other must carry for the two to be versions of ONE message, and how much when
#: the text also names the draft's own recipient address. A bound on overlap, in any language and any wording — no
#: word in it is read for what it means.
SAME_MESSAGE = 0.5
SAME_MESSAGE_ADDRESSED = 0.3
#: Below this many content words a text is too short to be recognised as a version of anything.
MIN_WORDS = 6


def _words(text) -> set[str]:
    return {w for w in re.findall(r"\w+", _fold(text)) if len(w) >= 4}


def _overlap(a: set, b: set) -> float:
    if min(len(a), len(b)) < MIN_WORDS:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def claim(db: dict, text: str, title: str = "") -> dict | None:
    """The held draft `text` is a version of, as the action that writes it there — or None.

    Measured (V2-807 T-09): a held email was copied into a document sheet, every spoken correction rewrote the COPY,
    and «send it» sent the untouched row. A text is that draft's when it carries most of the draft's content, or a
    good part of it while naming the draft's own recipient address. The row then holds the new text (`save_draft`,
    which also puts the draft screen up), so what is sent is what he last corrected."""
    body = str(text or "")
    mine = _words(body)
    whole = _fold(f"{title} {body}")
    for k, d in sorted((db.get("drafts") or {}).items(), key=lambda kv: -(kv[1].get("at") or 0)):
        t = d.get("target") or {}
        addrs = [_fold(t.get(f)) for f in ("to", "chatId", "senderId") if len(_fold(t.get(f))) >= 6]
        named = any(a in whole for a in addrs)
        score = _overlap(mine, _words(d.get("text")))
        if score >= SAME_MESSAGE or (named and score >= SAME_MESSAGE_ADDRESSED):
            return {"action": "save_draft", "payload": {"key": k, "text": body},
                    "to": str(t.get("name") or t.get("to") or t.get("chatId") or ""),
                    "why": f"overlap {score:.2f}" + (" + recipient named" if named else "")}
    return None
