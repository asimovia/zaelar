"""V2-879 O3 — a reader of the sheet tells what the sheet KEPT, never what a producer wrote.

Measured in the lab (en, 2026-11-11): «find me coffee shops near me» ran the listing fast pass; the sheet's door
(the category gate) filed all eight rows in Rejected, and the turn said «I found eight results… They're in your
sheet». The pass counted the ladder's own list, so the face was told «delivered, 8 real listings already on his
sheet» over a list of zero — and no deeper search was handed on.

The real `fast_pass`, the real sheet and its real door; only the network ladder, the errand row, the canvas and the
picture fetcher are stubbed. Asserts the PROPERTY (what is reported equals what the sheet holds), never wording.
"""
from __future__ import annotations

import pytest

from memory import db as memdb
from memory import embeddings as mememb
from nucleo.acts import search_listing as SL
from nucleo.acts import search_sheet as SS
from widgets import store
from widgets.results import data as sheet

SID = "results--o3test"

# Index pages: the sheet's door files every one as «a listing index, not one offer» (search/row_fit).
_INDEX = [{"title": f"Coffee shops in San Francisco, page {i} — see all {40 + i}",
           "url": f"https://www.example-guide.com/sf/coffee?page={i}", "source": "example-guide.com"}
          for i in range(1, 9)]
_REAL = [{"title": t, "url": f"https://www.example-cafe.com/{i}", "source": "example-cafe.com",
          "location": "Mission, San Francisco"}
         for i, t in enumerate(("Blue Bottle Coffee Mint Plaza", "Sightglass Coffee 7th St", "Ritual Coffee Valencia"))]


@pytest.fixture
def pass_over(monkeypatch, tmp_path):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    mememb.reset()
    memdb.reset_db()
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path / "widgets"))
    monkeypatch.setattr("widgets.results.media.jobs", lambda data: [])
    monkeypatch.setattr("nucleo.acts.canvas.apply", lambda *a, **kw: None)
    monkeypatch.setattr("nucleo.acts.errand.born", lambda asked, ctx=None: (0, SID))
    handed: list = []
    monkeypatch.setattr(SS, "_hand_on", lambda delivered, asked, sid, n, errand_id=0, uid="":
                        handed.append((delivered, n)) or (0 if delivered else 77))

    def run(items: list[dict]) -> tuple[dict, list]:
        import search.listing as LS
        monkeypatch.setattr(LS, "search", lambda q: {"items": items, "needs_browser": False,
                                                    "sources": [{"tier": "serp", "target": "web", "status": "ok"}]})
        return SS.fast_pass("coffee shops in San Francisco", operator_text="find me coffee shops near me"), handed

    yield run
    memdb.reset_db()
    mememb.reset()


def test_a_pass_whose_every_row_was_rejected_reports_no_findings(pass_over):
    res, handed = pass_over(_INDEX)
    held = sheet.holding(SID)
    assert held["state"] == sheet.HELD_REJECTED and held["kept"] == 0 and held["rejected"] == 8, held
    assert res["n"] == 0 and not res["delivered"], f"the pass reported the ladder's rows, not the sheet's: {res}"
    assert res["rejected"] == 8 and not res["ctx"].strip()
    assert handed == [(False, 0)], "nothing was kept, so the hunt is handed on, not closed as delivered"
    face = SL.compose_face(res, "find me coffee shops near me")
    assert "ANUNCIOS ENCONTRADOS" not in face and "PROVISIONALES" not in face, "the face names rows he does not have"
    assert "8 DESCARTADOS" in face, "the face is not told what the sheet filed away"


def test_a_pass_reports_only_the_rows_the_sheet_kept(pass_over):
    res, _ = pass_over(_REAL + _INDEX[:5])
    held = sheet.holding(SID)
    assert held["state"] == sheet.HELD_KEPT and held["kept"] == 3 and held["rejected"] == 5, held
    assert res["delivered"] and res["n"] == 3 and res["rejected"] == 5
    assert "Ritual Coffee" in res["ctx"] and "see all" not in res["ctx"], "a rejected row reached the face's rows"


def test_an_untouched_sheet_holds_nothing(pass_over):
    assert sheet.holding("results--never") == {"state": sheet.HELD_NONE, "kept": 0, "rejected": 0, "rows": []}
