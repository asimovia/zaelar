"""The RUNNING ERRANDS block of the live state — what the Brain Workers are solving NOW (`dispatch.pending_summaries()`).

Its faces and why: no step reported yet (V2-133) · stalled (V2-131) · no plan step done (V2-354) · what the worker SAYS
it found (V2-444) · something delivered while it runs (V2-222) · something FAILED (V2-348) · its sheet's rows (V2-451)
· and the offer to stop, made ONCE (V2-454). Moved from `nucleo/flash/task_block.py` (refactor2710-08b).
"""
from __future__ import annotations

from nucleo.flash.errand_sheet import rows_of_sheet

def _short_note(note: str, limit: int = 110) -> str:
    """A worker's step note, shortened WITHOUT cutting a word in half — and saying so when it was cut.

    Measured 2026-08-23 (`cheapest-monitor`, round 7): a hard `[:60]` turned

        «Comparativa entregada en pantalla (hoja de resultados con los 3 finalistas)»

    into «…con lo», dropping exactly the words that said results existed. The brain, asked four times
    whether it had anything, answered «sigo pendiente» over a sheet already holding three candidates.

    Two rules, and the second matters as much as the first: cut on whitespace, and mark the cut with an
    ellipsis. A truncated note that ends cleanly reads as a COMPLETE one, which is how «con lo» became a
    sentence the model was entitled to treat as the whole message.
    """
    n = " ".join((note or "").split())
    if len(n) <= limit:
        return n
    head = n[:limit]
    cut = head.rfind(" ")
    return (head[:cut] if cut > limit // 2 else head).rstrip(" ,;:.") + "…"


#: V2-874 — the most his commissioning sentence takes on a live errand's line (≈ 40 tokens; cut on a word, marked).
ASKED_MAX = 140


def name_of(t: dict) -> str:
    """The errand's ONE name on its line (V2-878 §2): his commissioning sentence when it was heard, bounded (`ASKED_MAX`,
    cut on a word and marked), the errand's request otherwise — never both, so one errand is never said twice.

    Measured (demo S3, 2026-11-10, V2-874): the line carried only the worker's title cut at 60 («Buscar monitores de 27
    pulgadas con resolución 4K (UHD) con ») and «abre el que sea mejor oferta» found nothing to refer to. His words
    travel with the errand whatever the window holds; the worker's title is no longer said beside them."""
    heard = " ".join(str(t.get("heard") or "").split())
    if heard:
        return f"«{_short_note(heard, ASKED_MAX)}» (lo pidió así)"
    return f'«{_short_note(str(t.get("request") or ""), 60)}»'


def pending_task_lines() -> list[str]:
    """El bloque de TAREAS DE FONDO EN CURSO, renderizado (V2-348).

    Mudado desde `prompt.live_state()` el 2026-08-26 por el trinquete de arquitectura, con el mismo criterio y
    el mismo precedente que `navegador_lines()` (V2-276): es un bloque que se compone ENTERO a partir de un solo
    registro —`dispatch.pending_summaries()`— y no comparte un dato con los otros dos. Mudanza, no cambio de
    interfaz; el contrato público sigue siendo `live_state()`.

    Las CARAS y el porqué de cada una siguen documentados donde se aplican, abajo: sin paso reportado (V2-133) ·
    encallada (V2-131) · ya ha encontrado candidatos (V2-222) · algo ya entregado con la tarea viva (V2-222,
    segunda cara) · algo ha FALLADO (V2-348, la simétrica de la anterior).
    """
    lines: list[str] = []
    try:
        # V2-038 §v3·G: UNA sola verdad — el registro RAM de dispatch (no el summary_line del escalate legacy).
        # Lectura de dict en RAM (µs, sin I/O): más fresca que el bloque BRAIN WORKERS del ESTADO (proyección ~1 Hz),
        # útil para el turno inmediatamente posterior a lanzar una tarea.
        from nucleo import dispatch as _disp
        _pend = _disp.pending_summaries()
        if _pend:
            # Incluye el PASO concreto (phase) + el tiempo → el operador preguntó "¿en qué punto estás?" y recibía
            # siempre "sigue en desarrollo continuo" ("eso has dicho hace 6 min", sesión 2026-07-15). El modelo debe
            # dar el paso real + elapsed y ser HONESTO si lleva mucho en el mismo paso.
            bits = []
            _ofrecer: list[str] = []
            for t in _pend:
                ph = (t.get("phase") or "").strip()
                bit = name_of(t) + (f' — {ph}' if ph else "")
                # V2-059: progreso ESTRUCTURADO si el worker lo reporta (paso N/total, %, nota) → respuesta precisa
                # a "¿cómo va?" en vez de una fase vaga.
                pct, done, total = t.get("pct", -1), t.get("done", 0), t.get("total", 0)
                if total:
                    bit += f' [paso {min(done, total)}/{total}'
                    bit += (f', {pct}%]' if pct >= 0 else ']')
                elif pct >= 0:
                    bit += f' [{pct}%]'
                if t.get("note"):
                    # 60 chars used to CUT THE PAYLOAD OUT of the note, and measured 2026-08-23 on
                    # `cheapest-monitor` (round 7) that cost the round. The worker reported
                    #     «Comparativa entregada en pantalla (hoja de resultados con los 3 finalistas)»
                    # and the prompt carried
                    #     «Comparativa entregada en pantalla (hoja de resultados con lo»
                    # — severed mid-word at exactly the point where it said results EXIST and how many. The
                    # brain then spent five turns answering «sigo pendiente» over a sheet that already held
                    # Dell, LG and MSI. A note is written to be read whole; cut it on a WORD boundary and say
                    # out loud when it was cut, so a truncated note can never read as a complete one.
                    bit += f' — {_short_note(str(t["note"]))}'
                if not ph and pct < 0 and not total and not t.get("note"):
                    # SIN PASO REPORTADO. Se dice con esas letras (V2-133): el bloque pedía «di el PASO concreto»
                    # a secas, y cuando no había ninguno el modelo rellenaba el hueco NARRANDO uno. La tanda del
                    # 2026-08-18 lo midió en 8 de 12 casos, con la forma exacta de una fase de worker: «en estos
                    # momentos está en la fase de login» de un gimnasio cuyo nombre todavía no tenía. No es que
                    # el modelo mintiera por gusto: se le mandaba decir algo que nadie le había dado.
                    bit += " — SIN paso reportado aún"
                # V2-131 — «llevo un rato intentándolo y parece que se está demorando» dicho al ARRANCAR, y
                # después seis turnos de «sigue en marcha» sobre una tarea que no había emitido nada. El
                # supervisor de `nucleo/pulse/loop.py` SÍ sabía que estaba encallada (`silent_s`, umbral compartido)
                # y lo decía por su cuenta; aquí nunca llegaba, así que el cerebro solo veía «arrancó hace N
                # segundos» y tenía que adivinar qué cuenta como mucho. Se le da el HECHO, como con «SIN paso
                # reportado aún»: la instrucción vaga («si lleva MUCHO, sé honesto») pedía un juicio con el
                # dato fuera de la vista.
                _silent = int(t.get("silent_s", 0) or 0)
                _atascada = False
                if _silent >= _disp.STUCK_SECS:
                    bit += f" — ENCALLADA: {_silent // 60} min SIN DAR NINGUNA SEÑAL"
                    _atascada = True
                # V2-354, TERCERA cara de la misma familia: viva, hablando, y sin avanzar UN paso de su plan.
                # Medido en `restaurant-tonight-madrid` (2026-08-27): plan de 4 pasos declarado a los 49 s y el
                # primero reportado a los 380 — **331 segundos en «0/4, 0%»** mientras navegaba y leía capturas.
                # Ninguna cara salió: ENCALLADA mira el SILENCIO y ésta no callaba; «SIN paso reportado» no
                # aplica porque plan SÍ había. Y el plan lo empeora en vez de ayudar — «0/4, 0%» se lee como
                # «no ha empezado», que es una cifra tranquilizadora, y el operador tuvo que insistir tres
                # veces. Va en un `elif`: una tarea CALLADA ya está dicha, y decir las dos es ruido.
                elif int(t.get("total", 0) or 0) and int(t.get("no_step_s", 0) or 0) >= _disp.NO_STEP_SECS:
                    _ns = int(t["no_step_s"])
                    bit += (f" — SIN AVANZAR: {_ns // 60} min sin completar un paso "
                            f"(sigue en {min(int(t.get('done', 0) or 0), int(t['total']))}/{int(t['total'])})")
                    _atascada = True
                # V2-454 — LA OFERTA DE PARAR SE HACE UNA VEZ. El hecho se queda (V2-224).
                if _atascada:
                    if _disp.stall_offered(t.get("id")):
                        bit += " [YA le ofreciste pararla]"
                    else:
                        _ofrecer.append(str(t.get("id") or ""))
                # V2-222, third face — measured on `search-secondhand-monitor__es` (2026-08-23 23:24). The
                # browser block said, in the same prompt, «YA TIENE RESULTADOS … DÁSELOS en este turno», and
                # this one said «en cola (llevas 23s)». Two registries describing ONE errand, disagreeing:
                # the finalists live in the worker record (`kept`, written by `hbnote considered --kept N`),
                # and this block never read it, so the queue phase — which the worker had simply never
                # updated — was the only thing here. The turn answered «te aviso en cuanto tenga
                # resultados» with 35 real listings on the sheet, twice, and the round was scored as
                # disobedience. It was not: a self-contradicting prompt has no obedient answer. The datum
                # is already on the summary; the same signal the browser face reads (V2-200) is read here.
                _kept = int(t.get("kept", 0) or 0)
                if _kept > 0:
                    bit += f" — DICE haber encontrado {_kept} candidato(s) (es SU cuenta sin comprobar)"   # V2-444
                _f = rows_of_sheet(str(t.get("sheet") or ""), 3) if t.get("sheet") else []   # V2-451
                if _f:
                    bit += " — ENCONTRADO (en su hoja): " + "; ".join(_f)
                    # WHERE that sheet is NOW, as a fact (demo pass 30, S1). The block below says «negar una
                    # entrega que el operador tiene delante en la pantalla…», and with the sheet CLOSED the
                    # model answered «the shortlist is on your screen» to «show me» — and opened nothing. The
                    # canvas reports what is open; the block now says it instead of leaving it to be assumed.
                    from nucleo.flash import canvas_visibility as _cv
                    _up = _cv.card_is_open(str(t.get("sheet") or ""))
                    if _up is True:
                        bit += " [su hoja ESTÁ abierta ahora]"
                    elif _up is False:
                        bit += " [su hoja NO está en pantalla: la cerró]"
                # The errand's latest WEB LEAD (demo pass 30): it used to arrive as a note pushed into
                # whatever the next turn was about. Here it sits next to its own task, and it is a lead.
                try:
                    from nucleo.workers import findings as _fd
                    _lead = _fd.last_lead(t.get("id"))
                except Exception:  # noqa: BLE001
                    _lead = ""
                if _lead:
                    bit += f" — ÚLTIMA PISTA DE LA WEB (una página que miró, NO un candidato salvo que traiga su nombre y su precio): «{_lead}»"
                bits.append(bit + f' (llevas {t.get("secs", 0)}s)')
            for _t in _ofrecer:
                _disp.mark_stall_offered([_t])     # V2-454: este turno la lleva delante
            # V2-878 §2 — FACTS ONLY, like `recent_lines`. The ~900-token imperative paragraph that rode here every turn
            # with a live errand (V2-130/131/142/222/348/354/444/454/556) is gone; each face it was written for stays as
            # its FACT on the errand's own line (SIN paso · ENCALLADA · SIN AVANZAR · DICE · ENCONTRADO · hoja abierta o
            # cerrada · ÚLTIMA PISTA). If a face regresses, the fact it lacked is added — never the sentence.
            lines.append("TAREAS DE FONDO EN CURSO (hechos de cada una; lo que no figura aquí no se sabe): "
                         + "; ".join(bits) + ".")
    except Exception:
        pass
    return lines


def waiting_lines() -> list[str]:
    """The tasks whose ROW waits for his answer (`waiting_for=user_answer`), oldest first — read fresh into EVERY turn
    (V2-851 §2b: Flash knows the state of every task from the row, and answers «how is it going» in one line without
    waking anybody; the worker ended after asking). Battery C7 measured the old reader: it rode the memory block's
    cache, so the turn 15 ms after the row turned `waiting` read a block built before it. Each row the turn carries is
    recorded on the turn's trace (`task_id`), so what the line was composed from is in the flow. Never raises."""
    try:
        from nucleo.circuit import ledger
        rows = [r for r in ledger.store().tasks_where(states=("waiting",), visible_only=False, limit=20)
                if str(r.get("waiting_for") or "") == ledger.USER_ANSWER][:6]
    except Exception as e:  # noqa: BLE001
        from loguru import logger
        logger.debug(f"live_tasks: waiting rows unreadable — {e!r}")
        return []
    if not rows:
        return []
    lines = []
    for r in rows:
        goal = (str(r.get("title") or r.get("goal") or "")).strip().replace("\n", " ")[:90]
        ask = (str(r.get("ask") or "")).strip()[:120]
        since = _ago(r.get("waiting_since"))
        lines.append(f"  · [{r.get('id')}] «{goal}» — ESPERA tu respuesta a: «{ask}»" + (f" (desde {since})" if since else ""))
        _carried(r)
    return ["⚠️ Un proceso de fondo ESPERA una respuesta del operador (abajo). PROCESOS DE FONDO en marcha ahora:\n"
            + "\n".join(lines)]


def _carried(row: dict) -> None:
    try:
        from voice.observer import emit
        emit("task", "📌 row read into the turn", text=str(row.get("title") or "")[:120], role="system",
             extra={"cat": "flash", "task_id": str(row.get("id") or ""), "state": str(row.get("state") or ""),
                    "waiting_for": str(row.get("waiting_for") or ""), "ask_id": str(row.get("ask_id") or "")})
    except Exception as e:  # noqa: BLE001 — the flow is a witness; the prompt line stands without it
        from loguru import logger
        logger.debug(f"live_tasks: carried row not recorded — {e!r}")


def _ago(ts) -> str:
    if not ts or not str(ts).strip().lstrip("-").isdigit():
        return ""
    import time
    secs = max(0, int(time.time()) - int(ts))
    if secs < 3600:
        return f"hace {max(1, secs // 60)} min"
    if secs < 86400:
        return f"hace {secs // 3600} h"
    return f"hace {secs // 86400} d"
