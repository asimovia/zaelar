"""The cloud entry point, as a visitor WITHOUT a session sees it (LIVE — read-only, opt-in).

`my.zaelar.com` is a routing edge, not a server: with a session cookie it replays the request to that account's
Machine, and with NO cookie it sends the visitor to the login (2026-10-21; until then it guessed they were a
self-hoster and bounced them to an engine on their own computer). The login brings them back with `next`. That is
the ONLY part of the cloud surface that can be checked without spending money, provisioning a Machine or leaving
an account behind.

WHY IT IS WORTH A TEST. The unauthenticated fallback is what every stranger who types the address gets, and it
fails in a way nobody would notice from inside: a routing change turns it into a 404, a 500 or — worse — into
something that serves real content to someone with no account, and the engine's own suite has no opinion about
it because the engine is not what answers.

⚠️ AND THE TRAP IT PINS, measured 2026-09-04. WITHOUT a session cookie the edge answers EVERY path on the
origin the same way — `/m`, `/manifest.webmanifest` and `/sw.js` included. So a browser with no account cannot
install the PWA and cannot register a service worker: the manifest and the worker only become real once the cookie
routes the request to the account's Machine. That is correct (a visitor with no account has nothing to install)
and it is exactly the shape that reads as "the PWA is broken" to whoever debugs it from a logged-out browser.

READ-ONLY and OPT-IN: nothing but GETs, no account, no session, no writes. Built whole and SKIPPED unless the
runner asks for it (`ZAELAR_CLOUD_LIVE=1`) — the same shape as the connectors' live round-trip, and for the same
reason: reaching the real internet on every commit is flaky, and it would put CI traffic on production. It also
SKIPS rather than fails when the network is not there — a broken wifi is not a broken product. It is deliberately
NOT a `live` node in the map: those are removed from the deterministic run entirely, which is how a test quietly
stops being true (the third form in `test_a_test_outside_the_map_is_not_a_test.py`). Skipped is visible; absent
is not.

Run:  ZAELAR_CLOUD_LIVE=1 ./.venv/bin/python -m pytest tests/infrastructure/e2e/cloud/ -q
Env:  ZAELAR_CLOUD_URL (default https://my.zaelar.com)
"""
from __future__ import annotations

import os
import urllib.error
import urllib.request

import pytest

CLOUD = os.getenv("ZAELAR_CLOUD_URL", "https://my.zaelar.com").rstrip("/")

pytestmark = pytest.mark.skipif(
    os.getenv("ZAELAR_CLOUD_LIVE", "") not in ("1", "true", "yes"),
    reason="reaches the real cloud entry point — enable with ZAELAR_CLOUD_LIVE=1 "
           "(read-only GETs, no account, no cost)",
)

# Cloudflare sits in front and 403s a request whose User-Agent looks like a bot — urllib's default is blocked
# and a browser one passes (measured in `tests/voice/e2e/agent/cloud_smoke.py`, same reason). The tester is a
# legitimate client, so it presents itself as one.
_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
       "Version/17.0 Mobile/15E148 Safari/604.1")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def _get(path: str) -> tuple[int, dict, str]:
    """One GET, redirects NOT followed — the redirect is what is under test."""
    req = urllib.request.Request(CLOUD + path, headers={"User-Agent": _UA})
    try:
        with _OPENER.open(req, timeout=20) as r:
            return r.status, dict(r.headers), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode("utf-8", "replace")
    except Exception as e:                      # noqa: BLE001 — no network is not a product failure
        pytest.skip(f"{CLOUD} unreachable: {type(e).__name__}: {e}")


def _login_target(path: str) -> str:
    status, headers, _ = _get(path)
    assert status == 302, f"{CLOUD}{path} answered {status} to a visitor without a session, not a redirect"
    return headers.get("Location", "")


@pytest.mark.parametrize("path", ["/", "/m"])
def test_a_visitor_without_a_session_is_sent_to_the_login_and_back(path):
    """No cookie means no account to route to: the visitor is sent to log in, and the login is told where to
    bring them back — the same shell they asked for (/m stays /m)."""
    import urllib.parse
    loc = _login_target(path)
    parsed = urllib.parse.urlparse(loc)
    assert parsed.path.rstrip("/").endswith("/login"), loc
    nxt = urllib.parse.parse_qs(parsed.query).get("next", [""])[0]
    assert nxt == CLOUD + path, f"the login would not bring them back to {path}: next={nxt!r}"


@pytest.mark.parametrize("path", ["/manifest.webmanifest", "/sw.js", "/api/status"])
def test_nothing_of_an_account_is_served_to_a_visitor_without_a_session(path):
    """Pins the trap in this module's docstring: the PWA files and the API answer a stranger with the same
    redirect, never with a real Machine's file."""
    status, headers, body = _get(path)
    assert status == 302 and "/login" in headers.get("Location", ""), (path, status, headers.get("Location"))
    for leak in ("zaelar_cloud_session", "api_key", "sk-", "Bearer "):
        assert leak not in body, f"{path} contains {leak!r}"
