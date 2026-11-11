"""widgets/confirm.py: CONFIRMATION gate for IRREVERSIBLE widget actions (V2-017, V2-025).

Reusable seam for any action requiring explicit OK before execution. Before running it, a pending confirmation is
registered and a "Yes / No" overlay is painted on the canvas card itself. This is host-level, so it works for any
widget and does not touch its `widget.js`. The operator confirms in two ways, both resolving the same pending item:
  - **card button** -> `POST /widgets/{id}/confirm {ok}` -> `resolve()`;
  - **voice** -> the brief's pick over the question's row, a reply that IS one of its declared answers
    (`answers_pending`), or the model's tool (`confirm_widget_delete`).
Without a yes, or after TTL expiry, nothing is executed. Two pending classes exist today:
  - **`delete`**: delete the whole widget (V2-017); execution is handled by `lifecycle.delete_widget`.
  - **`data`**: an irreversible data-op marked `confirm:true` in the manifest (V2-025, sibling of
    `nucleo/danger.py`). On confirmation, the provider dispatches the mutation (`op` = {action, payload}) through
    the same `apply_action`, without escalating to code. That is the point: irreversible does not mean code work.

V2-878 §4 — the question WAITS ON A ROW, always: `request()` writes it through the one asker
(`nucleo/request/consent_ask`, a `waiting_for=user_answer` row with its `ask_id` and two declared answers). The registry
below is this process's INDEX of those rows — what the voice's early answer and the brain's line read — never the truth:
an entry whose row no longer waits on its `ask_id` is dropped, and an entry on a row never expires by the wall clock
(a suspension's frozen hours are not his silence; the row's own `deadline` ends it). Only an entry no row could be
written for keeps the old in-memory TTL. Which of several questions a reply answers is the brief's binding verdict
(`nucleo/cli/worker_api_bind`), never «the most recent».
"""
from __future__ import annotations

import time

_PENDING: dict[str, dict] = {}     # widget_id -> {action, question, ts, trace_id, uid?, ask_id?} — an index of rows
_TTL = 90.0                        # only an entry with NO row expires in memory (no store could hold its question)

# Queue of confirmations that JUST expired unanswered, awaiting a proactive notice to the operator (2026-08-16,
# operator request after a real diagnosed incident: two turns for the same "delete all my agenda" instruction —
# split by the segmenter — each opened its OWN confirmation on the same widget, silently clobbering one another
# in `_PENDING`; nothing ever told the operator, and one of the two flows sat "EN CURSO" forever with no way to
# answer it). `_sweep()` (called constantly, from request/pending/resolve) only enqueues here; it never notifies
# directly — that would require an async call from a function with no guaranteed running loop. `nucleo/pulse/loop.py`'s
# ~1Hz tick, which already owns the proactive-delivery rails (voice+chat), drains this once per tick instead.
_EXPIRED_QUEUE: list[dict] = []


def _emit(action: str, wid: str, extra: dict | None = None) -> None:
    try:
        from voice.observer import emit
        emit("widget", action, extra={"id": wid, **(extra or {})})
    except Exception:
        pass


def _close_flow(trace_id: str, reason: str) -> None:
    """Emits the explicit flow-close for a confirmation's ASKING trace once it's superseded or expired
    (2026-08-16). Without this, that flow shows "EN CURSO" in the flow viewer forever: the turn that opened it made
    its ONE close decision (`nucleo.py::_maybe_close_flow`, at the moment IT finished) and correctly chose not
    to close while its confirmation was alive — nothing ever revisits that decision afterward, so once the
    confirmation disappears from `_PENDING` (superseded by a new ask on the same widget, or TTL-expired) the
    flow would otherwise never get a close event again. Best-effort, never blocks `request()`/`_sweep()`."""
    if not trace_id:
        return
    try:
        from voice import trace as _trace, observer as _observer
        with _trace.scope(trace_id):
            _observer.emit("flow", "end", role="system", extra={"ok": False, "reason": reason})
    except Exception:
        pass


def _sweep() -> None:
    now = time.time()
    for k, v in list(_PENDING.items()):
        if v.get("ask_id"):
            from nucleo.circuit import asker
            if not asker.row_waits(str(v.get("uid") or ""), str(v["ask_id"])):
                _PENDING.pop(k, None)          # answered on its row (the brief's pick, the card's button) or ended there
            continue
        if now - v["ts"] > _TTL:
            _PENDING.pop(k, None)
            _close_flow(v.get("trace_id", ""), "confirm_expired")
            _EXPIRED_QUEUE.append({"widget_id": k, **v})


