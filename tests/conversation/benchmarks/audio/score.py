"""Units of what a detector delivered, scored against the scenario's truth.

A UNIT is one thing the agent would act on: a Flux turn (the old path: `turn_detection="stt"` makes each EndOfTurn a
LiveKit turn), an ear intervention (the new path's ear), or a manager batch (what reaches the model in one run). Each
unit has the words it carries (with audio times) and the instant it was delivered.

Every heard word is matched to the truth by time: to the labelled word it overlaps most (Inworld voices carry
per-word times), else to the labelled segment it overlaps most, else it is `noise` (heard where nobody spoke).

    false cut    a user turn whose words arrive in more than one unit (each extra unit counts one)
    false merge  a unit that carries words of more than one user turn (each extra turn counts one); a unit with the
                 user's words AND a stranger's counts apart (`merged_with_stranger`)
    exposure     stranger segments (`other`, `tv`) with at least one word inside some unit / all stranger segments
    crosstalk    words of someone who is not the user (`other`, `tv`) inside a unit; a unit made ONLY of them is a
                 turn the agent would take from a stranger
    lost         a user turn none of whose words reached any unit
    unclosed     a user turn whose unit was never delivered while the audio ran (no end of turn before the stream ended)
    eot delay    delivery of the unit holding the turn's last word − the instant the person truly finished
"""
from __future__ import annotations

TOL_MS = 120
STRANGERS = ("other", "tv", "echo")      # everything said that is not the person (echo = our own voice)
NEAR_MS = 700           # how far from a segment a heard word may land (Flux's word times drift)
SIMILAR = 0.75


def _overlap(a0: int, a1: int, b0: int, b1: int) -> int:
    return max(0, min(a1, b1) - max(a0, b0))


def _norm(token: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", str(token).lower())
    return "".join(ch for ch in t if ch.isalnum())


def _similar(a: str, b: str) -> float:
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a, b).ratio() if a and b else 0.0


def match_word(labels: dict, w0: int, w1: int, text: str = "") -> dict:
    """The truth a heard word belongs to: `{"role", "turn", "seg"}`; role `noise` when nobody spoke there.

    We know exactly what each voice said, so the TEXT decides among the segments near the word in time (a heard
    word ≥ `SIMILAR` to a word that segment said); time alone decides only when no nearby segment said anything like
    it (a misheard word), and then a foreground voice beats the TV at equal overlap."""
    heard = _norm(text)
    best, best_key = None, (0.0, 0, 0)
    for seg in labels["segments"]:
        if seg["role"] == "cough":
            continue
        if not _overlap(w0, w1, seg["start_ms"] - NEAR_MS, seg["end_ms"] + NEAR_MS):
            continue
        said = [(_norm(w), a, b) for w, a, b in seg["words"]] or [(_norm(w), seg["start_ms"], seg["end_ms"])
                                                                   for w in seg["text"].split()]
        sim = max((_similar(heard, t) for t, _, _ in said), default=0.0)
        sim = sim if sim >= SIMILAR else 0.0
        timed = [(a, b) for _, a, b in seg["words"] if a is not None and b is not None]
        if timed:                                   # a voice that gave no word times is matched by its segment
            ov = max(_overlap(w0 - TOL_MS, w1 + TOL_MS, a, b) for a, b in timed)
        else:
            ov = _overlap(w0 - TOL_MS, w1 + TOL_MS, seg["start_ms"], seg["end_ms"])
        key = (sim, 1 if seg["role"] in ("user", "other", "echo") else 0, ov) if (sim or ov) else (0.0, 0, 0)
        if key > best_key:
            best, best_key = seg, key
    if best is None:
        return {"role": "noise", "turn": None, "seg": None}
    return {"role": best["role"], "turn": best["turn"], "seg": best["i"]}


