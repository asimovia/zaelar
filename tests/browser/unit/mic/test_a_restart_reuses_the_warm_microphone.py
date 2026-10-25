"""A session restart takes the microphone back instead of asking for it again (2026-10-26, node 4.272).

The operator, on an iPhone home-screen app: «cada vez que entro en el agente me pide el permiso del micrófono… se lo
quisiera dar una vez y ya». Every start() called getUserMedia and every stop() — plus LiveKit's own disconnect, which
stops local tracks by default — killed the track, and a phone runs stop→start constantly (the reconnect after the
screen locks, the voice taken back, ⏻). The stream is now PARKED warm for a few seconds and taken back by the next
start with the same constraints. Read from the source because the module needs a browser and a LiveKit room.
"""
import re
from pathlib import Path

SRC = (Path(__file__).resolve().parents[4] / "frontend/app/services/session-lk.js").read_text()


def _fn(name: str) -> str:
    m = re.search(rf"(?:export )?(?:async )?function {name}\(.*?\n}}\n", SRC, re.S)
    assert m, f"{name} not found"
    return m.group(0)


def test_start_takes_the_warm_stream_before_asking_the_browser():
    start = _fn("start")
    take, ask = start.find("_takeWarm("), start.find("getUserMedia(")
    assert 0 <= take < ask, "start() must try the parked stream before a new getUserMedia"
    assert re.search(r"warm \|\| await navigator\.mediaDevices\.getUserMedia", start)


def test_stop_parks_the_stream_and_livekit_does_not_kill_it():
    stop = _fn("stop")
    assert "_parkMic(stream" in stop, "stop() must park the stream, not stop its tracks"
    assert "room.disconnect(false)" in stop, "LiveKit stops local tracks on disconnect unless told not to"
    assert not re.search(r"stream\.getTracks\(\)\.forEach\(t => t\.stop\(\)\)", stop)


def test_the_warm_window_is_short_and_leaving_the_page_releases_it():
    ms = int(re.search(r"const _WARM_MS = (\d+);", SRC).group(1))
    assert 1000 <= ms <= 10000, "the recording indicator must not outlive a stopped agent by more than seconds"
    assert re.search(r'addEventListener\("pagehide", _releaseWarm\)', SRC)
    assert "_warmKey === key" in _fn("_takeWarm"), "another device or capture mode must never get the old stream"
