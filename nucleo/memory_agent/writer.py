"""The pill GRAMMAR, and the one door a RESULT is written through.

A pill's `kind` says what KIND of knowledge it is, and `result` is not like the others: it claims an errand
delivered. Only the circuit that ran the errand and judged its end state knows that; the operator's words never do —
«captúrame el estilo hasta darlo por capturado» is a REQUEST, and stored as a result it answered «¿has terminado?»
with «Sí, está terminado» for an errand that had failed (V2-825 F1).

So the grammar is enforced where a pill is born, not at the reader:
  - the distiller's kinds are `profile · pref · fact · event · intent · request` (`request` = something he ASKED
    the assistant to do). A `result` the model returns is stored as a `request` (`distilled_kind`).
  - `admits(...)` is the gate of the circuit's verdict: a `result` is written (by the row's close,
    `ledger.remembered`) only when the worker DELIVERED (the verdicts that declare `delivered`), stamped with the
    verdict so a reader tells «checked» from «delivered, unverified»; a failed or parked errand writes nothing.
"""
from __future__ import annotations

RESULT = "result"


def distilled_kind(raw: object) -> str:
    """The kind a distilled pill is stored as. A `result` from the distiller is a request by construction; an
    unknown kind stays as the model wrote it (readers treat it as a fact), an empty one is a fact."""
    kind = (str(raw or "") or "fact").strip().lower() or "fact"
    return "request" if kind == RESULT else kind


def admits(task_id: str, verdict: str, text: str) -> tuple[str, str]:
    """THE gate of a task's outcome into memory: `(verdict name, why not)` — `why` is '' only when the verdict
    declares the worker DELIVERED and there is text. Observed either way. Its one writer is the row's close
    (`ledger.remembered`), so a failed or parked errand writes nothing anywhere."""
    from nucleo.circuit import verdict as _verdict   # each verdict declares whether the worker DELIVERED
    v = getattr(_v := _verdict.of(str(verdict or "").strip().lower()), "name", str(verdict or "").strip().lower())
    why = ("" if text and _v is not None and _v.delivered
           else "empty text" if not text else f"verdict is {v or 'missing'}, nothing delivered")
    _observe(task_id, v, why)
    return v, why


def _observe(task_id: str, verdict: str, why: str) -> None:
    """The door's decision is an event: accepted, or refused and why."""
    try:
        from voice.observer import emit
        emit("memory", "resultado rechazado" if why else "resultado aceptado", role="system", text=why,
             extra={"layer": "write", "pill_kind": RESULT, "task_id": task_id, "verdict": verdict,
                    "accepted": not why, "reason": why})
    except Exception as e:  # noqa: BLE001 — observability NEVER breaks the memory
        from loguru import logger
        logger.debug(f"memory_agent.writer: result-door event not emitted: {e}")
