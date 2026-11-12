"""OpenAI STT — the ear's stand-in (V2-889 row 10). Not streaming: the failover adapter wraps it with the VAD."""
from __future__ import annotations

from livekit.plugins import openai as _openai

from ...core import langs
from ...core.config import SETTINGS
from . import registry


@registry.register("openai")
def build(vad=None):
    from nucleo.energy import egress
    base_url, api_key = egress.route_url(egress.base_of("openai"), SETTINGS.openai_api_key or "")
    if not api_key:
        raise ValueError("OpenAI STT: no OPENAI_API_KEY")
    auto = langs.first_run_auto()
    return _openai.STT(model="gpt-4o-mini-transcribe", base_url=base_url, api_key=api_key,
                       language="" if auto else langs.current_code(), detect_language=auto)
