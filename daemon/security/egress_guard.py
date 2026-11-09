"""Where the egress tunnel may take a connection — and, far more often, where it may not (V2-836).

THE RULE THAT DECIDES WHETHER THE FEATURE IS ACCEPTABLE AT ALL: the daemon must never become a way into his own
network. A connected engine asks the daemon to open TCP connections on its behalf; if «my router's admin page», «the
printer», «the NAS» or «a service on this very computer» were reachable that way, switching the tunnel on would
publish his LAN to whoever controls the engine. So every destination is judged by the ADDRESS it resolves to, never
by its name:

  · a name is resolved here, EVERY address it returns is checked, and the connection is then made to one of those
    checked addresses — never by name again. A resolver that answers public then private (DNS rebinding) gets
    nothing: there is no second lookup to win.
  · one private answer refuses the whole name. A name that resolves to both a public and a private address is not a
    public site that happens to have a stray record; it is exactly the shape a rebinding attack takes.
  · after the connect, the peer's address is checked once more (defence in depth against a platform that maps
    addresses under us — a NAT64 prefix, an IPv4-mapped IPv6).

Refused: loopback (127/8, ::1), RFC 1918 (10/8, 172.16/12, 192.168/16), link-local (169.254/16, fe80::/10), unique
local (fc00::/7), carrier-grade NAT (100.64/10), «this network» (0/8), multicast, reserved and unspecified ranges, and
any address whose embedded IPv4 (mapped, NAT64, 6to4) is one of those. By NAME, before any lookup: `localhost`, and
`.local` / `.localhost` / `.internal` / `.lan` / `.home.arpa` — names that only mean something inside his network.

Ports: 80, 443, 8080, 8443 — the web, and nothing else. A tunnel that reaches port 25 is a spam relay; one that
reaches 22 is a login prompt on somebody's server with his IP on it.

Pure where it can be: the resolver is a parameter, so the tests feed it a «public-looking name that resolves to
10.0.0.5» without a network.
"""
from __future__ import annotations

import ipaddress
import re
import socket
import threading
import time

ALLOWED_PORTS = frozenset({80, 443, 8080, 8443})

_LOCAL_SUFFIXES = (".local", ".localhost", ".internal", ".lan", ".home.arpa")
_LOCAL_NAMES = frozenset({"localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback"})
_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,253}$")

# Explicit, so the rule does not depend on which Python's `ipaddress` tables shipped with the daemon.
_BLOCKED_NETS = tuple(ipaddress.ip_network(n) for n in (
    "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16", "172.16.0.0/12",
    "192.0.0.0/24", "192.0.2.0/24", "192.168.0.0/16", "198.18.0.0/15", "198.51.100.0/24", "203.0.113.0/24",
    "224.0.0.0/4", "240.0.0.0/4", "255.255.255.255/32",
    "::/128", "::1/128", "fc00::/7", "fe80::/10", "fec0::/10", "ff00::/8", "2001:db8::/32", "100::/64",
))
_NAT64 = ipaddress.ip_network("64:ff9b::/96")


