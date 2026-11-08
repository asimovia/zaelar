#
# owner/seams.py — the small doors the messaging owner talks through: the operator note, the secret scan a
# model-composed text passes before it leaves, the origin of an incoming message, and the outbox bookkeeping
# (settling a send, recording the body it left with).
#
from loguru import logger

from connectors.messaging import store as msgstore


def _note(text: str) -> None:
    """Tell the operator a failure he cannot see any other way — the same seam the connectors use for a send that did
    not go out: a matter of the order, said once out of turn (V2-851 F4). The order carries no task id at this seam,
    so the notice is keyed by its words."""
    from nucleo.events import task_event
    task_event.told(text, key=f"messaging:{abs(hash(text)) % 10**10}", ok=False)


def _scrub(text: str) -> tuple[str, str]:
    """The last door before a MODEL-composed text leaves toward somebody outside (V2-683). Returns `(text, "")`
    when clean and `(text, what)` when not, and the caller does not send.

    It FAILS CLOSED and never redacts-and-sends: a secret in a model's text for a third party is a mistake or an
    injection, answered by stopping. Same detector (`memory/secrets.py`) the cluster's outbound scan runs."""
    try:
        from memory import secrets as _secrets
        found = _secrets.detect(text or "")
    except Exception as e:  # noqa: BLE001 — a scan that could not run is not a licence to send
        logger.warning(f"mensajeria: no pude revisar el texto saliente ({e!r}) — no se envía")
        return (text, "un texto que no he podido revisar")
    if found:
        kinds = sorted({str(getattr(f, "kind", "") or "un secreto") for f in found})
        return (text, ", ".join(kinds))
    return (text, "")


def _origin(m: dict) -> tuple[str, str | None]:
    if m.get("isGroup"):
        return (m.get("senderName") or "?", m.get("chatName") or "grupo")
    return (m.get("senderName") or "?", None)


def _settle(ref, ok: bool, reason: str = "", *, retried: bool = False) -> None:
    """Settle the card's outbox row for the send `ref` (V2-819). Never raises: bookkeeping is not the send."""
    try:
        from .. import sent as _sent
        db = msgstore.load()
        if _sent.outbox_settle(db, ref, ok, reason, retried=retried):
            msgstore.save(db)
    except Exception as e:  # noqa: BLE001
        logger.info(f"mensajeria: outbox row {ref} not settled ({type(e).__name__}: {e})")


def _record_left(ev: dict) -> None:
    """The body a send of this card LEFT with (V2-807), on the timeline (`sent.left_event`): what was sent is
    then read from the record, never rebuilt from the conversation that wrote it."""
    from .. import sent as _sent
    rec = _sent.left_event(ev)
    if rec is None:
        return
    try:
        from voice.observer import emit
        emit("widget", "sent", text=rec["text"], extra={"id": "mensajeria", **rec["extra"]})
    except Exception as e:  # noqa: BLE001 — bookkeeping never breaks the owner's loop
        logger.info(f"mensajeria: the sent body was not recorded ({type(e).__name__}: {e})")


def _offer_after_failure(ev: dict) -> list[str]:
    """A send that did not leave: the contact's OTHER channels whose link is up, kept on its outbox row and said to
    him once as an OFFER. Nothing is resent — a message to a third party through another channel is his decision.
    [] when the order names no known contact, or none of the contact's other channels is connected. Never raises."""
    try:
        from widgets import directory
        from .. import sent as _sent
        from ..outbound import targets
        ev = ev if isinstance(ev, dict) else {}
        plat = str(ev.get("platform") or "").strip().lower()
        cid = str(ev.get("contactId") or "").strip()
        contact = next((c for c in directory._contacts() if cid and str(c.get("id") or "") == cid), None) \
            or directory.find_by_channel(plat, ev.get("chatId") or ev.get("to"))
        if not contact:
            return []
        db = msgstore.load()
        alts = targets.alternatives(contact, targets.connected_platforms(db), directory, but=plat)
        if not alts:
            return []
        ref = str(ev.get("ref") or "")
        for r in db.get("outbox") or []:
            if isinstance(r, dict) and ref and r.get("ref") == ref:
                r["offer"] = list(alts)
                msgstore.save(db)
                break
        name = str(contact.get("name") or ev.get("name") or "")
        chans = ", ".join(targets.label(p) for p in alts)
        from .. import owner as _f            # the facade: a patch on `owner._note` governs this line too
        _f._note(f"[SISTEMA] El mensaje a {name} por {targets.label(plat)} no ha salido. Puedo escribirle por {chans}, "
              f"que sí está conectado: ofréceselo al operador y NO lo reenvíes hasta que él lo diga.")
        return alts
    except Exception as e:  # noqa: BLE001 — an offer that cannot be computed is not the failure
        logger.info(f"mensajeria: no offer after the failed send ({type(e).__name__}: {e})")
        return []
