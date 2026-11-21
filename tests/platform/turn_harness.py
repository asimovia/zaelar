"""The isolated-turn harness — one turn in, one DECISION out, with every consequence door closed.

Born as the decision bank's harness (V2-776 A1); the bank itself was retired on 2026-11-05 (the three-layer test
model: unit · module benches · use cases), and what stays is this fixture, which ~35 unit tests use to run a REAL
turn in isolation: `Isolated` seeds the screen and the memory, `RecordedModel` fixes what the model would have said
and the verdicts Jev would have returned, and `run_case` asks the engine ONE question — given all that, what did
you DECIDE? The answer is a line of a small grammar (`DECISIONS`), deterministic by construction.

WHICH CHANNEL. The turn runs through `nucleo.cli.turn.run_turn` — the VOICE turn itself, typed and dry
(refactor2710-01): the real prompt, the real fast lanes, the real guards and the real decision seam, with every
consequence door closed (`nucleo/consequence.py`) so nothing spawns a worker or moves a card for real. There is no
second implementation of the turn any more, so a case green here is the microphone's turn deciding right.

ISOLATION. Everything the turn touches is redirected before the first import that would cache a path:
`ZAELAR_WORKSPACE`, `ZAELAR_DB`, the widget store's data dir, the observer's log dir, the language, and the
Jev switch (off — a verdict comes from the case or from nowhere). The operator's database, agenda and
credentials are never on the path. Usable from pytest and from the CLI runner alike, so it patches by hand
and restores in `finally`, which is what a disarm harness owes the product (2026-09-14, V2-669).
"""
from __future__ import annotations

import datetime as _dt
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENGINE = HERE.parents[1]
LANGS = ("es", "en")

# ── the grammar of a decision ─────────────────────────────────────────────────────────────────────────────
# One line per turn. `talk` is the model's own words and nothing else; `ask` is a clarifying question the
# ENGINE decided to ask (not a question the model happened to write); the rest name a mechanism and its target.
DECISIONS = re.compile(
    r"^(talk|ask|escalate|search|listings|close all|minimize|unfullscreen|fullscreen [a-z0-9_-]+"
    r"|show [a-z0-9_-]+|close [a-z0-9_-]+|read [a-z0-9_-]+|panel:[a-z_]+|controls:(?:mute|unmute|off)"
    r"|data-op [a-z0-9_-]+:[a-z_]+|music [a-z_]+|stop|settle)$")

# What `forbid` may name. Each one is a question the judge knows how to ask of an outcome.
FORBIDS = ("worker", "search", "show", "close", "data-op", "second-card", "model", "ask", "stop")

CASE_KEYS = {"id", "lang", "phrase", "source", "screen", "memory", "model", "brief", "expect", "also",
             "forbid", "open", "note", "file", "widgets", "history", "live_only", "accept", "focus", "connectors",
             "select", "close_scope", "errand"}

#: Connectors a case may declare enabled; every other one is OFF for that case.
CONNECTOR_IDS = ("whatsapp", "telegram", "email")


