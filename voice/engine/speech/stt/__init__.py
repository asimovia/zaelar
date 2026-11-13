"""STT family — streaming speech-to-text (remote or local), with the table's stand-in (V2-889 row 10).

The titular ear (`SETTINGS.stt_provider`) and the `stt` row's failover in `config/models` are built together and
LiveKit's `FallbackAdapter` switches to the stand-in the moment the titular fails — a non-streaming stand-in is wrapped
with the session's VAD by the adapter. Before, the row existed and nobody read it: an outage of the titular left the
agent deaf. Every switch is SAID (an alert event) WITH the titular's last error (V2-896), so a relay never hides an
outage — nor a defect of ours that looks like one (a socket closed on silence); a stand-in that cannot be built here is
said at boot too. `active_provider()` names the ear hearing now; the meter bills each metric to the plugin that
produced it (`relay.provider_for`), never to the titular by default.
"""
from __future__ import annotations

from loguru import logger

from ...core.config import SETTINGS
from ...core.registry import Registry
from .. import relay

registry = Registry("STT")


def _note(msg: str, **extra) -> None:
    logger.warning(msg)
    try:
        from voice.observer import emit
        emit("alert", msg, role="system", extra={"cat": "stt", **extra})
    except Exception as e:  # noqa: BLE001 — the log line above already says it
        logger.debug(f"stt: alert not emitted: {e!r}")


def _stand_in(primary: str) -> str:
    try:
        from config import models as _models
        row = _models.failover("stt") or {}
    except Exception as e:  # noqa: BLE001 — no table row means no stand-in, never a boot failure
        logger.debug(f"stt: no failover row: {e!r}")
        return ""
    name = str(row.get("provider") or "").strip()
    return name if name and name != primary and name in registry.names() else ""


def active_provider() -> str:
    """The ear hearing now: the selected one until the adapter gave up on it."""
    return relay.active("stt", SETTINGS.stt_provider)


def build_stt(vad=None):
    primary = SETTINGS.stt_provider
    relay.forget("stt")
    first = registry.create(primary, vad=vad)
    backup = _stand_in(primary)
    if not backup:
        relay.track("stt", [(primary, first)])
        return first
    try:
        second = registry.create(backup, vad=vad)
    except Exception as e:  # noqa: BLE001 — a stand-in that cannot hear here is not offered, and that is SAID
        _note(f"⚠️ STT has no stand-in here: «{backup}» cannot be built ({type(e).__name__}: {e}) — "
              f"an outage of «{primary}» leaves the agent deaf", provider=primary, stand_in=backup, standin_missing=True)
        relay.track("stt", [(primary, first)])
        return first
    if vad is None and not second.capabilities.streaming:
        _note(f"⚠️ STT stand-in «{backup}» needs a VAD and none was given", provider=primary, stand_in=backup,
              standin_missing=True)
        relay.track("stt", [(primary, first)])
        return first
    from livekit.agents.stt import FallbackAdapter
    names = [primary, backup]
    adapter = FallbackAdapter([first, second], vad=vad, max_retry_per_stt=1)
    relay.track("stt", [(primary, first), (backup, second)])
    # The session reads the TITULAR's capabilities (interim results, word-aligned transcript), as it did before the
    # relay: the adapter's own are the intersection, which would quietly change barge-in for every session.
    import dataclasses
    adapter._capabilities = dataclasses.replace(first.capabilities, streaming=True)

    def _changed(ev) -> None:
        stt = getattr(ev, "stt", None)
        i = 0 if stt is first else 1 if stt is second else None
        if i is None:
            return
        if not ev.available:
            if relay.active("stt", names[0]) == names[i]:
                relay.set_active("stt", names[1 - i])
            cause = relay.take_cause("stt", names[i]) or "no error reported"
            _note(f"🙉 STT «{names[i]}» failed ({cause}) — hearing with «{names[1 - i]}»", provider=names[i],
                  stand_in=names[1 - i], cause=cause)
        elif i == 0:
            relay.set_active("stt", names[0])
            relay.take_cause("stt", names[0])
            _note(f"👂 STT «{names[0]}» is back", provider=names[0])

    adapter.on("stt_availability_changed", _changed)
    adapter._zaelar_providers = names
    return adapter


def available() -> list[str]:
    return registry.names()


from . import deepgram, openai_stt, voxtral, whisper_local  # noqa: E402,F401

__all__ = ["build_stt", "available", "registry", "active_provider"]
