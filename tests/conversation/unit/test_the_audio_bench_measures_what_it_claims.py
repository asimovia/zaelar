"""The audio bench (level 3a) proves its own instrument: every measure goes red on a record that breaks it and green on
one that does not, a cell with nothing evaluated is INFRA, and labels moved off the audio make the flow INFRA.

No network, no Flux, no voices: the records are synthetic, the composer runs on a stub voice.
"""
from __future__ import annotations

import json

import numpy as np
import pytest

from tests.conversation.benchmarks.audio import compose as C
from tests.conversation.benchmarks.audio import probe as P
from tests.conversation.benchmarks.audio import score as S


def _seg(i, role, turn, start, end, text, stranger=None):
    return {"i": i, "role": role, "turn": turn, "start_ms": start, "end_ms": end, "text": text, "words": [],
            "cut": False, "stranger": stranger}


LABELS = {
    "duration_ms": 20_000,
    "segments": [
        _seg(0, "user", 1, 1000, 2500, "what does the share do on fridays"),
        _seg(1, "user", 1, 3500, 4500, "over the last thirty"),
        _seg(2, "other", None, 5000, 6000, "did you feed the cat", "question"),
        _seg(3, "user", 2, 9000, 10000, "and how many went down"),
    ],
    "turns": [{"turn": 1, "start_ms": 1000, "end_ms": 4500, "kind": "complete", "segments": [0, 1]},
              {"turn": 2, "start_ms": 9000, "end_ms": 10000, "kind": "complete", "segments": [3]}],
}
T1 = "what does the share do on fridays over the last thirty"
T2 = "and how many went down"


def _ear(*units):
    return [{"end_ms": end, "words": words} for end, words in units]


EAR = _ear((4900, [["thirty", 4300, 4500]]), (10400, [["down", 9800, 10000]]))


def test_a_span_arrives_at_seventy_percent_and_a_short_one_at_all_but_one():
    span = S.words_of("one two three four five six seven eight nine ten")
    assert S.arrives(span, span[:7])
    assert not S.arrives(span, span[:6])
    short = S.words_of("how many down")
    assert S.arrives(short, ["how", "down"])
    assert not S.arrives(short, ["down"])
    assert S.words_of("¿Cuántas, BAJA?") == ["cuántas", "baja"]        # case and punctuation go, accents stay


def test_a_thought_whole_in_one_prompt_with_nothing_said_before_is_not_a_cut():
    runs = [{"run": "r1", "t_ms": 4900, "text": [T1]}, {"run": "r2", "t_ms": 10400, "text": [T2]}]
    rows = S.prompt_score(LABELS, runs, [5200, 10700], EAR)["thoughts"]
    assert [r["cut"] for r in rows] == [False, False] and [r["merged"] for r in rows] == [False, False]
    assert rows[0]["wait_ms"] == 400 and rows[1]["wait_ms"] == 400


def test_a_thought_whose_last_span_never_reaches_a_prompt_is_a_cut():
    runs = [{"run": "r1", "t_ms": 2900, "text": ["what does the share do on fridays"]},
            {"run": "r2", "t_ms": 10400, "text": [T2]}]
    rows = S.prompt_score(LABELS, runs, [], EAR)["thoughts"]
    assert rows[0]["cut"] and not rows[0]["r2"] and not rows[1]["cut"]


def test_a_thought_answered_in_two_prompts_is_a_cut_even_if_the_last_holds_the_end():
    runs = [{"run": "r1", "t_ms": 2900, "text": ["what does the share do on fridays"]},
            {"run": "r2", "t_ms": 4900, "text": ["over the last thirty"]}]
    assert S.prompt_score(LABELS, runs, [], EAR)["thoughts"][0]["cut"]


def test_a_line_said_before_the_last_span_ended_is_a_cut_even_with_the_whole_prompt():
    runs = [{"run": "r1", "t_ms": 4900, "text": [T1]}]
    row = S.prompt_score(LABELS, runs, [3200], EAR)["thoughts"][0]
    assert row["r2"] and row["spoke_during"] == 1 and row["cut"]


def test_two_thoughts_in_one_prompt_is_a_merge_and_a_stranger_is_exposure_not_a_merge():
    merged = S.prompt_score(LABELS, [{"run": "r1", "t_ms": 10400, "text": [T1, T2]}], [], EAR)
    assert all(r["merged"] for r in merged["thoughts"])
    exposed = S.prompt_score(LABELS, [{"run": "r1", "t_ms": 6400, "text": [T1 + " did you feed the cat"]}], [], EAR)
    assert not exposed["thoughts"][0]["merged"]
    assert exposed["exposure"] == [1, 1] and exposed["exposure_by_kind"]["question"] == [1, 1]


