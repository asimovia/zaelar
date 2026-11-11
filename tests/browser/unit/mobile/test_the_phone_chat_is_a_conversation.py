"""The phone's chat is a conversation, not a log (V2-876 rule 6, V2-877 #10).

Seen on the review account: the voice's wait-fillers («Un segundo…», «Sure…», «Let me search…») landed as bubbles, the
list did not follow the newest line, and a line typed with the agent stopped got no answer and no word why. The engine
already marks a filler (`kind:"filler"`, `voice/engine/speech/filler_audio.py`); the stream now keeps that mark on the
row and the phone draws only replies and his own lines. And every label the phone shell asks `t()` for exists in
every pack — «ENERGY» showed in English under the Spanish shell because the ES value WAS the English word.

RENDERED: the real `services/sse.js` router, the real store and the real `ChatSheet`, at 393×852 with touch.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from tests.browser.unit.mobile.phone_page import ENGINE, PACK, open_phone, shot

SETUP = """
  window.__sse = await import('/frontend/app/services/sse.js?v=6');
  const { ChatSheet } = await import('/frontend/mobile/app/shell/ChatSheet.js?v=1');
  document.body.append(ChatSheet());
  window.__store.setChatMsgs([]);
  window.__store.setChatOpen(true);
"""


@pytest.fixture(scope="module")
def phone():
    with open_phone(SETUP) as pg:
        pg.wait_for_timeout(300)
        yield pg


def _bubbles(pg):
    return pg.evaluate("() => [...document.querySelectorAll('.zm-chat .zm-msgs .zm-msg')].map(e => e.textContent)")


def test_a_filler_from_the_stream_leaves_no_bubble(phone):
    phone.evaluate("""() => {
        window.__store.setChatMsgs([]);
        window.__store.pushChat({ role: 'you', text: '¿qué tiempo hace en Soria?' });
        window.__sse.routeEvent(null, { kind: 'filler', label: 'relleno', text: 'Un segundo…', role: 'assistant' });
        window.__store.pushAgentChat('En Soria hay 12 grados y sol.');
    }""")
    phone.wait_for_timeout(100)
    assert _bubbles(phone) == ["¿qué tiempo hace en Soria?", "En Soria hay 12 grados y sol."]
    assert any(m.get("kind") == "filler" for m in phone.evaluate("() => window.__store.chatMsgs()")), \
        "the filler is still in the history (the desktop wall shows it): the phone does not draw it"


def test_the_list_follows_the_newest_line_and_respects_a_reader(phone):
    phone.evaluate("""() => { window.__store.setChatMsgs([]);
        for (let i = 0; i < 40; i++) window.__store.pushAgentChat('Line ' + i + ' ' + 'word '.repeat(30)); }""")
    phone.wait_for_timeout(200)
    gap = "() => { const l = document.querySelector('.zm-chat .zm-msgs'); return l.scrollHeight - l.scrollTop - l.clientHeight; }"
    assert phone.evaluate(gap) < 4, "the newest line is in view"
    shot(phone, "pr1-chat-follows")
    phone.evaluate("() => { const l = document.querySelector('.zm-chat .zm-msgs'); l.scrollTop = 0; l.dispatchEvent(new Event('scroll')); }")
    phone.evaluate("() => window.__store.pushAgentChat('A late line ' + 'word '.repeat(30))")
    phone.wait_for_timeout(200)
    assert phone.evaluate("() => document.querySelector('.zm-chat .zm-msgs').scrollTop") == 0, \
        "he scrolled up to read: a new line does not yank him down"
    phone.fill(".zm-chat .zm-compose input", "y mañana?")
    phone.press(".zm-chat .zm-compose input", "Enter")
    phone.wait_for_timeout(200)
    assert phone.evaluate(gap) < 4, "his own line brings the list down to it"


def test_a_line_sent_with_the_agent_off_says_the_agent_is_off(phone):
    phone.evaluate("() => { window.__store.setChatMsgs([]); window.__store.setPowerOff(true); }")
    phone.fill(".zm-chat .zm-compose input", "hola")
    phone.press(".zm-chat .zm-compose input", "Enter")
    phone.wait_for_timeout(150)
    assert _bubbles(phone)[-1] == PACK["es"]["mobile.chat_off"]
    shot(phone, "pr1-chat-agent-off")
    phone.evaluate("() => window.__store.setPowerOff(false)")
    phone.wait_for_timeout(100)
    assert PACK["es"]["mobile.chat_off"] not in _bubbles(phone), "switched on, the note goes"


def test_every_label_the_phone_shell_asks_for_exists_in_every_pack():
    keys = set()
    for p in pathlib.Path(ENGINE, "frontend/mobile").rglob("*.js"):
        keys |= set(re.findall(r'\bt\(\s*"([\w.\-]+)"\s*[,)]', p.read_text(encoding="utf-8")))
    assert len(keys) > 40, "the scan found the shell's labels"
    for lang, pack in PACK.items():
        assert not sorted(k for k in keys if not str(pack.get(k) or "").strip()), f"labels missing from {lang}"


def test_the_energy_row_speaks_the_shell_language():
    """V2-877 #3: the ES pack carried the English word; the row is uppercased by CSS, so it read «ENERGY»."""
    assert PACK["es"]["energy.label"] != PACK["en"]["energy.label"]


def test_no_script_error(phone):
    assert not phone._errors, phone._errors
