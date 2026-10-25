"""Every event kind declares which screen it is for (V2-792, node 4.266).

`frontend/app/services/event-scope.js` is the ONE table that says what a request does to the screen that asked
(`origin`) and what the whole conversation shares (`all`). Scoping by `if`s scattered through `sse.js` is how the
widget flags decayed; so a kind routed by `sse.js` that is in NEITHER list fails here, and the author of a new kind
has to decide where it belongs.

Also pinned: the placement rule itself (run under Node, the real module), and the wiring of the immediate hand-over —
the stream's «voice held by» event reaches `session-lk.js`, which stands down on it instead of waiting for a beat.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess

import pytest

ENGINE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
SVC = os.path.join(ENGINE, "frontend", "app", "services")


def _strip(src: str) -> str:
    """Prose about the pattern is not the pattern: comments are removed before any source check."""
    return re.sub(r"^[ \t]*//.*$", "", re.sub(r"/\*[\s\S]*?\*/", "", src), flags=re.M)


def _node(script: str):
    if not shutil.which("node"):
        pytest.skip("node not installed")
    r = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, cwd=SVC,
                       timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_every_kind_sse_routes_has_a_declared_scope():
    routed = set(re.findall(r'd\.kind === "([a-z_]+)"', _strip(open(os.path.join(SVC, "sse.js")).read())))
    tables = _node("import * as s from './event-scope.js'; "
                   "console.log(JSON.stringify({o: Object.keys(s.ORIGIN_SCOPED), a: s.ALL_SCREENS}))")
    declared = set(tables["o"]) | set(tables["a"])
    assert routed, "sse.js routes no kind at all — the regex no longer reads it"
    assert not (routed - declared), f"kinds routed with no declared screen: {sorted(routed - declared)}"
    assert not (set(tables["o"]) & set(tables["a"])), "a kind cannot be both origin- and all-scoped"


def test_a_card_opens_where_it_was_asked_and_the_conversation_everywhere():
    out = _node("""import { placement } from './event-scope.js';
      const D = 'desktop:a', P = 'mobile:b';
      console.log(JSON.stringify({
        showHere:   placement({kind:'widget', label:'show', origin_dev: D}, D),
        showThere:  placement({kind:'widget', label:'show', origin_dev: D}, P),
        fullThere:  placement({kind:'widget', label:'fullscreen', origin_dev: D}, P),
        panelThere: placement({kind:'panel', label:'open', origin_dev: D}, P),
        closeThere: placement({kind:'widget', label:'close', origin_dev: D}, P),
        dataThere:  placement({kind:'widget', label:'data', origin_dev: D}, P),
        talkThere:  placement({kind:'transcript', origin_dev: D}, P),
        unstamped:  placement({kind:'widget', label:'show'}, P),
      }));""")
    assert out == {"showHere": "apply", "showThere": "elsewhere", "fullThere": "elsewhere",
                   "panelThere": "elsewhere", "closeThere": "apply", "dataThere": "apply",
                   "talkThere": "apply", "unstamped": "apply"}


def test_the_screen_that_loses_the_voice_stands_down_on_the_stream_event():
    sse = _strip(open(os.path.join(SVC, "sse.js")).read())
    lk = _strip(open(os.path.join(SVC, "session-lk.js")).read())
    assert re.search(r'd\.kind === "session" && d\.voice_sid', sse)
    assert re.search(r'new CustomEvent\("hb:voice-held"', sse)
    listener = re.search(r'addEventListener\("hb:voice-held",[\s\S]{0,260}?\}\);', lk)
    assert listener, "session-lk.js does not listen for the hand-over"
    assert "_lostVoice(" in listener.group(0) and "!== SID" in listener.group(0)


def test_a_screen_without_the_voice_types_over_http():
    lk = _strip(open(os.path.join(SVC, "session-lk.js")).read())
    body = re.search(r"export function sendText\(text\) \{[\s\S]*?\n\}", lk).group(0)
    assert re.search(r"if \(!started && !starting\) \{\s*api\.chatText\(", body)
