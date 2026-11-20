"""The conversation corpus (test plan level 4): multi-turn conversations generated ONCE by a model, then frozen.

    ./.venv/bin/python -m tests.conversation.tools.corpus generate --version v1 [--classes U22 U27] [--langs es]
    ./.venv/bin/python -m tests.conversation.tools.corpus check --version v1
    ./.venv/bin/python -m tests.conversation.tools.corpus freeze --version v1 --removed removed.json
    ./.venv/bin/python -m tests.conversation.tools.corpus stats --version v1

One call per (class, language) asks the generator model for `N` conversations of that class in the JSON shape below,
through the Claude Code CLI with the local licence — a model different from the one under test — from a neutral
directory, with no settings, no tools and our own system prompt, so nothing of this repo leaks into the data.
Every answer is checked against the schema and its class's own shape; what fails is dropped and counted.

A conversation:

    {"id": "U22-es-007", "class": "U22", "lang": "es",
     "turns": [{"thought": 1, "channel": "text", "pieces": [{"text": "…", "after_ms": 0}],
                "amends": null, "refers_to": null, "needs_answer": true,
                "expect_tools": ["search"], "forbid_tools": ["agenda"], "entity": "NVIDIA", "act_refused": false}]}

A TURN is one thought of the person: what they want answered once and whole. `pieces` are how it arrives — one piece
for a sentence; several for a thought typed in bursts or said with pauses, `after_ms` after the previous piece (or
after the previous thought's last piece). `amends` names the thought it corrects, `refers_to` the one it points back
to. Tools are FAMILIES, not engine names, so the same corpus judges the old path and the new one:
`search · agenda · contacts · memory · about_self · messaging · screen`.

`freeze` writes `manifest.json`: the sha256 of every file, the exact brief each was generated with, the model id the
CLI reported, the date, and how many conversations were removed by hand and why. A version is never overwritten:
regenerating makes a new version. People are invented (the only contacts are the fixtures, Rowan and Inworld);
public things — listed companies, cities, teams — are real, so that a question can be answered from the web.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "corpus"
MODEL = "claude-sonnet-5-5"
PER_CALL = 20
FAMILIES = ("search", "agenda", "contacts", "memory", "about_self", "messaging", "screen")
LANG_NAME = {"es": "Spanish (Spain)", "en": "English (US)", "mix": "a mix of Spanish and English inside the same "
                                                                   "conversation and often inside one sentence"}

SYSTEM = ("You write synthetic test data for a voice and text personal assistant. You output ONLY a JSON array, no "
          "prose, no code fences. Public things are real, so that a question can be answered from the web: listed "
          "companies and their shares, cities, countries, sports teams, currencies, commodities, public events. "
          "PEOPLE are never real: a private person is invented, and the only contacts in the test agenda are Rowan "
          "and Inworld. Never name a real private person.")

SCHEMA = """Each element of the array is one conversation:
{"id": "<CLASS>-<LANG>-NNN", "class": "<CLASS>", "lang": "<LANG>",
 "turns": [  // one entry per THOUGHT of the person, in order
   {"thought": 1,                       // 1, 2, 3… in order
    "channel": "text" | "voice",        // how it arrives
    "pieces": [{"text": "...", "after_ms": 0}],   // how the thought arrives: ONE piece for a sentence; several when it
                                        // is typed in bursts or said with pauses; after_ms = silence before the piece
                                        // (for the first piece of a thought: since the previous thought ended)
    "amends": null | <thought number it corrects>,
    "refers_to": null | <earlier thought number it points back to>,
    "needs_answer": true | false,       // false only for a remark that asks for nothing ("ok", "thanks")
    "expect_tools": [...],              // the families the assistant should use to answer THIS thought; [] = none
    "forbid_tools": [...],              // families that would be a wrong route here
    "entity": "<what the thought is about, short>" | null,
    "act_refused": true | false         // true when the thought asks to SEND, CLOSE or CHANGE something
   }]}