class Refused(Exception):
    """A destination the tunnel will not reach. `code` is the stable reason the engine branches on and the audit
    keeps; the message is for a person."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code
        self.message = message or code


def _embedded_v4(ip: ipaddress.IPv6Address) -> ipaddress.IPv4Address | None:
    if ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    if ip in _NAT64:
        return ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    if ip.sixtofour is not None:
        return ip.sixtofour
    return None


def _address(text: str):
    """The IP address `text` spells, or None when it spells a name (not a failure: most hosts are names)."""
    try:
        parsed = ipaddress.ip_address(str(text).split("%", 1)[0])
    except ValueError:
        parsed = None
    return parsed


def is_public(address: str) -> bool:
    """Whether one ADDRESS (not a name) is somewhere on the public internet the tunnel may reach."""
    ip = _address(address)
    if ip is None:
        return False
    if isinstance(ip, ipaddress.IPv6Address):
        inner = _embedded_v4(ip)
        if inner is not None and not is_public(str(inner)):
            return False
    if any(ip in net for net in _BLOCKED_NETS if net.version == ip.version):
        return False
    if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_multicast or ip.is_reserved \
            or ip.is_unspecified:
        return False
    return ip.is_global


def check_port(port) -> int:
    try:
        p = int(port)
    except (TypeError, ValueError):
        raise Refused("bad_port", "That is not a port number.") from None
    if p not in ALLOWED_PORTS:
        raise Refused("port_not_allowed", "The tunnel only carries web traffic (ports 80, 443, 8080, 8443).")
    return p


def clean_host(host) -> str:
    """The host as the tunnel will treat it: lower case, brackets off an IPv6 literal, no trailing dot. Refuses a
    name that only means something inside his network BEFORE any lookup is made."""
    h = str(host or "").strip().lower()
    if h.startswith("[") and h.endswith("]"):
        h = h[1:-1]
    h = h.rstrip(".")
    if not h:
        raise Refused("bad_host", "No destination was named.")
    if _address(h) is not None:
        return h
    if not _NAME_RE.match(h) or ".." in h:
        raise Refused("bad_host", "That is not a host name.")
    if h in _LOCAL_NAMES or h.endswith(_LOCAL_SUFFIXES):
        raise Refused("private_address", "That name only exists inside your own network.")
    return h


def resolve_public(host: str, port: int, resolver=socket.getaddrinfo) -> list[str]:
    """Every address `host` resolves to — all of them public, or `Refused`. The caller connects to these addresses,
    never to the name again."""
    h = clean_host(host)
    try:
        infos = resolver(h, port, 0, socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError, OSError):
        raise Refused("unresolvable", "That name does not resolve.") from None
    addresses: list[str] = []
    for info in infos or []:
        sockaddr = info[4] if isinstance(info, (tuple, list)) and len(info) > 4 else None
        addr = str(sockaddr[0]) if isinstance(sockaddr, (tuple, list)) and sockaddr else ""
        if addr and addr not in addresses:
            addresses.append(addr)
    if not addresses:
        raise Refused("unresolvable", "That name does not resolve.")
    if not all(is_public(a) for a in addresses):
        raise Refused("private_address", "That destination is inside a private or local network.")
    return addresses


def check_peer(sock: socket.socket) -> None:
    """After the connect: the address actually reached is public too."""
    try:
        peer = sock.getpeername()[0]
    except OSError:
        raise Refused("connect_failed", "The connection did not come up.") from None
    if not is_public(str(peer)):
        raise Refused("private_address", "That destination is inside a private or local network.")


def domain_of(host: str) -> str:
    """The rate limiter's key: the last two labels of a name (`img.cdn.example.com` → `example.com`), the address
    itself for an IP literal. Coarse on purpose — a site that spreads over many subdomains is still one site."""
    h = str(host or "").lower().rstrip(".")
    if _address(h) is not None:
        return h
    labels = [x for x in h.split(".") if x]
    return ".".join(labels[-2:]) if len(labels) >= 2 else h


class DomainBuckets:
    """A token bucket per site: `capacity` new connections at once, refilled at `rate` per second. A browser opening
    a page uses a few dozen connections across a handful of sites; a loop hammering one site from his IP runs dry
    here instead of getting his address banned there."""

    def __init__(self, capacity: float = 120.0, rate: float = 4.0, clock=time.monotonic, max_keys: int = 4096):
        self.capacity, self.rate, self._clock, self._max = capacity, rate, clock, max_keys
        self._lock = threading.Lock()
        self._b: dict[str, tuple[float, float]] = {}

    def take(self, key: str) -> bool:
        now = self._clock()
        with self._lock:
            tokens, at = self._b.get(key, (self.capacity, now))
            tokens = min(self.capacity, tokens + (now - at) * self.rate)
            ok = tokens >= 1.0
            self._b[key] = (tokens - 1.0 if ok else tokens, now)
            if len(self._b) > self._max:      # forget the fullest buckets first: they are the idle sites
                for k, _ in sorted(self._b.items(), key=lambda kv: -kv[1][0])[: len(self._b) - self._max]:
                    self._b.pop(k, None)
            return ok

    def reset(self) -> None:
        with self._lock:
            self._b.clear()


LIMITER = DomainBuckets()
