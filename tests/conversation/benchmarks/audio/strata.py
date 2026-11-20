"""The stratified scenarios of level 3a (plan §5.2): language (es · en · mix) × condition, ~25 s flows, each with
several labelled THOUGHTS (a thought = one user turn, which the agent must answer once and whole).

    clean          each thought said in one breath
    pauses         each thought cut at breath points by a pause from the grid (300 · 700 · 900 · 1500 · 2500 ms …);
                   with `pause_mode: one_utterance` the thought is synthesised in ONE utterance and the pause is
                   inserted at the word boundary (only voices with word times), so the piece before the pause keeps
                   the prosody of a sentence that goes on — piece by piece, each piece ends like a sentence
    interruption   the person starts, someone cuts in for 1–3 s, the person resumes and finishes (U10)
    second         another voice says something unrelated inside or beside the thought (U11)
    tv             continuous speech in the background, 20 · 10 · 5 dB below the person (U12)
    cough          a cough inside a pause of a thought, or alone right after a thought ends (U13)
    long           a monologue: 4–7 pieces cut mid-clause, pauses drawn from the measured human distribution
    words          the agent's name said in the middle of a sentence, and sentences that START with «para» / «for»
                   that are not an order to stop
    echo           our own voice reaching the microphone at 10 · 20 dB below, after each thought, while the engine
                   knows it is playing (the rise it causes is not echo-safe)

Every text is invented; the only names are the contact fixtures (Rowan). A flow is a `compose.py` spec, so the
labels come out of the generator, never from anyone listening.

The numbers (pause grid, TV levels, gaps, gains, flows per cell) come from a parameter FILE — `params.default.json`
beside this module, or the file named by `ZAELAR_AUDIO_PARAMS` / `load_params(path)` — so a profile measured on real
sessions re-weights the strata without touching code. The flow ids do not change with the parameters: compare two
runs only with the parameter file each one names in its report.
"""
from __future__ import annotations

import json
import os
import random
from pathlib import Path

from tests.conversation.benchmarks.audio.voices import TIMED_USER_VOICES, USER_VOICES, timed

DEFAULT_PARAMS = Path(__file__).with_name("params.default.json")
CONDITIONS = ("clean", "pauses", "interruption", "second", "tv", "cough", "long", "words", "echo")
LANGS = ("es", "en", "mix")
PARAMS: dict = {}
PARAMS_PATH = ""


def load_params(path: str | Path | None = None) -> dict:
    """Read the parameter file into `PARAMS` (and the module constants that mirror it)."""
    global PARAMS, PARAMS_PATH, PAUSE_GRID_MS, TV_BELOW_DB, THOUGHTS_PER_FLOW, GAP_BETWEEN_THOUGHTS_MS
    global FLOWS_PAUSE_CELL, FLOWS_OTHER_CELL, INNER_PAUSE_GRID_MS
    p = Path(path or os.environ.get("ZAELAR_AUDIO_PARAMS") or DEFAULT_PARAMS)
    PARAMS, PARAMS_PATH = json.loads(p.read_text(encoding="utf-8")), str(p)
    PAUSE_GRID_MS = tuple(PARAMS["pause_grid_ms"])
    TV_BELOW_DB = tuple(PARAMS["tv_below_db"])
    THOUGHTS_PER_FLOW = int(PARAMS["thoughts_per_flow"])
    GAP_BETWEEN_THOUGHTS_MS = int(PARAMS["gap_between_thoughts_ms"])   # long enough for an answer: a new thought
    FLOWS_PAUSE_CELL, FLOWS_OTHER_CELL = int(PARAMS["flows_pause_cell"]), int(PARAMS["flows_other_cell"])
    INNER_PAUSE_GRID_MS = tuple(PARAMS.get("inner_pause_grid_ms") or PARAMS["pause_grid_ms"])
    return PARAMS


def _pick(rng: random.Random, v):
    return rng.choice(v) if isinstance(v, list) else v


