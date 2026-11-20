"""Drive the frozen corpus through an engine's text channel and judge it by rules — the «before» (old path) and, once
the switch exists, the «after» (test plan §7).

    ./.venv/bin/python -m tests.conversation.tools.corpus_drive --port 43951 --lang es --version v1 [--classes U22]
        [--seed] [--limit 2] [--out DIR]

One conversation at a time, each in its own session, on a disposable engine started with `ZAELAR_HOLD_OUTBOUND=all`
(never the operator's). The schedule comes from the corpus and is the same on both paths: the pieces of a thought
are posted `after_ms` apart WITHOUT waiting for an answer, as a person types in bursts; the first piece of the next
thought goes `after_ms` after the last answer to the previous one arrived, as a person who heard it.

What is read per thought, from the channel's answer and the engine's own flow (`/api/observability/flow/<trace>`):
the answers, the tools called (mapped to the corpus's FAMILIES), whether the model wrote any of them, Jev reads, the
wall latency, and the tasks the conversation left (each one recorded, then cancelled so no worker runs on).

Rules that the old path can be held to (plan §2.1), per thought:
  R4   one answer per thought (a thought sent in pieces answered piece by piece fails)
  R6   no act: no messaging or screen act called, no new task row
  R7   where the class expects a search, a search happened (a call or a search event); never a family the class
       forbids (`corpus.reading`: an act expects no tool — R6 judges it). Agenda, contacts, memory and about_self
       ride inside the old path's prompt with no call to see: reported as unmeasured, never failed
  R15  the answer is in the conversation's language (es/en; mixed conversations are not judged)
  R19  every answer comes from a turn of the model (an answer with no prompt in its flow was given by something else)
`--seed` puts the fixtures every class assumes in place first: the contacts Rowan and Inworld, three appointments.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from tests.conversation.tools.corpus import ROOT as CORPUS, reading

OUT = Path(__file__).resolve().parents[2] / "runs" / "conversation" / "drive"

_ES = set("el la los las de que y en un una por para con no se lo es al del me te le mi tu su qué cómo cuánto cuántos "
          "cuál está están hoy tiene hay sí muy más pero también ya".split())
_EN = set("the a an of and to in is are it you for on with that this what how many much it's i'm your my there "
          "today yes not but also".split())


#: The families R7 can see on any path: a search leaves a call or a search event. Agenda, contacts, memory and the
#: agent's own catalogue travel INSIDE the old path's prompt (the widgets' state, the automatic recall, the self
#: catalogue) with no call to see, so there R7 is reported as unmeasured rather than failed.
MEASURABLE = frozenset({"search"})
#: Cards whose data is live (prices, weather): reading one is a read of fresh data, counted as `search`.
LIVE_DATA_WIDGETS = ("markets", "weather", "tiempo")


def lang_of(text: str) -> str:
    words = re.findall(r"[a-záéíóúñü']+", str(text).lower())
    es, en = sum(w in _ES for w in words), sum(w in _EN for w in words)
    return "es" if es > en else "en" if en > es else "?"


def families(call: dict) -> set[str]:
    """An old-path tool call → the corpus's families. Acts are named apart (`messaging`, `screen`) so R6 can see them."""
    name = str(call.get("name") or "")
    args = call.get("args") or {}
    wid, act = str(args.get("widget_id") or args.get("widget") or ""), str(args.get("action") or "")
    if name in ("web_search", "search", "search_web", "news", "market_data") or name.startswith("search"):
        return {"search"}
    if name in ("about_self",):
        return {"about_self"}
    if name in ("recall", "memory_search", "remember", "memory") or name.startswith("memory"):
        return {"memory"}
    if name in ("widget_data", "read_widget", "widget_action"):
        if wid in ("mensajeria",):
            return {"messaging"}
        if wid in LIVE_DATA_WIDGETS:
            return {"search"}                         # a live-data card read is a read of fresh data, as a search is
        if wid in ("agenda", "calendario", "calendar"):
            return {"agenda"}
        if wid in ("contactos", "contacts"):
            return {"contacts"}
        return {f"widget:{wid}:{act}"}
    if name.startswith(("canvas", "close", "hide")) or name in ("screen", "clear_screen"):
        return {"screen"}
    return {name}