def test_labels_moved_off_the_audio_are_caught_by_the_alignment_check():
    heard = [["what", 1000, 1200], ["does", 1200, 1350], ["share", 1400, 1700], ["fridays", 2000, 2500],
             ["last", 3800, 4000], ["thirty", 4100, 4500], ["how", 9100, 9300], ["many", 9300, 9500],
             ["down", 9700, 10000]]
    assert S.label_alignment(LABELS, heard)["ok"]
    assert not S.label_alignment(P._shift(LABELS, 2000), heard)["ok"]
    assert not S.label_alignment(LABELS, heard[:3])["ok"]                     # too few words to say anything


def _flow(stratum, thoughts, infra=False):
    lat = {"thoughts": thoughts, "exposure_by_kind": {"narration": [0, 0], "question": [0, 0]}}
    return {"stratum": stratum, "infra": infra, "by_latency": {"300": lat, "800": lat, "1500": lat},
            "flux": {"turns": []}, "ear": {"turns": []}}


def _thought(cut=False, merged=False, wait=400):
    return {"cut": cut, "merged": merged, "unclosed": False, "wait_ms": wait, "kind": "complete"}


def test_a_cell_with_nothing_evaluated_is_infra_never_green():
    agg = P.aggregate({"f1": _flow("es×clean", [_thought()] * 4, infra=True)})
    assert agg["es×clean"]["verdict"] == "INFRA" and agg["es×clean"]["infra_flows"] == 1
    empty = P.aggregate({"f1": _flow("es×clean", [])})                      # scored, but no thought to score
    assert empty["es×clean"]["verdict"] == "INFRA"
    assert {d["verdict"] for d in empty["es×clean"]["by_latency"].values()} == {"INFRA"}


def test_profile_a_needs_fifty_two_clean_thoughts_and_one_bad_cell_latency_decides():
    assert P.aggregate({"f": _flow("c", [_thought()] * 52)})["c"]["verdict"] == "PASS"
    assert P.aggregate({"f": _flow("c", [_thought()] * 51)})["c"]["verdict"] == "FAIL"   # Wilson 0/51 > 7 %
    slow = _flow("c", [_thought()] * 52)
    slow["by_latency"]["300"] = {"thoughts": [_thought(cut=True)] + [_thought()] * 51,
                                 "exposure_by_kind": {"narration": [0, 0], "question": [0, 0]}}
    assert P.aggregate({"f": slow})["c"]["verdict"] == "FAIL"
    assert P.aggregate({"f": _flow("c", [_thought(wait=700)] * 52)})["c"]["verdict"] == "FAIL"   # wait p95


def test_the_composer_labels_what_was_said_where_it_was_said(tmp_path, monkeypatch):
    def utter(voice, text):
        words = tuple((w, 0.3 * i, 0.3 * i + 0.25) for i, w in enumerate(text.split()))
        audio = (0.1 * np.sin(np.linspace(0, 400 * np.pi, int(C.RATE * 0.3 * len(text.split()))))).astype(np.float32)
        return C.V.Utterance(voice, text, audio, words)

    monkeypatch.setattr(C.V, "utter", utter)
    monkeypatch.setattr(C.V, "write_wav", lambda path, x: path.write_bytes(b""))
    spec = {"id": "t", "lang": "en", "calibrate": True, "items": [
        {"say": "en_1", "text": "one two three", "role": "user", "turn": 1},
        {"say": "en_1", "text": "four five six seven", "role": "user", "turn": 1, "gap_ms": 900, "continues": True},
        {"say": "en_1", "text": "eight nine ten eleven", "role": "user", "turn": 2, "gap_ms": 4000, "cut_s": 0.5},
    ]}
    _, lab = C.compose(spec, tmp_path)
    labels = json.loads(lab.read_text())
    user = [s for s in labels["segments"] if s["role"] == "user"]
    assert user[1]["start_ms"] - user[0]["end_ms"] == pytest.approx(900, abs=2) and user[1]["continues"]
    assert user[2]["cut"] and user[2]["text"] == "eight nine"                 # the label says what was SAID
    t1, t2 = labels["turns"]
    assert t1["segments"] == [user[0]["i"], user[1]["i"]] and t2["kind"] == "cut_off"
    assert t1["end_ms"] == user[1]["words"][-1][2]
    cal = [s for s in labels["segments"] if s["role"] == "calibration"]
    assert len(cal) == 2 and cal[0]["start_ms"] < user[0]["start_ms"] and cal[1]["start_ms"] > user[2]["end_ms"]