_QS = (("p1", 0.01), ("p10", 0.10), ("p25", 0.25), ("p50", 0.50), ("p75", 0.75), ("p90", 0.90), ("p99", 0.99))


def draw(rng: random.Random, q: dict) -> float:
    """Inverse CDF of a quantile object {p1 … p99}: u ~ U(0,1), linear between neighbouring percentiles, clamped."""
    pts = [(f, float(q[k])) for k, f in _QS if k in q]
    u = min(max(rng.random(), pts[0][0]), pts[-1][0])
    for (f0, v0), (f1, v1) in zip(pts, pts[1:]):
        if u <= f1:
            return v0 + (v1 - v0) * (u - f0) / (f1 - f0)
    return pts[-1][1]


def human_pause(rng: random.Random, lang: str = "es") -> int:
    """A pause inside a thought. With `quantiles` in the parameters (a measured profile), drawn from them by language
    (a low-n language falls back to es); otherwise the log-normal through the median and p90."""
    import math
    q = PARAMS["human_pause"]
    if q.get("quantiles"):
        table = q["quantiles"].get(lang) or q["quantiles"]["es"]
        if table.get("low_n"):
            table = q["quantiles"]["es"]
        return int(min(q.get("max_ms", 30000), draw(rng, table)))
    sigma = math.log(q["p90_ms"] / q["median_ms"]) / 1.2816
    return int(min(q["max_ms"], rng.lognormvariate(math.log(q["median_ms"]), sigma)))

#: Thoughts split at the points where a person breathes. Joined, each is one request.
THOUGHTS = {
    "es": [
        ["¿Qué suele hacer NVIDIA los viernes?", "los últimos treinta, ¿cuántas veces sube?"],
        ["Ponme una alarma mañana", "a las siete y cuarto,", "que tengo médico."],
        ["¿Qué tiempo va a hacer el sábado", "en Valencia?"],
        ["Recuérdame llamar a Rowan", "cuando salga de la oficina."],
        ["¿Cuánto se tarda en tren", "de Madrid a Zaragoza?"],
        ["Busca un restaurante japonés", "cerca de casa,", "que abra los lunes."],
        ["¿Qué tengo en la agenda", "el jueves por la tarde?"],
        ["Apunta en la lista de tareas", "llamar al banco", "y pagar la luz."],
        ["¿A cuánto está el euro", "frente al dólar hoy?"],
        ["Cuéntame las noticias", "más importantes de esta mañana."],
        ["¿Cuántos kilómetros hay", "de Sevilla a Granada?"],
        ["Pon música tranquila", "para trabajar,", "sin letra si puede ser."],
        ["¿A qué hora juega el Betis", "este fin de semana?"],
        ["Quiero reservar mesa para cuatro", "el viernes a las nueve."],
        ["¿Cuál es la capital de Australia", "y cuánta gente vive allí?"],
        ["Mueve la reunión del martes", "al miércoles a la misma hora."],
        ["¿Me dices cuántas calorías tiene", "un plato de lentejas?"],
        ["Avísame cuando falten", "diez minutos para la reunión."],
        ["¿Qué películas echan hoy", "en el cine del centro?"],
        ["Traduce al inglés", "mañana no puedo ir a la cena."],
    ],
    "en": [
        ["What does NVIDIA usually do on Fridays?", "over the last thirty, how many times did it go up?"],
        ["Set an alarm for tomorrow", "at a quarter past seven,", "I have a doctor's appointment."],
        ["What's the weather going to be like on Saturday", "in Boston?"],
        ["Remind me to call Rowan", "when I leave the office."],
        ["How long does the train take", "from New York to Philadelphia?"],
        ["Find me a Japanese restaurant", "close to home,", "that's open on Mondays."],
        ["What do I have on my calendar", "on Thursday afternoon?"],
        ["Add to the shopping list", "milk, eggs", "and ground coffee."],
        ["What's the exchange rate", "between the euro and the dollar today?"],
        ["Tell me the most important news", "from this morning."],
        ["How many miles is it", "from Chicago to Detroit?"],
        ["Play some calm music", "to work to,", "without lyrics if possible."],
        ["What time do the Celtics play", "this weekend?"],
        ["I want to book a table for four", "on Friday at nine."],
        ["What's the capital of Australia", "and how many people live there?"],
        ["Move Tuesday's meeting", "to Wednesday at the same time."],
        ["How many calories are there", "in a bowl of lentil soup?"],
        ["Let me know when there are", "ten minutes left before the meeting."],
        ["What movies are showing today", "at the downtown cinema?"],
        ["Translate into Spanish", "I can't make it to dinner tomorrow."],
    ],
    "mix": [
        ["Búscame un restaurante italiano para esta noche,", "I mean, something close to the office."],
        ["Ponme una alarma a las siete,", "actually make it seven thirty."],
        ["What's the weather in Madrid,", "¿va a llover el domingo?"],
        ["Recuérdame llamar a Rowan,", "after lunch please."],
        ["Can you check my calendar,", "¿tengo algo el jueves?"],
        ["¿Cuánto cuesta un billete a Londres", "for next Friday?"],
        ["Add bread to the shopping list,", "y también tomates."],
        ["¿A qué hora cierra el supermercado,", "the one near the station?"],
        ["Play some jazz,", "pero bajito, que estoy trabajando."],
        ["¿Qué tal ha cerrado la bolsa hoy,", "especially the tech stocks?"],
        ["Move my dentist appointment,", "al viernes por la mañana."],
        ["¿Cómo se dice despertador", "in English?"],
    ],
}

