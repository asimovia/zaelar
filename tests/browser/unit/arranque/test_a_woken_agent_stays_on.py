"""Nobody wakes the agent to leave it stopped (INI-042 #46, node 4.598).

Measured on the operator's Machine (2026-11-19 16:31): the Machine resumed from its sleep with the agent RUNNING on the
server, the desktop tab reloaded, its storage still said «stopped» from an older moment, and the boot probe SENT that old
⏻ to the server (`api.runStop("client_state")`) — the agent stopped with nobody pressing anything, and he had to press ⏻.
The phone shell had the same line. The class: a page's stored ⏻ stopping a running agent.

So: (1) the only client code that stops the agent is the ⏻ door, `power.setPower` — no boot, reconcile or sync path
calls `runStop`; (2) both shells' boot probe goes through `presence.reflectRunState`, which REFLECTS the server's ⏻ and
never sends one; (3) run in node, that reflection turns a stale local «stopped» on when the server runs, keeps a real
stop (the agent stopped on purpose still needs ⏻), and leaves alone a reply asked before his last press.
Disarm: the boot probe propagates its stored ⏻ again.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[4]
FRONT = ENGINE / "frontend"
SHELLS = [FRONT / "app" / "main.js", FRONT / "mobile" / "app" / "main.js"]
DOOR = FRONT / "app" / "services" / "power.js"
API = FRONT / "app" / "services" / "api.js"
_CALL = re.compile(r"\brunStop\s*\(")


def _strip_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"(?m)(^|[^:\"'])//.*$", r"\1", src)


def _stoppers(base: Path = ENGINE) -> list[str]:
    """Every client file (and line) under `base/frontend` that calls `runStop(` — the API's own definition excluded."""
    out = []
    for f in sorted((base / "frontend").rglob("*.js")):
        if f.relative_to(base) == API.relative_to(ENGINE) or "node_modules" in f.parts:
            continue
        code = _strip_comments(f.read_text(encoding="utf-8"))
        out += [f"{f.relative_to(base)}:{n}" for n, line in enumerate(code.splitlines(), 1) if _CALL.search(line)]
    return out


def _not_the_door(found: list[str]) -> list[str]:
    return [x for x in found if not x.startswith(str(DOOR.relative_to(ENGINE)) + ":")]


def test_only_the_power_door_stops_the_agent():
    found = _stoppers()
    assert found and not _not_the_door(found), f"a client path other than the ⏻ door stops the agent: {found}"


@pytest.mark.parametrize("shell", SHELLS, ids=lambda p: str(p.relative_to(FRONT)))
def test_each_shell_reflects_the_servers_power_at_boot(shell):
    code = _strip_comments(shell.read_text(encoding="utf-8"))
    assert "reflectRunState(r, askedAt, store)" in code, f"{shell.name}: the boot probe does not reflect the server's ⏻"


_NODE = r"""
const P = await import(process.argv[2]);
const mk = (off, cmdAt = 0) => { const s = { off, cmdAt, setPowerOff: (v) => { s.off = v; },
                                             powerOff: () => s.off, powerCmdAt: () => s.cmdAt }; return s; };
const NOW = 1_800_000_000_000, out = {};
let s = mk(true);  out.stale_off_running = [P.reflectRunState({ running: true }, NOW, s), s.off];
s = mk(false);     out.stopped_on_purpose = [P.reflectRunState({ running: false }, NOW, s), s.off];
s = mk(true, NOW + 1); out.after_his_press = [P.reflectRunState({ running: true }, NOW, s), s.off];
console.log(JSON.stringify(out));
"""


def test_a_stale_stop_follows_the_running_agent_and_a_real_stop_holds(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("node unavailable")
    script = tmp_path / "reflect.mjs"
    script.write_text(_NODE, encoding="utf-8")
    shim = "globalThis.window={addEventListener(){}};globalThis.document={hidden:false,getElementById(){return null}," \
           "createElement(){return {style:{},setAttribute(){}}},body:{appendChild(){}}};globalThis.setInterval=()=>0;"
    r = subprocess.run([node, "--import", "data:text/javascript," + shim, str(script),
                        (FRONT / "app" / "services" / "presence.js").as_uri()],
                       capture_output=True, text=True, timeout=60, cwd=ENGINE)
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout.strip().splitlines()[-1])
    assert got["stale_off_running"] == [False, False], f"woken, the agent stays ON on this screen: {got}"
    assert got["stopped_on_purpose"] == [True, True], f"stopped on purpose, it stays stopped: {got}"
    assert got["after_his_press"] == [None, True], f"a reply older than his press changes nothing: {got}"


def test_disarm_a_boot_probe_that_propagates_its_stored_power_turns_it_red(tmp_path):
    src = SHELLS[0].read_text(encoding="utf-8")
    probe = "if (reflectRunState(r, askedAt, store) === true)"
    assert src.count(probe) == 1, "disarm did not land"
    fake = tmp_path / "frontend" / "app"
    fake.mkdir(parents=True)
    (fake / "main.js").write_text(src.replace(probe, 'if (store.powerOff()) api.runStop("client_state");\n    ' + probe),
                                  encoding="utf-8")
    (fake / "services").mkdir()
    (fake / "services" / "power.js").write_text(DOOR.read_text(encoding="utf-8"), encoding="utf-8")
    stray = _not_the_door(_stoppers(tmp_path))
    assert len(stray) == 1 and stray[0].startswith("frontend/app/main.js:"), stray
