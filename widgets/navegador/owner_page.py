"""The browser's PAGE: launching Chromium and keeping one live page, URL normalising, the cursor overlay, the
capture the widget shows, and navigation with its own history (V2-778 F1, 2026-10-01).

Moved out of `widgets/navegador/owner.py` with no behaviour change. Every module-level name these functions read —
each other included — is read through the owner (`_o.<name>`), so a patch on `owner` still governs every call, and
the owner imports them back. The browser's state (`_pw`, `_browser`, `_context`, `_page`, `_rev`, the history)
stays the owner's: what was `global` there is `_o.<name>` here.
"""
from __future__ import annotations

from widgets.navegador import launch_env as _launch_env, owner as _o


async def _ensure_page():
    """ONE real window (headed) with a PERSISTENT PROFILE and lazy startup. Reuses any existing window/tab (never opens
    one window per request → no desktop clutter). Isolated profile: does not touch your Chrome or your 9222/9200
    browser (own process and instance). If the real window fails (no display), degrades to headless so the widget is
    not left dead. Lazy Playwright import: if the dependency is missing, only this widget degrades."""
    if _o._page is not None and not _o._page.is_closed():
        return _o._page
    from playwright.async_api import async_playwright
    if _o._pw is None:
        _o._pw = await async_playwright().start()
    if _o._context is None:
        # OPTIONAL debugging port chosen by env — NEVER yours (9222/9200). Empty = Playwright internal pipe
        # (zero ports, zero collisions). If you want to attach, set NAVEGADOR_REMOTE_PORT to a different port.
        args = list(_o._LAUNCH_ARGS)
        port = _o._remote_port()                         # configurable through UI (settings.json) / env; never 9222/9200
        if port:
            args.append(f"--remote-debugging-port={port}")
            _o._emit("remote_port", f"puerto de depuración {port}")
        # V2-836: while his daemon carries this engine's browsing (an engine away from his computer, his tunnel
        # switched on), the browser leaves through the local forwarder; with no tunnel the args are what they were.
        args += await _egress_args()

        async def _launch(headless: bool, channel: str | None):
            # channel="chrome" = the installed REAL Chrome (real-browser fingerprint, not Playwright's Chromium that
            # anti-bot systems recognize). timezone_id keeps the zone consistent with the locale.
            _loc, _tz = _o._browser_locale()
            kw = dict(headless=headless, viewport=_o.VIEWPORT, locale=_loc,
                      timezone_id=_tz, user_agent=_o._UA, args=args)
            if channel:
                kw["channel"] = channel
            if not headless:
                # A graphical server this process's env does not name (a service on a desktop): the probe that
                # said a window can open also says how to reach it (`nucleo/browser_window.display_env`).
                from nucleo import browser_window
                extra = browser_window.display_env() or {}
                if extra:
                    kw["env"] = {**_o.os.environ, **extra}
                    if "WAYLAND_DISPLAY" in extra and "DISPLAY" not in kw["env"]:
                        kw["args"] = [*args, "--ozone-platform=wayland"]
            return await _o._pw.chromium.launch_persistent_context(_o._profile_dir(), **kw)

        # Prefer REAL Chrome (less detectable). If it is not installed, fall back to Playwright's Chromium; if there
        # is no display (headed fails), fall back to headless. Never leave the widget dead.
        # V2-867 F2: the launch asks the worker envelope for room first. His own window is never refused: at most
        # one short poll for the newest worker's pause to take effect, then it opens.
        from nucleo.workers import room as _room
        async with _room.room_for("browser", patient=False):
            _o._context = None
            _o._headed = False
            for _ch in ("chrome", None):
                try:
                    _o._context = await _launch(_o._headless(), _ch)
                    _o._headed = not _o._headless()
                    break
                except Exception as e:
                    _o.logger.warning(f"navegador: launch channel={_ch or 'chromium'} falló "
                                   f"({_o._brief(e, 100)})")
            if _o._context is None:
                try:
                    _o._context = await _launch(True, None)      # last resort: headless chromium
                except Exception as e:
                    _o.logger.warning(f"navegador: headless también falló ({_o._brief(e, 100)})")
                    raise
        _o._browser = None                               # the persistent context IS the browser (no separate object)
        from widgets.navegador import page_outcome as _po   # V2-837 G6: every navigation's status, time, size, wall
        _po.attach(_o._context)
        try:
            await _o._context.add_init_script(_launch_env.stealth_js())   # stealth: browse like a human, not like a scraper
        except Exception:
            pass
        _o._context.set_default_navigation_timeout(_o._NAV_TIMEOUT)
        _o._context.set_default_timeout(_o._NAV_TIMEOUT)
        # Google/YouTube consent in the EU: cookies that avoid the wall (best effort). With the persistent profile,
        # once a banner is accepted it is also saved → it stops appearing on subsequent visits.
        try:
            await _o._context.add_cookies([
                {"name": "SOCS", "value": "CAI", "domain": ".youtube.com", "path": "/"},
                {"name": "SOCS", "value": "CAI", "domain": ".google.com", "path": "/"},
                {"name": "CONSENT", "value": "YES+", "domain": ".youtube.com", "path": "/"},
                {"name": "CONSENT", "value": "YES+", "domain": ".google.com", "path": "/"},
                # Wallapop: OptanonConsent (OneTrust) + its own EU consent cookie
                {"name": "OptanonConsent",
                 "value": "isGpcEnabled=0&datestamp=Tue+Jul+2026+12%3A00%3A00+GMT%2B0200&version=6.29.0&isIABGlobal=false&hosts=&consentId=&interactionCount=1&landingPath=NotLandingPage&groups=C0001%3A1%2CC0002%3A1%2CC0003%3A1%2CC0004%3A1%2CC0005%3A1",
                 "domain": ".wallapop.com", "path": "/"},
                {"name": "euconsent-v2",
                 "value": "CQ...",  # placeholder — auto-click is the real mechanism
                 "domain": ".wallapop.com", "path": "/"},
                # Wallapop: accepted-banner marker (covers its own system when OneTrust is absent)
                {"name": "wp_consent", "value": "1", "domain": ".wallapop.com", "path": "/"},
                {"name": "_consent", "value": "1", "domain": ".wallapop.com", "path": "/"},
                {"name": "user_consent", "value": "true", "domain": ".wallapop.com", "path": "/"},
                {"name": "cookie_consent", "value": "accepted", "domain": ".wallapop.com", "path": "/"},
            ])
        except Exception:
            pass
        await _apply_imported_sessions(_o._context)      # V2-575 P3: a session his daemon handed over survives relaunches
    # ONE tab: reuse the one the persistent context already brings instead of opening another → no extra tabs.
    _o._page = _o._context.pages[0] if _o._context.pages else await _o._context.new_page()
    # V2-835 — the label says what WAS launched, not what was wanted: a headed launch with no screen falls back to
    # headless above, and a «real window» label then promised him a window nobody could see.
    _o._emit("launched", f"navegador {'ventana real' if _o._headed else 'headless'} · perfil persistente")
    return _o._page


