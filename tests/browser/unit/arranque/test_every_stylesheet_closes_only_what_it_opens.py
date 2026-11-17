"""Every shipped stylesheet closes only the braces it opens.

A stray `}` at the top level of a stylesheet is not an error a browser reports: CSS error recovery reads it as the
start of the NEXT rule's selector, so that rule is dropped in silence. In V2-926 an `@media` block was unwrapped and
its closing brace stayed behind in `core/shared-surfaces.css`; the rule it swallowed was `.lang-onb{display:none}`,
and the first-run language gate showed on every screen of both shells. Nothing failed — the page just looked wrong.

The test reads every tracked `.css` file under `frontend/`, strips comments and strings, and walks the braces.
"""

import re
import subprocess
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[4]


def _stylesheets():
    out = subprocess.run(
        ["git", "ls-files", "frontend/*.css", "frontend/**/*.css"],
        cwd=ENGINE, capture_output=True, text=True, check=True,
    ).stdout.split()
    return sorted(set(out))


def _unbalanced(css: str):
    """Line numbers of stray closing braces, and the depth left open at the end."""
    css = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), css, flags=re.S)
    css = re.sub(r'"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'', '""', css)
    depth, stray = 0, []
    for lineno, line in enumerate(css.split("\n"), 1):
        for ch in line:
            if ch == "{":
                depth += 1
            elif ch == "}":
                if depth == 0:
                    stray.append(lineno)
                else:
                    depth -= 1
    return stray, depth


def test_there_are_stylesheets_to_read():
    assert _stylesheets(), "no tracked stylesheet found under frontend/"


@pytest.mark.parametrize("path", _stylesheets())
def test_the_stylesheet_has_no_stray_brace(path):
    stray, open_left = _unbalanced((ENGINE / path).read_text(encoding="utf-8"))
    assert not stray, f"{path}: stray '}}' at line(s) {stray} — the rule after it is silently dropped"
    assert open_left == 0, f"{path}: {open_left} block(s) never closed"


def test_the_check_catches_the_brace_that_hid_the_language_gate():
    broken = ".pb-cap{bottom:0}\n}\n\n.lang-onb{display:none}\n"
    assert _unbalanced(broken) == ([2], 0)
