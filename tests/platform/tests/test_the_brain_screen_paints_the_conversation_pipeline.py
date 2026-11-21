"""THE BRAIN screen, second picture: a flow that carries `conv_*` events is painted with the conversation package's
own stations (`CONV_STATIONS`: ear · inbox · compose · model · gateway · ledger · mouth · close) — the only picture
since the old turn's twelve went (INI-078 L1). A replayed session (`python -m conversation.replay <signals> --events`) is a source of its own:
`/api/replay?name=…&trace=…` paints one request of it, with the strip across every request.

What would rot: a conv flow painted with the old stations (every one dark); a station lit by another's kind; a request
that ran and never closed shown as healthy; a mouth event with no trace of its own lost from its request.
"""
from __future__ import annotations

import json
from pathlib import Path

from conversation.replay import Replay, load
from tests.platform import observatory_data as od
from tests.platform.tests.observatory_fixture import get, observatory, runs_root  # noqa: F401 — fixtures

S1 = Path(od.ENGINE) / "tests" / "conversation" / "fixtures" / "sessions" / "s1.jsonl"
KINDS = {"conv_ear": "ear", "conv_inbox": "inbox", "conv_effect": "gateway", "conv_ledger": "ledger",
         "conv_mouth": "mouth", "conv_close": "close"}


def _write_replay(root: Path, name: str = "s1") -> list[dict]:
    with open(S1, encoding="utf-8") as fh:
        events = Replay(load(fh)).run().observer_events()
    out = root / "conversation" / "replays"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{name}.events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
    return events


def _row(i: int, kind: str, label: str, **payload) -> dict:
    return {"id": i, "ts_ms": 1000 + 10 * i, "cat": "conversation", "kind": kind, "label": label, "span": "",
            "payload": json.dumps(payload)}


def test_the_picture_follows_the_package_and_each_kind_lights_its_own_station() -> None:
    assert [s["id"] for s in od.CONV_STATIONS] == ["ear", "inbox", "compose", "model", "gateway", "ledger", "mouth",
                                                  "close"]
    for s in od.CONV_STATIONS:
        assert (od.ENGINE / s["module"]).exists(), f"{s['module']} is not in the package any more"
    for kind, sid in KINDS.items():
        assert od._conv_station_of({"kind": kind, "label": "x"}) == sid
    assert od._conv_station_of({"kind": "conv_run", "label": "prompt"}) == "compose"
    assert od._conv_station_of({"kind": "conv_run", "label": "model_first_token"}) == "model"
    assert od._conv_station_of({"kind": "trace", "label": "turno"}) == ""


def test_a_conv_flow_is_painted_with_the_conversation_stations_and_an_unclosed_request_is_dark() -> None:
    rows = [_row(1, "conv_ear", "closed", closed_by="eot", words=["w1", "w2"]),
            _row(2, "conv_inbox", "accepted", surfacing="now"),
            _row(3, "conv_run", "started", reason="closed"), _row(4, "conv_run", "prompt", prompt_tokens=812)]
    f = od.light_flow(rows)
    st = {s["id"]: s for s in f["stations"]}
    assert set(st) == set(od.CONV_STATION_IDS) and f["order"] == ["ear", "inbox", "model", "compose"]
    assert st["ear"]["state"][0] == {"k": "closed", "v": "2 words · closed_by eot"}
    assert st["compose"]["state"][0]["v"] == "prompt_tokens 812"
    assert st["close"]["expected"] and "I-limbo" in st["close"]["why"][0]
    done = od.light_flow(rows + [_row(5, "conv_close", "answered", total_ms=900)])
    dark = [s["id"] for s in done["stations"] if s["expected"]]
    assert dark == ["mouth"]                                   # answered and the mouth said nothing
    old = od.light_flow([{**_row(1, "trace", "turno", text="hola"), "cat": "flash"}])
    assert [s["id"] for s in old["stations"]] == list(od.CONV_STATION_IDS) and not old["order"], \
        "a flow of the old turn has no picture of its own any more: nothing in it lights a station"


def test_a_replay_of_s1_is_painted_whole_on_the_brain_screen(observatory) -> None:  # noqa: F811
    _, root, url = observatory
    events = _write_replay(root)
    d = get(f"{url}/api/replay?name=s1")
    assert d["readable"] and d["replay"] == "s1" and d["corr_id"] == d["strip"][0]["corr_id"]
    assert d["order"][0] == "ear" and set(d["order"]) == set(od.CONV_STATION_IDS)
    assert not [s for s in d["stations"] if s["expected"]]
    assert d["heard"].startswith("w0001") and d["said"].endswith("chars")
    traces = {e["trace"] for e in events if e["trace"]}
    assert len(d["strip"]) == len(traces) and all(t["lit"] for t in d["strip"])
    last = d["strip"][-1]["corr_id"]
    one = get(f"{url}/api/replay?name=s1&trace={last}")
    assert one["corr_id"] == last and one["turn"] == len(traces) - 1
    rows = od.replay_rows(root, "s1")                                         # an event with a run has its trace
    assert all(r["corr_id"] for r in rows if (r["payload"].get("refs") or {}).get("run"))


def test_a_replay_is_read_by_name_never_by_path(observatory) -> None:  # noqa: F811
    _, root, url = observatory
    assert get(f"{url}/api/replay?name=nothing")["readable"] is False
    import urllib.error
    try:
        get(f"{url}/api/replay?name=..%2F..%2Fetc")
        raise AssertionError("a path was accepted as a replay name")
    except urllib.error.HTTPError as e:
        assert e.code == 400
