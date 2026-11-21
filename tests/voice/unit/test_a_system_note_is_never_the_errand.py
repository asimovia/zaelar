"""A `[SISTEMA]` note is CONTEXT for the turn. It can never become the thing to go and do.

Measured live, operator session c480413b (2026-08-31). He asked for an appointment with a traumatologist in
Soria through Sanitas. What appeared on his screen, in the widget titles and out loud was a PLUMBER:

    «Oye, el proceso "· [tarea web] un fontanero que pueda ven" pregunta: …»

The chain, event by event:
  1. Turn one's recall did not close inside the 800 ms budget — `memory | recall sin entregar`.
  2. It finished afterwards, and `recall_budget.py` salvaged it as a note for the NEXT turn:
     `[SISTEMA] La memoria durable llegó tarde … Esto es lo que tenía: · [tarea web] un fontanero…`.
  3. `nucleo.py` glues pending notes to the front of the turn: `text = notes + "\\n\\n" + text`. The line right
     above it captures `operator_text` BEFORE that, and says why — the notes are «NUNCA como parte de lo que el
     operador pidió».
  4. The promise-backstop then read `text`, not `operator_text`. A Brain Worker was born with that memory line
     as its goal, racing the real errand for nine minutes: two browser tabs, two results cards, two workers.

So the fix was already sitting in the file as a variable. What was missing was using it at the seam that turns
a promise into WORK — the one place where reading the wrong string does not just confuse an answer, it spends
money and fills the screen.
"""
from tests import voice_turn_source as _vts


NOTE = ("[SISTEMA] La memoria durable llegó tarde para la pregunta «Hola, ¿estás ahí?» del turno anterior. "
        "Esto es lo que tenía: Puede que venga a cuento (de tu memoria):\n"
        "· [tarea web] un fontanero que pueda venir hoy → Me he quedado sin cuota en el proveedor.")
ASKED = "Necesito concertar una cita en un traumatólogo en Soria."


# ── the seam itself: the backstops must read the operator, not the turn ───────────────────────────────────
from pathlib import Path

NUCLEO = Path(__file__).resolve().parents[3] / "voice" / "engine" / "llm" / "providers" / "nucleo.py"


def _backstop_block() -> str:
    src = _vts.read(NUCLEO)
    i = src.find('_no_tool = (not acted["widget"]')
    assert i > 0, "the backstop block moved: this guard would be watching nothing"
    j = src.find("BACKSTOP DETERMINISTA de CIERRE", i)
    assert j > i, "the end of the backstop block moved: this guard would be watching nothing"
    return "\n".join(l for l in src[i:j].splitlines() if not l.strip().startswith("#"))


# ── the note is a BLOCK, and a question is not a promise (2026-09-01, session 651cd038) ───────────────────
"""The plumber came back, through the other door.

The operator pressed Reset, restarted his browser and asked for catamaran prices. Two browsers opened. The
second card was titled «Cita en Valls» — a city name from a medical-appointment errand of weeks earlier, taken
from a late recall's `[SISTEMA]` note. Three things had to be true at once, and every one of them was:

  1. The V2-049 promise backstop (the FORCED escalation) still read the note-prefixed turn text. Yesterday's
     fix converted its sibling block and left this one; the source guard only watched the sibling.
  2. `strip_system_notes` — the single door every escalation passes through — strips only the LINES that start
     with the prefix, and the late-recall note announces itself on line one and then LISTS what it recovered.
     Its body survived, and with it the errand's name.
  3. The reply that triggered it was «¿Los precios de qué, Ricardo? Dime de qué quieres verlos y te lo miro.»
     — the agent asking for the datum it needs, which is the correct behaviour. The «te lo miro» read as an
     unkept promise.

Measured over every firing of that gate in the operator's own sessions (2026-08-17 → 2026-09-01): of ten, THREE
were a clarifying question and only one ever escalated — the one above.
"""

NOTE_MULTILINE = (
    "[SISTEMA] La memoria durable llegó tarde para la pregunta «Es el primer turno. Salúdame en 1-2 frases» "
    "del turno anterior. Esto es lo que tenía: Puede que venga a cuento (de tu memoria):\n"
    "· La ciudad se llama Valls (pronunciado 'Valch').\n"
    "· El operador prefiere que se use solo su nombre de pila; si piden un apellido, que se invente uno.\n"
    "· Usa solo mi nombre, Vale, pues mira, quiero cita para mí, ¿vale? Búscame el traumatólogo, y creo que e")
ASKED_FRAGMENT = "A ver, quiero ver cuáles son los precios"


def test_a_multiline_note_does_not_leak_its_body_through_the_single_door():
    """Stripping only line one is WORSE than not stripping: what is left has lost the `[SISTEMA]` marker that
    would let anyone downstream recognise it, so it reads as something the operator said."""
    from nucleo.acts import errand as escalate
    got = escalate.strip_system_notes(NOTE_MULTILINE + "\n\n" + ASKED_FRAGMENT)
    assert got == ASKED_FRAGMENT, "the note's body became the operator's request — that is «Cita en Valls»"
    assert "Valls" not in got and "·" not in got


def test_only_notes_still_yields_nothing_to_do():
    from nucleo.acts import errand as escalate
    assert escalate.strip_system_notes(NOTE_MULTILINE) == ""


def test_a_turn_with_no_notes_is_untouched():
    """The common case must not change: a plain turn keeps every one of its lines."""
    from nucleo.acts import errand as escalate
    plain = "búscame un hotel en Soria\n\npara el jueves"
    assert escalate.strip_system_notes(plain) == plain


ASKS_FOR_A_DETAIL = [
    "¿Los precios de qué, Ricardo? Dime de qué quieres verlos y te lo miro.",
    "Zaragoza a la ciudad de... me has dejado la frase a la mitad, Ricard — ¿a qué ciudad quieres ir?",
    "Perdona, Ricard: me falta saber los dos puntos exactos para poder calcular el trayecto.",
    "Which model are you looking for?",
]
REALLY_PROMISES = [
    "¡Claro! Me pongo a buscar un digestólogo en Soria. Dame un momento y te enseño lo que encuentre.",
    "Voy a mirarlo, Ricardo.",
    "Ahora mismo te la enseño. Estoy aún con la búsqueda, que va un poco lenta.",
    "Me pongo con ello. ¿Te aviso cuando lo tenga?",
]
