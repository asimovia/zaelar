"""An errand the manager starts carries what the model decided about it (node 13.135, INI-078 F2 F5): the old turn's
brief gave it its kind, its consent class, its surface and the act it starts with, and the manager has no brief — so
`start_task` declares them, their choices read from the modules that own them (never copied), and the errand's
context carries them at the model's word, with his words; the worker's first step is the declared action it named; a
widget the model orders built starts with no «shall I?» (C4: a sure order), a changed one as a change."""
from __future__ import annotations

from nucleo.conversation_host import acts, acts_life, acts_tasks, routing


def test_start_tasks_choices_are_the_owners_and_the_errand_carries_the_models_reading(monkeypatch):
    from nucleo.acts import errand
    from nucleo.request import kind
    from nucleo import surfaces
    schema = next(t for t in acts.catalog() if t.name == "start_task").schema["properties"]
    assert schema["kind"]["enum"] == [k for k, _ in kind._KINDS]
    assert schema["class"]["enum"] == [c for c, _ in errand._CLASSES]
    assert schema["surface"]["enum"] == list(surfaces._QUESTION["criteria"])
    born = {}
    monkeypatch.setattr(errand, "escalate_to_slowbrain", lambda req, context=None: born.update(context) or 5)
    monkeypatch.setitem(routing._last, "said", "w_book me a table and pay the deposit")
    acts_tasks.run("start", {"request": "w_book", "kind": kind.WEB, "class": "moves_money", "surface": surfaces.ITEM,
                             "widget": "w_agenda", "action": "w_add"})
    assert kind.kind_of(born[kind.KEY]) == "web" and born["errand_class"] == {"choice": "moves_money", "confidence": 1.0}
    assert born["surface"] == surfaces.ITEM and born["first_act"] == {"widget": "w_agenda", "action": "w_add"}
    assert born["heard"] == "w_book me a table and pay the deposit"
    ctx = dict(born)
    kind.carry(ctx)                                     # the old brief is read only for a key that is missing
    assert ctx[kind.KEY] == born[kind.KEY] and ctx["errand_class"] == born["errand_class"]


def test_the_workers_first_step_is_the_declared_action_the_model_named(monkeypatch):
    from nucleo.acts import payload_fill
    from nucleo.acts import frontend
    from nucleo.workers.prompts import first_act
    monkeypatch.setattr(frontend, "declared_actions", lambda base: {"w_add": {}} if base == "w_agenda" else {})
    monkeypatch.setattr(payload_fill, "_payload_spec", lambda wid, act: {"w_title": "w_what"})
    named = {"first_act": {"widget": "w_agenda", "action": "w_add"}}
    assert first_act.identified(None, named) == ("w_agenda", "w_add", {"w_title": "w_what"})
    assert first_act.identified(None, {"first_act": {"widget": "w_agenda", "action": "w_invented"}})[0] == ""


def test_a_widget_the_model_orders_built_is_a_sure_order(monkeypatch):
    from nucleo.acts import errand
    from nucleo.request import kind
    born = []
    monkeypatch.setattr(errand, "escalate_to_slowbrain", lambda req, context=None: born.append(context) or 9)
    acts_life.run("build", {"request": "w_a_tracker"})
    acts_life.run("build", {"request": "w_my_tracker", "change": True})
    assert [kind.code_change(c[kind.KEY]) for c in born] == ["create", "modify"]
    assert all(kind.sure_order(c) for c in born) and not kind.sure_order({kind.KEY: born[0][kind.KEY]})
