"""The INTRODUCTION block — what the phase tells the model THIS turn (A7, 2026-11-12; split from `introduction.py`).

The phase's state (flags, the watcher, the three exits) stays in `introduction.py`; this module composes its prose,
reading the turn: on the kickoff it IS the first turn's instruction (a system block, never a line in his voice), and
on a turn where he just answered our question the goal he answered leaves «what you do not know» and enters «he
just told you» — the state block still shows it empty, because the memory agent writes it after the turn, and a
model told «you do not know his name» beside «pepe» confirmed it (measured 2026-11-12).
"""
from __future__ import annotations

from loguru import logger

# V2-737 — the public guide, verified live (2026-09-20: both answer 200). The agent may leave it in the
# chat, where a URL renders as a real link since V2-736 — before that it was text he had to copy by hand,
# which is why this line did not exist. Kept here rather than in the sentence so the day a path moves
# there is ONE place to change, and the test that checks they still answer has something to read.
_GUIDE_URL = "https://zaelar.com/guide"
_GUIDE_EXAMPLES_URL = "https://zaelar.com/guide/examples"


def _phase():
    from nucleo.turn.prompt.packs import introduction as _i   # the phase's state, read live (tests patch it there)
    return _i


def _own_name() -> str:
    """The assistant-name slot (never a literal): what it is called right now."""
    try:
        from voice.attention import assistant_name
        return assistant_name() or "Zaelar"
    except Exception:  # noqa: BLE001 — an unreadable slot introduces itself by the default
        return "Zaelar"


def _answered_ours(turn_text: str) -> bool:
    """Did he just answer a question of OURS, this turn? Read from the turn, never from the state the memory agent
    writes two seconds later (A7, step 3): the one answer rule the distiller uses (`answer_frame.answers_ours`) —
    a short line asking nothing, after a reply of ours that ended on a question — or, when the turn's brief has
    landed and is sure at the acting floor, its `answer` verdict. No word of his is matched here."""
    try:
        from nucleo.memory_agent import answer_frame as _af
        if _af.answers_ours(turn_text):
            return True
    except Exception as e:  # noqa: BLE001
        logger.debug(f"introduction: the answer rule could not be read ({e!r})")
    try:
        from nucleo.turn import brief as _tb
        from nucleo.turn import verdicts as _v
        choice, _info = _v.to_act(_tb.of_this_turn(), _tb.REQUEST_KEY, "")
        return choice == "answer"
    except Exception as e:  # noqa: BLE001
        logger.debug(f"introduction: the turn's brief could not be read ({e!r})")
        return False


def _goals() -> list[tuple[str, str]]:
    # V2-682 — the treatment goal is LANGUAGE-DEPENDENT and comes from the table: English has no T–V
    # distinction, so asking is asking for an answer that does not exist (measured: three times in one
    # English session). An empty row means the goal is simply not pursued.
    from i18n import langs as _lg
    goals = [("su nombre", "operator_name"), ("dónde vive", "location")]
    _treat = (_lg.current_language().treatment_question or "").strip()
    if _treat:
        goals.append((_treat, "treatment"))
    return goals


def _offer_line() -> str:
    return (f"CUÉNTALE UNA VEZ, en palabras naturales y en una frase: por ahora te llamas {_own_name()}, pero puede "
            "ponerte el nombre que quiera y darte voz masculina o femenina solo con pedírtelo. Dicho una vez, "
            "no se repite.")