#: Monologues: 4–7 pieces cut where half the real Spanish finals end — mid-clause, at a comma or a function word.
LONG = {
    "es": [
        ["Mira, lo que quiero es que", "me busques un hotel en Lisboa para", "el puente de diciembre, pero que", "no esté lejos del centro y", "que tenga desayuno incluido."],
        ["A ver, la semana que viene tengo", "lo del dentista el martes y", "el jueves la reunión de equipo, entonces", "¿qué día me queda libre por", "la tarde para ir al gimnasio?"],
        ["Oye, el otro día estuve mirando", "lo de cambiar de compañía de luz porque", "la factura me ha subido bastante, y", "quería saber qué tarifas hay ahora", "con discriminación horaria, que", "son las que salen más baratas."],
        ["Quiero preparar una cena para", "seis personas el sábado, y como", "dos son vegetarianos, dime", "un menú sencillo que", "se pueda hacer la mañana antes."],
        ["Lo de las acciones de NVIDIA, que", "te pregunté ayer, ¿al final", "cómo cerraron el viernes y", "cuántas veces han subido en", "los últimos treinta viernes?"],
        ["Necesito saber si", "para ir al aeropuerto de Barajas", "desde Atocha es mejor", "el tren de cercanías o", "el autobús exprés, sobre todo", "a las seis de la mañana."],
    ],
    "en": [
        ["So what I want is for", "you to find me a hotel in Lisbon for", "the long weekend in December, but", "not too far from the center and", "with breakfast included."],
        ["Let me see, next week I've got", "the dentist on Tuesday and", "the team meeting on Thursday, so", "which day do I have free in", "the afternoon to go to the gym?"],
        ["Hey, the other day I was looking at", "switching electricity providers because", "the bill has gone up quite a bit, and", "I wanted to know what plans there are", "with time-of-use pricing, since", "those are usually the cheapest."],
        ["I want to cook dinner for", "six people on Saturday, and since", "two of them are vegetarian, give me", "a simple menu that", "I can prepare the morning before."],
        ["About the NVIDIA shares that", "I asked you about yesterday, how", "did they close on Friday and", "how many times have they gone up over", "the last thirty Fridays?"],
        ["I need to know whether", "to get to JFK from", "Midtown it's better to take", "the subway and the AirTrain or", "a cab, especially at", "six in the morning."],
    ],
    "mix": [
        ["Mira, I was thinking that", "para el viaje a Londres podríamos", "stay somewhere near the river, y", "que no sea muy caro, like", "under two hundred a night."],
        ["Lo que necesito es que", "you check my calendar for", "la semana que viene and", "tell me qué tardes tengo libres."],
        ["So the thing is that", "mañana tengo una reunión con Rowan y", "I need the address of", "the office where we're meeting, que", "creo que está en Castellana."],
        ["Oye, ¿sabes si", "the Champions League match", "es mañana o pasado, y", "at what time it starts?"],
    ],
}
#: The agent's name said in the middle of a sentence, and sentences that START with «para» (or «for») without being
#: an order to stop: the profile found the vocative misheard, and «para + complement» in 70 % of the «para…» starts.
WORDS = {
    "es": [
        ["Johnny, ¿qué tiempo", "va a hacer mañana en Sevilla?"], ["Oye Johnny, ponme", "una alarma a las siete."],
        ["¿Cuánto tarda el tren", "a Valencia, Johnny?"], ["Para mañana, ¿qué tengo", "en la agenda?"],
        ["Para la cena de esta noche,", "busca un italiano cerca."], ["Para ir al aeropuerto,", "¿cuánto se tarda en taxi?"],
        ["Para el jueves, ¿va a llover", "en Madrid?"], ["Johnny, ¿a cuánto", "está el euro hoy?"],
        ["Para cuatro personas, ¿cuánto", "arroz hace falta para una paella?"],
        ["Mira Johnny, dime cuántos", "habitantes tiene Japón."],
    ],
    "en": [
        ["Johnny, what's the weather", "going to be tomorrow in Boston?"], ["Hey Johnny, set", "an alarm for seven."],
        ["How long is the train", "to Philadelphia, Johnny?"], ["For tomorrow, what do I have", "on my calendar?"],
        ["For dinner tonight,", "find an Italian place nearby."], ["For the airport,", "how long does a cab take?"],
        ["For Thursday, is it going to rain", "in New York?"], ["Johnny, what's the euro", "worth in dollars today?"],
        ["For four people, how much", "rice do I need for a paella?"], ["Look Johnny, tell me how many",
                                                                          "people live in Japan."],
    ],
    "mix": [
        ["Johnny, ¿qué tiempo", "will it be tomorrow in London?"], ["Para mañana, what do I have", "on my calendar?"],
        ["Hey Johnny, ponme", "una alarma at seven."], ["For the dinner tonight,", "busca un sitio italiano."],
        ["Para el jueves, is it going to rain", "en Madrid?"], ["Johnny, how much", "está el euro hoy?"],
    ],
}
#: What our own voice says when it reaches the microphone: an answer, in the agent's voice.
ECHO = {
    "es": ["Mañana en Sevilla hará sol, con máximas de veinticuatro grados.", "Hecho, te he puesto la alarma a las siete.",
           "El tren a Valencia tarda unas dos horas.", "El euro está hoy a uno con ocho dólares.",
           "Tienes la reunión de equipo a las diez y el dentista a las cuatro."],
    "en": ["Tomorrow in Boston it'll be sunny, with a high of seventy-five.", "Done, your alarm is set for seven.",
           "The train to Philadelphia takes about an hour and a half.", "The euro is at one point eight dollars today.",
           "You have the team meeting at ten and the dentist at four."],
}


