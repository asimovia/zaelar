"""The daemon opens ONE sign-in window on a persistent profile and reports progress without the secret (V2-575 P2).

The engine asks for a window (`/browser/open`), watches it (`/browser/state`) and closes it (`/browser/close`). The
state answers the page's URL and HOW MANY cookies appeared since the window opened — enough to tell «signed in» from
«still on the form» — and never a cookie, a cookie name or a value. The capability `browser.auth` is declared only
when a browser is really there to open.

The Chromium is a fake injected through the launcher seam, so the contract runs in milliseconds; the routes run over a
real HTTP daemon on an ephemeral port with its token.
Disarms: the baseline not subtracted (every pre-existing cookie counted as new) → red; the cookie NAMES leaked into
the state → red.
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

import pytest


class _Page:
    def __init__(self, ctx):
        self.ctx, self.url = ctx, "about:blank"

    async def goto(self, url, timeout=0):
        self.url = url

    async def bring_to_front(self):
        return None


class _Ctx:
    def __init__(self, cookies):
        self._cookies = list(cookies)
        self.pages = []
        self.closed = False

    async def new_page(self):
        p = _Page(self)
        self.pages.append(p)
        return p

    async def cookies(self):
        return [dict(c) for c in self._cookies]


@pytest.fixture
def fake(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    from daemon.browser import window
    launched: list = []

    async def launcher(profile):
        ctx = _Ctx([{"domain": ".shop.example", "name": "consent", "value": "old"}])
        launched.append((str(profile), ctx))

        async def stop():
            ctx.closed = True
        return ctx, stop
    w = window.Windows(launcher=launcher)
    yield w, launched, tmp_path
    w.close()


def test_the_window_opens_counts_new_cookies_and_never_names_them(fake):
    w, launched, _ = fake
    out = w.open("t1", "https://shop.example/login")
    assert out == {"ok": True, "task": "t1", "open": True}
    profile, ctx = launched[0]
    assert profile.endswith("config/daemon/browser/profile"), f"the default profile is the daemon's own: {profile}"
    s = w.state("t1")
    assert s["open"] and s["url"] == "https://shop.example/login" and s["new_cookies"] == 0, \
        f"a cookie that was there before the window opened is not a sign-in: {s}"
    ctx._cookies.append({"domain": ".shop.example", "name": "session-id", "value": "SECRET"})
    ctx.pages[0].url = "https://shop.example/account"
    s = w.state("t1")
    assert s["new_cookies"] == 1 and s["url"].endswith("/account"), s
    blob = json.dumps(s)
    assert "SECRET" not in blob and "session-id" not in blob and "consent" not in blob, \
        f"the state carries no cookie value or name: {blob}"
    w.close("t1")
    assert ctx.closed and w.state("t1")["open"] is False


def test_a_window_he_closed_reads_as_closed(fake):
    w, launched, _ = fake
    w.open("t1", "https://shop.example/login")
    launched[0][1].pages.clear()                               # he closed the window
    s = w.state("t1")
    assert s["open"] is False and s.get("closed_by_user"), s


def test_one_window_at_a_time(fake):
    w, launched, _ = fake
    w.open("a", "https://one.example/login")
    w.open("b", "https://two.example/login")
    assert launched[0][1].closed, "opening task b's window closed task a's"
    assert w.state("a")["open"] is False and w.state("b")["open"] is True


@pytest.mark.parametrize("url", ["file:///etc/passwd", "javascript:alert(1)", "shop.example/login", ""])
def test_only_http_addresses_open(fake, url):
    from daemon.fs.refusal import Refusal
    w, _, _ = fake
    with pytest.raises(Refusal) as e:
        w.open("t1", url)
    assert e.value.code == "bad_url"


def test_a_named_profile_must_be_absolute_and_symlink_free(fake):
    from daemon.fs.refusal import Refusal
    w, launched, tmp = fake
    real = tmp / "engine-profile"
    w.open("t1", "https://shop.example/login", str(real))
    assert launched[-1][0] == str(real), "the engine on this computer names its own profile and gets it"
    link = tmp / "link"
    link.symlink_to(tmp)
    for bad in ("relative/profile", str(link / "p"), str(tmp / "x" / ".." / "y")):
        with pytest.raises(Refusal) as e:
            w.open("t2", "https://shop.example/login", bad)
        assert e.value.code == "bad_profile", bad


def test_the_capability_is_measured_never_declared(monkeypatch):
    from daemon.browser import window
    from daemon.http import routes
    monkeypatch.setattr(window, "_chromium_on_disk", lambda: True)
    monkeypatch.delenv("ZAELAR_DAEMON_BROWSER", raising=False)
    assert window.available() == (window.importlib.util.find_spec("playwright") is not None)
    assert ("browser.auth" in routes.capabilities()) == window.available()
    monkeypatch.setenv("ZAELAR_DAEMON_BROWSER", "0")
    assert not window.available() and "browser.auth" not in routes.capabilities()
    monkeypatch.delenv("ZAELAR_DAEMON_BROWSER")
    monkeypatch.setattr(window, "_chromium_on_disk", lambda: False)
    assert not window.available(), "no Chromium on disk → no window promised"


def test_the_routes_serve_the_window_behind_the_token(fake, monkeypatch):
    from daemon import browser, config as dcfg, server as dsrv
    w, launched, _ = fake
    monkeypatch.setattr(browser, "WINDOWS", w)
    dcfg.reset_cache()
    srv = dsrv.build(port=0)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    def post(path, body, token=True):
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(body).encode(),
                                     method="POST", headers={"Content-Type": "application/json", "Host": f"127.0.0.1:{port}",
                                                             **({"Authorization": f"Bearer {dcfg.token()}"} if token else {})})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")
    try:
        assert post("/browser/open", {"task": "t1", "url": "https://shop.example/login"}, token=False)[0] == 401
        status, body = post("/browser/open", {"task": "t1", "url": "https://shop.example/login"})
        assert status == 200 and body["open"], body
        status, body = post("/browser/state", {"task": "t1"})
        assert status == 200 and body["new_cookies"] == 0 and body["open"], body
        status, body = post("/browser/open", {"task": "t1", "url": "ftp://x"})
        assert status == 403 and body["error"] == "bad_url", (status, body)
        assert post("/browser/close", {"task": "t1"})[1]["open"] is False
        from daemon import audit
        ops = [e.get("op") for e in audit.tail(50)]
        assert "browser.open" in ops and "browser.close" in ops, ops
        assert not any("login" in json.dumps(e) for e in audit.tail(50) if e.get("op") == "browser.open"), \
            "the audit keeps the HOST, never the full address"
    finally:
        srv.shutdown(); srv.server_close(); dcfg.reset_cache()
