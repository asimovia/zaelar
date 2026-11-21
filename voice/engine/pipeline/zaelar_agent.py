"""The node overrides of zaelar's LiveKit agent in the voice's own process (V2-538, V2-891).

  · `llm_node` — the reply comes from the body (`remote_brain.remote_llm_node`): the voice process observes, the body
    decides.
  · `tts_node` — what is SPOKEN, and the one place every spoken path converges on (a reply, `say()`, a proactive
    notice). Figures are made speakable here and nowhere else, so «151.008 €» cannot slip through by taking another
    road (V2-538); on screen he reads «151.008 €». What the voice is fed is what the wall gets if the synthesis fails
    (`reply_wall.tee`, V2-773).

The ear's own events pass untouched (`stt_node` is LiveKit's), and so does what LiveKit forwards as subtitles
(`transcription_node`).
"""
from __future__ import annotations

from livekit.agents import Agent

from ..core import langs


class ChildAgent(Agent):
    def llm_node(self, chat_ctx, tools, model_settings):
        from . import remote_brain as _rb
        return _rb.remote_llm_node(self, chat_ctx, tools, model_settings)

    def tts_node(self, text, model_settings):
        from voice.engine.speech import say_numbers as _sn
        from . import reply_wall as _rw     # V2-773: what the voice is fed is what the wall gets if it fails
        return _sn.tts_node_speaking_figures(self, Agent.default.tts_node, _rw.tee(text), model_settings,
                                             langs.current_code())