#: What «the other person» says, in two kinds (plan §5.2): a NARRATION (someone telling something) and a QUESTION
#: aimed at the person. The second exists to say with numbers what the design does not promise.
OTHER = {
    "es": {"narration": ["Hoy en el trabajo ha venido el técnico a arreglar la impresora.",
                         "Mañana viene tu madre a comer, ya se lo he dicho.", "Voy a sacar al perro un momento.",
                         "Se ha vuelto a ir la luz en el portal."],
           "question": ["¿Has visto mis llaves?", "¿Has dado de comer al gato?", "¿Quién se ha dejado la luz encendida?",
                        "¿Me pasas el cargador?"]},
    "en": {"narration": ["The technician came by work today to fix the printer.",
                         "Your mom is coming for lunch tomorrow, I told her already.",
                         "I'm taking the dog out for a minute.", "The power went out in the hallway again."],
           "question": ["Have you seen my keys?", "Did you feed the cat?", "Who left the light on?",
                        "Can you pass me the charger?"]},
}
#: What the TV says in the background: narration, or a host asking the audience a question.
TV = {
    "es": {"narration": ["Y ahora, el tiempo para mañana en toda la península.",
                         "Fuertes lluvias en el norte y viento en la costa.",
                         "En deportes, el equipo local ha ganado su tercer partido seguido.",
                         "La bolsa cerró la sesión con ligeras subidas."],
           "question": ["¿Y usted, sabe cuál es el río más largo de Europa?", "¿Cuántos goles cree que marcará el equipo?",
                        "¿Ha probado ya nuestra receta de hoy?", "¿Qué haría usted con un millón de euros?"]},
    "en": {"narration": ["And now, the weather for tomorrow across the country.",
                         "Heavy rain in the north and strong winds on the coast.",
                         "In sports tonight, the home team won its third game in a row.",
                         "The markets closed the session slightly higher."],
           "question": ["And you, do you know the longest river in Europe?", "How many goals do you think they'll score?",
                        "Have you tried today's recipe yet?", "What would you do with a million dollars?"]},
}