def score(labels: dict, units: list[dict]) -> dict:
    """`units`: [{"id", "words": [[text, t0_ms, t1_ms], …], "end_ms": int | None}] in delivery order."""
    turns = {t["turn"]: t for t in labels["turns"]}
    per_turn = {t: {"units": [], "last_unit": None, "last_word_ms": -1} for t in turns}
    unit_rows = []
    crosstalk_words = crosstalk_units = noise_words = merged_with_stranger = 0
    exposed: set[int] = set()
    for u in units:
        roles = [match_word(labels, int(w[1]), int(w[2]), w[0]) for w in u["words"]]
        user_turns = sorted({r["turn"] for r in roles if r["role"] == "user" and r["turn"] is not None})
        strangers = sum(1 for r in roles if r["role"] in STRANGERS)
        noise = sum(1 for r in roles if r["role"] == "noise")
        crosstalk_words += strangers
        noise_words += noise
        if u["words"] and not user_turns and strangers:
            crosstalk_units += 1
        if user_turns and strangers:
            merged_with_stranger += 1
        exposed |= {r["seg"] for r in roles if r["role"] in STRANGERS}
        for (w, r) in zip(u["words"], roles):
            if r["role"] == "user" and r["turn"] in per_turn:
                pt = per_turn[r["turn"]]
                if u["id"] not in pt["units"]:
                    pt["units"].append(u["id"])
                if int(w[2]) >= pt["last_word_ms"]:
                    pt["last_word_ms"], pt["last_unit"] = int(w[2]), u
        u["_user_turns"], u["_strangers"] = user_turns, strangers
        unit_rows.append({"id": u["id"], "end_ms": u.get("end_ms"), "words": len(u["words"]), "user_turns": user_turns,
                          "stranger_words": strangers, "noise_words": noise, "text": " ".join(w[0] for w in u["words"])})
    rows, delays = [], []
    for t, tr in turns.items():
        pt = per_turn[t]
        unit = pt["last_unit"]
        end = unit.get("end_ms") if unit else None
        unclosed = unit is not None and (end is None or end > labels["duration_ms"])
        delay = None if (unit is None or unclosed) else end - tr["end_ms"]
        if delay is not None:
            delays.append(delay)
        merged = bool(unit) and (len(unit["_user_turns"]) > 1 or unit["_strangers"] > 0)
        rows.append({"turn": t, "kind": tr["kind"], "true_end_ms": tr["end_ms"], "units": pt["units"], "merged": merged,
                     "eot_delay_ms": delay, "lost": not pt["units"],
                     "unclosed": unclosed})
    return {
        "units": len(units),
        "false_cuts": sum(max(0, len(r["units"]) - 1) for r in rows),
        "false_merges": sum(max(0, len(u["user_turns"]) - 1) for u in unit_rows),
        "merged_with_stranger": merged_with_stranger,
        "exposure": [len(exposed), sum(1 for g in labels["segments"] if g["role"] in STRANGERS)],
        "crosstalk_words": crosstalk_words, "crosstalk_units": crosstalk_units, "noise_words": noise_words,
        "lost_turns": sum(1 for r in rows if r["lost"]),
        "unclosed_turns": sum(1 for r in rows if r["unclosed"]),
        "eot_delay_ms": delays,
        "turns": rows, "unit_rows": unit_rows,
    }


# ── The plan's measure on what the model was handed (test plan §5.3) ─────────────────────────────────────────────

ARRIVE = 0.70        # a span ARRIVES in a prompt when this share of its words is there, in order
SHORT_SPAN = 4       # under this many words: all but one


def words_of(text: str) -> list[str]:
    """Lower case, no punctuation (§5.3). Accents stay: the plan normalises case and punctuation only."""
    out = []
    for raw in str(text).split():
        w = "".join(ch for ch in raw.lower() if ch.isalnum() or ch in "'")
        if w:
            out.append(w)
    return out


FUZZY = 0.80         # the tolerant alignment: accents off and words this similar count as the same word


def _same(x: str, y: str, fuzzy: bool) -> bool:
    if x == y:
        return True
    if not fuzzy:
        return False
    import unicodedata
    from difflib import SequenceMatcher
    plain = lambda w: "".join(c for c in unicodedata.normalize("NFKD", w) if not unicodedata.combining(c))   # noqa: E731
    a, b = plain(x), plain(y)
    return a == b or SequenceMatcher(None, a, b).ratio() >= FUZZY


def _lcs(a: list[str], b: list[str], fuzzy: bool = False) -> int:
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    for x in a:
        cur = [0]
        for j, y in enumerate(b, start=1):
            cur.append(prev[j - 1] + 1 if _same(x, y, fuzzy) else max(prev[j], cur[-1]))
        prev = cur
    return prev[-1]


