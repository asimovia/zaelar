"""`browser.export_session {site}` hands over ONE site's session, only from the daemon's OWN profile (V2-575 P3).

After he signs in on the daemon's window, a remote engine asks for that site's session to import it into its own
browser. What may leave is bounded three ways: the registrable domain of `site` (its cookies and its subdomains', the
localStorage of its origins — nothing of any other site), the daemon's own profile (a window a local engine opened on
ITS profile is refused, and no other browser is ever read), and 2 MB. The audit line names the domain and COUNTS,
never a cookie name or value.

The browser is faked at its seams (the window's context, `READ_PROFILE` for a closed window); state is in a temporary
workspace.
Disarms: `filter_state` keeping every cookie → red; the own-profile check removed → red; the 2 MB cap removed → red.
"""
from __future__ import annotations

import json

import pytest

_STATE = {
    "cookies": [
        {"name": "sid", "value": "SECRET-SHOP", "domain": ".shop.example.com", "path": "/"},
        {"name": "pref", "value": "v", "domain": "www.example.com", "path": "/"},
        {"name": "sid", "value": "SECRET-BANK", "domain": ".bank.example.org", "path": "/"},
        {"name": "x", "value": "evil", "domain": "notexample.com", "path": "/"},
    ],
    "origins": [
        {"origin": "https://shop.example.com", "localStorage": [{"name": "token", "value": "LS-SHOP"}]},
        {"origin": "https://bank.example.org", "localStorage": [{"name": "token", "value": "LS-BANK"}]},
    ],
}


@pytest.fixture
def ws_root(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    from daemon import browser
    monkeypatch.setattr(browser.WINDOWS, "_current", {})
    return tmp_path


@pytest.mark.parametrize("site,domain", [
    ("https://www.shop.example.com/login?next=/", "example.com"),
    ("example.com", "example.com"),
    ("a.b.example.co.uk", "example.co.uk"),
    ("WWW.Example.COM", "example.com"),
])
def test_the_registrable_domain(site, domain):
    from daemon.relay import session_export
    assert session_export.registrable_domain(site) == domain


@pytest.mark.parametrize("site", ["", "localhost", "127.0.0.1", "co.uk", "https://[::1]/", "exa mple.com"])
def test_no_registrable_domain_no_export(site):
    from daemon.fs.refusal import Refusal
    from daemon.relay import session_export
    with pytest.raises(Refusal):
        session_export.registrable_domain(site)


def test_only_the_sites_cookies_and_storage_leave(ws_root, monkeypatch):
    from daemon import audit
    from daemon.relay import session_export
    profiles: list = []

    async def read(profile):
        profiles.append(profile)
        return json.loads(json.dumps(_STATE))
    monkeypatch.setattr(session_export, "READ_PROFILE", read)
    out = session_export.export("https://shop.example.com/account")
    assert profiles == [session_export.own_profile()], "a closed window is read from the daemon's own profile"
    assert out["domain"] == "example.com"
    st = out["storage_state"]
    assert sorted(c["value"] for c in st["cookies"]) == ["SECRET-SHOP", "v"], st["cookies"]
    assert [o["origin"] for o in st["origins"]] == ["https://shop.example.com"]
    blob = json.dumps(st)
    assert "BANK" not in blob and "evil" not in blob
    line = audit.tail(1)[-1]
    assert line["op"] == "browser.export_session" and line["path"] == "example.com"
    assert line["detail"]["message"] == "session exported for example.com"
    assert line["detail"]["cookies"] == 2 and line["detail"]["origins"] == 1
    assert "SECRET" not in json.dumps(line) and "sid" not in json.dumps(line), "counts only in the audit"


def test_an_open_window_on_the_daemons_profile_is_read_live(ws_root, monkeypatch):
    from daemon import browser
    from daemon.relay import session_export

    class Ctx:
        async def storage_state(self):
            return json.loads(json.dumps(_STATE))
    monkeypatch.setattr(browser.WINDOWS, "_current",
                        {"task": "t", "profile": session_export.own_profile(), "context": Ctx()})
    out = session_export.export("shop.example.com")
    assert len(out["storage_state"]["cookies"]) == 2


def test_a_window_on_any_other_profile_is_never_exported(ws_root, monkeypatch):
    from daemon import browser
    from daemon.fs.refusal import Refusal
    from daemon.relay import session_export

    class Ctx:
        async def storage_state(self):
            raise AssertionError("another profile's session was read")
    monkeypatch.setattr(browser.WINDOWS, "_current",
                        {"task": "t", "profile": str(ws_root / "engine-profile"), "context": Ctx()})
    with pytest.raises(Refusal) as e:
        session_export.export("shop.example.com")
    assert e.value.code == "not_own_profile"


def test_a_session_over_two_megabytes_is_refused(ws_root, monkeypatch):
    from daemon.fs.refusal import Refusal
    from daemon.relay import session_export

    async def read(profile):
        return {"cookies": [{"name": f"c{i}", "value": "x" * 4000, "domain": ".example.com", "path": "/"}
                            for i in range(600)], "origins": []}
    monkeypatch.setattr(session_export, "READ_PROFILE", read)
    with pytest.raises(Refusal) as e:
        session_export.export("example.com")
    assert e.value.code == "too_large"


def test_export_crosses_the_relay_as_an_op(ws_root, monkeypatch):
    from daemon.relay import dispatch, session_export

    async def read(profile):
        return json.loads(json.dumps(_STATE))
    monkeypatch.setattr(session_export, "READ_PROFILE", read)
    out = dispatch.handle({"id": "e", "op": "browser.export_session", "args": {"site": "shop.example.com"}})
    assert out["ok"] and out["data"]["domain"] == "example.com"
