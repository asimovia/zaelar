"""nucleo/turn/owed_words.py — the words a cut turn still owes ride THIS turn's message to the model.

A turn cancelled before its first word leaves his sentence in the dialog window (`dialog.push_user`) and owes it to the
next turn's verdict (`stt.whole_turn`): the brief judges both sentences as one. The model was handed them apart — the
cut sentence as an earlier user message, the new one as the turn's own — on the expectation that it answers both.

Measured on a text session (2026-11-16): three typed lines reached the engine within a second («Add a piano lesson
on Thursday at 6pm.», «Add brunch with the family on Sunday at 11am.», «Remind me tomorrow at 8am…»). Each cut the
one before it, the brief judged the three together, and the model — three consecutive user messages in its window —
served only the last: two appointments were never written and never mentioned.

So the model is handed what the verdict judged: the owed sentences and this turn's as ONE user message, and the
window's trailing copies of the owed ones are left out of this call (the window itself is not rewritten). One
sentence, one verdict, one message.
"""
from __future__ import annotations

from loguru import logger


def _norm(text) -> str:
    return " ".join(str(text or "").lower().split())


def as_one_message(window: list[dict], text: str, judged) -> tuple[list[dict], str]:
    """`(window, user_text)` for the model. `judged` is the brain's `(said, whole)` pair (`stt.whole_turn`): when
    `whole` is `said` preceded by owed words, the user text carries them first and the window's trailing user
    messages that are those words are dropped. Anything else comes back untouched. Never raises."""
    try:
        said, whole = (str(x or "").strip() for x in (judged or ("", "")))
        if not said or whole == said or not whole.endswith(said) or not str(text or "").strip().startswith(said):
            return window, text
        owed = whole[: len(whole) - len(said)].strip()
        if not owed:
            return window, text
        kept, n_owed = list(window), _norm(owed)
        while kept and kept[-1].get("role") == "user" and (c := _norm(kept[-1].get("content"))) and c in n_owed:
            kept.pop()
        try:
            from voice.observer import emit
            emit("brain", "🧩 the words a cut turn owed ride this turn's message", text=owed[:160], role="system",
                 extra={"cat": "flash", "owed_chars": len(owed), "dropped": len(window) - len(kept)})
        except Exception as e:  # noqa: BLE001 — the trace never decides the prompt
            logger.debug(f"owed_words: trace not emitted — {e!r}")
        return kept, f"{owed}\n{str(text).strip()}"
    except Exception as e:  # noqa: BLE001 — a prompt may never break on its own bookkeeping
        logger.debug(f"owed_words: not merged — {e!r}")
        return window, text


def for_model(brain, window: list[dict], text: str) -> tuple[list[dict], str]:
    """`as_one_message` with what this brain's admission judged (`stt.whole_turn`)."""
    return as_one_message(window, text, getattr(brain, "_judged_turn", None))
