"""A turn the fast model could not read is answered with ONE line that asks him — never a second look (V2-833 F7/F8,
V2-851 F5).

The class: the voice model runs with reasoning off, so a garbled transcript — «…y lo pon pa tipos como tú de Shakira» —
cannot be read. «Unreadable» is a STATE of the turn: the brief's `readable` verdict holds the reflex pass's words (an
act proves it read him and keeps them), and the model's own `not_understood` call is the second reader. Either way the
turn says one `not_understood_lines` line from the table. The deliberate pass that re-ran the model with reasoning on
went in V2-851 F5 with every model re-run after the main stream: Flash asks until it is clear.
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


class _Lang:
    def __init__(self, code: str):
        from i18n import langs
        self._s = langs.spec(code)

    def __getattr__(self, k):
        return getattr(self._s, k)


# ── V2-833 F8 · «unreadable» is a STATE of the turn, decided by the brief's verdict ─────────────────────────────────────


# ── V2-851 F5 · the turn asks; nothing runs the model again ─────────────────────────────────────────────────────────


def test_the_lines_exist_in_both_languages():
    for code in ("es", "en"):
        assert len(_Lang(code).not_understood_lines) >= 2
