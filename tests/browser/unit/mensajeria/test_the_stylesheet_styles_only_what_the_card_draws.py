"""The messaging card's stylesheet styles only what the card draws.

Found 2026-10-26: when the connector screens left this card for ⚙ Conectores (2026-10-04), twenty classes of their
CSS stayed behind — and so did the rule that gave the reply button its channel's colour, still aimed at a
`.composerow` the compose bar no longer drew. A rule for a class nobody draws is not harmless: it is where a live
rule hides when its element is renamed. Classes the card builds by concatenation are named here, with their prefix.
"""
from __future__ import annotations

import re
from pathlib import Path

_WIDGET = Path(__file__).resolve().parents[4] / "widgets" / "mensajeria" / "widget.js"
_BUILT = ("plat-",)      # `"thread plat-" + platform`


def test_every_class_the_stylesheet_names_is_drawn_by_the_card():
    src = _WIDGET.read_text(encoding="utf-8")
    start = src.index("s.textContent=`")
    end = src.index("`;", start)
    css, js = src[start:end], src[:start] + src[end:]
    classes = set(re.findall(r"\.([a-zA-Z][\w-]*)", re.sub(r"/\*.*?\*/", "", css, flags=re.S)))
    orphans = sorted(c for c in classes if not c.startswith(_BUILT)
                     and not re.search(r"(?<![\w-])" + re.escape(c) + r"(?![\w-])", js))
    assert not orphans, f"styled but never drawn: {orphans}"
