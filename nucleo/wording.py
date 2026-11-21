"""nucleo/wording.py — a FACT the engine has to tell him, worded by a model: never a fixed sentence.

His rule (2026-11-18): what the agent says is natural and different every time; nothing he hears is a hardcoded line.
The engine knows FACTS — «the message for her is ready», «it was sent and the service confirmed it», «it could not be
sent: no connection» — and it used to say each one with the same string. `word(fact)` hands the fact to a small model
with the voice's rules and a few EXAMPLES of tone (the old strings, as examples and never as templates) and returns
what it wrote, in his language.

Two things it never does. It adds nothing: the model words the fact, the engine decides it — a line cannot claim a
send the receipt has not confirmed, because the fact handed over is the receipt's. And it never leaves him in
silence: with no answer in `WORD_S` the caller's `fallback` is said (the example line), and the timeline says so.

It speaks about WHAT HE ASKED FOR, in his terms — the message to her, the coffee study, the car he is looking for —
and never about tasks, processes, flows or any other inner working.
"""
from __future__ import annotations

import asyncio

from loguru import logger

SEAT = "wording"
#: The budget of one line. Past it the fallback is said: a line that arrives late is worse than a plain one on time.
WORD_S = 1.8

SYSTEM = (
    "You are the voice of a personal assistant speaking to its owner. You are given a FACT the assistant must tell "
    "him right now. Say it to him in {language}, the way a person says it aloud: one short sentence, two at most, "
    "plain and warm, no preamble and no formatting.\n"
    "Word it differently every time: the examples only show the tone and the length, never copy one.\n"
    "Say exactly what the fact states and nothing else: no extra detail, no promise, no name and no outcome the fact "
    "does not state. If the fact is a question for him, ask it and stop there.\n"
    "Speak about WHAT HE ASKED FOR, in his own terms — the message to her, the coffee brands study, the car he is "
    "looking for. Never mention tasks, processes, flows, workers, jobs, queues or any other inner working of the "
    "assistant: to him there is only what he asked for.\n"
    "You are talking TO him: say «you», never «he» — the fact is written about him, your sentence is said to him.\n"
    "Reply with the sentence only."
)


#: The exit door's question: the plain one names who it goes to; the model asks it its own way.
READY = ("What he asked to send is written and he can read it on screen. Ask him whether you should send it TO THE "
         "PERSON the plain question names (the message goes to that person, never to him), and name that person. "
         "The plain question: {plain}")
#: The same door for an act that is NOT a message (a group, an invitation): its own question, never the message's.
READY_ACT = ("What he asked for is ready to be done and needs his go-ahead first. Ask him the plain question below in "
             "your own words, naming what it is and who it reaches. It is not a message unless the question says so. "
             "The plain question: {plain}")
#: He may want one of his widgets changed, or a new one built, and the reading is not sure he ORDERED it.
UNSURE_CARD = ("It is not clear whether he wants you to {change} a widget of his. What you understood he may want: "
               "«{what}». Ask him, in one short question, whether he wants you to do that. Do not start anything.")
#: A question about ONE of several things he asked for: he has to know which one it is about.
ASKS = ("Several things he asked for are under way; about ONE of them he has to answer a question. Say which one it "
        "is about, in a few words of his own, and ask it. The question: {question}")
#: What the engine knows at each point of a request — the FACT behind each line it says. Keyed by the language's own
#: line for that moment, which rides as the example and the last resort.
FACTS = {
    "send_preparing": "He asked to send a message. You are getting it ready now; nothing has been sent yet.",
    "send_going": ("He gave his go-ahead. The message is being sent right now — not confirmed yet. He will be told if "
                   "anything goes wrong."),
    "send_not_sent": "He said no. The message is NOT sent and nothing has left.",
    "send_done": ("The message has been SENT: the messaging service confirmed it went out. (Sent — say nothing about "
                  "it being received or read.)"),
    "send_failed": "The message could NOT be sent. The reason the messaging service gave: {why}.",
    "send_unconfirmed": ("The message was handed over to be sent, but its confirmation has not arrived yet. He will "
                         "be told as soon as it does."),
    # the same moments of an act that leaves and is NOT a message (a group created, an invitation placed): said of
    # WHAT HE ASKED FOR, which rides as `about` — never «the message»
    "act_preparing": "You are starting on what he asked for now; it is not done yet.",
    "act_going": ("He gave his go-ahead. What he asked for is being done right now — not confirmed yet. He will be "
                  "told if anything goes wrong."),
    "act_not_done": "He said no. What he asked for is NOT done and nothing has left.",
    "act_done": ("What he asked for is DONE (confirmed by the service — do not mention the confirmation). Tell him "
                 "it is done, naming what it was in a few words."),
    "act_failed": "What he asked for could NOT be done. The reason the service gave: {why}.",
    "act_unconfirmed": ("What he asked for was handed over, but its confirmation has not arrived yet. He will be told "
                        "as soon as it does."),
    "work_started": "He gave his go-ahead. You are starting on what he asked for now and will tell him when it is done.",
    "confirm_cancelled": "He said no. Nothing has been done or changed.",
    "answer_taken": ("He just added or answered something about what he asked for. You heard it and you are on it. "
                     "Tell him only that — two to five plain words, an acknowledgement with no praise and no "
                     "«perfect»; say nothing of what he said."),
    "kept_until_start": ("What he asked for has NOT started yet: this computer is too busy right now and it is waiting "
                         "for room. What he just said is kept for it. It starts by itself as soon as there is room; he "
                         "can tell you to start it anyway, or to drop it. Tell him exactly that, briefly."),
    "starting_anyway": ("He told you to start it without waiting. You are starting what he asked for right now, even "
                        "though this computer is busy."),
    "still_held": ("What he asked for has NOT started yet: this computer is too busy right now and it is still waiting "
                   "for room. It starts by itself when there is room; he can tell you to start it anyway, or to drop "
                   "it. Tell him exactly that, briefly — no apology."),
    "stopped_now": "He asked to stop. What he had asked for has been stopped now; it is no longer being worked on.",
}


