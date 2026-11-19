"""F0 probe: what Deepgram Flux actually sends, raw, with its arrival times — and what the pinned plugin keeps of it.

    ./.venv/bin/python -m tests.conversation.benchmarks.flux_probe <audio.wav> --out raw.jsonl [--cut-at-s 4.0]
    ./.venv/bin/python -m tests.conversation.benchmarks.flux_probe <audio.wav> --out plugin.jsonl --through-plugin
    ./.venv/bin/python -m tests.conversation.benchmarks.flux_probe --summarize raw.jsonl [--plugin plugin.jsonl]

Raw mode opens the Flux websocket with the configuration of the engine's ear (`voice/engine/speech/stt/deepgram.py`:
model, `eot_threshold`, `eager_eot_threshold`, `eot_timeout_ms`, read from the same settings), streams a 16 kHz mono
PCM16 WAV in 20 ms frames AT REAL TIME, and writes EVERY message as it arrived, with `arrived_ms` (monotonic, from
the first frame sent) and `sent_through_ms` (audio sent so far). `--cut-at-s` stops sending at that point WITHOUT a
close message and keeps listening for `--tail-s` seconds: the stalled-stream case (question A6).
`--through-plugin` streams the same audio through `livekit.plugins.deepgram.STTv2` and writes the `SpeechEvent`s it
emits, so the two files can be compared field by field. `--summarize` answers questions A1–A6 of the adapter doc in
numbers: no transcript text is printed.

The key is read from the credential store into memory (or `DEEPGRAM_API_KEY`), never printed or written. The output
files carry real speech when the audio is real speech: they are for the machine that ran the probe and are NEVER
committed. The probe sends no audio anywhere but Deepgram.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import wave
from pathlib import Path
from urllib.parse import urlencode

FRAME_MS = 20
FLUX_URL = "wss://api.deepgram.com/v2/listen"


def _key(store: Path | None) -> str:
    if store is not None:
        for line in store.read_text(encoding="utf-8").splitlines():
            name, _, value = line.partition("=")
            if name.strip() == "DEEPGRAM_API_KEY":
                return value.strip().strip('"').strip("'")
    if os.environ.get("DEEPGRAM_API_KEY"):
        return os.environ["DEEPGRAM_API_KEY"]
    from config import credentials   # the engine's store, read in memory
    return credentials.get("DEEPGRAM_API_KEY")


def ear_config() -> dict:
    """The engine ear's Flux options, from the same settings it reads."""
    from voice.engine.core.config import SETTINGS
    opts = {"model": SETTINGS.stt_model_deepgram, "eot_threshold": SETTINGS.stt_eot_threshold,
            "eot_timeout_ms": SETTINGS.stt_eot_timeout_ms}
    if SETTINGS.stt_eager_eot > 0:
        opts["eager_eot_threshold"] = min(SETTINGS.stt_eager_eot, SETTINGS.stt_eot_threshold)
    return opts


def _frames(path: Path) -> tuple[int, list[bytes]]:
    with wave.open(str(path), "rb") as w:
        if w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise SystemExit("the probe takes mono 16-bit PCM WAV")
        rate = w.getframerate()
        per = rate * FRAME_MS // 1000
        out = []
        while chunk := w.readframes(per):
            out.append(chunk)
    return rate, out


async def raw(audio: Path, out: Path, *, key: str, cut_at_s: float | None, tail_s: float) -> None:
    import aiohttp
    rate, frames = _frames(audio)
    params = {**ear_config(), "encoding": "linear16", "sample_rate": rate}
    url = f"{FLUX_URL}?{urlencode(params)}"
    t0 = time.monotonic()
    sent = {"ms": 0}

    async with aiohttp.ClientSession() as http, http.ws_connect(url, headers={"Authorization": f"Token {key}"}) as ws:
        with open(out, "w", encoding="utf-8") as fh:
            async def send() -> None:
                for i, frame in enumerate(frames):
                    if cut_at_s is not None and i * FRAME_MS >= cut_at_s * 1000:
                        return
                    await ws.send_bytes(frame)
                    sent["ms"] = (i + 1) * FRAME_MS
                    await asyncio.sleep(max(0.0, t0 + sent["ms"] / 1000 - time.monotonic()))
                await ws.send_str(json.dumps({"type": "CloseStream"}))

            async def recv() -> None:
                async for msg in ws:
                    if msg.type != aiohttp.WSMsgType.TEXT:
                        continue
                    fh.write(json.dumps({"arrived_ms": round((time.monotonic() - t0) * 1000, 1),
                                         "wall_ms": int(time.time() * 1000), "sent_through_ms": sent["ms"],
                                         "msg": json.loads(msg.data)}) + "\n")
                    fh.flush()

            receiver = asyncio.create_task(recv())
            await send()
            try:
                await asyncio.wait_for(receiver, timeout=tail_s)
            except asyncio.TimeoutError:
                receiver.cancel()


