"""The rules of the test plan (§2.1, R1–R19), as pure functions over what the engine leaves written.

Every rule returns a `Verdict`: PASS, FAIL or INFRA, the number of cases it EVALUATED and the failures with their
evidence. Zero cases evaluated is INFRA, never PASS (plan §2.4): a rule that reads a field that changed name sees zero
rows, and that must not read as green. A rule that needs data the record does not carry (the proof counters, the exit
door's counters, `notices`, the evidence of a figure) is INFRA with the reason, never a guess.

A RECORD is one conversation as the driver saw it and the engine wrote it:

    events      [(kind, label, payload)] — the `conv_*` events, in order, payload with `t_ms` and `refs`
    thoughts    [{"id", "pieces": [text], "start_ms", "end_ms", "lang", "refers_to": [ids], "amends": id|None,
                  "expect": {families}, "forbid": {families}, "act_refused", "needs_answer", "foreign": [text]}]
    replies     {req: text} — what was said, for R8 and R15 (the wall or the mouth's line)
    proof       {"manager_runs", "livekit_turns", "old_prompts", "jev_reads", "generate_reply"} | None
    exits       {"out": n, "held": n} — the exit door's counters for the conversation | None
    tasks_new, drafts_new   ints | None
    notices     [{"key", "state", "claimed_until_ms", ...}] | None
    evidence    {req: [figures as strings]} | None
    stops       [t_ms] — when a stop was given (R10)
    family      callable tool name → family (default: the name)

The thresholds that are numbers (latency, stop-to-silence) are arguments: the plan freezes them (§6), not the rule.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

PASS, FAIL, INFRA = "PASS", "FAIL", "INFRA"
#: the gateway's labels for something that left or was reserved to leave; `sealed` is not one — it is the seal of his
#: interventions when a reply is published, which every answered batch carries
ACT_LABELS = ("claimed", "submitted", "receipt", "unknown", "reconciled")
ALLOWED_INBOX = ("user.utterance", "user.text", "user.control")


@dataclass
class Verdict:
    rule: str
    status: str
    n: int = 0
    failures: list = field(default_factory=list)
    why: str = ""

    def __bool__(self) -> bool:
        return self.status == PASS


def _verdict(rule: str, n: int, failures: list, why_infra: str = "") -> Verdict:
    if why_infra:
        return Verdict(rule, INFRA, n, failures, why_infra)
    if n == 0:
        return Verdict(rule, INFRA, 0, [], "zero cases evaluated")
    return Verdict(rule, FAIL if failures else PASS, n, failures)


def _ev(rec: dict, kind: str, label: str | None = None) -> list[dict]:
    return [p for k, lab, p in rec["events"] if k == kind and (label is None or lab == label)]


def _ref(p: dict, key: str):
    return (p.get("refs") or {}).get(key)


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[\w']+", str(text).lower())]


def _in_order(needle: list[str], hay: list[str]) -> bool:
    it = iter(hay)
    return all(any(w == h for h in it) for w in needle)


def _inputs(rec: dict) -> dict[str, list[str]]:
    """run → the words of its prompt's input, in order."""
    return {_ref(p, "run"): _words(" ".join(t for t in (p.get("text") or []) if t)) for p in _ev(rec, "conv_run", "input")}


# ── R1–R19 ───────────────────────────────────────────────────────────────────────────────────────────────────────

def r1_single_close(rec: dict, liveness_ms: int = 30_000) -> Verdict:
    opened = {_ref(p, "req"): p["t_ms"] for p in _ev(rec, "conv_ledger", "opened") if p.get("item_kind") == "request"}
    closes: dict[str, list] = {}
    for p in _ev(rec, "conv_close"):
        closes.setdefault(_ref(p, "req"), []).append(p["t_ms"])
    fails = [{"req": r, "closes": len(closes.get(r, [])), "late_ms": (closes[r][0] - t - liveness_ms)
              if closes.get(r) and closes[r][0] - t > liveness_ms else 0}
             for r, t in opened.items() if len(closes.get(r, [])) != 1 or closes[r][0] - t > liveness_ms]
    return _verdict("R1", len(opened), fails)


