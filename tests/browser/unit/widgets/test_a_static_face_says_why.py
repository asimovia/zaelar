"""A face nothing moves declares it, with the reason — never by leaving `state` out (V2-884 C8 step 5).

Step 6 makes `state` required for every app; before it, an app with no `state` could be one that was never migrated
or one with nothing to report, and the two read the same. A static face says `{"static": "<why>"}`: it gets no state
line, no door and no revision to ack, and the reason is checked to exist. The clock is the first (it shows the time,
which every turn already carries). Disarms (named in the test): the reason not checked → a bare `static` passes; the
served data stamping a static face → a revision nothing will ever ack.
"""
from __future__ import annotations

import json
import pathlib

from widgets import state, state_decl, state_render

ENGINE = pathlib.Path(__file__).resolve().parents[4]


def test_a_static_face_declares_why_and_gets_no_line_no_door_no_revision():
    man = json.loads((ENGINE / "widgets/clock/manifest.json").read_text())
    assert set(man["state"]) == {"static"} and state_decl.problem(man) is None
    assert state_render.clause("clock") == "", "a static face got a state line"
    assert state.report("clock", {"dev": "desktop:aaa", "mount": "m", "n": 1, "patch": {}})[0] == 404
    assert "_rev" not in state.served("clock", "", {"now": "12:00"}), "a static face was handed a revision to ack"


def test_static_needs_its_reason_and_stands_alone():
    assert "static" in state_decl.problem({"state": {"static": "x"}}), "a bare static passed"
    assert "static" in state_decl.problem({"state": {"static": 1}})
    assert state_decl.problem({"state": {"static": "a long enough reason", "report": {}}}) is not None
