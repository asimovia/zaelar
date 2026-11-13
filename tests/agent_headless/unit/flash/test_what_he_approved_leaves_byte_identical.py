"""What he approved leaves byte-identical — no door rewrites a send between his yes and the card (V2-903 P1-1).

An English session; «send Avery: ya estamos, nos vemos mañana a las ocho». The send door used to judge every
outgoing text with a ~70-word es/en table and, when it differed from the session language, had a model translate it
AFTER his yes — so Avery received English words he never said nor saw (CRIT-T2e: his words, in order). The card's
door now receives exactly the payload the turn retained or he confirmed, in any language, on both paths that reach
it: the linear send task and the confirmed irreversible act (`receipt=True`).

Disarm: put a rewrite of `payload["text"]` back between the door's entry and `widgets.dispatch_tag` — every case
here goes red (the translator below is a live fake that WOULD answer in English).
"""
from __future__ import annotations

import asyncio

import pytest

_SPANISH = "ya estamos, nos vemos mañana a las ocho"
_JAPANESE = "もう着いたよ、明日八時に会おう"


@pytest.fixture
def door(monkeypatch):
    """The card's door with the world faked: an English session, a model that would translate if anyone asked it,
    and a card that records the payload it receives."""
    import widgets
    from i18n import langs
    from nucleo.flash import data_ops, spoken_lang
    from nucleo.llm import fast_client
    monkeypatch.setattr(langs, "current_code", lambda: "en")
    asked = []

    class _WouldTranslate:
        async def complete(self, messages, **_kw):
            asked.append(messages[-1]["content"])
            return "We're here, see you tomorrow at eight."
    monkeypatch.setattr(fast_client, "FastClient", _WouldTranslate)
    monkeypatch.setattr(spoken_lang, "LIVE", True)
    got = []

    async def _card(tag, body):
        got.append(((body.get("data") or {}).get("payload") or {}).copy())
        return {"ok": True, "queued": True}
    monkeypatch.setattr(widgets, "dispatch_tag", _card)

    def run(payload, *, receipt=False):
        got.clear()
        asyncio.run(data_ops.dispatch_and_report("mensajeria", "send_to", dict(payload), receipt=receipt,
                                                 text=f"send Avery: {payload.get('text')}"))
        assert got, "the card's door was never reached"
        return got[-1], asked
    return run


@pytest.mark.parametrize("receipt", [False, True], ids=["linear-send", "confirmed-yes"])
@pytest.mark.parametrize("text", [_SPANISH, _JAPANESE, "Running late, sorry!"], ids=["es", "ja", "en"])
def test_the_card_receives_his_words_byte_for_byte(door, text, receipt):
    payload = {"contact": "Avery", "text": text}
    sent, asked = door(payload, receipt=receipt)
    assert sent.get("text") == text, f"the text that leaves was rewritten: {sent.get('text')!r}"
    assert sent.get("text").encode() == text.encode()
    assert not asked, f"a model was asked about a text he already approved: {asked}"


def test_the_send_door_has_no_language_rewrite_left():
    """The retired door stays retired: nothing in the module the send path imports offers it."""
    from nucleo.flash import spoken_lang
    assert not hasattr(spoken_lang, "in_session_language")
    with pytest.raises(ImportError):
        __import__("nucleo.flash.outgoing_lang")
