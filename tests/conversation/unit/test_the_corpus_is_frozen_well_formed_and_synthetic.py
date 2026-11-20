"""The frozen corpus is what its manifest says, every conversation is of its class, and nothing in it — nor in the
simulator's personas, nor in the audio fixtures — is personal (test plan §5.1).

A changed byte breaks the manifest's hash: regenerating makes a NEW version, never an edit of a frozen one. The
privacy check is structural (no e-mail but the fixtures' example.com, no phone number, no URL; the audio fixtures carry
tokens only); names are checked against `ZAELAR_PRIVATE_NAMES_FILE` where that private list exists — it never lives
in this public repo.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from tests.conversation.tools import corpus

HERE = Path(__file__).resolve().parents[1] / "fixtures"
VERSION = HERE / "corpus" / "v1"
MANIFEST = json.loads((VERSION / "manifest.json").read_text(encoding="utf-8"))
FILES = sorted(MANIFEST["files"])

EMAIL = re.compile(r"[\w.+-]+@(?!example\.com\b)[\w-]+\.[\w.]+")
PHONE = re.compile(r"\+?\d[\d\s().-]{8,}\d")
URL = re.compile(r"https?://|www\.")


@pytest.mark.parametrize("name", FILES)
def test_every_file_is_the_one_the_manifest_froze(name):
    data = (VERSION / name).read_bytes()
    assert hashlib.sha256(data).hexdigest() == MANIFEST["files"][name]["sha256"], f"{name} changed after freezing"
    assert len(json.loads(data)) == MANIFEST["files"][name]["conversations"]


def test_the_manifest_names_the_generator_the_brief_and_the_review():
    assert MANIFEST["generator"] and MANIFEST["frozen"] and MANIFEST["review"] and MANIFEST["reading_rules"]
    assert MANIFEST["total"] == sum(f["conversations"] for f in MANIFEST["files"].values())
    assert all(f["brief"] and f["model"] for f in MANIFEST["files"].values())


@pytest.mark.parametrize("name", FILES)
def test_every_conversation_is_of_its_class(name):
    cls, lang = name.removesuffix(".json").split(".")
    convs = json.loads((VERSION / name).read_text(encoding="utf-8"))
    bad = {c["id"]: corpus.problems(c, cls, lang) for c in convs if corpus.problems(c, cls, lang)}
    assert not bad, bad
    assert len({c["id"] for c in convs}) == len(convs)


def _texts() -> list[tuple[str, str]]:
    out = [(f, (VERSION / f).read_text(encoding="utf-8")) for f in FILES]
    out.append(("personas", (HERE / "sim" / "personas.v1.json").read_text(encoding="utf-8")))
    return out


@pytest.mark.parametrize("name,text", _texts(), ids=[n for n, _ in _texts()])
def test_nothing_personal_in_the_corpus_or_the_personas(name, text):
    assert not EMAIL.findall(text), name
    assert not URL.findall(text), name
    assert not [m for m in PHONE.findall(text) if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", m.strip())], name
    private = corpus._private_names()
    found = [n for n in private if re.search(rf"\b{re.escape(n)}\b", text.lower())]
    assert not found, f"{name} names a real person"


def test_the_audio_fixtures_carry_tokens_only():
    for path in sorted((HERE / "audio3a").glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            sig = json.loads(line)
            for w in sig.get("words") or []:
                assert re.fullmatch(r"w\d{4}", w[0]), f"{path.name}: {w[0]!r} is not a token"
    labels = json.loads((HERE / "audio3a" / "labels.json").read_text(encoding="utf-8"))
    for sc in labels["scenarios"].values():
        for seg in sc["segments"]:
            assert all(re.fullmatch(r"w\d{4}", w[0]) for w in seg["words"]), seg["i"]
