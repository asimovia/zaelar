"""V2-705 · V2-859 T562 · A send under a playbook that continues with the other person opens its follow-through
errand even when the model forgot to label it — and the kind is the playbook the TASK named, never its words.

Measured 2026-09-15 (the manual autonomy test): Zaelar sent «Hi! I'd like to propose a meeting tomorrow at 8am…»
to the contact, the model dropped the `objective`, no errand existed, and the operator's «Yes, I agree» woke
nothing. The net that closed it was a word table over the message (`kind_for(text) == "meeting"`) — a table of
verbs is not a router (V2-750), and its words were mostly Spanish.

Now the worker names its playbook at checkpoint 1, the exit door stamps it on the message that leaves
(`exit_gate._continues_as`), and the errand inherits it: `meeting`/`booking` open a follow-through in any
language; a message under `message` (or none) opens nothing, whatever it says.
"""
from __future__ import annotations

import pytest

from nucleo.errands import playbooks, watch

ES_PROPOSAL = "¡Hola! ¿Quedamos el viernes a las 10 para vernos? Te paso un enlace de videollamada."
EN_PROPOSAL = "Hi! Could we meet this Friday at 10am? I will set up a video call link for us."


def test_an_explicit_objective_is_used_verbatim():
    assert watch._gestion_objective({"ref": "r", "objective": "Propose X and book it", "text": "hi"}) \
        == "Propose X and book it"


@pytest.mark.parametrize("text", [ES_PROPOSAL, EN_PROPOSAL])
@pytest.mark.parametrize("playbook", ["meeting", "booking"])
def test_a_send_under_a_continuing_playbook_seeds_its_objective_from_its_text(text, playbook):
    ev = {"ref": "r", "objective": "", "text": text, "playbook": playbook}
    assert watch._gestion_objective(ev) == text


@pytest.mark.parametrize("text", [ES_PROPOSAL, EN_PROPOSAL, "Running late, see you at 5!", "Gracias, recibido."])
@pytest.mark.parametrize("playbook", ["", "message", "errand", "not-a-playbook"])
def test_a_send_under_no_continuing_playbook_opens_nothing_whatever_it_says(text, playbook):
    """The words no longer decide: a proposal sent by a `message` task is a one-off message."""
    assert watch._gestion_objective({"ref": "r", "objective": "", "text": text, "playbook": playbook}) == ""


def test_an_empty_send_opens_nothing():
    assert watch._gestion_objective({"ref": "r", "objective": "", "text": "", "playbook": "meeting"}) == ""
    assert watch._gestion_objective({}) == ""


def test_the_errand_kind_is_the_named_playbook_never_the_objectives_words():
    assert playbooks.kind_of("meeting") == "meeting" and playbooks.kind_of("booking") == "booking"
    assert playbooks.kind_of("") == "generic" and playbooks.kind_of("message") == "generic"
    assert not hasattr(playbooks, "kind_for"), "the word table is gone, not bypassed"


def test_the_word_table_is_gone_from_genesis():
    """Genesis holds the STRUCTURE (done_when, need ids); words and prose are language data."""
    for kind, spec in playbooks.playbooks().items():
        assert "matches" not in spec, f"«{kind}» still carries a word table"
        assert "brief" not in spec, f"«{kind}» carries prose in a language-neutral file"
        for need in spec.get("needs") or []:
            assert need.isascii() and " " not in need, f"«{kind}» need «{need}» is a word, not an id"


@pytest.mark.parametrize("lang", ["es", "en"])
def test_every_continuing_playbook_is_worded_in_both_languages(lang):
    from i18n import langs
    from nucleo.workers.prompts import playbook as pb
    for kind in pb.WITH_A_PARTY:
        assert kind in playbooks.playbooks(), f"«{kind}» is in the worker's catalogue and not in genesis"
        assert langs.words(f"worker_brief.done_when.{kind}", lang), f"no end state for «{kind}» in {lang}"
        assert langs.words(f"errands.brief.{kind}", lang), f"no brief for «{kind}» in {lang}"
        for need in playbooks.needs(kind):
            assert langs.words(f"errands.needs.{need}", lang), f"need «{need}» unworded in {lang}"


# ── the exit door stamps the name the task gave ─────────────────────────────────────────────────────────

class _Rec:
    def __init__(self, chosen: str):
        self.playbook_chosen = chosen
        self.task_id = "t-1"


@pytest.mark.parametrize("chosen,expected", [("meeting", "meeting"), ("booking", "booking"),
                                             ("message", ""), ("errand", ""), ("", "")])
