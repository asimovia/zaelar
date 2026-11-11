"""V2-887 — a send the model CALLED and did not narrate is said as a start, never as «I lost that».

Measured (his session T15, and the kindergarten bench 3 of 3 before the fix): «mándale un whatsapp a Raquel Salvador…»
— the model called `mensajeria:send_to` with no words, the send went to its task, and the turn, counting nothing as
handled, fell to the mute line «Perdona, se me ha ido. ¿Me lo dices otra vez?» while the message was on its way. The
typed channel also reported the turn as `chat`. Now the routed send IS the turn's act and its line is the start.
"""
from __future__ import annotations

import pytest

from tests.platform import parvulario as P
from tests.platform import turn_harness as th

SAID = {"es": "Mándale un whatsapp a Raquel Salvador diciéndole que llego diez minutos tarde",
        "en": "Send Raquel Salvador a WhatsApp saying I'll be ten minutes late"}
TEXT = {"es": "llego diez minutos tarde", "en": "I'll be ten minutes late"}


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_silent_send_call_says_the_start_and_names_the_act(lang):
    case = {"id": f"silent-send-{lang}", "lang": lang, "phrase": SAID[lang], "screen": {"open": []},
            "widgets": {"contactos": P.DIRECTORY, "mensajeria": P.INBOX}, "connectors": ["whatsapp", "email"],
            "model": {"say": "", "tools": [{"name": "widget_data", "args": {
                "widget_id": "mensajeria", "action": "send_to",
                "payload": {"contact": "Raquel Salvador", "channel": "whatsapp", "text": TEXT[lang]}}}]},
            "expect": "data-op mensajeria:send_to"}
    out = th.run_case(case)
    from i18n import langs
    start = langs.spec(lang).done_just_started
    mute = tuple(langs.spec(lang).mute_lines)
    assert out.decision == "data-op mensajeria:send_to", out.decision
    assert start in out.reply and not any(m in out.reply for m in mute), out.reply
