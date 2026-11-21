"""The mouth says the verdict (refactor2710-03): for each verdict of an act, the line — and only the lines it owes.

`nucleo/turn/reply.py` composes an acting turn's last words from what its acts ENDED in. One i18n key per verdict
(`reply_<verdict>`), in every language the engine ships. The rules: `met` names its object unless the words already
named it; `unmet`, `cannot` and `asked` are always said (unless the act's own door already said them); `started`,
`skipped` and the rest add nothing. Each line leaves one event carrying its verdict.

The disarm feeds a WRONG verdict to the same act and sees the line change: a test that stays green over it would be
checking the template, not the verdict.
"""
from __future__ import annotations


import pytest


VALUES = ("started", "met", "unmet", "unverifiable", "undeclared", "cannot", "asked", "skipped")


@pytest.fixture(params=["en", "es"])
def lang(request, monkeypatch):
    from i18n import langs
    spec = langs.LANGUAGES[request.param]
    monkeypatch.setattr(langs, "current_language", lambda: spec)
    return spec


def _send():
    said = []

    class _Speech:
        @staticmethod
        def sanitize(t, drop_metadata=False):
            return t

    return said, said.append, _Speech


def test_every_verdict_has_its_key_in_every_language(lang):
    for v in VALUES:
        assert hasattr(lang, f"reply_{v}"), f"{lang.code}: no reply_{v}"
    for v in ("started", "met", "unmet", "unverifiable", "undeclared", "cannot", "asked"):
        assert getattr(lang, f"reply_{v}"), f"{lang.code}: reply_{v} is empty"