def test_a_short_span_is_not_found_through_a_function_word_and_never_picks_an_unrelated_run():
    short = S.words_of("en Valencia")
    assert S.arrives(short, S.words_of("apunta en la lista"))           # the frozen rule alone is this lax…
    assert not S.present(short, S.words_of("apunta en la lista"))       # …so merges and exposure ask two words
    assert S.present(short, S.words_of("y en Valencia mañana"))
    labels = {"duration_ms": 30_000, "turns": [{"turn": 1, "start_ms": 0, "end_ms": 3000, "kind": "complete"}],
              "segments": [_seg(0, "user", 1, 0, 1500, "qué tiempo va a hacer el sábado"),
                           _seg(1, "user", 1, 2000, 3000, "en Valencia")]}
    runs = [{"run": "r1", "t_ms": 3500, "text": ["qué tiempo va a hacer el sábado", "en Valencia"]},
            {"run": "r2", "t_ms": 9000, "text": ["apunta en la lista de tareas"]}]
    row = S.prompt_score(labels, runs, [], [])["thoughts"][0]
    assert row["answering_run"] == "r1" and row["r2"] and not row["cut"]


def test_the_tolerant_alignment_forgives_what_flux_mishears_and_the_frozen_one_does_not():
    span, heard = S.words_of("Recuérdame llamar a Rowan"), S.words_of("Recuerda me llamara Rowan")
    assert not S.arrives(span, heard)
    assert S.arrives(span, heard, fuzzy=True)
    assert not S.arrives(span, S.words_of("pon música tranquila"), fuzzy=True)


def test_the_tolerant_r2_still_goes_red_on_a_real_split_and_green_on_a_misheard_whole():
    labels = {"duration_ms": 30_000, "turns": [{"turn": 1, "start_ms": 0, "end_ms": 4000, "kind": "complete"}],
              "segments": [_seg(0, "user", 1, 0, 1500, "Recuérdame llamar a Rowan"),
                           _seg(1, "user", 1, 2500, 4000, "cuando salga de la oficina")]}
    misheard = [{"run": "r1", "t_ms": 4500, "text": ["Recuerda me llamara Rowan. Cuando salga de la oficina."]}]
    row = S.prompt_score(labels, misheard, [], [])["thoughts"][0]
    assert row["r2"] and not row["r2_strict"] and not row["cut"]           # the STT's fault, not the ear's
    split = [{"run": "r1", "t_ms": 1900, "text": ["Recuerda me llamara Rowan."]},
             {"run": "r2", "t_ms": 4500, "text": ["Cuando salga de la oficina."]}]
    row = S.prompt_score(labels, split, [], [])["thoughts"][0]
    assert not row["r2"] and row["cut"]                                     # answered in two prompts: a cut
    row = S.prompt_score(labels, misheard, [3000], [])["thoughts"][0]
    assert row["cut"]                                                       # a line said before he finished: a cut


def test_a_merge_needs_more_than_a_function_word_of_the_other_thought():
    labels = {"duration_ms": 30_000,
              "turns": [{"turn": 1, "start_ms": 0, "end_ms": 3000, "kind": "complete"},
                        {"turn": 2, "start_ms": 9000, "end_ms": 11000, "kind": "complete"}],
              "segments": [_seg(0, "user", 1, 0, 1500, "qué tiempo va a hacer el sábado"),
                           _seg(1, "user", 1, 2000, 3000, "en Valencia"),
                           _seg(2, "user", 2, 9000, 11000, "apunta en la lista de tareas")]}
    runs = [{"run": "r1", "t_ms": 3500, "text": ["qué tiempo va a hacer el sábado", "en Valencia"]},
            {"run": "r2", "t_ms": 11500, "text": ["apunta en la lista de tareas"]}]
    rows = S.prompt_score(labels, runs, [], [])["thoughts"]
    assert [r["merged"] for r in rows] == [False, False]
    together = [{"run": "r1", "t_ms": 11500, "text": ["qué tiempo va a hacer el sábado en Valencia",
                                                       "apunta en la lista de tareas"]}]
    assert all(r["merged"] for r in S.prompt_score(labels, together, [], [])["thoughts"])


def _marked_flow(stratum, goes_on, terminal):
    f = _flow(stratum, [_thought()] * 52)
    f["end_marks"] = {"goes_on": goes_on, "goes_on_terminal": terminal}
    return f


