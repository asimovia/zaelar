"""The feedback button is NEVER hidden — not by settings, not by any panel, overlay or modal (operator, 2026-10-23).

«No esconder nunca el icono de feedback, porque si me está fallando el conector de WhatsApp tengo que poder
avisar y no puedo porque no está el icono.» The launcher sat at z-index 9200, deliberately BELOW the full-screen
surfaces (settings 9600, memory map, vault, debug, every modal), so opening ⚙ — exactly where a broken connector
sends him — covered it. The class fix: the launcher owns the TOP layer, and nothing toggles it off.
"""
from __future__ import annotations

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[4] / "frontend" / "app"
CSS_FILES = [APP / "styles.css", APP / "core" / "shared-surfaces.css", APP / "core" / "components.css"]
WIDGET = (APP / "components" / "FeedbackWidget.js").read_text(encoding="utf-8")


def _rules():
    for f in CSS_FILES:
        css = re.sub(r"/\*.*?\*/", "", f.read_text(encoding="utf-8"), flags=re.S)
        for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
            yield f.name, sel.strip(), body


def _z(body):
    m = re.search(r"z-index:\s*(\d+)", body)
    return int(m.group(1)) if m else None


def test_the_launcher_sits_above_every_other_layer_in_the_app():
    """Every z-index in the app — stylesheets AND the CSS some modules inject from JS — sits under the launcher."""
    fw = [_z(b) for _, s, b in _rules() if s == ".fw-wrap" and _z(b) is not None]
    assert fw, ".fw-wrap declares its z-index"
    others = [(f, s, _z(b)) for f, s, b in _rules()
              if _z(b) is not None and not re.search(r"\.fw-", s)]
    for js in APP.rglob("*.js"):
        others += [(js.name, "injected", int(n)) for n in re.findall(r"z-index:\s*(\d+)", js.read_text(encoding="utf-8"))]
    top = max(others, key=lambda x: x[2])
    assert min(fw) > top[2], f"the feedback launcher ({min(fw)}) is under {top[1]} in {top[0]} ({top[2]})"


def test_no_rule_hides_the_launcher():
    for f, sel, body in _rules():
        if re.search(r"\.fw-(wrap|launcher)\b", sel):
            assert not re.search(r"display:\s*none|visibility:\s*hidden|opacity:\s*0[;}\s]", body), (f, sel)


def test_the_launcher_has_no_visibility_condition_tied_to_other_surfaces():
    """The wrap and the launcher carry STATIC classes: no reactive class/style reading another panel's state."""
    wrap = re.search(r'h\("div", \{ class: "fw-wrap"[^}]*\}', WIDGET)
    launcher = re.search(r'h\("button", \{\s*class: "fw-launcher"', WIDGET)
    assert wrap and launcher, "the wrap and the launcher keep a static class string"
    assert not re.search(r"store\.(configOpen|memmapOpen|vaultOpen|debugOpen|wizardOpen|statusOpen)", WIDGET)
