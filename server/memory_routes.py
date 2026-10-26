#
# server/memory_routes.py — HTTP for episodic memory (V2-003 · T54).
#
# ⚠️ IT LIVED IN `memory/server_api.py` until the architecture audit of 2026-08-23, and from there it imported
# `nucleo.dispatch` and `nucleo.memory_agent`: the TWO most serious reverse imports in the memory package (dispatch
# drags in half the engine). They were not a leak to plug; they were the signal that this file is not memory — it is
# TRANSPORT. A FastAPI router that verifies a worker's token against the dispatcher's registry belongs in
# the server layer by definition, and there those imports are the NORMAL direction. The memory package remains
# autonomous without losing anything: memory is still what does the resolving, this only exposes it over HTTP.
#
# Replaces files/server_api.py: the
# operator pastes an image or drags a file onto the frontend (frontend/app/main.js), and it lands here. Instead of
# the old flat files/uploads/ tray plus a [SYSTEM] note containing the path (which was for Hermes file
# tools), the binary now goes to EPISODIC memory (bytes in the data directory, searchable embedded summary) →
# the brain's retriever finds it on its own, without an absolute path or Hermes tools. No auth: the same
# trust model as the rest of the local API.
#
import asyncio
import os

from fastapi import APIRouter, Body, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from memory import api as memapi

router = APIRouter()

_MAX_BYTES = 50 * 1024 * 1024   # 50 MB — ample for screenshots/PDFs, an inexpensive safeguard against filling the disk


@router.post("/api/files/upload")
async def upload(file: UploadFile = File(...), source: str = Form("drop")):
    data = await file.read()
    if len(data) > _MAX_BYTES:
        raise HTTPException(413, "archivo demasiado grande")
    # to_thread (2026-07-19 P1-4 audit): write_episode computes the summary embedding SYNCHRONOUSLY
    # (HTTP to Ollama, 20s timeout) — never in uvicorn's event loop (SSE/queue/widgets run there).
    ref = await asyncio.to_thread(
        memapi.write_episode, data, filename=file.filename or "archivo", mime=file.content_type or None,
    )
    return {"name": ref["name"], "size": ref["bytes"], "episode_id": ref["episode_id"]}


@router.get("/api/files")
async def list_files():
    eps = memapi.list_episodes()
    return {"files": [{"name": e["name"], "size": e.get("bytes"), "mime": e.get("mime"),
                       "summary": e.get("summary"), "episode_id": e["id"]} for e in eps]}


#: Window the default recall reads the conversation record over, in hours. The buffer keeps about this long.
_CONVERSATION_HOURS = 48.0


def _session_at(ts) -> str:
    """The work session open when a conversation line was written — from observability, which owns the event log.
    Unknown is '' and is said so; a broken read is reported, never swallowed into an empty field."""
    try:
        from observability import flows as _flows
        return _flows.session_at(float(ts or 0))
    except Exception as e:  # noqa: BLE001
        from voice.observer import emit
        emit("memory", "session lookup failed", text=str(e)[:160], extra={"module": "server.memory_routes"})
        return "?"


def _line(m: dict) -> str:
    """One digest line a worker can read and CITE: [when · where · who] text."""
    where = {"memory": f"memory/{m.get('kind') or '?'}", "conversation": "conversation",
             "message": "message"}.get(m.get("lane"), m.get("lane") or "?")
    tags = [m.get("created") or "?", where]
    if m.get("lane") == "conversation":
        if m.get("session"):
            tags.append(f"session {m['session'][:8]}")
        tags.append(m.get("who") or "?")
    else:
        if m.get("source"):
            tags.append(str(m["source"]))
        if m.get("entity"):
            tags.append(str(m["entity"]))
    return f"- [{' · '.join(tags)}] {m.get('text', '')}"


def _recall_sync(q: str, k: int, source: str, kind: str, hours: float) -> dict:
    # The lanes a recall can be filtered to (V2-802 T-06). Any other `source` value is read as a writer's
    # `meta.source` («whatsapp», «email», «voice», «worker:…») and narrows every lane to that source.
    is_lane = source in ("all", "memory", "messages", "conversation")
    lane = source if is_lane else "all"
    by_source = "" if is_lane else source
    kinds = {x.strip() for x in (kind or "").split(",") if x.strip()}
    out: list[dict] = []
    if q and lane in ("all", "memory", "messages"):
        r_lane = {"all": "all", "memory": "own", "messages": "messages"}[lane]
        res = memapi.query(q, limit=k, lane=r_lane)
        # `conv` rows are in the own lane of the retriever, but here they are served by the conversation reader
        # below, with who said them and when — not as a bare pill.
        mems = [m for m in (res.get("memories") or []) if m.get("text") and m.get("kind") != "conv"]
        prov = memapi.provenance([m["id"] for m in mems])
        for m in mems:
            p = prov.get(int(m["id"])) or {}
            out.append({"id": m["id"], "text": m.get("text", ""), "kind": m.get("kind", ""),
                        "slot": m.get("slot") or "", "level": m.get("level", ""), "created": p.get("created", ""),
                        "source": p.get("source"), "entity": p.get("entity"), "lane": p.get("lane", "memory")})
    if lane in ("all", "conversation") and (q or lane == "conversation"):
        h = hours or _CONVERSATION_HOURS
        sessions: dict[int, str] = {}                            # one lookup per turn, not per line
        for c in memapi.conversation(hours=h, query=q, limit=k if lane == "all" else 4 * k):
            if c["id"] not in sessions:
                sessions[c["id"]] = _session_at(c["ts"])
            out.append({"id": c["id"], "text": c["text"], "kind": "conv", "slot": "", "level": "short",
                        "created": c["at"], "source": "conv", "entity": None, "lane": "conversation",
                        "who": c["who"], "session": sessions[c["id"]]})
    if by_source:
        out = [m for m in out if str(m.get("source") or "") == by_source]
    if kinds:
        out = [m for m in out if m.get("kind") in kinds]
    # Lane order is the ranking contract: his own memory, then what he said, then what others wrote to him.
    order = {"memory": 0, "conversation": 1, "message": 2}
    out.sort(key=lambda m: order.get(m.get("lane"), 3))         # stable: each lane keeps its own order
    return {"memories": out, "text": "\n".join(_line(m) for m in out) or "(sin recuerdos relevantes)"}


