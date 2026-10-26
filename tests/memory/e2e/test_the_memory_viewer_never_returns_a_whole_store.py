"""The memory viewer never returns a whole store (V2-808).

The viewer used to read every row of `memories` and `edges` on each open and on every `memory.updated`. One install
is one person, but his store grows — weeks of conversation, an import of thousands of messages — and whatever device
opens the viewer has to draw what comes back. The contract, endpoint by endpoint:

  * every list is capped by the SERVER, whatever `limit` the client sends, and pages with a cursor that neither
    repeats nor skips a row;
  * totals are COUNTs that agree with what is stored, not the length of a page;
  * the graph is aggregated on the server and never has more nodes than the budget (itself clamped);
  * the old `/api/memory/map` is bounded too.

Fixture: 200.000 memories and 200.000 archived messages written straight into a temporary database — the size
of a heavy import — so «it is capped» and «it is fast» are measured on the volume that made them necessary.
Disarm (2026-10-26): with `memory.viewer.clamp_limit` returning the requested `limit` unclamped, the cap tests
went red (10.000 rows came back); with `archive.page` ordering by `id` instead of `(ts, id)`, the cursor test
went red (the backfilled rows were skipped).
"""
from __future__ import annotations

import os
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from memory import db as memdb
from memory import embeddings as mememb

N = 200_000


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    yield
    mememb.reset()


