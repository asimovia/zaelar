"""A row the order owes carries the data the order gave it, and a bare row does not attest (T-19 R2).

Demo sandbox at build 86, INIT: «Save <a> and <b>… <b>'s email is …» made ONE create, and a row only NAMED <b> read
«met». The class: a clause names the row (`where`) and carries what the order stated for it (`with`); the verifier
reads it. The write harness that re-ran the model after the turn to add the missing row (`compose.check`) went in
V2-851 F5 with every model re-run after the main stream; what stays is the verifier's reading of an end state.
"""

from nucleo.circuit import spec as _spec


def _contacts_goal():
    return {"all": [
        {"widget": "contactos", "collection": "contacts", "where": {"title~": "Quinn"}, "expect": "present"},
        {"widget": "contactos", "collection": "contacts", "where": {"title~": "Rowan"},
         "with": {"email": "rowan@example.com"}, "expect": "present"}]}


def test_the_inferrer_is_shown_the_fields_each_collection_creates_with():
    assert "email" in _spec.create_fields("contactos", "contacts")
    assert "list" in _spec.create_fields("agenda", "tasks")
    assert _spec.create_fields("agenda", "occurrences") == []
