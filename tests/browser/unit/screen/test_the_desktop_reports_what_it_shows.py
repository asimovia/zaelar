"""The windowed desk's screen document equals what the desk SHOWS (V2-907 T7, node 4.542).

Executed on the REAL `desktop.js` + `desktop-screen.js` + `screen-reporter.js` in Chromium, the engine's orders driven
through the REAL `services/sse.js` (`routeEvent`, with a `seq` as `canvas.apply` stamps it), his hand through the
card's own buttons and a pointer on it. After every step the last document the desk POSTed to `/api/screen/report`
is compared with the DOM read independently (a minimised card by its class, the front by its computed z-index, a
covered card by sampling what the browser hit-tests at its points), and every order's answer is checked.
Parametrized over every app in `widgets/*/manifest.json`. Disarm: the adapter reports a minimised card as `front`.
"""
from __future__ import annotations

import json
import pathlib
import socket
import subprocess
import sys

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

from tests.waiting import port_listening

ENGINE = pathlib.Path(__file__).resolve().parents[4]
MANIFESTS = {p.parent.name: json.loads(p.read_text(encoding="utf-8"))
             for p in sorted((ENGINE / "widgets").glob("*/manifest.json"))}
APPS = sorted(MANIFESTS)
_STUB_WIDGET = "export function render(el){ el.textContent = 'mounted'; }\nexport default { render };\n"
ADAPTER = ENGINE / "frontend" / "app" / "widgets" / "desktop-screen.js"
_MIN_GUARD = 'if (c.classList.contains("hb-minned")) return "min";'

# What the desk shows, read from the DOM and never from the adapter.
_TRUTH = """() => {
  const desk = window.__desk, out = {};
  const cards = [...document.querySelectorAll('#stage .hb-win[data-wid]')].filter(c => desk.wins.has(c.dataset.wid));
  const shown = cards.filter(c => !c.classList.contains('hb-minned'));
  const z = c => parseInt(getComputedStyle(c).zIndex, 10) || 0;
  const top = shown.slice().sort((a, b) => z(b) - z(a))[0];
  const seen = c => { const r = c.getBoundingClientRect(); let n = 0;
    for (const fx of [0.1, 0.5, 0.9]) for (const fy of [0.1, 0.5, 0.9]) {
      const e = document.elementFromPoint(r.left + r.width * fx, r.top + r.height * fy);
      if (e && e.closest('.hb-win') === c) n++; }
    return n; };
  for (const c of cards) {
    const id = c.dataset.wid;
    out[id] = c.classList.contains('hb-minned') ? 'min' : c === top ? 'front' : seen(c) ? 'visible' : 'behind';
    if (c._restore) out[id] += '+max';
  }
  if (desk._actId && !desk.wins.has(desk._actId) && document.getElementById('activity').childElementCount)
    out[desk._actId] = 'visible';
  return out;
}"""


def _free_port() -> int:
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    return port


@pytest.fixture(scope="module")
def browser():
    port = _free_port()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"], cwd=ENGINE,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    port_listening(port)
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            b._hb_port = port
            yield b
            b.close()
    finally:
        srv.terminate(); srv.wait(timeout=10)


def _page(browser, adapter_src: str | None = None):
    port = browser._hb_port
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    reports: list[dict] = []

    def _json(route, payload):
        route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

    def _report(route):
        reports.append(json.loads(route.request.post_data or "{}"))
        _json(route, {"ok": True})

    widgets = [{"id": i, "name": i, **{k: m[k] for k in ("transient", "fullscreen") if k in m}}
               for i, m in MANIFESTS.items()]
    page.route("**/widgets", lambda r: _json(r, {"widgets": widgets}))
    page.route("**/widgets/registry", lambda r: _json(r, {"registry": []}))
    page.route("**/widgets/*/widget.js*", lambda r: r.fulfill(status=200, content_type="application/javascript",
                                                               body=_STUB_WIDGET))
    page.route("**/widgets/*/data*", lambda r: _json(r, {}))
    page.route("**/widgets/*/aliases*", lambda r: _json(r, {"ok": True, "aliases": []}))
    page.route("**/api/**", lambda r: _json(r, {}))
    page.route("**/api/screen/report", _report)
    if adapter_src is not None:
        page.route("**/frontend/app/widgets/desktop-screen.js*", lambda r: r.fulfill(
            status=200, content_type="application/javascript", body=adapter_src))
    page.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
    page.evaluate("""async () => {
        document.body.innerHTML = '<div id="stage"></div><div id="activity"></div>';
        const m = await import('/frontend/app/widgets/desktop.js?v=1');
        window.__sse = await import('/frontend/app/services/sse.js?v=6');
        window.__desk = new m.Desktop(document.getElementById('stage'));
    }""")
    page.wait_for_timeout(300)
    return page, reports, errors


