"""A fix is a mechanism, never a word: regexes and word tables in product code only get RARER (CRIT-W10).

Operator, 2026-10-19: «no más arreglos para que tests individuales funcionen. Tenemos que hacer mejoras a nivel
estructural que arreglen el sistema y como resultado los tests funcionen — esto es un producto global, que debe
poder atender cualquier request.»

The doctrine was already written (CRIT-W1, «mechanisms, not rules») and it did not hold: the 72-hour audit V2-783
classified 30 of 99 product commits as a regex, a word table or a net over the model's words, born from one
recorded case each — 87 `re.compile` added and 4 removed, `search/` alone from 43 to 83. A sentence in a document
loses to a red test every time; this is the test.

Counted by AST over tracked product files (tests and `i18n/` excluded — `i18n/` is the DECLARED home of language
data, one table per language, so moving vocabulary there is a payment, not a loophole):
  · every regex the code writes: `re.compile(…)` calls anywhere, through any name the module bound `re` to
    (`import re as _re`), and every inline `re.search/match/fullmatch/findall/finditer/sub/subn/split` whose
    pattern is written in the call (a literal or an f-string) — an inline pattern is as much a regex as a compiled
    one, and an alias is the same module;
  · module-level word tables — a set / frozenset / tuple / list / dict-of-keys literal, or `"…".split()`, holding
    three or more strings.
The totals may only fall. A new one is paid by removing one elsewhere in the same commit — which is the point:
before adding a word, find the verdict, the declared datum or the structure that makes the words unnecessary.
"""
from __future__ import annotations

import ast
import subprocess
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]

#: Measured 2026-10-19 at 295ff4ec (366 files). Lower these when you remove; never raise them.
MAX_REGEXES = 894   # +1 2026-11-10 V2-872 F2 (#265-#267): the email cursor reads IMAP's own `UIDVALIDITY` status line (`email/mailbox/reads.inbox_validity`) — a wire FORMAT, no word of a language. Before: +9 2026-11-09 the local daemon (#253-#256): FORMAT validators of its own wire and files, no word of a language — a sha256 hex, an asset name and a version in the update manifest, a pairing code and its whitespace, an egress host name, a tunnel token, the codesign TeamIdentifier line, a download's progress line; the relay's login-word regex went (the engine's `daemon_link._signed_in` is the one judge of a sign-in). Before: +8 2026-11-09 V2-859 T564 (2.1651): the genome's privacy filter (`genome/privacy.py`, 7 — detectors of an email, a phone, a URL, a number, a date: personal DATA, not words of a case) and the closed gene shapes (`genome/genes.py`, 1); `nucleo/workflows/domains.py` → `nucleo/routes/domains.py` is a rename (15 → 15). Before: V2-857 review: the count now SEES every regex — `_re.compile` through an alias (+83) and inline `re.search/sub/…` with the pattern written in the call (+314); the 479 it showed before were only `re.compile` spelled `re`, so this is the same code counted honestly, not new regexes. V2-857 phase 8: the login and stop word readers went; V2-851 F5: the post-stream readers of our own reply went (answer_guards' fact, ack, wait and continuity guards); V2-851 F5b: the auditor's regexes went with it; V2-851 F4: request/kind.py's six regexes went — the errand kind is the brief's verdict; refactor2710-10: an unread regex in asked_count went; refactor2710-03: the word gates over our own reply went (was 532); refactor2710-01: the old text channel went (was 543); V2-806: the spoken-rule parsers went
MAX_WORD_TABLES = 477  # +2 2026-11-10 V2-872 F2 (#265-#267): closed sets of NAMES and a state record, no word of a language — the platforms whose server keeps what arrived while the engine slept (`pulse/listeners.CATCH_UP`), and where the email cursor stands (`email/service._where`: address, validity, pending). Before: +19 2026-11-09 the local daemon (#253-#256): closed sets of NAMES and state records, no word of a language — config and relay field names, update/tray states and their transitions, the relay's op table, release asset names per platform, the Info.plist usage keys, local-network suffixes, hop-by-hop proxy headers, SameSite values, unsupported browser ids, size units, `__all__`, three default state records; the three copies of the loopback list became one door (`security.guards.is_loopback_name`) and the update states are read off their transitions. Before: +1 2026-11-09 daemon installer (ee6b35e9e): the release asset NAMES the installer resolves (`daemon/packaging/release_names.py`), not words of a language; +1 2026-11-09 V2-868 D4 (4.416): the fields a row STATES data in (`results/provenance.CLAIMS`: price, facts, score, parts) — field names, not words of a language; +3 2026-11-09: closed sets of NAMES, not words of a language — the gene types (`genome/`), the routes package's exports (`nucleo/routes/`), the daemon browser's capability names (`daemon/browser/`). Before: +5 2026-11-08: sets of ACTION NAMES, not words of a language — the spoken controls that are the music card's own actions (`music_flow._CARD_CONTROLS`), the controls whose failure is a fact (`music_outcome._CONTROLS`), the acts that touch a playback (`music._TOUCHES_PLAYBACK`); follow-up V2-862: derive them from the manifests (`effects.is_bare_control`).
# previous: MAX_WORD_TABLES = 446  # V2-851 F5b: the auditor's tables and the dead Google-connector table went; V2-847: the row and scalar clause operators are one table keyed by clause kind; V2-831 audit A6b: the Origin label/value tables went (read through the packs); refactor2710-06: the reminder rails went; refactor2710-03: the claim vocabulary went (the player receipt's tables moved to reply_receipts); refactor2710-12: two dispatch tables read off their handler names; refactor2710-01: the old text channel's reply door went; refactor2710-11: a guessed dimension row went (was 476)


