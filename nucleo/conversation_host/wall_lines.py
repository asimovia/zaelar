"""His spoken lines in the record and on the wall, as the old turn wrote them (V2-941).

Every reader of a conversation (the chat wall, the session log, the canvas's turn, the screens' stamps, the memory's
conversation log) reads his spoken words from ONE row: `transcript` 🗣, role user, followed by the attention verdict
that releases it on the wall (`ambient`, directed). The old turn wrote both from the provider's final transcript; in a
session of the manager LiveKit opens no turn, so the manager's ear writes them instead: once per intervention the
inbox ACCEPTED (closed, incomplete or a local phrase), with the words it entered with, before any reply to it. A
discard (echo, a closed microphone, not addressed, a bare stop) never enters, so it is never written. Interim captions
still come from the provider's own stream, as before.
"""
from __future__ import annotations

UTTERANCE = "user.utterance"
LABEL = "🗣"
VERDICT = "👂 addressed (conversation)"


def listen(kind: str, label: str, p: dict) -> None:
    """The conversation's telemetry, in its thread: an accepted spoken entry becomes his line."""
    if kind != "conv_inbox" or label != "accepted" or p.get("kind") != UTTERANCE:
        return
    refs = p.get("refs") or {}
    text = str(p.get("text") or "").strip()
    if refs.get("channel") != "voice" or not text:
        return
    from nucleo.conversation_host import turns
    trace = turns.corr(refs.get("iv"), text) or str(p.get("trace") or "")      # his turn's id (C16)
    from voice import attention, observer
    observer.emit("transcript", LABEL, text=text, role="user", extra={"trace": trace}, piece="u_voice")
    try:
        window = {"window_s": attention.window_s(), "window_open": attention.window_open()}
    except Exception:  # noqa: BLE001 — the window is a hint for the ring; the verdict goes without it
        window = {}
    observer.emit("ambient", VERDICT, extra={"directed": True, "reason": "conversation", "trace": trace, **window},
                  piece="f_gate")
