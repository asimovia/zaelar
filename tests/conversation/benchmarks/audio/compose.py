"""A scenario spec → one 16 kHz mono stream + its ground truth.

A spec is a dict (see `scenarios.py`):

    {"id": "...", "lang": "es", "noise_db": -55,
     "items": [
        {"say": "es_a", "text": "...", "role": "user", "turn": 1},                 # placed after the previous item
        {"say": "es_a", "text": "...", "role": "user", "turn": 1, "gap_ms": 1200}, # a pause INSIDE turn 1
        {"say": "es_b", "text": "...", "role": "other", "gap_ms": -400, "gain_db": -6},  # overlaps by 400 ms
        {"say": "es_a", "text": "...", "role": "user", "turn": 2, "cut_s": 0.9},   # cut off mid-sentence
        {"cough": 1, "gap_ms": 300},
        {"tv": "es_tv", "texts": ["...", "..."], "at_ms": 0, "until_ms": 9000, "gain_db": -20},
     ]}

Placement: an item starts `gap_ms` after the END of the previous foreground item (negative = overlap), or at
`at_ms` when given. Background items (`tv`, `noise`) never move the cursor. Roles: `user` (the person the agent
serves — the only role whose words should reach the agent), `other` (a second person in the room), `tv`, `cough`.

The label file says, for every segment, who spoke what and when (with per-word times when the voice gives them),
and for every user TURN where it truly ends — the instant the person finished, which is what an end-of-turn
detector is scored against. A cut-off turn ends where its audio stops. Each segment also says whether it `continues` the person's previous
segment of the same thought, and, for a stranger, its kind (`narration` or `question`). With `"calibrate": true` the
stream starts and ends with the labelled calibration phrase (role `calibration`, never scored).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from tests.conversation.benchmarks.audio import voices as V

RATE = V.RATE
LEAD_MS = 700
#: The clock-calibration phrase of level 3b (plan §5.2): said at the start and the end of a stream, labelled, so the
#: offset between the WAV's clock and the engine's events is read from its onset at both ends. A voice with per-word
#: times, so its onset is exact.
CALIBRATION_TEXT = "Calibration mark, one two three."
CALIBRATION_VOICE = "inworld:Dennis"
CALIBRATION_GAP_MS = 2500
TAIL_MS = 4000


def _db(gain_db: float) -> float:
    return float(10 ** (gain_db / 20))


def _fade(x: np.ndarray, ms: int = 25) -> np.ndarray:
    n = min(len(x) // 2, RATE * ms // 1000)
    if n > 0:
        x = x.copy()
        x[-n:] *= np.linspace(1.0, 0.0, n, dtype=np.float32)
    return x


def _pink(n: int, rng: np.random.Generator) -> np.ndarray:
    white = rng.standard_normal(n)
    f = np.fft.rfft(white)
    f[1:] /= np.sqrt(np.arange(1, len(f)))
    x = np.fft.irfft(f, n)
    return (x / (np.sqrt(np.mean(x ** 2)) + 1e-9)).astype(np.float32)


def _cough(rng: np.random.Generator) -> np.ndarray:
    """Two or three bursts of band-passed noise with a fast attack: a cough, as an ear hears it — loud, not speech."""
    from scipy.signal import butter, sosfilt
    sos = butter(4, [250, 3500], btype="band", fs=RATE, output="sos")
    parts = []
    for i in range(int(rng.integers(2, 4))):
        n = int(RATE * rng.uniform(0.12, 0.2))
        env = np.exp(-np.linspace(0, 6, n)) * np.minimum(1, np.linspace(0, 25, n))
        burst = sosfilt(sos, rng.standard_normal(n)) * env
        parts += [burst, np.zeros(int(RATE * rng.uniform(0.06, 0.12)))]
    x = np.concatenate(parts).astype(np.float32)
    return 0.5 * x / (np.max(np.abs(x)) + 1e-9)


def _rms_norm(x: np.ndarray, rms: float = 0.08) -> np.ndarray:
    r = float(np.sqrt(np.mean(x ** 2))) if len(x) else 0.0
    return x * (rms / r) if r > 0 else x



CUT_SEARCH_MS = 40       # the cut moves to the quietest 10 ms within this of the word boundary the voice gives
CUT_FADE_MS = 15         # a cosine fade on each side of the inserted silence: no click for the VAD or the STT
CUT_MAX_RATIO = 0.5      # a cut whose 20 ms on either side are louder than this share of the speech is not clean


def _norm_token(w: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", str(w).lower())
    return "".join(ch for ch in t if ch.isalnum())


def _split_points(words: list, pieces: list[str]) -> list[int] | None:
    """The index of the last aligned word of each piece but the last, or None when the voice's words cannot be laid
    over the pieces (then the flow is INFRA)."""
    idx, out = -1, []
    for piece in pieces[:-1]:
        toks = [_norm_token(t) for t in piece.split() if _norm_token(t)]
        if not toks:
            return None
        want = idx + len(toks)
        hit = next((j for j in (want, want - 1, want + 1, want - 2, want + 2)
                    if 0 <= j < len(words) - 1 and _norm_token(words[j][0]) == toks[-1]), None)
        if hit is None:
            return None
        out.append(hit)
        idx = hit
    return out


def _cut_at(x: np.ndarray, t_s: float) -> int:
    """The quietest 10 ms frame centre within CUT_SEARCH_MS of `t_s`."""
    frame, c = RATE // 100, int(t_s * RATE)
    lo, hi = max(frame, c - RATE * CUT_SEARCH_MS // 1000), min(len(x) - frame, c + RATE * CUT_SEARCH_MS // 1000)
    if hi <= lo:
        return max(0, min(len(x), c))
    cands = range(lo, hi, frame // 2)
    # the quietest; among equally quiet ones the nearest to the boundary (a silent gap is cut in its middle)
    return min(cands, key=lambda k: (round(float(np.sqrt(np.mean(x[k - frame // 2: k + frame // 2] ** 2))), 5),
                                     abs(k - c)))


def _energy_ratio(x: np.ndarray, k: int, speech: float) -> float:
    w = RATE // 50
    around = max(float(np.sqrt(np.mean(x[max(0, k - w): k] ** 2))) if k > 0 else 0.0,
                 float(np.sqrt(np.mean(x[k: k + w] ** 2))) if k < len(x) else 0.0)
    return around / speech


def split_thought(x: np.ndarray, words: list, pieces: list[str]) -> tuple[list, list[dict], list[str]] | None:
    """ONE utterance of a whole thought → its pieces, cut at word boundaries (plan §5.2). Each cut takes the quietest
    of the scripted boundary and its two neighbours (a person stops between words, and in fluent speech most boundaries
    are voiced), then the quietest 10 ms within 40 ms of it; a fade on each cut side. Returns each part's audio and its
    words, a check per cut (the energy 20 ms around it against the speech's: ≤ CUT_MAX_RATIO is clean) and the pieces'
    texts as finally cut. None when the voice's words cannot be laid over the pieces."""
    pts = _split_points(words, pieces)
    if pts is None:
        return None
    frame = RATE // 100
    energies = [float(np.sqrt(np.mean(x[k: k + frame] ** 2))) for k in range(0, len(x) - frame, frame)]
    voiced = sorted(e for e in energies if e > 0.1 * max(energies)) or [1e-9]
    speech = voiced[len(voiced) // 2]
    chosen, cuts, checks, prev = [], [], [], -1
    for n, j in enumerate(pts):
        nxt = pts[n + 1] if n + 1 < len(pts) else len(words) - 1
        options = [c for c in (j - 1, j, j + 1) if prev < c < nxt]
        best = None
        for c in options:
            k = _cut_at(x, (float(words[c][2]) + float(words[c + 1][1])) / 2)
            r = _energy_ratio(x, k, speech)
            if best is None or r < best[2] - 1e-9 or (abs(r - best[2]) < 1e-9 and c == j):
                best = (c, k, r)
        c, k, r = best
        chosen.append(c)
        cuts.append(k)
        prev = c
        checks.append({"at_ms": round(1000 * k / RATE), "ratio": round(r, 3), "ok": r <= CUT_MAX_RATIO,
                       "moved_words": c - j})
    bounds = [0] + cuts + [len(x)]
    fade = RATE * CUT_FADE_MS // 1000
    parts, texts, wi = [], [], 0
    for n in range(len(pieces)):
        a, b = bounds[n], bounds[n + 1]
        part = x[a:b].copy()
        if n > 0 and len(part) > 2 * fade:
            part[:fade] *= np.linspace(0.0, 1.0, fade, dtype=np.float32) ** 2
        if n < len(pieces) - 1 and len(part) > 2 * fade:
            part[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32) ** 2
        t0 = a / RATE
        last = chosen[n] if n < len(chosen) else len(words) - 1
        mine = [(w, max(0.0, float(s) - t0), max(0.0, min(float(e), b / RATE) - t0)) for w, s, e in words[wi:last + 1]]
        texts.append(" ".join(w for w, _, _ in words[wi:last + 1]))
        wi = last + 1
        parts.append((part, mine))
    return parts, checks, texts


def _expand(items: list[dict]) -> tuple[list[dict], list[dict], bool]:
    """A `split` item (a thought said as ONE utterance with its pauses inserted) → one `part` item per piece."""
    out, checks, broken = [], [], False
    for it in items:
        if "split" not in it:
            out.append(it)
            continue
        u = V.utter(it["split"], " ".join(it["pieces"]))
        res = split_thought(_rms_norm(u.audio), list(u.words), it["pieces"])
        if res is None:                                     # the voice's words do not lay over the pieces
            broken = True
            out.append({k: v for k, v in it.items() if k not in ("split", "pieces", "pauses")}
                       | {"say": it["split"].replace("elevenlabs_ts:", "elevenlabs:"), "text": " ".join(it["pieces"])})
            continue
        parts, cut_checks, texts = res
        checks += cut_checks
        for n, ((audio, words), piece) in enumerate(zip(parts, texts)):
            out.append({"part": audio, "words": words, "text": piece, "voice": u.voice, "say": it["split"],
                        "cut_check": cut_checks[n - 1] if n > 0 else None,
                        "role": it.get("role", "user"), "turn": it.get("turn"), "continues": n > 0,
                        "gap_ms": it.get("gap_ms", 0) if n == 0 else it["pauses"][n - 1]})
    return out, checks, broken


def compose(spec: dict, out_dir: Path) -> tuple[Path, Path]:
    """Render the spec; returns (wav path, labels path)."""
    rng = np.random.default_rng(int(hashlib.sha1(spec["id"].encode()).hexdigest()[:8], 16))
    placed: list[tuple[int, np.ndarray, dict]] = []      # (start sample, audio, segment label)
    cursor = LEAD_MS * RATE // 1000
    items = list(spec["items"])
    if spec.get("calibrate"):                             # 3b: a labelled phrase at both ends aligns the two clocks
        cal = {"say": CALIBRATION_VOICE, "text": CALIBRATION_TEXT, "role": "calibration"}
        items = [dict(cal)] + items + [dict(cal, gap_ms=CALIBRATION_GAP_MS)]
        items[1] = dict(items[1], gap_ms=max(items[1].get("gap_ms", 0), CALIBRATION_GAP_MS))
    items, cut_checks, split_broken = _expand(items)
    for i, it in enumerate(items):
        if "tv" in it:
            continue
        if "part" in it:
            x, words = it["part"], list(it["words"])
            seg = {"role": it["role"], "speaker": it["say"], "voice": it["voice"], "text": it["text"],
                   "turn": it.get("turn"), "cut": False, "lang": spec.get("lang"), "continues": it["continues"],
                   "stranger": None, "one_utterance": True,
                   "cut_ok": (it["cut_check"] or {}).get("ok", True),
                   "cut_ratio": (it["cut_check"] or {}).get("ratio")}
        elif "say" in it:
            u = V.utter(it["say"], it["text"])
            x = _rms_norm(u.audio)
            words = list(u.words)
            cut = it.get("cut_s")
            if cut is not None:
                x = _fade(x[: int(cut * RATE)])
                words = [w for w in words if w[1] < cut]
                words = [(w, s, min(e, cut)) for w, s, e in words]
            text = it["text"]
            if cut is not None:                           # the label says what was SAID, not what was scripted
                text = (" ".join(w for w, _, _ in words) if u.words else
                        " ".join(text.split()[: max(1, round(len(text.split()) * min(1.0, cut / u.seconds)))]))
            seg = {"role": it.get("role", "user"), "speaker": it["say"], "voice": u.voice, "text": text,
                   "turn": it.get("turn"), "cut": cut is not None, "lang": it.get("lang", spec.get("lang")),
                   "continues": bool(it.get("continues")), "stranger": it.get("stranger")}
        elif "cough" in it:
            x, words = _cough(rng), []
            seg = {"role": "cough", "speaker": "cough", "voice": "", "text": "", "turn": None, "cut": False,
                   "continues": False, "stranger": None}
        else:
            raise ValueError(f"item {i}: unknown kind {sorted(it)}")
        x = x * _db(it.get("gain_db", 0.0))
        start = it["at_ms"] * RATE // 1000 if "at_ms" in it else cursor + it.get("gap_ms", 0) * RATE // 1000
        start = max(0, start)
        seg["words_rel"] = words
        placed.append((start, x, seg))
        cursor = max(cursor, start + len(x))
    end = max(s + len(x) for s, x, _ in placed) + TAIL_MS * RATE // 1000
    for it in items:                                      # background speech: a bed of utterances
        if "tv" not in it:
            continue
        a = it.get("at_ms", 0) * RATE // 1000
        b = min(end, it.get("until_ms", end * 1000 // RATE) * RATE // 1000)
        t = a
        k = 0
        while t < b:
            text = it["texts"][k % len(it["texts"])]
            u = V.utter(it["tv"], text)
            x = _rms_norm(u.audio)[: max(0, b - t)] * _db(it.get("gain_db", -20.0))
            placed.append((t, x, {"role": "tv", "speaker": it["tv"], "voice": u.voice, "text": text, "turn": None,
                                  "cut": len(x) < len(u.audio), "continues": False,
                                  "stranger": it.get("stranger", "narration"), "words_rel": list(u.words)}))
            t += len(x) + int(RATE * 0.35)
            k += 1
    mix = np.zeros(end, dtype=np.float32)
    for s, x, _ in placed:
        mix[s: s + len(x)] += x
    if spec.get("noise_db") is not None:
        mix += _pink(end, rng) * _db(spec["noise_db"])
    peak = float(np.max(np.abs(mix)))
    if peak > 0.95:
        mix *= 0.95 / peak

    segments = []
    for s, x, seg in sorted(placed, key=lambda p: p[0]):
        t0 = s * 1000 // RATE
        seg = dict(seg)
        rel = seg.pop("words_rel")
        seg.update(start_ms=t0, end_ms=t0 + len(x) * 1000 // RATE,
                   words=[[w, t0 + round(a * 1000), t0 + round(b * 1000)] for w, a, b in rel])
        segments.append(seg)
    for i, seg in enumerate(segments):
        seg["i"] = i
    turns = []
    for t in sorted({s["turn"] for s in segments if s["role"] == "user" and s["turn"] is not None}):
        mine = [s for s in segments if s["role"] == "user" and s["turn"] == t]
        last = max(mine, key=lambda s: s["end_ms"])
        end_ms = last["words"][-1][2] if last["words"] else last["end_ms"]
        turns.append({"turn": t, "start_ms": min(s["start_ms"] for s in mine), "end_ms": min(end_ms, last["end_ms"]),
                      "kind": "cut_off" if last["cut"] else "complete", "segments": [s["i"] for s in mine],
                      "text": " ".join(s["text"] for s in sorted(mine, key=lambda s: s["start_ms"]))})
    labels = {"id": spec["id"], "lang": spec.get("lang"), "rate": RATE, "duration_ms": end * 1000 // RATE,
              "description": spec.get("description", ""), "segments": segments, "turns": turns}
    if cut_checks or split_broken:
        labels["one_utterance"] = {"cuts": cut_checks, "words_laid": not split_broken,
                                   "clean": not split_broken and all(c["ok"] for c in cut_checks)}
    out_dir.mkdir(parents=True, exist_ok=True)
    wav, lab = out_dir / f"{spec['id']}.wav", out_dir / f"{spec['id']}.labels.json"
    V.write_wav(wav, mix)
    lab.write_text(json.dumps(labels, ensure_ascii=False, indent=1), encoding="utf-8")
    return wav, lab