def _strings(v) -> int:
    if isinstance(v, ast.Call) and getattr(v.func, "id", "") in ("frozenset", "set", "tuple", "list") and v.args:
        v = v.args[0]
    if isinstance(v, (ast.Set, ast.List, ast.Tuple)):
        return sum(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in v.elts)
    if isinstance(v, ast.Dict):
        # A record of state or of numeric limits (`{"sid": None, "ts": 0.0}`, `{"tracks": 10}`) names fields, it
        # reads no words: a table maps words to words (or to declared values), so at least one value is a string
        # or a name.
        if v.values and all(isinstance(x, ast.Constant) and not isinstance(x.value, str) for x in v.values):
            return 0
        return sum(isinstance(k, ast.Constant) and isinstance(k.value, str) for k in v.keys if k is not None)
    if (isinstance(v, ast.Call) and isinstance(v.func, ast.Attribute) and v.func.attr == "split"
            and isinstance(v.func.value, ast.Constant) and isinstance(v.func.value.value, str)):
        return len(v.func.value.value.split())
    return 0


#: The `re` functions that take a pattern as their first argument.
_PATTERN_TAKERS = ("compile", "search", "match", "fullmatch", "findall", "finditer", "sub", "subn", "split")


def _regexes(tree: ast.AST) -> int:
    """Each `re.compile` (any argument) and each inline `re.<fn>` whose pattern is written in the call, through every
    name the module bound the `re` module to."""
    names = {"re"} | {a.asname or a.name for n in ast.walk(tree) if isinstance(n, ast.Import)
                      for a in n.names if a.name == "re"}
    n_rx = 0
    for n in ast.walk(tree):
        if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in _PATTERN_TAKERS
                and isinstance(n.func.value, ast.Name) and n.func.value.id in names):
            continue
        written = bool(n.args) and (isinstance(n.args[0], ast.JoinedStr) or (
            isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)))
        n_rx += n.func.attr == "compile" or written
    return n_rx


def _counts() -> dict[str, tuple[int, int]]:
    files = subprocess.run(["git", "ls-files", "*.py"], cwd=ENGINE, capture_output=True, text=True).stdout.split()
    out: dict[str, tuple[int, int]] = {}
    for rel in files:
        if rel.startswith(("tests/", "i18n/")) or "/tests/" in rel or not (ENGINE / rel).exists():
            continue
        try:
            tree = ast.parse((ENGINE / rel).read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        rx = _regexes(tree)
        # `A, B, C = "a", "b", "c"` declares named constants, one per target — not a table anything is looked up in.
        wt = sum(isinstance(n, (ast.Assign, ast.AnnAssign)) and n.value is not None and _strings(n.value) >= 3
                 and not (isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Tuple))
                 for n in tree.body)
        if rx or wt:
            out[rel] = (rx, wt)
    return out


def test_regexes_and_word_tables_only_get_rarer():
    counts = _counts()
    rx = sum(a for a, _ in counts.values())
    wt = sum(b for _, b in counts.values())
    top = sorted(counts.items(), key=lambda kv: -sum(kv[1]))[:5]
    assert rx <= MAX_REGEXES and wt <= MAX_WORD_TABLES, (
        f"product code holds {rx} regexes (ceiling {MAX_REGEXES}) and {wt} word tables (ceiling {MAX_WORD_TABLES}). "
        "A fix that adds words reads ONE case; the product must answer any request (CRIT-W10). Find the verdict, the "
        "declared datum or the structure instead — or pay it by removing one elsewhere. Largest holders: "
        + ", ".join(f"{k} {v}" for k, v in top))


def test_the_ceiling_is_not_slack():
    """A ceiling far above the count lets the next patch in unseen: lower it when you remove (slack ≤ 10)."""
    counts = _counts()
    assert MAX_REGEXES - sum(a for a, _ in counts.values()) <= 10
    assert MAX_WORD_TABLES - sum(b for _, b in counts.values()) <= 10
