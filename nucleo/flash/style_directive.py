"""The set_style_directive handler, whole (V2-046 A1 + V2-633 + V2-806). Identity actions get first refusal (a
rename / the attention-mode toggle ride the same tool); everything else is a RULE, understood ONCE when it is
written: `rules.shape.write` makes one structured model call against the declared vocabulary and stores, removes
or lists rows of the rules table — style knobs, permission gates and notes alike, by scope. The session layer
(`brain._directive`) carries his sentence only until its rows exist, and the agent repeats back once, in plain
words, what it understood. No regex decides the direction or the scope of a rule.
"""
from __future__ import annotations

import asyncio

from loguru import logger


def handle(directive: str, text: str, brain, emit, spawn) -> bool:
    """Run the whole directive path. Returns True when identity_actions consumed the turn — the caller must
    stop there (the identity handler speaks and acts on its own)."""
    from nucleo.flash import identity_actions as _ident   # rename/attention-mode toggle
    if _ident.handle_voice(directive, emit, spawn):
        return True
    brain._directive = directive         # obeyed at once, until the rows exist
    emit("brain", "🎯 directiva de estilo fijada", text=directive, role="system")
    spawn(write_rule(directive, text, emit, brain), "user-rule")
    return False


async def write_rule(directive: str, text: str, emit, brain=None, *, speak: bool = True) -> dict:
    """Shape and store the rule off the turn, say what was understood, and hand the session layer back."""
    import rules.shape as _shape
    try:
        res = await asyncio.to_thread(_shape.write, directive, text)
    except Exception as e:  # noqa: BLE001 — the session layer keeps the sentence for this session
        logger.warning(f"rule not written (the session keeps it): {e}")
        return {}
    for attr in ("_directive", "directive"):  # the voice brain's session layer, or the probe session's
        if brain is not None and getattr(brain, attr, None) == directive:
            setattr(brain, attr, "")     # his rows govern now
    for r in res.get("stored") or []:
        emit("brain", "🧬 user rule guardada (persiste)", text=(r["text"] or directive)[:100], role="system",
             extra={"id": r["id"], "scope": r["scope"], "kind": r["kind"], "key": r["key"]})
    for r in res.get("removed") or []:
        emit("brain", "🧬 user rule retirada", text=(r["text"] or r["id"])[:100], role="system", extra={"id": r["id"]})
    line = repeat_back(res)
    if line and speak:
        from voice import proactive
        await proactive.notify("reglas", line, speak=True, key=f"rule:{abs(hash(line)) % 10**8}",
                               opens_window=bool(res.get("doubt")))
    return {**res, "line": line}


def repeat_back(res: dict) -> str:
    """What the agent says once: the model's own restatement, with the rows it names when it lists or asks."""
    import rules.shape as _shape
    say = str(res.get("say") or "").strip()
    rows = res.get("listed") or res.get("doubt") or []
    if rows:
        return (say.rstrip(".:") + ": " if say else "") + _shape.listing_line(rows)
    return say if (res.get("stored") or res.get("removed") or res.get("op") == "list") else ""


def prompt_lines(mstate: dict) -> list[str]:
    """The runtime-mode lines the prompt's last layer appends — both teach or ride THIS module's tool.
    Wake-word: the attention mode is runtime config, so the line reflects its current state and tells the
    model the toggle is a set_style_directive call. Silent-orders (V2-633): while the style policy says a
    short order runs in silence, the MODEL's own mouth must match the gated engine mouths — the backstop no
    longer injects «Hecho.», and the model saying it itself would be the same noise."""
    lines: list[str] = []
    try:
        from config import settings as _cfg_att
        att_mode = str(_cfg_att.get("attention_mode") or "always")
        att_name = (mstate.get("assistant_name") or "Zaelar").strip() or "Zaelar"
        att_now = ("ACTIVADO (solo atiendes los turnos que dicen tu nombre, o los que siguen a uno reciente)"
                   if att_mode in ("smart", "wakeword") else "desactivado (escuchas siempre)")
        lines.append(
            f"MODO WAKE WORD — el modo en el que solo respondes cuando dicen tu palabra de activación, que ES "
            f"tu nombre («{att_name}»; nunca preguntes cuál es la palabra ni cómo se llama el operador: ambos "
            f"están en tu ESTADO). Ahora está {att_now}. Si el operador pide activarlo o desactivarlo («activa "
            f"el modo wake word», «escúchame/respóndeme solo cuando diga tu nombre», «vuelve a escucharme "
            f"siempre»), LLAMA a set_style_directive con esa orden tal cual — el sistema lo aplica al instante; "
            f"no pidas ningún dato más y nunca digas que está hecho sin haber llamado a la tool.")
        if att_mode in ("smart", "wakeword"):
            # V2-768 — WHY it is listening, as a fact: asked «¿por qué me has interrumpido?» after a window
            # its own spoken alert had opened, the model answered «porque oí tu nombre» — the likeliest cause,
            # and false. See `voice/attention_opening.py`.
            try:
                from voice import attention_opening as _opening
                why = _opening.why_listening()
            except Exception:
                why = ""
            if why:
                lines.append(
                    f"POR QUÉ ESTÁS EN CONVERSACIÓN AHORA — {why} Si te pregunta por qué entraste, te activaste "
                    f"o le interrumpiste, di ESTO con tus palabras; nunca inventes otra causa.")
            # V2-657 — the ASIDE exit. Measured at the 2026-09-10 dinner: «Acostaros» got «Buenas noches»,
            # «Luis, disfrutemos de las noticias» got a clarifying question — the model had no way to let a
            # turn PASS, so it answered room talk and every answer kept the conversation window alive.
            lines.append(
                "CONVERSACIÓN CON GENTE DELANTE — hay más personas en la sala y el micro lo oye todo. Si el "
                "turno va CLARAMENTE dirigido a otra persona (la nombra por su nombre, o es charla doméstica "
                "de la sala sin ninguna petición ni pregunta para ti), responde EXACTAMENTE con [[aparte]] y "
                "nada más: ni una palabra, ninguna tool. Nunca contestes a lo que no era para ti ni preguntes "
                "qué significaba. Ante la MÍNIMA duda de que sí te hablaba a ti, contesta con normalidad.")
    except Exception:
        pass
    try:
        from nucleo import style_policy as _stylep
        sl = _stylep.prompt_line()
        if sl:
            lines.append(sl)
        # V2-713 R5 — la FORMA del turno (cuántas frases, una acción o varias) compuesta desde la política.
        shape = _stylep.shape_line()
        if shape:
            lines.append(shape)
    except Exception:
        pass
    return lines


async def handle_probe(d: str, text: str, sess, ingest: bool):
    """Probe-channel mirror (this module owns the tool in BOTH channels). Returns the identity action label when
    identity_actions consumed the directive, else None after writing the rule (gated to real turns)."""
    from nucleo.flash import identity_actions as _ident
    act = await _ident.handle_probe(d, ingest=ingest) if d else None
    if act or not d:
        return act
    sess.directive = d
    if ingest:
        from voice.observer import emit
        await write_rule(d, text, emit, sess)
    return None
