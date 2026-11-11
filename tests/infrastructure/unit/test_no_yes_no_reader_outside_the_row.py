"""No reader of a yes or a no exists outside the row's declared answers or the brief's pick (V2-878 §4b, node 2.1685).

A reply to a question waiting on him was read by two regexes of answer words (`widgets/confirm._YES_RE`/`_NO_RE`: «si»,
«vale», «dale», «ok», «para», «nada»…) from six doors — the widget gate, the task gate, the browser click, the durable
answer, the model's tool guard and the voice's early path. A table of Spanish and English words is no reader of any
other language, and every case it got wrong grew it (CRIT-W10). Each door now reads ONE of two things:

  · the brief's binding pick over the open rows (`nucleo/cli/worker_api_bind`), any wording, any language;
  · a reply that IS one of the question's two DECLARED answers, in his language (`consent_ask.declared_answer`) —
    what the screen's buttons send.

Pinned structurally: no pattern written in product code reads answer words of both sides (a `re.compile` or inline
`re.*` whose pattern matches several of the answer words below, in any of the shipped languages), and the old names
are gone. Disarm (seen red): put a yes/no regex back in any product module.
"""
from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]

#: Probe replies — the answer words the old tables held, both sides. A pattern that matches a reply of each side is a
#: yes/no reader. (Test data, never product.)
YES = ("si", "sí", "vale", "dale", "claro", "venga", "ok", "okay", "yes", "yeah", "go ahead")
NO = ("no", "cancela", "déjalo", "olvídalo", "cancel", "stop", "never mind", "nop")
#: Words that answer no question: a pattern that also matches these reads any word, or small talk (a greeting or a
#: thanks is no yes) — not answers.
OTHER = ("monitor", "tomorrow", "reserva", "banana", "weather", "hola", "gracias", "hello", "thanks")
GONE = ("_YES_RE", "_NO_RE", "classify_reply", "opening_answer", "is_plain_answer", "answer_alone", "_judge")


def _patterns(tree: ast.AST):
    names = {"re"} | {a.asname or a.name for n in ast.walk(tree) if isinstance(n, ast.Import)
                      for a in n.names if a.name == "re"}
    for n in ast.walk(tree):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name)
                and n.func.value.id in names and n.args and isinstance(n.args[0], ast.Constant)
                and isinstance(n.args[0].value, str)):
            yield n.args[0].value, n.lineno


def _reads_answers(pattern: str) -> bool:
    try:
        rx = re.compile(pattern, re.IGNORECASE)
    except re.error:
        return False
    hit = lambda words: sum(bool(rx.fullmatch(w) or rx.search(f" {w} ")) for w in words)   # noqa: E731
    return hit(YES) >= 3 and hit(NO) >= 2 and hit(OTHER) == 0


def _product():
    files = subprocess.run(["git", "ls-files", "*.py"], cwd=ENGINE, capture_output=True, text=True).stdout.split()
    for rel in files:
        if rel.startswith(("tests/", "i18n/")) or "/tests/" in rel or not (ENGINE / rel).exists():
            continue
        try:
            yield rel, ast.parse((ENGINE / rel).read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue


def test_no_pattern_in_product_code_reads_a_yes_and_a_no():
    readers = [f"{rel}:{line}" for rel, tree in _product() for pat, line in _patterns(tree) if _reads_answers(pat)]
    assert not readers, f"a yes/no word reader is back — read the brief's pick or the row's declared answers: {readers}"


def test_the_old_readers_are_gone():
    from widgets import confirm
    assert not [n for n in GONE if hasattr(confirm, n)]


def test_the_probe_sees_the_old_tables():
    """The probe is not blind: the deleted tables, one regex per side as they were, are each half of a reader — and
    the classifier's way of using both at once is what a single pattern of both sides looks like."""
    old_yes = r"\b(si|sip|claro|vale|venga|dale|adelante|ok|okey|okay|yes|yeah|yep|do it|go ahead|confirm)\b"
    old_no = r"\b(no|nop|cancela|cancelar|dejalo|dejala|para|olvidalo|mejor no|nada|cancel|stop|nevermind)\b"
    assert _reads_answers(old_yes[:-4] + "|" + old_no[4:])


def test_a_declared_answer_is_the_whole_reply_in_his_language(monkeypatch):
    from nucleo.request import consent_ask as ca
    for lang, yes, no in (("es", "Sí.", "no"), ("en", "Yes!", "No")):
        monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
        assert ca.declared_answer(yes) == "yes" and ca.declared_answer(no) == "no", lang
        assert ca.declared_answer(f"{yes} and close the video") is None, lang
    assert ca.declared_answer("はい", ["はい", "いいえ"]) == "yes"
    assert ca.declared_answer("いいえ", ["はい", "いいえ"]) == "no"
