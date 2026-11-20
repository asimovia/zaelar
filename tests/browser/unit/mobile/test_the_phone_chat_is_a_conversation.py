"""The phone's chat is a conversation, not a log (V2-876 rule 6, V2-877 #10).

Seen on the review account: the voice's wait-fillers («Un segundo…», «Sure…», «Let me search…») landed as bubbles, the
list did not follow the newest line, and a line typed with the agent stopped got no answer and no word why. The engine
already marks a filler (`kind:"filler"`, `voice/engine/speech/filler_audio.py`); the stream keeps that mark on the
line and the phone draws only replies and his own lines. And every label the phone shell asks `t()` for exists in
every pack — «ENERGY» showed in English under the Spanish shell because the ES value WAS the English word.

RENDERED: the real `services/sse.js` router, the old path's real writer (`services/wall-legacy.js`) and the real chat
wall component that the real `ChatSheet` mounts through the real bridge (INI-042 #49), at 393×852 with touch. What is
asserted is what the page SHOWS — the bubbles that are rendered — never a list in a store.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from tests.browser.unit.mobile.phone_page import ENGINE, PACK, open_phone, shot

# The page's ONE old-path writer: the bridge imports `./wall-legacy.js?v=1`, and a module is cached by its resolved
# URL — any other spelling is a second instance, blind to the wall.
SETUP = """
  window.__sse = await import('/frontend/app/services/sse.js?v=6');
  window.__legacy = (await import('/frontend/app/services/wall-legacy.js?v=1')).legacy;
  const { ChatSheet } = await import('/frontend/mobile/app/shell/ChatSheet.js?v=1');
  document.body.append(ChatSheet());
  window.__legacy.reset();
  window.__store.setChatOpen(true);
"""

# A bubble is a line the page RENDERS: in the list or right after it (the «⏻ off» note), and not display:none.
BUBBLES = """() => [...document.querySelectorAll('.zm-chat .zm-msgs > *, .zm-chat .zm-off-note')]
    .filter(e => e.getClientRects().length > 0).map(e => e.textContent.trim())"""


@pytest.fixture(scope="module")
def phone():
    with open_phone(SETUP) as pg:
        pg.wait_for_timeout(300)
        yield pg


def _bubbles(pg):
    return pg.evaluate(BUBBLES)


def test_a_filler_from_the_stream_leaves_no_bubble(phone):
    phone.evaluate("""() => {
        window.__legacy.reset();
        window.__legacy.pushChat({ role: 'you', text: '¿qué tiempo hace en Soria?' });
        window.__sse.routeEvent(null, { kind: 'filler', label: 'relleno', text: 'Un segundo…', role: 'assistant' });
        window.__legacy.pushAgentChat('En Soria hay 12 grados y sol.');
    }""")
    phone.wait_for_timeout(100)
    assert _bubbles(phone) == ["¿qué tiempo hace en Soria?", "En Soria hay 12 grados y sol."]
    kept = phone.evaluate("""() => [...document.querySelectorAll('.zm-chat .zm-msgs > [data-id]')]
        .filter(e => e.textContent.includes('Un segundo')).map(e => e.getClientRects().length)""")
    assert kept == [0], f"the filler is still a line of the wall (the desktop wall shows it): the phone does not draw it: {kept}"


def test_the_list_follows_the_newest_line_and_respects_a_reader(phone):
    phone.evaluate("""() => { window.__legacy.reset();
        for (let i = 0; i < 40; i++) window.__legacy.pushAgentChat('Line ' + i + ' ' + 'word '.repeat(30)); }""")
    phone.wait_for_timeout(200)
    gap = "() => { const l = document.querySelector('.zm-chat .zm-msgs'); return l.scrollHeight - l.scrollTop - l.clientHeight; }"
    assert phone.evaluate(gap) < 4, "the newest line is in view"
    shot(phone, "pr1-chat-follows")
    phone.evaluate("() => { const l = document.querySelector('.zm-chat .zm-msgs'); l.scrollTop = 0; l.dispatchEvent(new Event('scroll')); }")
    phone.evaluate("() => window.__legacy.pushAgentChat('A late line ' + 'word '.repeat(30))")
    phone.wait_for_timeout(200)
    assert phone.evaluate("() => document.querySelector('.zm-chat .zm-msgs').scrollTop") == 0, \
        "he scrolled up to read: a new line does not yank him down"
    phone.fill(".zm-chat .zm-compose input", "y mañana?")
    phone.press(".zm-chat .zm-compose input", "Enter")
    phone.wait_for_timeout(200)
    assert _bubbles(phone)[-1] == "y mañana?", "his typed line is on the wall, last"
    assert phone.evaluate(gap) < 4, "his own line brings the list down to it"


def test_a_line_sent_with_the_agent_off_says_the_agent_is_off(phone):
    phone.evaluate("() => { window.__legacy.reset(); window.__store.setPowerOff(true); }")
    phone.fill(".zm-chat .zm-compose input", "hola")
    phone.press(".zm-chat .zm-compose input", "Enter")
    phone.wait_for_timeout(150)
    # The note is no longer a row of the list (the list is the wall's, INI-042 #49): it sits right after it, so it is
    # still the last thing he reads, under his line.
    assert _bubbles(phone)[-2:] == ["hola", PACK["es"]["mobile.chat_off"]], _bubbles(phone)
    g = phone.evaluate("""() => { const n = document.querySelector('.zm-chat .zm-off-note').getBoundingClientRect();
        const l = document.querySelector('.zm-chat .zm-msgs').getBoundingClientRect();
        const c = document.querySelector('.zm-chat .zm-compose').getBoundingClientRect();
        return { noteTop: n.top, noteBottom: n.bottom, listBottom: l.bottom, compTop: c.top }; }""")
    assert g["listBottom"] <= g["noteTop"] + 1 and g["noteBottom"] <= g["compTop"] + 1, \
        f"the note is in sight, between the conversation and the composer: {g}"
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
