"""I2: every final word of the speech-to-text belongs to exactly one intervention.

A provider turn (`seq`) is assigned to ONE intervention the first time it is seen. A later hypothesis of the same seq
REPLACES the earlier one — revisions rewrite words already given (adapter doc A4) — so a word is never counted twice.
Once that intervention has ended, what it was given is its own and never changes: a later hypothesis of the turn
counts only for the words it brings PAST what was delivered (the turn grew after the ear closed it). Those, and only
those, go to the next intervention — the turn is split there (`split`); a hypothesis with nothing new (the same final
delivered again) changes nothing. An intervention is COVERED when every part of a turn assigned to it has its final;
a part that never got one is a gap.
"""
from __future__ import annotations

from dataclasses import dataclass, field

Word = tuple[str, int, int, float]


@dataclass
class _Turn:
    iv: str
    revision: int
    final: bool
    words: tuple[Word, ...]


@dataclass
class Spans:
    #: (stream, seq, start) → the part of a provider turn from word `start` on that one intervention owns
    _turns: dict[tuple[str, int, int], _Turn] = field(default_factory=dict)
    _start: dict[tuple[str, int], int] = field(default_factory=dict)      # (stream, seq) → its current part

    def _key(self, stream: str, seq: int) -> tuple[str, int, int]:
        return stream, seq, self._start.get((stream, seq), 0)

    def add(self, stream: str, seq: int, revision: int, final: bool, words: tuple[Word, ...], iv: str) -> bool:
        """Record a hypothesis (the whole turn, as the provider sends it) for its current part; returns True when it
        brought words this part did not have."""
        key = self._key(stream, seq)
        mine = tuple(words[key[2]:])
        cur = self._turns.get(key)
        if cur is None:
            self._turns[key] = _Turn(iv, revision, final, mine)
            self._start.setdefault((stream, seq), key[2])
            return bool(mine)
        if cur.final and (not final or revision < cur.revision):
            return False                       # a late partial — or an OLDER final — never undoes a newer final
        if revision < cur.revision and not final:
            return False
        grew = len(mine) > len(cur.words)
        cur.revision, cur.final, cur.words = revision, final or cur.final, mine
        if final:                              # the turn's final also ends the parts ended interventions kept
            for k, t in self._turns.items():
                if k[:2] == (stream, seq) and k[2] < key[2]:
                    t.final = True
        return grew

    def owner(self, stream: str, seq: int) -> str | None:
        t = self._turns.get(self._key(stream, seq))
        return t.iv if t else None

    def brings_new(self, stream: str, seq: int, words: tuple[Word, ...]) -> bool:
        """Does this hypothesis carry words past what the turn's current part already holds?"""
        key = self._key(stream, seq)
        cur = self._turns.get(key)
        return cur is None or len(words) > key[2] + len(cur.words)

    def split(self, stream: str, seq: int, to_iv: str) -> None:
        """The turn grew after its intervention ended: what it held stays there, a new part starts after it and
        belongs to `to_iv`."""
        key = self._key(stream, seq)
        cur = self._turns[key]
        start = key[2] + len(cur.words)
        self._start[(stream, seq)] = start
        self._turns[(stream, seq, start)] = _Turn(to_iv, cur.revision, False, ())

    def seqs(self, iv: str) -> list[tuple[str, int, int]]:
        return sorted(k for k, t in self._turns.items() if t.iv == iv)

    def words(self, iv: str) -> list[Word]:
        return [w for k in self.seqs(iv) for w in self._turns[k].words]

    def final_words(self, iv: str) -> list[Word]:
        return [w for k in self.seqs(iv) if self._turns[k].final for w in self._turns[k].words]

    def covered(self, iv: str) -> bool:
        seqs = self.seqs(iv)
        return bool(seqs) and all(self._turns[k].final for k in seqs) and bool(self.words(iv))

    def final_word_ids(self) -> list[tuple[str, tuple[str, int, int]]]:
        """(intervention, word id) of every final word; a word is identified by its provider turn and its place in it,
        never by its text or time (two turns may carry the same word at the same instant)."""
        return [(t.iv, (k[0], k[1], k[2] + i)) for k, t in sorted(self._turns.items()) if t.final
                for i in range(len(t.words))]

    def all_final_words(self) -> list[tuple[str, Word]]:
        return [(t.iv, w) for _k, t in sorted(self._turns.items()) if t.final for w in t.words]
