"""The labelled set for the `complete` gate (v3.1 §1.6 quater), built for it and frozen — not cut from the corpus.

    ./.venv/bin/python -m tests.conversation.tools.complete_set build      # writes the next fixtures/complete/vN: never
                                                                          # an edit of a frozen one
    ./.venv/bin/python -m tests.conversation.tools.complete_set bench [complete_bench's flags]

Why its own set: the corpus was written for conversations, not for this reading. It holds 3 ES and 7 EN cuts after a
sentence mark, and two of those are whole questions followed by more (a label the bench would score against a right
reading). Here every item is built from the analyst's templates (`‖` = where the speech-to-text closes a final) and
its label comes from the TEMPLATE, by a rule written before measuring:

  INCOMPLETE  the text up to a `‖` where the person goes on, and the text itself says so: a lead-in that announces
              something («Oye, una cosa.»), the name alone, a clause left open on a function word, a subordinate clause
              with no main one («Si mañana llueve.»), a list announced and not given, a correction opened and not
              given («…, o sea, no.»), an «y además» with nothing after it. Every one ends with a sentence mark, as the
              provider marks 80 % of the pieces after which the person goes on (report 06) — the case the gate is for.
  COMPLETE    a whole thought that needs an answer, in the templates' shapes: bare, after a starter, after the name,
              after a context clause, a correction resolved, two errands, the thought in pieces joined.

Excluded on purpose, because the text alone cannot say: an order missing an argument (a message with no text — the
person may stop there and be asked), a statement with no request, a whole question the person then elaborates.

Invented content; the contacts are the fixtures' placeholders (Rowan, Inworld); real companies and cities so a
question has an answer.
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "complete"
SEED = 7
N = {"incomplete": 40, "complete": 110}

# (whole request, the request cut on a function word — what a final looks like when it closes mid-clause)
REQ = {
    "es": [
        ("¿Qué tiempo va a hacer el sábado en Bilbao?", "¿Qué tiempo va a hacer el sábado en"),
        ("¿A cuánto está hoy la acción de Inditex?", "¿A cuánto está hoy la acción de"),
        ("Pon una alarma mañana a las siete.", "Pon una alarma mañana a"),
        ("¿Qué tengo en la agenda el jueves por la tarde?", "¿Qué tengo en la agenda el"),
        ("Búscame un restaurante italiano cerca de la oficina para esta noche.", "Búscame un restaurante italiano cerca de"),
        ("¿Cuántos kilómetros hay de Madrid a Valencia?", "¿Cuántos kilómetros hay de Madrid a"),
        ("Apúntame una cita con el dentista el martes a las cinco.", "Apúntame una cita con el dentista el"),
        ("¿Cuánto son doscientos dólares en euros?", "¿Cuánto son doscientos dólares en"),
        ("Recuérdame llamar a Rowan cuando salga de trabajar.", "Recuérdame llamar a Rowan cuando"),
        ("¿A qué hora cierra hoy el Museo del Prado?", "¿A qué hora cierra hoy el"),
        ("¿Va a llover esta tarde en Sevilla?", "¿Va a llover esta tarde en"),
        ("¿Quién ganó anoche el partido del Betis?", "¿Quién ganó anoche el partido del"),
        ("Dime cómo está el tráfico para ir al aeropuerto.", "Dime cómo está el tráfico para ir al"),
        ("¿Cuál es la capital de Australia?", "¿Cuál es la capital de"),
        ("Mueve la reunión del viernes al lunes a las diez.", "Mueve la reunión del viernes al"),
        ("¿Cómo ha cerrado hoy el Ibex?", "¿Cómo ha cerrado hoy el"),
        ("Busca vuelos a Lisboa para el puente de diciembre.", "Busca vuelos a Lisboa para el"),
        ("¿Qué puedes hacer tú con mi correo?", "¿Qué puedes hacer tú con"),
        ("¿Cuántos días faltan para Navidad?", "¿Cuántos días faltan para"),
        ("Borra la cita del jueves con el fontanero.", "Borra la cita del jueves con"),
        ("¿Qué temperatura hace ahora mismo en Madrid?", "¿Qué temperatura hace ahora mismo en"),
        ("Dime una receta fácil de lentejas.", "Dime una receta fácil de"),
        ("¿A qué hora sale mañana el sol en Barcelona?", "¿A qué hora sale mañana el sol en"),
        ("Pon un temporizador de veinte minutos para la pasta.", "Pon un temporizador de veinte minutos para"),
        ("¿Cuánto cuesta un billete de AVE a Málaga?", "¿Cuánto cuesta un billete de AVE a"),
        ("¿Tengo algo el fin de semana?", "¿Tengo algo el"),
        ("Explícame qué es la inflación en dos frases.", "Explícame qué es la inflación en"),
        ("¿Cómo va el Brent esta semana?", "¿Cómo va el Brent esta"),
        ("Apunta que hay que comprar leche y huevos.", "Apunta que hay que comprar leche y"),
        ("¿Qué farmacia de guardia hay cerca de casa?", "¿Qué farmacia de guardia hay cerca de"),
    ],
    "en": [
        ("What's the weather going to be like in Chicago on Saturday?", "What's the weather going to be like in"),
        ("How is Apple stock doing compared to last week?", "How is Apple stock doing compared to"),
        ("Set an alarm for seven tomorrow morning.", "Set an alarm for"),
        ("What's on my calendar for Thursday afternoon?", "What's on my calendar for"),
        ("Find me a Thai place near the office for tonight.", "Find me a Thai place near the"),
        ("How far is it from Boston to New York?", "How far is it from Boston to"),
        ("Book a dentist appointment for Tuesday at five.", "Book a dentist appointment for"),
        ("How much is two hundred euros in dollars?", "How much is two hundred euros in"),
        ("Remind me to call Rowan when I leave work.", "Remind me to call Rowan when"),
        ("What time does the museum close today?", "What time does the"),
        ("Is it going to rain this afternoon in Seattle?", "Is it going to rain this afternoon in"),
        ("Who won the Lakers game last night?", "Who won the Lakers game last"),
        ("How's the traffic to the airport right now?", "How's the traffic to the"),
        ("What's the capital of Canada?", "What's the capital of"),
        ("Move Friday's meeting to Monday at ten.", "Move Friday's meeting to"),
        ("How did the S&P 500 close today?", "How did the"),
        ("Look up flights to Denver for Thanksgiving weekend.", "Look up flights to Denver for"),
        ("What can you do with my email?", "What can you do with"),
        ("How many days until Christmas?", "How many days until"),
        ("Delete the plumber appointment on Thursday.", "Delete the plumber appointment on"),
        ("What's the temperature in Miami right now?", "What's the temperature in"),
        ("Give me an easy recipe for chili.", "Give me an easy recipe for"),
        ("What time is sunrise tomorrow in Phoenix?", "What time is sunrise tomorrow in"),
        ("Set a twenty minute timer for the pasta.", "Set a twenty minute timer for the"),
        ("How much is a train ticket from Boston to Washington?", "How much is a train ticket from Boston to"),
        ("Do I have anything this weekend?", "Do I have anything this"),
        ("Explain what inflation is in two sentences.", "Explain what inflation is in"),
        ("How is oil doing this week?", "How is oil doing this"),
        ("Add milk and eggs to the shopping list.", "Add milk and eggs to the"),
        ("Which pharmacy near me is open late tonight?", "Which pharmacy near"),
    ],
}

# a correction resolved: (with the first value, the correction)
FIX = {
    "es": [("Pon una alarma a las siete", "a las seis y media"), ("Mira el tiempo en Bilbao", "en San Sebastián"),
           ("Apunta la cita el martes", "el miércoles"), ("Búscame vuelos a Roma", "a Milán"),
           ("Mueve la reunión a las diez", "a las once")],
    "en": [("Set an alarm for seven", "for six thirty"), ("Check the weather in Boston", "in Providence"),
           ("Put the appointment on Tuesday", "on Wednesday"), ("Find flights to Rome", "to Milan"),
           ("Move the meeting to ten", "to eleven")],
}
CLAUSE = {
    "es": ["Mañana tengo un día complicado", "Esta semana voy fatal", "Estoy pensando en el viaje",
           "Ya he salido de la oficina", "Que luego se me olvida"],
    "en": ["Tomorrow is a busy day", "This week is a mess", "I'm thinking about the trip",
           "I just left the office", "Before I forget"],
}
MRK = {"es": ["A ver", "Vale", "Pues", "Mira", "Bueno", "Venga"], "en": ["So", "Okay", "Well", "Right", "Now"]}
#: the agent's name is the ENGINE's, not the set's: `{AGENT}` is its name, `{AGENT~}` a spelling a recogniser writes
#: for it (template 2: the name misheard in about a third of the cases). `load` fills both from `genome.persona`.
AGENT = {"es": ["{AGENT}", "{AGENT~}", "{AGENT}"], "en": ["{AGENT}", "{AGENT~}", "{AGENT}"]}

# the incomplete shapes: (template id, prefix the final closes on, what follows in the template)
LEAD = {
    "es": ["Oye, una cosa.", "Te quería preguntar algo.", "A ver, escucha.", "Mira, lo de mañana.", "Vamos a ver.",
           "Una pregunta rápida.", "Vale, otra cosa."],
    "en": ["Hey, one thing.", "I wanted to ask you something.", "Okay, listen.", "So, about tomorrow.", "Let's see.",
           "Quick question.", "Okay, another thing."],
}
SUBORD = {
    "es": ["Si mañana llueve.", "Cuando salga de la reunión.", "Antes de que se me olvide.", "Como el viernes voy a Bilbao.",
           "Para lo del cumpleaños de Rowan.", "En cuanto llegue a casa."],
    "en": ["If it rains tomorrow.", "When I get out of the meeting.", "Since I'm flying to Denver on Friday.",
           "For Rowan's birthday thing.", "As soon as I get home.", "Before the call with Inworld."],
}
LIST = {
    "es": ["Necesito tres cosas.", "Te digo dos cosas.", "Apunta en la lista de tareas.", "Quiero que hagas varias cosas."],
    "en": ["I need three things.", "Two things.", "Add to my to-do list.", "I need you to do a few things."],
}
OPEN_FIX = {"es": "o sea, no.", "en": "I mean, no."}
AND_ALSO = {"es": ["Y además.", "Y otra cosa.", "Pero antes."], "en": ["And also.", "And another thing.", "But first."]}


def _low(s: str) -> str:
    """A request said after something else: its first letter lower, «¿» kept."""
    return ("¿" + s[1:2].lower() + s[2:]) if s.startswith("¿") else s[:1].lower() + s[1:]


def _incomplete(lang: str, rng: random.Random) -> list[dict]:
    reqs, out = REQ[lang], []
    for i, (full, cut) in enumerate(reqs):          # a clause open on a function word, marked as a final
        out.append({"shape": "open_function_word", "text": cut + ".", "goes_on": full[len(cut):].strip()})
    for lead in LEAD[lang]:
        full = rng.choice(reqs)[0]
        out.append({"shape": "lead_in", "text": lead, "goes_on": full})
    for a in sorted(set(AGENT[lang])):
        out.append({"shape": "name_alone", "text": a + ".", "goes_on": rng.choice(reqs)[0]})
    for s in SUBORD[lang]:
        out.append({"shape": "subordinate_alone", "text": s, "goes_on": rng.choice(reqs)[0]})
    for s in LIST[lang]:
        out.append({"shape": "list_announced", "text": s, "goes_on": rng.choice(reqs)[0]})
    for first, _fix in FIX[lang]:
        out.append({"shape": "correction_opened", "text": f"{first}, {OPEN_FIX[lang]}", "goes_on": _fix})
    for s in AND_ALSO[lang]:
        full = rng.choice(reqs)[0]
        out.append({"shape": "and_also_empty", "text": f"{full} {s}", "goes_on": rng.choice(reqs)[0]})
    return out


def _complete(lang: str, rng: random.Random) -> list[dict]:
    reqs, out = REQ[lang], []
    for full, _cut in reqs:
        out.append({"shape": "bare", "text": full})
        out.append({"shape": "after_starter", "text": f"{rng.choice(MRK[lang])}, {_low(full)}"})
        out.append({"shape": "after_name", "text": f"{rng.choice(AGENT[lang])}, {_low(full)}"})
    for full, _cut in rng.sample(reqs, 12):
        out.append({"shape": "after_context", "text": f"{rng.choice(CLAUSE[lang])}. {full}"})
    for first, fix in FIX[lang]:
        out.append({"shape": "correction_resolved", "text": f"{first}, {OPEN_FIX[lang][:-1]}, {fix}."})
    for _ in range(10):
        a, b = rng.sample(reqs, 2)
        joiner = " Y además, " if lang == "es" else " And also, "
        out.append({"shape": "two_errands", "text": a[0] + joiner + _low(b[0])})
    for full, cut in rng.sample(reqs, 10):           # the thought typed in pieces, joined: the whole is complete
        lead = rng.choice(LEAD[lang])
        out.append({"shape": "pieces_joined", "text": f"{lead} {cut} {full[len(cut):].strip()}"})
    return out


def build(version: str | None = None) -> Path:
    rng = random.Random(SEED)
    root = ROOT
    v = version or next(f"v{i}" for i in range(1, 100) if not (root / f"v{i}").exists())
    out = root / v
    out.mkdir(parents=True)
    files = {}
    for lang in ("es", "en"):
        inc, comp = _incomplete(lang, rng), _complete(lang, rng)
        rng.shuffle(inc)
        rng.shuffle(comp)
        # every shape that announces more is kept; the clause open on a function word fills the rest
        rest = [x for x in inc if x["shape"] != "open_function_word"]
        inc = rest + [x for x in inc if x["shape"] == "open_function_word"][: N["incomplete"] - len(rest)]
        comp = comp[: N["complete"]]
        assert len(inc) >= 30 and len(comp) >= 100, (lang, len(inc), len(comp))
        items = ([{"id": f"{lang}-i{k:03d}", "label": "incomplete", "cut": "marked", **x} for k, x in enumerate(inc)]
                 + [{"id": f"{lang}-c{k:03d}", "label": "complete", **x} for k, x in enumerate(comp)])
        assert all(x["text"].rstrip().endswith((".", "?", "!", "…")) for x in items if x["label"] == "incomplete")
        assert len({x["text"] for x in items}) == len(items), f"{lang}: a duplicate text"
        name = f"complete.{lang}.json"
        data = (json.dumps(items, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
        (out / name).write_bytes(data)
        files[name] = {"sha256": hashlib.sha256(data).hexdigest(), "incomplete": len(inc), "complete": len(comp),
                       "shapes": sorted({x["shape"] for x in items})}
    manifest = {"version": v, "generator": "tests/conversation/tools/complete_set.py", "seed": SEED,
                "source": "the analyst's templates (‖ = a speech-to-text final), filled by hand; no model wrote them",
                "label_rule": __doc__.split("by a rule written before measuring:")[1].split("Invented content")[0].strip(),
                "files": files,
                "debatable": {"correction_opened": "«…, o sea, no.» / «…, I mean, no.» is labelled incomplete (the "
                              "correction is pending) but also reads as «never mind»; on deepseek-flash the model read it "
                              "complete 10/10 (v1, 2026-11-20). Reported apart; the gate is read with and without it."}}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return out


def fill(items: list[dict], name: str, heard: tuple[str, ...] | list[str]) -> list[dict]:
    """`{AGENT}` → the agent's name, `{AGENT~}` → one of the spellings a recogniser writes for it (not the name itself),
    the same one for the same item every time."""
    other = [h for h in heard if h.lower() != name.lower()] or [name]
    out = []
    for x in items:
        miss = other[int(hashlib.sha1(x["id"].encode()).hexdigest(), 16) % len(other)]
        miss = miss[:1].upper() + miss[1:]
        out.append({**x, **{k: x[k].replace("{AGENT~}", miss).replace("{AGENT}", name)
                            for k in ("text", "goes_on") if isinstance(x.get(k), str)}})
    return out


def load(lang: str, version: str = "v3", *, name: str | None = None) -> list[dict]:
    """The frozen items, checked against the manifest; with placeholders (v3 on) filled with the engine's own name —
    `name` overrides it, as a renamed agent would."""
    root = ROOT / version
    man = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    data = (root / f"complete.{lang}.json").read_bytes()
    assert hashlib.sha256(data).hexdigest() == man["files"][f"complete.{lang}.json"]["sha256"], "the set changed"
    items = json.loads(data)
    if not any("{AGENT" in x["text"] for x in items):
        return items
    from genome import persona
    who = name or persona.default_name(lang)
    return fill(items, who, persona.heard_as(who))


def majority(values: list) -> bool | None:
    """One reading of an item from several samples: the value most of them gave; a tie, or no bool, is None."""
    bools = [v for v in values if isinstance(v, bool)]
    t, f = bools.count(True), bools.count(False)
    return True if t > f and t > len(values) / 2 else False if f > t and f > len(values) / 2 else None


def bench(argv: list[str], samples: int = 3) -> int:
    """`complete_bench` on this set, each item read `samples` times and decided by `majority` (a failed provider call
    stays a failure: it is INFRA, never a vote)."""
    from tests.conversation.benchmarks import complete_bench as CB
    CB.items = lambda lang, n_inc, n_comp, seed=1, version=None: (
        [x for x in load(lang) if x["label"] == "incomplete"][:n_inc]
        + [x for x in load(lang) if x["label"] == "complete"][:n_comp])
    once = CB.read

    async def read(model, text, lang):
        got = [await once(model, text, lang) for _ in range(samples)]
        failed = [g for g in got if isinstance(g, str)]
        if len(failed) > samples // 2:
            return failed[0]
        return majority([g for g in got if not isinstance(g, str)])
    CB.read = read
    return CB.main(argv)


if __name__ == "__main__":
    cmd, rest = (sys.argv[1] if len(sys.argv) > 1 else "build"), sys.argv[2:]
    if cmd == "build":
        print(build(rest[0] if rest else None))
    elif cmd == "bench":
        raise SystemExit(bench(rest))
