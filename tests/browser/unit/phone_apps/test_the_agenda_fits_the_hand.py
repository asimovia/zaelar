"""The agenda on a phone, RENDERED at 393×852 inside the deck's card (V2-876 P-30…P-32).

What a phone showed: the control row on three lines with the plug beside it and the picker cutting the day's title;
week and month titles cut to two letters («De…», «Cal…»); the first hour label half under the day header; the Day
view opened at 14:00 with a 09:00 appointment above it; «NOW —» over a lone dash; a reminder as raw «2026-11-11
08:00»; the built-in task list's internal id «general» printed next to its name; a decorative bell.

Disarm: drop `.agbar{display:contents}` from the phone rules → red (the row stops fitting one line).
"""
from __future__ import annotations

import json
import pathlib

import pytest

pytest.importorskip("playwright.sync_api")

from tests.browser.unit.phone_apps._phone import phone  # noqa: E402

_DATA = json.loads((pathlib.Path(__file__).parent / "agenda_week.json").read_text())


@pytest.fixture(scope="module")
def page():
    with phone("agenda") as pg:
        yield pg


def _view(page, v):
    page.evaluate("(d) => window.__render(d)", _DATA)
    page.evaluate("(v) => { const s = document.querySelector('.agviewsel'); s.value = v; s.dispatchEvent(new Event('change')); }", v)
    page.wait_for_timeout(150)


def test_the_control_row_is_one_line_and_the_title_is_whole(page):
    _view(page, "day")
    m = page.evaluate("""() => {
        const top = el => Math.round(el.getBoundingClientRect().top);
        const sec = document.querySelector('.agsec'), nav = document.querySelector('.agnav'),
              views = document.querySelector('.agviews'), range = document.querySelector('.agrange'),
              plug = document.querySelector('.agcalbtn');
        const r = range.getBoundingClientRect();
        return {tops: [top(sec), top(nav), top(views)], rightEdge: Math.round(views.getBoundingClientRect().right),
                rangeBelow: r.top >= views.getBoundingClientRect().bottom - 1, rangeCut: range.scrollWidth > range.clientWidth + 1,
                plugShown: !!plug && plug.getBoundingClientRect().width > 0,
                small: [...document.querySelectorAll('.agsub button, .agsub select')]
                         .filter(b => b.getBoundingClientRect().width > 0 && b.getBoundingClientRect().height < 44).length};
    }""")
    assert max(m["tops"]) - min(m["tops"]) <= 4, f"switch, ‹ Today › and the picker on ONE line: {m}"
    assert m["rightEdge"] <= 393, m
    assert m["rangeBelow"] and not m["rangeCut"], f"the title has its own line and is never cut: {m}"
    assert not m["plugShown"], "the connector leaves the phone's row"
    assert m["small"] == 0, f"every control a 44pt target: {m}"


def test_week_titles_wrap_instead_of_two_letters_and_the_first_hour_is_whole(page):
    _view(page, "week")
    m = page.evaluate("""() => {
        const t = [...document.querySelectorAll('.agev .agevt')].find(x => x.textContent.startsWith('Dentist'));
        const head = document.querySelector('.aghead').getBoundingClientRect();
        const first = document.querySelector('.aghour');
        const body = first.closest('.agbody') || document.querySelector('.agbody');
        body.scrollTop = 0;
        return {ws: getComputedStyle(t).whiteSpace, lines: Math.round(t.getBoundingClientRect().height / parseFloat(getComputedStyle(t).lineHeight)),
                firstTop: first.getBoundingClientRect().top, headBottom: head.bottom};
    }""")
    assert m["ws"] == "normal" and m["lines"] >= 2, f"a narrow column wraps the title: {m}"
    assert m["firstTop"] >= m["headBottom"] - 1, f"the first hour label is not under the day header: {m}"


def test_the_day_opens_on_the_earlier_of_now_and_the_first_appointment(page):
    _view(page, "day")
    page.wait_for_timeout(200)
    m = page.evaluate("""() => {
        const sc = document.querySelector('.agday-grid') || document.querySelector('.agbody');
        const ev = [...document.querySelectorAll('.agev')].find(x => x.textContent.includes('Standup'));
        const s = sc.getBoundingClientRect(), e = ev.getBoundingClientRect();
        const card = document.querySelector('.agcard');
        return {visible: e.top >= s.top - 1 && e.top < s.bottom, nowText: card ? card.innerText : ''};
    }""")
    assert m["visible"], "the 09:00 appointment is on screen when the day opens at 14:05"
    assert "—" not in m["nowText"], f"no dangling dash on «Now»: {m['nowText']!r}"


def test_the_reminder_is_said_as_a_date_and_the_bell_is_a_target(page):
    _view(page, "list")
    m = page.evaluate("""() => {
        const bell = document.querySelector('.agrow .agbadge');
        const r = bell.getBoundingClientRect();
        const rows = [...document.querySelectorAll('.agrow')].map(x => x.getBoundingClientRect().height);
        bell.click();
        const detail = document.querySelector('.hb-agenda').innerText;
        return {role: bell.getAttribute('role'), w: r.width, h: r.height, rows, detail};
    }""")
    assert m["role"] == "button" and m["w"] >= 44 and m["h"] >= 44, m
    assert min(m["rows"]) >= 44, m["rows"]
    assert "2026-11-11 08:00" not in m["detail"] and "08:00" in m["detail"], "the reminder in his language, never ISO"


def test_the_built_in_list_never_prints_its_internal_id(page):
    page.evaluate("(d) => window.__render(d)", _DATA)
    page.evaluate("() => document.querySelector('.agsecb[data-sec=tasks]').click()")
    assert page.locator(".agt-id").count() == 0, "«general» is the engine's slug, not his"
    page.evaluate("() => document.querySelector('.agt-list[data-list=\"tl_groceries\"]').click()")
    assert page.locator(".agt-id").inner_text() == "tl_groceries", "a list he made keeps its shareable id"
    fam = page.evaluate("() => getComputedStyle(document.querySelector('.agt-count')).fontFamily")
    assert "mono" not in fam.lower(), fam
