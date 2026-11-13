"""Asking whether an instance exists never CREATES it on disk (V2-884, step-3 audit P2-1).

Measured by the audit: `GET /widgets/agenda/data?q=make it blue please` left `_data/agenda--makeitblueplease/`, and five
browser task tabs left `navegador--t1…t5` — the data route, the state door and the facts reader asked `store.exists`,
which builds the folder (and runs the legacy-file move) before it looks. `q` is free text on real paths (the generator
re-renders with a change request as `q`; every task tab fetches `?q=tN`). Now the three ask `store.has_state`, which only
looks. Declared, not this mechanism: the results app's own read of a sheet (`view_data(q)` → `store.load`) still builds
that sheet's folder, as it did before V2-884. Disarm (named in the test): `has_state` built on `exists` → folders back.
"""
from __future__ import annotations

import os

import pytest

from voice import screens
from widgets import state, store


@pytest.fixture
def disk(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    state._reset_for_tests()
    screens._reset_for_tests()
    store.save("results", {"items": []})
    yield tmp_path
    state._reset_for_tests()
    screens._reset_for_tests()


def _folders(root) -> set[str]:
    return {p for p in os.listdir(root) if os.path.isdir(os.path.join(root, p))}


def test_a_free_query_and_a_made_up_instance_leave_no_folder(disk, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from widgets import server_api
    before = _folders(disk)
    app = FastAPI()
    app.include_router(server_api.router)
    c = TestClient(app)
    for wid, q in (("agenda", "make it blue please"), ("navegador", "t5"), ("contactos", "ana")):
        assert c.get(f"/widgets/{wid}/data", params={"q": q}).status_code == 200
    screens.attach("desktop:aaa")
    for inst in ("navegador::t9", "agenda::x", "results::ghost2"):
        code, _out = state.report(inst.split("::")[0], {"instance": inst, "dev": "desktop:aaa", "mount": "m1", "n": 1,
                                                        "full": True, "patch": {}})
        assert code == 400, f"{inst} was accepted"
    made = {f for f in _folders(disk) - before if "--" in f}           # an app's own folder is its; an instance's is not
    assert not made, f"asking about an instance created it on disk: {sorted(made)}"


def test_has_state_answers_what_is_there(disk):
    assert store.has_state("results") and not store.has_state("results--nothing") and not store.has_state("")
    (disk / "legacyapp.json").write_text("{}")
    assert store.has_state("legacyapp"), "a legacy flat store is a store"
    assert not os.path.exists(disk / "legacyapp"), "looking moved the legacy file"


def test_reading_the_facts_of_an_instance_without_a_store_creates_none(disk):
    from widgets import state_decl, state_render
    assert state_render._facts("youtube", "youtube::nope", state_decl.of("youtube"), {"playing": True}) == []
    assert not os.path.exists(disk / "youtube--nope"), "reading facts built the instance's folder"
