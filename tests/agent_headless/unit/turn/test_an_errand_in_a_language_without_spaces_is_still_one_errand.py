"""An errand said in a language written without spaces is still ONE errand (V2-878 §3 (d), node 2.1677).

The «same errand?» yardstick (`matching.content_words` + `containment`) counted words of four letters or more out of
`\\w+` runs. A Japanese or Chinese sentence is ONE run — one «word» — so two sentences about the same monitor shared
nothing and every refinement opened a second errand; and `task_recall.words` read only `[a-z0-9]`, so a goal in
Cyrillic, Greek or Arabic had no words at all to be recalled by.

Mechanism: when `\\w+` gives at most two runs, each eight characters or more on average, the sentence's words are its
character bigrams (3-grams were measured too coarse for two-character Chinese words); spaced languages are untouched
(the population `SAME_ERRAND` was calibrated on). `task_recall.words` reads `\\w+` after folding accents, in any
alphabet.

Disarms (seen red): the bigram fallback removed; `task_recall.words` back to `[a-z0-9]+`.
"""
from __future__ import annotations

import pytest

from nucleo import matching
from nucleo.turn import task_recall

SAME = [("モニターは27インチ以上で探して", "27インチのモニターはまだ？"),
        ("显示器要二十七寸以上的", "二十七寸的显示器找到了吗"),
        ("หาจอมอนิเตอร์ยี่สิบเจ็ดนิ้ว", "จอมอนิเตอร์ยี่สิบเจ็ดนิ้วได้หรือยัง")]
OTHER = [("モニターは27インチ以上で探して", "ローマ行きの飛行機を予約して"), ("显示器要二十七寸以上的", "帮我订二十七号去罗马的机票")]


@pytest.mark.parametrize("a,b", SAME)
def test_two_sentences_about_one_errand_share_its_content(a, b):
    got = matching.containment(matching.content_words(a), matching.content_words(b))
    assert got > matching.SAME_ERRAND, (a, b, got)


@pytest.mark.parametrize("a,b", OTHER)
def test_two_errands_stay_two(a, b):
    assert matching.containment(matching.content_words(a), matching.content_words(b)) < matching.SAME_ERRAND


@pytest.mark.parametrize("text,words", [("gaming monitor", {"gaming", "monitor"}),
                                        ("busca un monitor de 27 pulgadas", {"busca", "monitor", "pulgadas"})])
def test_a_spaced_language_keeps_its_words(text, words):
    assert matching.content_words(text) == words


def test_recall_reads_words_in_any_alphabet():
    assert task_recall.words("Поездка в Москву, Gràcia") == {"поездка", "москву", "gracia"}
    assert task_recall.words("ταξίδι στην Αθήνα") >= {"ταξιδι", "αθηνα"}