async def _egress_args() -> list[str]:
    """`--proxy-server=…` while his tunnel is up (waiting a moment for a dial that is on its way), else nothing."""
    try:
        from nucleo.daemon_egress import link
        await link.ready()
        return link.launch_args()
    except Exception as e:  # noqa: BLE001 — the tunnel is additive: a launch never fails on it
        _o.logger.debug(f"navegador: egress args unavailable ({type(e).__name__})")
        return []


# ── a session handed over by his daemon (V2-575 P3) ───────────────────────────────────────────────────────────
# After he signs in on his daemon's window, a remote engine receives THAT site's session (`browser.export_session`)
# and imports it here: the cookies into this context, the localStorage through an init script that fills the keys
# the page does not have yet. Kept in process memory and re-applied on every relaunch of the context (a persistent
# profile does not keep session cookies across a close). Only what belongs to the domain it came for is taken.

_imported_sessions: dict[str, dict] = {}     # registrable domain → {"cookies": [...], "origins": [...]}
_SAME_SITE = ("Strict", "Lax", "None")


def _belongs(host: str, domain: str) -> bool:
    host = (host or "").strip().lower().lstrip(".")
    return bool(domain) and (host == domain or host.endswith("." + domain))


def _session_for(domain: str, storage_state: dict) -> dict:
    """The part of `storage_state` that belongs to `domain`, in the shapes `add_cookies` and the init script take."""
    from urllib.parse import urlsplit
    cookies = []
    for c in (storage_state or {}).get("cookies") or []:
        if not isinstance(c, dict) or not _belongs(str(c.get("domain") or ""), domain):
            continue
        if not isinstance(c.get("name"), str) or not isinstance(c.get("value"), str):
            continue
        ck = {k: c[k] for k in ("name", "value", "domain", "path", "expires", "httpOnly", "secure") if k in c}
        ck.setdefault("path", "/")
        if c.get("sameSite") in _SAME_SITE:
            ck["sameSite"] = c["sameSite"]
        cookies.append(ck)
    origins = []
    for o in (storage_state or {}).get("origins") or []:
        origin = str((o or {}).get("origin") or "") if isinstance(o, dict) else ""
        if not origin.startswith("https://") or not _belongs(urlsplit(origin).hostname or "", domain):
            continue
        items = [{"name": str(i.get("name")), "value": str(i.get("value"))}
                 for i in (o.get("localStorage") or []) if isinstance(i, dict) and "name" in i]
        origins.append({"origin": origin, "localStorage": items})
    return {"cookies": cookies, "origins": origins}


