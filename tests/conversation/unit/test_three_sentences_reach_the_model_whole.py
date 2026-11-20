"""The NVIDIA case, end to end with a scripted model (node 13.17): three sentences with pauses reach the model as ONE
input, in ONE call, with the whole intervention — and no tool runs before the model chose it.

Spanish, English and another domain (the same shape with a recipe): the provider hints eager at each pause and
resumed when the person goes on; the intervention closes once, the model is called once with every word, it reads
the market data it chose, and the request closes `answered` exactly once.
"""
from __future__ import annotations

import pytest

from conversation.ports import Done, ToolCall
from conversation.testing.scripted_model import reply
from tests.conversation.unit.convkit import Harness

CASES = {
    "es": [(["w01", "w02", "w03", "w04", "w05", "w06"], 900), (["w07", "w08", "w09"], 700),
           (["w10", "w11", "w12", "w13"], 0)],
    "en": [(["w21", "w22", "w23", "w24", "w25"], 900), (["w26", "w27", "w28"], 700), (["w29", "w30", "w31"], 0)],
    "recipe": [(["w41", "w42", "w43"], 1100), (["w44", "w45"], 800), (["w46", "w47", "w48", "w49"], 0)],
}


@pytest.mark.parametrize("case", sorted(CASES))
def test_three_sentences_reach_the_model_whole_in_one_call(store, case):
    parts = CASES[case]
    h = Harness(store, grace=False, script={"iv_000001": [
        [ToolCall("c1", "market_data", {"q": "fridays"}), Done()],
        [reply("w99 w98"), Done()]]})
    h.utter(parts)
    h.pump()
    assert h.tel.labels("conv_run").count("conv_run/started") == 1
    first_inputs = [c for c in h.model.calls if not c.prompt.steps]
    assert len(first_inputs) == 1, "the model was called before the intervention closed, or twice"
    words = " ".join(w for toks, _ in parts for w in toks)
    assert f"«{words}»" in first_inputs[0].prompt.input
    assert h.tools.calls == [("market_data", {"q": "fridays"}, None)]      # only what the model chose, after it
    assert [lab for lab, _p in h.closes()] == ["answered"]
    assert h.mouth.orders[0].text == "w99 w98"
    labels = h.tel.labels("conv_ear")
    assert labels.count("conv_ear/closed") == 1 and labels.count("conv_ear/tentative") == 2
