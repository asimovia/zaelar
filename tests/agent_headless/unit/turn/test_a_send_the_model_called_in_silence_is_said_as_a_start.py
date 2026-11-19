"""V2-887 — a send the model CALLED and did not narrate is said as a start, never as «I lost that».

Measured (his session T15, and the kindergarten bench 3 of 3 before the fix): «mándale un whatsapp a Raquel Salinas…»
— the model called `mensajeria:send_to` with no words, the send went to its task, and the turn, counting nothing as
handled, fell to the mute line «Perdona, se me ha ido. ¿Me lo dices otra vez?» while the message was on its way. The
typed channel also reported the turn as `chat`. Now the routed send IS the turn's act and its line is the start.
Since V2-938 the send has ONE owner (`nucleo/send`): the model's call becomes the owner's draft, and the turn's line
is its confirmation — the message read back, never the mute line, and nothing sent before his yes.
"""
from __future__ import annotations

import pytest

from tests.platform import parvulario as P
from tests.platform import turn_harness as th

SAID = {"es": "Mándale un whatsapp a Raquel Salinas diciéndole que llego diez minutos tarde",
        "en": "Send Raquel Salinas a WhatsApp saying I'll be ten minutes late"}
TEXT = {"es": "llego diez minutos tarde", "en": "I'll be ten minutes late"}


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_silent_send_call_says_the_start_and_names_the_act(lang):
    case = {"id": f"silent-send-{lang}", "lang": lang, "phrase": SAID[lang], "screen": {"open": []},
            "widgets": {"contactos": P.DIRECTORY, "mensajeria": P.INBOX}, "connectors": ["whatsapp", "email"],
            "model": {"say": "", "tools": [{"name": "widget_data", "args": {
                "widget_id": "mensajeria", "action": "send_to",
                "payload": {"contact": "Raquel Salinas", "channel": "whatsapp", "text": TEXT[lang]}}}]},
            "expect": "talk"}
    out = th.run_case(case)
    from i18n import langs
    mute = tuple(langs.spec(lang).mute_lines)
    assert out.decision == "talk", out.decision          # V2-938: the send owner answers in the turn itself
    assert TEXT[lang] in out.reply and not any(m in out.reply for m in mute), out.reply   # the draft read back