@pytest.fixture(scope="module")
def big(tmp_path_factory):
    """One database and one message archive with N rows each, shared by the module (writing them is the cost)."""
    root = tmp_path_factory.mktemp("viewer")
    mp = pytest.MonkeyPatch()
    mp.setenv("ZAELAR_DB", str(root / "zaelar.db"))
    from widgets import store
    mp.setattr(store, "DATA_DIR", str(root / "widgets"))
    from connectors.messaging import archive
    archive.reset()
    memdb.reset_db()
    db = memdb.get_db()
    now = int(time.time())
    kinds = ("fact", "pref", "event", "msg", "conv")
    texts = ("viaje a Soria con la familia", "reunión de trabajo con el cliente", "pagar la hipoteca del banco",
             "partido de pádel el jueves", "receta de la cena")
    rows = [(("short" if i % 3 == 0 else "long"), kinds[i % 5], f"{texts[i % 5]} #{i}", 0.5, (i % 10) / 10,
             now - (N - i) * 30, now - (N - i) * 30) for i in range(N)]
    with db._lock:
        db.conn.executemany("INSERT INTO memories(level, kind, text, importance, weight, created, updated) "
                            "VALUES (?,?,?,?,?,?,?)", rows)
        db.conn.commit()
    conn = archive._conn()
    plats = ("whatsapp", "telegram", "email")
    # ids follow insertion, ts does not: the second half is a BACKFILL of older messages inserted later.
    msgs = [(plats[i % 3], f"c{i % 50}", f"Chat {i % 50}", 0, f"P{i % 7}", "in" if i % 4 else "out",
             float(now - (i if i < N // 2 else N + i) * 10), f"mensaje número {i} sobre el presupuesto" if i % 1000 == 0
             else f"mensaje {i}", "", f"m{i}") for i in range(N)]
    conn.executemany("INSERT INTO messages(platform, chat_id, chat_name, is_group, sender, direction, ts, body, "
                     "media_type, msg_id) VALUES (?,?,?,?,?,?,?,?,?,?)", msgs)
    conn.commit()
    media = os.path.join(store.DATA_DIR, "mensajeria")
    os.makedirs(media, exist_ok=True)
    for i in range(150):
        with open(os.path.join(media, f"img_{i:04d}.jpg"), "wb") as fh:
            fh.write(b"x" * 10)
    from server import memory_viewer_api as mva
    mva._stats_cache.update(at=0.0, body=None)
    mva._media.update(at=0.0, rows=None)
    from memory import viewer
    viewer._cache.clear()
    app = FastAPI()
    app.include_router(mva.router)
    from server.memory_routes import router as map_router
    app.include_router(map_router)
    yield TestClient(app)
    archive.reset()
    memdb.reset_db()
    mp.undo()


def _timed(client, url):
    t0 = time.perf_counter()
    r = client.get(url)
    assert r.status_code == 200, r.text
    return r.json(), time.perf_counter() - t0


def test_a_list_never_returns_more_than_the_server_cap_however_much_is_asked(big):
    from memory.viewer import LIST_CAP
    body, secs = _timed(big, "/api/memory/viewer/facts?limit=10000")
    assert len(body["items"]) == LIST_CAP and body["more"] is True
    assert secs < 1.5, f"a capped page of a {N}-row store took {secs:.2f}s"
    body, _ = _timed(big, "/api/memory/viewer/conversation?limit=10000")
    assert len(body["items"]) == LIST_CAP
    body, secs = _timed(big, "/api/memory/viewer/messages?limit=10000")
    assert len(body["items"]) == 200 and body["more"] is True
    assert secs < 1.5, f"a capped page of a {N}-row archive took {secs:.2f}s"
    body, _ = _timed(big, "/api/memory/viewer/files?limit=10000")
    assert len(body["items"]) == 60 and body["total"] == 150


def test_the_cursor_neither_repeats_nor_skips_a_row(big):
    seen, cursor = [], 0
    for _ in range(4):
        body, _ = _timed(big, f"/api/memory/viewer/facts?limit=50&before_id={cursor}")
        seen += [m["id"] for m in body["items"]]
        cursor = body["next"]
    assert len(seen) == len(set(seen)) == 200
    assert seen == sorted(seen, reverse=True), "newest first"
    assert seen[0] - seen[-1] < 400, "consecutive pages are contiguous (only own-lane kinds in between)"


def test_the_message_cursor_follows_time_not_insertion_order(big):
    """A backfill inserts OLD messages late: paging by id would serve them before newer ones, or skip them."""
    got, nxt = [], None
    for _ in range(3):
        q = f"&before_ts={nxt['ts']}&before_id={nxt['id']}" if nxt else ""
        body, _ = _timed(big, f"/api/memory/viewer/messages?limit=200{q}")
        got += body["items"]
        nxt = body["next"]
    ts = [m["ts"] for m in got]
    assert ts == sorted(ts, reverse=True)
    assert len({m["id"] for m in got}) == 600


def test_search_runs_on_the_server(big):
    body, _ = _timed(big, "/api/memory/viewer/messages?q=presupuesto&limit=150")
    assert body["items"] and all("presupuesto" in m["body"] for m in body["items"])
    assert len(body["items"]) == 150 and body["more"]                # 200 match (every 1000th row): one page of them
    body, _ = _timed(big, "/api/memory/viewer/facts?q=hipoteca&limit=20")
    assert body["items"] and all("hipoteca" in m["text"] for m in body["items"])


def test_the_totals_are_counts_of_what_is_stored(big):
    body, secs = _timed(big, "/api/memory/viewer/stats")
    stores = {s["key"]: s for s in body["stores"]}
    assert stores["facts"]["total"] == N * 3 // 5                 # fact, pref, event — not msg, not conv
    assert stores["conversation"]["total"] == N // 5
    assert stores["messages"]["total"] == N
    assert sum(stores["messages"]["parts"].values()) == N
    assert stores["files"]["total"] == 150
    assert {"facts", "conversation", "messages", "files", "contacts", "agenda", "apps", "rules", "phrases",
            "events", "vault"} <= set(stores)
    assert secs < 3, f"the overview counts took {secs:.2f}s"


def test_the_graph_never_has_more_nodes_than_the_budget(big):
    from memory.viewer import BUDGET_MAX
    body, secs = _timed(big, "/api/memory/viewer/graph?days=0&budget=300")
    assert body["shown"]["nodes"] <= 300
    assert body["shown"]["nodes"] == len(body["concepts"]) + len(body["memories"])
    assert body["total"]["nodes"] > body["shown"]["nodes"], "the honest total is reported beside what is drawn"
    assert body["capped"] is True, "a window larger than the scan cap says so"
    assert secs < 5, f"the aggregation took {secs:.2f}s"
    body, _ = _timed(big, "/api/memory/viewer/graph?days=0&budget=1000000")
    assert body["budget"] == BUDGET_MAX and body["shown"]["nodes"] <= BUDGET_MAX
    keys = {c["key"] for c in body["concepts"]}
    assert all(set(m["c"]) <= keys for m in body["memories"]), "a memory hangs only from concepts that are drawn"
    assert all(lk["a"] in keys and lk["b"] in keys for lk in body["links"])


def test_one_concept_is_read_one_page_at_a_time(big):
    graph, _ = _timed(big, "/api/memory/viewer/graph?days=0&budget=300")
    key = graph["concepts"][0]["key"]
    p1, _ = _timed(big, f"/api/memory/viewer/concept?key={key}&days=0&limit=20")
    assert len(p1["items"]) == 20 and p1["more"] and p1["count"] > 20
    p2, _ = _timed(big, f"/api/memory/viewer/concept?key={key}&days=0&limit=20&before_id={p1['next']}")
    assert not {m["id"] for m in p1["items"]} & {m["id"] for m in p2["items"]}
    huge, _ = _timed(big, f"/api/memory/viewer/concept?key={key}&days=0&limit=100000")
    assert len(huge["items"]) <= 200


def test_the_old_map_is_bounded_too(big):
    body, secs = _timed(big, "/api/memory/map")
    from memory.api import MAP_CAP
    assert len(body["layers"]["short"]) <= MAP_CAP and len(body["layers"]["long"]) <= MAP_CAP
    assert body["counts"]["short"] + body["counts"]["long"] == N, "its totals are COUNTs, not the page"
    assert "state" in body
    assert secs < 2, f"the bounded map took {secs:.2f}s"
