"""V2-623 → V2-928 — the orb lives in the bottom system bar, its swap is the FACE toggle, and memory moved upstairs.

V2-928 (operator, 2026-11-17): «desactivamos el orbe grande del ojo con el pulso, eso queda oculto. No se borra… el
botón que teníamos de subir o bajar en la barra… ahí podríamos poner un icono de una cara que activará o desactivará la
visualización de la representación física». The eye is HIDDEN, never deleted: the orb boots in the bar, the lid's
controls flank it, and the bar's swap shows/hides the agent's face (`#presence`), persisted across a reload.

The original V2-623 spec, kept for the bar's layout:

The operator's spec (2026-09-08): «move the left bar to bottom. orbe goes to center, left and right side
contains the open widgets and the other icons in the bar respectively. initially the hor bar orbe is
deactivated and we show the eye orbe. but if someone click the bar orbe swap icon, or the eye orbe new swap
icon, then the big orbe is hidden.» Plus: «quita el icono de la memoria del orbe. ponlo arriba a la derecha.»

The one rule only a BROWSER can check is the 4.19 lesson: there is ONE orb canvas, ever — swapping REPARENTS
the same element, and a canvas re-created inside a conditional renders blank with no error. So every case
here measures the rendered page: where the canvas's parent is, whether it has size, and what a real click
moves.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time

import pytest

ENGINE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

PREVIEW = '''
import sys; sys.path.insert(0, %r)
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from server import pages, i18n_api
app = FastAPI(); app.include_router(pages.router); app.include_router(i18n_api.router)
app.mount("/static", StaticFiles(directory=%r), name="static")
uvicorn.run(app, host="127.0.0.1", port=%d, log_level="critical")
'''

_STATE = """() => {
  const orb = document.getElementById('orb');
  const wrap = document.getElementById('orbwrap');
  const slot = document.querySelector('#wrail .wr-orbslot');
  const swap = document.querySelector('#wrail .wr-swap');
  const rail = document.querySelector('#wrail');
  const lid = [...document.querySelectorAll('.orbctl button')];
  const vis = el => { if (!el) return false; const r = el.getBoundingClientRect();
                      return r.width > 0 && r.height > 0 && getComputedStyle(el).display !== 'none'; };
  const rr = rail ? rail.getBoundingClientRect() : null;
  const orbR = orb ? orb.getBoundingClientRect() : null;
  return {
    barMode: document.body.classList.contains('hb-orb-bar'),
    orbParent: orb && orb.parentElement ? (orb.parentElement.classList[0] || orb.parentElement.tagName) : null,
    orbVisible: vis(orb),
    orbW: orbR ? Math.round(orbR.width) : 0,
    eyeChromeShown: vis(document.querySelector('#orbwrap .orbctl')),
    activityShown: !!wrap && getComputedStyle(document.getElementById('activity')).display !== 'none',
    slotShown: vis(slot),
    slotTag: slot ? slot.tagName : '',
    slotOff: slot ? slot.classList.contains('off') : null,
    slotTitle: slot ? slot.getAttribute('title') || '' : '',
    pwrFaceShown: (() => { const f = document.querySelector('#wrail .wr-orbpwr');
                           return !!f && getComputedStyle(f).visibility === 'visible'; })(),
    flankL: [...document.querySelectorAll('#wrail .wr-orbl button')].map(b => b.getAttribute('data-ctl')),
    flankR: [...document.querySelectorAll('#wrail .wr-orbr button')].map(b => b.getAttribute('data-ctl') || b.className.split(' ')[0]),
    swapShown: vis(swap), swapTitle: swap ? swap.getAttribute('title') || '' : '',
    rail: rr ? {top: Math.round(rr.top), bottom: Math.round(rr.bottom),
                left: Math.round(rr.left), w: Math.round(rr.width), h: Math.round(rr.height)} : null,
    lidCount: lid.length,
    lidTitles: lid.map(b => b.getAttribute('title') || ''),
    pwrSlot: lid.findIndex(b => (b.className || '').includes('pwr-')) + 1,
    memOnLid: lid.some(b => ((b.getAttribute('title') || '').toLowerCase().includes('memor'))),
    memBtn: !!document.getElementById('memBtn'),
    face: !!document.querySelector('#presence canvas'),
    faceBtnOn: !!(document.getElementById('faceBtn') || {classList:{contains:()=>false}}).classList.contains('on'),
    swapOn: !!swap && swap.classList.contains('on'),
    memBtnOn: !!(document.getElementById('memBtn') || {classList:{contains:()=>false}}).classList.contains('on'),
    // Stray TEXT nodes among the lid/flank buttons. Element.append(null) does not throw — it prints the
    // literal word "null" (the 2026-09-09 operator screenshot: seven of them beside the orb), so any
    // non-empty text directly inside these containers is a rendering bug, never content.
    strayText: (() => {
      const scopes = [document.querySelector('#orbwrap .orbctl'),
                      document.querySelector('#wrail .wr-orbl'),
                      document.querySelector('#wrail .wr-orbr')].filter(Boolean);
      let s = '';
      for (const sc of scopes) for (const n of sc.childNodes)
        if (n.nodeType === 3 && n.textContent.trim()) s += n.textContent.trim();
      return s;
    })(),
  };
}"""


def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


@pytest.fixture(scope="module")
def run():
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except Exception:  # pragma: no cover
        pytest.skip("playwright not installed")
    port = _free_port()
    proc = subprocess.Popen([sys.executable, "-c", PREVIEW % (ENGINE, os.path.join(ENGINE, "frontend"), port)],
                            cwd=ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close(); break
        except OSError:
            time.sleep(0.5)
    else:  # pragma: no cover
        proc.terminate(); pytest.skip("preview server never came up")
    time.sleep(1.0)
    yield f"http://127.0.0.1:{port}/"
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:  # pragma: no cover
        proc.kill()


def _boot(pg, url):
    pg.goto(url, wait_until="domcontentloaded")
    pg.wait_for_timeout(2200)
    pg.evaluate("() => document.querySelectorAll('.boot-ovl, .lang-onb, .lang-onb-veil').forEach(e=>e.remove())")
    pg.wait_for_timeout(300)


@pytest.fixture(scope="module")
def measured(run):
    from playwright.sync_api import sync_playwright
    out = {}
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = b.new_context(viewport={"width": 1280, "height": 800})
        pg = ctx.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        _boot(pg, run)
        out["eye"] = out["bar"] = pg.evaluate(_STATE)      # the eye is retired: the boot IS bar mode, face on
        out["boot_and_swap_errors"] = list(errors)

        # The bar's swap hides the face (a REAL click on the rendered button)…
        pg.evaluate("() => document.querySelector('#wrail .wr-swap').click()")
        pg.wait_for_timeout(400)
        out["face_off"] = pg.evaluate(_STATE)

        # …the choice survives a reload (the retry path: the bar's slot may mount after the orb)…
        _boot(pg, run)
        out["bar_reload"] = pg.evaluate(_STATE)

        # …and the same button brings the face back.
        pg.evaluate("() => document.querySelector('#wrail .wr-swap').click()")
        pg.wait_for_timeout(400)
        out["back"] = pg.evaluate(_STATE)

        # The memory button now lives in the TopBar; clicking it must flip its own on-state (the same
        # store.memOpen the orb's old lid button drove). Done LAST: the map's own fetches are not this
        # preview server's problem and must not poison the swap flow's error ledger above.
        pg.evaluate("() => document.getElementById('memBtn').click()")
        pg.wait_for_timeout(300)
        out["mem_after_click"] = pg.evaluate(_STATE)

        # V2-792 §9: the ⏻ face means STOPPED and nothing else. Measured the way a stopped agent really arrives on a
        # screen — the switch persisted off and the orb in the bar, then a load (this preview has no run switch).
        # (The guard keeps this preview's first-run takeover — it has no language chosen — from wiping the page.)
        pg.evaluate("() => { sessionStorage.setItem('hb_first_run_takeover', '1'); }")
        pg.evaluate("async () => { (await import('/static/app/core/store.js?v=2')).setPowerOff(true); }")
        pg.wait_for_timeout(500)
        out["bar_off"] = pg.evaluate(_STATE)
        b.close()
    return out


def test_the_eye_is_retired_and_the_orb_boots_in_the_bar_with_the_face_on(measured):
    """V2-928: the big eye is hidden (not deleted) — the ONE orb canvas rests in the bar, and the face is on."""
    e = measured["eye"]
    assert e["barMode"] and e["orbParent"] == "wr-orbslot" and e["orbVisible"], f"the orb must rest in the bar: {e}"
    assert not e["eyeChromeShown"], f"the eye chrome must stay hidden: {e}"
    assert e["swapShown"] and e["swapOn"] and e["face"], f"the face is on by default, its toggle lit: {e}"
    assert e["swapTitle"] and "." not in e["swapTitle"].split(" ")[0], f"raw i18n key on the toggle: {e['swapTitle']!r}"
    assert measured["boot_and_swap_errors"] == [], measured["boot_and_swap_errors"]


def test_the_bar_owns_the_bottom_edge(measured):
    """«move the left bar to bottom» — full width, bottom edge, a shallow band."""
    r = measured["eye"]["rail"]
    assert r and r["left"] <= 1 and r["w"] >= 1280 * 0.95, r
    assert r["bottom"] >= 799 and r["h"] < 80, r


def test_the_bar_swap_hides_the_face_and_leaves_the_orb_where_it_is(measured):
    """ONE canvas — measured by its PARENT and its rendered SIZE (the 4.19 lesson). Off means no face canvas at all."""
    b = measured["face_off"]
    assert not b["face"] and not b["swapOn"] and not b["faceBtnOn"], f"the face must be gone, both toggles off: {b}"
    assert b["barMode"] and b["orbParent"] == "wr-orbslot", f"hiding the face must not move the orb: {b}"
    assert b["orbVisible"] and 0 < b["orbW"] <= 60, f"the bar orb must render small and real: {b}"


def test_the_lid_controls_flank_the_bar_orb_three_a_side(measured):
    """Operator, 2026-09-08: «el orbe tiene que estar en el centro y a los lados tiene que haber los tres
    iconos a un lado y los tres al otro… el icono de arrancar y parar en el centro del orbe». mic·spk·cap
    left; robot·chat·swap right (reordered 2026-09-11, operator: immediately right of the orb comes the
    wake-word/activation-mode toggle, then chat, then the swap — the face toggle since V2-928); ⏻ does NOT travel — the
    slot IS the switch (the V2-124 mobile pattern): a BUTTON whose ⏻ face shows exactly while the agent is
    STOPPED (V2-792 §9, 2026-10-25: «starting» or «voice on another screen» wear the orb, never the ⏻)."""
    b = measured["bar"]
    assert b["flankL"] == ["mic", "spk", "cap"], f"left flank must be the three voice-side controls: {b['flankL']}"
    assert b["flankR"] == ["bot", "chat", "wr-swap"], f"right flank must be robot·chat·swap: {b['flankR']}"
    assert b["slotTag"] == "BUTTON", f"the slot must be clickable — it is the power switch: {b['slotTag']}"
    assert "pwr" not in b["flankL"] + b["flankR"], "⏻ must never sit beside the orb — it IS the orb's click"
    # This preview's agent is not stopped (it is starting): the orb shows, NOT the ⏻ face.
    assert not b["slotOff"] and not b["pwrFaceShown"], f"not stopped → the orb, never the ⏻ face: {b}"
    off = measured["bar_off"]
    assert off["slotOff"] and off["pwrFaceShown"], f"stopped → the ⏻ face over the (kept, hidden) canvas: {off}"
    assert b["slotTitle"] and "." not in b["slotTitle"].split(" ")[0], f"raw i18n key on the switch: {b['slotTitle']!r}"


def test_the_choice_survives_a_reload(measured):
    b = measured["bar_reload"]
    assert b["barMode"] and b["orbParent"] == "wr-orbslot" and b["orbVisible"], b
    assert not b["face"] and not b["swapOn"], f"a hidden face stays hidden after a reload: {b}"


def test_the_bar_swap_brings_the_face_back(measured):
    k = measured["back"]
    assert k["face"] and k["swapOn"] and k["faceBtnOn"], f"the face must come back, both toggles lit: {k}"
    assert k["barMode"] and k["orbParent"] == "wr-orbslot", k


def test_the_memory_control_moved_to_the_top_bar(measured):
    """«quita el icono de la memoria del orbe. ponlo arriba a la derecha» — and the lid keeps SEVEN slots with
    ⏻ at the apex (slot 4), because the arc's nth-child geometry is keyed by slot index."""
    e = measured["eye"]
    assert e["memBtn"], "the TopBar must carry the memory button now"
    assert not e["memOnLid"], f"the lid must NOT carry a memory control any more: {e['lidTitles']}"
    # V2-928: the eye is hidden, so its lid keeps only the swap and ⏻ while the other five flank the bar orb —
    # the seven controls are all still there (the eye can come back whole: hidden, not deleted).
    flanked = e["flankL"] + [c for c in e["flankR"] if c != "wr-swap"]
    assert e["lidCount"] + len(flanked) == 7, f"the seven controls must all survive: {e['lidTitles']} + {flanked}"
    assert measured["mem_after_click"]["memBtnOn"], "clicking the TopBar memory button must open the map"


def test_no_lid_move_ever_prints_the_word_null(measured):
    # 2026-09-09, operator screenshot: "nullnullnullnullnullnullnull" floating beside the orb. The first
    # applyOrbDock ran before the orb was in the document, byCtl() returned null seven times, and
    # Element.append(null) coerces each null to the TEXT "null" instead of throwing. The stray text nodes
    # then survive every later (correct) re-append. Measured across all four states so neither direction
    # of the swap can reintroduce it.
    for state in ("eye", "face_off", "bar_reload", "back"):
        stray = measured[state]["strayText"]
        assert stray == "", f"stray text printed among the lid/flank buttons in state '{state}': {stray!r}"
