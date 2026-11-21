"""What the model READS and what the agent SAYS calls a widget a «widget», never an «app» (INI-068 F5).

Measured: the operator said «open activity» and the agent answered «The activity app is already up in front of you»
— it had been told, in its prompts, its spoken replies and the widgets' own declarations, that the Activity widget
was an «app». «App» is Zaelar itself (the phone app), a provider's app (Spotify, WhatsApp's own app) or the
operator's own word (the recognisers keep it as a synonym); it is never the name of one of our widgets.

Scope — every place the model reads or the agent speaks from:
  (a) every string value of `i18n/genesis/{en,es}/voice.json`;
  (b) the text fields of every `widgets/*/manifest.json` (`description`, `desc`, `usage`, `whenToUse`, `how`, … —
      never `aliases`/`keywords`, which are HIS words, nor `instant`, a declaration the model never reads);
  (c) the string literals (by `ast`: no comments, no docstrings, no log/trace lines) of the model-facing modules
      listed in `MODULES`.

ALLOWLIST is a RATCHET: an entry is a legitimate «app» (a provider's app, Zaelar's own app, the operator's words, a
code identifier). It may only SHRINK — a new entry needs the same justification in its comment, and a widget is
never one.
"""

import ast
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
APP = re.compile(r"\b(apps?|Apps?|APPS?|aplicaci[oó]n(es)?)\b")

#: The model-facing Python modules (prompts, tool descriptions, verdict questions, digests, results it reads).
MODULES = (
    "nucleo/acts/card_pass.py", "nucleo/acts/repair_of_a_view.py", "nucleo/acts/search.py",
    "nucleo/agentes/code.py", "nucleo/circuit/__init__.py", "nucleo/circuit/compose.py", "nucleo/circuit/spec.py",
    "nucleo/circuit/spec_declares.py", "nucleo/circuit/verdict.py", "nucleo/circuit/verify.py",
    "nucleo/cli/report.py", "nucleo/cli/worker_api.py", "nucleo/cli/worker_api_exec.py", "nucleo/cli/worker_policy.py",
    "nucleo/dispatch/confirm.py", "nucleo/flash/build_decision.py", "nucleo/acts/bulk_close.py",
    "nucleo/flash/capability_gap.py", "nucleo/flash/compose_rung.py", "nucleo/flash/escalation_guard.py",
    "nucleo/flash/router_catalog.py", "nucleo/acts/show_target.py", "nucleo/flash/unclear_turn.py",
    "nucleo/flash/widget_read_tool.py", "nucleo/request/kind.py", "nucleo/request/stop.py",
    "nucleo/turn/brief_screen.py", "nucleo/turn/prompt/operating.py", "nucleo/turn/prompt/packs/introduction_block.py",
    "nucleo/workers/prompts/context.py", "nucleo/workers/prompts/playbook.py", "nucleo/workers/prompts/research.py",
    "nucleo/workers/prompts/surfaces.py", "nucleo/workers/prompts/web.py", "nucleo/workers/providers/generator.py",
    "voice/observer.py", "voice/screens.py", "rules/labels.py",
    "widgets/aliases.py", "widgets/brief.py", "widgets/confirm.py", "widgets/refs.py", "widgets/server_api.py",
    "widgets/state_render.py", "widgets/contactos/digest.py", "widgets/contactos/group_actions.py",
    "widgets/contactos/lookup.py", "widgets/mensajeria/held.py", "widgets/mensajeria/inbox_read.py",
    "widgets/mensajeria/outbound/queue.py", "widgets/musica/browse.py", "widgets/musica/digest.py",
    "widgets/navegador/data.py", "widgets/navegador/owner_actions.py", "widgets/results/digest.py",
)

#: A call whose string arguments are a log or trace line (the observability reads them, the model does not).
_LOG_CALLS = {"debug", "info", "warning", "error", "exception", "critical", "emit", "_emit", "_note", "note", "_say"}

#: Manifest keys that are never prose for the model: his words, and the `instant` declaration.
_NOT_PROSE = {"aliases", "keywords", "instant"}