async def through_plugin(audio: Path, out: Path, *, key: str) -> None:
    import aiohttp
    from livekit import rtc
    from livekit.plugins import deepgram
    rate, frames = _frames(audio)
    cfg = ear_config()
    t0 = time.monotonic()
    async with aiohttp.ClientSession() as http:
        stt = deepgram.STTv2(model=cfg["model"], sample_rate=rate, api_key=key, http_session=http,
                             eot_threshold=cfg["eot_threshold"], eot_timeout_ms=cfg["eot_timeout_ms"],
                             **({"eager_eot_threshold": cfg["eager_eot_threshold"]}
                                if "eager_eot_threshold" in cfg else {}))
        stream = stt.stream()

        async def push() -> None:
            for i, frame in enumerate(frames):
                n = len(frame) // 2
                stream.push_frame(rtc.AudioFrame(frame, rate, 1, n))
                await asyncio.sleep(max(0.0, t0 + (i + 1) * FRAME_MS / 1000 - time.monotonic()))
            stream.end_input()

        pusher = asyncio.create_task(push())
        with open(out, "w", encoding="utf-8") as fh:
            async for ev in stream:
                alt = ev.alternatives[0] if ev.alternatives else None
                fh.write(json.dumps({
                    "arrived_ms": round((time.monotonic() - t0) * 1000, 1), "type": str(ev.type),
                    "start_time": getattr(alt, "start_time", None), "end_time": getattr(alt, "end_time", None),
                    "words": [[w.start_time, w.end_time, w.confidence] for w in (getattr(alt, "words", None) or [])],
                    "text": getattr(alt, "text", None)}) + "\n")
        await pusher


def summarize(raw_path: Path, plugin_path: Path | None = None) -> dict:
    """A1–A6 in numbers, read from a raw dump (and optionally a plugin dump). No text."""
    msgs = [json.loads(line) for line in raw_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    turns = [m for m in msgs if m["msg"].get("type") == "TurnInfo"]
    events: dict[str, int] = {}
    for m in turns:
        events[m["msg"].get("event", "?")] = events.get(m["msg"].get("event", "?"), 0) + 1
    words = [w for m in turns for w in (m["msg"].get("words") or [])]
    with_times = sum(1 for w in words if "start" in w and "end" in w)
    ends = [m["msg"].get("audio_window_end") for m in turns]
    advancing = sum(1 for a, b in zip(ends, ends[1:]) if a is not None and b is not None and b > a)
    gaps = [b["arrived_ms"] - a["arrived_ms"] for a, b in zip(turns, turns[1:])]
    conf_present = sum(1 for m in turns if "end_of_turn_confidence" in m["msg"])
    rewritten = 0
    last: list[str] = []
    for m in turns:
        cur = [w.get("word") for w in (m["msg"].get("words") or [])]
        if last and cur[:len(last)] != last and m["msg"].get("event") != "StartOfTurn":
            rewritten += 1
        last = [] if m["msg"].get("event") == "EndOfTurn" else cur
    lag = [m["arrived_ms"] - 1000 * float(m["msg"]["audio_window_end"])
           for m in turns if m["msg"].get("audio_window_end") is not None]
    report = {
        "messages": len(msgs), "turn_info": len(turns), "events": events,
        "A1_words": len(words), "A1_words_with_start_end": with_times,
        "A2_window_end_advances": advancing, "A2_cadence_ms": _pct(gaps),
        "A3_eot_confidence_present": conf_present, "A3_turn_index_present":
            sum(1 for m in turns if "turn_index" in m["msg"]),
        "A4_updates_that_rewrite_given_words": rewritten,
        "A5_arrival_minus_window_end_ms": _pct(lag),
        "A6_last_message_after_audio_ms": (msgs[-1]["arrived_ms"] - msgs[-1]["sent_through_ms"]) if msgs else None,
    }
    if plugin_path is not None:
        pev = [json.loads(line) for line in plugin_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        report["plugin_events"] = {t: sum(1 for e in pev if e["type"] == t) for t in sorted({e["type"] for e in pev})}
        report["plugin_words_with_nonzero_times"] = sum(1 for e in pev for w in e["words"] if w[0] or w[1])
    return report


def _pct(xs: list[float]) -> dict:
    if not xs:
        return {"n": 0}
    s = sorted(xs)
    return {"n": len(s), "p50": s[len(s) // 2], "p95": s[min(len(s) - 1, int(len(s) * 0.95))], "max": s[-1]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("audio", type=Path, nargs="?")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--through-plugin", action="store_true")
    ap.add_argument("--cut-at-s", type=float)
    ap.add_argument("--tail-s", type=float, default=8.0)
    ap.add_argument("--store", type=Path, help="credential store file to read the key from (in memory)")
    ap.add_argument("--summarize", type=Path)
    ap.add_argument("--plugin", type=Path)
    args = ap.parse_args(argv)
    if args.summarize:
        json.dump(summarize(args.summarize, args.plugin), sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0
    if not (args.audio and args.out):
        ap.error("audio and --out are required unless --summarize")
    key = _key(args.store)
    if not key:
        raise SystemExit("no DEEPGRAM_API_KEY in the credential store")
    if args.through_plugin:
        asyncio.run(through_plugin(args.audio, args.out, key=key))
    else:
        asyncio.run(raw(args.audio, args.out, key=key, cut_at_s=args.cut_at_s, tail_s=args.tail_s))
    return 0


if __name__ == "__main__":
    sys.exit(main())
