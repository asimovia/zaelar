"""V2-666 · an order NAMES its target — a show never lands on the card that merely happens to be open, and a
sentence that names its widget is never treated as «muéstramelo».

Measured live, session 53de97d4 (2026-09-11):
  · 10:33:27 — «ponme un gráfico de la evolución del Bitcoin de este último año» with the YouTube card open:
    `runtime.identify` returned `youtube` with score 0.0 and zero candidates (`by_context: True`), the show
    guard consumed it as a NAME, stole the model's escalation, opened the video card and said «Aquí lo tienes».
  · 10:59:10 — «Mírame, ábreme la agenda inmediatamente» opened the SEARCH card: the article «la» is a bare
    deictic token, so the whole sentence was «muéstramelo»-shaped, the noun he said was discarded, and the
    fallback «the previous route was a web search» chose for him.

Both channels are driven — the voice provider's guard and the probe's mirror — because the decision exists twice
(V2-252). The deictic continuity these guards were built for («Vale, pues muéstramelo» after a weather question)
is asserted alongside, so the fix cannot be a regression dressed as a rule.
"""
from __future__ import annotations

import pytest

from widgets import runtime

_BITCOIN = "Ponme ahí... Johnny, ponme un gráfico de la evolución del Bitcoin de este último año."
_AGENDA = "Pero ¿cómo que no? Mírame, ábreme la agenda inmediatamente."
_PRIOR = [{"role": "user", "content": "Olvídate de eso, respóndeme a la pregunta que te he hecho lo primero."}]


@pytest.fixture
def _youtube_open(monkeypatch):
    """The canvas state the incident had: exactly ONE card open, the video player."""
    from memory import api as _memapi
    monkeypatch.setattr(_memapi, "state", lambda: {"open_widgets": ["youtube"], "recent_widgets": ["youtube"]})


# ── the resolver itself ──────────────────────────────────────────────────────────────────────────────────
def test_identify_still_hands_back_the_only_open_card_by_context():
    """The data-op nuance is intact — «súbele el volumen» with one card open must keep operating it."""
    r = runtime.identify(_BITCOIN, open_ids=["youtube"])
    assert r["match"] == "youtube" and r["by_context"] is True and r["candidates"] == []


def test_identify_named_refuses_the_by_context_fallback():
    assert runtime.identify_named(_BITCOIN, open_ids=["youtube"]) is None
    assert runtime.identify_named(_BITCOIN) is None


def test_identify_named_keeps_a_real_name_with_or_without_context():
    assert runtime.identify_named(_AGENDA) == "agenda"
    assert runtime.identify_named(_AGENDA, open_ids=["youtube"], recent_ids=["search"]) == "agenda"


    # …so the model's escalation stands instead of a blind «Aquí lo tienes» over the video player.
