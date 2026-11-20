"""A disposable engine with the conversation manager switched on (V2-941, B7; node 13.52) — for the live passes.

    ./.venv/bin/python -m tests.conversation.e2e.sandbox --lang es [--keep DIR] [--port N]

Boots an isolated engine (`tests/platform/sandbox_engine.py`: its own port, database, workspace and logs; never the
operator's) with the manager's switch on, EVERY outside write held and the language chosen — the three conditions the
switch fails closed on — and seeds what the suites assume: the contacts Rowan and Inworld and three appointments
(`corpus_drive.Engine.seed`). Prints the port and waits; Ctrl-C stops it and removes the workspace. The suites then
run against it: `tests.conversation.e2e.text_suite`, `tests.conversation.tools.corpus_drive`, `…tools.user_sim`.
"""
from __future__ import annotations

import argparse
import signal
import tempfile
import threading
from pathlib import Path

#: the switch on, every outside write held — without the hold the switch refuses the session (it fails closed)
ENV = {"ZAELAR_CONVERSATION": "1", "ZAELAR_HOLD_OUTBOUND": "all"}


def env_for(lang: str) -> dict:
    return {**ENV, "ZAELAR_LANGUAGE": lang}


def boot(lang: str, *, workspace: Path, port: int | None = None, spawn=None, client=None):
    """Spawn the engine and seed it; returns (engine, what the seed answered). `spawn` and `client` are the platform's
    by default — a test passes doubles."""
    from tests.conversation.tools.corpus_drive import Engine
    from tests.platform import sandbox_engine as sb
    spawn = spawn or sb.spawn_engine
    eng = spawn(workspace=workspace, port=port or sb.free_port(), extra_env=env_for(lang), boot_timeout=120.0)
    seeded = (client or Engine)(port_of(eng)).seed(lang)
    return eng, seeded


def port_of(eng) -> int:
    return int(str(eng.base_url).rstrip("/").rsplit(":", 1)[1])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default="es", choices=["es", "en"])
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--keep", type=Path, default=None, help="a workspace that survives the run, for inspection")
    a = ap.parse_args(argv)
    from tests.platform import sandbox_engine as sb
    tmp = None if a.keep else tempfile.TemporaryDirectory(prefix="zaelar-conv-sandbox-")
    workspace = a.keep or Path(tmp.name)
    eng, _seeded = boot(a.lang, workspace=workspace, port=a.port)
    print(f"sandbox up: port {port_of(eng)} · lang {a.lang} · switch on · ZAELAR_HOLD_OUTBOUND=all · workspace {workspace}")
    print(f"proof: http://127.0.0.1:{port_of(eng)}/api/debug/conversation/me — Ctrl-C stops it", flush=True)
    done = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: done.set())
    signal.signal(signal.SIGTERM, lambda *_: done.set())
    try:
        done.wait()
    finally:
        sb.stop_engine(eng)
        if tmp is not None:
            tmp.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
