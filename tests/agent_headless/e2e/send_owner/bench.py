"""The send, end to end, with the operator's own sentences: a real sandbox engine, real models, a WhatsApp double.

One isolated sandbox (`tests/platform/sandbox_engine`) whose WhatsApp is a loopback test double of the bridge
(`play_routing/wa_double.py`: it reads as connected, records every send, and nothing leaves the process). Invented
contacts are seeded — four people who share a first name, none with the surname he says. Each scenario is a list of
turns on the text channel (`POST /api/flash/say`, one session); after every turn the checks read what is TRUE, never
what the reply claims:

  · `sends` — what the double accepted since the scenario started (to whom, which text);
  · `owner` — the `send` events of the turn (`nucleo/send`): taken by the owner, not its own, opened, sent;
  · `draft` — the open draft as the owner's events last described it (who, text, what it asked);
  · `tasks` — the live task rows (a send never opens one).

Exit 0 when every check of every scenario holds; 1 otherwise; 2 when the sandbox did not boot.

    ./.venv/bin/python -m tests.agent_headless.e2e.send_owner.bench [--only S1,S3] [--out <dir>]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENGINE = HERE.parents[3]

#: Invented people (never a real contact): four share the first name he says, none carries the surname he says.
CONTACTS = [
    {"name": f"{first} {last}", "kind": "person", "phone": phone, "channels": [{"platform": "whatsapp", "handle": phone}],
     "preferred": "whatsapp"}
    for first, last, phone in (("Raquel", "Ortega", "+34600000101"), ("Raquel", "Prieto", "+34600000102"),
                               ("Raquel", "Vidal", "+34600000103"), ("Raquel", "Soler", "+34600000104"),
                               ("Tomeu", "Ferrer", "+34600000105"))
]
CHAT = {c["name"]: c["phone"].lstrip("+") + "@s.whatsapp.net" for c in CONTACTS}

#: Each turn: what he says, and what must be TRUE after it. Check keys:
#:   owner: "taken" (the owner answered it) · "not" (it was the conversation's) · "opened" (a draft was born)
#:          · "none" (no draft event at all)
#:   sends: how many messages the double accepted in the whole scenario so far
#:   to / has / lacks: the last accepted send's recipient, words it must carry, words it must not
#:   draft_has / draft_lacks: words the open draft's text must / must not carry
#:   reply_names: how many of the people sharing the first name the reply must name
#:   reply: "nonempty" — he was answered
SCENARIOS = [
    {"id": "S1", "what": "his script: a surname nobody carries, dictated in pieces, a phrase taken out, the people "
                         "listed, one chosen, confirmed — only what he kept is sent",
     "turns": [
         {"say": "Ahora quiero que le mandes un mensaje a Raquel Caro.", "owner": "opened", "sends": 0,
          "reply": "nonempty"},
         {"say": "Dile que la quiero mucho.", "owner": "taken", "sends": 0, "draft_has": ["quiero mucho"]},
         {"say": "que esté enamorado de mí.", "owner": "taken", "sends": 0, "draft_has": ["quiero mucho", "enamorad"]},
         {"say": "Quita esa última frase.", "owner": "taken", "sends": 0, "draft_has": ["quiero mucho"],
          "draft_lacks": ["enamorad"]},
         {"say": "Dime qué Raqueles tienes.", "owner": "taken", "sends": 0, "reply_names": 3},
         {"say": "A Raquel Ortega.", "owner": "taken", "sends": 0},
         {"say": "Sí, mándaselo.", "owner": "taken", "sends": 1, "to": "Raquel Ortega", "has": ["quiero mucho"],
          "lacks": ["enamorad"]},
     ]},
    {"id": "S2", "what": "interruptions while the message waits for his yes are answered at once and never swallowed",
     "turns": [
         {"say": "Mándale un mensaje a Tomeu Ferrer diciendo que llego tarde.", "owner": "opened", "sends": 0},
         {"say": "¿Por qué tardas tanto?", "owner": "not", "sends": 0, "reply": "nonempty"},
         {"say": "Deja de repetir lo que digo.", "owner": "not", "sends": 0, "reply": "nonempty"},
         {"say": "Vale, envíaselo.", "owner": "taken", "sends": 1, "to": "Tomeu Ferrer", "has": ["tarde"]},
     ]},
    {"id": "S3", "what": "«forget that message» with nothing open opens nothing",
     "turns": [
         {"say": "Estaba viendo la tele, olvida ese mensaje.", "owner": "none", "sends": 0, "tasks": 0,
          "reply": "nonempty"},
     ]},
    {"id": "S4", "what": "«forget that message» with a message open drops it; nothing leaves",
     "turns": [
         {"say": "Escríbele a Tomeu Ferrer que mañana no puedo.", "owner": "opened", "sends": 0, "draft_has": ["mañana"]},
         {"say": "Olvida ese mensaje.", "owner": "taken", "sends": 0},
         {"say": "Sí.", "sends": 0},
     ]},
]


class Timeline:
    def __init__(self, path: Path):
        self.path = path

    def mark(self) -> int:
        return self.path.stat().st_size if self.path.exists() else 0

    def since(self, mark: int) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        with self.path.open("rb") as f:
            f.seek(mark if self.path.stat().st_size >= mark else 0)
            for line in f:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
        return out


def _reply(res) -> str:
    r = (res or {}).get("reply") if isinstance(res, dict) else res
    return " ".join(str(x) for x in r) if isinstance(r, list) else str(r or "")


def _fold(s: str) -> str:
    import unicodedata
    return "".join(ch for ch in unicodedata.normalize("NFD", str(s or "").lower()) if unicodedata.category(ch) != "Mn")


def judge(turn: dict, *, evs: list[dict], reply: str, sends: list[dict], draft: dict, tasks: int) -> list[str]:
    """The failed checks of one turn (pure: what the engine did, read from its events and the double)."""
    fails = []
    steps = [str(e.get("step") or "") for e in evs if e.get("kind") == "send"]
    want = turn.get("owner")
    if want == "taken" and "taken" not in steps:
        fails.append(f"the owner did not take it (steps {steps})")
    if want == "not" and ("taken" in steps or "not mine" not in steps):
        fails.append(f"expected the conversation's, steps {steps}")
    if want == "opened" and "opened" not in steps:
        fails.append(f"no draft was opened (steps {steps})")
    if want == "none" and set(steps) & {"opened", "taken", "queued", "sent"}:
        fails.append(f"a draft was opened or acted on: {steps}")
    if "sends" in turn and len(sends) != turn["sends"]:
        fails.append(f"{len(sends)} message(s) left (want {turn['sends']}): {[s.get('text') for s in sends]}")
    if sends and turn.get("to") and sends[-1].get("chatId") != CHAT[turn["to"]]:
        fails.append(f"sent to {sends[-1].get('chatId')} (want {turn['to']})")
    if sends:
        text = _fold(sends[-1].get("text"))
        fails += [f"the sent text lacks «{w}»: {sends[-1].get('text')!r}" for w in turn.get("has") or () if _fold(w) not in text]
        fails += [f"the sent text carries «{w}»: {sends[-1].get('text')!r}" for w in turn.get("lacks") or () if _fold(w) in text]
    dtext = _fold(draft.get("text"))
    fails += [f"the draft lacks «{w}»: {draft.get('text')!r}" for w in turn.get("draft_has") or () if _fold(w) not in dtext]
    fails += [f"the draft carries «{w}»: {draft.get('text')!r}" for w in turn.get("draft_lacks") or () if _fold(w) in dtext]
    if turn.get("reply_names"):
        n = sum(1 for c in CONTACTS if c["name"].startswith("Raquel") and _fold(c["name"].split()[1]) in _fold(reply))
        if n < turn["reply_names"]:
            fails.append(f"the reply names {n} of the four (want ≥{turn['reply_names']}): {reply!r}")
    if turn.get("reply") == "nonempty" and not reply.strip():
        fails.append("he was not answered")
    if "tasks" in turn and tasks != turn["tasks"]:
        fails.append(f"{tasks} live task row(s) (want {turn['tasks']})")
    return fails


def _live_tasks(eng) -> int:
    _c, body = eng.get("/api/tasks?scope=live&all=1")
    rows = (body or {}).get("tasks") or [] if isinstance(body, dict) else []
    return sum(1 for t in rows if str(t.get("state") or "") not in ("done", "failed", "cancelled", "unverified"))


def run(eng, tl: Timeline, sc: dict, double) -> dict:
    session = f"so-{sc['id']}-{int(time.time())}"
    n0, rows, draft = len(double.sent), [], {}
    for turn in sc["turns"]:
        mark, t0 = tl.mark(), time.time()
        _code, res = eng.post("/api/flash/say", {"text": turn["say"], "session": session, "execute": True}, timeout=150)
        time.sleep(4.0 if turn.get("sends") else 1.5)             # a queued order reaches the double, its echo returns
        evs = tl.since(mark)
        for e in evs:
            if e.get("kind") == "send" and isinstance(e.get("draft"), dict):
                draft = e["draft"]
        sends = double.sends_since(n0)
        reply = _reply(res)
        fails = judge(turn, evs=evs, reply=reply, sends=sends, draft=draft, tasks=_live_tasks(eng))
        rows.append({"say": turn["say"], "reply": reply, "secs": round(time.time() - t0, 1),
                     "steps": [e.get("step") for e in evs if e.get("kind") == "send"], "draft": draft,
                     "fails": fails})
        print(f"  {'✓' if not fails else '✗'} «{turn['say']}» → {reply[:110]!r} {rows[-1]['steps']}"
              + (f"\n      {fails}" if fails else ""), flush=True)
    eng.post("/reset/hard", {}, timeout=60)
    return {"id": sc["id"], "what": sc["what"], "turns": rows, "pass": all(not r["fails"] for r in rows)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--out", default="")
    args = ap.parse_args(argv)
    sys.path.insert(0, str(ENGINE))
    os.environ.setdefault("ZAELAR_TEST_ACTOR", "send-owner-bench")
    import tests.platform.sandbox_engine as se
    from tests.platform.voice_sandbox import seed_language
    from tests.use_cases.lab.stage import _brain_env_from_table
    from tests.agent_headless.e2e.play_routing import wa_double
    only = {s.strip() for s in args.only.split(",") if s.strip()}
    scenarios = [s for s in SCENARIOS if not only or s["id"] in only]
    run_dir = Path(args.out).resolve() if args.out else ENGINE / "tests" / "runs" / f"send-owner-{time.strftime('%Y%m%d-%H%M%S')}"
    ws = run_dir / "ws"
    (ws / "config").mkdir(parents=True, exist_ok=True)
    seed_language(ws, "es")
    double = wa_double.Double(se.free_port()).start()
    wa_env = wa_double.env_for(double, ws)
    (ws / "config" / "connectors.json").write_text(json.dumps({"whatsapp": {"enabled": True}}))
    eng, results = None, []
    try:
        try:
            eng = se.spawn_engine(workspace=ws, port=se.free_port(), log_path=ws / "engine.log", boot_timeout=240,
                                  extra_env={"MEMORY_RERANK": "off", **_brain_env_from_table(), **wa_env})
        except Exception as e:  # noqa: BLE001
            print(f"sandbox did not boot: {e!r}", flush=True)
            return 2
        print("READY", eng.base_url, flush=True)
        from tests.waiting import until_sync

        def _wa() -> dict:
            _, conns = eng.get("/api/connectors")
            return next((c for c in (conns or {}).get("connectors") or [] if c.get("id") == "whatsapp"), {})
        until_sync(lambda: _wa().get("connected") is True, "WhatsApp connected through the double", timeout_s=60, poll_s=1.0)
        wa_double.assert_isolated(wa_env, ws, double)
        for c in CONTACTS:
            eng.post("/widgets/contactos/action", {"action": "add_contact", "payload": c})
        tl = Timeline(ws / "logs" / "timeline-latest.jsonl")
        for sc in scenarios:
            print(f"{sc['id']} — {sc['what']}", flush=True)
            results.append(run(eng, tl, sc, double))
    finally:
        if eng is not None:
            se.stop_engine(eng)
        double.stop()
    ok = sum(r["pass"] for r in results)
    (run_dir / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{ok}/{len(results)} scenarios pass · {run_dir}/results.json", flush=True)
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
