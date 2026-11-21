"""nucleo/ — cerebro propio de zaelar v2 «Colmena» (EPIC-v2-colmena).

It replaces `brains/` (Hermes retirement, V2-009). For now this package is the brain's **SKELETON**:
docstrings and signatures that define the contract. Nothing is wired to voice yet (`BRAIN=duo`/`hermes`
remains the default until V2-009). The pieces are filled in during V2-004→V2-007.

Dos velocidades:

- **The conversation & turn manager** (`conversation/`, hosted by `nucleo/conversation_host/`) — the only path for
  voice and text (INI-078). The typed line enters through `nucleo/cli/turn.py`; the voice runs in its own process and
  hands his words to the body. Its mouth is `conversation_host/mouth.py`/`voice_mouth.py`; its acts are
  `conversation_host/acts*.py`.

- **SlowBrain** (`nucleo/dispatch.py` + `nucleo/memory_agent.py` + `nucleo/agentes/`) — **async** deliberation:
  a constellation of **Claude Code** agents behind `CodeAgent` (replaceable by Codex; model per invocation).
  Dispatcher + MEMORY agent ★ (composes the minimum context from `memory/`) + work agents (web/code/other).
  The result returns through the usual rails: `voice/proactive` behind `nucleo/pulse/notices` (the notes mailbox went in V2-851 F5).

- **Orchestrator loop** (`nucleo/pulse/loop.py`, ~1 Hz) — the thread of time: scheduled tasks (built-in cron),
  🔥 sparks (spontaneous thought), memory consolidation ("sleep"), and voice+UI reporting.

Substratos compartidos (NO son parte del cerebro): la **memoria** (`memory/`, V2-002/003) y el **Sistema
Nervioso** (`bus/`, V2-001, ya construido).
"""

__all__ = ["flash", "agentes"]