def r2_whole_thought(rec: dict) -> Verdict:
    """Text and script levels: every word of the thought, in order, in ONE prompt."""
    inputs = list(_inputs(rec).values())
    fails = [{"thought": t["id"]} for t in rec["thoughts"] if t.get("needs_answer", True)
             and not any(_in_order(_words(" ".join(t["pieces"])), w) for w in inputs)]
    return _verdict("R2", sum(1 for t in rec["thoughts"] if t.get("needs_answer", True)), fails)


def r3_nothing_before(rec: dict) -> Verdict:
    starts = [p["t_ms"] for p in _ev(rec, "conv_mouth", "started")]
    if not starts and _ev(rec, "conv_mouth", "say"):
        return _verdict("R3", 0, [], "lines were said but none carries its `started`")
    fails = [{"thought": t["id"], "said_at": s} for t in rec["thoughts"] for s in starts
             if t["start_ms"] <= s < t["end_ms"]]
    return _verdict("R3", len(rec["thoughts"]), fails)


def r4_one_answer(rec: dict) -> Verdict:
    inputs = _inputs(rec)
    says_by_run: dict[str, int] = {}
    for p in _ev(rec, "conv_mouth", "say"):
        says_by_run[_ref(p, "run")] = says_by_run.get(_ref(p, "run"), 0) + 1
    fails = []
    for t in rec["thoughts"]:
        w = _words(" ".join(t["pieces"]))
        runs = [r for r, iw in inputs.items() if w and _in_order(w[-min(3, len(w)):], iw)]
        said = sum(says_by_run.get(r, 0) for r in runs)
        if said > 1:
            fails.append({"thought": t["id"], "publications": said})
    accounted: dict[str, int] = {}
    for p in _ev(rec, "conv_inbox", "accounted"):
        accounted[_ref(p, "env")] = accounted.get(_ref(p, "env"), 0) + 1
    fails += [{"env": e, "accounted": n} for e, n in accounted.items() if n > 1]
    return _verdict("R4", len(rec["thoughts"]), fails)


def r5_single_owner(rec: dict) -> Verdict:
    proof = rec.get("proof")
    if proof is None:
        return _verdict("R5", 0, [], "no proof counters in the record")
    fails = [] if proof.get("manager_runs", 0) > 0 else [{"manager_runs": proof.get("manager_runs", 0)}]
    fails += [{k: proof[k]} for k in ("livekit_turns", "old_prompts", "jev_reads", "generate_reply") if proof.get(k)]
    return _verdict("R5", 1, fails)


def r6_no_effects(rec: dict) -> Verdict:
    missing = [k for k in ("exits", "tasks_new", "drafts_new") if rec.get(k) is None]
    if missing:
        return _verdict("R6", 0, [], f"the record lacks {', '.join(missing)}")
    fails = [{"effect": lab, "tool": p.get("tool")} for k, lab, p in rec["events"]
             if k == "conv_effect" and lab in ACT_LABELS]
    ex = rec["exits"]
    if ex.get("out") or ex.get("held"):
        fails.append({"exits": ex})
    if rec["tasks_new"]:
        fails.append({"tasks_new": rec["tasks_new"]})
    if rec["drafts_new"]:
        fails.append({"drafts_new": rec["drafts_new"]})
    return _verdict("R6", 1, fails)


