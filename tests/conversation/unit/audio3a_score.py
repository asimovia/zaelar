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
        key = (sim, 1 if seg["role"] in ("user", "other") else 0, ov) if (sim or ov) else (0.0, 0, 0)
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
        strangers = sum(1 for r in roles if r["role"] in ("other", "tv"))
        noise = sum(1 for r in roles if r["role"] == "noise")
        crosstalk_words += strangers
        noise_words += noise
        if u["words"] and not user_turns and strangers:
            crosstalk_units += 1
        if user_turns and strangers:
            merged_with_stranger += 1
        exposed |= {r["seg"] for r in roles if r["role"] in ("other", "tv")}
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
        "exposure": [len(exposed), sum(1 for g in labels["segments"] if g["role"] in ("other", "tv"))],
        "crosstalk_words": crosstalk_words, "crosstalk_units": crosstalk_units, "noise_words": noise_words,
        "lost_turns": sum(1 for r in rows if r["lost"]),
        "unclosed_turns": sum(1 for r in rows if r["unclosed"]),
        "eot_delay_ms": delays,
        "turns": rows, "unit_rows": unit_rows,
    }
