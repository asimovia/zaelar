"""V2-859 T564 · only STRUCTURED genes cross, and no gene names anyone this agent knows.

A heritable gene is one of four closed shapes (alias · route · nothing_serves · threshold), each with the evidence
it needs; anything else is refused. And before anything leaves, a deterministic filter drops every gene whose key or
value carries something particular: a name of one of his contacts (or of the memory's concept hubs), an email, a
phone, a URL, a number of three digits or more, a date. The names below are invented fixtures.
"""
from __future__ import annotations

import json

import pytest

import genome
from genome import genes, privacy

G = json.loads(genome.GENESIS.read_text(encoding="utf-8"))
CONTACT = {"name": "Nadia Velasco", "channels": [{"platform": "whatsapp", "name": "Nadi V"}]}

ALIAS = {"type": "alias", "key": {"lang": "es", "phrase": "cierra todo ya"}, "value": {"do": "close_all"},
         "evidence": {"hits": 5, "agree": 4, "disagree": 1}}
ROUTE = {"type": "route", "key": {"domain": "wellness"}, "value": ["mesh", "worker"], "evidence": {"closures": 2}}
NONE = {"type": "nothing_serves", "key": {"domain": "wellness", "channel": "mesh"}, "value": None,
        "evidence": {"answers": 2}}
THRESHOLD = {"type": "threshold", "key": {"knob": "consent.intent_act_at"}, "value": 0.8,
             "evidence": {"measured": 120}}


def _with(g, **kw):
    out = json.loads(json.dumps(g))
    for k, v in kw.items():
        out[k] = v
    return out


@pytest.mark.parametrize("gene", [ALIAS, ROUTE, NONE, THRESHOLD], ids=lambda g: g["type"])
def test_each_closed_shape_with_its_evidence_is_a_gene(gene):
    assert genes.invalid(gene, G) == ""


@pytest.mark.parametrize("gene,why", [
    ({"type": "brief", "key": {}, "value": "always book the cheapest"}, "unknown gene type"),
    (_with(ALIAS, value={"do": "run_shell", "cmd": "x"}), "alias: unknown do"),
    (_with(ALIAS, evidence={"hits": 9, "agree": 1, "disagree": 3}), "alias: not enough evidence"),
    (_with(ALIAS, evidence={"hits": 1, "agree": 1, "disagree": 0}), "alias: not enough evidence"),
    (_with(ROUTE, value=["mesh", "agent-7"]), "route: a channel that is not declared"),
    (_with(ROUTE, key={"domain": "Casa Ejemplo"}), "route: domain is not a key"),
    (_with(NONE, key={"domain": "wellness", "channel": "site"}), "nothing_serves: a channel that is not declared"),
    (_with(THRESHOLD, value=0.2), "threshold: value outside its declared bounds"),
    (_with(THRESHOLD, key={"knob": "consent.ask_at"}), "threshold: a knob that is not declared heritable"),
    (_with(THRESHOLD, evidence={}), "threshold: not measured"),
], ids=lambda x: x if isinstance(x, str) else "")
def test_anything_else_is_refused_with_its_reason(gene, why):
    assert genes.invalid(gene, G).startswith(why)


def test_a_route_gene_carries_the_channel_kind_never_the_target():
    rows = [{"domain": "restaurant", "channel": "mesh", "rank": 10, "status": "active", "hits": 0,
             "target": "agent-for-casa-ejemplo"},
            {"domain": "restaurant", "channel": "browser", "rank": 5, "status": "active", "hits": 2},
            {"domain": "wellness", "channel": "mesh", "rank": 999, "status": "none", "hits": 0}]
    got = genes.routes(rows)
    assert got[0] == {"type": "route", "key": {"domain": "restaurant"}, "value": ["browser", "mesh"],
                      "evidence": {"closures": 4}}
    assert got[1]["type"] == "nothing_serves" and got[1]["key"] == {"domain": "wellness", "channel": "mesh"}
    assert "casa" not in json.dumps(got)


KNOWN = {"nadia velasco", "nadia", "velasco", "nadi"}


@pytest.mark.parametrize("gene", [
    _with(ALIAS, key={"lang": "es", "phrase": "llama a nadia velasco"}),
    _with(ALIAS, value={"do": "widget_data", "widget": "mensajeria", "action": "send", "to": "Velasco"}),
    _with(ROUTE, key={"domain": "velasco"}),
    _with(NONE, key={"domain": "nadia", "channel": "mesh"}),
    _with(THRESHOLD, key={"knob": "nadia.velasco"}),
], ids=["alias-phrase", "alias-payload", "route", "nothing_serves", "threshold"])
def test_a_gene_naming_a_known_contact_is_dropped(gene):
    assert privacy.reason(gene, KNOWN) == "known name"
    kept, dropped = privacy.keep([gene, ROUTE], KNOWN)
    assert kept == [ROUTE] and dropped == {"known name": 1}


@pytest.mark.parametrize("phrase,kind", [
    ("escribe a ana@example.org", "email"),
    ("llama al +34 600 11 22 33", "phone"),
    ("abre example.com/reservas", "url"),
    ("la mesa 204", "number"),
    ("el 12/03", "date"),
])
def test_a_gene_with_a_particular_shape_is_dropped_whoever_it_names(phrase, kind):
    assert privacy.reason(_with(ALIAS, key={"lang": "es", "phrase": phrase}), set()) == kind


def test_a_generic_gene_crosses():
    for g in (ALIAS, ROUTE, NONE, THRESHOLD):
        assert privacy.reason(g, KNOWN) == "", g


def test_what_he_knows_is_read_from_his_contacts_and_his_memory(monkeypatch):
    from memory import api as memory
    from widgets import directory
    monkeypatch.setattr(directory, "_contacts", lambda: [CONTACT])
    monkeypatch.setattr(memory, "concept_names", lambda limit=40: ["Club Ejemplo"])
    got = privacy.known()
    assert {"nadia velasco", "nadia", "velasco", "nadi v", "nadi", "club ejemplo"} <= got
    assert "v" not in got, "a one-letter word is never a name to match"


def test_the_export_drops_a_learned_alias_that_names_a_contact(mem, alias_row, monkeypatch):
    from genome import diff
    from widgets import directory

    monkeypatch.setattr(directory, "_contacts", lambda: [CONTACT])
    alias_row("es", "cierra todo ya", json.dumps({"do": "close_all"}))
    alias_row("es", "abre lo de nadia", json.dumps({"do": "show_widget", "widget": "mensajeria"}))
    d = diff.diff()
    assert [g["key"]["phrase"] for g in d["genes"]] == ["cierra todo ya"]
    assert d["dropped"] == {"known name": 1}
    assert "nadia" not in json.dumps(d).lower()
