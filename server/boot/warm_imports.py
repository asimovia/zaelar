"""Warm, off the loop, the vendor SDKs the voice's LLM providers import (INI-042 #34).

The first voice session builds its LLM (`voice.engine.llm.build_llm`), which imports every provider module, and each
one pulls a LiveKit plugin (`livekit.plugins.anthropic`, `.openai`, `.google`). Those plugins import large vendor
SDKs — `anthropic` alone is ~1000 modules — and all of it ran on the body's event-loop thread when the session
opened: 4.6 s measured on a hosted account, with the loop frozen (voice frames, SSE, typed turns all waiting).

The plugins themselves cannot be imported here: LiveKit refuses to register a plugin from any thread but the main
one (`Plugin.register_plugin` raises), and the main thread IS the loop. Their vendor SDKs carry no such rule, so
this module imports THOSE in a daemon thread at boot. When the session opens, the plugin's own import then finds
its SDK already in `sys.modules` and costs a fraction of a second.

The list is DERIVED, never kept by hand: the provider sources name the plugins they use, and each plugin's own
sources name the third-party modules it imports. A vendor that adds a dependency, or a provider that switches
plugin, is followed without touching this file.
"""
from __future__ import annotations

import ast
import importlib
import importlib.util
import threading
import time
from pathlib import Path

from loguru import logger

_PROVIDERS = Path(__file__).resolve().parents[2] / "voice" / "engine" / "llm" / "providers"
_SKIP = ("livekit", "voice", "__future__")     # the plugin packages themselves must stay on the main thread


def _from_imports(path: Path) -> list[tuple[str, list[str]]]:
    """Every absolute import in a source file as (module, names): `import a.b` → ("a.b", []), `from a import b, c` →
    ("a", ["b", "c"]). An unreadable file is logged and yields nothing — the warm is best effort."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError) as e:
        logger.debug(f"voice LLM warm: {path.name} not read: {e!r}")
        return []
    out: list[tuple[str, list[str]]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.extend((a.name, []) for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            out.append((node.module, [a.name for a in node.names]))
    return out


def plugins_used() -> list[str]:
    """The `livekit.plugins.<x>` packages the voice's LLM providers import, read from their sources."""
    found: set[str] = set()
    for src in sorted(_PROVIDERS.glob("*.py")):
        for module, names in _from_imports(src):
            if module == "livekit.plugins":
                found.update(f"livekit.plugins.{n}" for n in names)
            elif module.startswith("livekit.plugins."):
                found.add(".".join(module.split(".")[:3]))
    return sorted(found)


def vendor_modules() -> list[str]:
    """The third-party modules those plugins import — what is safe, and worth, importing off the main thread.

    The plugin's files are located with `find_spec` (which does NOT execute the package, so nothing registers)."""
    mods: set[str] = set()
    for plugin in plugins_used():
        try:
            spec = importlib.util.find_spec(plugin)
        except (ImportError, ValueError) as e:
            logger.debug(f"voice LLM warm: {plugin} not located: {e!r}")
            continue
        if spec is None or not spec.submodule_search_locations:
            continue
        for loc in spec.submodule_search_locations:
            for src in Path(loc).rglob("*.py"):
                mods.update(module for module, _names in _from_imports(src))
    return sorted(m for m in mods if m.split(".")[0] not in _SKIP)


def warm() -> dict:
    """Import every vendor module (best effort — a missing optional SDK is skipped). Returns a small report."""
    t0 = time.perf_counter()
    ok = failed = 0
    for name in vendor_modules():
        try:
            importlib.import_module(name)
            ok += 1
        except Exception as e:  # noqa: BLE001 — an optional SDK absent here is the provider's problem, not boot's
            failed += 1
            logger.debug(f"voice LLM warm: {name} not imported: {e!r}")
    return {"imported": ok, "skipped": failed, "seconds": round(time.perf_counter() - t0, 3)}


def start() -> threading.Thread:
    """Fire-and-forget at boot: a daemon thread, so the loop never waits for it and a stop never waits on it."""
    def _run():
        try:
            r = warm()
            logger.info(f"voice LLM vendor SDKs warmed off the loop: {r['imported']} modules in {r['seconds']} s")
        except Exception as e:  # noqa: BLE001 — a failed warm only means the session pays the import as before
            logger.warning(f"voice LLM vendor warm skipped: {e!r}")
    t = threading.Thread(target=_run, name="warm-voice-llm-sdks", daemon=True)
    t.start()
    return t
