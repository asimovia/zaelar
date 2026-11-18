"""The read of his words for an ACT toward a messaging platform (a group left, a group created) — apart from the
message's read, whose instruction was measured for messages and is not diluted with acts.

Two questions, one model call each:
  · `read(said, draft)` — with an act open: is this sentence about it (his go-ahead, his no, which groups or people)?
  · `choose(said, acts)` — an order on the messaging card with no act read and no call: which of the card's DECLARED
    acts his words order, if any, and what they name. The model picks among what is declared; it never invents one.
"""
from __future__ import annotations

import json
import re
import time

from loguru import logger

from nucleo.send import read as _read

SYSTEM = (
    "You help a voice assistant that is about to do ONE act for its owner on a messaging app (the act is named below: "
    "leaving groups, creating a group…). You get the act as it stands, what it is about, what the assistant asked him, "
    "and what the owner just said. Decide whether his words are about THIS act.\n"
    "They are about it (\"mine\": true) when they confirm it, refuse it, or say which groups or people it is about. They "
    "are NOT (\"mine\": false) when they are about the assistant itself (slow, repeating him, not listening), a "
    "greeting, a comment, a question about anything else, or another request. In doubt: false.\n"
    "When mine:\n"
    "  \"send\": true when he plainly tells it to go ahead as it stands (yes, do it, delete them, go ahead) — naming "
    "again the very things it is already about is no change.\n"
    "  \"bare\": true when his words are ONLY an affirmation (yes, ok, sure, vale) that never names the act («delete "
    "them», «leave them», «do it») nor what it is about.\n"
    "  \"drop\": true when he says not to do it, to cancel it or to forget it.\n"
    "  \"names\": EVERY group or person his words name for it, each as he said it, in a list — when his words point "
    "back («delete them», «those two»), the ones he named before; [] when he names none.\n"
    "Reply with JSON only: {\"mine\": bool, \"send\": bool, \"bare\": bool, \"drop\": bool, \"names\": [str]}"
)

CHOOSE = (
    "The owner of a voice assistant gave an order. Below are the ACTS the assistant can do on his messaging app, each "
    "with what it does. Decide which ONE of them his words order — only if they plainly order exactly that act (leave or "
    "delete groups he names, create a group…); a message to somebody is none of them; in doubt, none.\n"
    "Reply with JSON only: {\"act\": \"<one of the act names, or empty>\", \"names\": [<every group or person his words "
    "name for it, as he said them; when his words point back («delete them»), the ones he named before>]}"
)


def _ask(system: str, user: str) -> str:
    return _read._ask(system, user)          # the one seam of the owner's reads (`read._ask`, offline in the suite)


def _json(raw: str) -> dict | None:
    m = re.search(r"\{.*\}", str(raw or ""), re.S)
    try:
        got = json.loads(m.group(0)) if m else None
    except ValueError:
        got = None
    return got if isinstance(got, dict) else None


def _names(got: dict) -> list[str]:
    v = got.get("names")
    return [str(x).strip() for x in v if str(x or "").strip()][:20] if isinstance(v, list) else []


def _context(said: str, last_line: str, before) -> str:
    out = f"NOW: {time.strftime('%Y-%m-%dT%H:%M (%A)')}\n"
    if last_line:
        out += f"THE ASSISTANT JUST SAID: «{last_line[:300]}»\n"
    if before:
        out += "HE SAID BEFORE: " + " · ".join(f"«{b}»" for b in before[-2:]) + "\n"
    return out + f"HE NOW SAYS: «{str(said)[:600]}»"


def read(said: str, draft, last_line: str = "", before: list[str] | None = None) -> dict:
    """The message read's shape (`read.NOTHING`'s keys) for an act: mine · send · drop · names."""
    about = ", ".join(f"«{x}»" for x in draft.names_said()) or "(nothing named yet)"
    user = f"THE ACT: {draft.act} — he asked: «{draft.said}»\n  it is about: {about}\n"
    if draft.confirm_line:
        user += f"THE ASSISTANT ASKED HIM: «{draft.confirm_line[:300]}»\n"
    try:
        got = _json(_ask(SYSTEM, user + _context(said, last_line, before)))
    except Exception as e:  # noqa: BLE001
        logger.info(f"send.read_act: unread ({type(e).__name__}: {e})")
        got = None
    if got is None:
        return {**_read.NOTHING, "unread": True}
    return {**_read.NOTHING, "mine": got.get("mine") is True, "send": got.get("send") is True,
            "bare": got.get("bare") is not False, "drop": got.get("drop") is True, "names": _names(got)}


def choose(said: str, acts: dict[str, str], last_line: str = "", before: list[str] | None = None) -> dict:
    """`{"act": name, "names": [...]}` — the declared act his words order, or `{"act": ""}`."""
    if not acts:
        return {"act": "", "names": []}
    menu = "\n".join(f"- {name}: {desc[:240]}" for name, desc in acts.items())
    try:
        got = _json(_ask(CHOOSE, f"THE ACTS:\n{menu}\n" + _context(said, last_line, before)))
    except Exception as e:  # noqa: BLE001
        logger.info(f"send.read_act: no choice ({type(e).__name__}: {e})")
        got = None
    act = str((got or {}).get("act") or "").strip()
    return {"act": act if act in acts else "", "names": _names(got or {})}
