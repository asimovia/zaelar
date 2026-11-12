"""The INTRODUCTION pack — the only phase that exists today (V2-675).

The operator's words: *«una excepción al inicio en el que la conversación fuera guiada por el agente… ¿quién
eres? ¿cómo te llamas? ¿dónde vives? ¿qué podría hacer por ti?»*, *«tiene que conocerse a sí mismo y saber
quién es y sus capacidades»*, and the limit that shapes the whole block — *«tampoco hace falta que le diga qué
puede hacer y que se pase cuatro minutos hablando»*.

Measured before writing it (his own English session, 2026-09-11): the kickoff asked his name, he answered
around it, and the profile still held `operator_name: None` three sessions later. There was no phase — the
first turn had an instruction and the second turn had nothing, so the introduction depended entirely on
whether a single greeting happened to land.

**What this pack does NOT contain, and why.** It does not list the widgets: the resource layer
(`_flash_layer`) already puts the real, live catalog in the same prompt, and a second inventory written by
hand is how two lists end up disagreeing — the failure this codebase has paid for repeatedly (V2-594 named
it, V2-603 measured a prompt claiming less coverage than existed). What it names are the FAMILIES of what
the agent can do, which are architecture and do not go stale, and it points at the catalog for the rest.

**Closing it is the hard half.** The operator asked that the decision be ours and, when needed, a model's:
*«puede decidirlo un modelo de lenguaje con unas llamadas internas propias nuestras»*. So there are three
exits, cheapest first: a DETERMINISTIC one (we know his name — the one fact the introduction exists to
learn), a JUDGE (off the hot path, at most one call every `_JUDGE_EVERY` turns), and a CAP (an introduction
that never ends is a bug, not a long introduction). Whichever fires, the flag is written and the block is
gone for good — `settings.intro_done`, which lives on the AGENT side, so a factory reset correctly starts
the relationship over.
"""
from __future__ import annotations

import asyncio

from loguru import logger

FLAG = "intro_done"
#: A7 (2026-11-12) — the phase's second fact, persisted beside the first: he was told, once, that the agent's name
#: and voice are his to change. The phase does not close until both are true (his name known, this told).
OFFER_FLAG = "intro_offer_told"

# V2-737 — the public guide, verified live (2026-09-20: both answer 200). The agent may leave it in the
# chat, where a URL renders as a real link since V2-736 — before that it was text he had to copy by hand,
# which is why this line did not exist. Kept here rather than in the sentence so the day a path moves
# there is ONE place to change, and the test that checks they still answer has something to read.
from .introduction_block import _GUIDE_EXAMPLES_URL, _GUIDE_URL  # noqa: E402, F401 — the block's, read by its tests

_JUDGE_AFTER = 4        # turns before the judge is worth a call at all — nothing is settled before then
_JUDGE_EVERY = 4        # and then at most one call every N turns: this is off the hot path, not free
_MAX_TURNS = 30         # the cap. An introduction still running after this many turns is not introducing.

_turns = 0              # process-lived on purpose: a restart mid-introduction re-arms the cap, which is the
#                         safe direction — the cap is a backstop, and the other two exits are the real ones.
_judging = False
_tasks: list = []
#: A7 — the TRACE of the turn whose block carried the name-and-voice offer; that turn's close persists it (a compose
#: outside a turn — a prompt warmed ahead — carries no trace and settles nothing).
_offer_pending = ""
#: A7 — the memory agent writes his name ~2 s AFTER the turn closes (measured 2026-11-12, +2.1 s): a turn that ends
#: with the name still unknown is read again after this many seconds, so the phase closes on the turn he said it.
_RECHECK_S = 4.0


