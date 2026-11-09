"""Offer the tunnel, take the daemon's dial, renew it, and say what a browser launch should use (V2-836).

THE LIFE OF A TUNNEL, from this side:

  1. every `PRESENCE_POLL_S` the engine reads his daemon's presence through the relay (`relay_link.presence()`);
  2. a connected daemon whose capabilities include `egress` (he switched the tunnel on, on his computer) gets an
     `egress.offer {token, url, expires_at}` — the token from `tokens.mint()`, the url `ZAELAR_TUNNEL_ORIGIN` +
     `/daemon/tunnel`;
  3. his daemon dials that url; the route (`server/daemon_tunnel.py`) checks the token and hands the socket to
     `attach()`, which runs the `mux.Session` until the socket ends (a newer dial replaces an older one);
  4. while it runs, the offer is RENEWED before half its life is gone, so a dropped tunnel can always be redialled
     with a token that is still good; when `egress` leaves his capabilities (he switched it off), the session closes.

`proxy_url()` is what a Chromium launch and an httpx client read: the forwarder's address while a tunnel is up, None
otherwise — and with None the launch is exactly what it was before this existed.
"""
from __future__ import annotations

import asyncio
import contextlib
import os
import time
from urllib.parse import urlsplit

from loguru import logger

from . import tokens
from .forwarder import Forwarder
from .mux import Session

ENV_ORIGIN = "ZAELAR_TUNNEL_ORIGIN"
PRESENCE_POLL_S = 60.0
#: A daemon that has not dialled this long after an offer is offered again (its offer may have been lost).
DIAL_WAIT_S = 30.0
OFFER_DEADLINE_MS = 10_000
CAPABILITY = "egress"
#: The first daemon version that carries the tunnel: older ones cannot be switched on, so they are not «capable».
EGRESS_SINCE = (0, 2, 3)

_state: dict = {"session": None, "offer_at": 0.0, "offer_exp": 0.0, "task": None, "caps": [], "version": ""}
_hosts: dict[str, float] = {}             # host → last carried (epoch s), across tunnels: «sites in the last hour»
_forwarder: Forwarder | None = None
_connected_evt: asyncio.Event | None = None


def tunnel_url() -> str:
    """`wss://<origin>/daemon/tunnel` from `ZAELAR_TUNNEL_ORIGIN` (ws:// only for a loopback origin); "" when unset."""
    raw = (os.getenv(ENV_ORIGIN) or "").strip().rstrip("/")
    u = urlsplit(raw)
    if not u.hostname:
        return ""
    if u.scheme in ("https", "wss"):
        return f"wss://{u.netloc}/daemon/tunnel"
    if u.scheme in ("http", "ws") and u.hostname in ("127.0.0.1", "localhost", "::1"):
        return f"ws://{u.netloc}/daemon/tunnel"
    return ""


def _relay_link():
    from widgets.navegador import owner  # noqa: F401 — the login package loads through its owner
    from widgets.navegador.owner_login import relay_link
    return relay_link


def available() -> bool:
    """Can THIS engine offer a tunnel at all: an instance id, a public origin his daemon dials, a relay to offer by."""
    if not tokens.instance_id() or not tunnel_url():
        return False
    try:
        return bool(_relay_link().hosted())
    except Exception as e:   # noqa: BLE001
        logger.debug(f"daemon_egress: the relay link is unreadable ({type(e).__name__})")
        return False


def session() -> Session | None:
    s = _state["session"]
    return s if s is not None and not s.closed else None


def connected() -> bool:
    return session() is not None


def proxy_url() -> str | None:
    """The forwarder's URL while a tunnel is up; None otherwise (a launch then goes out directly, as before)."""
    if connected() and _forwarder is not None and _forwarder.port:
        return _forwarder.url()
    return None


def launch_args() -> list[str]:
    """What a Chromium launch adds: `--proxy-server=…` while a tunnel is up, nothing otherwise."""
    url = proxy_url()
    return [f"--proxy-server={url}"] if url else []


def _event() -> asyncio.Event:
    global _connected_evt
    if _connected_evt is None:
        _connected_evt = asyncio.Event()
    return _connected_evt


async def ready(timeout: float = 5.0) -> bool:
    """Before a browser launch: when an offer is out and his daemon has not dialled yet, wait up to `timeout` for it,
    so the launch picks the tunnel up instead of missing it by a second. Returns connected."""
    if connected():
        return True
    if not (_state["offer_at"] and time.time() < _state["offer_exp"]
            and time.time() - _state["offer_at"] < DIAL_WAIT_S):
        return False
    with contextlib.suppress(asyncio.TimeoutError):   # no dial in time: the launch goes out directly
        await asyncio.wait_for(_event().wait(), timeout)
    return connected()