def _acts(calls: list[dict], action: str) -> bool:
    """Did this answer try to ACT outside reading — a message drafted or sent, the screen closed?"""
    for c in calls:
        args = c.get("args") or {}
        if (args.get("widget_id") == "mensajeria" and str(args.get("action")) not in ("read", "list", "search", "")):
            return True
        if str(c.get("name") or "").startswith(("close", "hide")):
            return True
    return bool(re.match(r"(widget_data:mensajeria:(draft|send|send_to|compose)|canvas:(close|hide|clear))", action or ""))


class Engine:
    def __init__(self, port: int) -> None:
        self.base = f"http://127.0.0.1:{port}"

    def _req(self, method: str, path: str, body: dict | None = None, timeout: float = 240) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data, {"content-type": "application/json"}, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as fh:
            return json.load(fh)

    def say(self, text: str, session: str) -> dict:
        return self._req("POST", "/api/flash/say", {"text": text, "session": session, "execute": True,
                                                    "ingest": False})

    def tasks(self) -> list[dict]:
        return self._req("GET", "/api/tasks?scope=all", timeout=30).get("tasks") or []

    def cancel(self, task_id: str) -> None:
        try:
            self._req("POST", f"/api/tasks/{urllib.parse.quote(task_id, safe='')}/cancel", {}, timeout=30)
        except Exception:  # noqa: BLE001 — a task that already ended cannot be cancelled; it is recorded anyway
            pass

    def flow(self, trace: str) -> list[dict]:
        try:
            return self._req("GET", "/api/observability/flow/" + urllib.parse.quote(trace, safe=""), timeout=30)["events"]
        except Exception:  # noqa: BLE001
            return []

    def seed(self, lang: str) -> list:
        today = dt.date.today()
        nxt = lambda wd: (today + dt.timedelta(days=(wd - today.weekday()) % 7 or 7)).isoformat()   # noqa: E731
        es = lang == "es"
        out = []
        for name, kind, email in (("Rowan", "person", "rowan@example.com"), ("Inworld", "company", "hello@example.com")):
            out.append(self._req("POST", "/widgets/contactos/action", {"action": "add_contact", "payload": {
                "name": name, "kind": kind, "email": email}}))
        for title, wd, start, end in ((("Dentista", "Dentist")[not es], 3, "16:00", "16:45"),
                                      (("Reunión de equipo", "Team meeting")[not es], 1, "10:00", "11:00"),
                                      (("Cena con Rowan", "Dinner with Rowan")[not es], 4, "21:00", "23:00")):
            out.append(self._req("POST", "/widgets/agenda/action", {"action": "add_meeting", "payload": {
                "title": title, "date": nxt(wd), "startTime": start, "endTime": end}}))
        return out


async def drive_conversation(eng: Engine, conv: dict) -> dict:
    session = f"corpus-{conv['id']}-{int(time.time())}"
    before = {t.get("id") for t in eng.tasks()}
    loop = asyncio.get_running_loop()
    rows = []
    last_answer_at = None
    for turn in conv["turns"]:
        answers = []

        async def send(i: int, text: str) -> None:
            t0 = time.monotonic()
            try:
                res = await loop.run_in_executor(None, eng.say, text, session)
            except Exception as e:  # noqa: BLE001
                res = {"ok": False, "error": repr(e)[:200]}
            answers.append({"piece": i, "sent_at": t0, "wall_ms": round((time.monotonic() - t0) * 1000),
                            "ok": res.get("ok"), "error": res.get("error"), "reply": res.get("reply"),
                            "action": res.get("action"), "tool_calls": res.get("tool_calls") or [],
                            "trace": res.get("trace") or "", "answered_at": time.monotonic()})

        jobs = []
        for i, piece in enumerate(turn["pieces"]):
            wait = piece["after_ms"] / 1000
            if i == 0 and last_answer_at is not None:
                wait = max(0.0, last_answer_at + wait - time.monotonic())
            await asyncio.sleep(wait)
            jobs.append(asyncio.create_task(send(i, piece["text"])))
        await asyncio.gather(*jobs)
        last_answer_at = max(a["answered_at"] for a in answers)
        rows.append({"turn": turn, "answers": sorted(answers, key=lambda a: a["piece"])})
    await asyncio.sleep(3)                                              # the turn's tail lands before reading flows
    new = [t for t in eng.tasks() if t.get("id") not in before]
    for t in new:
        eng.cancel(t["id"])
    for row in rows:
        for a in row["answers"]:
            ev = eng.flow(a["trace"]) if a["trace"] else []
            labels = [str(e.get("label") or "") for e in ev]
            a["flow"] = {"events": len(ev), "prompts": sum("Nucleo(flash): prompt" in lab for lab in labels),
                         "search_events": sum(e.get("kind") == "search" for e in ev),
                         "jev_reads": sum(lab.startswith("jev read") for lab in labels),
                         "workers": sum(e.get("cat") == "worker" for e in ev)}
            a.pop("sent_at", None), a.pop("answered_at", None)
    return {"id": conv["id"], "class": conv["class"], "lang": conv["lang"], "session": session, "thoughts": rows,
            "new_tasks": [{"id": t.get("id"), "state": t.get("state"), "kind": t.get("kind"),
                           "title": str(t.get("title") or "")[:80]} for t in new]}


