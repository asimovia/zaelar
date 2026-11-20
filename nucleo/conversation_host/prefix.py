"""The model's stable prefix for the conversation manager (V2-941, the F1 plan §4.7): who is who, the language, how it
speaks (the language pack's `speech_style`: DNA, never a sentence here), what it may read (an act it carries out is a
tool of its own, never listed as a read), what exists but is held, and the fields of its two orders — declared, never
a script of how to behave (principles: «declare capabilities, never script behaviour»). Byte-identical between turns for the same names,
language and catalogue, so the provider caches it; every line is one of `LINES`, and the whole stays under
`MAX_TOKENS`.
"""
from __future__ import annotations

from nucleo.conversation_host.declared import declared

from conversation.ports import ToolSpec

#: measured with names of 23 letters, never the short ones (the stop review's P-2). 600 → 650 on 2026-11-20: the four
#: stops are named among the orders (P-1: the model must see them as orders, not a silence), paid in part by their
#: descriptions in the tool list, cut from ~530 characters to under 300. 650 → 750 on 2026-11-20: the STYLE line (the
#: language pack's `speech_style`, ~60 tokens: the manager read back phone numbers and a message's text like a robot)
#: and the narrower stop rule (E-2: «te paso la tarea dos» chose `stop_voice`); measured 732 in Spanish with both
#: reply budgets, the held acts having grown to 20 names. 750 → 800 on 2026-11-20 (F2 step 1): the `read_state` read and
#: `read_widget`'s actions — what each run no longer carries in its state (the connectors, what was done, the browser,
#: every open widget beside the one in front) is read when named; measured 784 with names of 23 letters
MAX_TOKENS = 800

#: the only lines a prefix carries, in this order
LINES = tuple(declared()["prefix_lines"])                     # declared data (`declared.json`), in their order


def build(catalog: list[ToolSpec], *, native: str, name: str, agent: str = "", person: str = "",
          held: tuple[str, ...] = (), budget: dict | None = None, style: str = "") -> str:
    """`agent`: the assistant's own name; `person`: the person's, when known; `held`: the acts that exist but are held in
    this phase (the event vocabulary's names); `style`: how the agent speaks, the language pack's `speech_style` (DNA,
    never a sentence of this file)."""
    from conversation.types import EffectClass
    reads = "; ".join(f"{t.name}: {t.about}" if t.about else t.name
                      for t in sorted(catalog, key=lambda t: t.name) if t.effect_class is EffectClass.READ)
    lines = {
        "YOU": f"the assistant{f', named {agent}' if agent else ''} — the name others call you, never the person's; "
               f"speak in the first person",
        "PERSON": f"named {person}" if person else "name not known yet",
        "LANGUAGE": f"each reply in the language of the person's entries it answers; when that is not clear, {native} "
                    f"({name})",
        "STYLE": style or "none declared",
        "INPUT": "the entries to answer now, each on its own whatever CONVERSATION holds, with its id, channel and "
                 "time; an entry cut off says so; CONVERSATION is what was said before, ours cut to what was heard, an "
                 "earlier session marked with its age; STATE is now and what is open, its notes maybe in another "
                 "language than the conversation's",
        "READS": reads or "none",
        "ACTS": ("held now, refused: never done, promised or said as done — the reply says so: "
                 + ", ".join(held)) if held
                else "none held in this session",
        "ORDERS": "reply(text, claims, complete) | no_reply(reason, complete) | stop_voice | stop_media | stop_run | "
                  f"stop_all; {declared()['stop_rule']}; no_reply: an entry not addressed to you, or nothing to say; "
                  "an act held or refused, or information missing: a reply "
                  "saying so or asking for it",
        "CLAIMS": "one per figure in the text, with its evidence id (a read or his entry); derived: true for a "
                  "figure computed from evidence, citing every id its operands are in, op and operands, "
                  "said with its basis",
        "COMPLETE": "true: the person has finished this thought, whether or not you can answer it yet; false: they "
                    "seem to be mid-thought",
    }
    told = "; ".join(f"{ch}: {v}" for ch, v in sorted((budget or {}).items()))
    lines["LENGTH"] = f"{told}; longer only when asked" if told else "as the answer needs"
    return "\n".join(f"{k}: {lines[k]}" for k in LINES)


def held_acts(catalog: list[ToolSpec] = ()) -> tuple[str, ...]:
    """Every leaving act of the event vocabulary, by its name (`messaging.send_new`), but the ones the catalogue
    carries as a local act: they exist, and the gateway refuses them. The names, not their descriptions: the line
    stays under the prefix's ceiling."""
    from conversation.types import EffectClass
    from nucleo.events import vocabulary
    opened = {t.act for t in catalog if t.effect_class is EffectClass.WRITE}
    return tuple(n for n in vocabulary.names(vocabulary.OUT) if n not in opened)


def current(catalog: list[ToolSpec]) -> str:
    """The prefix in the operator's language as it stands (`i18n.langs`), with the names as the engine knows them."""
    from i18n import langs
    from memory import api as memory
    from nucleo.self import snapshot
    spec = langs.current_language()
    person = str((memory.state() or {}).get("operator_name") or "").strip()
    import genome
    budget = (genome.genesis().get("conversation") or {}).get("reply_budget") or {}
    return build(catalog, native=spec.native, name=spec.name, agent=snapshot.name(), person=person, held=held_acts(catalog),
                 budget=budget, style=str(langs.words("speech_style", spec.code) or ""))
