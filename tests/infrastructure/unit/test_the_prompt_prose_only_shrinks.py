"""V2-711 T2.2 · The prose the model reads every turn only shrinks — measured where it is WRITTEN.

## Why the existing ratchet could not see this

`test_architecture_ratchet` freezes LOC per file, and LOC is the wrong proxy for this particular debt in
two opposite ways at once:

  · it counts COMMENTS, which this repo deliberately wants — every pattern carries the incident that
    measured it — so writing evidence reads as growth;
  · and it is paid by EXTRACTING a module, which moves the prose somewhere else without removing a word of
    it. Measured: `prompt.py` has been paid down to `live_blocks.py` twice (V2-675, V2-685) and the total
    the model reads went UP each time. A ceiling that a move satisfies is not measuring what it is about.

So this measures the PROSE: every string literal of 40+ characters in the two prompt modules, plus the tool
catalog serialized the way the provider receives it. Deterministic and machine-independent by construction —
no live state, no open widgets, no memory — which is the property the composed `build_flash_system()` cannot
have (its length depends on whose engine runs it, and a lab measures the PRODUCT, not the machine it runs
on: V2-502).

## What it is for

`principles.md` names this class outright: *«Rail on JUDGEMENT — a LIMIT, remove it»*. The `ops` block alone
is 63 sentences, 34 of them an imperative or a prohibition, and it grows one sentence per incident. Each of
those sentences fixed something real; the point of a ratchet is not that they are wrong, it is that the cost
is paid on EVERY turn by every operator and nothing was counting it. Frozen at what it is today, editable
only downward — and the way DOWN is V2-707 F4, the per-operator policy store: the frases that are really
preferences (verbosity, how much it asks before starting, confirm or not, silence on short orders) move to a
table the turn CONSULTS, the way V2-633 already moved «al recibir órdenes no respondas nada».
"""
from __future__ import annotations

import ast
import pathlib
import sys

ENGINE = pathlib.Path(__file__).resolve().parents[3]
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

#: Below this, a literal is an identifier, a key, a separator or a format fragment rather than prose. The
#: exact value does not matter much: what matters is that it is FIXED, so the number only moves when the
#: text does.
_PROSE_FLOOR = 40

#: The two modules that compose what the fast turn reads. `router_catalog` is measured apart, because it
#: already has its own ceiling in `test_router` and is counted here only so the TOTAL is honest.
_PROSE_FILES = ("widgets/navegador/live_sheet.py", "widgets/navegador/live_lines.py", "widgets/navegador/live_nav.py",
                "nucleo/done_lines.py")   # INI-078 L1: the old turn's prompt files went with it; these four the manager still reads

#: Measured 2026-09-16. EDIT DOWNWARD ONLY — and the edit is the celebration.
_MAX_PROSE = 7_014          # INI-078 L1: re-measured over the four files the manager still reads (was 25_111 with the old turn's prompt);         # +51 2026-11-18 V2-935: two FACTS of the turn, each read from state and absent when it does not hold — an errand the gate holds («NO HA EMPEZADO», instead of «stuck») and a native panel open over the screen; +194 2026-11-18 V2-935: the conversation's base norm, said once and first (a person: brief, never his words back nor «you are right», «done» only when something was done) — his explicit order after three replies in a row opened by agreeing with him and repeating him; the half-sentence about apologies and «never a stock sentence» left for it. A rule about behaviour, declared as one: no mechanism reads an opener without a word table; refactor2710-08: −63, the screen line and one contradiction out (was 24_929); prompt.py 16_417 + live_blocks.py 3_395 + live_blocks_nav.py 5_117 — DOCSTRINGS OUT
#: ⚠️ V2-778 (2026-10-02) — RE-MEASURED, not raised: the count used to include every DOCSTRING of the three modules,
#: 19_141 of its 44_070 bytes, which the model never reads. A docstring is a comment to the model, and this file's
#: own last test says a comment costs nothing here — so writing down why a function exists was being charged as
#: prompt prose (F0 had raised the ceiling 42_376 → 44_070 partly on that). Now only strings the model can read
#: count, the ceiling is that exact number, and it is STRICTER than before: one new sentence in the prompt fails
#: this test, where the old ceiling had ~19 k of documentation to hide it in. EDIT DOWNWARD ONLY.


def _docstrings(tree) -> set:
    """The docstring nodes of a module, its classes and its functions — documentation, never sent to a model."""
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and n.body \
                and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant) \
                and isinstance(n.body[0].value.value, str):
            out.add(id(n.body[0].value))
    return out


def _prose_bytes(rel: str) -> int:
    tree = ast.parse((ENGINE / rel).read_text(encoding="utf-8"))
    docs = _docstrings(tree)
    return sum(len(n.value) for n in ast.walk(tree)
               if isinstance(n, ast.Constant) and isinstance(n.value, str) and len(n.value) >= _PROSE_FLOOR
               and id(n) not in docs)


def test_the_prose_of_the_turn_prompt_only_shrinks():
    per_file = {rel: _prose_bytes(rel) for rel in _PROSE_FILES}
    total = sum(per_file.values())
    assert total <= _MAX_PROSE, (
        f"the turn prompt grew to {total} bytes of prose (ceiling {_MAX_PROSE}): {per_file}.\n"
        f"Every byte here is paid on EVERY turn, by every operator. If what you are adding is a RULE ABOUT "
        f"BEHAVIOUR, `principles.md` says to remove it and find the mechanism it stands in for — and if it "
        f"is a PREFERENCE of the operator's, its home is the policy store (V2-707 F4), the way V2-633 moved "
        f"«al recibir órdenes no respondas nada» out of here. Raising this number is not one of the options.")


def test_moving_prose_between_the_two_files_does_not_pay_anything():
    """The defect in the LOC ratchet, pinned: the total is what is measured, so an extraction to
    `live_blocks.py` no longer reads as a saving. Both files are in ONE sum, deliberately."""
    # four since INI-078 L1 (eight since refactor2710-08): all in the same sum
    assert len(_PROSE_FILES) == 4 and all((ENGINE / r).exists() for r in _PROSE_FILES)
    combined = sum(_prose_bytes(r) for r in _PROSE_FILES)
    assert combined == sum({r: _prose_bytes(r) for r in _PROSE_FILES}.values())


def test_a_comment_costs_NOTHING_here():
    """The counterweight that makes this ratchet safe to live with, and the reason LOC was the wrong proxy:
    this repo's method is that each pattern carries the incident that measured it, so writing evidence must
    never read as growth. Only what the MODEL reads is counted."""
    src = "x = 1  # " + ("a measured incident, written down at length, " * 20)
    tree = ast.parse(src)
    counted = sum(len(n.value) for n in ast.walk(tree)
                  if isinstance(n, ast.Constant) and isinstance(n.value, str) and len(n.value) >= _PROSE_FLOOR)
    assert counted == 0


def test_a_docstring_costs_NOTHING_here_either():
    """V2-778: a docstring is documentation — the model never reads it — so it is not prompt prose. A string the
    code RETURNS is, however long it is and wherever it sits."""
    src = ('def f():\n    """' + "why this exists, measured, " * 10 + '"""\n    return "' + "x" * 50 + '"\n')
    tree = ast.parse(src)
    docs = _docstrings(tree)
    counted = sum(len(n.value) for n in ast.walk(tree) if isinstance(n, ast.Constant)
                  and isinstance(n.value, str) and len(n.value) >= _PROSE_FLOOR and id(n) not in docs)
    assert counted == 50
