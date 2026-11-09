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

IMPORTED LAZILY ON PURPOSE. Playwright ships inside the installed daemon (the packaged builds bundle it) but is
never imported at the top of a module: `python -m daemon` still runs on a bare Python and the files half needs
nothing else. `available()` says whether this daemon can open a window right now (Playwright importable AND Google
Chrome installed or the downloaded Chromium complete — see `channel`), and `/health` declares `browser.auth` only
when it can — a capability the engine believes in is a promise to the user. `health_fields()` is the rest of what
`/health` says about the browser (`status`), and `DOWNLOAD` is the first-run Chromium job (`download`).

    channel     which browser: the person's Google Chrome, else the downloaded Chromium (v1: Chrome only)
    download    the cancellable `playwright install chromium` job, with progress
    status      the `/health` shape and the `browser.auth` rule
    window      the one sign-in window, driven over Playwright's pipe
    app_window  «Open Zaelar»: the agent in an app-mode window, launched with no automation attached
"""
from __future__ import annotations

from .download import DOWNLOAD  # noqa: F401
from .status import health_fields  # noqa: F401
from .window import CAPABILITY, WINDOWS, available  # noqa: F401 — the package's surface

__all__ = ["CAPABILITY", "WINDOWS", "DOWNLOAD", "available", "health_fields"]
