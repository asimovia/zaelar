"""A typed line that starts with `LOG:` is a note for whoever reads the timeline, not a turn.

Measured: the operator left notes for support inside his own session («LOG: the latency again…») and each one became
a turn — answered, routed, and once opened as an errand. There was no other way to write on the timeline from a
session: everything typed was his word to the agent.

The prefix is recognised at the typed door (`POST /api/chat`), case-insensitive, at the very start of the line
(`LOG:`, `log :`, `LOG:::` are the same). The note is recorded as one `feedback` event — the family the thumbs-down
already uses, so every viewer of the timeline shows it — and nothing else happens: no turn, no reply, no routing, no
errand, and no session is brought up for it.

The SPOKEN note (INI-042 #37, 2026-11-19): «I want to leave a message for support… you don't need to do anything» was
a turn — the agent opened a document, asked whether to draft the feedback, and the end of the sentence was lost. A
spoken note has no prefix, so it is recognised by INTENT, at the body's turn gate once the sentence is whole:

  · a cheap proposal — the sentence names the support team, in his language (`support_note.names` of the `voice`
    pack). Nothing else pays anything: a turn that names no support asks no question and waits for nothing;
  · the decision — the turn brief's `support_note` verdict (asked only when proposed, so the one trip the turn pays
    anyway carries it), awaited before the model like the hard stop's. Only a sure `note` makes it a note; a doubt,
    a late or an unreadable verdict is an ordinary turn.

A note goes to the timeline as the same `feedback` event, and the turn ends there: at most a two-to-four-word
acknowledgement, worded by `nucleo/wording.py` (or silence when no line comes back in time).
"""
from __future__ import annotations

import re

#: `LOG` then one or more colons, at the start of the line, any case.
_PREFIX = re.compile(r"^\s*log\s*:+\s*", re.IGNORECASE)
#: How much of a note the timeline keeps.
MAX_CHARS = 2000


def body(text: str) -> str | None:
    """The note without its prefix, or None when the line is not a note (an ordinary turn)."""
    m = _PREFIX.match(str(text or ""))
    return None if m is None else str(text)[m.end():].strip()


def _write(note: str, label: str, **extra) -> None:
    try:
        from voice.observer import emit
        emit("feedback", label, text=note[:MAX_CHARS], role="user",
             extra={"cat": "system", "support_note": True, **{k: v for k, v in extra.items() if v}})
    except Exception as e:  # noqa: BLE001 — a note that cannot be traced is still not a turn
        from loguru import logger
        logger.warning(f"support_note: the note could not be traced — {type(e).__name__}: {e}")


def record(text: str, dev: str = "") -> bool:
    """Record the line if it is a note. True = it was a note and must not become a turn."""
    note = body(text)
    if note is None:
        return False
    _write(note, "📝 support note (LOG:)", dev=dev)
    return True


# ── the spoken note ───────────────────────────────────────────────────────────────────────────────────────────────

KEY = "support_note"
INSTRUCTIONS = ("Is the operator leaving a note for the assistant's support team (the people who build and maintain "
                "it) — words meant for them to read later — rather than asking the assistant to do something now?")
CRITERIA = {
    "note": "he is leaving a note, report or comment for the support team to read later; the assistant is not asked "
            "to act on it, draft it, send it or answer it",
    "turn": "he is asking the assistant itself to do, show, find, answer, write or send something now — support may "
            "be mentioned, but the request is for the assistant",
}
#: What the acknowledgement says: that the note is kept, and nothing else.
ACK_FACT = ("He just left a note for the support team. It is written down for them; you do nothing else with it. "
            "Acknowledge it in two to four plain words — no question, no offer, nothing about what it says.")
#: How long the turn waits for the verdict once proposed — the same bound as the hard stop's early verdict.
WAIT_S = 2.0


def proposes(text: str) -> bool:
    """The sentence names the support team, in his language. A proposal only: the brief's verdict decides."""
    low = " ".join(str(text or "").lower().split())
    if not low:
        return False
    try:
        from i18n import langs
        names = langs.words("support_note.names", default=()) or ()
    except Exception as e:  # noqa: BLE001 — no words, no proposal: the sentence is a turn
        from loguru import logger
        logger.debug(f"support_note: the support words unread — {type(e).__name__}: {e}")
        return False
    return any(re.search(rf"(?<!\w){re.escape(str(n).lower())}(?!\w)", low) for n in names if str(n).strip())


def question(ctx) -> dict | None:
    """The brief's question — built only for a sentence that proposes a note, so no other turn pays for it."""
    if not proposes((ctx or {}).get("operator_text") or ""):
        return None
    return {"instructions": INSTRUCTIONS, "criteria": dict(CRITERIA)}


async def heard(text: str, say=None) -> bool:
    """At the body's turn gate, on the whole sentence: True = it was a note for support, recorded, and the turn ends.
    Never raises: anything unread is an ordinary turn."""
    if not proposes(text):
        return False
    try:
        from nucleo.turn import brief
        choice, info = await brief.verdict_before_the_turn(text, KEY, wait_s=WAIT_S)
    except Exception as e:  # noqa: BLE001 — an unread verdict is an ordinary turn
        from loguru import logger
        logger.info(f"support_note: the verdict was not read — {type(e).__name__}: {e}")
        return False
    if choice != "note" or not (info and info.get("used")):
        return False
    _write(str(text).strip(), "📝 support note (voice)", verdict=KEY)
    if say is not None:
        try:
            from nucleo import wording
            line = await wording.word_soon(ACK_FACT, fallback="")
            if line:
                say(line)
        except Exception as e:  # noqa: BLE001 — the note is kept; the acknowledgement is optional
            from loguru import logger
            logger.info(f"support_note: no acknowledgement — {type(e).__name__}: {e}")
    return True