def drain_expired_notices() -> list[dict]:
    """Pops every confirmation that just expired unanswered, for the caller to tell the operator — a pending
    question can never just die in silence (2026-08-16 operator request). Meant to be called once per tick by
    `nucleo/pulse/loop.py`, the only caller that acts on the return value; every other `_sweep()` call site (far more
    frequent) only needs the flow closed, which already happened inside `_sweep()` itself."""
    out = list(_EXPIRED_QUEUE)
    _EXPIRED_QUEUE.clear()
    return out


# Reserved id for a native surface that also asks for confirmation (V2-086). It is not a catalog widget: it is the
# ChatWall "Clusters" tab. This module's store has always been generic (a dict by key), so reusing it avoids a
# parallel confirmation mechanism. The only specifics are where the Yes/No UI is painted (tab, not card) and who
# resolves it (`/api/meshkore/confirm`, not `/widgets/{id}/confirm`).
NATIVE_CLUSTERS = "clusters"


def ui_paints(widget_id: str) -> bool:
    """Whether a confirmation on this widget should paint the card's visual Yes/No overlay. Default True.
    A widget opts out via `"confirm_ui": false` in its manifest (2026-08-15, operator request: the agenda
    is voice-only — no button/overlay). Voice resolution never depended on the overlay,
    so opting out changes only whether a card gets a button. Moved here from the provider (V2-515): it is
    widget-domain logic — it reads the manifest — and the provider's ratchet is right that it never
    belonged there."""
    try:
        from . import runtime as _runtime
        man = _runtime.get((widget_id or "").strip().lower())
        if man is not None:
            return bool(man.get("confirm_ui", True))
    except Exception:
        pass
    return True


def request_restore(spoken: str) -> dict:
    """Resolve + register a `restore` confirmation in ONE step (V2-515): match the operator's words against
    what is RESTORABLE (forks + hidden shipped widgets — `lifecycle.restorable_id`; a hidden widget is out
    of the catalog, so the normal identify cannot see it), then open the pending. Returns
    `{"wid", "question"}`, or `{}` when nothing restorable matches. Lives here, not in the provider: the
    resolution is widget-domain, and the confirmation seam is this module's whole job."""
    from . import lifecycle
    wid = lifecycle.restorable_id(spoken)
    if not wid:
        return {}
    from i18n import langs as _lg
    question = _lg.current_language().widget_restore_confirm.format(wid=wid)
    request("restore", wid, question, notify_ui=ui_paints(wid))
    return {"wid": wid, "question": question}


def request(action: str, widget_id: str, question: str = "", op: dict | None = None,
            notify_ui: bool = True) -> str | None:
    """Register a pending confirmation for `widget_id` and (unless `notify_ui=False`) request the card overlay
    through SSE. Returns the normalized id, or None if the id is invalid.

    `action` is the confirmation class: `"delete"` (delete the widget) or `"data"` (an irreversible data-op).
    For `"data"`, `op` carries the real mutation ({"action": <name>, "payload": {...}}) that the resolver dispatches
    through `apply_action` on confirmation; it never escalates to code.

    `notify_ui=False` (2026-08-15, operator request): some widgets are voice-only by DESIGN — a visual Yes/No
    overlay pinned on the card is unwanted "chrome" for them. The confirmation itself is UNCHANGED (still
    registered, still expires, still resolved the exact same way): this only skips the SSE emit that paints the
    overlay, so voice ("sí"/"no") is the ONLY way to answer. The caller (`nucleo.py`) decides this per widget by
    reading its manifest's `confirm_ui` flag — this module stays widget-agnostic."""
    _sweep()
    wid = (widget_id or "").strip().lower()
    if not wid:
        return None
    # Observability (V2-090 addenda, 2026-08-15): the OPERATOR's yes/no reply lands in its OWN turn — a different
    # trace than the one that asked — and today those show up as two unrelated flows in the flow viewer. Capturing the
    # asking turn's trace here lets `resolve()` hand it back so the resolver can adopt it: the confirmation's
    # whole life (ask → answer → executed action) reads as ONE flow, not two.
    try:
        from voice import trace as _trace
        _trace_id = _trace.current()
    except Exception:
        _trace_id = ""
    # SUPERSEDE explicitly, never silently drop (2026-08-16): a second ask for the same widget before the first
    # got answered used to overwrite the dict entry in place, orphaning the FIRST asking trace forever (see the
    # `_EXPIRED_QUEUE` comment above for the incident). The new ask's question gets spoken/chatted the normal
    # way (the provider's "never mute" fallback fires whenever a confirmation just opened); this only makes sure
    # the OLD one's flow doesn't linger unclosed once it can no longer be answered.
    _old = _PENDING.get(wid)
    if _old and _old.get("trace_id") and _old["trace_id"] != _trace_id:
        _close_flow(_old["trace_id"], "confirm_superseded")
    if _old and _old.get("ask_id"):
        _end_row(_old, False, outcome="a newer question on the same card replaced it")
    _PENDING[wid] = {"action": (action or "delete").strip(), "question": (question or "").strip(),
                     "op": op if isinstance(op, dict) else None, "ts": time.time(), "trace_id": _trace_id}
    _PENDING[wid].update(_on_its_row(wid, _PENDING[wid]))
    if notify_ui:
        _emit("confirm", wid, {"action": _PENDING[wid]["action"], "question": _PENDING[wid]["question"]})
    return wid