async def _ensure_forwarder() -> Forwarder:
    global _forwarder
    if _forwarder is None:
        _forwarder = Forwarder(session)
    await _forwarder.start()
    return _forwarder


async def attach(send_text, recv_text, close) -> None:
    """Run his daemon's tunnel until its socket ends. Called by the route ONCE the token checked out."""
    await _ensure_forwarder()
    old = session()
    s = Session(send_text, recv_text, close_transport=close)
    _state["session"] = s
    if old is not None:
        await old.close()              # a newer dial replaces the older one
    _event().set()
    logger.info("daemon_egress: his tunnel is up")
    try:
        await s.run()
    finally:
        _hosts.update(s._hosts)
        if _state["session"] is s:
            _state["session"] = None
            _event().clear()
        logger.info("daemon_egress: his tunnel ended")


async def offer() -> bool:
    """Mint a token and offer it to his daemon over the relay. Returns whether the daemon accepted it."""
    minted = tokens.mint()
    url = tunnel_url()
    if not minted or not url:
        return False
    token, exp = minted
    out = await _relay_link().command("egress.offer", {"token": token, "url": url, "expires_at": int(exp)},
                                      deadline_ms=OFFER_DEADLINE_MS)
    ok = bool(out.get("ok"))
    if ok:
        _state["offer_at"], _state["offer_exp"] = time.time(), exp
    else:
        code = (out.get("error") or {}).get("code") if isinstance(out.get("error"), dict) else ""
        logger.debug(f"daemon_egress: offer not taken ({code or 'no answer'})")
    return ok


def _version(raw) -> tuple:
    parts = str(raw or "").split(".")[:3]
    return tuple(int(x) for x in parts) if parts and all(x.isdigit() for x in parts) else ()


async def tick(presence: dict) -> None:
    """One look at his daemon: offer, renew, or close — never more than one relay command."""
    is_on = bool(presence.get("connected"))
    caps = [str(c) for c in (presence.get("caps") or [])] if is_on else []
    _state["caps"], _state["version"] = caps, str(presence.get("version") or "") if is_on else ""
    if CAPABILITY not in caps:
        s = session()
        if s is not None:
            await s.close()            # he switched it off (or the daemon left): the tunnel goes with it
        _state["offer_at"] = _state["offer_exp"] = 0.0
        return
    now = time.time()
    left = _state["offer_exp"] - now
    if connected():
        if left > tokens.TTL_S / 2:
            return                     # carrying, and its token still has more than half its life
    elif _state["offer_at"] and now - _state["offer_at"] < DIAL_WAIT_S and left > 0:
        return                         # offered a moment ago: give his daemon time to dial
    await offer()


async def _loop() -> None:
    while True:
        try:
            await tick(await _relay_link().presence())
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 — one failed look never ends the loop
            logger.debug(f"daemon_egress: tick failed ({type(e).__name__})")
        await asyncio.sleep(PRESENCE_POLL_S)


def start() -> bool:
    """Start the offer loop when this engine can offer a tunnel. A no-op (False) on every self-hosted engine."""
    if not available() or _state["task"] is not None:
        return False
    _state["task"] = asyncio.get_running_loop().create_task(_loop())
    return True


async def stop() -> None:
    t, _state["task"] = _state["task"], None
    if t is not None:
        t.cancel()
    s = session()
    if s is not None:
        await s.close()
    if _forwarder is not None:
        await _forwarder.stop()


def status(relay: dict | None = None) -> dict:
    """`/api/daemon/status.egress` on an engine away from his computer: `capable` (a connected daemon recent enough
    to carry a tunnel), `enabled` (he switched it on: `egress` in its capabilities), `connected` (the tunnel is up),
    `hosts_last_hour` (distinct sites it carried)."""
    r = relay or {}
    caps = [str(c) for c in (r.get("caps") or _state["caps"] or [])]
    version = _version(r.get("version") or _state["version"])
    on = bool(r.get("connected")) if relay is not None else bool(caps)
    s = session()
    return {"capable": on and (CAPABILITY in caps or (bool(version) and version >= EGRESS_SINCE)),
            "enabled": on and CAPABILITY in caps,
            "connected": s is not None,
            "hosts_last_hour": hosts_last_hour()}


def hosts_last_hour() -> int:
    now = time.time()
    seen = dict(_hosts)
    s = session()
    if s is not None:
        seen.update(s._hosts)
    for h in [h for h, t in _hosts.items() if now - t >= 3600.0]:
        _hosts.pop(h, None)
    return sum(1 for t in seen.values() if now - t < 3600.0)


def reset_for_tests() -> None:
    global _forwarder, _connected_evt
    _state.update(session=None, offer_at=0.0, offer_exp=0.0, task=None, caps=[], version="")
    _hosts.clear()
    _forwarder = None
    _connected_evt = None
    tokens.forget_all()
