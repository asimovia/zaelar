"""⚙ Settings is ONE left menu, and everything in it reads from the left edge (operator, 2026-10-25).

«Un menú a la izquierda, en lugar de tabuladores arriba del todo… que se vea Ajustes y debajo sus sub-items,
y luego los demás… en mobile tendremos un menú que será la primera página… y todo alineado a la izquierda.»
The four top tabs became the four groups of one side menu (Settings carries its sections under it); the
content column is no longer centred, a setting row's control and hint start from the left, and on a phone
the menu is the first page with «← Menú» to come back. Contract between ConfigPanel and the stylesheet.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[4]
APP = ENGINE / "frontend" / "app"
PANEL = (APP / "components" / "ConfigPanel.js").read_text(encoding="utf-8")
CSS = (APP / "styles.css").read_text(encoding="utf-8")


def _rule(selector: str) -> str:
    m = re.search(r"(?:^|\})\s*" + re.escape(selector) + r"\{([^}]*)\}", CSS, re.M)
    assert m, f"no rule for {selector}"
    return m.group(1)


def test_there_are_no_top_tabs_left():
    assert 'class="cf-tabs"' not in PANEL and "cf-tab\"" not in PANEL
    assert ".cf-tabs{" not in CSS and ".cf-tab{" not in CSS


def test_one_menu_holds_the_four_areas_and_settings_lists_its_sections_under_it():
    assert re.search(r'<nav class="cf-nav cf-side"', PANEL)
    for area in ("settings", "apariencia", "conectores", "widgets"):
        assert f'{{ id: "{area}", icon: ' in PANEL, area
    # the sections are sub-items of the Settings row, rendered right after it
    assert '(tab.id === "settings" ? `<div class="cf-nav-subs">${subs}</div>` : "")' in PANEL
    assert 'class="cf-nav-item cf-nav-sub' in PANEL and "data-sec=" in PANEL


def test_the_content_column_starts_at_the_left_edge():
    assert "margin:0" in _rule(".cf-panel") and "auto" not in _rule(".cf-panel")
    row, ctl, hint = _rule(".cf-row2"), _rule(".cf-row2-ctl"), _rule(".cf-hint")
    assert "grid-template-columns:200px" in row, "a label column, then the control column — not label ↔ right edge"
    assert "align-items:flex-start" in ctl and "flex-end" not in ctl
    assert "text-align:left" in hint
    assert "justify-content:flex-start" in _rule(".cf-foot")
    assert "text-align:left" in _rule(".cf-waliases")


def test_on_a_phone_the_menu_is_the_first_page_and_a_section_has_a_way_back():
    phone = CSS[CSS.index("@media(max-width:760px){\n  .cf-layout.is-menu"):]
    phone = phone[:phone.index("\n}\n")]
    assert ".cf-layout.is-menu .cf-main,.cf-layout:not(.is-menu) .cf-side{display:none}" in phone
    assert ".cf-mback{display:flex" in phone and ".cf-mback{display:none}" in CSS
    assert 'data-menu="1"' in PANEL and "navOpen = true; render();" in PANEL
    # a plain ⚙ lands on the menu; a request (a tab, a connector) lands on what it asked for
    assert "navOpen = !(want || cxWant);" in PANEL


def test_the_menu_label_exists_in_both_bundles():
    for lang in ("es", "en"):
        assert "config.menu" in json.loads((ENGINE / "i18n" / "genesis" / lang / "ui.json").read_text(encoding="utf-8"))
