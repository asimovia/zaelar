"""`browser.export_session {site}` — the session a sign-in left in the daemon's OWN profile, for ONE site.

After he signs in on the daemon's window, a remote engine cannot read that profile (it is on his disk), so it asks for
the session of that one site and imports it into its own browser. What leaves:

  · ONLY the daemon's own profile (`config/daemon/browser/profile`). A window a local engine opened on ITS profile is
    refused, and no other browser on the machine is ever read — there is no code path here that names another
    directory.
  · ONLY the registrable domain of `site` (its cookies and its subdomains', and the localStorage of its origins).
  · AT MOST `MAX_BYTES`; a bigger session is refused rather than cut (a half session signs nobody in).
  · The audit line says «session exported for <domain>» with COUNTS only — never a cookie name or value.

REGISTRABLE DOMAIN, conservatively. No public-suffix list ships with the daemon (no dependencies), so the rule is the
one the engine's scraper already uses: the last two labels, or three when the second-to-last is a short second-level
label under a two-letter country code (`shop.example.co.uk` → `example.co.uk`). A bare suffix (`co.uk`), a single
label and an IP address have no registrable domain and are refused outright.
"""
from __future__ import annotations

import asyncio
import ipaddress
import json
from urllib.parse import urlsplit

from .. import audit, paths
from ..fs.refusal import Refusal

#: The contract's ceiling for one exported session.
MAX_BYTES = 2 * 1024 * 1024
_TIMEOUT_S = 40.0


def _host_of(site: str) -> str:
    raw = (site or "").strip().lower()
    if not raw:
        return ""
    if "://" not in raw:
        raw = "https://" + raw
    return (urlsplit(raw).hostname or "").strip(".")


def registrable_domain(site: str) -> str:
    """`https://www.shop.example.com/x` → `example.com`; `a.example.co.uk` → `example.co.uk`. Raises `Refusal` for
    something that has no registrable domain (empty, an IP, a single label, a bare suffix)."""
    host = _host_of(site)
    try:
        ipaddress.ip_address(host)
        raise Refusal("bad_site", "A session is exported for a site name, not an address.")
    except ValueError:
        pass
    labels = [x for x in host.split(".") if x]
    if len(labels) < 2 or not all(x.replace("-", "").isalnum() for x in labels):
        raise Refusal("bad_site", "That is not a site name a session can be exported for.")
    if len(labels) >= 3 and len(labels[-1]) == 2 and len(labels[-2]) <= 3:
        return ".".join(labels[-3:])
    if len(labels) == 2 and len(labels[-1]) == 2 and len(labels[-2]) <= 3:
        raise Refusal("bad_site", "That is a public suffix, not a site.")
    return ".".join(labels[-2:])


def _belongs(host: str, domain: str) -> bool:
    host = (host or "").strip().lower().lstrip(".")
    return host == domain or host.endswith("." + domain)


def filter_state(state: dict, domain: str) -> dict:
    """Keep only what belongs to `domain`: its cookies and its origins' localStorage."""
    cookies = [c for c in (state.get("cookies") or []) if isinstance(c, dict) and _belongs(c.get("domain", ""), domain)]
    origins = [o for o in (state.get("origins") or [])
               if isinstance(o, dict) and _belongs(urlsplit(str(o.get("origin") or "")).hostname or "", domain)]
    return {"cookies": cookies, "origins": origins}


def own_profile() -> str:
    return str(paths.state_dir() / "browser" / "profile")


async def _headless_state(profile: str) -> dict:
    """No window open: read the profile with a short-lived headless context on it."""
    from playwright.async_api import async_playwright   # optional dependency — only reached when a browser exists
    pw = await async_playwright().start()
    try:
        ctx = await pw.chromium.launch_persistent_context(profile, headless=True)
        try:
            return await ctx.storage_state()
        finally:
            await ctx.close()
    finally:
        await pw.stop()


#: Reads the full storage state of the daemon's own profile when no window holds it. Replaced by tests.
READ_PROFILE = _headless_state


def _windows():
    from .. import browser
    return browser.WINDOWS


def _read_state() -> dict:
    """The daemon's own profile's storage state: from the open window when it is on that profile (one Chromium per
    profile), else from a headless read. Refuses a window open on any other profile."""
    windows = _windows()
    current = dict(getattr(windows, "_current", None) or {})
    mine = own_profile()
    if current:
        if str(current.get("profile") or "") != mine:
            raise Refusal("not_own_profile",
                          "The window open now is not on this daemon's own profile; its session is not exported.")
        ctx = current.get("context")
        return windows._submit(ctx.storage_state(), _TIMEOUT_S)
    try:
        return asyncio.run(asyncio.wait_for(READ_PROFILE(mine), _TIMEOUT_S))
    except Refusal:
        raise
    except Exception as e:  # noqa: BLE001 — no browser, a locked profile: a refusal with its reason
        raise Refusal("browser_failed", f"The session could not be read here: {type(e).__name__}.") from None


def export(site: str) -> dict:
    domain = registrable_domain(site)
    state = filter_state(_read_state() or {}, domain)
    size = len(json.dumps(state, ensure_ascii=False).encode("utf-8"))
    if size > MAX_BYTES:
        audit.record("browser.export_session", caller="relay", path=domain, outcome="refused", reason="too_large",
                     detail={"bytes": size})
        raise Refusal("too_large", "That site's session is bigger than what is exported at once.")
    audit.record("browser.export_session", caller="relay", path=domain, outcome="ok",
                 detail={"message": f"session exported for {domain}", "cookies": len(state["cookies"]),
                         "origins": len(state["origins"]), "bytes": size})
    return {"ok": True, "domain": domain, "storage_state": state}
