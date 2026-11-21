"""The agent itself — its name, how it listens, his rules and style, its controls — is changed by the doors that already
do it (node 13.129, INI-078 F2 step 6).

Each is a declared act to its one door; what changes who the agent is or how it speaks reaches the model's prefix at
once. How it speaks has ONE source: the language pack's `speech_style` and the turn's shape as genesis `style` and his
rows set it — a rule he dictates changes the next run. The declared choices are the modules' own: the attention modes
`voice.attention` accepts, the controls `self_controls` declares.
"""
from __future__ import annotations

from nucleo.conversation_host import acts_self, prefix
from nucleo.conversation_host.declared import declared


def test_the_declared_choices_are_the_modules_own():
    from nucleo.acts import self_controls
    from voice import attention
    acts = declared()["acts"]
    assert acts["set_attention"]["schema"]["properties"]["mode"]["enum"] == list(attention._VALID_MODES)
    assert all(a in acts["agent_controls"]["about"] for a in self_controls.ACTS)


def test_a_rename_reaches_the_wake_word_the_memory_and_the_prefix(monkeypatch):
    from nucleo.self import identity
    seen = []
    monkeypatch.setattr(identity, "_HEARD", {"name": "", "at": 0.0})
    monkeypatch.setattr(identity, "apply_rename_now", lambda n: seen.append(("now", n)))

    async def persist(n):
        seen.append(("kept", n))
    monkeypatch.setattr(identity, "persist_rename", persist)
    monkeypatch.setattr(acts_self, "_refresh", lambda: seen.append(("prefix",)))
    assert acts_self.run("rename", {"name": "w_nova"}).data == {"named": "w_nova"}
    assert seen == [("now", "w_nova"), ("kept", "w_nova"), ("prefix",)]
    assert identity.rename_heard("w_nova") and not identity.rename_heard("w_other"), "the memory may file only his name"


def test_a_rule_he_dictates_is_shaped_from_his_words_and_reaches_the_style(monkeypatch):
    from nucleo.conversation_host import routing
    from nucleo.flash import style_directive
    from nucleo import style_policy
    seen = {}

    async def write(directive, text, emit, brain=None, *, speak=True):
        seen.update(directive=directive, text=text, speak=speak)
        return {"stored": [{"id": 1}], "line": "w_kept"}
    monkeypatch.setattr(style_directive, "write_rule", write)
    monkeypatch.setattr(acts_self, "_refresh", lambda: seen.setdefault("prefix", True))
    monkeypatch.setitem(routing._last, "said", "w_speak_shorter")
    got = acts_self.run("rule", {"rule": "w_short"})
    assert got.data["say"] == "w_kept" and seen == {"directive": "w_short", "text": "w_speak_shorter", "speak": False,
                                                    "prefix": True}
    monkeypatch.setattr(style_policy, "policy", lambda: {"max_sentences": 1, "fillers": None})
    assert prefix.style_line("w_pack") == "w_pack; shape: max_sentences=1"      # his row, as data, beside the DNA


def test_a_control_is_the_buttons_own_act_and_an_unknown_one_names_them(monkeypatch):
    from nucleo.acts import self_controls
    from voice import observer
    sent = []
    monkeypatch.setattr(observer, "emit", lambda kind, label, **kw: sent.append((kind, label)))
    assert acts_self.run("controls", {"act": "mute"}).data["done"] == "mute" and sent == [("controls", "mute")]
    other = acts_self.run("controls", {"act": "w_dance"})
    assert other.status == "failed" and other.data["acts"] == list(self_controls.ACTS)