def _on_its_row(wid: str, p: dict) -> dict:
    """The question on a ROW through the one asker (V2-878 §4): `{uid, ask_id}`, or {} when no row could be written —
    then, and only then, this registry holds it alone. What his yes runs is retained on the row exactly as the
    consent door retains it, so an answer after a restart runs the same act (`inline_ask.rerun`)."""
    try:
        from nucleo.request import consent_ask as _ca
        op = p.get("op") if isinstance(p.get("op"), dict) else {}
        action, question = str(p.get("action") or ""), str(p.get("question") or "")
        if action in ("delete", "restore"):
            row, ask_id = _ca.ask_consent(wid, action, {}, question, kind=action)
        elif _cluster_op(op):
            row, ask_id = _ca.ask_consent(wid, "cluster", {}, question, kind="cluster", op=op)
        elif str(op.get("action") or "").strip():
            row, ask_id = _ca.ask_consent(wid, str(op["action"]), op.get("payload") or {}, question)
        else:
            return {}                                 # no act declared: nothing a yes could run, nothing to keep
        return {"uid": row, "ask_id": ask_id} if row and ask_id else {}
    except Exception as e:  # noqa: BLE001 — the in-memory entry still holds the question
        __import__("loguru").logger.warning(f"confirm: the question of {wid} is not on a row ({e!r})")
        return {}


def _cluster_op(op: dict) -> bool:
    try:
        from connectors.meshkore import send_gate
        return send_gate.confirmed_tag(op) is not None
    except Exception:  # noqa: BLE001
        return False


def pending() -> dict[str, dict]:
    _sweep()
    return dict(_PENDING)


def pending_line() -> str:
    """Line for FlashBrain live state: a confirmation is in flight, so the model must interpret the operator's
    yes/no as the answer to that and call `confirm_widget_delete`, not treat it as conversation. Covers both widget
    deletion and a pending irreversible data-op."""
    _sweep()
    if not _PENDING:
        return ""
    def _what(v: dict) -> str:
        if v.get("action") == "data" and isinstance(v.get("op"), dict):
            return f"la acción «{v['op'].get('action')}»"
        return "el borrado"
    bits = "; ".join(f"«{wid}» — {_what(v)}" for wid, v in _PENDING.items())
    return ("CONFIRMACIÓN PENDIENTE — le pediste al operador que confirme " + bits + ". Si dice que SÍ, llama a "
            "`confirm_widget_delete(confirmed=true)`; si dice que NO, `confirm_widget_delete(confirmed=false)`. "
            "No lo trates como charla nueva.")


def resolve(widget_id: str = "", ok: bool = True) -> dict | None:
    """Resolve one pending confirmation: the one for `widget_id`, or, with no id, the ONLY one. With several and no id
    nothing is resolved here: which one his reply answers is the brief's binding verdict over their rows (V2-878 §4) —
    «the most recent» answered the wrong question. Returns {'widget_id', 'action', ...} or None. Bookkeeping only: the
    caller performs execution in its own loop; the row is ended here, once (`inline_ask.take`), so its own answer path
    never runs the act a second time. If `ok` is False, notify the card to remove the overlay."""
    _sweep()
    wid = (widget_id or "").strip().lower()
    p = None
    if wid and wid in _PENDING:
        p = _PENDING.pop(wid)
    elif not wid and len(_PENDING) == 1:
        wid, p = _PENDING.popitem()
    if p is None:
        return None
    if p.get("ask_id") and not _end_row(p, ok):
        return None                                   # its row's own answer already ran it
    if not ok:
        _emit("confirm-cancel", wid)
    return {"widget_id": wid, **p}