def test_the_exit_door_stamps_a_continuing_playbook_on_an_act_that_can_open_one(chosen, expected, monkeypatch):
    from nucleo.workers import exit_gate
    from nucleo.workers.prompts import playbook as pb
    monkeypatch.setattr(pb, "_durable", lambda rec: ("", {}))
    assert exit_gate._continues_as(_Rec(chosen), "mensajeria", "send_to") == expected


def test_an_act_that_declares_no_follow_through_is_never_stamped(monkeypatch):
    """Read from the manifest (an `objective` it declares), never from the widget's name."""
    from nucleo.workers import exit_gate
    from widgets import contract
    monkeypatch.setattr(contract, "_declared", lambda wid, act: {"text": "the message"})
    assert exit_gate._continues_as(_Rec("meeting"), "mensajeria", "send_to") == ""


# ── …but an errand's OWN voice opens nothing (V2-705) ───────────────────────────────────────────────────
# Measured 2026-09-15 20:46: the errand's own confirmation was read as a fresh proposal, opened a SECOND errand,
# and `claim()` took the conversation off the first one.

def test_the_sender_is_read_from_the_STORE_not_from_the_shape_of_the_ref(monkeypatch):
    """A ref that merely LOOKS like an errand id opens its errand normally — the gate asks the store."""
    import nucleo.errands.watch as w
    monkeypatch.setattr("nucleo.errands.get", lambda eid: None)
    assert w._own_errand("e7457588--b60xTk:1789497987") == ""
    monkeypatch.setattr("nucleo.errands.get", lambda eid: {"id": eid})
    assert w._own_errand("e7457588--b60xTk:1789497987") == "e7457588--b60xTk"
    assert w._own_errand("") == "" and w._own_errand(None) == ""


# ── where the worker can name them ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_generic_worker_can_name_a_continuing_playbook_and_a_web_worker_is_not_offered_one(lang, monkeypatch):
    """A conversation with a person is offered where the worker may hold one; a worker the brief sent to do the job
    ON a website (`errand_kind` web) is not — decided by that verdict, never by the request's words."""
    from i18n import langs
    from nucleo.workers.prompts import playbook as pb
    monkeypatch.setattr(langs, "current_code", lambda: lang)
    generic, web = pb.catalogue(pb.ERRAND), pb.catalogue(pb.ERRAND, with_a_party=False)
    for kind in pb.WITH_A_PARTY:
        assert f"· {kind} —" in generic and f"· {kind} —" not in web
    assert "· message —" in web and "· errand —" in web
    assert pb.chosen(type("R", (), {"task_id": "", "uid": ""})(), "meeting") == "", "meeting is a name it may give"


@pytest.mark.parametrize("chosen,stamped", [("meeting", "meeting"), ("booking", "booking"), ("message", None)])
def test_the_send_that_crosses_the_exit_door_carries_the_tasks_playbook(chosen, stamped, monkeypatch):
    """The wiring, end to end through `exit_gate.gate`: what leaves carries the name the task gave — the errand born
    from its echo reads THAT (`watch._born_from_echo` → `start(kind=…)`). Disarm: drop the stamp in `gate`."""
    from types import SimpleNamespace
    from nucleo.workers import exit_gate
    from widgets import contract
    monkeypatch.setattr(exit_gate, "leaves", lambda wid, act: True)
    monkeypatch.setattr(contract, "would_refuse", lambda *a, **k: None)
    rec = SimpleNamespace(task_id="k1", uid="", mandate={}, reading=None, playbook_chosen=chosen,
                          done_when={"all": [{"widget": "mensajeria", "field": "last_sent", "expect": "changed"}]})
    out = exit_gate.gate(rec, {"widget_id": "mensajeria", "action": "send_to",
                               "payload": {"contact": "Rakel Karó", "text": "¿Quedamos el viernes?"}})
    assert not out.refused
    assert out.payload["payload"].get("playbook") == stamped


@pytest.mark.parametrize("playbook,kind", [("meeting", "meeting"), ("", "generic")])
def test_the_errand_born_from_the_echo_inherits_the_stamped_playbook(playbook, kind, monkeypatch):
    """`_born_from_echo` hands the order's playbook to the one door; the words of the objective decide nothing."""
    from nucleo.errands import watch as w
    seen = {}

    def _start(objective, **kw):
        seen.update(kw, objective=objective)
        return None                                   # nothing to claim: the call is what is measured

    monkeypatch.setattr("nucleo.errands.start", _start)
    w._pending_births.clear()
    w._pending_births["r1"] = {"ref": "r1", "objective": "organizar una reunión", "playbook": playbook,
                               "contactId": "c1", "platform": "telegram", "_at": 0}
    monkeypatch.setattr(w, "_drain", lambda name: [{"ref": "r1", "platform": "telegram", "chatId": "9"}]
                        if name == "out" else [])
    w._born_from_echo(0)
    assert playbooks.kind_of(seen.get("kind")) == kind
