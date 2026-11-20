"""The catalog of audio scenarios. Invented text, synthetic voices, the contact fixtures (Rowan); no real person.

Each scenario names what it stresses. A pause INSIDE a turn is a gap between two `user` items with the same `turn`;
a new turn is a new `turn` number after a gap long enough for an agent to answer (≥ 3 s).
"""
from __future__ import annotations

SCENARIOS: list[dict] = [
    {
        "id": "es-nvidia-pauses",
        "lang": "es",
        "description": "the NVIDIA question in three pieces with 0.9 s and 1.4 s pauses mid-sentence (ONE turn), then a "
                       "short follow-up turn",
        "noise_db": -58,
        "items": [
            {"say": "es_a", "text": "¿Qué suele hacer NVIDIA los viernes?", "role": "user", "turn": 1},
            {"say": "es_a", "text": "Quiero decir, los últimos treinta viernes,", "role": "user", "turn": 1,
             "gap_ms": 900},
            {"say": "es_a", "text": "¿cuántas veces sube?", "role": "user", "turn": 1, "gap_ms": 1400},
            {"say": "es_a", "text": "¿Y cuántas baja?", "role": "user", "turn": 2, "gap_ms": 4000},
        ],
    },
    {
        "id": "en-crosstalk-in-pause",
        "lang": "en",
        "description": "a second person says something unrelated during the user's mid-sentence pause; the user then "
                       "finishes the same sentence (ONE user turn; the other speaker is not the user)",
        "noise_db": -58,
        "items": [
            {"say": "en_a", "text": "Can you check what time my dentist appointment is", "role": "user", "turn": 1},
            {"say": "en_b", "text": "Did anyone feed the cat this morning?", "role": "other", "gap_ms": 350,
             "gain_db": -5},
            {"say": "en_a", "text": "on Thursday afternoon?", "role": "user", "turn": 1, "gap_ms": 250},
            {"say": "en_a", "text": "And move it to Friday if it clashes with work.", "role": "user", "turn": 2,
             "gap_ms": 4000},
        ],
    },
    {
        "id": "es-cut-off-and-correction",
        "lang": "es",
        "description": "a self-correction inside one turn; then the user is cut off mid-sentence by a second person "
                       "talking over, and restarts with a new turn",
        "noise_db": -58,
        "items": [
            {"say": "es_a", "text": "Pon una alarma a las siete,", "role": "user", "turn": 1},
            {"say": "es_a", "text": "no, perdona, a las seis y media.", "role": "user", "turn": 1, "gap_ms": 450},
            {"say": "es_a", "text": "Y mándale un mensaje a Rowan diciendo que llego tarde a la reunión",
             "role": "user", "turn": 2, "gap_ms": 4000, "cut_s": 1.5},
            {"say": "es_b", "text": "¡Espera, espera, que se está quemando la cena!", "role": "other", "gap_ms": -250,
             "gain_db": -3},
            {"say": "es_a", "text": "Vale, lo del mensaje luego.", "role": "user", "turn": 3, "gap_ms": 3500},
        ],
    },
    {
        "id": "en-tv-and-cough",
        "lang": "en",
        "description": "the TV talks in the background the whole time; the user coughs inside a pause of a turn",
        "noise_db": -50,
        "items": [
            {"tv": "en_tv", "texts": ["And now, the weather for tomorrow across the country.",
                                      "Heavy rain is expected in the north, with strong winds near the coast.",
                                      "In sports tonight, the home team won its third game in a row."],
             "at_ms": 0, "gain_db": -16},
            {"say": "en_b", "text": "What's on my calendar for tomorrow morning", "role": "user", "turn": 1},
            {"cough": 1, "gap_ms": 300},
            {"say": "en_b", "text": "before ten?", "role": "user", "turn": 1, "gap_ms": 250},
            {"say": "en_b", "text": "Thanks. Turn the volume down a bit.", "role": "user", "turn": 2,
             "gap_ms": 4000},
        ],
    },
    {
        "id": "mixed-es-en-switch",
        "lang": "es",
        "description": "the user switches from Spanish to English inside one turn after a 0.7 s pause, then a turn in "
                       "English",
        "noise_db": -58,
        "items": [
            {"say": "es_b", "text": "Búscame un restaurante italiano para esta noche,", "role": "user", "turn": 1},
            {"say": "en_b", "text": "I mean, something close to the office.", "role": "user", "turn": 1,
             "gap_ms": 700, "lang": "en"},
            {"say": "en_b", "text": "For two people, around nine.", "role": "user", "turn": 2, "gap_ms": 4000,
             "lang": "en"},
        ],
    },
]

BY_ID = {s["id"]: s for s in SCENARIOS}