# ── is the phase running? ───────────────────────────────────────────────────────────────────────────────
def is_active() -> bool:
    """Cheap, local, and asked on EVERY turn. Two conditions, and the second is not redundant: while the
    language ceremony is still open nobody has spoken yet (V2-672), and an introduction block riding a
    prompt in a language the operator has not chosen is the exact failure that batch closed."""
    try:
        from config import settings
        if settings.get(FLAG):
            return False
        return bool(str(settings.get("stt_language") or "").strip())
    except Exception:  # noqa: BLE001
        return False        # unreadable settings → no phase. A missing block costs a plainer first
    #                         conversation; a block that cannot be turned off costs every turn forever.


def close(reason: str) -> None:
    """End the phase. Idempotent, and it says so out loud — a phase of the relationship ending is exactly
    the kind of thing that is impossible to reconstruct later if nobody wrote it down."""
    try:
        from config import settings
        if settings.get(FLAG):
            return
        settings.update({FLAG: True})
    except Exception as e:  # noqa: BLE001
        logger.warning(f"context_packs.introduction: could not persist {FLAG}: {e!r}")
        return
    logger.info(f"context_packs.introduction: phase CLOSED ({reason})")
    try:
        from voice.observer import emit
        emit("phase", "🎓 presentación terminada — su contexto se archiva", role="system",
             extra={"cat": "flash", "pack": "introduction", "reason": reason, "turns": _turns})
    except Exception:  # noqa: BLE001
        pass


# ── the block ───────────────────────────────────────────────────────────────────────────────────────────
def _known() -> dict:
    try:
        from memory import api as _mem
        return _mem.state() or {}
    except Exception:  # noqa: BLE001
        return {}


def _own_name() -> str:
    from .introduction_block import _own_name as _n
    return _n()


def offer_told() -> bool:
    try:
        from config import settings
        return bool(settings.get(OFFER_FLAG))
    except Exception as e:  # noqa: BLE001
        logger.debug(f"introduction: {OFFER_FLAG} unreadable ({e!r})")
        return False


def block(turn_text: str = "", asked: str | None = None) -> str:
    """The phase's instructions for THIS turn — composed in `introduction_block.py`, reading the turn (A7)."""
    from .introduction_block import block as _block
    return _block(turn_text, asked)


# ── closing it ──────────────────────────────────────────────────────────────────────────────────────────
def _deterministic_close() -> str:
    """The cheap exit, asked before any model. Knowing his name is the one fact the introduction exists to
    learn, and it is also the one the memory writes on its own — so in the common case this phase ends
    without a single extra call."""
    st = _known()
    if str(st.get("operator_name") or "").strip() and offer_told():
        return "his name is known and he was told how to change ours"
    return ""


_JUDGE_SYSTEM = (
    "You watch the FIRST conversation between a person and their new personal assistant, to decide whether "
    "the introduction phase is over. It is OVER when the two have actually met: the assistant knows who the "
    "person is (at least their name), and the person has been told what the assistant can do for them — or "
    "has made clear they are not interested in being introduced and just want to use it. It is NOT over if "
    "they have only exchanged greetings, or if the assistant has not yet said what it is for. "
    'Answer with ONE word: "yes" if the introduction is over, "no" if it is not. Nothing else.'
)


def _judge_sync(transcript: str) -> bool:
    from nucleo.memory_agent.processor import llm
    raw = llm.chat_sync("errand_scope", _JUDGE_SYSTEM, transcript,
                           max_tokens=6, temperature=0.0, timeout=20.0)
    return (raw or "").strip().lower().startswith(("yes", "sí", "si"))


def _recent(limit: int = 14) -> str:
    try:
        from memory import api as _mem
        win = _mem.recent_window(limit=limit) or []
    except Exception:  # noqa: BLE001
        return ""
    lines = []
    for m in win:
        who = "PERSON" if (m.get("role") == "user") else "ASSISTANT"
        txt = (m.get("content") or "").strip().replace("\n", " ")[:220]
        if txt:
            lines.append(f"{who}: {txt}")
    return "\n".join(lines[-limit:])