def r7_route(rec: dict) -> Verdict:
    family = rec.get("family") or (lambda name: name)
    reads_by_req: dict[str, set] = {}
    for p in _ev(rec, "conv_effect", "read"):
        reads_by_req.setdefault(_ref(p, "req"), set()).add(family(p.get("tool")))
    called = set().union(*reads_by_req.values()) if reads_by_req else set()
    n, fails = 0, []
    for t in rec["thoughts"]:
        expect, forbid = (set(), set()) if t.get("act_refused") else (set(t.get("expect") or ()), set(t.get("forbid") or ()))
        reqs = t.get("reqs")
        mine = set().union(*(reads_by_req.get(r, set()) for r in reqs)) if reqs else called
        if not expect and not forbid:
            continue
        n += 1
        if (expect and not (mine & expect)) or (mine & forbid):
            fails.append({"thought": t["id"], "expected": sorted(expect), "called": sorted(mine)})
    return _verdict("R7", n, fails)


_FIG = re.compile(r"\d+(?:[.,]\d+)?")


def r8_figures(rec: dict) -> Verdict:
    if rec.get("evidence") is None or not rec.get("replies"):
        return _verdict("R8", 0, [], "the record lacks the evidence or the replies")
    said_by_person = set(_FIG.findall(" ".join(" ".join(t["pieces"]) for t in rec["thoughts"])))
    n, fails = 0, []
    for req, text in rec["replies"].items():
        figs = set(_FIG.findall(text or ""))
        if not figs:
            continue
        n += 1
        backed = {f.replace(",", ".") for f in rec["evidence"].get(req, [])} | {f.replace(",", ".") for f in said_by_person}
        loose = sorted(f for f in figs if f.replace(",", ".") not in backed)
        if loose:
            fails.append({"req": req, "unbacked": loose})
    return _verdict("R8", n, fails)


def r9_foreign_out(rec: dict) -> Verdict:
    inputs = list(_inputs(rec).values())
    discarded = [_words(p.get("text") or "") for p in _ev(rec, "conv_ear", "discarded")]
    n, fails = 0, []
    for t in rec["thoughts"]:
        for frag in t.get("foreign") or ():
            n += 1
            w = _words(frag)
            if any(_in_order(w, i) for i in inputs):
                fails.append({"thought": t["id"], "foreign_in_prompt": frag})
    if discarded and not all(p.get("reason") for p in _ev(rec, "conv_ear", "discarded")):
        fails.append({"discard_without_reason": True})
    return _verdict("R9", n, fails)


def r10_stop(rec: dict, silence_ms: int = 300) -> Verdict:
    stops = rec.get("stops") or []
    cuts = _ev(rec, "conv_mouth", "cut")
    fails = []
    for s in stops:
        cut = next((c for c in cuts if c["t_ms"] >= s), None)
        if cut is not None and (cut.get("stop_to_silence_ms") or 0) > silence_ms:
            fails.append({"stop": s, "stop_to_silence_ms": cut.get("stop_to_silence_ms")})
        cancelled = {_ref(p, "run") for p in _ev(rec, "conv_run", "cancelled") if p["t_ms"] >= s}
        late = [p for p in _ev(rec, "conv_mouth", "say") if p["t_ms"] > s and _ref(p, "run") in cancelled]
        if late:
            fails.append({"stop": s, "said_after": len(late)})
    return _verdict("R10", len(stops), fails)


def r11_channel(rec: dict) -> Verdict:
    channel_of = {_ref(p, "env"): _ref(p, "channel") for p in _ev(rec, "conv_inbox", "accepted")}
    voice_runs = {_ref(p, "run") for p in _ev(rec, "conv_run", "started")
                  if any(channel_of.get(e) == "voice" for e in p.get("batch_envs") or [])}
    has_channels = [p for p in _ev(rec, "conv_mouth", "say") if p.get("channels") is not None]
    fails = []
    for p in has_channels:
        ch = set(p["channels"])
        if "text" not in ch:
            fails.append({"say": _ref(p, "say"), "channels": sorted(ch), "why": "text always goes to the wall"})
        if "voice" in ch and _ref(p, "run") not in voice_runs and not p.get("rule_voice"):
            fails.append({"say": _ref(p, "say"), "why": "voice for a batch without voice"})
    return _verdict("R11", len(has_channels), fails)


