"""V2-750 — a document that CALLS itself the source of truth is not one until something measures it.

Found 2026-09-22 while the operator asked for the context to be pruned and kept current. §8 of
`.meshkore/docs/architecture/zaelar-architecture.md` opens with

    «**This is the single source of truth for the FlashBrain's function-calling catalog**
     (`nucleo/flash/router.py::TOOLS`) (…) no dead/stale entries.»

and listed **20** tools while `router.TOOLS` held **29**. Nine capabilities — `show_panel`,
`fullscreen_widget`, `arrange_canvas`, `read_widget`, `search_listings`, `show_images`,
`reopen_task`, `restore_widget`, `set_cluster_objective` — existed in the engine and did not exist
in the page an agent reads to learn what the engine can do.

That is the V2-540 failure pointed at ourselves: a capability nobody can see is one nobody uses, and
the next agent to wonder «is there a tool for this?» reads the doc, finds nothing, and writes a
second one. Nothing about that decay was noisy. It cannot be, because prose does not fail.

So the claim becomes a measurement, in BOTH directions: a tool added to the code without a row is a
capability nobody will find, and a row left behind after a tool is retired is worse — it sends the
next reader looking for something that is gone.

Since INI-078 L1 the catalogue is the conversation manager's declared reads and acts
(`nucleo/conversation_host/declared.json`); the old router's `TOOLS` went with the old turn.

Run: .venv/bin/pytest tests/infrastructure/unit/test_the_canonical_tool_catalog_is_canonical.py
"""
from __future__ import annotations

import pathlib
import re

ENGINE = pathlib.Path(__file__).resolve().parents[3]
DOC = ENGINE / ".meshkore" / "docs" / "architecture" / "zaelar-architecture.md"
HEADING = "## 8. The model's tool catalog"


def _documented() -> set[str]:
    """The tool names in §8's table — the first backticked token of every table row."""
    src = DOC.read_text(encoding="utf-8")
    start = src.index(HEADING)
    end = src.index("\n## ", start + len(HEADING))
    names = set()
    for line in src[start:end].split("\n"):
        if not line.startswith("| `"):
            continue
        hit = re.findall(r"`([a-z][a-z0-9_]*)`", line)   # tool names may hold digits (a2a_*)
        if hit:
            names.add(hit[0])
    return names


def test_the_table_was_actually_found():
    """A parser that silently reads nothing makes both assertions above vacuous — the exact shape of
    a guard that goes green the day the thing it guards disappears."""
    assert len(_documented()) >= 20, "§8's table did not parse; the two checks above proved nothing"


def _declared() -> set[str]:
    import json
    d = json.loads((ENGINE / "nucleo" / "conversation_host" / "declared.json").read_text(encoding="utf-8"))
    return set(d["reads"]) | set(d["acts"])


def test_every_declared_tool_has_a_row():
    missing = sorted(_declared() - _documented())
    assert not missing, f"declared in declared.json and absent from §8 — a capability nobody will find: {missing}"


def test_no_row_names_a_tool_that_is_gone():
    stale = sorted(_documented() - _declared())
    assert not stale, f"§8 rows for tools declared.json no longer has: {stale}"
