"""The daemon's OUTBOUND relay link (V2-575 · P3): how an engine that is not on his computer reaches this daemon.

A local engine talks to the daemon over loopback (`daemon/http/`). An engine running somewhere else cannot reach his
loopback, so the daemon dials OUT to a relay and the remote engine's requests arrive over that socket as framed
commands, run through the same route handlers. If no relay URL is configured (`ZAELAR_DAEMON_RELAY_URL`, `relay.json`
or a packaged `build_defaults.json`) or the daemon has not been paired, nothing here runs: loopback only.

    config.py          relay.json (url, credential, paired_at, account_hint), 0600, apart from daemon.json
    ws.py              a minimal standard-library WebSocket client
    client.py          the link: hello → welcome, commands, ping/pong, bye, backoff, browser.state events
    dispatch.py        command.op → the loopback handler; strips `profile`, deadlines, the 20 MB result cap
    session_export.py  browser.export_session — ONE site's session from the daemon's OWN profile, ≤ 2 MB
    pair.py            one-time code → credential (`python -m daemon.relay pair CODE`, or `pair_and_connect`)
    login_link.py      a one-time «Open Zaelar» link, when the relay offers it
"""
from __future__ import annotations
