"""ONE veil, one face at a time, and one press that activates everything here (V2-881). Rendered.

The operator (2026-11-11), measured on his agent: with it asleep he pressed ⏻ — the sleep veil lifted, a SECOND veil
appeared saying «the agent is stopped», and he had to press ⏻ again. There were two components (DormantVeil for the
engine asleep / the voice elsewhere, PowerVeil for stopped / in transit). Now `components/Veil.js` is the only one:
  * one face, by priority — stopped by him (`off`, and `pausing` on its way there) over asleep (`sleep`), asleep over
    `starting`, and `moved` (the voice on another screen) only when nothing else applies;
  * its button does it all in one gesture, on the screen where it was pressed: wake the engine (`reactivate`),
    and once the stream answered switch the agent on (`setPower`) and bring the voice here (`claimVoice`);
  * the stopped face shades the cards under the rail, the top bar and the orb; the black faces cover everything.

The doors are served as recording stubs, so the test clicks the REAL button of the REAL component and reads which
doors were called and in what order. Disarm (in this file): Veil.js served without its `setPower` call — the press
check must fail. The test asserts the mutation landed before measuring.
"""
from __future__ import annotations

import json
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from tests.waiting import until_sync

ENGINE = Path(__file__).resolve().parents[4]
FRONT = ENGINE / "frontend"
VEIL = FRONT / "app/components/Veil.js"
SHARED_CSS = FRONT / "app/core/shared-surfaces.css"
_EN = json.loads((ENGINE / "i18n/genesis/en/ui.json").read_text(encoding="utf-8"))
POWER_DOOR = "await setPower(false, where);"
#: `.fw-wrap` (styles.css): the one layer above the veil — test_the_feedback_button_is_never_hidden holds it on top.
FEEDBACK_LAUNCHER = 101000

STUBS = {
    "**/services/presence.js*": "export function reactivate() { (window.__doors ||= []).push('wake'); }",
    "**/services/power.js*": "export function setPower(off, where) { (window.__doors ||= []).push('power:' + off + ':' + where);"
                             " return Promise.resolve(); }",
    "**/services/session.js*": "export async function claimVoice(where) { (window.__doors ||= []).push('voice:' + where);"
                               " return true; }",
}


def _listening(port: int) -> bool:
    try:
        socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
        return True
    except OSError:
        return False


@pytest.fixture(scope="module")
def browser_and_port():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    until_sync(lambda: _listening(port), "the static server to accept connections", timeout_s=10)
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            yield b, port
            b.close()
    finally:
        srv.terminate(); srv.wait(timeout=10)


def _serve(body: str):
    return lambda route: route.fulfill(status=200, content_type="text/javascript", body=body)


def _page(browser, port, veil_src: str | None = None):
    pg = browser.new_page(viewport={"width": 1280, "height": 800})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
    pg.route("**/api/i18n/bundle/*", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps({"strings": _EN})))
    for pattern, body in STUBS.items():
        pg.route(pattern, _serve(body))
    if veil_src is not None:
        pg.route("**/components/Veil.js*", lambda r: r.fulfill(status=200, content_type="text/javascript", body=veil_src))
    pg.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
    pg.evaluate("""async () => {
        localStorage.clear();
        for (const h of ['/frontend/app/core/palette.css', '/frontend/app/core/shared-surfaces.css']) {
          const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = h; document.head.append(l); }
        const i18n = await import('/frontend/app/core/i18n.js?v=1');
        await i18n.loadBundle('en'); if (i18n.applyLang) await i18n.applyLang('en');
        window.__store = await import('/frontend/app/core/store.js?v=2');
        const v = await import('/frontend/app/components/Veil.js?v=1');
        document.body.append(v.Veil());
        window.__store.setBootReady(true);
    }""")
    pg._errors = errors
    return pg


FACE = """() => { const v = document.querySelector('.zv'); const btn = v.querySelector('.zv-btn.primary');
  return { cls: v.className, title: v.querySelector('.zv-title').textContent, btn: btn.textContent,
           shown: getComputedStyle(v).display !== 'none', doors: window.__doors || [] }; }"""