Tool families: search (web search, live data, news, weather, prices), agenda (the user's calendar and reminders),
contacts (the user's contact list), memory (what the user told the assistant before), about_self (questions about the
assistant itself), messaging (sending a message), screen (opening/closing things on the screen).
The assistant under test can only READ in this phase: anything that sends, closes or changes is refused (act_refused)."""

#: The classes of the test plan that run on the corpus (§3, level 4), with what each conversation must be.
CLASSES: dict[str, str] = {
    "U01": "Plain text: 1 to 3 thoughts, each ONE written question in ONE piece, independent of each other. Mix "
           "domains (facts, weather, prices, the user's calendar, definitions).",
    "U02": "Text with a pause: 2 or 3 thoughts typed; between them the person waits 5000 to 30000 ms (after_ms of the "
           "first piece of thoughts 2+), and each later line is a related follow-up (refers_to the earlier one).",
    "U03": "Segmented text: 1 or 2 thoughts, each typed as 2 to 5 short messages in a row (pieces), 100 to 3000 ms "
           "apart, which only make sense together (the question is split mid-sentence).",
    "U16": "Self-correction: the person corrects something inside a thought ('in Bilbao... no, in San Sebastian') or "
           "in the next line ('sorry, I meant Friday'): the correcting thought has amends = the corrected one. Only "
           "read requests (questions), never orders to change things.",
    "U17": "Complaint: thought 1 asks a question X; thought 2 is an unrelated remark or another small question; "
           "thought 3 complains that X was not answered ('I asked you about X') and refers_to thought 1.",
    "U19": "'Close everything': at some point the person asks to close, hide or clear what is on the screen "
           "(act_refused true, expect_tools [], forbid_tools ['screen']); it is never a request to stop talking. Other "
           "thoughts are ordinary questions.",
    "U20": "Two interleaved topics: thought 1 opens topic A, thought 2 opens an unrelated topic B, thought 3 goes back "
           "to A (refers_to 1), thought 4 answers or adds to B (refers_to 2). Each entity is explicit.",
    "U21": "Topic switch and back: thought 1 about A, thought 2 about an unrelated B, thought 3 'going back to the "
           "first thing...' about A (refers_to 1).",
    "U22": "Questions with figures: market data, weather, dates, quantities, scores, exchange rates; expect_tools "
           "['search'], forbid_tools ['agenda']. Include, in about a quarter of them, a stock asked in three pieces "
           "with pauses (for example how a share usually moves on Fridays and how many of the last 30 it went up), "
           "followed by 'and how many went down?' (refers_to).",
    "U23": "Follow-up with a pronoun: thought 1 is a full question; thoughts 2 and 3 are short follow-ups that only make "
           "sense with it ('and yesterday?', 'and how many went down?', 'what about her?'), refers_to the first.",
    "U24": "Nothing to answer: ordinary questions mixed with remarks that ask for nothing ('ok', 'thanks', 'great', "
           "'hmm', 'got it'): those have needs_answer false, expect_tools [].",
    "U26": "About itself: questions about the assistant ('what can you do?', 'what's your name?', 'can you send "
           "messages here?', 'and in this session?'): expect_tools ['about_self'].",
    "U27": "Action in read-only: the person asks to send a message to Rowan or Inworld, by WhatsApp, email or "
           "Telegram, with the exact text (act_refused true, expect_tools [], forbid_tools ['messaging']); then a "
           "follow-up such as 'did you send it?'.",
    "U28": "Languages: ordinary questions and follow-ups, 2 to 4 thoughts, written as a native speaker would.",
}


#: What the CLASS forbids (its card in the test plan): the only forbidden families R7 enforces. The generator also
#: writes thought-level forbids of its own (a market question «forbids» memory); those are recorded, not judged.
CLASS_FORBID: dict[str, frozenset[str]] = {"U22": frozenset({"agenda"})}
READING_RULES = ("a thought with act_refused expects no tool (F1 refuses acts; R6 judges the act, not R7); "
                 "R7 enforces only the class's own forbidden families (CLASS_FORBID); thought-level forbid_tools are "
                 "the generator's and are not judged")


def reading(cls: str, turn: dict) -> tuple[set[str], set[str]]:
    """The (expected, forbidden) families R7 judges a thought by — the corpus's labels read by READING_RULES."""
    if turn["act_refused"]:
        return set(), set()
    return set(turn["expect_tools"]), set(turn["forbid_tools"]) & CLASS_FORBID.get(cls, frozenset())


def brief(cls: str, lang: str, n: int = PER_CALL) -> str:
    return (f"Write {n} conversations of class {cls} in {LANG_NAME[lang]}.\n\nClass {cls}: {CLASSES[cls]}\n\n"
            f"{SCHEMA}\n\nUse lang \"{lang}\" and ids {cls}-{lang}-001 … {cls}-{lang}-{n:03d}. Vary the wording, the "
            "domain, the length and the register as different real people would; about a third of the thoughts come "
            "by voice. Output only the JSON array.")


def _call(prompt: str, timeout: int = 900) -> tuple[str, str]:
    env = {k: v for k, v in os.environ.items()
           if k not in ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY")}
    argv = ["claude", "-p", prompt, "--model", MODEL, "--output-format", "json", "--strict-mcp-config",
            "--setting-sources", "", "--system-prompt", SYSTEM, "--no-session-persistence", "--tools", ""]
    with tempfile.TemporaryDirectory() as neutral:
        out = subprocess.run(argv, cwd=neutral, env=env, capture_output=True, text=True, timeout=timeout)
    if out.returncode != 0:
        raise RuntimeError(f"claude rc={out.returncode}: {(out.stderr or out.stdout)[:300]}")
    d = json.loads(out.stdout)
    if d.get("is_error"):
        raise RuntimeError(f"claude error: {str(d.get('result'))[:300]}")
    return d.get("result") or "", ",".join((d.get("modelUsage") or {}).keys())


def _parse(text: str) -> list:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    a, b = text.find("["), text.rfind("]")
    return json.loads(text[a: b + 1])


def problems(conv: dict, cls: str, lang: str) -> list[str]:
    """Why a conversation is not of its class or not well formed ([] = fine)."""
    p: list[str] = []
    if conv.get("class") != cls or conv.get("lang") != lang:
        p.append("class or lang")
    turns = conv.get("turns")
    if not isinstance(turns, list) or not turns:
        return p + ["no turns"]
    for i, t in enumerate(turns, start=1):
        if t.get("thought") != i:
            p.append(f"thought {i} numbering")
        if t.get("channel") not in ("text", "voice"):
            p.append(f"thought {i} channel")
        pieces = t.get("pieces")
        if not isinstance(pieces, list) or not pieces or any(not str(x.get("text") or "").strip() for x in pieces):
            p.append(f"thought {i} pieces")
            continue
        if any(not isinstance(x.get("after_ms"), int) or x["after_ms"] < 0 for x in pieces):
            p.append(f"thought {i} after_ms")
        for key in ("amends", "refers_to"):
            v = t.get(key)
            if v is not None and (not isinstance(v, int) or not 1 <= v < i):
                p.append(f"thought {i} {key}")
        for key in ("expect_tools", "forbid_tools"):
            if not isinstance(t.get(key), list) or set(t[key]) - set(FAMILIES):
                p.append(f"thought {i} {key}")
        if not isinstance(t.get("needs_answer"), bool) or not isinstance(t.get("act_refused"), bool):
            p.append(f"thought {i} flags")
    if p:
        return p
    multi = [t for t in turns if len(t["pieces"]) > 1]
    later = [t["pieces"][0]["after_ms"] for t in turns[1:]]
    shape = {
        "U01": all(len(t["pieces"]) == 1 for t in turns) and len(turns) <= 3,
        "U02": len(turns) >= 2 and all(5000 <= a <= 30000 for a in later) and any(t["refers_to"] for t in turns[1:]),
        "U03": bool(multi) and all(2 <= len(t["pieces"]) <= 5 and all(100 <= x["after_ms"] <= 3000
                                                                       for x in t["pieces"][1:]) for t in multi),
        "U16": any(t["amends"] for t in turns) or any(len(t["pieces"]) > 1 for t in turns),
        "U17": len(turns) >= 3 and turns[2]["refers_to"] == 1,
        "U19": any(t["act_refused"] and "screen" in t["forbid_tools"] for t in turns),
        "U20": len(turns) >= 4 and turns[2]["refers_to"] == 1 and turns[3]["refers_to"] == 2,
        "U21": len(turns) >= 3 and turns[2]["refers_to"] == 1,
        "U22": any("search" in t["expect_tools"] for t in turns),
        "U23": len(turns) >= 2 and any(t["refers_to"] for t in turns[1:]),
        "U24": any(not t["needs_answer"] for t in turns),
        "U26": any("about_self" in t["expect_tools"] for t in turns),
        "U27": any(t["act_refused"] and "messaging" in t["forbid_tools"] for t in turns),
        "U28": 2 <= len(turns) <= 4,
    }[cls]
    if not shape:
        p.append(f"not of class {cls}")
    text = json.dumps(conv, ensure_ascii=False).lower()
    if any(re.search(rf"\b{re.escape(n)}\b", text) for n in _private_names()):
        p.append("a real name")
    return p


def _private_names() -> list[str]:
    """Names that must never appear in the corpus — the real people around whoever runs this — read from a file that
    lives OUTSIDE this public repo (`ZAELAR_PRIVATE_NAMES_FILE`, one name per line). No file: no names to check."""
    path = os.environ.get("ZAELAR_PRIVATE_NAMES_FILE", "")
    if not path or not Path(path).is_file():
        return []
    return [line.strip().lower() for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def _dir(version: str) -> Path:
    return ROOT / version


def generate(version: str, classes: list[str], langs: list[str], workers: int = 4) -> dict:
    d = _dir(version)
    if (d / "manifest.json").is_file():
        raise SystemExit(f"{version} is frozen; generate a new version")
    (d / "raw").mkdir(parents=True, exist_ok=True)
    jobs = [(c, lang) for c in classes for lang in (langs if c != "U28" else ["es", "en", "mix"])
            if lang in langs or c == "U28"]
    jobs = [(c, lang) for c, lang in jobs if not (d / f"{c}.{lang}.json").is_file()]

    def one(job):
        cls, lang = job
        prompt = brief(cls, lang)
        text, model = _call(prompt)
        (d / "raw" / f"{cls}.{lang}.txt").write_text(text, encoding="utf-8")
        convs = _parse(text)
        kept, dropped = [], []
        for c in convs:
            why = problems(c, cls, lang)
            (dropped if why else kept).append({"id": c.get("id"), "why": why} if why else c)
        (d / f"{cls}.{lang}.json").write_text(json.dumps(kept, ensure_ascii=False, indent=1), encoding="utf-8")
        (d / "raw" / f"{cls}.{lang}.meta.json").write_text(json.dumps(
            {"class": cls, "lang": lang, "brief": prompt, "system": SYSTEM, "model": model,
             "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
             "returned": len(convs), "kept": len(kept), "dropped": dropped}, ensure_ascii=False, indent=1),
            encoding="utf-8")
        return cls, lang, len(convs), len(kept)

    out = {}
    with cf.ThreadPoolExecutor(workers) as ex:
        for fut in cf.as_completed([ex.submit(one, j) for j in jobs]):
            try:
                cls, lang, n, k = fut.result()
                out[f"{cls}.{lang}"] = [n, k]
                print(f"{cls}.{lang}: {k}/{n} kept", flush=True)
            except Exception as e:  # noqa: BLE001 — one failed call is retried by running generate again
                print(f"failed: {e!r}"[:300], flush=True)
    return out


def check(version: str) -> dict:
    d = _dir(version)
    res = {}
    for f in sorted(d.glob("U*.json")):
        cls, lang = f.stem.split(".")
        convs = json.loads(f.read_text(encoding="utf-8"))
        bad = {c["id"]: problems(c, cls, lang) for c in convs if problems(c, cls, lang)}
        ids = [c["id"] for c in convs]
        res[f.stem] = {"n": len(convs), "bad": bad, "duplicate_ids": len(ids) - len(set(ids))}
    return res


def freeze(version: str, removed: Path | None, review: str = "") -> Path:
    d = _dir(version)
    if (d / "manifest.json").is_file():
        raise SystemExit(f"{version} is already frozen")
    removed_by_hand = json.loads(removed.read_text(encoding="utf-8")) if removed else {}
    files = {}
    for f in sorted(d.glob("U*.json")):
        meta = json.loads((d / "raw" / f"{f.stem}.meta.json").read_text(encoding="utf-8"))
        convs = json.loads(f.read_text(encoding="utf-8"))
        files[f.name] = {"sha256": hashlib.sha256(f.read_bytes()).hexdigest(), "conversations": len(convs),
                         "brief": meta["brief"], "system": meta["system"], "model": meta["model"],
                         "generated": meta["generated"], "returned": meta["returned"],
                         "dropped_by_check": len(meta["dropped"]),
                         "removed_by_hand": removed_by_hand.get(f.stem, [])}
    manifest = {"version": version, "frozen": dt.date.today().isoformat(), "generator": MODEL,
                "reading_rules": READING_RULES, "class_forbid": {k: sorted(v) for k, v in CLASS_FORBID.items()},
                "total": sum(v["conversations"] for v in files.values()), "review": review, "files": files}
    path = d / "manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def stats(version: str) -> dict:
    d = _dir(version)
    out = {}
    for f in sorted(d.glob("U*.json")):
        convs = json.loads(f.read_text(encoding="utf-8"))
        turns = [t for c in convs for t in c["turns"]]
        out[f.stem] = {"conversations": len(convs), "thoughts": len(turns),
                       "voice": sum(t["channel"] == "voice" for t in turns),
                       "multi_piece": sum(len(t["pieces"]) > 1 for t in turns)}
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").partition("\n")[0])
    ap.add_argument("cmd", choices=("generate", "check", "freeze", "stats", "brief"))
    ap.add_argument("--version", default="v1")
    ap.add_argument("--classes", nargs="*", default=list(CLASSES))
    ap.add_argument("--langs", nargs="*", default=["es", "en"])
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--removed", type=Path)
    ap.add_argument("--review", default="", help="what the hand review looked at, for the manifest")
    args = ap.parse_args(argv)
    if args.cmd == "generate":
        print(json.dumps(generate(args.version, args.classes, args.langs, args.workers)))
    elif args.cmd == "check":
        print(json.dumps(check(args.version), ensure_ascii=False, indent=1))
    elif args.cmd == "freeze":
        print(freeze(args.version, args.removed, args.review))
    elif args.cmd == "stats":
        print(json.dumps(stats(args.version), indent=1))
    else:
        print(brief(args.classes[0], args.langs[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
