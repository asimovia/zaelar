"""The agent's voice level holds where the platform ignores an element's volume (iOS WebKit) — V2-930 gain, node 4.573.

The `.mjs` beside this file pins the decision and the wiring over a recorded graph. Here the SAME path runs on a real
Web Audio graph in Chromium, with the element's volume made as deaf as iOS makes it: a tone stands in for the remote
voice track, and what leaves for the speakers is measured — 30 % is ~0.3 of 100 %, the 🔊 muted is silence, and the
element is held muted (one voice, not two). Plus the wiring the `.mjs` cannot see: both sessions route by the door
and the unlock resumes the context.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from tests.browser.unit.mobile.phone_page import open_phone

SCRIPT = Path(__file__).with_name("test_the_voice_level_holds_where_the_element_ignores_it.mjs")
APP = Path(__file__).resolve().parents[4] / "frontend" / "app"


def _code(p: Path) -> str:
    return "\n".join(s for s in (l.strip() for l in p.read_text(encoding="utf-8").splitlines())
                     if s and not s.startswith("//"))


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_gain_route_holds_the_level_and_the_speaker():
    r = subprocess.run(["node", str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")


def test_both_sessions_route_the_voice_by_the_door():
    for rel in ("services/session-lk.js", "services/session.js"):
        s = _code(APP / rel)
        assert "vol.routesOut())" in s, f"{rel}: the bot track is attached without asking where its voice leaves"
        i = s.index("export async function unlockAudio()")
        assert "audio.resumeContext()" in s[i:i + 200], f"{rel}: the unlock must resume the gain's context first"


# The element made as deaf as iOS WebKit (its volume reads back 1), a tone as the remote voice, and a probe on what
# the gain sends to the speakers.
SETUP = """
  localStorage.removeItem('hb_bot_volume'); localStorage.setItem('hb_bot_muted', '0');
  const d = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, 'volume');
  Object.defineProperty(HTMLMediaElement.prototype, 'volume', { configurable: true, get() { return 1; }, set(_) {} });
  window.__probe = null;
  const conn = AudioNode.prototype.connect;
  AudioNode.prototype.connect = function (n, ...r) {
    if (this instanceof GainNode && n instanceof AudioDestinationNode) {
      window.__probe = this.context.createAnalyser(); window.__probe.fftSize = 2048; conn.call(this, window.__probe);
    }
    return conn.call(this, n, ...r);
  };
  const toneCtx = new AudioContext();
  const tone = (f) => { const o = toneCtx.createOscillator(); o.frequency.value = f; const dst = toneCtx.createMediaStreamDestination();
                        o.connect(dst); o.start(); return dst.stream; };
  window.__audio = await import('/frontend/app/services/audio.js?v=2');
  window.__volume = await import('/frontend/app/services/volume.js?v=1');
  window.__store = await import('/frontend/app/core/store.js?v=2');
  const session = await import('/frontend/app/services/session.js?v=3');
  const a = document.createElement('audio'); a.id = 'botaudio'; document.body.append(a); session.attachBotAudio(a);
  window.__audio.initMic(tone(220));
  const voice = tone(440); a.srcObject = voice;
  window.__audio.attachBot(voice, window.__volume.routesOut());
  await toneCtx.resume(); await window.__audio.resumeContext();
"""

RMS = """async () => {
  await new Promise(r => setTimeout(r, 250));
  const b = new Float32Array(window.__probe.fftSize); window.__probe.getFloatTimeDomainData(b);
  let s = 0; for (const v of b) s += v * v; return Math.sqrt(s / b.length);
}"""


def test_what_leaves_for_the_speakers_follows_the_level_on_a_real_graph():
    with open_phone(SETUP) as pg:
        pg.wait_for_timeout(300)
        assert pg.evaluate("() => window.__volume.routesOut()") is True
        assert pg.evaluate("() => window.__audio.botOutRouted()") is True
        assert pg.evaluate("() => document.querySelector('#botaudio').muted") is True, "the element must stay silent"
        pg.wait_for_function(f"({RMS})().then(v => v > 0.01)", timeout=5000)   # the tone's first frames take a moment
        full = pg.evaluate(RMS)
        assert full > 0.2, f"the voice must reach the speakers at the default level: rms {full}"
        pg.evaluate("() => window.__volume.setLevel(30)")
        low = pg.evaluate(RMS)
        assert abs(low / full - 0.3) < 0.05, f"30 % must be ~0.3 of full: {low} / {full}"
        pg.evaluate("() => window.__volume.setLevel(100)")
        assert abs(pg.evaluate(RMS) / full - 1) < 0.05, "100 % is full again"
        pg.evaluate("() => window.__store.setBotMuted(true)")
        assert pg.evaluate(RMS) < 1e-4, "the 🔊 muted is silence"
        pg.evaluate("() => window.__store.setBotMuted(false)")
        assert abs(pg.evaluate(RMS) / full - 1) < 0.05, "un-muted, his level again"
        assert not pg._errors, pg._errors
