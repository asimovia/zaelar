"""The daemon's BROWSER (V2-575 · P2): a real, headed window on the user's screen for a sign-in or a challenge only a
person can pass.

WHAT IT OWNS AND WHAT IT DOES NOT. The daemon owns the browser — the Chromium process, its persistent profile, the
window — and nothing about the task that needed it. Which task is waiting, what the card says, what the voice says
and what happens after the sign-in all stay in the engine (`widgets/navegador/owner_login/`). The engine asks for a
window, watches its state, and closes it; that is the whole contract.

WHAT NEVER LEAVES. The session a sign-in creates is cookies inside the profile on this disk. No route returns a
cookie, a cookie name or a page's content: `state` answers the page's URL and HOW MANY cookies appeared since the
window opened — enough for the engine to tell «signed in» from «still on the form», and nothing a caller could
replay.

OPTIONAL ON PURPOSE. Playwright is not in `requirements.txt`: the daemon runs on a bare Python and the files half
needs nothing else. `available()` says whether this daemon can open a window at all (Playwright importable and a
Chromium on disk), and `/health` declares `browser.auth` only when it can — a capability the engine believes in is a
promise to the user.
"""
from __future__ import annotations

from .window import CAPABILITY, WINDOWS, available  # noqa: F401 — the package's surface

__all__ = ["CAPABILITY", "WINDOWS", "available"]