def judge(rec: dict) -> dict:
    """The old-path rules per thought; a conversation passes when every thought passes every rule that applies."""
    out = []
    for row in rec["thoughts"]:
        t, ans = row["turn"], row["answers"]
        said = [a for a in ans if str(a.get("reply") or "").strip()]
        called = set().union(*[families(c) for a in ans for c in a["tool_calls"]]) if ans else set()
        if any(a["flow"].get("search_events") or str(a.get("action") or "").startswith("search")
               or any(w in str(a.get("action") or "") for w in LIVE_DATA_WIDGETS) for a in ans):
            called |= {"search"}                     # the old path also searches without a tool call
        acted = any(_acts(a["tool_calls"], str(a.get("action") or "")) for a in ans)
        expect, forbid = reading(rec["class"], t)
        measurable = expect & MEASURABLE
        r = {"thought": t["thought"], "pieces": len(t["pieces"]), "answers": len(said), "called": sorted(called),
             "R4": len(said) == 1 if t["needs_answer"] else len(said) <= 1,
             "R6": not acted and not rec["new_tasks"],
             "R7": (not measurable or bool(called & measurable)) and not (called & forbid),
             "R7_unmeasured": sorted(expect - MEASURABLE),
             "R19": all(a["flow"]["prompts"] > 0 for a in said),
             "jev_reads": sum(a["flow"]["jev_reads"] for a in ans),
             "wall_ms": max((a["wall_ms"] for a in ans), default=None),
             "search": "search" in called}
        if rec["lang"] in ("es", "en") and said:
            r["R15"] = all(lang_of(a["reply"]) in (rec["lang"], "?") for a in said)
        r["pass"] = all(v for k, v in r.items() if k in ("R4", "R6", "R7", "R15", "R19"))
        out.append(r)
    return {"thoughts": out, "pass": all(r["pass"] for r in out)}


async def main_async(args) -> int:
    eng = Engine(args.port)
    d = CORPUS / args.version
    files = sorted(d.glob("U*.json"))
    convs = []
    for f in files:
        cls, lang = f.stem.split(".")
        if (args.classes and cls not in args.classes) or lang not in args.lang:
            continue
        convs += json.loads(f.read_text(encoding="utf-8"))[: args.limit or None]
    out = args.out or OUT / f"{time.strftime('%Y%m%d-%H%M%S')}-{'-'.join(args.lang)}"
    out.mkdir(parents=True, exist_ok=True)
    if args.seed:
        eng.seed(args.lang[0])
    manifest = json.loads((d / "manifest.json").read_text(encoding="utf-8")) if (d / "manifest.json").is_file() else {}
    (out / "run.json").write_text(json.dumps({"corpus": args.version, "corpus_frozen": manifest.get("frozen"),
                                              "port": args.port, "langs": args.lang, "n": len(convs),
                                              "started": time.strftime("%Y-%m-%dT%H:%M:%S")}, indent=1))
    done = {json.loads(line)["id"] for line in (out / "conversations.jsonl").read_text().splitlines()} \
        if (out / "conversations.jsonl").is_file() else set()
    with open(out / "conversations.jsonl", "a", encoding="utf-8") as fh:
        for i, conv in enumerate(convs, start=1):
            if conv["id"] in done:
                continue
            rec = await drive_conversation(eng, conv)
            rec["verdict"] = judge(rec)
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            print(f"[{i}/{len(convs)}] {conv['id']} {'PASS' if rec['verdict']['pass'] else 'fail'} "
                  f"tasks={len(rec['new_tasks'])}", flush=True)
    print(out)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").partition("\n")[0])
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--lang", nargs="+", required=True, help="the corpus languages this engine takes (es | en mix)")
    ap.add_argument("--version", default="v1")
    ap.add_argument("--classes", nargs="*", default=[])
    ap.add_argument("--limit", type=int, default=0, help="conversations per file (0 = all)")
    ap.add_argument("--seed", action="store_true")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
