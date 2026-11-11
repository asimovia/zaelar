#
# HTTP surface for the «Colmena» cron — the Tasks tab's periodic and scheduled rows (frontend/app/components/ChatWall.js).
#
# v2 «Colmena» (V2-005/009): replaces the old Hermes `/api/cron` (brains/hermes/cron_api.py, retired).
# The engine's OWN proactivity lives in `nucleo/pulse/scheduler.py` (tasks persisted in `memory.journal`,
# fired by the orchestrator loop `nucleo/pulse/loop.py`). This router is only the MANUAL surface: list and delete.
# A job is CREATED by asking the agent (V2-883): the hand-filled form and its `/api/cron/create` route were removed —
# a cadence typed as «0 9 * * *» was a second way in that nothing on the voice side could read back or correct. Mounted under the brain whose loop actually fires them (V2-601
# T-14: mounting it under a brain that does not run the loop is the V2-121 silent-alarm class).
#
from fastapi import APIRouter
from pydantic import BaseModel

from nucleo.pulse import scheduler

router = APIRouter()


class RefBody(BaseModel):
    ref: str


@router.get("/api/cron")
async def list_cron():
    # The panel expects {jobs:[{id,name,schedule,prompt,state,paused,...}]}. `state`/`paused` are from
    # the Hermes era (pause/resume); this scheduler does not pause — a task is active until it is met
    # or deleted.
    jobs = []
    for j in scheduler.list_jobs(active_only=True):
        jobs.append({**j, "state": "activo", "paused": False})
    return {"jobs": jobs}


@router.post("/api/cron/remove")
async def remove_cron(body: RefBody):
    ok = scheduler.cancel(body.ref)
    return {"ok": ok, "message": "tarea cancelada" if ok else "no encontrada"}