def test_a_piece_by_piece_pause_cell_informs_and_does_not_decide():
    piecewise = P.aggregate({"f": _marked_flow("es×pauses-900", 100, 80)})["es×pauses-900"]
    assert piecewise["verdict"].startswith("INFORMATIVE") and piecewise["terminal_share_goes_on"] == 0.8
    one_breath = P.aggregate({"f": _marked_flow("es×pauses-900", 100, 30)})["es×pauses-900"]
    assert one_breath["verdict"] == "PASS"
    assert P.aggregate({"f": _marked_flow("es×clean", 100, 80)})["es×clean"]["verdict"] == "PASS"   # pauses only


def test_one_utterance_is_cut_at_a_quiet_word_boundary_with_a_fade_and_a_loud_cut_leaves_its_thought_out():
    rate = C.RATE
    t = np.arange(int(rate * 2.0)) / rate
    x = (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    x[int(0.95 * rate):int(1.05 * rate)] = 0.0                   # the quiet gap a person leaves between two words
    words = [("one", 0.1, 0.6), ("two", 0.6, 0.97), ("three", 1.03, 1.5), ("four", 1.5, 1.9)]
    parts, checks, texts = C.split_thought(x, words, ["one", "two three four"])
    assert texts == ["one two", "three four"]                    # moved one word, to the quiet boundary
    assert checks[0]["ok"] and checks[0]["moved_words"] == 1
    assert abs(float(parts[0][0][-1])) < 1e-3 and abs(float(parts[1][0][0])) < 1e-3   # faded: no step at the cut
    loud = (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)   # no quiet boundary anywhere
    parts, checks, _ = C.split_thought(loud, words, ["one two", "three four"])
    assert not checks[0]["ok"]
    tail, head = parts[0][0][-8:], parts[1][0][:8]                # cut in full voice: the fade still leaves no step
    assert float(np.max(np.abs(tail))) < 0.01 and float(np.max(np.abs(head))) < 0.01
    labels = {"duration_ms": 9000, "turns": [{"turn": 1, "start_ms": 0, "end_ms": 3000, "kind": "complete"}],
              "segments": [_seg(0, "user", 1, 0, 1000, "one two"), {**_seg(1, "user", 1, 2000, 3000, "three four"),
                                                                     "cut_ok": False}]}
    row = S.prompt_score(labels, [{"run": "r1", "t_ms": 3500, "text": ["one two three four"]}], [], [])["thoughts"][0]
    assert row["infra"]
    f = _flow("c", [{**_thought(), "infra": True}] * 3 + [_thought()] * 52)
    agg = P.aggregate({"f": f})["c"]
    assert agg["by_latency"]["800"]["n"] == 52 and agg["infra_thoughts"] == 3


def test_a_word_boundary_the_voice_gives_a_little_off_is_moved_to_the_quiet_beside_it():
    rate = C.RATE
    t = np.arange(int(rate * 2.0)) / rate
    x = (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    x[int(1.025 * rate):int(1.045 * rate)] = 0.0                 # 20 ms of quiet, 35 ms after the boundary given
    words = [("one", 0.1, 0.6), ("two", 0.6, 0.99), ("three", 0.99, 1.5), ("four", 1.5, 1.9)]
    parts, checks, texts = C.split_thought(x, words, ["one two", "three four"])
    assert texts == ["one two", "three four"]
    assert 1025 <= checks[0]["at_ms"] <= 1045                    # cut in the quiet, not at 990 where it was said


def test_flux_end_marks_tell_a_piece_that_goes_on_from_one_that_ended():
    labels = {"duration_ms": 9000, "turns": [{"turn": 1, "start_ms": 0, "end_ms": 3000, "kind": "complete"}],
              "segments": [{**_seg(0, "user", 1, 0, 1000, "what time"), "words": [["what", 0, 400], ["time", 400, 1000]]},
                           {**_seg(1, "user", 1, 2000, 3000, "is it"), "words": [["is", 2000, 2400], ["it", 2400, 3000]]}]}
    raw = [{"msg": {"type": "TurnInfo", "event": "EndOfTurn", "turn_index": 0,
                    "words": [{"word": "What", "start": 0.0, "end": 0.4}, {"word": "time.", "start": 0.4, "end": 1.0}]}},
           {"msg": {"type": "TurnInfo", "event": "EndOfTurn", "turn_index": 1,
                    "words": [{"word": "is", "start": 2.0, "end": 2.4}, {"word": "it?", "start": 2.4, "end": 3.0}]}}]
    m = S.flux_end_marks(labels, raw)
    assert m == {"goes_on": 1, "goes_on_terminal": 1, "ended": 1, "ended_terminal": 1}
