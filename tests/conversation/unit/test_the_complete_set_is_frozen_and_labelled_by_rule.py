"""The `complete` gate's labelled set (v3.1 §1.6 quater) is what its manifest froze, big enough for the gate, and every
label follows the rule written before measuring: an incomplete item ends with a sentence mark (the case the gate is
for) and says what follows; a complete one is a whole thought.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tests.conversation.tools import complete_set

ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "complete" / "v2"
MANIFEST = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("lang", ["es", "en"])
def test_each_file_is_the_one_the_manifest_froze(lang):
    data = (ROOT / f"complete.{lang}.json").read_bytes()
    assert hashlib.sha256(data).hexdigest() == MANIFEST["files"][f"complete.{lang}.json"]["sha256"]


@pytest.mark.parametrize("lang", ["es", "en"])
def test_the_set_is_big_enough_for_the_gate_and_follows_its_rule(lang):
    items = complete_set.load(lang)
    inc = [x for x in items if x["label"] == "incomplete"]
    comp = [x for x in items if x["label"] == "complete"]
    assert len(inc) >= 30 and len(comp) >= 100
    assert all(x["text"].rstrip().endswith((".", "?", "!", "…")) and x["goes_on"] for x in inc)
    assert all(x["shape"] in MANIFEST["files"][f"complete.{lang}.json"]["shapes"] for x in items)
    assert len({x["text"] for x in items}) == len(items)


def test_a_changed_byte_is_refused_by_the_loader(tmp_path, monkeypatch):
    (tmp_path / "v2").mkdir()
    for f in ("manifest.json", "complete.es.json"):
        (tmp_path / "v2" / f).write_bytes((ROOT / f).read_bytes())
    p = tmp_path / "v2" / "complete.es.json"
    p.write_bytes(p.read_bytes().replace(b"incomplete", b"complete", 1))
    monkeypatch.setattr(complete_set, "ROOT", tmp_path)
    with pytest.raises(AssertionError):
        complete_set.load("es")