def _local_storage_script(origins: list) -> str:
    import json
    data = json.dumps({o["origin"]: o["localStorage"] for o in origins if o.get("localStorage")})
    return ("(() => { try { const all = " + data + "; const items = all[location.origin]; if (!items) return;"
            " for (const it of items) { if (localStorage.getItem(it.name) === null)"
            " localStorage.setItem(it.name, it.value); } } catch (e) {} })();")


async def _apply_imported_sessions(ctx) -> None:
    for session in list(_imported_sessions.values()):
        try:
            if session["cookies"]:
                await ctx.add_cookies(session["cookies"])
            if any(o.get("localStorage") for o in session["origins"]):
                await ctx.add_init_script(_local_storage_script(session["origins"]))
        except Exception as e:  # noqa: BLE001 — a session that does not apply leaves the probe to say so
            _o.logger.warning(f"navegador: imported session not applied ({type(e).__name__})")


async def _import_session(domain: str, storage_state: dict) -> dict:
    """Import his daemon's session for `domain` into this engine's browser. Returns COUNTS, never names or values."""
    domain = (domain or "").strip().lower().lstrip(".")
    session = _session_for(domain, storage_state)
    if not domain or not (session["cookies"] or session["origins"]):
        return {"ok": False, "cookies": 0, "origins": 0}
    _imported_sessions[domain] = session
    if _o._context is not None:
        await _apply_imported_sessions(_o._context)
    return {"ok": True, "cookies": len(session["cookies"]), "origins": len(session["origins"])}


# ── utilities ────────────────────────────────────────────────────────────────────────────────────────────────
_YT_RE = _o.re.compile(r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([0-9A-Za-z_-]{11})")
_YT_ID_RE = _o.re.compile(r'"videoId":"([0-9A-Za-z_-]{11})"')


def _looks_like_url(s: str) -> bool:
    s = (s or "").strip()
    if not s or " " in s:
        return False
    if s.startswith(("http://", "https://")):
        return True
    return bool(_o.re.match(r"^[a-z0-9-]+(\.[a-z0-9-]+)+(/.*)?$", s, _o.re.I))   # domain with TLD


def _normalize_url(s: str) -> str:
    s = (s or "").strip()
    if not s.startswith(("http://", "https://")):
        s = "https://" + s
    return s


def _youtube_id(s: str) -> str:
    m = _o._YT_RE.search(s or "")
    return m.group(1) if m else ""


def _draw_cursor(path: str, x: float, y: float) -> None:
    """Draw a mouse cursor (OS-style arrow) over the screenshot, at the VIRTUAL mouse position, so the operator can
    SEE where the automator is acting (the mouse lives inside server-side Chromium, invisible in the photo; this makes
    it visible). Best-effort: if Pillow fails, leave the screenshot as-is."""
    try:
        from PIL import Image, ImageDraw
        img = Image.open(path).convert("RGBA")
        ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)
        x, y = int(x), int(y)
        arrow = [(x, y), (x, y + 18), (x + 5, y + 13), (x + 9, y + 20),
                 (x + 12, y + 18), (x + 8, y + 12), (x + 14, y + 12)]
        d.polygon(arrow, fill=(250, 250, 250, 255))     # light fill
        d.line(arrow + [arrow[0]], fill=(20, 20, 20, 255), width=2, joint="curve")   # dark outline (visible on any background)
        d.ellipse([x - 6, y - 6, x + 6, y + 6], outline=(255, 70, 70, 230), width=2)  # halo to draw the eye
        img.alpha_composite(ov)
        img.convert("RGB").save(path)
    except Exception:
        pass