def r12_order(rec: dict) -> Verdict:
    accepted = _ev(rec, "conv_inbox", "accepted")
    if accepted and all("onset_ms" not in p for p in accepted):
        return _verdict("R12", 0, [], "conv_inbox events carry no onset_ms: the order by onset cannot be read")
    onset = {_ref(p, "env"): p.get("onset_ms") for p in accepted}
    fails = []
    for p in _ev(rec, "conv_run", "started"):
        seq = [onset.get(e) for e in p.get("batch_envs") or [] if onset.get(e) is not None]
        if seq != sorted(seq):
            fails.append({"run": _ref(p, "run"), "onsets": seq})
    return _verdict("R12", len(_ev(rec, "conv_run", "started")), fails)


def r13_notice(rec: dict, now_ms: int | None = None) -> Verdict:
    notices = rec.get("notices")
    if notices is None:
        return _verdict("R13", 0, [], "the record lacks the notices table")
    said: dict[str, int] = {}
    for p in _ev(rec, "conv_mouth", "say"):
        if p.get("notice_key"):
            said[p["notice_key"]] = said.get(p["notice_key"], 0) + 1
    fails = [{"notice": k, "said": n} for k, n in said.items() if n > 1]
    for row in notices:
        if row.get("state") not in ("spoken", "owed", "shown", "covered", "delivered"):
            if row.get("state") == "claimed" and now_ms and (row.get("claimed_until_ms") or 0) < now_ms:
                fails.append({"notice": row.get("key"), "state": "claimed past its deadline"})
    return _verdict("R13", len(notices), fails)


def r14_trace(rec: dict) -> Verdict:
    traces = {_ref(p, "run"): p.get("trace") for k, lab, p in rec["events"] if p.get("trace") and _ref(p, "run")}
    fails = [{"event": f"{k}/{lab}"} for k, lab, p in rec["events"]
             if not p.get("trace") and not traces.get(_ref(p, "run"))]
    return _verdict("R14", len(rec["events"]), fails)


_ES = set("el la los las de que y en un una por para con no se lo es al del me te le qué cómo cuánto está hoy hay sí".split())
_EN = set("the a an of and to in is are it you for on with that this what how many much today yes not".split())


def lang_of(text: str) -> str:
    w = _words(text)
    es, en = sum(x in _ES for x in w), sum(x in _EN for x in w)
    return "es" if es > en else "en" if en > es else "?"


def r15_language(rec: dict) -> Verdict:
    replies = rec.get("replies") or {}
    lang_of_req = {r: t["lang"] for t in rec["thoughts"] for r in t.get("reqs") or () if t.get("lang") in ("es", "en")}
    n, fails = 0, []
    for req, text in replies.items():
        want = lang_of_req.get(req)
        if not want or not str(text or "").strip():
            continue
        n += 1
        got = lang_of(text)
        if got not in (want, "?"):
            fails.append({"req": req, "want": want, "got": got})
    return _verdict("R15", n, fails)


