"""An answer to a confirmation that does not exist is no act, and the turn says so (refactor2710-99, bank class A).

Bank `msg-es-send-draft` («Envíalo», 7 → 4): in three reds the model called `confirm_widget_delete` — the answer to
a pending confirmation — when nothing was pending, and said «Hecho.». The confirm door resolved nothing, in silence,
so the false «done» stood and nothing was sent.

Now the door reads the pending set first: with nothing waiting for a yes, the call resolves nothing, the turn's
line is the truth in the agent's language («there was nothing waiting for a yes…»), and the timeline says why. A
real pending confirmation is answered exactly as before.
"""
from __future__ import annotations



def test_both_languages_carry_the_line():
    from i18n import langs
    assert all(langs.LANGUAGES[c].confirm_nothing_pending for c in ("es", "en"))
