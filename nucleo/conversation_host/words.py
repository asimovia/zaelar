"""The `Words` port (V2-941, B7b): the few fixed lines the manager says itself, as they are, from the language pack of
the person's language (`i18n.langs`) — a figure it could not confirm (`unverified_fact`), an answer it lost
(`mute_lines`, its first variant). The operator's pack first, then the English one: a pack that does not carry a key
yet falls back, so the manager is never silent for a missing line — and never says a line of ours.
"""
from __future__ import annotations


#: the pack every language falls back to when its own does not carry a line yet
FALLBACK = "en"


def _of(spec, key: str) -> str:
    v = getattr(spec, str(key), "")
    if isinstance(v, (list, tuple)):                     # a family of variants: its first, the pack's own
        v = v[0] if v else ""
    return v.strip() if isinstance(v, str) else ""


class PackWords:
    def line(self, key: str) -> str:
        """The operator's language pack first, then English: a pack that does not carry the key yet never makes the
        manager silent."""
        from i18n import langs
        return _of(langs.current_language(), key) or _of(langs.spec(FALLBACK), key)
