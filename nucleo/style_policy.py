"""Conversational style policy (V2-633): who may SPEAK when a short order runs, and when a wait filler may
sound. Three engine mouths talk without the model — the fast lane's ack (V2-572), the provider's never-mute
backstops («Hecho.» / «Aquí lo tienes», V2-026), and the lead-in filler (V2-529) — and none of them consulted
any rule, so the operator's own directive («al recibir órdenes no responder nada») was obeyed by the model
and then overridden by the engine putting words in its mouth. Measured live (session 6c715232, 2026-09-09):
the rule was set and persisted at 16:40:41 and «Reproduce el vídeo» still produced «Déjame ver…» + «Hecho.».

Layering, exactly as the operator ordered it:
  1. GENESIS (`nucleo/genesis.json`, ships with the engine): the factory defaults every install starts from.
     Today: short orders run in SILENCE (the visible effect is the answer) and fillers are "smart" (never on
     a turn that is itself a short order — a thinking sound before «pausa» reads as incomprehension, V2-572).
  2. HIS ROWS (V2-806): each knob is a `pref` row of the rules table at the `voice` scope (`rules/`); the
     genesis value is the default row. Written when a spoken rule is understood (`rules.shape`, one structured
     call when the rule is written — no word table) and read per use through the cascade, so it survives
     restarts. Removing the rule deletes his row and the genesis default is back. The legacy
     `<workspace>/config/style.json` is imported once.

Scope: these flags gate the VOICE mouths only. The chat channel keeps its text acks — a written «Hecho.»
interrupts nobody, while an empty chat bubble looks broken; the probe (text-channel parity harness) is
untouched for the same reason.
"""
from __future__ import annotations

import json
import time
from pathlib import Path


_FILLER_MODES = ("off", "smart", "on")



def _overrides_path() -> Path:
    from nucleo import workspace as _ws
    return _ws.root() / "config" / "style.json"


def _migrate() -> None:
    """One-time import of the legacy `config/style.json` into the rules table (V2-806): each override becomes a
    user `pref` row at the `voice` scope. A marker per database and deterministic ids keep a re-run a no-op."""
    from rules import store as _rstore
    p = _overrides_path()
    marker = f"migrated:style.json:{p}"
    if _rstore.once_done(marker):
        return
    try:
        data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except (OSError, ValueError) as e:
        import logging
        logging.getLogger("zaelar.style").warning(f"style: {p} unreadable ({e}) — nothing migrated")
        data = {}
    data = data if isinstance(data, dict) else {}
    at = float(data.get("_set_at") or time.time())
    for k, v in data.items():
        if not str(k).startswith("_"):
            _rstore.insert_new({"id": f"m_style_{k}", "scope": "voice", "kind": "pref", "key": str(k), "value": v,
                                "source": "user", "created_at": at, "origin": f"style.json:{k}"})
    _rstore.mark_done(marker)


def policy() -> dict:
    """The effective style knobs: genesis `style` (the `voice` default rows) under his rows, through the rules
    cascade over the voice surface."""
    import rules
    from rules import defaults as _rdef
    _migrate()
    vals = rules.resolve(rules.path(surface="voice"))["values"]
    return {k: vals.get(k) for k in _rdef.style_keys()}


def set_pref(key: str, value, text: str = "") -> dict:
    """His row for one style knob at the `voice` scope — effective on the very next turn."""
    import rules
    _migrate()
    rules.add("voice", "pref", str(key), value, text=text)
    return {key: value}


def confirm_short_actions() -> bool:
    """May a VOICE mouth speak a bare ack («Hecho.») after a short order ran with nothing else to say?"""
    return bool(policy().get("confirm_short_actions", False))


def filler_mode() -> str:
    m = str(policy().get("fillers", "smart")).lower()
    return m if m in _FILLER_MODES else "smart"


def filler_allowed(kind: str = "neutral") -> bool:
    """May the lead-in filler sound on a turn of this `filler_audio.filler_kind`? "smart" (genesis default)
    keeps it for thinking turns (questions, requests that take real work) and drops it on ACTION turns —
    the operator's literal complaint: «te digo reproduce esta canción y me dices vale, un segundo — me
    molestas»."""
    m = filler_mode()
    if m == "off":
        return False
    if m == "on":
        return True
    return kind != "action"


def retract(key: str) -> dict:
    """Remove his row for one knob — the genesis default is back. Returns what was released."""
    import rules
    _migrate()
    gone = rules.clear("voice", key)
    return {key: gone[-1]["value"]} if gone else {}


def max_sentences() -> int:
    """Cuántas frases habla la capa rápida. 0 = sin límite (V2-713 R5)."""
    try:
        return max(0, int(policy().get("max_sentences", 2)))
    except Exception:  # noqa: BLE001
        return 2


def one_action_per_turn() -> bool:
    """Si ejecuta UNA acción por turno o puede encadenar varias (V2-713 R5)."""
    return bool(policy().get("one_action_per_turn", True))


def shape_line() -> str:
    """La FORMA del turno, compuesta desde la política en vez de escrita en el prompt (V2-713 R5).

    Dos frases del bloque `ops` eran preferencias con forma de receta: «Respondes SIEMPRE al instante en 1-2
    frases» y «UNA ACCIÓN por turno». `principles.md` nombra la clase —carril sobre el JUICIO— y desde V2-633
    hay dónde ponerlas, con el operador cambiándolas al decirlo en vez de con un despliegue.

    Se compone, no se enumera: si él sube el límite a cinco frases, la línea lo dice; si quita el límite, la
    mitad de la frase desaparece en vez de contradecir a la política.
    """
    partes = []
    n = max_sentences()
    if n:
        # El plural entero, no solo el sustantivo: «en 1 frase habladas» se lee como una plantilla mal
        # rellenada, y es de las costuras que hacen que el operador deje de creerse lo que lee.
        _pl = "s" if n != 1 else ""
        partes.append(f"Respondes al instante en {n} frase{_pl} hablada{_pl} como mucho")
    if one_action_per_turn():
        partes.append("UNA ACCIÓN por turno")
    if not partes:
        return ""
    return (" · ".join(partes) + ". «Una» es de ACCIONES, no de RESPUESTAS: si en la misma frase te "
            "preguntan DOS cosas, las contestas las dos en ese turno.") if one_action_per_turn() \
        else (" · ".join(partes) + ".")


def prompt_line() -> str:
    """One prompt line so the MODEL's own mouth matches the engine's: under silent-orders it must not say
    «Hecho.» itself (the backstops are gated, but the model's text is its own)."""
    if confirm_short_actions():
        return ""
    return ("ÓRDENES CORTAS EN SILENCIO: cuando ejecutas una orden directa con una tool (pausa, reproduce, "
            "volumen, abrir/cerrar un widget, siguiente canción…), NO digas nada — ni «hecho» ni «un "
            "segundo»: el efecto visible es la respuesta. Habla solo si algo falló, falta un dato, o el "
            "encargo es largo (di brevemente qué vas a hacer). Esta es una regla base; una regla del "
            "OPERADOR más específica manda sobre ella.")


def _reset_for_tests() -> None:
    import rules
    rules._reset_for_tests()