def _press_while_asleep_and_stopped(pg):
    """His case: the agent stopped AND the engine asleep AND the voice elsewhere — every face at once."""
    pg.evaluate("""() => { const s = window.__store;
        s.setPowerOff(true); s.setDormant({ face: 'sleep', waking: false }); s.setRemoteHeld(true); }""")
    f = pg.evaluate(FACE)
    assert f["shown"] and " off" in f["cls"], f"stopped by him wins over asleep and moved: {f}"
    assert f["title"] == _EN["veil.off_title"], f
    pg.click(".zv .zv-btn.primary")
    pg.wait_for_timeout(150)
    early = pg.evaluate(FACE)["doors"]
    pg.evaluate("() => window.__store.setDormant({ face: '', waking: false })")   # the stream answered: awake
    until_sync(lambda: len(pg.evaluate(FACE)["doors"]) >= 3, "the press to reach every door", timeout_s=2)
    return early, pg.evaluate(FACE)["doors"]


def test_one_press_wakes_switches_on_and_brings_the_voice_here(browser_and_port):
    b, port = browser_and_port
    pg = _page(b, port)
    early, doors = _press_while_asleep_and_stopped(pg)
    assert early == ["wake"], f"a sleeping engine is woken first, and nothing is sent to it before it answers: {early}"
    assert doors == ["wake", "power:false:veil", "voice:veil"], f"one press, three doors, in order: {doors}"
    assert not pg._errors, pg._errors
    pg.close()


def test_a_press_that_drops_a_door_is_caught(browser_and_port):
    src = VEIL.read_text(encoding="utf-8")
    assert POWER_DOOR in src, "the door this disarm drops is gone — update the disarm"
    disarmed = src.replace(POWER_DOOR, "")
    assert POWER_DOOR not in disarmed
    b, port = browser_and_port
    pg = _page(b, port, veil_src=disarmed)
    pg.evaluate("""() => { const s = window.__store;
        s.setPowerOff(true); s.setDormant({ face: 'sleep', waking: false }); }""")
    pg.click(".zv .zv-btn.primary")
    pg.evaluate("() => window.__store.setDormant({ face: '', waking: false })")
    pg.wait_for_timeout(400)
    doors = pg.evaluate(FACE)["doors"]
    assert doors != ["wake", "power:false:veil", "voice:veil"], f"the disarm stayed green: {doors}"
    pg.close()


def test_one_face_at_a_time_by_priority(browser_and_port):
    b, port = browser_and_port
    pg = _page(b, port)
    seq = pg.evaluate("""() => { const s = window.__store, out = [];
        const face = () => { const v = document.querySelector('.zv');
          return v.classList.contains('on') ? [...v.classList].filter(c => c !== 'zv' && c !== 'on').join(' ') : ''; };
        s.setDormant({ face: 'sleep', waking: false }); s.setRemoteHeld(true); s.setPowerOff(true); out.push(face());
        s.setPowerOff(false); out.push(face());
        s.setDormant({ face: '', waking: false }); out.push(face());
        document.querySelectorAll('.zv .zv-btn')[1].click(); out.push(face());
        s.setRemoteHeld(false); out.push(face());
        return out; }""")
    assert seq == ["off", "sleep", "moved", "", ""], f"off > sleep > moved, «continue here with text» lifts it: {seq}"
    assert pg.evaluate("() => document.querySelectorAll('.zv').length") == 1
    pg.close()


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_pure_face_function():
    src = VEIL.read_text(encoding="utf-8")
    fn = src[src.index("export function veilFace"):src.index("/** Resolves once the engine is awake")]
    script = fn.replace("export function", "function") + """
const S = { face: "sleep" }, N = { face: "" };
const cases = [
  [["off", S, true, true, false], "off"], [["pausing", S, true, true, false], "pausing"],
  [["live", S, true, true, false], "sleep"], [["starting", S, false, true, false], "sleep"],
  [["starting", N, false, true, false], "starting"], [["starting", N, false, false, false], ""],
  [["remote", N, true, true, false], "moved"], [["remote", N, true, true, true], ""],
  [["live", N, false, true, false], ""], [["stalled", N, false, true, false], ""]];
for (const [args, want] of cases) { const got = veilFace(...args);
  if (got !== want) { console.error(JSON.stringify(args), got, want); process.exit(1); } }
"""
    r = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr


