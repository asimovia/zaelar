"""V2-802 T-08 — the words before the wake word are his only when the paid STT could not hear them.

Measured live: the browser's free recogniser keeps listening while the agent's voice plays, so the reply the
agent had just spoken («the draft to … I'll pick it up now, shall I send…») sat in its tail. He then said «show
it to me first, <name>»; the spot sent that tail as `before`, the engine glued it in front of the paid STT's
transcript, and memory stored the agent's sentence as HIS. The paid STT had been listening the whole time, so the
pre-roll added nothing true.

The rule: the pre-roll exists for a PARKED tap. The browser says whether the tap was parked when the name was
heard, and the engine drops `before` when it was not. An old client that sends no flag keeps the old contract.

Disarm: remove the engine's `parked is False` drop, or stop sending `parked` from the spot, and this goes red.
"""

from pathlib import Path

from tests import voice_turn_source as _vts

ROOT = Path(__file__).resolve().parents[4]
SESSION = ROOT / "frontend" / "app" / "services" / "session-lk.js"
EVENTS = ROOT / "voice" / "engine" / "pipeline" / "agent_events.py"


def _src(p: Path) -> str:
    assert p.exists(), f"{p} is gone — the seam moved and this test has to move with it"
    return _vts.read(p)


def test_the_spot_reads_the_park_state_before_it_opens_the_tap():
    s = _src(SESSION)
    spot = s.split("onSpot: (spot) => {", 1)[1].split("\n    },", 1)[0]
    i_read, i_open = spot.find("const parked = tapParked();"), spot.find("setTapParked(false)")
    assert i_read != -1, "the spot must capture whether the paid STT was hearing BEFORE it unparks"
    assert i_open != -1 and i_read < i_open, "read after the unpark, the flag would always say «open»"
    assert "sendWake({ ...spot, parked })" in spot


def test_the_wake_packet_carries_the_park_state_and_defaults_to_parked():
    s = _src(SESSION)
    send = s.split("export function sendWake(spot) {", 1)[1].split("\n}", 1)[0]
    assert "{ t: \"zaelar-wake\", phase, text, before, parked }" in send
    assert "spot.parked === false" in send, "only an explicit «open» drops the pre-roll; unknown keeps it"


def test_the_engine_drops_the_preroll_when_the_paid_stt_was_listening():
    s = _src(EVENTS)
    wake = s.split('if topic == "zaelar-wake":', 1)[1].split("except Exception as we", 1)[0]
    i_drop = wake.find('if _d.get("parked") is False:')
    assert i_drop != -1, "the engine must read the park state the browser sent"
    assert wake[i_drop:i_drop + 120].count('_before = ""') == 1
    assert i_drop < wake.find("_attn_wake.note_preroll(_before)"), "the drop must happen before any pre-roll is noted"
