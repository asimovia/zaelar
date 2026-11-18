"""The post-stream chain SETTLES what is pending: a confirmation the model left unresolved, a worker that was waiting for an answer, a stop nobody called, and the question the turn owes (V2-778 F1, 2026-10-01).

Moved out of `post_stream.run`: every name it read there is read through it (`_pst.<name>`), so a patch still governs.
"""
from __future__ import annotations

from nucleo.flash import card_receipt as _pst_receipt   # V2-781: a bare ack names the cards the turn changed
from nucleo.flash import post_stream as _pst
from nucleo.turn import split_by_errand as _sbe   # the status line names the errand a send reached (2.644)
from nucleo.request import stop as _stop_decision   # V2-807 T-14: a stop order is the turn's verdict
from nucleo.turn import reply as _reply   # refactor2710-03: the mouth speaks the verdict
from nucleo.turn import wait_lines as _wait_lines
from i18n import langs as _i18n_langs   # V2-834 T01: an answered gate is said as a START or as nothing touched


def stop_ack(spoken_text: str) -> str:
    """What he hears when the backstop stopped an errand: alone, or after the model's words — in HIS language (V2-694)."""
    lang = __import__("i18n.langs", fromlist=["langs"]).current_language()
    return lang.stopped_now if not spoken_text else " " + lang.stopped_also


def settled_ack(spoken_text: str) -> str:
    """A settled errand (V2-831 T-29): the model's own answer to his decision stands; alone, the settled line."""
    return "" if spoken_text else __import__("i18n.langs", fromlist=["langs"]).current_language().errand_settled