def arrives(span: list[str], prompt: list[str], fuzzy: bool = False) -> bool:
    """§5.3 as frozen: ≥ 70 % of the span's words in the prompt, in order; under four words, all but one. `fuzzy` is
    the tolerant variant reported beside it (accents off, words ≥ 80 % alike), for what Flux mis-hears."""
    n = len(span)
    if n == 0:
        return False
    need = max(1, n - 1) if n < SHORT_SPAN else -(-int(ARRIVE * 100) * n // 100)
    return _lcs(span, prompt, fuzzy) >= need


def present(span: list[str], prompt: list[str]) -> bool:
    """Is a span of ANOTHER thought (or a stranger's) in this prompt? As `arrives`, but never on one word: under four
    words «all but one» lets a two-word span («en Valencia») be found through a function word of any prompt."""
    n = len(span)
    if n == 0:
        return False
    need = max(min(2, n), max(1, n - 1) if n < SHORT_SPAN else -(-int(ARRIVE * 100) * n // 100))
    return _lcs(span, prompt) >= need


SPAN_TOL_MS = 150     # a heard word belongs to a span when its middle is inside the span's window ± this
SAME_WORD_MS = 60     # a word of a run's prompt IS a heard word when their middles are this close (the ear's words
                      # are the provider's words: by time, never by text)


def _mid(w) -> float:
    return (int(w[1]) + int(w[2])) / 2


def heard_in_span(labels: dict, span: dict, heard: list) -> list:
    """The provider's words for one span: inside its time window, and attributed to it (`match_word`) — so a voice
    over it (the TV, another person) is not his."""
    return [w for w in heard if span["start_ms"] - SPAN_TOL_MS <= _mid(w) <= span["end_ms"] + SPAN_TOL_MS
            and match_word(labels, int(w[1]), int(w[2]), w[0]).get("seg") == span["i"]]


def _covered(w, run_words: list) -> bool:
    return any(abs(_mid(w) - _mid(r)) <= SAME_WORD_MS for r in run_words)


def r2_by_time(span_heard: list[list], runs: list[dict]):
    """§5.3 (decided 2026-11-20): every word the provider transcribed inside his spans reaches the prompt of the run
    that answers him, matched by TIME. A span with nothing transcribed is out of R2 (the provider's baseline); a
    thought with nothing transcribed at all is out (None). The answering run: among the runs holding a word of his
    last transcribed span, the one holding most of his words (the later on a tie)."""
    spans = [ws for ws in span_heard if ws]
    if not spans:
        return None, None
    words = [w for ws in spans for w in ws]
    cands = [(sum(_covered(w, r.get("words") or []) for w in words), i, r) for i, r in enumerate(runs)
             if any(_covered(w, r.get("words") or []) for w in spans[-1])]
    if not cands:
        return False, None
    _, _, run = max(cands, key=lambda c: (c[0], c[1]))
    return all(_covered(w, run.get("words") or []) for w in words), run


def prompt_score(labels: dict, runs: list[dict], says_ms: list[int], ear_closes: list[dict],
                 says: list[dict] | None = None, heard: list | None = None, eots: list | None = None) -> dict:
    """Per thought, on the prompts the manager actually built (`conv_run/input`):

    answering run  among the runs the thought's last span arrives in, the one holding most of its spans (the last on a
                   tie); none = its end never reached a prompt
    R2             with `heard` (the provider's words) and runs carrying their words: BY TIME — every word the
                   provider transcribed inside his spans is in the answering run's prompt (`r2_by_time`); a thought
                   with nothing transcribed is out of R2 (`r2` None). How well the provider transcribed each span is
                   its baseline (`heard_fz`, `heard_strict`, `heard_empty`), never a cut. Without them: every span
                   arrives by the tolerant text alignment. `r2_fz` (tolerant text) and `r2_strict` (exact text) are
                   kept beside it, for information
    R3             no line of ours starts between the thought's first onset and the end of its last span
    false cut      R2 or R3 broken; `cut_why` says which: `r2` (the thought never reached one prompt whole), `half` (a
                   line of the run that held part of THIS thought), `previous_late` (the answer to an earlier thought,
                   published while the person had already started this one)
    false merge    the answering prompt also carries a span of another thought of the person (a stranger is exposure)
    wait           the close of the ear intervention holding the last span − the instant the person finished
    wait (ear)     with `eots` (the provider's EndOfTurn arrivals, each with its words): that close − the EndOfTurn
                   that carries his last transcribed word — the ear's OWN time over what the provider already took;
                   profile A's wait (decided 2026-11-20). None when no EndOfTurn carries it
    say after end  our first line after the thought's last span ended − that end: what the person waits to hear
    exposure       stranger spans arriving in any prompt / stranger spans
    """
    prompts = [(r, words_of(" ".join(t for t in r["text"] if t))) for r in runs]
    user = [s for s in labels["segments"] if s["role"] == "user"]
    rows = []
    for t in labels["turns"]:
        spans = sorted((s for s in user if s["turn"] == t["turn"]), key=lambda s: s["start_ms"])
        last = spans[-1]
        lw = words_of(last["text"])
        sw = [words_of(s["text"]) for s in spans]
        # the answering run: among the runs the last span arrives in, the one holding MOST of the thought (the last on
        # a tie) — a short last span («en Valencia») can «arrive» in an unrelated prompt through one function word.
        # R2 in audio is the TOLERANT alignment (decided 2026-11-20: a word the STT misheard is the STT's fault, not a
        # cut by the ear); the frozen exact alignment is kept beside it as `r2_strict`, for information.
        def pick(fuzzy: bool):
            cands = [(sum(arrives(w, pw, fuzzy) for w in sw), i, r, pw) for i, (r, pw) in enumerate(prompts)
                     if arrives(lw, pw, fuzzy)]
            if not cands:
                return None, False
            _, _, run, pw = max(cands, key=lambda c: (c[0], c[1]))
            return run, all(arrives(w, pw, fuzzy) for w in sw)
        answering, r2_fz = pick(True)
        answering_strict, r2_strict = pick(False)
        r2 = r2_fz
        base = None
        if heard is not None and all("words" in r for r in runs):
            span_heard = [heard_in_span(labels, sg, heard) for sg in spans]
            r2, run_t = r2_by_time(span_heard, runs)
            answering = run_t or (answering if r2 is None else None)
            hw = [[w[0] for w in ws] for ws in span_heard]
            base = {"spans": len(spans), "empty": sum(not ws for ws in hw),
                    "fz": sum(bool(ws) and arrives(words_of(sg["text"]), words_of(" ".join(ws)), True)
                              for sg, ws in zip(spans, hw)),
                    "strict": sum(bool(ws) and arrives(words_of(sg["text"]), words_of(" ".join(ws)), False)
                                  for sg, ws in zip(spans, hw))}
        pw = words_of(" ".join(x for x in answering["text"] if x)) if answering else []
        spoke = sum(1 for ms in says_ms if t["start_ms"] <= ms < last["end_ms"])
        during = [x for x in (says or []) if t["start_ms"] <= x["t_ms"] < last["end_ms"]]
        span_words = [words_of(s["text"]) for s in spans]
        run_words = {r["run"]: w for r, w in prompts}
        half = any(any(arrives(w, run_words.get(x["run"], []), True) for w in span_words) for x in during)
        others = [s for s in user if s["turn"] != t["turn"]]
        merged = bool(answering) and any(present(words_of(s["text"]), pw) for s in others)
        holding = [c for c in ear_closes if any(last["start_ms"] - 150 <= int(w[2]) and int(w[1]) <= last["end_ms"] + 300
                                                for w in c["words"])]
        close = max((c for c in holding), key=lambda c: max(int(w[2]) for w in c["words"]))["end_ms"] if holding else None
        wait_ear = None
        if eots is not None and heard is not None and close is not None:
            his = [w for sg in spans for w in heard_in_span(labels, sg, heard)]
            if his:
                last_word = max(his, key=_mid)
                eot = min((e for e, ws in eots if _covered(last_word, ws)), default=None)
                wait_ear = (close - eot) if eot is not None else None
        first_after = min((ms for ms in says_ms if ms >= last["end_ms"]), default=None)
        r2_broken = r2 is False
        cut_why = None if (not r2_broken and not spoke) else ("half" if half else "previous_late" if spoke and during
                                                              else "r2" if r2_broken else "half")
        unclean = any(sg.get("cut_ok") is False for sg in spans)
        rows.append({"turn": t["turn"], "kind": t["kind"], "spans": len(spans), "r2": r2, "r2_fz": r2_fz,
                     "r2_strict": r2_strict, "heard": base,
                     "infra": unclean,
                     "spoke_during": spoke,
                     "cut_why": cut_why,
                     "say_after_end_ms": (first_after - last["end_ms"]) if first_after is not None else None,
                     "cut": r2_broken or spoke > 0, "merged": merged,
                     "answering_run": answering["run"] if answering else None,
                     "run_start_after_end_ms": (answering["t_ms"] - t["end_ms"]) if answering else None,
                     "wait_ms": (close - t["end_ms"]) if close is not None else None,
                     "wait_ear_ms": wait_ear,
                     "unclosed": close is None or close > labels["duration_ms"]})
    strangers = [s for s in labels["segments"] if s["role"] in STRANGERS and s["text"]]
    exposed = [s for s in strangers if any(present(words_of(s["text"]), pw) for _, pw in prompts)]
    return {"thoughts": rows, "exposure": [len(exposed), len(strangers)],
            "exposure_by_kind": {k: [sum(1 for s in exposed if s.get("stranger") == k),
                                     sum(1 for s in strangers if s.get("stranger") == k)]
                                 for k in ("narration", "question", "echo")}}


ALIGN_WINDOW_MS = 400
ALIGN_MIN = 0.80
ALIGN_MIN_WORDS = 5


def label_alignment(labels: dict, heard: list[list]) -> dict:
    """Do the labels sit on the audio? (node 13.81) A labelled word of the person that Flux heard SOMEWHERE must have
    been heard inside its span's window (± `ALIGN_WINDOW_MS`). R2 aligns by text and cannot see a label moved in
    time; this check can, and a flow that fails it is INFRA: nothing on it is scored."""
    matched = aligned = 0
    for s in labels["segments"]:
        if s["role"] != "user":
            continue
        for w in set(words_of(s["text"])):
            times = [(int(h[1]), int(h[2])) for h in heard if words_of(h[0]) == [w]]
            if not times:
                continue
            matched += 1
            aligned += any(s["start_ms"] - ALIGN_WINDOW_MS <= a and b <= s["end_ms"] + ALIGN_WINDOW_MS
                           for a, b in times)
    ratio = aligned / matched if matched else 0.0
    return {"matched": matched, "aligned": aligned, "ratio": round(ratio, 3),
            "ok": matched >= ALIGN_MIN_WORDS and ratio >= ALIGN_MIN}


TERMINAL_MARKS = (".", "?", "!", "…")
END_TOL_MS = 350


def flux_end_marks(labels: dict, raw: list[dict]) -> dict:
    """How Flux closed the person's pieces: for every `EndOfTurn` placed on his speech, did the thought GO ON after it
    or END there, and did the transcript close with a sentence mark? A pause cell whose «goes on» pieces mostly come
    with a mark is measuring pieces that sound finished (plan §5.2): it informs and does not decide."""
    out = {"goes_on": 0, "goes_on_terminal": 0, "ended": 0, "ended_terminal": 0}
    last_words: dict = {}
    for m in raw:
        x = m["msg"]
        if x.get("type") != "TurnInfo":
            continue
        if x.get("words"):
            last_words[x.get("turn_index")] = x["words"][-1]
        if x.get("event") != "EndOfTurn" or x.get("turn_index") not in last_words:
            continue
        w = last_words[x.get("turn_index")]
        w0, w1, text = int(round(1000 * w.get("start", w["end"]))), int(round(1000 * w["end"])), str(w.get("word") or "")
        who = match_word(labels, w0, w1, text)
        if who["role"] != "user":
            continue
        seg = next(s for s in labels["segments"] if s["i"] == who["seg"])
        spans = sorted((s for s in labels["segments"] if s["role"] == "user" and s["turn"] == seg["turn"]),
                       key=lambda s: s["start_ms"])
        ended = seg["i"] == spans[-1]["i"] and w1 >= spans[-1]["end_ms"] - END_TOL_MS
        key = "ended" if ended else "goes_on"
        out[key] += 1
        out[key + "_terminal"] += text.rstrip().endswith(TERMINAL_MARKS)
    return out
