"""V2-650 — an explicit replay of a play order is an ORDER, not context-bleed.

One live morning (session aed0736c, 2026-09-10): the «True Blue» playlist was built, playback failed
in silence, and the operator said «Vale, pues reproduce la lista», then «Vamos, dale al play, a la
primera canción» — and the data-op dedupe guard (V2-038) ate every replay, because its only escape
measures word overlap between the turn and the PAYLOAD, and no natural play order names
{"playlist": "true-blue"}. The missing discriminator is declared data plus grammar (V2-635 doctrine,
never intent): the widget itself declares which actions start production (`runtime.produce`), and the
turn either carries a conjugated media request or it does not. Agenda-class ops declare no production,
so the guard's founding case («borra el reloj» dragging the dentist's add_meeting) stays dead.
"""
from __future__ import annotations


# ── 1 · the license, against the session's own sentences ─────────────────────────────────────────────────

def test_the_declaration_is_read_not_hardcoded():
    """The escape rides `runtime.produce` — the declared list, exactly as producers.py reads it."""
    from widgets import producers
    assert producers.starts_production("musica", "play_playlist") is True
    assert producers.starts_production("agenda", "add_meeting") is False


# ── 2 · the voice provider consults the license inside the dedupe guard ──────────────────────────────────
