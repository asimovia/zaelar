"""The model's stable prefix for the conversation manager (V2-941, the F1 plan §4.7): who is who, the language, what it
may read and what exists but is held, and the fields of its two orders — declared, never a script of how to behave
(principles: «declare capabilities, never script behaviour»). Byte-identical between turns for the same names,
language and catalogue, so the provider caches it; every line is one of `LINES`, and the whole stays under
`MAX_TOKENS`.
"""
from __future__ import annotations

from conversation.ports import ToolSpec

MAX_TOKENS = 600

#: the only lines a prefix carries, in this order
LINES = ("YOU", "PERSON", "LANGUAGE", "INPUT", "READS", "ACTS", "ORDERS", "CLAIMS", "COMPLETE", "LENGTH")


def build(catalog: list[ToolSpec], *, native: str, name: str, agent: str = "", person: str = "",
          held: tuple[str, ...] = (), budget: dict | None = None) -> str:
    """`agent`: the assistant's own name; `person`: the person's, when known; `held`: the acts that exist but are held in
    this phase (the event vocabulary's names)."""
    reads = "; ".join(f"{t.name}: {t.about}" if t.about else t.name for t in sorted(catalog, key=lambda t: t.name))
    lines = {
        "YOU": f"the assistant{f', named {agent}' if agent else ''} — the name the person calls you by, never the "
               f"person's",
        "PERSON": f"named {person}" if person else "name not known yet",
        "LANGUAGE": f"each reply in the language of the person's entries it answers; when that is not clear, {native} "
                    f"({name})",
        "INPUT": "the entries to answer now, each on its own whatever CONVERSATION holds, with its id, channel and "
                 "time; an entry cut off says so; CONVERSATION is what was said before, ours cut to what was heard, an "
                 "earlier session marked with its age; STATE is now and what is open, its notes possibly in another "
                 "language than the conversation's",
        "READS": reads or "none",
        "ACTS": ("they exist and are held in this phase, refused if called: " + ", ".join(held)) if held
                else "none in this session: nothing but a read passes",
        "ORDERS": "reply(text, claims, complete) | no_reply(reason, complete); no_reply: an entry not addressed to "
                  "you, or nothing to say; an act held or refused, or information missing: a reply saying so or "
                  "asking for it",
        "CLAIMS": "one per figure of data in the text, with the id of the evidence it is in; derived: true for a "
                  "figure computed from evidence of this reply, with its op and operands (figures of that evidence), "
                  "said with what it rests on",
        "COMPLETE": "true: the person has finished this thought, whether or not you can answer it yet; false: they "
                    "seem to be mid-thought",
    }
    told = "; ".join(f"{ch}: {v}" for ch, v in sorted((budget or {}).items()))
    lines["LENGTH"] = f"{told}; longer only when asked" if told else "as the answer needs"
    return "\n".join(f"{k}: {lines[k]}" for k in LINES)


def held_acts() -> tuple[str, ...]:
    """Every leaving act of the event vocabulary, by its name (`messaging.send_new`): they exist; in this phase the
    gateway refuses them. The names, not their descriptions: the line stays under the prefix's ceiling."""
    from nucleo.events import vocabulary
    return tuple(vocabulary.names(vocabulary.OUT))


def current(catalog: list[ToolSpec]) -> str:
    """The prefix in the operator's language as it stands (`i18n.langs`), with the names as the engine knows them."""
    from i18n import langs
    from memory import api as memory
    from nucleo.self import snapshot
    spec = langs.current_language()
    person = str((memory.state() or {}).get("operator_name") or "").strip()
    import genome
    budget = (genome.genesis().get("conversation") or {}).get("reply_budget") or {}
    return build(catalog, native=spec.native, name=spec.name, agent=snapshot.name(), person=person, held=held_acts(),
                 budget=budget)
