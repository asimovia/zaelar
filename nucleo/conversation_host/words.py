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
    def line(self, key: str, near: str = "") -> str:
        """The pack of the language his words are in (`near`, when the engine can tell), else the operator's, then
        English: a reply to an English line is never a Spanish one, and a pack without the key never makes the manager
        silent."""
        from i18n import langs
        from nucleo.flash import spoken_lang
        heard = spoken_lang.language_of(near) if near else ""
        packs = ([langs.spec(heard)] if heard else []) + [langs.current_language(), langs.spec(FALLBACK)]
        return next((got for got in (_of(p, key) for p in packs) if got), "")