def _end_row(p: dict, ok: bool, *, outcome: str = "") -> bool:
    """The answer read here ends the question's row — once: False when the row's answer was already taken."""
    try:
        from nucleo.request import inline_ask
        if not inline_ask.take(str(p["ask_id"])):
            return False
        from nucleo import circuit
        circuit.settle(row=str(p.get("uid") or ""), state="done" if ok else "cancelled",
                       outcome=outcome or ("he confirmed it" if ok else "he did not confirm it"))
    except Exception as e:  # noqa: BLE001 — the act is still his answer; the row is the part that failed
        __import__("loguru").logger.warning(f"confirm: the row of the answered question not ended ({e!r})")
    return True


def bound_by_brief(brief) -> bool:
    """The turn's brief read the binding question over the open rows (`worker_api_bind`): its pick answers the one it
    names (or none, or asks which), so no reading of his words here answers a question that waits on a row."""
    if brief is None or not any(v.get("ask_id") for v in _PENDING.values()):
        return False
    try:
        from nucleo.cli import worker_api_bind as _bind
        from nucleo.turn import verdicts as _v
        choice, info = _v.read(brief, _bind.KEY, None, min_confidence=0.0)
        return bool(info) and choice is not None
    except Exception as e:  # noqa: BLE001
        __import__("loguru").logger.debug(f"confirm: binding verdict unreadable — {e!r}")
        return False


def only_pending() -> tuple[str, dict]:
    """The one confirmation waiting, or ("", {}) when none or several — several are told apart by the brief only."""
    items = list(pending().items())
    return items[0] if len(items) == 1 else ("", {})


def _options(p: dict):
    """The two answers its row DECLARED (in his language when it was asked), or None for the pack's own."""
    try:
        from nucleo.circuit import asker
        return asker.artefact(str(p.get("uid") or "")).get("options") or None
    except Exception:  # noqa: BLE001
        return None


def answers_pending(text: str, brief=None) -> str | None:
    """'yes' | 'no' | None — his reply to the ONE confirmation waiting, before the model (V2-090: a barge-in used to
    lose his «yes»). Only a reply that IS one of the row's two declared answers is read here (`consent_ask
    .declared_answer`, V2-878 §4b); anything longer, or several questions waiting, or a brief that read the binding
    question over the rows, is the brief's pick — never a word table (the yes/no regexes went), never a second model
    (the judge went in §4a). Demo pass 45: «ok book it, call it catch up with rowan» sent a pending mail on its «ok»."""
    if bound_by_brief(brief):
        return None
    wid, p = only_pending()
    if not wid:
        return None
    from nucleo.request import consent_ask as _ca
    return _ca.declared_answer(text, _options(p))


def _leaves(wid: str, p: dict) -> bool:
    """Is the pending act one that leaves the machine (`external.send`)? Unreadable → yes (never a licence)."""
    op = p.get("op") if isinstance(p.get("op"), dict) else {}
    if "external.send" in (op.get("effects") or []):
        return True                     # a row outside any widget declares its own effect (V2-805: a cluster send)
    try:
        from widgets import effects as _fx
        return p.get("action") == "data" and _fx.carries(wid, str(op.get("action") or ""), _fx.EXTERNAL_SEND)
    except Exception:  # noqa: BLE001
        return True


def backs_a_yes(text: str) -> bool:
    """Do HIS words agree to the pending act — when that act LEAVES the machine (`external.send`)? Any other pending
    act keeps the model's reading (True). Demo pass 133 (2026-10-15), E3→E4: the forward to Quinn asked «Shall I send
    it?», the next turn was «oh and leave that inworld one as unread», and the model answered the question itself —
    `confirm_widget_delete(confirmed=true)` — so the mail went out on a sentence that never said yes. His words back
    it only when they ARE the row's declared yes; a longer yes is the brief's pick over the row, which answers it."""
    wid, p = only_pending()
    if not wid or not _leaves(wid, p):
        return True
    from nucleo.request import consent_ask as _ca
    return _ca.declared_answer(text, _options(p)) == "yes"


def reset() -> None:
    """Clear the registry for tests — and end the rows it indexed, so no question outlives the test that asked it."""
    for p in list(_PENDING.values()):
        if p.get("ask_id"):
            _end_row(p, False, outcome="reset")
    _PENDING.clear()