def validate(case: dict) -> None:
    unknown = set(case) - CASE_KEYS
    if unknown:
        raise ValueError(f"{case.get('id')}: unknown keys {sorted(unknown)}")
    for key in ("id", "lang", "phrase", "screen", "expect", "source"):
        if key not in case:
            raise ValueError(f"{case.get('id')}: missing {key!r}")
    if case["lang"] not in LANGS:
        raise ValueError(f"{case['id']}: lang must be one of {LANGS}")
    if not DECISIONS.match(case["expect"]):
        raise ValueError(f"{case['id']}: expect {case['expect']!r} is not in the decision grammar")
    for extra in (*case.get("also", ()), *case.get("accept", ())):
        if not DECISIONS.match(extra):
            raise ValueError(f"{case['id']}: also {extra!r} is not in the decision grammar")
    for f in case.get("forbid", ()):
        if f not in FORBIDS:
            raise ValueError(f"{case['id']}: forbid {f!r} is not one of {FORBIDS}")
    if not isinstance(case["screen"], dict) or set(case["screen"]) - {"open", "maximized"}:
        raise ValueError(f"{case['id']}: screen must be {{'open': [...], 'maximized'?: id}}")
    model = case.get("model")
    if model is not None:
        if set(model) - {"say", "tools"}:
            raise ValueError(f"{case['id']}: model must be {{say, tools}}")
        for t in model.get("tools", ()):
            if set(t) != {"name", "args"}:
                raise ValueError(f"{case['id']}: a recorded tool call is {{name, args}}")
    for key, verdict in (case.get("brief") or {}).items():
        if not (isinstance(verdict, list) and len(verdict) == 2 and isinstance(verdict[1], (int, float))):
            raise ValueError(f"{case['id']}: brief[{key!r}] must be [choice, confidence]")
    memory = case.get("memory") or {}
    if set(memory) - {"agenda", "state", "pills"}:
        raise ValueError(f"{case['id']}: memory fixtures are 'agenda', 'state' and 'pills'")
    if memory.get("pills") and not (isinstance(memory["pills"], list)
                                    and all(isinstance(p, str) and p.strip() for p in memory["pills"])):
        raise ValueError(f"{case['id']}: memory.pills is a list of the sentences the case takes as remembered")
    for turn in case.get("history") or ():
        if not (isinstance(turn, dict) and set(turn) == {"role", "text"} and turn["role"] in ("user", "assistant")):
            raise ValueError(f"{case['id']}: a history turn is {{role: user|assistant, text}}")
    widgets = case.get("widgets") or {}
    if not isinstance(widgets, dict) or any(not isinstance(v, dict) for v in widgets.values()):
        raise ValueError(f"{case['id']}: widgets is {{card id: its store document}}")
    errand = case.get("errand")
    if errand is not None and not (isinstance(errand, dict) and set(errand) == {"goal"} and str(errand["goal"]).strip()):
        raise ValueError(f"{case['id']}: errand is {{goal}} — the one errand running behind the turn")
    conns = case.get("connectors") or []
    if not isinstance(conns, list) or any(c not in CONNECTOR_IDS for c in conns):
        raise ValueError(f"{case['id']}: connectors is a list of {CONNECTOR_IDS}")


# ── the outcome and its judge ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Outcome:
    case_id: str
    decision: str = ""
    also: list[str] = field(default_factory=list)   # secondary mutations the turn also produced
    action: str = ""                                # the typed channel's action string
    tool_calls: list = field(default_factory=list)
    tags: list = field(default_factory=list)
    reply: str = ""
    model_consulted: bool = False
    cards_touched: set = field(default_factory=set)
    events: list = field(default_factory=list)
    error: str = ""
    ms: float = 0.0
    live: bool = False                              # the real model: «which lane answered» is not what is measured

    @property
    def all_decisions(self) -> list[str]:
        return [self.decision, *self.also]

    def failures(self, case: dict) -> list[str]:
        """Why this outcome does not satisfy the case. Empty means the case is green."""
        why: list[str] = []
        if self.error:
            why.append(f"turn failed: {self.error}")
        if self.decision != case["expect"] and self.decision not in case.get("accept", ()):
            why.append(f"decided {self.decision!r}, expected {case['expect']!r}")
        for extra in case.get("also", ()):
            if extra not in self.also:
                why.append(f"expected also {extra!r}, observed {self.also}")
        if case.get("model") is None and self.model_consulted and not self.live:
            why.append("the model was consulted for a turn a deterministic lane owns")
        for f in case.get("forbid", ()):
            hit = {
                "worker": "escalate" in self.all_decisions,
                "search": "search" in self.all_decisions,
                "show": any(d.startswith("show ") for d in self.all_decisions),
                "close": any(d.startswith("close") for d in self.all_decisions),
                "data-op": any(d.startswith("data-op ") for d in self.all_decisions),
                "second-card": len(self.cards_touched) > 1,
                "model": self.model_consulted,
                "ask": "ask" in self.all_decisions,
                "stop": any(d in ("stop", "settle") for d in self.all_decisions),   # the running errand ended at all
            }[f]
            if hit:
                why.append(f"forbidden {f!r} happened ({self.all_decisions})")
        return why

    def as_dict(self) -> dict:
        return {"id": self.case_id, "decision": self.decision, "also": self.also, "action": self.action,
                "tool_calls": self.tool_calls, "tags": self.tags, "reply": self.reply[:200],
                "model_consulted": self.model_consulted, "cards": sorted(self.cards_touched),
                "error": self.error, "ms": round(self.ms, 1)}


def _widget_data_target(tool_calls: list) -> tuple[str, str]:
    for t in tool_calls:
        if t.get("name") == "widget_data":
            a = t.get("args") or {}
            return str(a.get("widget_id") or "").strip().lower(), str(a.get("action") or "").strip()
    return "", ""


