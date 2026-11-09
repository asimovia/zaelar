"""The OUTBOUND TUNNEL (V2-836): a connected engine's browser leaves the internet from this computer.

A hosted engine runs in a datacenter, and many sites wall datacenter addresses. When the person switches the tunnel
on, the engine's own browser and its direct fetches open their TCP connections HERE, so sites see his own connection.

    connect.py   one stream: the kill switch → the guard (`daemon/security/egress_guard.py`) → TCP to a CHECKED address
    ledger.py    the audit: one line per destination host and hour (counts and bytes, never a URL or a path)
    tunnel.py    the second outbound WebSocket — to the URL an `egress.offer` names, with the offered token — and the
                 frames multiplexed over it: `{id, t: open|ok|data|close, host, port, b64, error}`

What it is NOT: a proxy that reads traffic. The engine speaks `CONNECT host:port` semantics; TLS runs end to end
between the engine's browser and the site, so this computer sees host names and byte counts, nothing inside.

Off by default (`config.egress.enabled`), switched only here (tray, or the local screen over loopback), never by a
remote command: an offer that arrives while it is off is refused (`egress_disabled`), and switching it off closes the
tunnel and every stream on it at once.
"""
from __future__ import annotations

import sys


def note(where: str, e: BaseException) -> None:
    """One line on stderr — the daemon's log — with the exception's TYPE only (its text can carry an address)."""
    print(f"zaelar-daemon egress: {where}: {type(e).__name__}", file=sys.stderr, flush=True)