@router.post("/api/memory/recall")
async def memory_recall(query: str = Body("", embed=True), k: int = Body(8, embed=True),
                        source: str = Body("all", embed=True), kind: str = Body("", embed=True),
                        hours: float = Body(0, embed=True)):
    """MEMORY bridge for the SlowBrain Claude Code agents (V2-036): direct READ (no LLM, milliseconds) of the
    memories relevant to `query`. It is the "ask for a fact" half of the serial component: the agent makes one call,
    receives the nuggets, and continues execution. Read-only (it does not change weights here beyond the query's
    normal reinforcement).

    WITH PROVENANCE (V2-802 T-06): every row carries `id`, `created` (local ISO), `level`, `kind`, `slot`,
    `source`/`entity` and its `lane`, and the digest prints them, so a worker can tell an inbound email from a fact
    the operator dictated and can cite where «it is on record». Three lanes, in this order, never fused:
    `memory` (his facts, pills, errand results), `conversation` (what was said, verbatim, with session and who —
    V2-803 T-01) and `messages` (what others wrote him). `source` filters to one lane, or to one writer's
    `meta.source` (`whatsapp`, `email`, `voice`…); `kind` to a comma list of kinds. `source="conversation"` with an
    empty query reads the last `hours` (default 48) of conversation whole."""
    q = (query or "").strip()
    src = (source or "all").strip().lower() or "all"
    if not q and src != "conversation":
        return {"memories": [], "text": ""}
    try:
        # to_thread (2026-07-19 P1-4 audit): query = embedding + retriever + reranker (hundreds of ms) —
        # outside the server's event loop, as FlashBrain already does (V2-011).
        return await asyncio.to_thread(_recall_sync, q, max(1, min(int(k or 8), 20)), src, kind or "",
                                       float(hours or 0))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"recall falló: {e}")


def _worker_source(task_id: str, token: str) -> str | None:
    """Per-task auth for the write bridge (2026-07-14 audit): same scheme as `/api/worker/act` —
    the worker sends its `ZAELAR_TASK_ID`/`ZAELAR_TASK_TOKEN` (headers, set by `mem_cli`), and they are verified
    against the dispatch RAM registry. Returns the provenance label, or None if authorization fails.
    `ZAELAR_MEM_API_OPEN=1` = hatch for local dev/scripts (`source="local"` is stamped)."""
    if task_id and token:
        try:
            from nucleo import dispatch
            rec = dispatch.get_record(task_id)
            if rec is not None and dispatch.rec_token(rec) == token:
                return f"worker:{task_id}"
        except Exception:
            return None
        return None
    if os.getenv("ZAELAR_MEM_API_OPEN", "").strip() == "1":
        return "local"
    return None


@router.post("/api/memory/remember")
async def memory_remember(text: str = Body(..., embed=True), slot: str = Body("", embed=True),
                          kind: str = Body("", embed=True), importance: float = Body(None, embed=True),
                          x_zaelar_task: str = Header("", alias="X-Zaelar-Task"),
                          x_zaelar_token: str = Header("", alias="X-Zaelar-Token")):
    """MEMORY bridge for Brain Workers (V2-036/V2-038): WRITING through the ONE authorized writer
    (async queue), preserving the single-writer invariant. Hardened in the 2026-07-14 audit:
    it requires the worker's PER-TASK token (headers from `mem_cli`) and goes through
    `memory_agent.remember_external` — the same precision gates as voice, with no access to `state` or identity slots."""
    t = (text or "").strip()
    if not t:
        raise HTTPException(400, "text vacío")
    source = _worker_source(x_zaelar_task.strip(), x_zaelar_token.strip())
    if source is None:
        raise HTTPException(401, "token de tarea inválido o ausente (ZAELAR_TASK_ID/ZAELAR_TASK_TOKEN)")
    item = {"text": t}
    if slot:
        item["slot"] = slot
    if kind:
        item["kind"] = kind
    if importance is not None:
        item["importance"] = float(importance)
    try:
        from nucleo import memory_agent
        res = await memory_agent.remember_external(item, source=source)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"remember falló: {e}")
    if not res.get("ok"):
        raise HTTPException(422, f"descartado por el gate de precisión ({res.get('reason')})")
    return res


@router.get("/api/memory/map")
async def memory_map():
    """COMPLETE map of memory for the VIEWER (V2-014 · T129): state + memories by layer (short/long) +
    graph (`edges`) + complete metadata (scoring, weight, access, recency, ttl, pinned, dates). Read-only,
    `no-cache` — the viewer rereads it on the fly when the `memory.updated` signal arrives via SSE (real time)."""
    return JSONResponse(await asyncio.to_thread(memapi.map), headers={"Cache-Control": "no-cache"})
