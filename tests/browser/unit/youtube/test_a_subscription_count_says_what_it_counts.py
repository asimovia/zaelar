"""A count of «subscriptions» always says WHAT it counts, and the screen and the reply read the same list.

Session 3df07e48 (2026-11-19): «how many subscriptions do I have» ran `suggest`, whose answer carried a bare
`channels: 50` — the CAP of the account read, not a count — and the reply was «you have 50 subscriptions». The
Subscriptions tab listed the ONE channel followed in the widget, and the next reply carried both figures at once.

Three seams, one per test: the client reports the provider's total apart from the capped rows; the facade's
`channels` is the channels that really fed the band; and the op answers through a declared `result` where every
figure is named, with the tab answering from the same list it renders.

Disarm: `suggest` answering without its `result` turns the second test red (the bare counts reach the reply again);
`tab_answer.result` without its `subs` branch turns the third red; dropping `total` from
`youtube.list_subscriptions` turns the first red.
"""
from __future__ import annotations

from connectors.video import service
from connectors.video import youtube as ytc
from nucleo.acts import data_ops
from widgets.youtube import data as yt  # noqa: F401 — the package loads through `data`
from widgets.youtube import account, tab_answer


class _R:
    status_code = 200

    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


class _Client:
    def __init__(self, pages):
        self.pages = list(pages)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, url, params=None, headers=None, timeout=None):
        return self.pages.pop(0)


def _page(n, total, more):
    items = [{"snippet": {"title": f"Channel {i}", "resourceId": {"channelId": f"UC{i:04d}"}}} for i in range(n)]
    return _R({"items": items, "pageInfo": {"totalResults": total}, **({"nextPageToken": "p2"} if more else {})})


def test_a_capped_read_reports_the_providers_total_not_its_own_length():
    r = ytc.list_subscriptions(_Client([_page(50, 312, True)]), "https://api", "tok", max_n=50)
    assert len(r["channels"]) == 50 and r["total"] == 312
    # A listing that ended before the cap was read whole: its length IS the total, said or not.
    whole = _Client([_R({"items": [{"snippet": {"title": "One", "resourceId": {"channelId": "UCa"}}}]})])
    assert ytc.list_subscriptions(whole, "https://api", "tok", max_n=50)["total"] == 1
    # Cut short with no figure from the provider: nobody knows, and None says so.
    cut = _R({"items": _page(50, 0, True)._body["items"], "nextPageToken": "p2"})
    assert ytc.list_subscriptions(_Client([cut]), "https://api", "tok", max_n=50)["total"] is None


def test_the_op_answers_with_named_counts_and_never_a_bare_one(monkeypatch):
    class _P:
        id, label, api_base = "youtube", "YouTube", "https://api"
    monkeypatch.setattr(service, "_prepared", lambda pid: (_P, "tok", None))
    monkeypatch.setattr(ytc, "channel_recent_uploads", lambda *a, **k: [])
    import httpx
    monkeypatch.setattr(httpx, "Client", lambda *a, **k: _Client([_page(50, 312, True)]))
    r = service.suggestions("youtube")
    assert r["channels"] == service._MAX_CHANNELS and r["subscriptions"] == 312

    class _Svc:
        available = staticmethod(lambda: True)
        status = staticmethod(lambda: {"ok": True, "providers": [{"id": "youtube", "connected": True}]})
        suggestions = staticmethod(lambda platform: r)
    monkeypatch.setattr(account, "_svc", lambda: _Svc)
    monkeypatch.setattr(account.store, "save", lambda *a, **k: None)
    db = {"channels": [{"name": "SpaceX"}]}
    said = data_ops.answer_of(account.apply("suggest", {}, db))
    assert set(said) == {"result"}                                  # nothing unnamed reaches the reply
    res = said["result"]
    assert res["channels_followed_in_widget"] == 1 and res["account_subscriptions_total"] == 312
    assert res["account_channels_read_for_suggestions"] == service._MAX_CHANNELS
    assert 50 not in [v for v in res.values() if isinstance(v, int)]   # the cap is not a fact about him
    # A total the provider did not say stays unknown instead of being stood in for by the rows read.
    r.pop("subscriptions")
    assert account.apply("suggest", {}, db)["result"]["account_subscriptions_total"] is None


def test_the_subscriptions_face_answers_with_the_list_it_renders():
    db = {"channels": [{"name": "SpaceX"}]}
    res = tab_answer.result(db, "subs")
    assert res == {"channels_followed_in_widget": ["SpaceX"], "total": 1}
    assert res["total"] == len(yt.channels.cards(db))               # the same rows the tab draws
