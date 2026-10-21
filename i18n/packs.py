"""i18n/packs.py — THE registry of every per-language word the product carries (2026-10-21).

One language = one folder, the same files for every language:

    i18n/genesis/<code>/<pack>.json          the languages the repo SHIPS (en = the manifest, es = preset)
    <workspace>/i18n/generated/<code>/<pack>.json   every other language, generated at onboarding

A pack is one kind of words: `ui` (what the screen shows, and what the engine sends the screen), `voice` (what
the agent says and hears: its spoken lines, fillers, prompts' language directives, detector vocabulary), `smalltalk`,
`aliases` (voice words for the system surfaces), `actionmap` (whole-utterance commands). English is the manifest of
every pack: a generated language is a translation of the English one, topped up when the English changes.

The rule this module exists to keep: a word meant for one human language lives HERE and nowhere else. A table of
Spanish and English in a module is a language a third operator never gets — `tests/infrastructure/unit/
test_every_word_lives_in_a_language_pack.py` fails on a new one. Reading is `pack(name, code)`; generating is
`i18n.init.prepare(code)`, which walks `PACKS` in order.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

GENESIS = Path(__file__).resolve().parent / "genesis"
BASE = "en"
PRESET = ("en", "es")


@dataclass(frozen=True)
class Pack:
    name: str
    what: str
    preset_only: bool = False      # generated languages read the English one (nothing to translate)


#: In the order onboarding prepares them: the screen first, then what the agent says, then what it understands.
PACKS: tuple[Pack, ...] = (
    Pack("ui", "every string the screen shows, the engine's own included"),
    Pack("voice", "what the agent says and the vocabulary its detectors read"),
    Pack("smalltalk", "the greetings/thanks/goodbye phrasebook of the conversational lane"),
    Pack("aliases", "the voice words that name each system surface"),
    Pack("actionmap", "whole-utterance commands mapped to a direct action"),
)
NAMES = tuple(p.name for p in PACKS)


def _workspace_generated() -> Path:
    try:
        from nucleo import workspace as _ws
        return _ws.root() / "i18n" / "generated"
    except Exception:  # noqa: BLE001 — a bare checkout with no workspace module still reads the presets
        return Path(__file__).resolve().parents[1] / "i18n" / "generated"


def preset_path(code: str, name: str) -> Path:
    return GENESIS / code / f"{name}.json"


def generated_dir(code: str = "") -> Path:
    d = _workspace_generated()
    return d / code if code else d


def generated_path(code: str, name: str) -> Path:
    return generated_dir(code) / f"{name}.json"


#: Where a generated pack lived before the per-language folders (one flat directory, suffix per kind).
_LEGACY = {"ui": "{code}.json", "aliases": "{code}.aliases.json", "smalltalk": "{code}.smalltalk.json"}


def _migrate(code: str, name: str) -> None:
    """Move a pre-folder generated file into its language folder, once. Nothing is regenerated."""
    tpl = _LEGACY.get(name)
    if not tpl:
        return
    old = generated_dir() / tpl.format(code=code)
    new = generated_path(code, name)
    if old.is_file() and not new.exists():
        new.parent.mkdir(parents=True, exist_ok=True)
        os.replace(old, new)


def read_json(path: Path) -> dict:
    """A pack file, or {} when it does not exist yet (the normal state of a language not generated)."""
    if not path.is_file():
        return {}
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        from loguru import logger
        logger.warning(f"i18n.packs: unreadable pack {path}: {e}")
        d = {}
    return d if isinstance(d, dict) else {}


def write_json(path: Path, data: dict) -> None:
    """Atomic (tmp + replace): a crash mid-write never leaves half a language behind."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def preset(name: str, code: str) -> dict:
    return read_json(preset_path(code, name))


def generated(name: str, code: str) -> dict:
    code = (code or "").strip().lower()
    if not code or code in PRESET:
        return {}
    _migrate(code, name)
    return read_json(generated_path(code, name))


def generated_codes() -> list[str]:
    """Languages with anything generated on disk (folders, plus not-yet-migrated flat UI files)."""
    d = generated_dir()
    if not d.is_dir():
        return []
    out = {p.name for p in d.iterdir() if p.is_dir() and any(p.glob("*.json"))}
    out |= {p.name[:-5] for p in d.glob("*.json") if p.name.count(".") == 1}
    return sorted(out - set(PRESET))


