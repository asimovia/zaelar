"""An exception with an EMPTY message still names itself in the log and the timeline (V2-831 T-19 R3).

Demo pass on a sandbox at build 86: the INIT step «Remember: Laura…» died with
`nucleo fast brain error (not spoken raw): ` — nothing after the colon. The provider had answered 200; the
exception was an `httpx.ReadError` raised while the body streamed, and `str()` of it is the empty string. The
handler logged `{e}`, so the one line meant to explain the failure explained nothing.

Class: every voice-turn handler that reports an exception as `{e}` / `str(e)` loses the exceptions whose message
is empty (`ReadError()`, `TimeoutError()`, `CancelledError()`…). They report it as `{e!r}` (type + args), the
fast-brain handler through `turn_failure.log_named` (plus the traceback at debug), and an AST guard keeps
`voice/engine/` from formatting a caught exception bare again.

Disarm: make `turn_failure.log_named` format `{e}` → the behavioural tests go red; put `{e}` back in the
fast-brain handler → the guard goes red.
"""
from __future__ import annotations

import ast
import pathlib


ENGINE = pathlib.Path(__file__).resolve().parents[3]


def _read_error():
    import httpx
    return httpx.ReadError("")


# ── THE GUARD: no handler under voice/engine formats its caught exception bare ─────────────────────────────
def _bare_uses(path: pathlib.Path) -> list[str]:
    """`file:line` of every log/emit call, inside an `except … as NAME`, that formats NAME as `{NAME}` (no `!r`,
    no `type(NAME)` in the same string) or passes `str(NAME)` — the forms that print nothing for an empty
    message."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    rel = path.relative_to(ENGINE) if path.is_relative_to(ENGINE) else path
    out = []
    for h in ast.walk(tree):
        if not (isinstance(h, ast.ExceptHandler) and h.name):
            continue
        nm = h.name
        for call in (n for b in h.body for n in ast.walk(b) if isinstance(n, ast.Call)):
            f = call.func
            fname = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
            if fname not in ("debug", "info", "warning", "error", "exception", "critical", "emit"):
                continue
            for arg in [*call.args, *(k.value for k in call.keywords)]:
                for node in ast.walk(arg):
                    if isinstance(node, ast.JoinedStr):
                        typed = any(isinstance(c, ast.Call) and getattr(c.func, "id", "") == "type"
                                    and c.args and getattr(c.args[0], "id", "") == nm for c in ast.walk(node))
                        bare = any(isinstance(v, ast.FormattedValue) and v.conversion != ord("r")
                                   and isinstance(v.value, ast.Name) and v.value.id == nm
                                   for v in node.values)
                        if bare and not typed:
                            out.append(f"{rel}:{node.lineno}")
                    elif (isinstance(node, ast.Call) and getattr(node.func, "id", "") == "str"
                          and node.args and getattr(node.args[0], "id", "") == nm):
                        out.append(f"{rel}:{node.lineno}")
    return out


#: Outside the voice turn path, owned elsewhere: the TTS fallback note. May only shrink.
_KNOWN = {"voice/engine/speech/tts/kokoro.py"}


def test_no_voice_engine_handler_formats_its_exception_bare():
    offenders = [o for py in sorted((ENGINE / "voice/engine").rglob("*.py")) if "__pycache__" not in str(py)
                 for o in _bare_uses(py) if o.split(":")[0] not in _KNOWN]
    assert not offenders, ("a handler logs/emits its exception as `{e}`/`str(e)` — an exception with an empty "
                           "message leaves no trace; use `{e!r}` or `turn_failure.log_named`:\n  "
                           + "\n  ".join(offenders))


def test_the_guard_sees_the_shape_it_forbids(tmp_path):
    """A guard aimed at nothing stays green: it must flag the exact line that hid the ReadError."""
    p = tmp_path / "probe.py"
    p.write_text('try:\n    pass\nexcept Exception as e:\n'
                 '    logger.warning(f"nucleo fast brain error (not spoken raw): {e}")\n', encoding="utf-8")
    assert _bare_uses(p), "the guard does not see `{e}` inside a handler"
