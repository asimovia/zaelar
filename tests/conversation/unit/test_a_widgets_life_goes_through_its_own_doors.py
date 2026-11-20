"""A widget's life and pictures go through their own doors (node 13.130, INI-078 F2 step 7): building one is an errand
of kind `code` (the dispatch door asks his yes, C4); deleting or restoring one asks his yes on its row through the one
asker, the question the language pack's own line; a name it opens by goes through `widgets.aliases`; a widget no
manifest declares is never touched."""
from __future__ import annotations

from nucleo.conversation_host import acts_life


def test_delete_and_restore_ask_on_their_row_and_build_is_a_code_errand(monkeypatch):
    from nucleo.acts import errand
    from nucleo.flash import widget_read
    from nucleo.request import consent_ask
    from widgets import lifecycle
    asked, born = [], {}
    monkeypatch.setattr(widget_read, "resolve", lambda named, text="": "w_notes" if named == "w_my_notes" else None)
    monkeypatch.setattr(lifecycle, "restorable_id", lambda t: "w_notes" if t else "")
    monkeypatch.setattr(consent_ask, "ask_consent", lambda w, k, p, q, **kw: asked.append((w, k, kw.get("kind"))) or
                        ("row1", "a1"))
    monkeypatch.setattr(errand, "escalate_to_slowbrain", lambda req, context=None: born.update(req=req, **context) or 9)
    assert acts_life.run("delete", {"widget": "w_my_notes"}).data["waits_for"] == "his yes"
    assert acts_life.run("restore", {"widget": "w_my_notes"}).status == "ok"
    assert asked == [("w_notes", "delete", "delete"), ("w_notes", "restore", "restore")]
    assert acts_life.run("delete", {"widget": "w_nothing"}).status == "failed" and len(asked) == 2
    assert acts_life.run("build", {"request": "w_a_tracker"}).data == {"task": 9} and born["kind"] == "code"


def test_a_name_a_widget_opens_by_goes_through_its_aliases(monkeypatch):
    from nucleo.flash import widget_read
    from widgets import aliases
    monkeypatch.setattr(widget_read, "resolve", lambda named, text="": "w_notes")
    monkeypatch.setattr(aliases, "add", lambda w, a: {"ok": True, "added": a})
    got = acts_life.run("alias", {"widget": "w_notes", "alias": "w_jotter"})
    assert got.status == "ok" and got.data == {"widget": "w_notes", "alias": "w_jotter", "added": "w_jotter"}
