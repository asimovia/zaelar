"""The model's stable prefix for the conversation manager (V2-941, the F1 plan §4.7): what it may read, the language
it writes in and the fields of its two orders — declared, never a script of how to behave (principles: «declare
capabilities, never script behaviour»). Byte-identical between turns for the same language and catalogue, so the
provider caches it; every line is one of `LINES`, and the whole stays under `MAX_TOKENS`.
"""
from __future__ import annotations

from conversation.ports import ToolSpec

MAX_TOKENS = 600

#: the only lines a prefix carries, in this order
LINES = ("LANGUAGE", "INPUT", "READS", "ACTS", "ORDERS", "CLAIMS", "COMPLETE")


def build(catalog: list[ToolSpec], *, native: str, name: str) -> str:
    reads = ", ".join(sorted(t.name for t in catalog)) or "none"
    lines = {
        "LANGUAGE": f"every reply and every text written: {native} ({name}); entries may come in any language",
        "INPUT": "the person's entries since the last reply, each with its id, channel and state; CONVERSATION is "
                 "what was said, ours cut to what was heard; STATE is now and what is open",
        "READS": reads,
        "ACTS": "none in this session: nothing but a read passes",
        "ORDERS": "reply(text, claims, complete) | no_reply(reason, complete)",
        "CLAIMS": "one per figure of data in the text that a read returned as structured evidence (an evidence with "
                  "a value), with that evidence's id",
        "COMPLETE": "true: what was said so far is a thought that can be answered; false: something seems missing",
    }
    return "\n".join(f"{k}: {lines[k]}" for k in LINES)


def current(catalog: list[ToolSpec]) -> str:
    """The prefix in the operator's language as it stands (`i18n.langs`)."""
    from i18n import langs
    spec = langs.current_language()
    return build(catalog, native=spec.native, name=spec.name)
