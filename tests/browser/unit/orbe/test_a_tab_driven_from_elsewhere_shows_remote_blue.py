"""A tab whose voice session is held elsewhere is NOT a fault (not the amber `stalled`) and NOT stopped.

(Until 2026-10-25 it showed the ⏻ in blinking remote-control blue; V2-792 §9 moved that state onto the orb.)

Operator, 2026-09-27, watching his own tab while an agent drove the engine remotely: the blinking ⏻ is right, and
blue is the colour of every remote-control indicator. Before this, «another session holds the voice» painted
`stalled` — the amber alarm meant for a dead agent — though nothing was broken.
"""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[4]
APP = ROOT / "frontend" / "app"


def _code(p):
    return "\n".join(s for s in (l.strip() for l in p.read_text(encoding="utf-8").splitlines())
                     if s and not s.startswith("//"))


def test_the_state_is_remote_while_another_session_holds_the_voice():
    store = _code(APP / "core" / "store.js")
    body = store[store.index("export const agentState"):store.index("export const agentLive")]
    assert 'if (remoteHeld()) return "remote";' in body
    assert body.index('return "live"') < body.index('return "remote"') < body.index('return "stalled"'), \
        "a live session wins; remote is decided before the stalled fallback"


def test_the_blocked_start_marks_it_and_a_real_start_clears_it():
    s = _code(APP / "services" / "session-lk.js")
    i = s.index('t("voice.session_open_other_tab")')
    blocked = s[i:s.index("_armRetry();", i)]
    assert "store.setRemoteHeld(true)" in blocked
    assert "store.setStarted(true); store.setRemoteHeld(false);" in s


def test_the_power_button_means_power_and_the_orb_says_the_voice_is_elsewhere():
    """V2-792 §9 (operator, 2026-10-25) replaced the blinking remote-blue ⏻: «voice elsewhere» wore a ⏻ face, and on
    the bar it was the SAME face as «stopped» — pressing it to switch the agent on stopped everything. The ⏻ now means
    power only (lilac while the agent runs, grey only when stopped); the state is the orb's: grey, the slashed mic."""
    css = (APP / "styles.css").read_text(encoding="utf-8")
    assert not re.search(r"\.orbic\.pwr-remote\{", css), "the ⏻ no longer has a remote face"
    orb = _code(APP / "components" / "Orb.js")
    assert 'store.agentState() === "remote" ? "live"' in orb, "a running agent whose voice is elsewhere is powered ON"
    assert 'store.screenState() === "secondary"' in orb and "orbsec" in orb, "the orb wears the secondary mark"
    assert re.search(r"\.orbsec\.show\{display:block\}", css)
    pal = (APP / "core" / "palette.css").read_text(encoding="utf-8")
    assert pal.count("--hb-remote:") >= 2, "the remote token stays for the other remote-control indicators"


def test_its_title_is_translated():
    for lang in ("es", "en"):
        b = json.loads((ROOT / "i18n" / "genesis" / lang / "ui.json").read_text(encoding="utf-8"))
        assert b.get("orb.power_remote"), lang
