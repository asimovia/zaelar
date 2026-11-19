"""I2: every final word of the speech-to-text belongs to exactly one intervention.

A provider turn (`seq`) is assigned to ONE intervention the first time it is seen and never to another (unless the
whole assignment is moved, `reassign`, when a reopen loses to a seal). A later hypothesis of the same seq REPLACES the
earlier one — revisions rewrite words already given (adapter doc A4) — so a word is never counted twice. An
intervention is COVERED when every seq assigned to it has its final; a seq that never got one is a gap.
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
    tag: int                      # the intervention revision it was heard in


@dataclass
class Spans:
    _turns: dict[tuple[str, int], _Turn] = field(default_factory=dict)

    def add(self, stream: str, seq: int, revision: int, final: bool, words: tuple[Word, ...], iv: str,
            tag: int) -> bool:
        """Record a hypothesis; returns True when it brought words this seq did not have."""
        key = (stream, seq)
        cur = self._turns.get(key)
        if cur is None:
            self._turns[key] = _Turn(iv, revision, final, tuple(words), tag)
            return bool(words)
        if cur.final and not final:
            return False                       # a late partial never undoes a final
        if revision < cur.revision and not final:
            return False
        grew = len(words) > len(cur.words)
        cur.revision, cur.final, cur.words = revision, final or cur.final, tuple(words)
        return grew

    def owner(self, stream: str, seq: int) -> str | None:
        t = self._turns.get((stream, seq))
        return t.iv if t else None

    def seqs(self, iv: str) -> list[tuple[str, int]]:
        return sorted(k for k, t in self._turns.items() if t.iv == iv)

    def words(self, iv: str) -> list[Word]:
        return [w for k in self.seqs(iv) for w in self._turns[k].words]

    def final_words(self, iv: str) -> list[Word]:
        return [w for k in self.seqs(iv) if self._turns[k].final for w in self._turns[k].words]

    def covered(self, iv: str) -> bool:
        seqs = self.seqs(iv)
        return bool(seqs) and all(self._turns[k].final for k in seqs) and bool(self.words(iv))

    def reassign(self, iv: str, from_tag: int, to_iv: str) -> int:
        """Move the seqs heard since revision `from_tag` to another intervention; returns how many moved."""
        moved = 0
        for t in self._turns.values():
            if t.iv == iv and t.tag >= from_tag:
                t.iv, t.tag, moved = to_iv, 1, moved + 1
        return moved

    def all_final_words(self) -> list[tuple[str, Word]]:
        return [(t.iv, w) for _k, t in sorted(self._turns.items()) if t.final for w in t.words]
