"""ONE model read of what he just said, against the send that is open: is it about THIS message, and what changes.

It never decides who the person is (that is `people`, by his contacts) and never sends: it says what his words
change — the name he gives or picks, the whole new text, his go-ahead, his no, or a question about which people
carry a name — and whether his words are about this message at all. Words that are not stay the conversation's.
"""
from __future__ import annotations

import json
import re

from loguru import logger

SEAT = "send"
#: The read's budget. Past it his words are the conversation's: a slow read never holds them.
READ_S = 4.0

SYSTEM = (
    "You help a voice assistant that is writing ONE message for its owner to send to somebody. You get the message as "
    "it stands — who it is for (or the people it could be for), its text, what the assistant last said — and what the "
    "owner just said. Decide whether his words are about THIS message, and what they change.\n"
    "They are about it (\"mine\": true) only when they: name or pick who it goes to (a name, «the second one», «the one "
    "from Valencia»), dictate, add to, remove from or reword what it says, tell the assistant to send it, tell it not "
    "to send it or to forget it, or ask which people he has with the name in question (or who the options are).\n"
    "They are NOT about it (\"mine\": false) when they are about the assistant itself (it is slow, it repeats him, it "
    "did not listen, it talks too much), a greeting, thanks, a comment, a question about anything else, another "
    "request — even while the message is open, even if it is about the same person. In doubt: false.\n"
    "When mine, fill only what his words change:\n"
    "  \"who\": the person he names or picks — when he picks among the people listed, their FULL name exactly as "
    "listed; otherwise the name as he said it. \"\" when he does not name anyone.\n"
    "  \"text\": the WHOLE message as it must now read, or null when he does not change what it says. Write it as "
    "the message itself, in his voice, addressed to the person, in the language he speaks: «dile que la quiero mucho» "
    "→ «Te quiero mucho»; «tell him I'm late» → «I'm late». Keep what the message already says and apply his change "
    "(add his new words; when he removes a part — «quita esa última frase», «drop the last bit» — take exactly that "
    "part out). Never add words he did not give.\n"
    "  \"channel\": \"whatsapp\", \"telegram\" or \"email\" only when he names one; else \"\".\n"
    "  \"send\": true only when he plainly tells it to send the message as it stands now (yes, send it, go ahead) "
    "with no change in the same words.\n"
    "  \"drop\": true when he says not to send it, to cancel it or to forget it.\n"
    "  \"list\": the name he asks about when he asks which people with that name he has (or who the options are); "
    "else \"\".\n"
    "Reply with JSON only: {\"mine\": bool, \"who\": str, \"text\": str|null, \"channel\": str, \"send\": bool, "
    "\"drop\": bool, \"list\": str}"
)

#: The read of a sentence that changes nothing (a failed read is this too, with `mine` false).
NOTHING = {"mine": False, "who": "", "text": None, "channel": "", "send": False, "drop": False, "list": ""}


def _state(draft, last_line: str) -> str:
    if draft.target:
        to = f"«{draft.target.get('name')}» (chosen)"
    elif draft.candidates:
        to = "not chosen yet; the people it could be: " + "; ".join(
            f"«{c['name']}»" + (f" ({c['note']})" if c.get("note") else "") for c in draft.candidates)
    elif draft.who:
        to = f"not found yet — he said «{draft.who}»"
    else:
        to = "nobody yet"
    text = f"«{draft.text}»" if draft.text else "(nothing yet)"
    out = f"THE MESSAGE:\n  for: {to}\n  text: {text}\n"
    if last_line:
        out += f"THE ASSISTANT JUST SAID: «{last_line[:300]}»\n"
    return out


def parse(raw: str) -> dict:
    """The model's JSON as a read; `NOTHING` when it cannot be read."""
    m = re.search(r"\{.*\}", str(raw or ""), re.S)
    try:
        got = json.loads(m.group(0)) if m else None
    except ValueError:
        got = None
    if not isinstance(got, dict):
        return dict(NOTHING)
    text = got.get("text")
    chan = str(got.get("channel") or "").strip().lower()
    return {"mine": got.get("mine") is True, "who": str(got.get("who") or "").strip(),
            "text": " ".join(str(text).split()) if isinstance(text, str) and text.strip() else None,
            "channel": chan if chan in ("whatsapp", "telegram", "email") else "",
            "send": got.get("send") is True, "drop": got.get("drop") is True,
            "list": str(got.get("list") or "").strip()}


def _ask(system: str, user: str) -> str:
    from nucleo.memory_agent.processor import llm
    return llm.chat_sync(SEAT, system, user, max_tokens=220, temperature=0.0, timeout=READ_S) or ""


def read(said: str, draft, last_line: str = "", before: list[str] | None = None) -> dict:
    """What `said` changes in `draft`. Blocking: call it off the loop. Never raises."""
    user = _state(draft, last_line)
    if before:
        user += "HE SAID BEFORE: " + " · ".join(f"«{b}»" for b in before[-2:]) + "\n"
    user += f"HE NOW SAYS: «{str(said)[:600]}»"
    try:
        return parse(_ask(SYSTEM, user))
    except Exception as e:  # noqa: BLE001 — an unread sentence is the conversation's
        logger.info(f"send.read: unread ({type(e).__name__}: {e})")
        return dict(NOTHING)
