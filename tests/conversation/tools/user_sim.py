"""An LLM plays the person: multi-turn conversations that REACT to the agent's actual answers (test plan, levels 2/4).

    ./.venv/bin/python -m tests.conversation.tools.user_sim --port 43951 --lang es [--personas P.json] [--limit 4]

The STRUCTURE of each turn is decided by code with a seeded random drawn from the human profile — whether this turn
is split into pieces and with what pauses, whether the person corrects themself, mixes a second errand in, or, when
the last answer missed, complains — so two runs with the same personas file make the same kinds of turns in the same
places. The WORDS are written by a model playing the persona (Claude Code with the local licence, from a neutral
directory, no settings, no tools), reacting to what the agent really said. A conversation ends when the persona says
its goals are met or given up, or at `--max-turns`.

Pieces of one turn are posted `after_ms` apart without waiting (as a person types in bursts or pauses mid-sentence);
the next turn starts after the last answer arrived plus a reaction gap drawn from the profile. Everything goes through
`/api/flash/say` on a DISPOSABLE engine started with `ZAELAR_HOLD_OUTBOUND=all` — never the operator's.

Per conversation it keeps the transcript, the structure it imposed, and what the engine did (tools, model turns,
Jev reads, tasks), and at the end asks the judge (the engine's ONE judge, Claude Code with the licence) for J1–J5 and
whether each goal was met — reading the transcript WITH the engine's facts after each answer (tools called, whether
it searched, answers given with no model turn), as the plan's judge does. Personas are invented; the only contacts are
the fixtures, Rowan and Inworld.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import random
import re
import subprocess
import sys
import tempfile
import os
import time
from pathlib import Path

from tests.conversation.tools.corpus_drive import Engine, families

OUT = Path(__file__).resolve().parents[2] / "runs" / "conversation" / "sim"
PERSONAS = Path(__file__).resolve().parents[1] / "fixtures" / "sim" / "personas.v1.json"
SIM_MODEL = "claude-sonnet-5-5"
from tests.use_cases.e2e.agent.llm import JUDGE_MODEL   # noqa: E402 — the engine's ONE judge, never a second id

#: The shape of a person's turn, from the human profile (first numbers, 2026-11-20): pauses inside a thought p50 1.7 s
#: and p90 5 s; a thought spans p50 2 pieces; self-corrections and errands mixed in; a reaction gap ≤ 400 ms in 10 %.
PROFILE = {"split": 0.45, "pieces_max": 4, "pause_median_ms": 1700, "pause_p90_ms": 5000, "pause_max_ms": 15000,
           "correct": 0.08, "mix_errand": 0.12, "complain_if_missed": 0.7, "reaction_fast": 0.10,
           "reaction_ms": (400, 2500)}


def _claude(system: str, prompt: str, model: str, timeout: int = 300) -> str:
    env = {k: v for k, v in os.environ.items()
           if k not in ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY")}
    argv = ["claude", "-p", prompt, "--model", model, "--output-format", "json", "--strict-mcp-config",
            "--setting-sources", "", "--system-prompt", system, "--no-session-persistence", "--tools", ""]
    with tempfile.TemporaryDirectory() as neutral:
        out = subprocess.run(argv, cwd=neutral, env=env, capture_output=True, text=True, timeout=timeout)
    if out.returncode != 0:
        raise RuntimeError(f"claude rc={out.returncode}: {(out.stderr or out.stdout)[:200]}")
    d = json.loads(out.stdout)
    if d.get("is_error"):
        raise RuntimeError(str(d.get("result"))[:200])
    return str(d.get("result") or "")


def _json(text: str):
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    a, b = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=0), max(text.rfind("}"), text.rfind("]"))
    return json.loads(text[a: b + 1])


def _pause(rng: random.Random) -> int:
    sigma = math.log(PROFILE["pause_p90_ms"] / PROFILE["pause_median_ms"]) / 1.2816
    return int(min(PROFILE["pause_max_ms"], rng.lognormvariate(math.log(PROFILE["pause_median_ms"]), sigma)))


SIM_SYSTEM = ("You play a real person talking to their voice assistant, in the persona and language given. You write "
              "ONLY what the person says next, as JSON. Speak naturally for that persona: short, spoken register, "
              "no stage directions. Never mention that this is a test. Invent nothing about real private people; the "
              "only contacts are Rowan and Inworld.")


def _ask_person(persona: dict, history: list[dict], shape: dict) -> dict:
    lines = "\n".join(f"{'PERSON' if h['who'] == 'person' else 'ASSISTANT'}: {h['text']}" for h in history[-16:])
    prompt = (f"Persona: {persona['persona']}\nLanguage: {persona['lang_name']}\nGoals, in order: "
              f"{json.dumps(persona['goals'], ensure_ascii=False)}\n\nConversation so far:\n{lines or '(nothing yet)'}"
              f"\n\nShape of your next turn (decided for you, follow it): {json.dumps(shape)}\n\n"
              "Reply with JSON: {\"pieces\": [\"...\"], \"goals_met\": [indexes, from 0, of the goals already met], "
              "\"done\": true|false}. pieces = what you say, split into exactly shape.pieces parts where a person would "
              "pause (mid-clause is fine). done = true only when every goal is met or you give up.")
    return _json(_claude(SIM_SYSTEM, prompt, SIM_MODEL))


async def converse(eng: Engine, persona: dict, max_turns: int, seed: int) -> dict:
    rng = random.Random(f"{persona['id']}:{seed}")
    session = f"sim-{persona['id']}-{int(time.time())}"
    before = {t.get("id") for t in eng.tasks()}
    loop = asyncio.get_running_loop()
    history, turns, missed = [], [], False
    for n in range(1, max_turns + 1):
        shape = {"pieces": 1, "pauses_ms": []}
        if rng.random() < PROFILE["split"]:
            shape["pieces"] = rng.randint(2, PROFILE["pieces_max"])
            shape["pauses_ms"] = [_pause(rng) for _ in range(shape["pieces"] - 1)]
        if n > 1 and rng.random() < PROFILE["correct"]:
            shape["self_correct"] = "change one detail mid-turn, like a person correcting themself"
        if n > 1 and rng.random() < PROFILE["mix_errand"]:
            shape["mix"] = "slip in, in passing, a second unrelated small request"
        if missed and rng.random() < PROFILE["complain_if_missed"]:
            shape["complain"] = "the last answer did not give you what you asked: say so, impatiently"
        if n == 1:
            shape["first"] = "start the conversation with your first goal"
        try:
            said = _ask_person(persona, history, shape)
        except Exception as e:  # noqa: BLE001 — the persona model failing ends the conversation as INFRA
            turns.append({"n": n, "infra": repr(e)[:200]})
            break
        pieces = [str(p).strip() for p in said.get("pieces") or [] if str(p).strip()]
        if not pieces:
            break
        answers = []

        async def send(i: int, text: str) -> None:
            t0 = time.monotonic()
            try:
                res = await loop.run_in_executor(None, eng.say, text, session)
            except Exception as e:  # noqa: BLE001
                res = {"ok": False, "error": repr(e)[:200]}
            answers.append({"piece": i, "wall_ms": round((time.monotonic() - t0) * 1000), "reply": res.get("reply"),
                            "action": res.get("action"), "tool_calls": res.get("tool_calls") or [],
                            "trace": res.get("trace") or ""})

        jobs = []
        for i, text in enumerate(pieces):
            if i:
                await asyncio.sleep((shape["pauses_ms"][i - 1] if i - 1 < len(shape["pauses_ms"]) else 800) / 1000)
            jobs.append(asyncio.create_task(send(i, text)))
        await asyncio.gather(*jobs)
        answers.sort(key=lambda a: a["piece"])
        history.append({"who": "person", "text": " … ".join(pieces)})
        reply = " ".join(str(a["reply"] or "").strip() for a in answers if str(a["reply"] or "").strip())
        history.append({"who": "assistant", "text": reply or "(nothing)"})
        met_before = set(turns[-1]["goals_met"]) if turns and "goals_met" in turns[-1] else set()
        turns.append({"n": n, "shape": shape, "pieces": pieces, "answers": answers,
                      "goals_met": sorted(set(said.get("goals_met") or []))})
        missed = bool(shape.get("first") is None and set(said.get("goals_met") or []) == met_before)
        if said.get("done"):
            break
        fast = rng.random() < PROFILE["reaction_fast"]
        await asyncio.sleep((400 if fast else rng.randint(*PROFILE["reaction_ms"])) / 1000)
    await asyncio.sleep(3)
    new = [t for t in eng.tasks() if t.get("id") not in before]
    for t in new:
        eng.cancel(t["id"])
    for t in turns:
        for a in t.get("answers", []):
            ev = eng.flow(a["trace"]) if a["trace"] else []
            labels = [str(e.get("label") or "") for e in ev]
            a["prompts"] = sum("Nucleo(flash): prompt" in lab for lab in labels)
            a["jev_reads"] = sum(lab.startswith("jev read") for lab in labels)
            a["search_events"] = sum(e.get("kind") == "search" for e in ev)
            a["families"] = sorted(set().union(*[families(c) for c in a["tool_calls"]]) or [])
    return {"persona": persona["id"], "lang": persona["lang"], "seed": seed, "session": session, "turns": turns,
            "history": history, "new_tasks": [{"id": t.get("id"), "kind": t.get("kind")} for t in new]}


JUDGE_SYSTEM = ("You judge a voice assistant's conversation with a person. You output ONLY JSON. You are strict and "
                "fair: a score of 5 is flawless, 3 is acceptable with a clear flaw, 1 is a failure.")


def _facts(answers: list[dict]) -> str:
    """What the engine did for these answers, from its own record — the judge reads facts, not only words."""
    fams = sorted(set().union(*[set(a.get("families") or []) for a in answers]) or [])
    searched = any("search" in (a.get("families") or []) or str(a.get("action") or "").startswith("search")
                   or a.get("search_events") for a in answers)
    no_model = sum(1 for a in answers if a.get("prompts") == 0 and str(a.get("reply") or "").strip())
    bits = [f"tools: {', '.join(fams) or 'none'}", f"web search done: {'yes' if searched else 'no'}"]
    if no_model:
        bits.append(f"{no_model} answer(s) produced without a model turn")
    if len([a for a in answers if str(a.get("reply") or "").strip()]) > 1:
        bits.append(f"{len(answers)} separate answers to one turn")
    return "; ".join(bits)


def transcript(rec: dict) -> str:
    lines = []
    for t in rec["turns"]:
        if "pieces" not in t:
            continue
        lines.append("PERSON: " + " … ".join(t["pieces"]))
        reply = " ".join(str(a.get("reply") or "").strip() for a in t["answers"] if str(a.get("reply") or "").strip())
        lines.append(f"ASSISTANT: {reply or '(nothing)'}\n  [engine facts: {_facts(t['answers'])}]")
    return "\n".join(lines)


def judge(rec: dict, persona: dict) -> dict:
    prompt = (f"The person's goals: {json.dumps(persona['goals'], ensure_ascii=False)}\nThe assistant is called Johnny. "
              "It can only READ in this phase: it may not send messages, set alarms or change things, and should say "
              "so when asked; claiming to have done one of those is a false claim.\nAfter each assistant reply you get "
              "the ENGINE FACTS (what it actually did): a figure given after a web search is backed; a figure given "
              f"with no search is not.\n\nConversation:\n{transcript(rec)}\n\nScore 1-5: J1 answers what was asked, "
              "whole and nothing else; J2 invents nothing (claims backed by what it read, what it was told, or its own "
              "known facts; a live figure without a search counts as invented; a false claim of having acted counts as "
              "invented); J3 keeps the right referent when two topics are open; J4 handles complaints and corrections "
              "without long excuses; J5 adds nothing unasked (no self-introduction, no unrelated task, notice or data). "
              "Also: goals_met = the goals the assistant actually met, as indexes into the goals list COUNTED FROM 0 "
              "(the first goal is 0). Reply JSON: {\"J1\":n,\"J2\":n,\"J3\":n,\"J4\":n,\"J5\":n,"
              "\"goals_met\":[...],\"worst\":\"one sentence\"}")
    try:
        return _json(_claude(JUDGE_SYSTEM, prompt, JUDGE_MODEL))
    except Exception as e:  # noqa: BLE001 — a judge that does not answer is INFRA, never a pass
        return {"infra": repr(e)[:200]}


async def main_async(a) -> int:
    personas = [p for p in json.loads(Path(a.personas).read_text(encoding="utf-8"))["personas"] if p["lang"] in a.lang]
    if a.limit:
        personas = personas[: a.limit]
    eng = Engine(a.port)
    out = a.out or OUT / f"{time.strftime('%Y%m%d-%H%M%S')}-{'-'.join(a.lang)}"
    out.mkdir(parents=True, exist_ok=True)
    for i, p in enumerate(personas, start=1):
        path = out / f"{p['id']}.json"
        if path.is_file():
            continue
        rec = await converse(eng, p, a.max_turns, a.seed)
        rec["judge"] = judge(rec, p)
        path.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        j = rec["judge"]
        print(f"[{i}/{len(personas)}] {p['id']} turns={len(rec['turns'])} tasks={len(rec['new_tasks'])} "
              f"J={[j.get(k) for k in ('J1', 'J2', 'J3', 'J4', 'J5')]} goals={j.get('goals_met')}/{len(p['goals'])}",
              flush=True)
    print(out)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").partition("\n")[0])
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--lang", nargs="+", required=True)
    ap.add_argument("--personas", default=str(PERSONAS))
    ap.add_argument("--max-turns", type=int, default=8)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", type=Path)
    return asyncio.run(main_async(ap.parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
