---
title: Architecture
updated: 2026-11-13
status: stable
---

# Architecture — mental model

**Three layers, decoupled** (full model: `docs/architecture/zaelar-architecture.md`):

1. **Voice + canvas** — the ONLY user surface (`:43917`). Mic → STT → brain → TTS, the voice in its own process (`python -m voice.engine`), STT and TTS each behind a relay (titular → OpenAI stand-in, a hung titular bounded in shadow, each metric billed to its producer); widget desktop driven BY VOICE via silent tags over SSE. Every widget REPORTS the state its face shows through one door (`widgets/state.py`) and the turn reads one line per open widget — its report, never its order. `frontend/` is a thin ES-module shell (no build), no business logic.
2. **Brain («Colmena» = `nucleo/`)** — decides + acts. **Flash is the interface and the life; the Worker does the work; the agent's memory is the state.**
   - **FlashBrain** owns the conversation, the reflexes (one declared action, one call), the router, the mouth and the screen. Every turn — voice or text — runs ONE pipeline (`nucleo/turn/pipeline.py`) with ONE model call (non-reasoning, per invocation); nothing runs the model after the main stream.
   - **The router** (`nucleo/turn/flow_of.route`) decides, before anything is opened, where a request goes: conversation, a reflex, an open flow, or a new **task**. Events (an inbound message or mail, a due job, a worker that ended or asked) go through the same door.
   - **A task** = one row of `tasks` + one Brain Worker session per request (Claude Code / Codex), resumable by id, following the **playbook the worker chooses** from its catalogue; checkpoint 1 (playbook + declared end state) is held by the harness before anything leaves. The row is the truth (what it waits for, its open question, its session id); the session is a cache, re-briefed from the row. The worker asks him through Flash and ends; his answer resumes that session.
   - **Verdicts** (`nucleo/turn/verdicts.py`): every reader reads one act floor; at the VETO a sure verdict takes the model's call when what enters leaves or deletes, and the words follow the act. His answer binds to the row that asked him, by identity; a clarification ends with its conversation. What he approved leaves byte-identical.
   - **The circuit** verifies against the task's end state and is the only writer of its ending; an act on a card is done when the app REPORTS it. **One mouth** in a turn (the reply) and one out of it (`nucleo/pulse/notices`).
   - **The internal API**: the worker's hands are the agent's doors, reached through the bridge (`nucleo/cli/`) with a per-task token; consent lives in each door, and a session that read a stranger's text is tainted — its exits ask.
   - **One vocabulary of events** (`nucleo/events/vocabulary.py`): what arrives and what leaves is an event type `<family>.<act>` declared once (channel and subject on the instance); the topics a rule subscribes to, the consent class and level of a leaving act, the grants of a mandate and the effect a manifest action carries are read off that one table — a new act declares itself there and nothing else is written.
   - **Contacts**: one resolver (`widgets/directory.py`) ranks who a name is by sound and closeness, filtered by the act; contacts are structured memory (`nucleo/memory_agent/contacts.py`), groups are rows with ids, REM links one person's records.
   - The pulse (~1 Hz) + own cron + sparks own proactivity. Drives the canvas through a thin tag contract.
3. **Compute** — one atomic headless agent per widget task: born → builds `widgets/<id>/` → exits. File tools only, scoped, hard timeout, output validated.

**The MeshKore network** (`docs/architecture/zaelar-meshkore-network.md`): live agents found through the Oracle; a declared skill is CALLED by id (`nucleo/mesh_call.py` — one order, one thread, one key; its jobs followed by the pulse under a `remote_job` row).

**Ownership**: `memory/` (SQLite `zaelar.db`: vec + FTS5 + graph + forgetting) is the central memory; `bus/` is the in-process event bus; `server/` (FastAPI) is transport + composition root; `config/v2.py` owns model routing. Layers are independent — widgets never touch the voice core. Beside the brain sits a deterministic autonomic homeostasis layer (`nucleo/pulse/homeostasis.py`, no model) for machine health.

**The A2A network** (`docs/architecture/zaelar-a2a-network.md`, V2-866, planned): a third mesh surface — the agent of a
PERSON you know. A store-and-forward mailbox on the server (never a 24 h socket), discovery by mutual email/phone hash
through three triggers (daily · contact saved · the owner asks) where the automatic ones PROPOSE and only his yes sends,
a `contact` trust class (data, never an order), per-contact scopes as rules rows, and one observability row per step
carrying the relationship id `rel` on both machines. Code in `a2a/` only.

**The slow lane** (`context/slow-lane.md`, V2-811): a second model seat for background work that can wait — off by default, adopted call site by call site, the route decided once and stored, never per item.