async def _maybe_close() -> None:
    """Off the hot path, one turn behind the conversation. Fail-open in the direction that keeps the phase
    RUNNING: a judge that cannot be reached leaves the introduction open, and the cap ends it eventually."""
    global _judging
    if _judging:
        return
    why = _deterministic_close()
    if why:
        close(why)
        return
    if _turns >= _MAX_TURNS:
        close(f"tope de {_MAX_TURNS} turnos")
        return
    if _turns < _JUDGE_AFTER or (_turns - _JUDGE_AFTER) % _JUDGE_EVERY:
        return
    transcript = _recent()
    if not transcript:
        return
    _judging = True
    try:
        done = await asyncio.to_thread(_judge_sync, transcript)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"context_packs.introduction: judge unreachable, phase stays open: {e!r}")
        done = False
    finally:
        _judging = False
    if done:
        close("el juez dice que ya os conocéis")


def _settle_offer(payload) -> None:
    """The turn whose block carried the offer closed with a reply: the offer is told, for good (A7)."""
    global _offer_pending
    if not _offer_pending or (payload or {}).get("trace") != _offer_pending:
        return
    _offer_pending = ""
    win = (payload or {}).get("window") if isinstance(payload, dict) else None
    reply = next((str(m.get("text") or "") for m in (win or [])[-1:] if (m or {}).get("role") == "assistant"), "")
    if _own_name().lower() not in reply.lower():   # A7 audit: our reply names us (the slot): necessary, not enough
        return
    try:
        from config import settings
        if not settings.get(OFFER_FLAG):
            settings.update({OFFER_FLAG: True})
            logger.info("context_packs.introduction: the name-and-voice offer has been told")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"context_packs.introduction: could not persist {OFFER_FLAG}: {e!r}")


async def _recheck() -> None:
    """One more DETERMINISTIC read after the memory agent has had time to write his name (A7) — never the judge, which
    the turn's own close already asked (it ran twice every `_JUDGE_EVERY` turns)."""
    await asyncio.sleep(_RECHECK_S)
    if is_active() and (why := _deterministic_close()):
        close(why)


async def _consume_turns(q) -> None:
    global _turns
    while True:
        try:
            payload = await q.get()
        except asyncio.CancelledError:
            return
        try:
            if not is_active():
                continue
            _turns += 1
            _settle_offer(payload)
            await _maybe_close()
            if is_active() and _RECHECK_S > 0:
                asyncio.get_event_loop().create_task(_recheck())
        except Exception as e:  # noqa: BLE001
            logger.warning(f"context_packs.introduction: {e!r}")


def start() -> None:
    """Watch `turn.completed` — the Susurro/actionmap pattern (zero coupling with the voice provider, and it
    covers BOTH channels for free, because `observer.turn_detail` is where a voice turn and a probe turn
    both close). Idempotent; never raises into the caller.

    ALWAYS subscribed (A7, 2026-11-12). It used to return when `is_active()` was false at boot — and at boot the
    language is not locked yet (the ceremony runs AFTER the brain starts, and so does every reset), so on the
    operator's first session the watcher never armed, the phase never closed, and its block rode every turn. The
    condition is read per turn, in `_consume_turns`, where it is true when it matters."""
    global _tasks
    if _tasks:
        return
    try:
        import bus
        loop = asyncio.get_event_loop()
        _tasks = [loop.create_task(_consume_turns(bus.subscribe("turn.completed")))]
        logger.info("context_packs.introduction: watching the turns — phase "
                    + ("OPEN" if is_active() else "not running yet (no language, or already over)"))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"context_packs.introduction: watcher not started (conversation unaffected): {e!r}")


async def stop() -> None:
    global _tasks
    for t in _tasks:
        t.cancel()
    for t in _tasks:
        try:
            await t
        except (asyncio.CancelledError, Exception):  # noqa: B014
            pass
    _tasks = []


def install() -> None:
    from . import Pack, register
    register(Pack(id="introduction", title="Presentación", order=10, active=is_active, block=block, wants_turn=True))
