"""An `expect: added` clause names a row by the id field its collection DECLARES (operator, 2026-11-08).

`baseline._ids` read `row["id"]` only, so a collection keyed on another field (`contactos.groups` rows carry
`groupId`) had no ids: every `added` clause over it read «unverifiable» — never met, never unmet, nothing iterates.
"""
import pytest

from nucleo.circuit import baseline, verify


class _Groups:
    def __init__(self, monkeypatch, rows=()):
        from widgets import rows as R
        self.rows = [dict(r) for r in rows]
        monkeypatch.setattr(R, "declared", lambda wid: {"groups": {"id": "groupId"}} if wid == "contactos" else {})
        monkeypatch.setattr(R, "_rows", lambda wid, coll: list(self.rows) if (wid, coll) == ("contactos", "groups")
                            else [])


CLAUSE = {"widget": "contactos", "collection": "groups", "where": {"name~": "school"}, "expect": "added"}


@pytest.mark.parametrize("name", ["School parents", "Padres del colegio (school)"])
def test_an_added_group_is_judged_by_its_group_id(monkeypatch, name):
    g = _Groups(monkeypatch, [{"groupId": "g1", "name": "Old school friends"}])
    c = dict(CLAUSE)
    baseline.snapshot(c)
    assert c["baseline_ids"] == ["g1"], "the declared id field names the row at birth"
    assert verify.check(c) is False, "the group that already existed is not the one he asked for"
    g.rows.append({"groupId": "g2", "name": name})
    assert verify.check(c) is True


def test_a_row_without_its_declared_id_still_reads_unverifiable(monkeypatch):
    g = _Groups(monkeypatch)
    c = dict(CLAUSE)
    baseline.snapshot(c)
    g.rows.append({"name": "School parents"})
    assert verify.check(c) is None
