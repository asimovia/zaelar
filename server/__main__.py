#!/usr/bin/env python3
"""
zaelar — personal voice assistant (English). Entrypoint for the whole app.
The FastAPI app + routes live in this `server/` package; run it as a module.

  Single screen / · live voice API (WebRTC offer/ice · SSE events).

Run:  ./.venv/bin/python -m server      → http://localhost:43917
   (or: make run)   ·   self-contained: zaelar/.venv + zaelar/.env
"""
import os
import sys

# The engine is developed and shipped on 3.12; an older interpreter fails later, deep inside a dependency,
# with an error that never names the real cause. Refuse at the door instead (V2-601 T-11).
if sys.version_info < (3, 11):
    sys.exit(f"zaelar needs Python >= 3.11 (you are on {sys.version.split()[0]}). "
             "Create the venv with a newer interpreter: python3.12 -m venv .venv")

from loguru import logger

logger.remove()
logger.add(sys.stderr, level=os.getenv("LOG_LEVEL", "INFO"),
           format="{time:HH:mm:ss.SSS} | {level: <7} | {message}")

# repo ROOT (parent of server/) must be importable so the domain packages resolve:
# voice/ · brains/ · widgets/ · config/ · server/  (works for both `python -m server` and a direct run)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# THE PER-TENANT TREE, BEFORE ANYTHING READS A PATH (V2-562). `server/__init__` pulls in config/settings.py,
# which loads `settings.json` at import time, and everything downstream resolves its own persistent path the same
# way. On a self-host clone those directories come from git; on a cloud Machine the mounted Volume starts EMPTY,
# and every one of those writers then fails best-effort and steps over it. This one line is what makes a first
# boot on an empty disk indistinguishable from every later one — so it has to run BEFORE the import below, not
# inside a FastAPI startup hook that fires after it.
from nucleo import workspace as _workspace  # noqa: E402

_workspace.ensure()

from server import app  # noqa: E402

if __name__ == "__main__":
    import asyncio
    import uvicorn

    # zaelar's FIXED local port (43917): it always starts here — never a random port — unless PORT is overridden
    # (prod sets 8080). Every other port the instance opens is fixed too; the list is `scripts/zaelar.py::PORTS`.
    host = os.getenv("HOST", "localhost"); port = int(os.getenv("PORT", "43917"))
    logger.info(f"Assistant (voice) on http://{host}:{port}")
    servers = [uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="warning"))]

    async def _serve_all():
        await asyncio.gather(*(s.serve() for s in servers))

    asyncio.run(_serve_all())