def _z(src: str, selector: str) -> int:
    m = re.search(re.escape(selector) + r"\{[^}]*?z-index:(\d+)", src)
    assert m, f"no z-index for {selector}"
    return int(m.group(1))


def test_the_stopped_face_leaves_the_rail_and_the_orb_above_and_the_black_faces_cover_everything():
    shared = SHARED_CSS.read_text(encoding="utf-8")
    css = (FRONT / "app/styles.css").read_text(encoding="utf-8")
    shaded, black = _z(shared, ".zv"), _z(shared, ".zv.sleep,.zv.moved")
    stage = _z((FRONT / "app/widgets/desktop.js").read_text(encoding="utf-8"), ".hb-stage")
    rail = _z((FRONT / "app/components/WidgetRail.js").read_text(encoding="utf-8"), "#wrail")
    assert stage < shaded < rail < _z(css, ".orbwrap") and shaded < _z(css, ".trw")
    assert "body:has(.zv.on.sleep,.zv.on.moved) #desk{transform:none;z-index:%d}" % black in shared, \
        "a black face lifts #desk (where the veil lives on the desktop) above everything"
    for p in [*FRONT.joinpath("app").rglob("*.css"), *FRONT.joinpath("app").rglob("*.js"),
              *FRONT.joinpath("mobile").rglob("*.css"), *FRONT.joinpath("mobile").rglob("*.js")]:
        for z in re.findall(r"z-index:\s*(\d+)", p.read_text(encoding="utf-8", errors="ignore")):
            if int(z) == FEEDBACK_LAUNCHER or (p == SHARED_CSS and int(z) == black):
                continue
            assert int(z) < black, f"{p} has a layer at z-index {z}, above the black veil ({black})"


def test_both_shells_mount_the_one_veil_and_the_two_old_ones_are_gone():
    desk = (FRONT / "app/core/system-surfaces.js").read_text(encoding="utf-8")
    phone = (FRONT / "mobile/app/shell/mobile-surfaces.js").read_text(encoding="utf-8")
    assert re.search(r'id: "veil",\s*comp: Veil,\s*target: "desk"', desk)
    assert re.search(r'id: "veil",\s*comp: Veil,\s*target: "body".*shared: true', phone)
    for gone in ("DormantVeil", "PowerVeil"):
        assert not (FRONT / f"app/components/{gone}.js").exists()
        assert gone not in desk and gone not in phone
    assert ".power-veil" not in (FRONT / "app/styles.css").read_text(encoding="utf-8")
    assert ".dz-" not in SHARED_CSS.read_text(encoding="utf-8")


@pytest.mark.parametrize("lang", ["en", "es"])
def test_every_line_of_the_veil_is_in_the_ui_pack(lang):
    pack = json.loads((ENGINE / f"i18n/genesis/{lang}/ui.json").read_text(encoding="utf-8"))
    used = set(re.findall(r'"((?:veil|dormant)\.[a-z_]+)"', VEIL.read_text(encoding="utf-8")))
    assert len(used) >= 13, used
    missing = sorted(k for k in used if not pack.get(k))
    assert not missing, missing


def test_the_sleep_face_is_a_blurred_veil_with_zs_and_one_click_wakes_it(browser_and_port):
    b, port = browser_and_port
    pg = _page(b, port)
    pg.evaluate("() => window.__store.setDormant({ face: 'sleep', waking: false })")
    st = pg.evaluate("""() => { const v = document.querySelector('.zv');
        return { blur: getComputedStyle(v).backdropFilter, zs: v.querySelectorAll('.zv-zs span').length,
                 title: v.querySelector('.zv-title').textContent, shown: getComputedStyle(v).display !== 'none' }; }""")
    assert st["shown"] and "blur" in st["blur"] and st["zs"] == 3, st
    assert st["title"] == _EN["dormant.sleeping"] == "Sleeping", st
    pg.mouse.click(40, 40)    # anywhere on the screen, not only the button
    until_sync(lambda: pg.evaluate("() => window.__doors || []")[:1] == ["wake"], "the click to wake the engine", timeout_s=2)
    pg.close()