def decision_of(res: dict, tool_calls: list) -> str:
    """Map the typed channel's action vocabulary onto the bank's grammar. Unknown actions come back verbatim, so a
    new mechanism shows up as a red case with its own name rather than as a silent `talk`."""
    a = str(res.get("action") or "")
    if a == "chat":
        return "talk"
    if a == "clarify":
        return "ask"
    if a == "canvas:close":
        return "close all"
    if a == "canvas:minimize" or a.startswith("canvas:minimize:"):
        return "minimize"
    if a.startswith("canvas:unfullscreen"):
        return "unfullscreen"
    if a.startswith("canvas:fullscreen:"):
        return "fullscreen " + a.split(":", 2)[2]
    if a == "canvas:show:imagenes" and any(t.get("name") == "show_images" and (t.get("args") or {}).get("more")
                                           for t in tool_calls):
        return "data-op imagenes:add"                   # «more of those»: the image turn hands them to the viewer's `add`
    if a.startswith("canvas:show:"):
        return "show " + a.split(":", 2)[2]
    if a.startswith("canvas:close:"):
        return "close " + a.split(":", 2)[2]
    if a.startswith("widget_data:"):
        _, wid, act = a.split(":", 2)
        return f"data-op {wid}:{act}"
    if a == "widget_data":
        wid, act = _widget_data_target(tool_calls)
        return f"data-op {wid}:{act}"
    if a == "read_widget":
        wid = next((str((t.get("args") or {}).get("widget_id") or "") for t in tool_calls
                    if t.get("name") == "read_widget"), "")
        return f"read {wid.strip().lower()}"
    if a == "music":
        act = next((str((t.get("args") or {}).get("action") or "play") for t in tool_calls
                    if t.get("name") == "play_music"), "play")
        return f"music {act}"
    if a in ("escalate", "search", "listings"):
        return a
    if a.startswith(("panel:", "controls:")):
        return a
    return a


def _secondary(res: dict, tool_calls: list, primary: str) -> tuple[list[str], set[str]]:
    """Everything else the turn did: the canvas tags and the heavy tools, minus the primary decision."""
    also: list[str] = []
    cards: set[str] = set()
    for t in res.get("tags") or []:
        act = t.get("action")
        wid = str((t.get("extra") or {}).get("id") or "").strip().lower()
        if act == "show" and wid:
            also.append(f"show {wid}")
            cards.add(wid)
        elif act == "close":
            also.append(f"close {wid}" if wid else "close all")
            if wid:
                cards.add(wid)
    doors = [str((e or {}).get("door") or "") for e in res.get("consequences") or ()]
    for door, act in (("worker.settle", "settle"), ("worker.stop", "stop")):
        if door in doors:
            also.append(act)                            # a replace stops the errand AND escalates
    names = [t.get("name") for t in tool_calls]
    if "escalate_to_slowbrain" in names and str(res.get("action") or "") == "escalate":
        also.append("escalate")                         # only a worker the channel would launch (2026-10-15)
    if "web_search" in names:
        also.append("search")
    if primary.startswith(("show ", "close ", "data-op ", "read ")):
        target = primary.split(" ", 1)[1].split(":", 1)[0]
        cards.add(target)
    also = [d for d in dict.fromkeys(also) if d != primary]
    return also, cards


def close_pick_answer(picked, named: float = 0.75, scope: str = ""):
    """A stand-in for `jev.choose_many_sync` that answers only the close questions: «named» at `named` for the cards in
    `picked` (P strong+partial as live pass 4 measured it, margin 0.16), «not_named» for the rest; the bulk close's
    `close_scope` with `scope` at 0.75 when given; None otherwise."""
    def answer(state, questions, *, question_id: str = "", **_k):
        if question_id == "close_scope" and scope:
            other = "spare" if scope == "every_card" else "every_card"
            return {k: {"choice": scope, "confidence": 0.5, "probs": {scope: 0.75, other: 0.25}} for k in questions}
        if question_id != "close_pick":
            return None
        def one(q):
            p = named if any(f"«{w}" in q["instructions"] for w in picked) else 1.0 - named
            return {"choice": "named" if p >= 0.5 else "not_named", "confidence": 0.16,
                    "probs": {"named": p, "not_named": 1.0 - p}}
        return {k: one(q) for k, q in questions.items()}
    return answer


