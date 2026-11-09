"""EGRESS THROUGH HIS DAEMON (V2-836) — the engine side of the outbound tunnel.

Not to be confused with `nucleo/energy/egress.py`, which is the MODEL gateway (where provider calls go). This package
is about where the engine's own BROWSER traffic leaves from.

If this engine runs away from his computer (an account routing deployment: an instance id, a relay to reach his
daemon, and `ZAELAR_TUNNEL_ORIGIN` naming the public origin his daemon dials) and his daemon declares `egress` —
he switched the tunnel on, on his computer — the engine offers a tunnel over the relay, his daemon dials back a
WebSocket to `/daemon/tunnel`, and from then on the engine's Chromium and its direct fetches open their connections
through it, so sites see his own connection instead of a datacenter's. Without all of that, nothing here runs and the
traffic goes out directly, exactly as before.

    tokens.py     `<instance_id>.<32 random bytes, base64url>`, short-lived, kept in memory, verified in constant time
    mux.py        the frames over that one WebSocket: `{id, t: open|ok|data|close, host, port, b64, error}` + ping
    forwarder.py  `127.0.0.1:<ephemeral>` speaking `CONNECT host:port` (and absolute-form http) to Chromium and httpx
    link.py       offer → wait for the dial → renew; the proxy URL a launch reads; the status the 🖥 screen shows
"""