def _other_lang(lang: str, rng: random.Random) -> str:
    return lang if lang != "mix" else rng.choice(("es", "en"))


def _stranger(items: list, lang: str, rng: random.Random, kind: str, *, gap_ms: int, gain_db: float) -> None:
    ol = _other_lang(lang, rng)
    items.append({"say": f"{ol}_other", "text": rng.choice(OTHER[ol][kind]), "role": "other", "stranger": kind,
                  "gap_ms": gap_ms, "gain_db": gain_db})


def flow(lang: str, condition: str, k: int, pause_ms: int | None = None) -> dict:
    """The k-th flow of a cell: deterministic in (lang, condition, pause, k). In the pauses condition EVERY pause of
    the flow has the same length, so each thought is one event of that length's cell."""
    tag = f"{condition}{pause_ms}" if condition == "pauses" else condition
    rng = random.Random(f"{lang}:{tag}:{k}")
    # the agent speaks with the first voice of each language: with its echo in the room, the person is another voice
    voice = USER_VOICES[lang][1 + k % 2] if condition == "echo" else USER_VOICES[lang][k % 3]
    bank = {"long": LONG, "words": WORDS}.get(condition, THOUGHTS)[lang]
    picks = rng.sample(range(len(bank)), THOUGHTS_PER_FLOW)
    stranger_kind = ("narration", "question")[k % 2]
    items: list[dict] = []
    tv_below = None
    if condition == "tv":
        tv_below = TV_BELOW_DB[k % len(TV_BELOW_DB)]
        ol = _other_lang(lang, rng)
        items.append({"tv": f"{ol}_tv", "texts": rng.sample(TV[ol][stranger_kind], len(TV[ol][stranger_kind])),
                      "at_ms": 0, "gain_db": -tv_below, "stranger": stranger_kind})
    one_utterance = condition == "pauses" and PARAMS.get("pause_mode") == "one_utterance"
    if one_utterance:                     # plan §5.2: the thought said in ONE breath, the pause inserted at a word
        pool = TIMED_USER_VOICES[lang]
        voice = pool[k % len(pool)]
    for n, idx in enumerate(picks, start=1):
        chunks = bank[idx]
        gap = 0 if n == 1 else GAP_BETWEEN_THOUGHTS_MS
        if one_utterance:
            items.append({"split": timed(voice), "pieces": chunks, "pauses": [pause_ms] * (len(chunks) - 1),
                          "role": "user", "turn": n, "gap_ms": gap})
            continue
        whole = condition in ("clean", "tv") or (condition == "second" and n % 2 == 0)
        if whole:
            items.append({"say": voice, "text": " ".join(chunks), "role": "user", "turn": n, "gap_ms": gap})
        else:
            for c, chunk in enumerate(chunks):
                if c == 0:
                    pause = gap
                elif condition == "pauses":
                    pause = pause_ms
                elif condition in ("long", "words", "echo"):
                    pause = human_pause(rng, lang)
                else:
                    pause = INNER_PAUSE_GRID_MS[(k * 7 + n * 3 + c) % len(INNER_PAUSE_GRID_MS)]
                if c == 1 and condition == "interruption":            # someone cuts in for 1–3 s; the person resumes
                    q = PARAMS["interruption"]
                    _stranger(items, lang, rng, stranger_kind, gap_ms=_pick(rng, q["stranger_gap_ms"]),
                              gain_db=_pick(rng, q["stranger_gain_db"]))
                    pause = _pick(rng, q["resume_ms"])
                if c == 1 and condition == "second":                  # another voice inside the thought
                    q = PARAMS["second"]
                    _stranger(items, lang, rng, stranger_kind, gap_ms=_pick(rng, q["inside_gap_ms"]),
                              gain_db=_pick(rng, q["inside_gain_db"]))
                    pause = _pick(rng, q["resume_ms"])
                if c == 1 and condition == "cough":                   # a cough inside the pause
                    items.append({"cough": 1, "gap_ms": PARAMS["cough"]["gap_ms"]})
                    pause = PARAMS["cough"]["resume_ms"]
                items.append({"say": voice, "text": chunk, "role": "user", "turn": n, "gap_ms": pause,
                              "continues": c > 0})
        if condition == "cough" and n % 2 == 0:                       # a cough alone, during the agent's run
            items.append({"cough": 1, "gap_ms": _pick(rng, PARAMS["cough"]["alone_gap_ms"])})
        if condition == "echo":                                       # our answer, heard back by the microphone
            q = PARAMS["echo"]
            items.append({"say": f"{lang if lang != 'mix' else rng.choice(('es', 'en'))}_agent",
                          "text": rng.choice(ECHO[lang if lang != "mix" else "es"]), "role": "echo",
                          "stranger": "echo", "gap_ms": _pick(rng, q["after_ms"]), "gain_db": -_pick(rng, q["below_db"])})
        if condition == "second" and n % 2 == 0:                      # another voice right after the thought
            _stranger(items, lang, rng, stranger_kind, gap_ms=_pick(rng, PARAMS["second"]["after_gap_ms"]),
                      gain_db=_pick(rng, PARAMS["second"]["after_gain_db"]))
    cell = f"{lang}×{condition}" + (f"-{pause_ms}" if condition == "pauses" else "")
    tagged = PARAMS.get("id_tag_all") or condition in ("long", "words", "echo")
    suffix = f"-{PARAMS['id_tag']}" if PARAMS.get("id_tag") and tagged else ""
    return {"id": f"st-{lang}-{tag}-{k:02d}{suffix}", "lang": lang, "noise_db": PARAMS["noise_db"], "stratum": cell,
            "description": f"cell {cell}, flow {k}" + (f", TV {tv_below} dB below" if tv_below else "")
                           + (f", stranger {stranger_kind}" if condition in ("second", "interruption", "tv") else ""),
            "items": items}


#: Every profile-A cell must hold ≥ 52 thoughts: the least n at which 0 failures can pass a Wilson 95 % upper bound
#: ≤ 7 % (decided 2026-11-20; plan §5.2 asked ≥ 30). The default file gives 13 flows × 4 thoughts.
load_params()


def strata(scale: float = 1.0, langs=LANGS, conditions=CONDITIONS, pauses=None) -> list[dict]:
    pauses = PAUSE_GRID_MS if pauses is None else pauses
    out = []
    for lang in langs:
        for cond in conditions:
            if cond == "pauses":
                for p in pauses:
                    out += [flow(lang, cond, k, p) for k in range(max(1, round(FLOWS_PAUSE_CELL * scale)))]
            else:
                out += [flow(lang, cond, k) for k in range(max(1, round(FLOWS_OTHER_CELL * scale)))]
    return out
