"""A recall searches the operator's OWN words first, and a reference to the conversation fires it (V2-865, second cut).

Measured 2026-11-09 on build 118: the model's recall query was its own paraphrase of his request; the paraphrase's
words reached the complaint turns, his own sentence reached the one turn that named the artist. And the turn that
said «I did ask you some time ago…» fired no recall at all: `recall_fired` read `needs_recall` only.

Pinned here:
  · `conversation_lines(query, his_words=…)` searches his words first and fills with the paraphrase, merged,
    chronological, at most `CONVERSATION_TURNS` turns, each side cut at `CONVERSATION_CHARS` as rendered;
  · the voice recall pass hands his sentence over (`recall_spoken` → `compose_recall(…, his_words=text)`);
  · `recall_fired` is `needs_recall or needs_recent`.
"""
import ast
import time
from pathlib import Path

import pytest

from memory import db as memdb
from memory import embeddings as mememb
from memory import writer as memwriter

ENGINE = Path(__file__).resolve().parents[4]
H = 3600


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    monkeypatch.setenv("ZAELAR_MEM_OBSERVABILITY", "0")
    mememb.reset()
    yield
    mememb.reset()


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


def _turn(u: str, a: str, ago_s: int) -> int:
    mid = memwriter.insert_memory(f"Operador: {u} · zaelar: {a}", kind="conv", level="short", importance=0.2,
                                  ttl_days=2.0, meta={"source": "conv", "u": u, "a": a})
    memdb.get_db().execute("UPDATE memories SET created=? WHERE id=?", (int(time.time()) - ago_s, mid))
    return mid


HIS = "I did ask you some time ago to put some music here, the artist co-starring in that drama, play her"
PARAPHRASE = "vocalist television programme actress"


def _the_day():
    _turn("put some music here by an artist co-starring in that drama",
          "She co-stars in the drama and sings; playing her now", 5 * H)
    for i in range(4):                                   # an older episode the PARAPHRASE matches better
        _turn(f"which vocalist from the television programme {i}", f"the actress or the vocalist {i}?",
              2 * H + (4 - i) * 30 * 60)


def test_his_own_words_reach_the_turn_the_paraphrase_misses(fresh_db):
    from nucleo.turn.prompt import recall
    _the_day()
    only_paraphrase = "\n".join(recall.conversation_lines(PARAPHRASE, skip_newest=0))
    assert "playing her now" not in only_paraphrase, "the paraphrase alone does not reach it (the measured miss)"
    lines = recall.conversation_lines(PARAPHRASE, skip_newest=0, his_words=HIS)
    assert any("playing her now" in ln for ln in lines), lines
    assert len(lines) <= recall.CONVERSATION_TURNS


def test_the_merged_lines_are_chronological_and_cut_per_side(fresh_db):
    from nucleo.turn.prompt import recall
    # His words find the NEWER turn first and the paraphrase the older one: the merge must put them back in order.
    _turn("which vocalist from the television programme", "the actress or the vocalist?", 5 * H)
    _turn("put some music here by an artist co-starring in that drama " + "x" * 400,
          "She co-stars in the drama; playing her now " + "y" * 400, 2 * H)
    lines = recall.conversation_lines(PARAPHRASE, skip_newest=0, his_words=HIS)
    assert len(lines) == 2 and "vocalist" in lines[0] and "co-starring" in lines[1], lines
    assert recall.CONVERSATION_CHARS == 200
    assert "x" * 100 in lines[1] and "x" * 201 not in lines[1] and "y" * 201 not in lines[1], \
        "each side is cut as rendered, so one long row cannot spend the lane"


def _calls(rel: str, name: str) -> list[ast.Call]:
    tree = ast.parse((ENGINE / rel).read_text(encoding="utf-8"))
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call)
            and getattr(n.func, "attr", getattr(n.func, "id", "")) == name]


def test_the_voice_recall_hands_his_sentence_over():
    calls = _calls("nucleo/flash/tool_round.py", "compose_recall")
    assert calls and all(any(k.arg == "his_words" for k in c.keywords) for c in calls), \
        "the voice recall searched the model's paraphrase only"


def test_a_reference_to_the_conversation_fires_the_recall():
    tree = ast.parse((ENGINE / "voice/engine/llm/providers/turn_prompt.py").read_text(encoding="utf-8"))
    fired = [n.value for n in ast.walk(tree) if isinstance(n, ast.Assign)
             and any(isinstance(t, ast.Subscript) and getattr(t.slice, "value", None) == "recall_fired"
                     for t in n.targets)]
    assert fired, "recall_fired is no longer set here"
    named = {getattr(c.func, "attr", "") for v in fired for c in ast.walk(v) if isinstance(c, ast.Call)}
    assert {"needs_recall", "needs_recent"} <= named, f"«I did ask you some time ago…» fires nothing: {named}"
