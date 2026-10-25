"""Each screen shows its OWN state, the same on the desktop bar and the phone dock (V2-792 §9, node 4.271).

Operator, 2026-10-25, dictating on the phone while the desktop showed the ⏻ of a stopped agent: on the desktop,
«voice on another screen» wore the same ⏻ face as «stopped», and pressing it to switch the agent on STOPPED the whole
agent, phone included (measured on his Machine: three `run stop` from the desktop in two minutes). His spec:

  off        → the ⏻ in grey;                        a tap switches the agent ON (server first)
  holder     → the orb, grey;                        a tap switches it OFF
  speaking   → the orb, ORANGE (only here);          a tap switches it OFF
  secondary  → the orb, grey, the slashed mic over it, never orange;   a tap BRINGS THE VOICE HERE
  icons      → grey off/closed, lilac on/open; the mic and the speaker lilac only while really live on THIS screen.

Two real browsers (a 1280 desktop with the orb in the bar, a 390 phone) on one preview of the engine; every state is
set on the page's own store and READ from the rendered page — classes, computed colours, the orb canvas's own
pixels, and which request a tap sends. A source check cannot see a ⏻ face showing over the orb.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

from two_screens import TwoScreens  # noqa: E402

STATES = {
    "off": "s.setPowerOff(true); s.setRemoteHeld(false); s.setStarted(false); s.setBotSpeaking(false);",
    "secondary": "s.setPowerOff(false); s.setStarted(false); s.setRemoteHeld(true); s.setBotSpeaking(true);",
    "holder": "s.setPowerOff(false); s.setRemoteHeld(false); s.setStarted(true); s.setBotSpeaking(false);",
    "speaking": "s.setPowerOff(false); s.setRemoteHeld(false); s.setStarted(true); s.setBotSpeaking(true);",
}

SET = """async (code) => { const s = await import('/static/app/core/store.js?v=2'); s.setBootReady(true);
  s.setMicMuted && s.setMicMuted(false); s.setBotMuted(false); s.setChatOpen(true);
  new Function('s', code)(s); await new Promise(r => setTimeout(r, 1300)); return s.screenState(); }"""

# The orb canvas's own pixels: warm = clearly more red than blue in the brightest part of the disc.
WARM = """() => { const c = document.getElementById('orb'); if (!c || !c.width) return null;
  const x = c.getContext('2d'); const d = x.getImageData(0, 0, c.width, c.height).data; let r = 0, b = 0, n = 0;
  for (let i = 0; i < d.length; i += 4) { if (d[i + 3] > 200 && d[i] + d[i + 1] + d[i + 2] > 240) { r += d[i]; b += d[i + 2]; n++; } }
  return n ? (r - b) / n : null; }"""

COLOURS = """(sel) => { const css = getComputedStyle(document.documentElement);
  const probe = (v) => { const e = document.createElement('i'); e.style.color = `var(${v})`; document.body.appendChild(e);
    const c = getComputedStyle(e).color; e.remove(); return c; };
  const lilac = probe('--hb-accent'), grey = probe('--hb-muted-2');
  const out = {}; for (const [k, q] of Object.entries(sel)) { const e = document.querySelector(q);
    const c = e ? getComputedStyle(e).color : null; out[k] = c === lilac ? 'lilac' : c === grey ? 'grey' : c; }
  return out; }"""

DESK_READ = """() => { const slot = document.querySelector('#wrail .wr-orbslot');
  const vis = (e) => !!e && getComputedStyle(e).visibility !== 'hidden' && getComputedStyle(e).display !== 'none';
  return { state: slot && slot.dataset.state, pwrFace: vis(document.querySelector('#wrail .wr-orbpwr')),
           secMark: vis(document.querySelector('#wrail .wr-orbsec')),
           orbShown: vis(document.getElementById('orb')),
           pwrCtl: (document.querySelector('[data-ctl="pwr"]') || {}).className || '',
           eyeSec: (document.querySelector('.orbsec') || {}).className || '' }; }"""

PHONE_READ = """() => { const vis = (e) => !!e && !e.classList.contains('zm-hide') && getComputedStyle(e).display !== 'none';
  const orb = document.querySelector('.zm-orb');
  return { pwrFace: vis(document.querySelector('.zm-pwr')), orbBtn: vis(document.querySelector('.zm-orb-btn')),
           orbCls: orb ? orb.className : '', micSlash: !!document.querySelector('.zm-orb-mic.muted'),
           btnCls: (document.querySelector('.zm-orb-btn') || {}).className || '' }; }"""

TAP = """async (sel) => { window.__sent = []; const f = window.fetch;
  window.fetch = (u, o) => { window.__sent.push(String(u)); return f(u, o); };
  document.querySelector(sel).click(); await new Promise(r => setTimeout(r, 700));
  window.fetch = f; return window.__sent.filter(u => /\\/api\\/(session\\/|run)/.test(u)); }"""


@pytest.fixture(scope="module")
def seen():
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except Exception:  # pragma: no cover
        pytest.skip("playwright not installed")
    out = {"desk": {}, "phone": {}, "tap": {}}
    with TwoScreens(desk_init="localStorage.setItem('hb_orb_dock','bar');", spy=False) as ts:
        for name, code in STATES.items():
            for side, pg, read in (("desk", ts.desk, DESK_READ), ("phone", ts.phone, PHONE_READ)):
                got = pg.evaluate(SET, code)
                r = pg.evaluate(read)
                r["screenState"] = got
                r["warm"] = pg.evaluate(WARM)
                r["icons"] = pg.evaluate(COLOURS, {"mic": '[data-ctl="mic"]', "chat": '[data-ctl="chat"]',
                                                   "spk": '[data-ctl="spk"]'} if side == "desk"
                                         else {"mic": '.zm-ic[data-ctl="mic"]'})
                out[side][name] = r
        # what a tap on the centre SENDS, per state (the desktop bar slot and the phone orb / ⏻)
        for name in ("secondary", "holder", "off"):
            ts.desk.evaluate(SET, STATES[name])
            out["tap"][("desk", name)] = ts.desk.evaluate(TAP, "#wrail .wr-orbslot")
            ts.phone.evaluate(SET, STATES[name])
            out["tap"][("phone", name)] = ts.phone.evaluate(TAP, ".zm-pwr" if name == "off" else ".zm-orb-btn")
        out["errors"] = list(ts.errors)
    return out


@pytest.mark.parametrize("name", list(STATES))
def test_the_store_derives_the_screen_state(seen, name):
    assert seen["desk"][name]["screenState"] == name and seen["phone"][name]["screenState"] == name


def test_stopped_wears_the_grey_power_symbol_on_both(seen):
    d, p = seen["desk"]["off"], seen["phone"]["off"]
    assert d["pwrFace"] and not d["secMark"], d
    assert "off" in d["pwrCtl"].split(), d
    assert p["pwrFace"] and not p["orbBtn"], p


@pytest.mark.parametrize("name", ["secondary", "holder", "speaking"])
def test_a_running_agent_never_wears_the_power_symbol(seen, name):
    d, p = seen["desk"][name], seen["phone"][name]
    assert not d["pwrFace"] and d["orbShown"], (name, d)
    assert "on" in d["pwrCtl"].split(), f"the ⏻ is power: lilac while the agent runs ({name}): {d}"
    assert not p["pwrFace"] and p["orbBtn"], (name, p)


def test_the_secondary_screen_wears_the_slashed_mic_and_is_never_orange(seen):
    d, p = seen["desk"]["secondary"], seen["phone"]["secondary"]
    assert d["secMark"] and "show" in d["eyeSec"].split(), d
    assert p["micSlash"] and "talking" not in p["orbCls"].split(), p
    for side in (d, p):
        assert side["warm"] is None or side["warm"] < 30, f"the agent is speaking elsewhere; this orb stays grey: {side}"


def test_the_orb_is_orange_only_while_the_agent_talks_on_the_screen_that_holds_the_voice(seen):
    for side in ("desk", "phone"):
        hold, talk = seen[side]["holder"]["warm"], seen[side]["speaking"]["warm"]
        assert hold is not None and talk is not None, (side, hold, talk)
        assert talk > 40 and hold < 30, f"{side}: grey while quiet ({hold:.0f}), orange while talking ({talk:.0f})"


def test_icons_are_lilac_only_when_really_on_here(seen):
    d = seen["desk"]
    assert d["holder"]["icons"]["mic"] == "lilac" and d["holder"]["icons"]["spk"] == "lilac", d["holder"]["icons"]
    for st in ("secondary", "off"):
        assert d[st]["icons"]["mic"] == "grey" and d[st]["icons"]["spk"] == "grey", (st, d[st]["icons"])
        assert d[st]["icons"]["chat"] == "lilac", f"an OPEN chat is lilac whatever the agent does ({st})"
    p = seen["phone"]
    assert p["holder"]["icons"]["mic"] == "lilac" and p["secondary"]["icons"]["mic"] == "grey", p


def test_a_tap_on_the_secondary_centre_brings_the_voice_and_never_stops_anything(seen):
    for side in ("desk", "phone"):
        sent = seen["tap"][(side, "secondary")]
        assert any("/api/session/steal" in u for u in sent), (side, sent)
        assert not any("/api/run/stop" in u for u in sent), f"{side}: a tap on «voice elsewhere» stopped the agent"


def test_a_tap_on_the_holder_stops_and_on_the_stopped_starts_the_server_first(seen):
    for side in ("desk", "phone"):
        assert any("/api/run/stop" in u for u in seen["tap"][(side, "holder")]), side
        sent = seen["tap"][(side, "off")]
        # FIRST — before the session's own look at the server (GET /api/run) or its claim on the voice lock.
        assert sent and "/api/run/start" in sent[0], f"{side}: the server's switch goes FIRST: {sent}"


def test_no_page_error(seen):
    assert not seen["errors"], seen["errors"]
