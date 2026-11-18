"""Every ⚙ Settings page is drawn by ONE layout, and the benchmarks screen is gone (operator, 2026-11-18).

«Los headers están mal construidos, los botones puestos en cualquier sitio, cada uno de un tamaño, no hay cancelar»:
each section built its own header, rows and buttons. Now `components/settings/layout.js` is the only place a page
shape lives — breadcrumb, title, one line, rows with a fixed label column, Cancel + Save at the bottom right — and
every section reaches the screen through it, so a new section cannot skip it. Read from the sources, no browser.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[4]
APP = ENGINE / "frontend" / "app"
COMP = APP / "components"
PANEL = (COMP / "ConfigPanel.js").read_text(encoding="utf-8")
LAYOUT = (COMP / "settings" / "layout.js").read_text(encoding="utf-8")
SECTIONS = (COMP / "settings" / "sections.js").read_text(encoding="utf-8")
CSS = (APP / "styles.css").read_text(encoding="utf-8")
SETTINGS_FILES = {p.name: p.read_text(encoding="utf-8") for p in
                  (COMP / "ConfigPanel.js", COMP / "settings" / "sections.js", COMP / "RulesSection.js", COMP / "PermissionsSection.js")}


def _ids(name: str) -> list[str]:
    block = PANEL[PANEL.index(f"const {name} = ["):]
    return re.findall(r'\{ id: "([a-z_]+)"', block[:block.index("];")])


def test_every_section_and_area_is_built_by_the_layout():
    builders = PANEL[PANEL.index("const builders = {"):]
    builders = builders[:builders.index("};")]
    for sid in _ids("SECTIONS"):
        line = re.search(rf"^\s*{sid}: \(\) => (.+)$", builders, re.M)
        assert line, f"Settings section «{sid}» has no builder"
        assert re.match(r"(S\.sec_\w+\(|page\(|host\()", line.group(1)), f"«{sid}» is not drawn by the layout: {line.group(1)}"
    for tab in _ids("TABS"):
        if tab == "settings":
            continue
        branch = re.search(rf'activeTab === "{tab}"\) content = (.+?);\n', PANEL)
        assert branch, f"area «{tab}» has no branch"
        assert re.match(r"(S\.sec_\w+\(|page\(|sec_connectors\(\))", branch.group(1)), f"«{tab}» skips the layout"
    # every exported page builder in sections.js returns a layout page
    for name, body in re.findall(r"export (?:function|const) (sec_\w+)[^{]*?(?:\{|=>)(.*?)(?=\nexport |\Z)", SECTIONS, re.S):
        assert "page(" in body or "sec(" in body, f"{name} builds its own page shape"
    cx = PANEL[PANEL.index("function sec_connectors()"):PANEL.index("async function settle()")]
    assert cx.count("page({") >= 2 and 'class="set-page set-page--cx"' in cx, "the connectors list and one connector sit in a layout page"


def test_no_settings_file_draws_its_own_header_rows_or_buttons():
    for name, src in SETTINGS_FILES.items():
        for old in ("cf-row2", "cf-panel-sec", "cf-panel-head", "cf-foot", "cf-save", "<h4>"):
            assert old not in src, f"{name} still draws «{old}» by hand"
    for gone in (".cf-row2{", ".cf-panel-sec{", ".cf-foot{", ".cf-benchmarks-btn", ".bp-"):
        assert gone not in CSS, gone


def test_the_layout_has_one_header_one_row_and_one_action_bar():
    assert '<nav class="set-crumb"' in LAYOUT and 'class="set-title"' in LAYOUT and 'class="set-sub"' in LAYOUT
    assert 'class="set-row"' in LAYOUT and 'class="set-label"' in LAYOUT and 'class="set-ctl"' in LAYOUT
    # Cancel + Save, both disabled until something changes; Cancel restores, Save says its result in place
    assert 'attrs: "data-set-cancel disabled"' in LAYOUT
    assert re.search(r'btn\(t\("settings.form.save"\), \{ kind: "primary", attrs: "data-set-save disabled" \}\)', LAYOUT)
    assert "saveB.disabled = cancelB.disabled = !dirty;" in LAYOUT and "cancelB.onclick" in LAYOUT
    assert 'say(here, "✓ "' in LAYOUT and 'say(here, "✗ "' in LAYOUT
    # the sizes are tokens, the same for every page; a phone stacks label over field
    for tok in ("--st-label-w:", "--st-field-w:", "--st-ctl-h:", "--st-btn-w:"):
        assert tok in CSS, tok
    assert re.search(r"\.set-row\{display:grid;grid-template-columns:var\(--st-label-w\) minmax\(0,var\(--st-field-w\)\)", CSS)
    phone = CSS[CSS.index("@media(max-width:760px){\n  .cf-layout.is-menu"):]
    assert ".set-row,.set-row--wide{grid-template-columns:minmax(0,1fr)" in phone[:phone.index("\n}\n")]


def test_every_form_page_binds_cancel_and_save():
    saves = PANEL[PANEL.index("const saves = {"):]
    saves = saves[:saves.index("};")]
    for sid in ("fast", "code", "memory", "voice", "search"):
        assert f"{sid}:" in saves, sid
    assert "bindForm(pg, { save: saves[activeSec], reset: render })" in PANEL
    assert "bindForm(pg, {" in PANEL[PANEL.index("function wireAppearance"):], "Appearance saves and cancels like the rest"
    for name in ("RulesSection.js", "PermissionsSection.js"):
        assert "bindForm(pageEl" in SETTINGS_FILES[name], name


def test_the_strings_exist_in_both_languages():
    keys = set(re.findall(r't\("((?:settings\.form|config\.(?:fast|presence|theme)\.)[a-z_.]+)"\)', LAYOUT + SECTIONS + PANEL))
    assert {"settings.form.save", "settings.form.cancel", "config.fast.sub", "config.presence.sub"} <= keys
    for lang in ("en", "es"):
        bundle = json.loads((ENGINE / "i18n" / "genesis" / lang / "ui.json").read_text(encoding="utf-8"))
        assert not sorted(k for k in keys if k not in bundle), lang


def test_the_benchmarks_screen_and_its_data_are_gone():
    assert not (COMP / "BenchmarksPanel.js").exists()
    assert not (ENGINE / "config" / "model_benchmarks.py").exists()
    assert not (ENGINE / ".meshkore" / "docs" / "ops" / "zaelar-model-benchmarks.md").exists()
    assert "/api/config/benchmarks" not in (ENGINE / "server" / "config_api.py").read_text(encoding="utf-8")
    assert "getBenchmarks" not in (APP / "services" / "api.js").read_text(encoding="utf-8")
    assert "benchmarksOpen" not in (APP / "core" / "store.js").read_text(encoding="utf-8")
    assert "benchmark" not in PANEL.lower()
    assert '"benchmarks"' not in (APP / "core" / "system-surfaces.js").read_text(encoding="utf-8")
    assert '"benchmarks"' not in (ENGINE / "widgets" / "system_surfaces.py").read_text(encoding="utf-8")
    assert "surface:benchmarks" not in (ENGINE / "nucleo" / "self" / "catalog.json").read_text(encoding="utf-8")
    for lang in ("en", "es"):
        bundle = json.loads((ENGINE / "i18n" / "genesis" / lang / "ui.json").read_text(encoding="utf-8"))
        assert not [k for k in bundle if k.startswith("bench.") or k == "config.fast.benchmarks"], lang
        # the FlashBrain line is for the person, not a note to the team
        for k in ("config.fast.sub", "config.catalog.fast.note"):
            assert not re.search(r"benchmark|operator|§|\d{4}-\d{2}-\d{2}", bundle[k], re.I), (lang, k, bundle[k])
