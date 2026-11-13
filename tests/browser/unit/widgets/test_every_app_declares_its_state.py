"""Every app says what its face shows — `state` is REQUIRED, and the generator is taught it (V2-884 C8 step 6).

Until step 6 a manifest with no `state` meant «not migrated yet»; with every shipped app declaring one, a missing
block is a defect: the gate (`validator._validate`, what the generator runs on everything it builds or changes) refuses
it with a sentence that says what to declare; the contract the code agent reads (`generator._CONTRACT`, in the create
AND the modify prompt), `widgets/AGENTS.md` and the new-widget checklist teach order · report · facts, `static` with its
reason, `by: "host"`, and never `adopt` on a shared app; an app on disk that predates the rule (his own, never
rewritten without asking) is named LOUD when the catalogue loads it, never skipped in silence. Disarms (named in the
test): the requirement off → a manifest with no state passes the gate; the contract bullet gone → the agent is never
told; the catalogue warning gone → an undeclared app loads in silence.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from widgets import state_decl

ENGINE = pathlib.Path(__file__).resolve().parents[4]
WIDGETS = ENGINE / "widgets"


def _apps():
    return sorted(p.parent.name for p in WIDGETS.glob("*/manifest.json") if not p.parent.name.startswith("_"))


@pytest.mark.parametrize("app", _apps())
def test_every_shipped_app_declares_a_valid_state(app):
    man = json.loads((WIDGETS / app / "manifest.json").read_text(encoding="utf-8"))
    assert state_decl.problem(man) is None, f"{app}: {state_decl.problem(man)}"


def _scratch(tmp_path, monkeypatch, wid, **extra):
    from widgets import paths
    d = tmp_path / wid
    d.mkdir()
    (d / "manifest.json").write_text(json.dumps({"id": wid, "title": "Probe", "keywords": [f"{wid}-kw"],
                                                 "entry": "widget.js", "screens": "shared", **extra}), encoding="utf-8")
    (d / "widget.js").write_text("export function render(el, data, ctx) { el.textContent = ''; }\n", encoding="utf-8")
    monkeypatch.setattr(paths, "dir_for", lambda w: str(d) if w == wid else None)
    monkeypatch.setattr(paths, "is_repo_source", lambda _d: True)
    return wid


def test_the_gate_refuses_an_app_without_state_and_says_what_to_declare(tmp_path, monkeypatch):
    from widgets import validator
    wid = _scratch(tmp_path, monkeypatch, "zz-no-state")
    ok, err = validator._validate(wid, stamp_origin=True)
    assert not ok and "state is required" in err and "static" in err and "report" in err, err


def test_the_gate_passes_the_smallest_declared_app(tmp_path, monkeypatch):
    from widgets import validator
    wid = _scratch(tmp_path, monkeypatch, "zz-static", state={"static": "a probe face that nothing moves"})
    assert validator._validate(wid, stamp_origin=True) == (True, "")


def test_the_code_agent_and_the_docs_are_taught_state():
    from widgets import generator
    c = generator._CONTRACT
    assert "\n- WHAT DOES ITS FACE SHOW? (REQUIRED" in c and c in generator._CREATE_PROMPT and c in generator._MODIFY_PROMPT
    prompt = generator._CREATE_PROMPT.format(wid="x", spec="s", folder="f")
    for word in ('"order"', '"report"', '"facts"', '"static"', '"by": "host"', '"adopt"', "ctx.state(", "applied: true"):
        assert word in prompt, f"the agent is not told {word}"
    agents = (WIDGETS / "AGENTS.md").read_text(encoding="utf-8")
    assert '**Declare `"state"` in `manifest.json`**' in agents and '"static"' in agents and '"by": "host"' in agents
    flow = (ENGINE / ".meshkore/docs/ops/zaelar-new-widget-or-connector-workflow.md").read_text(encoding="utf-8")
    assert '`"state"` declared (V2-884' in flow


def test_an_undeclared_app_on_disk_is_named_loud_once(tmp_path, monkeypatch):
    from loguru import logger
    from widgets import runtime
    said = []
    sink = logger.add(lambda m: said.append(str(m)), level="WARNING")
    try:
        runtime._WARNED.clear()
        runtime._undeclared({"id": "his-own-app"}, str(tmp_path / "his-own-app"), 1.0)
        runtime._undeclared({"id": "his-own-app"}, str(tmp_path / "his-own-app"), 1.0)
        runtime._undeclared({"id": "declared", "state": {"static": "nothing moves it here"}}, str(tmp_path), 1.0)
    finally:
        logger.remove(sink)
    assert len(said) == 1 and "his-own-app" in said[0] and "declares no `state`" in said[0], said
