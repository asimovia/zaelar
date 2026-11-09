"""ONE tunnel stream's TCP connection: the kill switch, then the guard, then a socket to a CHECKED address (V2-836).

The order is the security argument, so it is written once, here:

  1. the switch (`config.egress.enabled`) is read for EVERY new stream — a stream asked a millisecond after he
     switched the tunnel off is refused, whatever the tunnel thread has not noticed yet;
  2. the port is one of the web's, and the name is not one that only exists inside his network;
  3. the site's rate bucket has room;
  4. the name is resolved HERE and every address it returns must be public (`egress_guard.resolve_public`);
  5. the socket connects to one of those addresses — never to the name, so there is no second lookup a rebinding
     resolver could answer differently — and the peer it reached is checked once more.

Semantics are CONNECT's: a byte stream to `host:port`, nothing parsed, nothing rewritten.
"""
from __future__ import annotations

import socket

from .. import config
from ..security import egress_guard as guard

CONNECT_TIMEOUT_S = 10.0


def open_stream(host, port, *, resolver=socket.getaddrinfo, enabled=None, limiter=None,
                create=socket.create_connection, timeout: float = CONNECT_TIMEOUT_S) -> tuple[socket.socket, str]:
    """A connected socket and the cleaned host name, or `guard.Refused` with the reason."""
    is_on = enabled if enabled is not None else config.egress_enabled
    if not is_on():
        raise guard.Refused("egress_disabled", "The tunnel is switched off on this computer.")
    p = guard.check_port(port)
    h = guard.clean_host(host)
    if not (limiter or guard.LIMITER).take(guard.domain_of(h)):
        raise guard.Refused("rate_limited", "Too many connections to that site from this computer just now.")
    addresses = guard.resolve_public(h, p, resolver)
    last: Exception | None = None
    for address in addresses:
        try:
            sock = create((address, p), timeout)
        except OSError as e:
            last = e
            continue
        try:
            guard.check_peer(sock)
        except guard.Refused:
            sock.close()
            raise
        sock.settimeout(None)
        return sock, h
    raise guard.Refused("connect_failed", f"Could not reach {h}:{p} ({type(last).__name__ if last else 'no route'}).")
