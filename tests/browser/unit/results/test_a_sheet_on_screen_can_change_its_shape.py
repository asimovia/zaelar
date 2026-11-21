"""«Compare them visually» over a results sheet already on screen (demo run, 2026-09-26): the agent promised to put
the three monitors side by side and had no way to — a template could only arrive with `present`, re-sending
every item. `layout` re-shapes what is there, keeps every item, and returns to the results list."""
import pytest


@pytest.fixture
def rs(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.results import data as d
    assert d.apply_action("present", {"items": [{"title": "Dell S2721QS", "price": "$214"},
                                                {"title": "LG 27UP850K", "price": "$289"},
                                                {"title": "MSI 27 4K", "price": "$163"}]}).get("ok") is not False
    return d


def test_the_sheet_takes_a_new_shape_and_keeps_its_items(rs):
    got = rs.apply_action("layout", {"layout": "tile"})
    assert got["ok"] and got["layout"] == "tile" and got["items"] == 3
    v = rs.view_data()
    assert v["layout"] == "tile" and [i["title"] for i in v["items"]][0] == "Dell S2721QS"


def test_an_unknown_shape_teaches_the_choices(rs):
    got = rs.apply_action("layout", {"layout": "pie chart"})
    assert not got["ok"] and "tile" in got["error"]


def test_the_action_is_declared_so_the_brain_can_choose_it():
    import json
    import pathlib
    m = json.loads((pathlib.Path(__file__).resolve().parents[4] / "widgets/results/manifest.json").read_text())
    assert "compare them visually" in m["actions"]["layout"]["desc"]
    assert m["actions"]["detail"]["desc"].startswith("OPENS ONE result in full («open the best value option»")


@pytest.mark.parametrize("said, shape", [("table", "compare"), ("side_by_side", "compare"), ("Comparison", "compare"), ("grid", "tile")])
def test_a_shape_named_by_a_declared_alias_is_that_shape_for_the_act_and_its_end_state(rs, said, shape):
    """Demo sandbox 2026-11-17, S2: «compare them side by side» → `layout: "table"`, then `"side_by_side"` — refused, and
    «I couldn't get that done» over the sheet on screen. The manifest declares the aliases (`widgets.enums`, V2-754);
    the act and the end state (`spec.render` → `spec_call`) read that one declaration. Disarm: drop the aliases from the
    manifest's `layout` payload → the act refuses and the clause still owes the raw word."""
    got = rs.apply_action("layout", {"layout": said})
    assert got["ok"] and got["layout"] == shape, got
    from nucleo.circuit import spec
    clause = spec.render("results", "layout", {"layout": said})
    assert clause and clause.get("is") == shape, clause


def test_his_words_still_name_one_shape_when_the_call_carries_none():
    """Pass 4 of 2026-11-17: an alias «side by side» on `tile` made «compare them side by side» name TWO shapes, so the
    words no longer filled a call that carried only `mode` (`enum_fill`) — the aliases must not make his phrase ambiguous."""
    from nucleo.acts import payload_fill
    assert payload_fill.enum_fill("results", "layout", "compare them side by side") == {"layout": "compare"}
