"""The egress tunnel never becomes a way into his network (V2-836): every destination is judged by the ADDRESS it
resolves to, only web ports pass, one site cannot be hammered from his IP, and the switch is read on every stream.

A fake resolver plays the attacker: a public-looking name that resolves to 10.0.0.5, to 127.0.0.1, to fe80::1, a
name with one public and one private answer (the rebinding shape). The socket factory records WHAT the daemon
connected to, so «it connected to the checked address, never to the name» is asserted, not assumed.

Disarms (seen red 2026-11-09): `is_public` returning True for everything → every private-range case red; the
`all(...)` in `resolve_public` turned into `any(...)` → the mixed-answer case red; `check_port` accepting any port →
the port case red; the switch read removed from `open_stream` → the kill-switch case red.
"""
from __future__ import annotations

import socket

import pytest

from daemon.egress import connect
from daemon.security import egress_guard as guard

PRIVATE = [
    "127.0.0.1", "127.255.255.254", "10.0.0.5", "10.255.0.1", "172.16.0.1", "172.31.255.254", "192.168.1.1",
    "169.254.169.254", "100.64.0.1", "0.0.0.0", "224.0.0.1", "255.255.255.255",
    "::1", "::", "fc00::1", "fd12:3456::1", "fe80::1", "ff02::1",
    "::ffff:10.0.0.5", "::ffff:127.0.0.1", "64:ff9b::a00:5", "2002:a00:5::1",
]
PUBLIC = ["93.184.216.34", "8.8.8.8", "1.1.1.1", "2606:4700:4700::1111", "2a00:1450:4003:80e::200e"]


def _resolver(*addresses):
    def resolve(host, port, family=0, type_=0, *a):
        return [(socket.AF_INET6 if ":" in a_ else socket.AF_INET, socket.SOCK_STREAM, 6, "",
                 (a_, port) if ":" not in a_ else (a_, port, 0, 0)) for a_ in addresses]
    return resolve


class _Sock:
    def __init__(self, peer):
        self.peer, self.closed, self.timeout = peer, False, "unset"

    def getpeername(self):
        return (self.peer, 443)

    def settimeout(self, t):
        self.timeout = t

    def close(self):
        self.closed = True


def _open(host, port=443, *, resolver, enabled=True, limiter=None, made=None):
    made = made if made is not None else []

    def create(addr, timeout):
        made.append(addr)
        return _Sock(addr[0])
    return connect.open_stream(host, port, resolver=resolver, enabled=lambda: enabled,
                               limiter=limiter or guard.DomainBuckets(), create=create)


@pytest.mark.parametrize("address", PRIVATE)
def test_a_public_looking_name_that_resolves_private_is_refused(address):
    made: list = []
    with pytest.raises(guard.Refused) as r:
        _open("shop.example.com", resolver=_resolver(address), made=made)
    assert r.value.code == "private_address", (address, r.value.code)
    assert made == [], f"it connected to {address} anyway"


@pytest.mark.parametrize("address", PRIVATE)
def test_an_address_literal_in_a_private_range_is_refused(address):
    with pytest.raises(guard.Refused) as r:
        _open(f"[{address}]" if ":" in address else address, resolver=socket.getaddrinfo)
    assert r.value.code == "private_address"


def test_one_private_answer_refuses_the_whole_name():
    """The rebinding shape: public AND private records for one name. Nothing is connected."""
    made: list = []
    with pytest.raises(guard.Refused):
        _open("rebind.example.com", resolver=_resolver("93.184.216.34", "192.168.0.10"), made=made)
    assert made == []


@pytest.mark.parametrize("name", ["printer.local", "nas.lan", "router.home.arpa", "localhost", "app.localhost",
                                  "db.internal", "Printer.Local."])
def test_names_that_only_exist_inside_his_network_are_refused_before_any_lookup(name):
    asked: list = []

    def resolver(*a, **k):
        asked.append(a)
        return _resolver("93.184.216.34")(*a)
    with pytest.raises(guard.Refused) as r:
        _open(name, resolver=resolver)
    assert r.value.code == "private_address" and asked == [], "no lookup is even made"


@pytest.mark.parametrize("address", PUBLIC)
def test_a_public_site_connects_to_the_checked_address_never_to_the_name(address):
    made: list = []
    sock, host = _open("www.example.com", resolver=_resolver(address), made=made)
    assert host == "www.example.com"
    assert made and made[0][0] == address, "the socket goes to the address that was checked"
    assert sock.timeout is None


def test_the_peer_actually_reached_is_checked_again():
    def create(addr, timeout):
        return _Sock("10.0.0.9")          # the platform mapped us somewhere private after all
    with pytest.raises(guard.Refused) as r:
        connect.open_stream("www.example.com", 443, resolver=_resolver("93.184.216.34"), enabled=lambda: True,
                            limiter=guard.DomainBuckets(), create=create)
    assert r.value.code == "private_address"


@pytest.mark.parametrize("port", [22, 25, 53, 3306, 5432, 6379, 0, 65536, "x", None])
def test_only_web_ports_pass(port):
    with pytest.raises(guard.Refused) as r:
        _open("www.example.com", port, resolver=_resolver("93.184.216.34"))
    assert r.value.code in ("port_not_allowed", "bad_port")


@pytest.mark.parametrize("port", [80, 443, 8080, 8443])
def test_the_four_web_ports_are_the_ones_allowed(port):
    assert _open("www.example.com", port, resolver=_resolver("93.184.216.34"))[1] == "www.example.com"


def test_one_site_is_rate_limited_and_another_is_not():
    clock = [0.0]
    lim = guard.DomainBuckets(capacity=5, rate=1.0, clock=lambda: clock[0])
    res = _resolver("93.184.216.34")
    for i in range(5):
        _open(f"a{i}.cdn.example.com", resolver=res, limiter=lim)
    with pytest.raises(guard.Refused) as r:
        _open("img.cdn.example.com", resolver=res, limiter=lim)
    assert r.value.code == "rate_limited", "subdomains of one site share its bucket"
    assert _open("other.example.org", resolver=res, limiter=lim), "another site has its own bucket"
    clock[0] += 2.0
    assert _open("img.cdn.example.com", resolver=res, limiter=lim), "the bucket refills with time"


def test_the_switch_is_read_on_every_new_stream():
    state = {"on": True}
    res = _resolver("93.184.216.34")
    lim = guard.DomainBuckets()

    def go():
        return connect.open_stream("www.example.com", 443, resolver=res, enabled=lambda: state["on"], limiter=lim,
                                   create=lambda a, t: _Sock(a[0]))
    assert go()
    state["on"] = False
    with pytest.raises(guard.Refused) as r:
        go()
    assert r.value.code == "egress_disabled"