def flatten(tree, prefix: str = "") -> dict[str, str]:
    """Every string leaf of a pack, keyed by its path («fillers.3», «intents.greeting.cues.0»)."""
    out: dict[str, str] = {}
    if isinstance(tree, dict):
        for k, v in tree.items():
            if str(k).startswith("_"):
                continue
            out.update(flatten(v, f"{prefix}{k}."))
    elif isinstance(tree, (list, tuple)):
        for i, v in enumerate(tree):
            out.update(flatten(v, f"{prefix}{i}."))
    elif isinstance(tree, str):
        out[prefix[:-1]] = tree
    return out


def unflatten_onto(shape, flat: dict[str, str], prefix: str = ""):
    """The English `shape` with every string leaf replaced by `flat`'s, where it has one."""
    if isinstance(shape, dict):
        return {k: (v if str(k).startswith("_") else unflatten_onto(v, flat, f"{prefix}{k}."))
                for k, v in shape.items()}
    if isinstance(shape, (list, tuple)):
        return [unflatten_onto(v, flat, f"{prefix}{i}.") for i, v in enumerate(shape)]
    if isinstance(shape, str):
        v = flat.get(prefix[:-1])
        return v if isinstance(v, str) and v.strip() else shape
    return shape


# ── the actionmap pack: only its WORDS travel — the actions they map to are code, never translated ──────────

def _actionmap_texts(tree: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for i, e in enumerate(tree.get("entries") or []):
        if isinstance(e, dict) and isinstance(e.get("phrase"), str):
            out[f"entries.{i}.phrase"] = e["phrase"]
    for i, g in enumerate(tree.get("grids") or []):
        if not isinstance(g, dict):
            continue
        for j, v in enumerate(g.get("verbs") or []):
            out[f"grids.{i}.verbs.{j}"] = v
        for j, k in enumerate((g.get("objects") or {}).keys()):
            out[f"grids.{i}.objects.{j}"] = k
    return out


def _actionmap_rebuild(tree: dict, flat: dict[str, str]) -> dict:
    def tr(key: str, en: str) -> str:
        v = flat.get(key)
        return v.strip().lower() if isinstance(v, str) and v.strip() else en
    entries = [dict(e, phrase=tr(f"entries.{i}.phrase", e["phrase"])) if isinstance(e, dict) and "phrase" in e else e
               for i, e in enumerate(tree.get("entries") or [])]
    grids = []
    for i, g in enumerate(tree.get("grids") or []):
        if not isinstance(g, dict):
            grids.append(g)
            continue
        verbs = [tr(f"grids.{i}.verbs.{j}", v) for j, v in enumerate(g.get("verbs") or [])]
        objects = {tr(f"grids.{i}.objects.{j}", k): v for j, (k, v) in enumerate((g.get("objects") or {}).items())}
        grids.append(dict(g, verbs=verbs, objects=objects))
    return dict(tree, entries=entries, grids=grids)


def texts(name: str, tree: dict) -> dict[str, str]:
    """The translatable strings of a pack, flat — what a translator receives and the upgrade diff compares."""
    return _actionmap_texts(tree) if name == "actionmap" else flatten(tree)


def rebuild(name: str, tree: dict, flat: dict[str, str]):
    """The English `tree` of a pack with its strings replaced by a translation's."""
    return _actionmap_rebuild(tree, flat) if name == "actionmap" else unflatten_onto(tree, flat)


def read(name: str, code: str):
    """THE reader of a pack for a language: the shipped file, or English rebuilt with the generated strings.

    A language with nothing generated for this pack gets English — except the packs that are GENERATED rather than
    translated (`smalltalk`, `aliases`): there the generated file is the pack, and its absence is answered `{}`."""
    code = (code or BASE).strip().lower()
    if code in PRESET:
        return preset(name, code)
    gen = generated(name, code)
    if name in ("smalltalk", "aliases"):
        return gen
    flat = gen.get("strings") if isinstance(gen.get("strings"), dict) else {}
    base = preset(name, BASE)
    return rebuild(name, base, flat) if flat else base