#: The line of each moment of an act that leaves, by the family its event type declares
#: (`nucleo/events/vocabulary.says`): a message has its own; any other act is told as what he asked for.
LINES = {"send": {"preparing": "send_preparing", "going": "send_going", "no": "send_not_sent", "done": "send_done",
                  "failed": "send_failed", "late": "send_unconfirmed"},
         "act": {"preparing": "act_preparing", "going": "act_going", "no": "act_not_done", "done": "act_done",
                 "failed": "act_failed", "late": "act_unconfirmed"}}


def line(family: str, moment: str) -> str:
    """The key of the line for this moment of a leaving act of this family ("act" for any family not declared)."""
    return LINES.get(family if family in LINES else "act", LINES["act"])[moment]


def ready(family: str) -> str:
    """The exit door's question as a fact, for the act's family of lines ("send" — a message — or the act's own)."""
    return READY if family == "send" else READY_ACT


def _clean(raw: str) -> str:
    """The model's sentence as it is said: one line, no wrapping quotes, bounded."""
    line = " ".join(str(raw or "").split()).strip()
    for a, b in (('"', '"'), ("«", "»"), ("“", "”"), ("'", "'")):
        if len(line) > 1 and line.startswith(a) and line.endswith(b):
            line = line[1:-1].strip()
    return line[:280]


def _model(system: str, user: str, seat: str) -> str:
    """The model's answer: warm enough that two tellings of one fact differ, bounded by the line's budget."""
    from nucleo.memory_agent.processor import llm
    return llm.chat_sync(seat, system, user, max_tokens=90, temperature=0.9, timeout=WORD_S) or ""


_ask = _model       # the seam: the suite keeps every line offline by replacing THIS name (`tests/conftest.py`)


def word(fact: str, *, examples: tuple = (), about: str = "", fallback: str = "", seat: str = SEAT,
         system: str = "") -> str:
    """`fact` worded for his ear, in his language. `examples`: lines that show the tone; `about`: what he asked for, in
    his words, so the line can name it. With no answer in time → `fallback`. Blocking: call it off the loop
    (`word_soon`) or from a worker thread."""
    fact = " ".join(str(fact or "").split())
    if not fact:
        return fallback
    try:
        from i18n import langs
        language = str(getattr(langs.current_language(), "name", "") or "his language")
        user = f"FACT: {fact}"
        if about:
            user += f"\nWHAT HE ASKED FOR, in his words: «{str(about)[:200]}»"
        shown = [str(e) for e in examples if str(e or "").strip()][:3]
        if shown:
            user += "\nEXAMPLES of the tone (do not copy): " + " · ".join(f"«{e}»" for e in shown)
        line = _clean(_ask(_styled((system or SYSTEM).format(language=language)), user, seat))
        if line:
            return line
        logger.info(f"wording: no line came back for «{fact[:60]}» — the plain one is said")
    except Exception as e:  # noqa: BLE001 — a line that cannot be worded is said plainly, never dropped
        logger.info(f"wording: not worded ({type(e).__name__}: {e}) — the plain one is said")
    return fallback


def _styled(system: str) -> str:
    """The wording's system with HOW the agent speaks — the one style line the conversation's prefix reads too
    (`style_policy.line`), so a worded line and a reply never speak two ways (C3)."""
    try:
        from nucleo import style_policy
        style = style_policy.line()
    except Exception as e:  # noqa: BLE001 — unread: the wording's own rules alone
        logger.debug(f"wording: style unread ({e!r})")
        style = ""
    return f"{system}\nHOW YOU SPEAK: {style}" if style else system


async def said(key: str, about: str = "", **fmt) -> str:
    """The line for the moment `key` names (`FACTS`), worded: the language's own line for it is the example and the
    last resort. "" when the language has no such line and no model answered."""
    from i18n import langs
    plain = str(getattr(langs.current_language(), key, "") or "")
    try:
        plain = plain.format(**fmt).strip().rstrip(":").strip()
    except Exception:  # noqa: BLE001 — a line whose blanks cannot be filled is not an example
        plain = ""
    fact = FACTS.get(key, "")
    told = {k: (str(v).strip() or "not given") for k, v in fmt.items()}
    return await word_soon(fact.format(**told), examples=(plain,), about=about, fallback=plain) if fact else plain


async def word_soon(fact: str, **kw) -> str:
    """`word` off the loop, bounded: the fallback when it does not come back in time."""
    try:
        return await asyncio.wait_for(asyncio.to_thread(word, fact, **kw), WORD_S + 0.4)
    except Exception as e:  # noqa: BLE001
        logger.info(f"wording: late ({type(e).__name__}) — the plain one is said")
        return str(kw.get("fallback") or "")
