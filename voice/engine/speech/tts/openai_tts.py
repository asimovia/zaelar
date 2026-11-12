"""OpenAI TTS — the voice's stand-in where no local voice can sound (V2-889 row 10).

The titular voice is a paid remote service; when it fails, the failover adapter (`tts/__init__.py`) switches to this
one. Kokoro cannot sound in a container, so a cloud agent without a REMOTE stand-in went mute on the titular's first
outage. The stand-in keeps the operator's chosen gender (`voices.openai_default_voice`) and is told the language it
speaks, so an outage changes the timbre, never the language. Egress: a mediated deployment calls through egress with
its own credential, like every other remote call.
"""
from __future__ import annotations

from livekit.plugins import openai as _openai

from ...core import langs
from ...core.config import SETTINGS
from .. import voices as _voices
from . import registry


@registry.register("openai")
def build():
    from nucleo.energy import egress
    base_url, api_key = egress.route_url(egress.base_of("openai"), SETTINGS.openai_api_key or "")
    if not api_key:
        raise ValueError("OpenAI TTS: no OPENAI_API_KEY")
    spec = langs.current_language()
    return _openai.TTS(model="gpt-4o-mini-tts", voice=_voices.openai_default_voice(), base_url=base_url,
                       api_key=api_key,
                       instructions=f"Speak natural, warm {spec.name} ({spec.native}) with a native accent.")