async def settle_what_is_pending(*, _ans, _ask_waiting, _auth_pending, _brief, _dialog, _filler_audio, _langs, _prev_pending, _r, _resolve_confirm, _router, _shown_ids, _turn_op_tasks=(), acted, aside, brain, clarify, confirm_state, data_done, emit, escalate_req, had_pending_confirm, llm_metrics, music_req, operator_text, search_req, send, speech, spoken_text, style_fired, text, worker_acted) -> dict:
    if had_pending_confirm and not confirm_state["handled"]:
        try:
            verdict = _pst._wconfirm.answers_pending(text, _brief)
            if verdict:
                _resolve_confirm(verdict == "yes")
        except Exception:
            pass
    # The same key opens the other two gates: a parked irreversible TASK (V2-126, re-launched) and the browser held on
    # an irreversible CLICK (V2-202, unblocked now). One «yes» used to authorise both (2026-08-24); the precedence is
    # decided once, for both channels, in `nucleo/turn/confirm_gates.py`.
    if not had_pending_confirm and not worker_acted["v"]:
        from nucleo.turn import confirm_gates as _gates
        _ans = _gates.resolve_all(text, brief=_brief, say=lambda s: send(speech.sanitize(s, drop_metadata=False)))
        if _ans:   # it answers what is PARKED; an unrelated errand of the same breath still starts (three-tasks)
            _r = _ans.result if isinstance(_ans.result, dict) else {}
            _pst._eot.keep_beside_an_answer(escalate_req, str(_r.get("request") or "") if _ans.gate == "task" else None, declined=not _ans.yes)
            if _ans.gate == "task":
                emit("brain", "✅ confirmación de tarea resuelta" if _ans.yes
                     else "🚫 tarea irreversible descartada por el operador",
                     text=str(_r.get("request", ""))[:120], role="system", extra={"cat": "flash"})
            else:
                emit("brain", "✅ clic confirmado por el operador" if _ans.yes
                     else "🚫 clic descartado por el operador",
                     text=str(_r.get("task_id", "")), role="system", extra={"cat": "flash"})
            # The answer IS the act: said as a START or as nothing touched, never a mute «say it again» (V2-834 T01).
            if not spoken_text and (spoken_text := str(getattr((_langs or _i18n_langs).current_language(), "work_started" if _ans.yes else "confirm_cancelled", "") or "")):
                send(speech.sanitize(spoken_text, drop_metadata=False))

    # V2-931 — his words for an open process were delivered by the switchboard before this turn ran
    # (`nucleo/switchboard`): nothing here binds an answer or reads the model's own routing.
    # STOP backstop: workers are live and the model did NOT call stop_worker. Only the turn's sure stop verdict (or his
    # taken offer) stops one here; with no verdict nothing stops — no word list over his sentence (V2-857 phase 8).
    if worker_acted["v"] not in ("stop",):
        try:
            # V2-773 — «Stop it and close the video widget» is about the CARD the verdict names, never the
            # errands running behind it (two were cancelled on the demo's kickoff).
            tids = _stop_decision.repair(_brief, text, escalating=escalate_req["v"] is not None, acted=worker_acted,
                card_acts={"acted": acted, "data_done": data_done, "lanes": (music_req,)})   # a card's turn (U3)
            if tids:
                worker_acted["v"] = "stop"
                _sr = _stop_decision.reading(_brief, "verdict")
                emit("brain", "🛑 stop worker (stop verdict, the model did not call it)", text=str(tids), role="system",
                     extra={"cat": "flash", **_sr, "source": "verdict" if _sr["verdict"] else "offer"})
                # Un kill SIEMPRE se anuncia por voz (demo 2026-07-14: se mató el worker del widget en
                # silencio mientras la voz decía "no te he entendido" — incoherente). Si el modelo ya
                # habló otra cosa, se AÑADE la frase; nunca un kill mudo.
                _ack = settled_ack(spoken_text) if worker_acted.get("settled") else stop_ack(spoken_text)
                if _ack:
                    send(speech.sanitize(_ack, drop_metadata=False))
                    spoken_text = (spoken_text + _ack) if spoken_text else _ack.strip()
        except Exception:
            pass

    # Confirmación abierta este turno → la pregunta la decimos NOSOTROS, gane lo que gane el modelo.
    # Cubre borrado y data-op irreversible (V2-025).
    #
    # ⚠️ Esto exigía `not spoken_text` hasta V2-693, con el razonamiento de «si el modelo ya dijo algo,
    # ya formuló él la pregunta». Medido el 2026-09-14 en su propia sesión: pidió «limpia todo los items
    # de esta semana, menos lo de mañana a las 15h y el inicio de instituto»; el modelo llamó a
    # `agenda:clear_all`, el gate abrió la confirmación REAL («¿Vacío la agenda entera? Es permanente.»)
    # — y como el modelo había hablado, esa pregunta se calló. Lo único que él leyó fue «Clearing this
    # week from your calendar — keeping tomorrow at 15:00…»: una acción NARRADA como hecha que ni
    # siquiera se había despachado, y cuyo alcance real era el calendario entero, no la semana.
    # Su reacción es la medida del coste: «no ha funcionado la orden… necesitamos un sistema estable».
    #
    # Es exactamente la lección que el bloque de `clarify` de abajo ya aprendió el 2026-07-22 y que
    # este no heredó: una señal DETERMINISTA («esto no se ha hecho y necesito tu sí») no puede perder
    # contra una frase que el modelo se inventó. Y sustituye, no acompaña: la frase del modelo habla de
    # algo que no ha pasado, así que dejarla delante es dejar la mentira delante.
    if confirm_state.get("opened") and escalate_req["v"] is None and search_req["v"] is None:
        spoken_text = confirm_state["opened"]
        send(speech.sanitize(spoken_text, drop_metadata=False))

    # An unresolved item reference (V2-026) is ALWAYS asked, even over words the model already said: a confident
    # «done» over an item that does not exist must never silence the door's question, which is a hard fact.
    if clarify["msg"] and escalate_req["v"] is None and search_req["v"] is None:
        spoken_text = clarify["msg"]
        send(speech.sanitize(spoken_text, drop_metadata=False))
        _reply.settle_asked("clarify")      # V2-831 T-08 — the turn ends on our question: its verdict is `asked`

    # A data-op with no spoken line gets a short ack that never repeats the last one (V2-038); under silent-orders
    # (V2-633) the success ack stays unspoken — failures, clarify and confirm are reports, never gated.
    try:
        from nucleo import style_policy as _style_ack
        _ack_allowed = _style_ack.confirm_short_actions()
    except Exception:
        _ack_allowed = True
    if escalate_req["v"] is None and search_req["v"] is None:   # refactor2710-03: the acts' verdicts are said
        spoken_text = await _reply.after_acts(_turn_op_tasks if data_done["v"] else (), spoken_text, send, speech,
                                              prior=next((str(m.get("content") or "") for m in reversed(getattr(brain, "_window", None) or [])
                                                          if m.get("role") == "assistant"), ""),   # our PREVIOUS reply
                                              # A claim nobody ran (`turn/unserved`): the model's calls verbatim, whether
                                              # any door of the turn ran, and whether an act waits for his yes or his row.
                                              model_calls=list(getattr(brain, "_turn_calls", None) or []),
                                              quiet=not (acted["widget"] or data_done["v"] or style_fired["v"]
                                                         or music_req["v"] is not None or worker_acted["v"]),
                                              held=bool(confirm_state.get("opened") or clarify["msg"]))
    spoken_text = await __import__("nucleo.turn.reply", fromlist=["x"]).routed_send_line(   # V2-887: a routed send is a START
        spoken_text, escalate_req.get("send") or ("send" in escalate_req), data_done["v"], send, speech)
    if data_done["v"] and not spoken_text and _ack_allowed and not ("send" in escalate_req) and escalate_req["v"] is None and search_req["v"] is None:
        try:
            from i18n import langs as _langs   # same object as the voice.engine.core shim
            _lg = _langs.current_language()
            _acks = list(getattr(_lg, "data_acks", None) or (_lg.data_ack,))
            _last = _dialog.sanitize_reply(brain._last_spoken or "").strip().lower()
            spoken_text = _pst_receipt.voice_ack(next((a for a in _acks if a.strip().lower() != _last), _acks[0]))
        except Exception:
            spoken_text = "Hecho."
        # The ack is a claim about the cards (V2-783 P0-2): an unmet end state on a card this turn wrote to says what is
        # true instead (`reply_receipts.bare_ack`).
        from nucleo.turn import reply_receipts as _receipts
        spoken_text = _receipts.bare_ack(spoken_text, {str(w).split("::", 1)[0] for w, _a in (data_done.get("ops") or [])},
                                         turn=__import__("voice.trace", fromlist=["x"]).current(),
                                         ops=data_done.get("ops"))   # «Done.» only over attested acts (2026-11-18)
        send(speech.sanitize(spoken_text, drop_metadata=False))

    # Regla de usuario fijada/retirada SIN frase hablada → ack corto (V2-046 A1, visto en el probe: la
    # RETIRADA dejaba el turno MUDO). Nunca mudo al aceptar/quitar una regla.
    if style_fired["v"] and not spoken_text and escalate_req["v"] is None and search_req["v"] is None:
        try:
            from i18n import langs as _langs   # same object as the voice.engine.core shim
            spoken_text = _langs.current_language().data_ack
        except Exception:
            spoken_text = "Vale, lo tengo."
        send(speech.sanitize(spoken_text, drop_metadata=False))

    # SHOW/CLOSE de canvas por tag SIN frase hablada → ack corto (bug 2026-07-13: el modelo emitía [[show:agenda]]
    # sin decir nada → turno MUDO; el operador no oía NI veía nada y creía que estaba roto). Nunca mudo al abrir/
    # cerrar un widget.
    if acted["widget"] and not spoken_text and _ack_allowed and not ("send" in escalate_req) \
            and escalate_req["v"] is None and search_req["v"] is None \
            and not confirm_state.get("opened") and not clarify["msg"]:
        try:
            from i18n import langs as _langs   # same object as the voice.engine.core shim
            from nucleo.flash import router_guards as _rg_show2
            _lg_ack = _langs.current_language()
            spoken_text = (_rg_show2.show_ack(_lg_ack, str(acted.get("widget_id") or ""),
                                              chose=str(acted.get("show_chose") or ""))
                           if acted.get("widget_id") else _pst_receipt.voice_ack(acted.get("act_line", _lg_ack.data_ack)))   # a close is not an open (S4); a chooser opened says so
        except Exception:
            spoken_text = "Aquí lo tienes."
        send(speech.sanitize(spoken_text, drop_metadata=False))
    spoken_text = __import__("nucleo.acts.self_controls", fromlist=["x"]).say_the_way_back(acted, spoken_text, send, speech)   # one-way: the button is the way back (V2-930)

    # V2-660/V2-658 — what the turn OWES (`harness_turn`): the cards it showed are goals the prompt carries, and a
    # widget_data cut by the cap escalates with a document surface. No line is said for it after the reply (V2-851 F5).
    try:
        _pst._ht.note_shown(_shown_ids, _router.operator_words(operator_text, text), trace=_pst._ht.current_trace())
        _owed = None if (escalate_req["v"] is not None or aside["v"] or acted["widget"] or data_done["v"]
                         or search_req["v"] is not None or music_req["v"] is not None) \
            else _pst._ht.oversized(text, llm_metrics)
        if _owed:
            escalate_req["v"] = _owed["request"]
            escalate_req["surface"][_owed["request"]] = _owed["surface"]
            emit("brain", "🧾 widget_data cortada por el tope → escalada con superficie documento",
                 text=_owed["head"][:120], role="system")
    except Exception as _e_h: _pst.logger.warning(f"turn repairs skipped: {_e_h}")  # noqa: BLE001,E701

    # Escalada sin texto hablado → frase de espera neutral (V2-029/V2-189): varía turno a turno y esquiva
    # la apertura si un filler ya sonó — en `harness_turn.holding_line`, con su historia.
    if escalate_req["v"] is not None and not spoken_text:
        spoken_text = _wait_lines.holding_line_now(brain._window, _prev_pending, after_filler=_filler_audio.played_recently())
        send(speech.sanitize(spoken_text, drop_metadata=False))
    elif not spoken_text and worker_acted["v"] and (spoken_text := _sbe.status_with_refined(operator_text, _brief)):
        send(speech.sanitize(spoken_text, drop_metadata=False))   # a status question owes the phases (three-tasks)
    if spoken_text and (_oq := __import__("nucleo.dispatch.confirm", fromlist=["x"]).owed_question(spoken_text)):
        send(speech.sanitize(_oq, drop_metadata=False)); spoken_text = f"{spoken_text} {_oq}"  # noqa: E702 — never said
    _out = locals()
    return {k: _out[k] for k in ('spoken_text', ) if k in _out}