def _bump_rev(prev: dict | None = None) -> int:
    """The next `rev`, always past what the card holds: `done_when` reads `rev changed`, and a restarted owner
    counting from zero again could land on the very number the baseline took."""
    try:
        stored = int((prev if prev is not None else _o._read()).get("rev") or 0)
    except (TypeError, ValueError, AttributeError):
        stored = 0
    _o._rev = max(_o._rev, stored) + 1
    return _o._rev


async def _capture() -> None:
    """Screenshot the viewport → widgets/_data/navegador/shot.png and bump rev (client <img> cache-bust)."""
    page = _o._page
    shot = f"{_o.store.data_dir(_o.WID)}/shot.png"
    await page.screenshot(path=shot, type="png", full_page=False)
    if _o._automating:                                     # running task → draw the virtual cursor where it is acting
        # OFF-LOOP (V2-035): the PIL composite is synchronous CPU work that held the GIL in the uvicorn loop and
        # starved the TTS audio pump (choppy voice). Move it to a thread → it does not block voice.
        await _o.asyncio.to_thread(_o._draw_cursor, shot, _o._mouse["x"], _o._mouse["y"])
    prev = _o._read()
    _bump_rev(prev)
    title = ""
    try:
        title = await page.title()
    except Exception:
        pass
    from widgets.navegador import page_outcome as _po
    outcome = _po.take(page)
    # `wall` is what the page on screen IS (none · antibot · captcha · http), written as a VALUE so `done_when`
    # reads a walled page as unmet, never as unverifiable. A capture with no new navigation (a scroll) keeps the
    # page's wall; one after `_goto` reset it reads the response the listener noted, or the URL when none was.
    wall = str(outcome.get("wall") or "") or str(prev.get("wall") or "") or _po.classify(200, page.url)
    _o._write(mode="page", url=page.url, title=title or page.url, rev=_o._rev, loading=False, error="",
           youtube_id="", youtube_title="", wall=wall)
    _o._emit("screenshot", page.url, rev=_o._rev, **outcome)   # V2-837 G6: the navigation it shows, once


async def _goto(url: str, push: bool = True, query: str = "") -> None:
    page = await _o._ensure_page()
    # The URL is written BEFORE navigating, so it proves nothing; `rev` (bumped only by a capture) and `wall`
    # (reset here, read again by that capture) are what say the page arrived. `query` is what this page searched.
    _o._write(loading=True, error="", url=url, wall="", query=str(query or ""))
    _o._emit("navigate", url)
    try:
        await page.goto(url, wait_until="domcontentloaded")
        await _o._dismiss_overlays(page)                    # close cookie banners that block the website
        await _o.asyncio.sleep(0.35)                     # let the above-the-fold render before the screenshot
    except Exception as e:
        _o._write(loading=False, error=f"No pude abrir la página: {_o._brief(e, 200)}")
        _o._emit("nav_error", url, error=str(e)[:200])
        return
    if push:
        _o._hist = _o._hist[:_o._idx + 1] + [page.url]
        _o._idx = len(_o._hist) - 1
    await _o._capture()