def r16_latency(rec: dict, p50_ms: int, p95_ms: int, key: str = "total_ms") -> Verdict:
    xs = sorted(p.get(key) for p in _ev(rec, "conv_close", "answered") if p.get(key) is not None)
    if not xs:
        return _verdict("R16", 0, [])
    p50, p95 = xs[len(xs) // 2], xs[min(len(xs) - 1, int(0.95 * len(xs)))]
    fails = [{"p50": p50}] if p50 > p50_ms else []
    fails += [{"p95": p95}] if p95 > p95_ms else []
    return _verdict("R16", len(xs), fails)


def r17_clean_start(rec: dict) -> Verdict:
    rec_ = rec.get("recovered")
    if rec_ is None:
        return _verdict("R17", 0, [], "no restart in this record (level 1, P8, judges it)")
    fails = [{"said_twice": rec_["said_twice"]}] if rec_.get("said_twice") else []
    fails += [{"open_voice": rec_["open_voices"]}] if rec_.get("open_voices") else []
    return _verdict("R17", 1, fails)


def r18_contract(rec: dict) -> Verdict:
    accepted = _ev(rec, "conv_inbox", "accepted")
    fails = [{"env": _ref(p, "env"), "kind": p.get("kind")} for p in accepted if p.get("kind") not in ALLOWED_INBOX]
    return _verdict("R18", len(accepted), fails)


def r19_context(rec: dict) -> Verdict:
    """Every request closed `answered` had a run with the model on its batch; a follow-up's PROMPT carries the thoughts
    it refers to. The prompt is not in the events (only its size): the context half needs `prompts` {run: text} from a
    prompt capture; without it, a record with follow-ups is INFRA (unless the first half already failed)."""
    run_reqs = {_ref(p, "req") for p in _ev(rec, "conv_run", "started")} | \
               {_ref(p, "req") for p in _ev(rec, "conv_inbox", "dequeued") if p.get("batch")}
    answered = [_ref(p, "req") for p in _ev(rec, "conv_close", "answered")]
    fails = [{"req": r, "why": "answered with no run of its own"} for r in answered if r not in run_reqs]
    n = len(answered)
    prompts = rec.get("prompts")
    follow_ups = [t for t in rec["thoughts"] if t.get("refers_to")]
    if follow_ups and prompts is None:
        if fails:
            return _verdict("R19", n, fails)
        return _verdict("R19", n, [], "the context half needs the prompts (a prompt capture), not in the record")
    by_id = {t["id"]: t for t in rec["thoughts"]}
    texts = [_words(x) for x in (prompts or {}).values()]
    for t in follow_ups:
        for ref in t["refers_to"]:
            n += 1
            mine = _words(" ".join(t["pieces"]))
            theirs = _words(" ".join(by_id[ref]["pieces"])) if ref in by_id else []
            if not any(_in_order(mine[-3:], w) and _in_order(theirs, w) for w in texts):
                fails.append({"thought": t["id"], "missing_context_of": ref})
    return _verdict("R19", n, fails)


RULES = {"R1": r1_single_close, "R2": r2_whole_thought, "R3": r3_nothing_before, "R4": r4_one_answer,
         "R5": r5_single_owner, "R6": r6_no_effects, "R7": r7_route, "R8": r8_figures, "R9": r9_foreign_out,
         "R10": r10_stop, "R11": r11_channel, "R12": r12_order, "R13": r13_notice, "R14": r14_trace,
         "R15": r15_language, "R17": r17_clean_start, "R18": r18_contract, "R19": r19_context}


def judge_all(rec: dict, **thresholds) -> dict[str, Verdict]:
    """Every rule that needs no threshold, plus R16 when its thresholds are given."""
    out = {name: fn(rec) for name, fn in RULES.items()}
    if "p50_ms" in thresholds:
        out["R16"] = r16_latency(rec, thresholds["p50_ms"], thresholds["p95_ms"])
    return out


def from_observer(rows: list[dict]) -> list[tuple[str, str, dict]]:
    """Events as the engine STORES them (`/api/observability/flow/<trace>` rows, or the `events` table) → the
    `(kind, label, payload)` the rules read. The observer keeps the package's colliding fields under `extra_<key>`
    (`voice/observer.py::_merge`): the package's own clock is `extra_t_ms` and an inbox envelope's kind is
    `extra_kind`; both are put back where the rules look."""
    out = []
    for r in rows:
        kind = str(r.get("kind") or "")
        if not kind.startswith("conv_"):
            continue
        p = r.get("payload")
        p = json.loads(p) if isinstance(p, str) else dict(p or {})
        if "extra_t_ms" in p:
            p["t_ms"] = p["extra_t_ms"]
        if "extra_kind" in p:
            p["kind"] = p["extra_kind"]
        p.setdefault("trace", r.get("corr_id") or "")
        out.append((kind, str(r.get("label") or p.get("label") or ""), p))
    return sorted(out, key=lambda e: (e[2].get("t_ms") or 0))