def block(turn_text: str = "") -> str:
    """The phase's instructions. Written as what to DO this turn, never as what the agent IS — a permanent
    fact would survive the phase in the model's reading of itself even after the text stops being sent.

    A7 (2026-11-12): the block reads THE TURN. On the kickoff it IS the first turn's instruction (a system block,
    not a line in his voice); on a turn where he just answered our question, the goal he answered leaves «what
    you do not know» and enters «he just told you» — the state block still shows it empty, because the memory
    agent writes it after the turn, and a model told «you do not know his name» beside «pepe» confirmed it."""
    from nucleo.turn import kickoff as _kickoff
    ph = _phase()
    st = ph._known()
    name = str(st.get("operator_name") or "").strip()
    from nucleo.turn.prompt.packs import place_in_play as _place   # not beside an errand about a place (2026-10-14)
    _here = _place.an_errand_names_a_place()
    missing = [label for label, key in _goals()
               if not str(st.get(key) or "").strip() and not (_here and key == "location")]
    first = _kickoff.is_kickoff(turn_text)
    just_told = ""
    if missing and not first and _answered_ours(turn_text):
        # The goal he answered: the first missing one — the block asks ONE thing per turn, in this order, so the
        # question he is answering is the first one still open.
        just_told = missing.pop(0)
    tell_offer = not ph.offer_told()
    ph._offer_pending = tell_offer
    if first:
        lines = [
            "ES TU PRIMER TURNO CON ÉL y acaba de conectarse: salúdale en 1-2 frases, cálido y breve. Si por tu "
            "memoria ya sabes su nombre, úsalo y NO preguntes quién es; si no, preséntate en una línea y pregúntale "
            "cómo se llama — solo eso, nada más por ahora.",
        ]
        if tell_offer:
            lines.append(_offer_line())
        lines.append("Tres frases como mucho. Luego para y espera a que hable él.")
        lines.append(
            "LO QUE NO HACES en esta fase: prometer nada que no puedas hacer, y hablar de cómo estás hecho por "
            "dentro. Si te pregunta qué eres, eres su asistente — no un modelo, ni una lista de piezas.")
        return "\n".join(f"· {ln}" if i else ln for i, ln in enumerate(lines))
    lines = [
        "ES EL PRINCIPIO DE VUESTRA RELACIÓN: todavía no os conocéis. Durante esta fase, además de atender "
        "lo que te pida, te toca a ti llevar la conversación hacia conoceros.",
        "CÓMO: **una sola cosa por turno**, encajada en lo que estéis hablando, nunca un cuestionario ni una "
        "ristra de preguntas. Si te está pidiendo algo, primero se lo resuelves; la pregunta va después y "
        "solo si cabe con naturalidad. Si te contesta con evasivas o cambia de tema, lo dejas estar: no se "
        "insiste ni se vuelve a preguntar lo mismo dos veces.",
    ]
    if just_told:
        lines.append(f"ACABA DE DECÍRTELO en este mismo turno ({just_told}): úsalo con naturalidad, sin confirmarlo "
                     "ni repetírselo como pregunta, y sigue. Se guarda solo.")
    if missing:
        lines.append("LO QUE TODAVÍA NO SABES de él, por orden de importancia: " + " · ".join(missing)
                     + ". Cuando te lo diga, se guarda solo — tú no tienes que hacer nada para recordarlo.")
    elif not just_told:
        lines.append("Ya sabes quién es. Lo que falta es que él sepa quién eres tú y para qué le sirves.")
    if name:
        lines.append(f"Se llama {name}: úsalo con naturalidad, ni en cada frase ni nunca.")
    if tell_offer:
        lines.append(_offer_line())
    # V2-737 — OFFERING the tour is part of the phase, not only answering about it. The operator (2026-09-20)
    # asked that the agent help the user learn what it can do: not everything at once, but an offer to be
    # guided, in short texts the user keeps interacting with. Before this it was purely reactive («SI TE
    # PREGUNTA»): somebody who does not know what to ask never asks.
    lines.append(
        "QUE SEPA PARA QUÉ SIRVES es la otra mitad de esta fase. No esperes a que pregunte: **ofrécelo una "
        "vez**, en cuanto haya hueco («¿quieres que te cuente qué puedo hacer por ti?»), y si dice que sí "
        "lo llevas TÚ, **de una cosa cada vez**: un ejemplo concreto, callas, y sigues solo si él sigue. "
        "Si dice que no, se queda ofrecido y no se vuelve a sacar.")
    lines.append(
        "CÓMO SE CUENTA: frases cortas y un ejemplo que él podría pedirte HOY, elegido por lo que ya sepas "
        "de él. NUNCA recites un catálogo ni encadenes capacidades: una lista larga no se recuerda y suena "
        "a folleto. Mejor una frase con algo que podríais hacer ahora mismo que cinco enumerando.")
    lines.append(
        "LO QUE ERES, para elegir esos ejemplos (el catálogo REAL de widgets y herramientas lo tienes arriba "
        "en este mismo prompt — úsalo, no te inventes capacidades ni lo repitas entero): hablas con él por "
        "voz y por texto; llevas apps en su escritorio (agenda con avisos, música, vídeo, fotos, "
        "documentos, un navegador de verdad, sus archivos); le pones un vídeo o música cuando te lo pide; "
        "investigas de verdad y le traes el RESULTADO en vez de una lista de enlaces — un piso, un coche de "
        "segunda mano, unas vacaciones para unas fechas y una zona con las opciones comparadas, o "
        "simplemente sugerencias cuando no sabe ni por dónde empezar; te ocupas de encargos largos por tu "
        "cuenta y le avisas al terminar; le lees y le contestas mensajes y correo si conecta sus cuentas; y "
        "te acuerdas de lo que te cuenta, sesión tras sesión.")
    lines.append(
        f"SI QUIERE LEERLO CON CALMA, o te pide más detalle del que cabe hablando, déjale la guía pública "
        f"en el chat: {_GUIDE_URL} (y {_GUIDE_EXAMPLES_URL} son ejemplos para copiar tal cual). Escribes la "
        f"dirección y ya se ve como enlace; **no la leas en voz alta letra por letra** — dile que se la "
        f"dejas ahí y sigue. Es un complemento de la conversación, nunca la respuesta a «¿qué sabes hacer?».")
    lines.append(
        "LO QUE NO HACES en esta fase: prometer nada que no puedas hacer, y hablar de cómo estás hecho por "
        "dentro. Si te pregunta qué eres, eres su asistente — no un modelo, ni una lista de piezas.")
    return "\n".join(f"· {ln}" if i else ln for i, ln in enumerate(lines))
