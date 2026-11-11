"""A video whose owner refuses embedding is never OFFERED as playable (V2-877 #6).

A search put a video on the catalog, the embed refused it (150), the card swapped and said «blocked by its owner —
playing the next one». YouTube's public oEmbed endpoint already says so before anyone presses play: 401 when the owner
disabled embedding, 404 when the video is removed or private. `embed_check` asks it for the search hits; the refused ones
join the player's own blocklist and never reach the catalog or a «play X». An unanswered check keeps the hit (fail-open).
"""
import io
import urllib.error
import urllib.request

import pytest

from widgets import store
from widgets.youtube import availability, embed_check
from widgets.youtube import data as yt

_HTML = "".join(
    '{"videoRenderer":{"videoId":"%s","title":{"runs":[{"text":"%s"}]}}}' % (v, t)
    for v, t in (("AAAAAAAAAA1", "Golden Gate Modern Marvels"), ("BBBBBBBBBB2", "Golden Gate FD Engineering"),
                 ("CCCCCCCCCC3", "Golden Gate timelapse")))


def _oembed(statuses):
    """urlopen stand-in: the results page for a search, the given HTTP status for each oEmbed lookup."""
    def opener(req, timeout=6):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "oembed" not in url:
            return io.BytesIO(_HTML.encode())
        vid = urllib.request.unquote(url).rsplit("v=", 1)[1]
        st = statuses.get(vid, 200)
        if st == "down":
            raise urllib.error.URLError("network down")
        if st != 200:
            raise urllib.error.HTTPError(url, st, "refused", {}, io.BytesIO(b""))
        return _Resp()
    return opener


class _Resp:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return b"{}"


@pytest.fixture
def sandbox(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ZAELAR_EMBED_CHECK", "1")
    return monkeypatch


def test_oembeds_refusal_is_read_as_the_players_own_code(sandbox):
    sandbox.setattr(urllib.request, "urlopen", _oembed({"AAAAAAAAAA1": 401, "BBBBBBBBBB2": 404, "CCCCCCCCCC3": 200}))
    assert embed_check.refused(["AAAAAAAAAA1", "BBBBBBBBBB2", "CCCCCCCCCC3"]) == {"AAAAAAAAAA1": "150",
                                                                                "BBBBBBBBBB2": "100"}


def test_an_unanswered_check_never_hides_a_video(sandbox):
    sandbox.setattr(urllib.request, "urlopen", _oembed({"AAAAAAAAAA1": "down", "BBBBBBBBBB2": 503}))
    assert embed_check.refused(["AAAAAAAAAA1", "BBBBBBBBBB2"]) == {}


def test_the_catalog_never_shows_a_refused_video_and_remembers_it(sandbox):
    sandbox.setattr(urllib.request, "urlopen", _oembed({"AAAAAAAAAA1": 401}))
    r = yt.apply_action("search", {"query": "golden gate"})
    assert r["ok"] and r["count"] == 2
    d = yt.view_data()
    assert [it["videoId"] for it in d["search_results"]] == ["BBBBBBBBBB2", "CCCCCCCCCC3"]
    assert "AAAAAAAAAA1" in availability.blocked_ids(d), "on the player's blocklist: no later search offers it"


def test_play_x_lands_on_the_first_video_that_can_play_here(sandbox):
    sandbox.setattr(urllib.request, "urlopen", _oembed({"AAAAAAAAAA1": 401}))
    assert yt._search_id("golden gate")["videoId"] == "BBBBBBBBBB2"


def test_the_suite_stays_off_the_network_by_default(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_CHECK", "0")
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: pytest.fail("network reached"))
    assert embed_check.refused(["AAAAAAAAAA1"]) == {}