def _order(page, label, id_="", seq=0, **extra):
    page.evaluate("(d) => window.__sse.routeEvent(window.__desk, d)",
                  {"kind": "widget", "label": label, **({"id": id_} if id_ else {}), "seq": seq, "src": "brain", **extra})
    page.wait_for_timeout(330)


def _doc_view(doc: dict) -> dict:
    return {r["id"]: r["vis"] + ("+max" if r.get("max") else "") for r in doc["open"]}


def _same(page, reports, step):
    assert reports, f"{step}: the desk never reported"
    doc, truth = reports[-1]["doc"], page.evaluate(_TRUTH)
    assert doc["layout"] == "windows"
    assert _doc_view(doc) == truth, f"{step}: the document {_doc_view(doc)} is not the desk {truth}"
    fronts = [i for i, v in truth.items() if v.startswith("front")]
    assert doc["front"] == (fronts[0] if fronts else ""), f"{step}: front {doc['front']!r} vs {fronts}"


def _answers(reports) -> dict:
    return {a["seq"]: a["why"] for r in reports for a in r.get("acks", [])}


def _scenario(page, reports, app):
    a, b = [x for x in APPS if x != app and not MANIFESTS[x].get("transient")][:2]
    _order(page, "show", app, 1); _same(page, reports, f"show {app}")
    _order(page, "show", a, 2); _order(page, "show", b, 3); _same(page, reports, "three shown")
    if not MANIFESTS[app].get("transient"):
        _order(page, "minimize", app, 4); _same(page, reports, f"minimise {app} by order")
        page.click(f"[data-wid='{a}'] .hb-max"); page.wait_for_timeout(330); _same(page, reports, f"maximise {a} by hand")
        page.evaluate(f"() => document.querySelector(\"[data-wid='{b}']\").dispatchEvent(new PointerEvent('pointerdown', {{bubbles: true}}))")
        page.wait_for_timeout(330); _same(page, reports, f"{b} brought forward by hand")
        _order(page, "fullscreen", b, 5, on=True); _same(page, reports, f"{b} to full screen by order")
        page.click(f"[data-wid='{b}'] .hb-x", force=True); page.wait_for_timeout(330); _same(page, reports, f"close {b} by hand")
    _order(page, "show", a, 6); _order(page, "close", "nope", 7); _same(page, reports, "a show of the front, a close of nothing")
    _order(page, "close", "", 8); _same(page, reports, "close all")
    _order(page, "close", "", 9)
    doc = reports[-1]["doc"]
    assert doc["open"] == [] and doc["front"] == "", doc
    return _answers(reports)


@pytest.mark.parametrize("app", APPS)
def test_the_desktop_reports_what_it_shows(browser, app):
    page, reports, errors = _page(browser)
    try:
        got = _scenario(page, reports, app)
        rail = bool(MANIFESTS[app].get("transient"))       # an app the desk shows in the rail above the orb
        want = {1: "done", 2: "done", 3: "done", 6: "done" if rail else "already_front",
                7: "not_open", 8: "done", 9: "already_closed"}
        if not rail:
            want |= {4: "done", 5: "done"}
        assert {k: got.get(k) for k in want} == want, got
        ns = [r["n"] for r in reports if r["mount"] == reports[0]["mount"]]
        assert ns == sorted(set(ns)), f"n went back: {ns}"
        assert not errors, errors
    finally:
        page.close()


def test_disarm_a_minimised_card_reported_in_front_turns_it_red(browser):
    src = ADAPTER.read_text(encoding="utf-8")
    assert src.count(_MIN_GUARD) == 1, "disarm did not land"
    page, reports, _ = _page(browser, src.replace(_MIN_GUARD, _MIN_GUARD.replace('"min"', '"front"')))
    try:
        with pytest.raises(AssertionError, match="minimise agenda by order"):
            _scenario(page, reports, "agenda")
    finally:
        page.close()
