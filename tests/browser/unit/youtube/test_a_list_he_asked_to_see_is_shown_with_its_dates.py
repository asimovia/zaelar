"""V2-791 · A list of videos he asked to SEE ends on screen, and every video carries when it was published.

Measured (one session): a weekly show loaded by name, and «¿has comprobado que el vídeo sea el de hoy?» could not
be answered — the title repeats every week and nothing the model read carried a date (the player line, the queue
items, the op's result). Then «ábreme su pestaña de vídeos para ver las fechas» → `channel_videos` filled the
queue BEHIND the player face: an op that ran and that nobody saw, four times.

  · the one door where an answer fills the queue (`library._fill_list`: a channel, the history, a saved list)
    brings the queue face forward on the card's `goto_tab` rail — another domain than the measured one (history,
    saved lists) rides the same door;
  · the publication date rides the player line of the digest, the search band, the queue items' hints, the op
    results, and the queue rows on the card.
"""
from __future__ import annotations

import io
import json
import urllib.request

import pytest

from widgets import refs, store
from widgets.youtube import data as yt

_HITS = [{"videoId": "AAAAAAAAAA%d" % i, "title": "Las 4 claves de la semana %d" % i,
          "channel": "José Luis Cárpatos", "published": p} for i, p in enumerate(
              ["hace 3 horas", "hace 1 semana", "hace 2 semanas"], 1)]


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=6: io.BytesIO(
        json.dumps({"title": "Vídeo", "author_name": "Canal"}).encode()))
    monkeypatch.setattr(yt, "_search_many", lambda q, n=5: [dict(h) for h in _HITS])
    from i18n import langs
    monkeypatch.setattr(langs, "current_code", lambda: "es")


def _face():
    return (yt.view_data().get("goto_tab") or {}).get("tab")


def test_a_channels_latest_videos_are_shown_not_filled_behind_the_player():
    yt.apply_action("load", {"query": "Cárpatos cuatro claves de la semana"})
    assert _face() == "player"
    r = yt.apply_action("channel_videos", {"channel": "José Luis Cárpatos"})
    assert r["ok"] and r["count"] == 3
    assert _face() == "cola", "the list he asked to see stayed behind the player"


def test_every_door_that_answers_with_videos_shows_them():
    """The class, not the measured op: the history and a saved list fill the same queue through the same door."""
    yt.apply_action("load", {"videoId": "AAAAAAAAAA1"})
    yt.apply_action("show_history", {})
    assert _face() == "cola"
    yt.apply_action("save_list", {"name": "la de la tarde"})
    yt.apply_action("load", {"videoId": "AAAAAAAAAA2"})
    assert _face() == "player"
    yt.apply_action("open_list", {"name": "la de la tarde"})
    assert _face() == "cola"


def test_the_channel_result_says_when_each_video_was_published():
    r = yt.apply_action("channel_videos", {"channel": "José Luis Cárpatos"})
    assert [v["published"] for v in r["videos"]] == ["hace 3 horas", "hace 1 semana", "hace 2 semanas"]


def test_the_loaded_video_says_when_it_was_published():
    r = yt.apply_action("load", {"query": "Cárpatos cuatro claves de la semana"})
    assert r["published"] == "hace 3 horas", "the op's own result must carry the date"
    assert "publicado «hace 3 horas»" in yt.prompt_digest(), "and so must what the brain reads of the player"


def test_the_queue_items_carry_their_dates_for_the_brain():
    yt.apply_action("channel_videos", {"channel": "José Luis Cárpatos"})
    hints = [i["hint"] for i in yt.ref_index()]
    assert all(any(d in h for d in ("hace 3 horas", "hace 1 semana", "hace 2 semanas")) for h in hints), hints
    assert "hace 3 horas" in refs.items_line("youtube")


def test_the_search_band_carries_the_dates():
    yt.apply_action("search", {"query": "Cárpatos claves"})
    assert "hace 1 semana" in yt.prompt_digest()


def test_the_card_shows_the_date_on_each_queue_row(tmp_path):
    """RENDERED: the queue row's subtitle carries the date beside the channel, on the face the op brought forward."""
    pytest.importorskip("playwright.sync_api")
    import pathlib
    import socket
    import subprocess
    import sys

    from playwright.sync_api import sync_playwright
    yt.apply_action("channel_videos", {"channel": "José Luis Cárpatos"})
    data = yt.view_data()
    engine = pathlib.Path(__file__).resolve().parents[4]
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=engine, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    from tests.waiting import port_listening
    port_listening(port)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page.route("**://i.ytimg.com/**", lambda r: r.fulfill(status=200, content_type="image/gif", body=b"GIF89a"))
            page.goto(f"http://127.0.0.1:{port}/widgets/youtube/")
            page.set_content("<div id='w' style='width:660px'></div>")
            page.evaluate("""async ([src, data]) => { const mod = await import(src);
                 mod.render(document.getElementById('w'), data,
                            {action: () => Promise.resolve({ok: true}), top: () => {}, running: true}); }""",
                          [f"http://127.0.0.1:{port}/widgets/youtube/widget.js", json.loads(json.dumps(data))])
            assert "hb-yt-t-cola" in page.evaluate("() => document.querySelector('.hb-yt').className")
            subs = page.eval_on_selector_all(".hb-yt-row .hb-yt-rowc", "els => els.map(e => e.textContent)")
            browser.close()
    finally:
        srv.terminate()
    assert subs[:3] == ["José Luis Cárpatos · hace 3 horas", "José Luis Cárpatos · hace 1 semana",
                        "José Luis Cárpatos · hace 2 semanas"], subs