#: (file, key path or snippet) → why this «app» is not a widget. ONLY SHRINKS.
ALLOWLIST = {
    # voice.json — the provider's own app (Spotify / the service that owns the track).
    ("i18n/genesis/en/voice.json", "music.spotify.needs_app_phone"): "the provider's phone app",
    ("i18n/genesis/en/voice.json", "music.spotify.needs_app"): "the provider's app",
    ("i18n/genesis/en/voice.json", "music.outcome_reasons.needs_app"): "the service's own app",
    ("i18n/genesis/es/voice.json", "music.spotify.needs_app"): "the provider's app",
    ("i18n/genesis/es/voice.json", "music.outcome_reasons.needs_app"): "the service's own app",
    # voice.json — the word the agent must NOT say: «app» is named to forbid it.
    ("i18n/genesis/en/voice.json", "widget_read.task"): "«Never say «app»» — the word is quoted to forbid it",
    ("i18n/genesis/es/voice.json", "widget_read.task"): "«Nunca digas «app»» — the word is quoted to forbid it",
    # manifests — Zaelar's phone app, and the third-party messaging apps.
    ("widgets/activity/manifest.json", "description"): "«In the phone app» = Zaelar's iOS/Android app",
    ("widgets/mensajeria/manifest.json", "actions.read.desc"): "«su app real» = WhatsApp/Telegram/mail's own app",
    ("widgets/mensajeria/manifest.json", "actions.unread.desc"): "«su app real» = the channel's own app",
    ("widgets/mensajeria/manifest.json", "actions.readchat.desc"): "«su app real» = the channel's own app",
    ("widgets/mensajeria/manifest.json", "actions.dismiss.desc"): "«no toca su app» = the channel's own app",
    ("widgets/mensajeria/manifest.json", "actions.hide.desc"): "«leídos en la app» = the channel's own app",
    ("widgets/mensajeria/manifest.json", "actions.load_more.desc"): "«la app real (Telegram/correo/WhatsApp)»",
    ("widgets/mensajeria/manifest.json", "actions.send_to.payload.files"): "files he attached in Zaelar's app",
    ("widgets/mensajeria/manifest.json", "usage"): "«PROPAGA a la app real» = the channel's own app",
    # Python — the operator's words, OS apps, third-party apps and code identifiers.
    ("nucleo/flash/router_catalog.py", "'apps' (widgets)"): "the `panel` enum value `apps` (a code identifier)",
    ("widgets/brief.py", "navegador/apps del sistema"): "the operating system's own apps",
}


def _voice_strings(code: str):
    path = f"i18n/genesis/{code}/voice.json"

    def walk(o, key):
        if isinstance(o, dict):
            for k, v in o.items():
                yield from walk(v, f"{key}.{k}" if key else k)
        elif isinstance(o, list):
            for i, v in enumerate(o):
                yield from walk(v, f"{key}[{i}]")
        elif isinstance(o, str):
            yield path, key, o

    yield from walk(json.loads((ROOT / path).read_text(encoding="utf-8")), "")


def _manifest_strings():
    for f in sorted((ROOT / "widgets").glob("*/manifest.json")):
        if f.parent.name.startswith("_"):
            continue
        path = f.relative_to(ROOT).as_posix()

        def walk(o, key):
            if isinstance(o, dict):
                for k, v in o.items():
                    if k not in _NOT_PROSE:
                        yield from walk(v, f"{key}.{k}" if key else k)
            elif isinstance(o, list):
                for i, v in enumerate(o):
                    yield from walk(v, key)
            elif isinstance(o, str):
                yield path, key, o

        yield from walk(json.loads(f.read_text(encoding="utf-8")), "")


def _module_strings(path: str):
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    skip = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and body \
                and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            skip.add(id(body[0].value))
        if isinstance(node, ast.Call):
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            if name in _LOG_CALLS:
                for arg in list(node.args) + [k.value for k in node.keywords]:
                    for sub in ast.walk(arg):
                        skip.add(id(sub))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip:
            yield path, node.value, node.value


def _allowed(path: str, key: str) -> bool:
    return any(p == path and (k == key or k in key) for p, k in ALLOWLIST)


def _offenders(items):
    return [f"{path} · {key[:80]!r}: …{text[max(0, m.start() - 50):m.end() + 30]}…"
            for path, key, text in items for m in [APP.search(text)] if m and not _allowed(path, key)]


@pytest.mark.parametrize("code", ["en", "es"])
def test_no_spoken_or_prompted_string_calls_a_widget_an_app(code: str) -> None:
    bad = _offenders(_voice_strings(code))
    assert not bad, "voice.json strings that call a widget «app» (say «widget»):\n" + "\n".join(bad)


def test_no_widget_declaration_calls_a_widget_an_app() -> None:
    bad = _offenders(_manifest_strings())
    assert not bad, "manifest text that calls a widget «app» (say «widget»):\n" + "\n".join(bad)


@pytest.mark.parametrize("path", MODULES)
def test_no_model_facing_literal_calls_a_widget_an_app(path: str) -> None:
    bad = _offenders(_module_strings(path))
    assert not bad, f"{path}: literals that call a widget «app» (say «widget»):\n" + "\n".join(bad)


def test_the_allowlist_only_names_what_still_exists() -> None:
    """A stale entry is a hole the next «app» walks through: every entry must still match a real string."""
    seen = {(p, k) for p, k, _t in [*_voice_strings("en"), *_voice_strings("es"), *_manifest_strings(),
                                    *(s for m in MODULES for s in _module_strings(m))]
            if APP.search(_t)}
    stale = [e for e in ALLOWLIST if not any(p == e[0] and (k == e[1] or e[1] in k) for p, k in seen)]
    assert not stale, f"allowlist entries that match nothing any more (remove them — the list only shrinks): {stale}"
