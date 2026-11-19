"""A line the home draws after its own fetch reaches the screen document (V2-907 A3, node 4.547).

RENDERED: the real `Deck.js` + `HomeToday.js` + `deck-screen.js`. The home is put on screen before the agenda's data
arrives (`/widgets/agenda/data` answered late, in the page); once it arrives the home draws «next appointments» and
the deck's LAST report must say `next_events` in `home.holds` — without any other change of the deck to carry it.
Disarm: `HomeToday` redraws without telling the deck's screen.
"""
from __future__ import annotations

import pathlib

from tests.browser.unit.mobile.phone_page import open_phone
from tests.browser.unit.mobile.test_the_deck_reports_what_it_shows import _LAYOUT, _widgets

ENGINE = pathlib.Path(__file__).resolve().parents[4]
HOME = ENGINE / "frontend" / "mobile" / "app" / "shell" / "HomeToday.js"
_NOTICE = "    if (holds.join() !== was && deck._screen) deck._screen.changed();   // V2-907 A3: a late redraw is said too\n"
LATE_MS = 700

# The agenda's data arrives LATE_MS after it is asked: one appointment tomorrow.
_LATE_AGENDA = """(ms) => { const f = window.fetch.bind(window);
  window.fetch = (u, i) => {
    if (!String(u).includes('/widgets/agenda/data')) return f(u, i);
    const d = new Date(Date.now() + 86400000), pad = (x) => String(x).padStart(2, '0');
    const date = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
    const body = JSON.stringify({ meetings: [{ date, startTime: '10:00', title: 'Dentist' }] });
    return new Promise((r) => setTimeout(() => r(new Response(body, { status: 200,
      headers: { 'Content-Type': 'application/json' } })), ms));
  }; }"""


def _last_holds(home_src: str | None = None) -> tuple[list, list]:
    routes = [(lambda u: "/widgets" in u and "/frontend/" not in u, _widgets), _LAYOUT]
    if home_src is not None:
        routes.append(("**/frontend/mobile/app/shell/HomeToday.js*", lambda r: r.fulfill(
            status=200, content_type="text/javascript", body=home_src)))
    with open_phone("", routes=routes) as pg:
        pg.evaluate(_LATE_AGENDA, LATE_MS)
        pg.evaluate("""async () => {
            const stage = document.createElement('div'); stage.id = 'zm-deck-wrap'; document.body.append(stage);
            // The LAUNCHER home is what this test reads: the agent's face off (with it on, the home is only the face).
            (await import('/frontend/app/presence/state.js?v=1')).setPresenceOn(false);
            const { Deck } = await import('/frontend/mobile/app/shell/Deck.js?v=a3');
            window.__deck = new Deck(stage); window.__deck.home();
        }""")
        pg.wait_for_timeout(LATE_MS + 900)
        drawn = pg.evaluate("() => window.__deck._today.holds()")
        reps = [p["body"] for p in pg._posts if p["url"] == "/api/screen/report"]
        assert reps and not pg._errors, (reps, pg._errors)
        return drawn, reps[-1]["doc"]["home"]["holds"]


def test_a_late_home_line_is_reported():
    drawn, said = _last_holds()
    assert "next_events" in drawn, f"the home never drew the appointment: {drawn}"
    assert said == drawn, f"the screen document says the home holds {said}, the home drew {drawn}"


def test_disarm_a_redraw_that_does_not_tell_the_screen_turns_it_red():
    src = HOME.read_text(encoding="utf-8")
    assert src.count(_NOTICE) == 1, "disarm did not land"
    drawn, said = _last_holds(src.replace(_NOTICE, ""))
    assert "next_events" in drawn and "next_events" not in said, (drawn, said)