# ── the recorded model and the recorded brief ─────────────────────────────────────────────────────────────
class RecordedModel:
    """Stands in for `FastClient`: yields the recorded words, fires the recorded tool calls, and records
    that it was consulted at all. A case without a `model` block still gets an instance — one that says
    nothing — so a lane that should have skipped the model is caught by `model_consulted`, not by a crash."""
    consulted = False
    say: str = ""
    tools: list = []

    @classmethod
    def load(cls, model: dict | None) -> None:
        cls.consulted = False
        cls.say = str((model or {}).get("say") or "")
        cls.tools = list((model or {}).get("tools") or [])

    async def stream(self, messages, spec=None, tools=None, on_tool_call=None, metrics=None, **_kw):
        RecordedModel.consulted = True
        if RecordedModel.say:
            yield RecordedModel.say
        for t in RecordedModel.tools:
            if on_tool_call:
                on_tool_call(t["name"], dict(t.get("args") or {}))

    async def complete(self, messages, spec=None, *args, **_kw):
        # A second pass (act repair, widget read, card commission) asks the model again. The bank answers
        # NOTHING on purpose: what is measured is the decision the engine takes with what it already has.
        RecordedModel.consulted = True
        return ""

    def describe(self, spec=None) -> str:
        return "bank/recorded"


def brief_handle(case: dict):
    """A ready Jev brief with the case's verdicts, in the exact shape `nucleo.jev.peek/read` consume."""
    verdicts = case.get("brief")
    if not verdicts:
        return None
    ev = threading.Event()
    ev.set()
    result = {key: {"choice": choice, "confidence": float(conf), "probs": {choice: float(conf)}}
              for key, (choice, conf) in verdicts.items()}
    return {"event": ev, "result": result, "_call_id": f"bank:{case['id']}", "turn_id": case["id"], "judged": case["phrase"],
            "open_ids": [str(w) for w in case["screen"].get("open") or []]}


# ── isolation ─────────────────────────────────────────────────────────────────────────────────────────────
def _unbind_copies(name: str, fake, real) -> None:
    """A module first imported WHILE a patch was on bound the fake under its own name (`from … import FastClient`
    took `RecordedModel`), and restoring the patched attribute does not reach that copy — five tests went red only in
    wide runs, missing `_client_for`. Put the real object back wherever the fake is still bound under that name."""
    import sys
    if fake is None or fake is real:
        return
    for mod in list(sys.modules.values()):
        try:
            if getattr(mod, name, None) is fake:
                setattr(mod, name, real)
        except Exception:  # noqa: BLE001 — a module that refuses attribute access keeps what it has
            continue


_ENV_KEYS = ("ZAELAR_WORKSPACE", "ZAELAR_DB", "ZAELAR_JEV", "ZAELAR_EMBED_BACKEND", "MEMORY_RERANK",
             "ZAELAR_LANGUAGE_GATE", "ZAELAR_LANGUAGE", "ZAELAR_LOG_DIR", "ZAELAR_TEST_EMBED_CLOUD", "BROWSER_SEARCH")


def _forget_what_the_turns_did() -> None:
    """The process-level records a LIVE turn leaves for the next one («what we just did», `done_ops`): a case that runs
    with `execute=True` must not hand them to whatever test runs next (a later brief asked `corrects_last`)."""
    from nucleo import done_ops
    done_ops.reset()


def _await_the_turns_own_threads() -> bool:
    """The threads a turn starts AFTER it closes (the whisperer, off `turn.closed`, V2-889 F2) end inside the case's
    world: they read the keys and the database this case lent. Measured 2026-11-12 on the multi-turn bench: the last
    turn's whisper resolved its key after the case had given the operator's keys back, so DeepSeek answered 401 to a
    `local` sentinel — and its event would have landed in the install's database. Bounded by the whisperer's own clock:
    its two rungs and the brief it may wait for. True when they all ended."""
    try:
        from nucleo.whisper import run as whisper
    except Exception:  # noqa: BLE001 — no whisperer, nothing to wait for
        return True
    return whisper.wait(2 * whisper.DEFAULT_TIMEOUT_S + whisper.BRIEF_WAIT_S)


def _relative_day(spec: str) -> _dt.date:
    """`+1` = tomorrow, `+0` = today, or an ISO date — fixtures never carry a date that goes stale."""
    if spec.startswith(("+", "-")):
        return _dt.date.today() + _dt.timedelta(days=int(spec))
    return _dt.date.fromisoformat(spec)


# ── run ───────────────────────────────────────────────────────────────────────────────────────────────────
def _a_model_turn(event: dict) -> bool:
    """Live mode has no recorded model to ask, so «was the model consulted?» is read from the turn's perf row. The
    action-map lane writes that same row with an EMPTY system prompt (it answers without the model), so the row alone
    counted every action-map hit as a model turn and turned `forbid: model` red on exactly the turns it protects.
    A model turn is the row with a prompt behind it."""
    return str(event.get("label") or "").startswith("🧾 turno") and int(event.get("system_chars") or 0) > 0

