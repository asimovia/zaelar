"""The files card says the section, the folder and the file open on each screen (V2-884 C8 step 5).

Shared: the computer can stand in one folder while the phone stands in another, and the viewer a double-click opens
is the card's own (`ui.preview`), never in the store — «what's in this one?» was unanswerable. The card says
`section`, `folder` (the trail's last step, "" = the top) and `open` (the file in its viewer) after every paint; a
folder or section change is `?ordered` on each screen until it acks. Two screen pairs; the rendered card through the
real reporter into the real door. Invented files. Disarms (named in the test): the card that never reports → `state
unreported`; `folder` following only the folder id → a provider switch reads as the old folder confirmed.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from voice import screens
from widgets import state, state_decl, state_render, store
from tests.browser.unit.widgets.state_card import card_page, deliver, mount, posts, push  # noqa: F401

ENGINE = pathlib.Path(__file__).resolve().parents[4]
PAIRS = [("desktop:aaa", "mobile:bbb"), ("desktop:aaa", "desktop:bbb")]
TRAIL = [{"id": "f1", "name": "Viajes"}, {"id": "f2", "name": "Lisboa 2024"}]


@pytest.fixture
def files(tmp_path, monkeypatch):
    from server import canvas_api
    from widgets.archivos import data
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    state._reset_for_tests()
    screens._reset_for_tests()
    store.save("archivos", {**data._load(), "section": "biblioteca", "folder_id": "f2", "trail": TRAIL, "updated": 1,
                            "entries": [{"id": "e1", "name": "plano.pdf", "kind": "file", "provider": "local"}]})

    def on(a, b):
        for d in (a, b):
            screens.attach(d)
        monkeypatch.setattr(canvas_api, "_BY_DEV", {a: {"open": ["archivos"]}, b: {"open": ["archivos"]}})
    yield data, on
    state._reset_for_tests()
    screens._reset_for_tests()


def _say(dev, n, full=False, **fields):
    return state.report("archivos", {"dev": dev, "mount": "m1", "n": n, "full": full or n == 1, "patch": fields,
                                     "ack": state.stamp("archivos")})[0]


def test_the_files_card_declares_its_state_and_it_is_shared():
    man = json.loads((ENGINE / "widgets/archivos/manifest.json").read_text())
    assert man["screens"] == "shared" and state_decl.problem(man) is None and "adopt" not in json.dumps(man["state"])


@pytest.mark.parametrize("a,b", PAIRS)
def test_two_screens_each_its_folder_and_a_move_waits_for_each_ack(files, a, b):
    data, on = files
    on(a, b)
    assert state_render.clause("archivos") == "archivos: state unreported"
    assert _say(a, 1, section="biblioteca", folder="Lisboa 2024", open="plano.pdf") == 200
    assert _say(b, 1, section="torrents", folder="", open="") == 200
    assert state_render.clause("archivos", dev=a).endswith(': folder="Lisboa 2024", open="plano.pdf"')
    assert state_render.clause("archivos", dev=b).endswith(": section=torrents")
    db = data._load(); db["provider"] = "gdrive"; store.save("archivos", db)        # another storage
    for d in (a, b):
        assert "folder=?ordered" in state_render.clause("archivos", dev=d), f"a provider switch read as shown on {d}"
    assert _say(a, 2, full=True, section="biblioteca", folder="", open="") == 200
    assert state_render.clause("archivos", dev=a).endswith(": at rest")
    assert "folder=?ordered" in state_render.clause("archivos", dev=b), "one screen's ack confirmed the other"


def test_the_rendered_card_says_its_folder_and_the_file_he_opened(files, card_page):
    data, on = files
    a, b = PAIRS[0]
    on(a, b)
    shown = {**data.view_data(), "needs_refresh": False, "providers_stale": False, "_rev": state.stamp("archivos")}
    mount(card_page, "archivos", shown, a)
    sent = posts(card_page)
    assert sent and sent[0]["full"] and sent[0]["patch"] == {"section": "biblioteca", "folder": "Lisboa 2024", "open": ""}
    deliver("archivos", sent)
    card_page.evaluate("() => { document.getElementById('w')._arxUi.preview = {name: 'plano.pdf', kind: 'pdf', url: ''}; }")
    push(card_page, shown)                                                            # his double-click's repaint
    sent = posts(card_page)
    assert sent and sent[-1]["patch"] == {"open": "plano.pdf"}, sent
    deliver("archivos", sent)
    assert state_render.clause("archivos", dev=a).endswith(': folder="Lisboa 2024", open="plano.pdf"')
