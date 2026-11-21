"""What the Observatory's screens READ — cheap readers over `tests/runs/`, cached by mtime.

The Observatory is for JUDGING, not for watching what the agent does: the raw trace already has a home (the
agent's own ◷ viewer, served by every sandbox on its port), so nothing here rebuilds a trace. Every reader answers one question of one screen and links out for anything deeper:

  · `running()`       — who is testing right now and how far along (the live runs' event logs, tailed once)
  · `sandboxes()`     — the kept use-case workspaces and the lab: locale, port, alive or kept, age, size
  · `home()`          — the home's NUMBERS: unit (last sweep), benches (run / green / red), use cases ES|US by theme
  · `results()`       — the last result per SET: unit sweeps (`watchdog-*.json`), benches, use cases ES/US
  · `scoreboard()`    — `tests/use_cases/status.json` summarised per tier × locale, with the stale rows
  · `unit_sets()`     — suites → folders with the last sweep each folder got
  · `benches()`       — the module benches of `tests/README.md` §Module benches, with their last run file
  · `usecase_sets()`  — the catalog by tier and theme with the verdict per case
  · `rounds()`        — every judged round on disk (`report_*.json`) and every unjudged one (`pending/`)
  · `round_view()`    — ONE round read as a verdict with its evidence (the judge viewer)
  · `turn_flow()`     — ONE turn of ONE round, the stations of the turn pipeline it crossed (the brain screen)

Everything reads files; nothing calls a model and nothing launches anything (V2-709). A reader that cannot read
says so in its payload (`readable: false`, `matched_by: "none"`) instead of returning an empty structure that
looks like a healthy, idle system — the same rule `verify.py` keeps for the mechanism report.
"""
from __future__ import annotations

import glob
import json
import os
import re
import sqlite3
import time
import urllib.parse
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
ENGINE = HERE.parents[1]
TESTS = HERE.parent

# ── a tiny mtime cache ────────────────────────────────────────────────────────────────────────────────────────
# Keyed by name + the (path, mtime, size) of every file the builder depends on. A screen polls every few
# seconds; a sweep report does not change between polls. TTL-only entries exist for things with no single
# file to key on (a directory walk, a port probe).
_CACHE: dict[str, tuple[Any, Any, float]] = {}
_STALE_LOCK = __import__("threading").Lock()


def _sig(paths) -> tuple:
    out = []
    for p in paths:
        try:
            st = Path(p).stat()
            out.append((str(p), st.st_mtime, st.st_size))
        except OSError:
            out.append((str(p), 0, 0))
    return tuple(out)


def cached(name: str, paths, builder: Callable[[], Any], ttl: float = 0.0) -> Any:
    key = (name, _sig(paths))
    hit = _CACHE.get(name)
    now = time.monotonic()
    if hit and hit[0] == key and (not ttl or now - hit[2] < ttl):
        return hit[1]
    value = builder()
    _CACHE[name] = (key, value, now)
    return value


def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


_STAMP = re.compile(r"(\d{8})-(\d{6})")


def stamp_epoch(name: str) -> float:
    """`20261104-131310` anywhere in a name → epoch seconds (local time), or 0."""
    m = _STAMP.search(name)
    if not m:
        return 0.0
    try:
        return time.mktime(time.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S"))
    except ValueError:
        return 0.0


def ledger_path(root: Path | None = None) -> Path:
    """`tests/use_cases/status.json` of the tests tree the runs root belongs to. The ledger is local (gitignored), so
    a server started from a worktree against the main checkout's runs reads the main checkout's ledger."""
    if root is not None:
        beside = root.resolve().parent / "use_cases" / "status.json"
        if beside.exists():
            return beside
    return TESTS / "use_cases" / "status.json"


def _rel(root: Path, p: Path) -> str:
    try:
        return str(p.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(p)


# ═══ 1 · RUNNING NOW ═════════════════════════════════════════════════════════════════════════════════════════
class RunProgress:
    """Incremental reader of one run's `events.jsonl`: how many tests, how many done, which one is in flight.

    The file is read from the last position each time, so a 7 000-node sweep costs one pass, not one per poll.
    Counts ACTIONS the way the live view does: a pytest node is one, a use case is its plan plus its turns."""

    def __init__(self, run_dir: Path) -> None:
        self.path = run_dir / "events.jsonl"
        self.pos = 0
        self.total = 0
        self.done = 0
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self.current: dict = {}
        self.reds: list[str] = []
        self.turns = 0
        self.turn_budget = 0
        self.step = ""
        self.last_ts = 0.0

    def update(self) -> None:
        try:
            with self.path.open("rb") as fh:
                fh.seek(self.pos)
                while line := fh.readline():
                    if not line.endswith(b"\n"):
                        break
                    self.pos = fh.tell()
                    try:
                        e = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    self._take(e)
        except OSError:
            return

    def _take(self, e: dict) -> None:
        t = e.get("type")
        self.last_ts = float(e.get("ts") or self.last_ts)
        if t == "test.discovered":
            self.total = max(self.total, int(e.get("total") or 0), int(e.get("index") or 0))
        elif t == "collection.finished":
            self.total = max(self.total, int(e.get("total") or 0))
        elif t == "test.started":
            self.current = {"test_id": e.get("test_id", ""), "label": e.get("label") or e.get("test_id", ""),
                            "locale": e.get("locale", ""), "tier": e.get("tier", 0), "since": e.get("ts")}
            self.turns = 0
            self.turn_budget = int(e.get("turns") or 0)
            self.step = ""
        elif t == "test.finished":
            self.done += 1
            st = e.get("status")
            if st == "passed":
                self.passed += 1
            elif st == "failed" or e.get("state") == "FAIL":
                self.failed += 1
                self.reds.append(e.get("label") or e.get("test_id") or "?")
            else:
                self.skipped += 1
            if self.current.get("test_id") == e.get("test_id"):
                self.current = {}
        elif t == "step.started":
            self.step = e.get("label") or e.get("step") or ""
        elif t == "interaction.input":
            self.turns += 1

    def row(self) -> dict:
        cur = dict(self.current)
        if cur:
            cur["step"] = self.step
            if self.turns:
                cur["turn"] = self.turns
                cur["turn_budget"] = self.turn_budget
        return {"total": self.total, "done": self.done, "passed": self.passed, "failed": self.failed,
                "skipped": self.skipped, "current": cur, "reds": self.reds[-6:], "last_event_at": self.last_ts}


def running(server, progress: dict[str, RunProgress]) -> list[dict]:
    """One row per LIVE run (status running, not stale). `progress` is the server's per-run reader cache."""
    rows = []
    for run_dir in server.run_dirs():
        meta = server.run_meta(run_dir)
        if not meta or meta.get("status") != "running" or meta.get("stale"):
            continue
        rp = progress.get(meta["run_id"])
        if rp is None:
            rp = progress[meta["run_id"]] = RunProgress(run_dir)
        rp.update()
        by = meta.get("launched_by") or {}
        actor = by.get("actor") or "@".join(filter(None, [by.get("user"), by.get("parent_command")])) \
            or by.get("host") or "agente"
        rows.append({"run_id": meta["run_id"], "actor": actor, "suite": meta.get("suite", ""),
                     "target": meta.get("target", ""), "started_at": meta.get("created_at", 0),
                     "elapsed_s": round(time.time() - float(meta.get("created_at") or time.time()), 1),
                     **rp.row()})
    # Forget readers of runs that are no longer live, so the dict does not grow with the directory.
    live = {r["run_id"] for r in rows}
    for rid in [k for k in progress if k not in live]:
        progress.pop(rid, None)
    rows.sort(key=lambda r: r["started_at"])
    return rows


# ═══ 2 · SANDBOXES ═══════════════════════════════════════════════════════════════════════════════════════════
def _locale_of_dir(name: str) -> str:
    suffix = name.rsplit("-", 1)[-1].lower()
    return {"es": "es", "en": "us", "us": "us"}.get(suffix, "")


def _dir_size(p: Path) -> int:
    total = 0
    try:
        for root, _dirs, files in os.walk(p):
            for f in files:
                try:
                    total += os.lstat(os.path.join(root, f)).st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total


_SIZES: dict[str, tuple[float, int]] = {}        # path → (computed_at, bytes)
_SIZING: set[str] = set()


def _size_async(p: Path, ttl: float = 300.0) -> int | None:
    """The workspace's size, or None while a daemon thread walks it. A kept sandbox holds a Chromium profile —
    thousands of files — and fifty of them measured 2.8 s on the home screen's first paint. The number can wait
    one poll; the screen cannot."""
    import threading
    key = str(p)
    hit = _SIZES.get(key)
    if hit and time.monotonic() - hit[0] < ttl:
        return hit[1]
    with _STALE_LOCK:
        if key in _SIZING:
            return hit[1] if hit else None
        _SIZING.add(key)

    def work():
        try:
            n = _dir_size(p)
            _SIZES[key] = (time.monotonic(), n)
        finally:
            with _STALE_LOCK:
                _SIZING.discard(key)
    threading.Thread(target=work, daemon=True, name="observatory-size").start()
    return hit[1] if hit else None


def _engine_status(port: int) -> dict | None:
    from tests.platform import ports
    return ports._answers(port, timeout=0.8) if not ports.is_free(port) else None


def sandboxes(root: Path) -> dict:
    """The kept sandbox workspaces (`use_cases/sandbox/<stamp>-<lang>`) and the lab's, newest first.

    ALIVE is decided by the PORT (`tests/platform/ports.py`: one fixed port per locale), never by the folder: several kept
    workspaces of one locale share the port, so only the last-booted one of a locale can be answering, and the row
    says `alive` only when something answers there AND identifies as a zaelar engine."""
    from tests.platform import ports

    def build():
        out = []
        for kind in ("sandbox", "lab"):
            base = root / "use_cases" / kind
            try:
                entries = sorted((e for e in os.scandir(base) if e.is_dir()), key=lambda e: e.name, reverse=True)
            except OSError:
                continue
            for e in entries:
                p = Path(e.path)
                loc = _locale_of_dir(e.name)
                db = p / "memory" / "_data" / "sandbox.db"
                try:
                    mtime = max(e.stat().st_mtime, db.stat().st_mtime if db.exists() else 0)
                except OSError:
                    mtime = 0
                out.append({"name": e.name, "kind": kind, "path": str(p), "locale": loc,
                            "port": ports.sandbox_port(loc) if loc else 0,
                            "stamp": stamp_epoch(e.name) or mtime, "mtime": mtime,
                            "size": _size_async(p),
                            "has_db": db.exists(), "has_config": (p / "config").exists(),
                            "alive": False, "engine": None})
        # the port probe, once per locale
        for loc in ("es", "us"):
            port = ports.sandbox_port(loc)
            st = cached(f"engine:{port}", [], lambda port=port: _engine_status(port), ttl=5)
            if not st:
                continue
            candidate = next((r for r in out if r["locale"] == loc and r["kind"] == "sandbox"), None) \
                or next((r for r in out if r["locale"] == loc), None)
            if candidate:
                build = next((str((it.get("extra") or {}).get("short") or it.get("detail") or "")
                              for it in (st.get("items") or []) if it.get("key") == "version"), "")
                candidate["alive"] = True
                candidate["engine"] = {"url": f"http://127.0.0.1:{port}", "version": build}
        return {"schema": 1, "now": time.time(), "sandboxes": out}

    return cached("sandboxes", [root / "use_cases" / "sandbox", root / "use_cases" / "lab"], build, ttl=5)


# ═══ 3 · ROUNDS (judged and pending) ═════════════════════════════════════════════════════════════════════════
def _locale_of_result(r: dict) -> str:
    loc = ((r.get("run") or {}).get("mechanism_report") or {}).get("locale")
    if loc in ("es", "us"):
        return loc
    sid = str(r.get("scenario") or "")
    return "us" if sid.endswith("__us") else "es"


def _state_of_result(r: dict, ledger_row: dict | None) -> str:
    """The scoreboard's state for this result. The ledger wrote it with the full rule (`status._state`); when the
    ledger has no row for this exact round, the same thresholds are applied to what the result carries."""
    if ledger_row and ledger_row.get("last_run") and r.get("_stamp_min") == ledger_row.get("last_run"):
        return str(ledger_row.get("state") or "")
    if r.get("_infra_reason") or str((r.get("run") or {}).get("crashed") or "").strip():
        return "INFRA"
    v = r.get("verdict") or {}
    if not v:
        return "PENDING"
    if str(v.get("veredicto") or "").startswith("INFRA"):
        return "INFRA"
    if r.get("data_limit") or ((r.get("run") or {}).get("mechanism_report") or {}).get("data_limit"):
        return "CAPPED"
    try:
        return "PASS" if float(v.get("overall")) >= 4 else "FAIL"
    except (TypeError, ValueError):
        return "INFRA"


def _first_turn_at(r: dict) -> float:
    for t in (r.get("run") or {}).get("transcript") or []:
        try:
            return float(t.get("at") or 0)
        except (TypeError, ValueError):
            continue
    return 0.0


def rounds(root: Path) -> list[dict]:
    """Every round on disk, newest first: one row per RESULT inside a `report_*.json` (a batch of three cases is
    three rounds) and one per unjudged file in `pending/`. `file` + `idx` are the handle the viewer takes."""
    uc = root / "use_cases"
    files = sorted(glob.glob(str(uc / "report_*.json"))) + sorted(glob.glob(str(uc / "pending" / "*.json")))

    def build():
        ledger = _json(ledger_path(root)) or {}
        scen = ledger.get("scenarios") or {}
        out = []
        for f in files:
            p = Path(f)
            data = _json(p)
            if not isinstance(data, dict):
                continue
            pending = p.parent.name == "pending"
            results = [data] if pending else list(data.get("results") or [])
            for idx, r in enumerate(results):
                if not isinstance(r, dict):
                    continue
                sid = str(r.get("scenario") or "")
                at = _first_turn_at(r) or stamp_epoch(p.name)      # an INFRA round that never spoke: its file's stamp
                r["_stamp_min"] = time.strftime("%Y-%m-%d %H:%M", time.localtime(at)) if at else ""
                v = r.get("verdict") or {}
                row = scen.get(sid) or {}
                out.append({
                    "file": p.name, "dir": p.parent.name if pending else "", "idx": idx,
                    "scenario": sid, "locale": _locale_of_result(r), "tier": r.get("tier"),
                    "channel": r.get("channel", ""), "stamp": data.get("stamp") if not pending else "",
                    "started_at": at, "finished_at": _last_turn_at(r),
                    "state": _state_of_result(r, row), "overall": v.get("overall"),
                    "scores": v.get("scores") or {}, "veredicto": v.get("veredicto") or "",
                    "judge": v.get("_judge_model") or "", "pending": pending,
                    "missing_signals": ((r.get("run") or {}).get("mechanism_report") or {}).get("missing_signals") or [],
                    "code": r.get("code") or {}, "report_md": f"use_cases/report_{data.get('stamp')}.md" if not pending else "",
                    "report_json": _rel(root, p),
                })
        out.sort(key=lambda x: x["started_at"], reverse=True)
        return out

    return cached("rounds", files + [ledger_path(root)], build)


def _last_turn_at(r: dict) -> float:
    at = 0.0
    for t in (r.get("run") or {}).get("transcript") or []:
        try:
            at = max(at, float(t.get("at") or 0))
        except (TypeError, ValueError):
            pass
    return at


def _sandbox_for(root: Path, locale: str, started_at: float) -> dict | None:
    """The kept workspace that MADE a round, matched by time: the newest workspace of the round's locale whose boot
    stamp precedes the first turn — within a six-hour window, because a batch reuses one sandbox across cases.
    The fallback for rounds written before the harness emitted `run.workspace` (see `_sandbox_of_round`)."""
    if not started_at:
        return None
    best = None
    for s in sandboxes(root)["sandboxes"]:
        if s["locale"] != locale or s["kind"] != "sandbox":
            continue
        if s["stamp"] <= started_at + 2 and started_at - s["stamp"] < 6 * 3600:
            if best is None or s["stamp"] > best["stamp"]:
                best = s
    return best


def _sandbox_of_round(root: Path, r: dict, locale: str, started_at: float) -> dict | None:
    """The workspace that MADE a round: the one the round names (`run.workspace`, emitted by the harness since V2-856),
    else the guess by time for rounds written before the emit. `matched_by` says which."""
    ws = str((r.get("run") or {}).get("workspace") or "")
    if ws:
        want = os.path.realpath(ws)
        for s in sandboxes(root)["sandboxes"]:
            if os.path.realpath(s["path"]) == want:
                return {**s, "matched_by": "emitted"}
        if os.path.isdir(ws):    # outside the runs root (a lab of another checkout): still the round's own
            from tests.platform import ports
            db = Path(ws) / "memory" / "_data" / "sandbox.db"
            return {"name": Path(ws).name, "kind": "sandbox", "path": ws, "locale": locale, "alive": False,
                    "port": ports.sandbox_port(locale) if locale else 0, "has_db": db.exists(), "engine": None,
                    "stamp": 0, "matched_by": "emitted"}
        return None              # it named a workspace that is gone (pruned): never guess another one in its place
    best = _sandbox_for(root, locale, started_at)
    return best and {**best, "matched_by": "time"}


# ═══ 4 · LAST RESULTS PER SET ════════════════════════════════════════════════════════════════════════════════
def watchdog_files(root: Path) -> list[Path]:
    return sorted(Path(p) for p in glob.glob(str(root / "watchdog-*.json")))


def _sweep_summary(p: Path) -> dict | None:
    d = _json(p)
    if not isinstance(d, dict):
        return None
    res = list(d.get("results") or [])
    totals = d.get("totals") or {}
    failures, hung = [], []
    for r in res:
        if r.get("hung_at"):
            hung.append(f"{r.get('target')} · {r.get('hung_at')}")
        for f in r.get("failures") or []:
            node = f.get("node") if isinstance(f, dict) else str(f)
            if node and node not in failures:
                failures.append(node)
    verdicts = {r.get("verdict") for r in res}
    verdict = "hung" if hung else ("failed" if ("failed" in verdicts or failures) else ("ok" if res else "empty"))
    counts = {"passed": 0, "failed": 0}
    for r in res:
        for k, v in (r.get("counts") or {}).items():
            counts[k] = counts.get(k, 0) + int(v or 0)
    return {"file": p.name, "at": stamp_epoch(p.name) or p.stat().st_mtime, "verdict": verdict,
            "seconds": round(sum(float(r.get("seconds") or 0) for r in res), 1), "targets": len(res),
            "counts": counts, "totals": totals, "reds": failures[:12], "n_reds": len(failures), "hung": hung,
            "by_target": {r.get("target"): {"verdict": r.get("verdict"), "seconds": r.get("seconds"),
                                            "counts": r.get("counts") or {}, "hung_at": r.get("hung_at"),
                                            "failures": [f.get("node") if isinstance(f, dict) else str(f)
                                                         for f in (r.get("failures") or [])]}
                          for r in res}}


def unit_results(root: Path) -> dict:
    """The unit sweeps: the newest, the one before (for the trend), and the latest verdict per target folder."""
    files = watchdog_files(root)

    def build():
        sums = [s for s in (_sweep_summary(p) for p in files[-12:]) if s]
        latest_by_target: dict[str, dict] = {}
        for s in sums:                       # oldest → newest, so the newest wins
            for tgt, r in s["by_target"].items():
                latest_by_target[tgt] = {**r, "at": s["at"], "file": s["file"]}
        last = sums[-1] if sums else None
        prev = sums[-2] if len(sums) > 1 else None
        trend = None
        if last and prev:
            trend = {"reds": last["n_reds"] - prev["n_reds"],
                     "seconds": round(last["seconds"] - prev["seconds"], 1),
                     "prev_at": prev["at"], "prev_verdict": prev["verdict"]}
        for s in sums:
            s.pop("by_target", None)
        return {"last": last, "prev": prev, "trend": trend, "history": sums[-8:], "by_target": latest_by_target}

    return cached("unit_results", files[-12:], build)


#: The module benches — the table in `tests/README.md` §Module benches, with the run file each one leaves (when it
#: leaves one). `test_the_sets_screen_browses_three_layers.py` pins this list to that table.
BENCHES: tuple[dict, ...] = (
    {"id": "search", "module": "search (`search/`)", "command": "python -m tests.search.live.bench",
     "measures": "the same cases to every index, judged blind: route, failover, quality per provider",
     "glob": "search-bench-*.json", "kind": "search"},
    {"id": "memory", "module": "memory", "command": "python -m tests run memory --case memory::group::1.4::v4",
     "measures": "extraction and discard over the real memory gateway; six months of ageing, REM and recall; the API",
     "glob": "", "kind": ""},
    {"id": "task-engine", "module": "task engine (the brain)", "command": "pytest tests/agent_headless/e2e/task_battery",
     "measures": "C01–C15 over a sandbox through the headless chat: questions, resumption, settle, stop, rules, a killed worker",
     "glob": "", "kind": ""},
    {"id": "play-routing", "module": "request routing (fast brain + playbook)",
     "command": "python -m tests.agent_headless.e2e.play_routing.bench [--only A1,C3]",
     "measures": "~30 orders by text on ONE sandbox: the play/route destination per order, the actions that ran, the widget state each declares, the play/step walk of a send, and sameness of one order sent three times",
     "glob": "", "kind": ""},
    {"id": "scrape", "module": "browser extraction", "command": "python -m tests.scrape.live.bench",
     "measures": "what the extractor gets out of recorded pages", "glob": "scrape-bench-*.json", "kind": "scrape"},
    {"id": "voice", "module": "voice", "command": "python -m tests.voice.e2e.mic.mic_selftest · tests/voice/bench/",
     "measures": "the microphone→STT path; the screen and acts questions against the real fast model",
     "glob": "", "kind": ""},
    {"id": "prompt-cost", "module": "prompt cost",
     "command": "python -m tests.agent_headless.e2e.prompt_cost.bench_fast_model · …bench_tools",
     "measures": "tokens and latency per turn, with and without the tools", "glob": "", "kind": ""},
    {"id": "personas", "module": "personas", "command": "python -m tests.agent_headless.harness.run",
     "measures": "a synthetic multi-turn dialogue scored by a judge", "glob": "", "kind": ""},
    {"id": "connectors", "module": "connectors", "command": "python -m tests.connectors.live.bench [--send]",
     "measures": "mail and Telegram through the card's own door on a running engine: fetch, read, search, summarise; with `--send`, one marked line to each private test contact and the read-back that proves it left",
     "glob": "connectors-bench-*.json", "kind": "connectors"},
    {"id": "speech", "module": "speech", "command": "python -m tests.voice.bench.speech_bench",
     "measures": "every STT and TTS we can build over fixed phrases ES/EN: word error rate and latency per recogniser, first audio and round-trip WER per voice, and a TTS failover whose stand-in must really speak",
     "glob": "speech-bench-*.json", "kind": "speech"},
    {"id": "jev", "module": "turn brief (Jev)", "command": "tests/runs/jev-bench/*.json (written by the brief bench)",
     "measures": "one question of the brief over fixed phrases: wanted vs got, confidence, latency",
     "glob": "jev-bench/*.json", "kind": "jev"},
)


def _bench_numbers(kind: str, d: Any) -> dict:
    """The headline numbers of one bench run file, by kind. `headline` is ONE number the trend compares."""
    if not isinstance(d, dict):
        return {}
    if kind == "search":
        summ = d.get("summary") or {}
        best = max(summ.items(), key=lambda kv: float((kv[1] or {}).get("score") or 0), default=(None, {}))
        return {"at": d.get("at"), "judge": d.get("judge"), "mode": d.get("mode"), "cases": len(d.get("rows") or []),
                "providers": {k: {"score": v.get("score"), "lat_s": v.get("lat_s"), "errors": v.get("errors")}
                              for k, v in summ.items()},
                "headline": float((best[1] or {}).get("score") or 0), "headline_label": f"best index {best[0]} score"}
    if kind == "scrape":
        rows = d.get("rows") or []
        met = sum(1 for r in rows if r.get("met"))
        return {"at": d.get("at"), "sites": len(rows), "met": met,
                "failed": [f"{r.get('site')} ({r.get('n', 0)}/{r.get('floor', '?')})" for r in rows if not r.get("met")],
                "headline": met, "headline_label": f"sites over their floor of {len(rows)}"}
    if kind == "connectors":
        rows = [r for r in d.get("rows") or [] if r.get("ok") is not None]
        ok = sum(1 for r in rows if r.get("ok"))
        return {"at": d.get("at"), "sent": d.get("sent"), "steps": len(rows), "ok": ok,
                "failed": [f"{r.get('platform')} {r.get('step')}: {r.get('why')}"[:90] for r in rows if not r.get("ok")][:6],
                "headline": ok, "headline_label": f"steps ok of {len(rows)}" + ("" if d.get("sent") else " (nothing sent)")}
    if kind == "speech":
        summ = d.get("summary") or {}
        stt = {k[4:]: v for k, v in summ.items() if k.startswith("stt:")}
        best = min(stt.items(), key=lambda kv: float(kv[1].get("wer") or 1), default=(None, {}))
        fo = d.get("failover") or {}
        return {"at": d.get("at"), "providers": summ, "failover": fo,
                "failed": sorted({f"{k} {r.get('provider')}: {str(r.get('why'))[:60]}" for k in ("stt", "tts")
                                  for r in d.get(k) or [] if r.get("ok") is False})[:6],
                "headline": float(best[1].get("wer") or 0) if best[0] else None,
                "headline_label": f"best STT word error rate ({best[0]})" + (" · failover BROKEN" if fo.get("ok") is False else "")}
    if kind == "jev":
        rows = d.get("rows") or []
        hit = sum(1 for r in rows if r.get("got") == r.get("want"))
        lat = [float(r.get("ms") or 0) for r in rows if r.get("ms")]
        return {"question": d.get("question"), "phrases": len(rows), "hit": hit,
                "misses": sorted({str(r.get("phrase"))[:70] for r in rows if r.get("got") != r.get("want")})[:6],
                "ms_avg": round(sum(lat) / len(lat)) if lat else None,
                "headline": hit, "headline_label": f"answers as wanted of {len(rows)}"}
    return {}


def benches(root: Path) -> list[dict]:
    """The bench table with, for each bench that leaves a run file, its newest run and the trend vs the previous."""
    def build():
        out = []
        for b in BENCHES:
            row = {k: v for k, v in b.items() if k != "glob"}
            files = sorted(glob.glob(str(root / b["glob"]))) if b["glob"] else []
            row["runs_on_disk"] = len(files)
            row["last"] = None
            row["trend"] = None
            if files:
                p = Path(files[-1])
                last = _bench_numbers(b["kind"], _json(p))
                last.update({"file": _rel(root, p), "at_epoch": stamp_epoch(p.name) or p.stat().st_mtime})
                row["last"] = last
                if len(files) > 1:
                    prev = _bench_numbers(b["kind"], _json(Path(files[-2])))
                    if prev.get("headline") is not None and last.get("headline") is not None:
                        row["trend"] = {"headline": round(last["headline"] - prev["headline"], 2),
                                        "prev_at": stamp_epoch(Path(files[-2]).name)}
            out.append(row)
        return out

    watched = [root] + [Path(p) for b in BENCHES if b["glob"] for p in glob.glob(str(root / b["glob"]))[-2:]]
    return cached("benches", watched, build, ttl=10)


def usecase_results(root: Path) -> dict:
    """The last batch per locale, from the round files when there are any and from the ledger otherwise (the ledger
    keeps the verdicts after `retention.py` has pruned the files: `source` says which one answered)."""
    def build():
        rows = rounds(root)
        out: dict[str, Any] = {}
        for loc in ("es", "us"):
            mine = [r for r in rows if r["locale"] == loc and not r["pending"]]
            batches: dict[str, list] = {}
            for r in mine:
                batches.setdefault(r["stamp"] or r["file"], []).append(r)
            ordered = sorted(batches.values(), key=lambda b: max(x["started_at"] for x in b), reverse=True)
            if ordered:
                last, prev = ordered[0], (ordered[1] if len(ordered) > 1 else None)
                out[loc] = {"source": "reports", **_batch_summary(last),
                            "trend": _batch_trend(last, prev) if prev else None}
                continue
            out[loc] = _ledger_batch(loc, root)
        return out

    files = sorted(glob.glob(str(root / "use_cases" / "report_*.json")))
    return cached("usecase_results", files + [ledger_path(root)], build)


def _batch_summary(batch: list[dict]) -> dict:
    states = {}
    for r in batch:
        states[r["state"]] = states.get(r["state"], 0) + 1
    start = min(r["started_at"] for r in batch)
    end = max(r["finished_at"] or r["started_at"] for r in batch)
    if not any(r["finished_at"] for r in batch):
        end = start                                        # no turn ever spoke: a duration would be invented
    return {"at": start, "seconds": round(end - start, 1), "n": len(batch), "states": states,
            "reds": [{"scenario": r["scenario"], "overall": r["overall"], "file": r["file"], "idx": r["idx"],
                      "veredicto": r["veredicto"][:160]} for r in batch if r["state"] == "FAIL"][:8],
            "stamp": batch[0]["stamp"], "report_md": batch[0]["report_md"],
            "rounds": [{"scenario": r["scenario"], "state": r["state"], "overall": r["overall"],
                        "file": r["file"], "idx": r["idx"]} for r in batch]}


def _batch_trend(last: list[dict], prev: list[dict]) -> dict:
    p = lambda b: sum(1 for r in b if r["state"] == "PASS")    # noqa: E731
    return {"pass": p(last) - p(prev), "prev_at": min(r["started_at"] for r in prev), "prev_n": len(prev)}


def _ledger_batch(loc: str, root: Path) -> dict:
    ledger = _json(ledger_path(root)) or {}
    rows = []
    for sid, row in (ledger.get("scenarios") or {}).items():
        rloc = "us" if sid.endswith("__us") else "es"
        if rloc == loc and row.get("last_run"):
            rows.append((row["last_run"], sid, row))
    if not rows:
        return {"source": "ledger", "at": 0, "n": 0, "states": {}, "reds": [], "trend": None}
    rows.sort(key=lambda x: x[0], reverse=True)
    day = rows[0][0][:10]
    batch = [(at, sid, row) for at, sid, row in rows if at[:10] == day]
    states: dict[str, int] = {}
    for _at, _sid, row in batch:
        states[row.get("state", "?")] = states.get(row.get("state", "?"), 0) + 1
    try:
        at = time.mktime(time.strptime(batch[-1][0], "%Y-%m-%d %H:%M"))
        end = time.mktime(time.strptime(batch[0][0], "%Y-%m-%d %H:%M"))
    except ValueError:
        at, end = 0.0, 0.0
    return {"source": "ledger", "at": at, "seconds": round(end - at, 1), "n": len(batch), "states": states,
            "reds": [{"scenario": sid, "overall": row.get("overall"), "veredicto": (row.get("verdict") or "")[:160]}
                     for _at, sid, row in batch if row.get("state") == "FAIL"][:8],
            "trend": None, "note": "the round files of this day were pruned; the ledger keeps the verdicts"}


def results(root: Path) -> dict:
    unit = {k: v for k, v in unit_results(root).items() if k != "by_target"}
    return {"schema": 1, "now": time.time(), "unit": unit, "benches": benches(root),
            "use_cases": usecase_results(root), "scoreboard": {k: v for k, v in scoreboard(root).items() if k != "rows"}}


# ═══ 5 · SCOREBOARD SUMMARY ══════════════════════════════════════════════════════════════════════════════════
def _git_head() -> str:
    try:
        import subprocess
        return subprocess.run(["git", "rev-parse", "--short=9", "HEAD"], cwd=str(ENGINE), capture_output=True,
                              text=True, timeout=5).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


_STALE: dict = {"key": None, "ready": False, "by_sha": {}}


def _stale_flags(shas: set[str], head: str, key) -> dict | None:
    """`sha → stale?` for every sha the ledger measured, computed ONCE per (ledger, HEAD) in a background thread.
    `settle.stale` runs one `git diff` per distinct sha (~40 on this ledger, ~0.1 s each): fine once, not on the
    home screen's first paint. Until the thread is done the caller gets None and says `stale_ready: false`."""
    import threading
    from tests.use_cases.e2e.agent import settle
    with _STALE_LOCK:
        if _STALE["key"] == key:
            return dict(_STALE["by_sha"]) if _STALE["ready"] else None
        _STALE.update(key=key, ready=False, by_sha={})

    def work():
        out = {}
        for sha in shas:
            try:
                out[sha] = settle.stale({"code": {"sha": sha}}, head or "HEAD")
            except Exception:  # noqa: BLE001
                out[sha] = True
        with _STALE_LOCK:
            if _STALE["key"] == key:
                _STALE.update(ready=True, by_sha=out)
        _CACHE.pop(f"scoreboard:{key[0]}", None)       # the next read folds the flags in
    threading.Thread(target=work, daemon=True, name="observatory-stale").start()
    return None


def scoreboard(root: Path | None = None) -> dict:
    """`status.json` folded per tier × locale, plus the STALE rows (the code they measured is not HEAD any more —
    `settle.stale`, product paths only) and the settled verdict per row (`settle.kk`)."""
    path = ledger_path(root)

    def build():
        from tests.use_cases.e2e.agent import settle
        data = _json(path) or {}
        scen = data.get("scenarios") or {}
        head = _git_head()
        try:
            key = (str(path), path.stat().st_mtime, head)
        except OSError:
            key = (str(path), 0, head)
        flags = _stale_flags({str((row.get("code") or {}).get("sha") or "") for row in scen.values()}, head, key)
        cells: dict[str, dict] = {}
        stale_rows, by_state = [], {}
        rows_out = {}
        for sid, row in scen.items():
            loc = "us" if sid.endswith("__us") else "es"
            tier = int(row.get("tier") or 0)
            cell = cells.setdefault(f"{tier}:{loc}", {"tier": tier, "locale": loc, "total": 0,
                                                       "PASS": 0, "FAIL": 0, "INFRA": 0, "CAPPED": 0, "stale": 0})
            st = str(row.get("state") or "")
            cell["total"] += 1
            if st in cell:
                cell[st] += 1
            by_state[st] = by_state.get(st, 0) + 1
            sha = str((row.get("code") or {}).get("sha") or "")
            is_stale = None if flags is None else bool(flags.get(sha, True))
            kk = settle.kk(row)
            if is_stale:
                cell["stale"] += 1
                stale_rows.append({"id": sid, "state": st, "last_run": row.get("last_run"), "sha": sha})
            rows_out[sid] = {"state": st, "overall": row.get("overall"), "last_run": row.get("last_run"),
                             "tier": tier, "locale": loc, "stale": is_stale, "kk": kk,
                             "sha": sha, "blind_turns": row.get("blind_turns"),
                             "infra_reason": row.get("infra_reason"), "verdict": row.get("verdict", ""),
                             "scores": row.get("scores") or {}, "rounds_n": len(row.get("rounds") or []),
                             "brain": row.get("brain", ""), "judge": row.get("judge", "")}
        stale_rows.sort(key=lambda r: r["last_run"] or "")
        return {"schema": 1, "updated": data.get("updated"), "head": head, "n": len(scen), "by_state": by_state,
                "cells": sorted(cells.values(), key=lambda c: (c["tier"], c["locale"])),
                "stale": stale_rows, "n_stale": len(stale_rows), "stale_ready": flags is not None, "rows": rows_out}

    return cached(f"scoreboard:{path}", [path, ENGINE / ".git" / "HEAD"], build)


# ═══ 5b · THE HOME: NUMBERS ONLY ═════════════════════════════════════════════════════════════════════════════
# Operator, 2026-11-06: the home is a dashboard of COUNTS — how many tests each layer has, how many green, how many
# red — three boxes (unit · benches · use cases), the use cases split ES | US and by theme. Nothing here is a list;
# every number links to the screen that has the rows behind it.
_STATES = ("PASS", "FAIL", "INFRA", "CAPPED")


def unit_numbers(root: Path) -> dict:
    """The last sweep of `tests/watchdog.py` as counts: total, passed, failed (+ errors), skipped, hung."""
    last = unit_results(root)["last"]
    if not last:
        return {"last": None}
    c = last["totals"] if last.get("totals") else last["counts"]
    passed, failed = int(c.get("passed") or 0), int(c.get("failed") or 0) + int(c.get("error") or 0)
    skipped = int(c.get("skipped") or 0)
    return {"last": {"at": last["at"], "file": last["file"], "verdict": last["verdict"], "seconds": last["seconds"],
                     "targets": last["targets"]},
            "total": passed + failed + skipped, "passed": passed, "failed": failed, "skipped": skipped,
            "hung": len(last.get("hung") or []), "reds": last["n_reds"]}


def _bench_verdict(kind: str, last: dict | None) -> str:
    """green / red only where the bench file carries its own all-or-nothing criterion (every site over its floor,
    every step ok, every answer as wanted, a failover that spoke). A score with no threshold is `no_threshold`,
    never a colour; a bench that leaves no file is `no_run`."""
    if not last:
        return "no_run"
    if kind == "scrape":
        return "green" if last.get("sites") and last.get("met") == last.get("sites") else "red"
    if kind == "connectors":
        return "green" if last.get("steps") and last.get("ok") == last.get("steps") else "red"
    if kind == "jev":
        return "green" if last.get("phrases") and last.get("hit") == last.get("phrases") else "red"
    if kind == "speech":
        return "red" if (last.get("failover") or {}).get("ok") is False else "no_threshold"
    return "no_threshold"


def bench_numbers(root: Path) -> dict:
    """The benches of the README table as counts: how many, how many with a run on disk, green, red, no threshold."""
    rows = []
    for b, row in zip(BENCHES, benches(root)):
        last = row.get("last")
        rows.append({"id": row["id"], "module": row["module"], "verdict": _bench_verdict(b["kind"], last),
                     "at": last.get("at_epoch") if last else None,
                     "headline": last.get("headline") if last else None,
                     "headline_label": last.get("headline_label") if last else ""})
    counts = {k: sum(1 for r in rows if r["verdict"] == k) for k in ("green", "red", "no_threshold", "no_run")}
    return {"n": len(rows), "with_run": len(rows) - counts["no_run"], **counts, "rows": rows}


def _uc_cell() -> dict:
    return {"total": 0, "never": 0, **{k: 0 for k in _STATES}}


def usecase_numbers(root: Path) -> dict:
    """The use cases as counts, ES | US: the denominator is the CATALOG's `completable` segment
    (`segments.py` — the cases runnable start to finish today), the state of each is its ledger row
    (`status.json`, the accumulated marker — never the last batch's report, which is one evening's run), a case
    with no row is `never`. Credentials and capability cases are counted APART, not in the total. Below, the same
    per theme (`themes.py`): one row per theme with cases, `es` and `us` side by side."""
    path = ledger_path(root)

    def build():
        from tests.use_cases import themes
        from tests.use_cases.catalog import case_groups
        from tests.use_cases.e2e.agent import segments
        sb = scoreboard(root)
        board = sb["rows"]
        locales = {loc: {**_uc_cell(), "excluded": {segments.CREDENTIALS: 0, segments.CAPABILITY: 0, "": 0}}
                   for loc in ("es", "us")}
        by_theme: dict[str, dict] = {}
        for g in case_groups():
            for c in g["cases"]:
                bare = c["id"].split("::")[-1]
                loc = c.get("locale") or ""
                if loc not in locales:
                    continue
                group = segments.group_of(bare)
                if group != segments.COMPLETABLE:
                    locales[loc]["excluded"][group if group in locales[loc]["excluded"] else ""] += 1
                    continue
                row = board.get(_ledger_key(board, bare, loc))
                state = str(row.get("state") or "") if row else ""
                theme = by_theme.setdefault(themes.theme_of(bare), {"es": _uc_cell(), "us": _uc_cell()})
                for cell in (locales[loc], theme[loc]):
                    cell["total"] += 1
                    if state in _STATES:
                        cell[state] += 1
                    else:
                        cell["never"] += 1
        rows = [{"id": t["id"], "label": t["label"], "hint": t.get("hint", ""), **by_theme[t["id"]]}
                for t in themes.THEMES if t["id"] in by_theme]
        return {"locales": locales, "themes": rows, "updated": sb.get("updated"), "head": sb.get("head"),
                "segment": segments.COMPLETABLE}

    return cached("usecase_numbers", [path, ENGINE / ".git" / "HEAD", TESTS / "use_cases" / "cases_data.py",
                                      TESTS / "use_cases" / "themes.py", TESTS / "use_cases" / "e2e" / "agent" / "segments.py"],
                  build)


def home(root: Path) -> dict:
    """The three boxes of the home. The live agents are added by the server (`running()` needs its tailers)."""
    return {"schema": 1, "now": time.time(), "unit": unit_numbers(root), "benches": bench_numbers(root),
            "use_cases": usecase_numbers(root)}


# ═══ 6 · TEST SETS ═══════════════════════════════════════════════════════════════════════════════════════════
def _sweep_covering(sums: list[dict], folder: str, files: list[str]) -> dict | None:
    """The NEWEST sweep that covered this folder, aggregated over its matching targets. A watchdog target is a folder
    (the default sweep) or a file (`--impacted`): exact folder, a parent folder, or files inside all count."""
    fileset = set(files)
    for s in reversed(sums):
        hits = []
        for tgt, r in s["by_target"].items():
            if tgt == folder or folder.startswith(tgt.rstrip("/") + "/") or tgt in fileset \
                    or (tgt.startswith(folder + "/") and tgt.endswith(".py")):
                hits.append((tgt, r))
        if not hits:
            continue
        verdicts = {r.get("verdict") for _t, r in hits}
        counts: dict[str, int] = {}
        failures: list[str] = []
        hung = [r.get("hung_at") for _t, r in hits if r.get("hung_at")]
        for _t, r in hits:
            for k, v in (r.get("counts") or {}).items():
                counts[k] = counts.get(k, 0) + int(v or 0)
            failures += [f for f in (r.get("failures") or []) if f]
        scope = ("folder" if any(t == folder for t, _r in hits) else
                 "parent" if any(folder.startswith(t.rstrip("/") + "/") for t, _r in hits) else f"{len(hits)} file(s)")
        return {"at": s["at"], "file": s["file"], "scope": scope,
                "verdict": "hung" if hung else "failed" if "failed" in verdicts or failures else "ok",
                "seconds": round(sum(float(r.get("seconds") or 0) for _t, r in hits), 1),
                "counts": counts, "hung_at": hung[0] if hung else None, "failures": sorted(set(failures))}
    return None


def unit_sets(root: Path) -> dict:
    """The deterministic layer by DIRECTORY — `tests/<area>/…` → folders → files — each folder with the last sweep
    that covered it. Folders, because that is the unit the watchdog runs and reports (`watchdog-*.json` targets);
    the suite a folder's tests belong to is a tag, read from the catalog."""
    from tests.platform.catalog import SUITES, deterministic_paths

    def build():
        files = watchdog_files(root)[-12:]
        sums = [x for x in (_sweep_summary(p) for p in files) if x]
        suite_of: dict[str, set[str]] = {}
        for sid in SUITES:
            for p in deterministic_paths(sid):
                suite_of.setdefault(p, set()).add(sid)
        folders: dict[str, list[str]] = {}
        for p in deterministic_paths("all"):
            folders.setdefault(str(Path(p).parent), []).append(p)
        areas: dict[str, dict] = {}
        for folder, members in sorted(folders.items()):
            parts = Path(folder).parts
            area = parts[1] if len(parts) > 1 and parts[0] == "tests" else parts[0]
            sw = _sweep_covering(sums, folder, members)
            red_files = sorted({f.split("::", 1)[0] for f in (sw or {}).get("failures") or []
                                if f.split("::", 1)[0] in members or f.startswith(folder + "/")}) if sw else []
            suites = sorted({sid for m in members for sid in suite_of.get(m, ())})
            row = {"folder": folder, "files": len(members), "suites": suites, "sweep": sw, "red_files": red_files,
                   "hung": bool(sw and sw.get("hung_at")), "exists": (ENGINE / folder).exists()}
            a = areas.setdefault(area, {"id": area, "label": SUITES[area.replace("_", "-")].label
                                        if area.replace("_", "-") in SUITES else area, "folders": [],
                                        "files": 0, "reds": 0, "never_swept": 0, "hung": 0})
            a["folders"].append(row)
            a["files"] += len(members)
            a["reds"] += len(red_files)
            a["never_swept"] += 0 if sw else 1
            a["hung"] += 1 if row["hung"] else 0
        last = sums[-1] if sums else None
        if last:
            last = {k: v for k, v in last.items() if k != "by_target"}
        return {"schema": 1, "areas": sorted(areas.values(), key=lambda a: -a["files"]), "last_sweep": last,
                "sweeps_read": len(sums)}

    return cached("unit_sets", watchdog_files(root)[-12:] + [TESTS / "run_testmap.py"], build)


def _ledger_key(board: dict, bare: str, loc: str) -> str:
    """The ledger row of a catalog case: `<bare>__<loc>`, or the bare id for an ES row written before the suffix
    existed. "" when the case was never judged."""
    if f"{bare}__{loc}" in board:
        return f"{bare}__{loc}"
    return bare if loc == "es" and bare in board else ""


def usecase_sets(root: Path) -> dict:
    """The use-case catalog (language → theme → tier) joined with the verdict per case from the ledger and the
    newest round file of each case, so a row goes from «what we promise» to «how it went» in one click."""
    def build():
        from tests.use_cases import themes
        from tests.use_cases.catalog import case_groups
        board = scoreboard(root)["rows"]
        latest_round: dict[tuple, dict] = {}
        for r in rounds(root):
            key = (r["scenario"], r["locale"])
            if key not in latest_round:
                latest_round[key] = {"file": r["file"], "idx": r["idx"], "state": r["state"],
                                     "overall": r["overall"], "started_at": r["started_at"], "pending": r["pending"]}
        try:
            from tests.use_cases.e2e.agent import phases
            phase_of, parked = phases.phase_of, phases.parked_reason
        except Exception:  # noqa: BLE001
            phase_of, parked = (lambda _s: 0), (lambda _s: "")
        groups = []
        for g in case_groups():
            cases = []
            for c in g["cases"]:
                bare = c["id"].split("::")[-1]
                loc = c.get("locale") or ""
                ledger_key = _ledger_key(board, bare, loc)
                row = board.get(ledger_key) if ledger_key else None
                sid = ledger_key or bare
                cases.append({"id": c["id"], "scenario": sid, "title": c["title"], "locale": loc,
                              "tier": int((c.get("raw") or {}).get("tier") or c.get("input", {}).get("tier") or 0),
                              "theme": c.get("theme", ""), "status": (c.get("raw") or {}).get("status", ""),
                              "utterance": (c.get("input") or {}).get("utterance", ""),
                              "outcome": (c.get("expected") or {}).get("outcome", ""),
                              "phase": phase_of(bare), "parked": parked(bare),
                              "verdict": row, "latest_round": latest_round.get((sid, loc)) or latest_round.get((bare, loc))})
            groups.append({"id": g["id"], "label": g.get("label", g["id"]), "hint": g.get("hint", ""), "cases": cases})
        return {"schema": 1, "themes": [{"id": t["id"], "label": t["label"], "hint": t.get("hint", "")} for t in themes.THEMES],
                "groups": groups, "n": sum(len(g["cases"]) for g in groups)}

    return cached("usecase_sets", [ledger_path(root), TESTS / "use_cases" / "cases_data.py",
                                   root / "use_cases"] + sorted(glob.glob(str(root / "use_cases" / "report_*.json")))[-3:], build)


# ═══ 7 · THE JUDGE VIEWER ════════════════════════════════════════════════════════════════════════════════════
_TURN_REF = re.compile(r"(tester|zaelar|user|usuario)?@?turn\s*(\d+)(?:\s*[-–]\s*(\d+))?", re.I)


def _turns_cited(ref: str) -> list[int]:
    """`zaelar@turn2`, `turn2-5`, `tester@turn3` → the turn indexes a finding cites; [] when unanchored."""
    m = _TURN_REF.search(str(ref or ""))
    if not m:
        return []
    a = int(m.group(2))
    b = int(m.group(3)) if m.group(3) else a
    return list(range(a, b + 1)) if b >= a else [a]


def load_round(root: Path, file: str, idx: int) -> tuple[dict | None, dict | None, Path | None]:
    """(result, report, path) for a round handle. `file` is a basename — never a path — under `use_cases/` or
    `use_cases/pending/`: a handle that walks out of those two folders reads nothing."""
    if not file or "/" in file or "\\" in file or file.startswith(".") or not file.endswith(".json"):
        return None, None, None
    for p in (root / "use_cases" / file, root / "use_cases" / "pending" / file):
        if p.is_file():
            data = _json(p)
            if not isinstance(data, dict):
                return None, None, p
            if p.parent.name == "pending":
                return data, {"stamp": "", "results": [data], "pending": True}, p
            results = data.get("results") or []
            if 0 <= idx < len(results):
                return results[idx], data, p
            return None, data, p
    return None, None, None


def _check(cid: str, label: str, status: str, measured: str, expected: str = "", evidence: str = "",
           where: str = "") -> dict:
    """One row of the mechanism checklist. `status`: ok · bad · info · na. `where` names the field of the report
    JSON that holds the proof, so a developer can open exactly that and nothing else."""
    return {"id": cid, "label": label, "status": status, "measured": measured, "expected": expected,
            "evidence": evidence, "where": where}


def mechanism_checks(r: dict) -> list[dict]:
    """The mechanism report read as a CHECKLIST — each expected signal with what was measured and the one field
    that proves it. Mirrors what `judge.mechanism_facts` tells the judge, as rows instead of prose."""
    mech = ((r.get("run") or {}).get("mechanism_report") or {})
    out: list[dict] = []
    if not mech:
        return [_check("report", "mechanism report", "na", "none — the verification could not run; absence proves nothing")]
    fam = set(mech.get("families_observed") or [])
    ev = mech.get("signal_evidence") or {}     # the first event behind each signal (V2-856); older rounds name the family

    def _proof(sig: str) -> str:
        e = ev.get(sig) or {}
        return " · ".join(x for x in (f"event #{e['id']}" if e.get("id") else "", e.get("corr_id") or "", e.get("label") or "") if x) or sig

    for sig in mech.get("expected_signals") or []:
        present = sig in fam
        out.append(_check(f"signal:{sig}", f"signal «{sig}» fired", "ok" if present else "bad",
                          "observed" if present else "MISSING", "the case expects it", _proof(sig) if present else sig,
                          f"mechanism_report.signal_evidence.{sig}" if sig in ev else "mechanism_report.families_observed"))
    for sig in mech.get("overreach_signals") or []:
        out.append(_check(f"forbidden:{sig}", f"signal «{sig}» must NOT fire", "bad", "fired", "forbidden by the case",
                          _proof(sig), f"mechanism_report.signal_evidence.{sig}" if sig in ev else "mechanism_report.overreach_signals"))
    sr = mech.get("search_returns") or {}
    if sr.get("queries") or "search" in (mech.get("expected_signals") or []):
        late = int(sr.get("returns_after_last_turn") or 0)
        out.append(_check("search", "search fired and reached the brain",
                          "ok" if sr.get("queries") and (sr.get("notes_from_search") or sr.get("inline_returns") or not sr.get("returns")) else ("info" if sr.get("queries") else "bad"),
                          f"{sr.get('queries', 0)} queries · {sr.get('returns', 0)} returns · {sr.get('notes_from_search', 0)} notes to the brain"
                          + (f" · {late} after the last turn" if late else ""),
                          "a query, and its answer read by a turn", "", "mechanism_report.search_returns"))
    sh = mech.get("results_sheet") or {}
    si = mech.get("sheet_instances") or {}
    if si.get("n_opens") or sh.get("n_items") or sh.get("read") is False:
        if not sh.get("read"):
            st, measured = "na", "could not be read (not the same as empty)"
        elif sh.get("n_named"):
            st = "ok" if int(sh.get("n_backed") or 0) >= int(sh.get("n_named") or 0) else "info"
            measured = f"{sh['n_named']} named of {sh.get('n_items', 0)} rows · {sh.get('n_backed', 0)} with a source"
        else:
            st, measured = ("bad" if si.get("n_opens") else "info"), f"opened {si.get('n_opens', 0)}× · {sh.get('n_items', 0)} rows, none named"
        out.append(_check("sheet", "results sheet written", st, measured, "one sheet per errand, rows with a source",
                          ", ".join(si.get("ids") or []), "mechanism_report.results_sheet"))
        if si.get("shared"):
            out.append(_check("sheet:shared", "one sheet per errand", "bad", "two errands shared a box", "",
                              ", ".join(si.get("ids") or []), "mechanism_report.sheet_instances.shared"))
    stg = mech.get("sheet_timing") or {}
    if stg.get("sheet_ms"):
        named = stg.get("sheet_named_ms")
        lag = stg.get("delivery_lag_s")
        out.append(_check("timing", "first candidate row, and when the turn named it",
                          "ok" if named and (lag is None or lag < 60) else ("bad" if not named else "info"),
                          (f"{round((named - stg['sheet_ms']) / 1000, 1)} s after the sheet opened" if named else "NEVER arrived")
                          + (f" · named {lag} s after it existed" if lag is not None else "")
                          + (f" · clock: {stg['delivery_clock']}" if stg.get("delivery_clock") else ""),
                          "rows before the turn claims them", "", "mechanism_report.sheet_timing"))
    wh = mech.get("worker_health") or {}
    q = mech.get("quiescence") or {}
    if wh.get("spawned") or "worker" in (mech.get("expected_signals") or []):
        bad = bool(wh.get("errored") or wh.get("still_running"))
        out.append(_check("worker", "task row settled (Brain Worker)", "bad" if bad else ("ok" if wh.get("spawned") else "info"),
                          f"{wh.get('spawned', 0)} spawned · {wh.get('ok', 0)} ok · {wh.get('errored', 0)} errored · "
                          f"{wh.get('still_running', 0)} still running · {wh.get('cancelled', 0)} cancelled"
                          + (f" · engine still working when measured ({q.get('waited_s')} s waited)" if q.get("settled") is False else ""),
                          "every worker ends, the circuit writes the ending",
                          ", ".join(((mech.get("audit") or {}).get("spans") or {}).keys()), "mechanism_report.worker_health"))
    dup = mech.get("duplicate_errands") or {}
    if dup.get("groups"):
        out.append(_check("dup", "one worker per errand", "bad",
                          f"{len(dup['groups'])} group(s) of repeated escalations · worst {dup.get('worst')}", "",
                          "; ".join(str(g.get("goal"))[:60] for g in dup["groups"][:2]), "mechanism_report.duplicate_errands"))
    sj = mech.get("scheduled_jobs") or {}
    if sj.get("readable") and (sj.get("created") or "agenda" in str(mech.get("widget_ops_by_turn") or "")):
        created = sj.get("created") or []
        out.append(_check("notice", "notice scheduled", "ok" if created else "bad",
                          f"{len(created)} job(s) created" + (": " + "; ".join(f"{j.get('name')} @ {j.get('schedule')}" for j in created[:3]) if created else ""),
                          "a job with the right moment", "", "mechanism_report.scheduled_jobs.created"))
    am = mech.get("agenda_meetings")
    if isinstance(am, list) and am:
        out.append(_check("agenda", "agenda row written", "ok",
                          "; ".join(f"{m.get('title')} {m.get('date')} {m.get('startTime')}" for m in am[:3]), "",
                          "", "mechanism_report.agenda_meetings"))
    gw = mech.get("ghost_widgets") or {}
    ow = mech.get("open_widgets_by_turn") or {}
    if gw.get("observed") or ow.get("max_open"):
        ghosts = gw.get("ghosts") or []
        out.append(_check("cards", "cards opened only when asked", "bad" if ghosts else "ok",
                          f"{ow.get('max_open', 0)} open at most ({', '.join(ow.get('kinds') or [])})"
                          + (f" · {len(ghosts)} ghost card(s): " + ", ".join(g.get("id", "?") for g in ghosts) if ghosts else ""),
                          "no card without an owner", "", "mechanism_report.ghost_widgets"))
    mc = mech.get("market_claims_before_delivery") or {}
    tb = mech.get("told_but_given_no_rows") or {}
    dn = mech.get("delivered_by_name") or {}
    if mc.get("measurable") or dn.get("n") or tb.get("n"):
        n_false = int(mc.get("n") or 0) + int(tb.get("n") or 0)
        out.append(_check("claims", "no claim without rows behind it", "bad" if n_false else "ok",
                          (f"{n_false} unbacked claim(s) at turn(s) {', '.join(str(t) for t in (mc.get('turns') or []) + (tb.get('turns') or []))}"
                           if n_false else f"none · {dn.get('n', 0)} candidate(s) named from the sheet"),
                          "a name said is a row that exists", "", "mechanism_report.market_claims_before_delivery"))
    pm = mech.get("price_mismatches") or []
    if pm:
        out.append(_check("prices", "prices said match the sheet", "bad", f"{len(pm)} mismatch(es)", "",
                          "; ".join(str(p)[:60] for p in pm[:2]), "mechanism_report.price_mismatches"))
    da = mech.get("dropped_actions") or []
    if da:
        out.append(_check("dropped", "every action the model called ran", "bad", f"{len(da)} dropped", "",
                          "; ".join(str((d or {}).get("tool") or d)[:40] for d in da[:3]), "mechanism_report.dropped_actions"))
    ml = mech.get("memory_language") or {}
    loc = mech.get("locale") or _locale_of_result(r)
    if ml.get("effective"):
        want = "es" if loc == "es" else "en"
        out.append(_check("lang", "reply language is the case's", "ok" if ml["effective"].startswith(want) else "bad",
                          f"engine language {ml['effective']} ({ml.get('source', '')})", want, "", "mechanism_report.memory_language"))
    au = mech.get("audit") or {}
    if au:
        errs = au.get("errors") or []
        an = au.get("anomalies") or []
        out.append(_check("audit", "stream clean (no internal errors)", "ok" if au.get("clean") else "bad",
                          f"{au.get('n_events', 0)} events · {len(errs)} error(s) · {len(an)} anomaly(ies)"
                          + (f" · gap max {round(au.get('max_gap_ms', 0) / 1000, 1)} s" if au.get("max_gap_ms") else ""),
                          "clean", "; ".join(f"{e.get('span') or e.get('cat')}: {str(e.get('text'))[:70]}" for e in errs[:2]),
                          "mechanism_report.audit"))
    pj = mech.get("page_journey") or {}
    if pj.get("n_walls"):
        out.append(_check("walls", "the outside world let us in", "info",
                          f"{pj['n_walls']} page(s) closed the door: " + "; ".join(str(w.get("why"))[:30] for w in pj.get("walls") or []),
                          "— not the product's fault", "", "mechanism_report.page_journey.walls"))
    pe = mech.get("provider_exhausted") or {}
    if pe.get("deaths") or pe.get("asleep"):
        out.append(_check("provider", "model providers answered", "info",
                          f"{pe.get('deaths')} death(s) · {pe.get('asleep')} asleep · {', '.join(pe.get('providers') or [])}",
                          "", "", "mechanism_report.provider_exhausted"))
    for st in mech.get("script_checks") or []:
        ok = st.get("ok") is True
        out.append(_check(f"script:{st.get('step')}", f"script step {st.get('step')}: {str(st.get('check'))[:60]}",
                          "ok" if ok else "bad", "met" if ok else "NOT met — a «done» over this is a false claim",
                          str(st.get("said"))[:80], "", "mechanism_report.script_checks"))
    gu = mech.get("ground_truth_unreadable")
    if gu:
        out.append(_check("unreadable", "the engine could be read", "na", f"{len(gu) if isinstance(gu, list) else gu} read failure(s)",
                          "", "", "mechanism_report.ground_truth_unreadable"))
    return out


def round_view(root: Path, file: str, idx: int = 0) -> dict:
    """ONE round as a developer's hand-off: the blocker, the scores, the state and its reason, how to reproduce it,
    the sandbox and its ◷ viewer, the settle state; the mechanism as a checklist; the conversation with markers."""
    r, report, path = load_round(root, file, idx)
    if not r:
        return {"schema": 1, "readable": False, "file": file, "idx": idx,
                "why": "no such round file" if path is None else "the file has no result at that index"}
    run = r.get("run") or {}
    mech = run.get("mechanism_report") or {}
    v = r.get("verdict") or {}
    sid = str(r.get("scenario") or "")
    loc = _locale_of_result(r)
    started = _first_turn_at(r)
    r["_stamp_min"] = time.strftime("%Y-%m-%d %H:%M", time.localtime(started)) if started else ""
    board = scoreboard(root)["rows"]
    ledger_row = board.get(sid)
    state = _state_of_result(r, (_json(ledger_path(root)) or {}).get("scenarios", {}).get(sid))
    sb = _sandbox_of_round(root, r, loc, started)
    _eng = (sb.get("engine") or {}).get("url") if sb and sb.get("alive") else ""

    # the conversation, turn by turn, with the markers
    transcript = list(run.get("transcript") or [])
    turn_actions = {int(t.get("turn", -1)): t for t in (mech.get("turn_actions") or []) if isinstance(t, dict)}
    ops_by_turn = mech.get("widget_ops_by_turn") or {}
    open_by_turn = (mech.get("open_widgets_by_turn") or {}).get("by_turn") or {}
    claim_turns = set((mech.get("market_claims_before_delivery") or {}).get("turns") or []) \
        | set((mech.get("told_but_given_no_rows") or {}).get("turns") or [])
    named_turns = set((mech.get("delivered_by_name") or {}).get("turns") or [])
    findings = list(v.get("findings") or [])
    notes_by_turn: dict[int, list] = {}
    unanchored = []
    for f in findings:
        cited = _turns_cited(f.get("turno"))
        if not cited:
            unanchored.append(f)
        for t in cited:
            notes_by_turn.setdefault(t, []).append(f)
    # the judge's per-criterion notes, keyed to the turns that decided each score (`por_criterio`, V2-856); a round
    # judged before the field has scores only, and the screen shows them unanchored
    criteria: dict[str, dict] = {}
    for name, score in (v.get("scores") or {}).items():
        pc = (v.get("por_criterio") or {}).get(name) or {}
        refs = pc.get("turnos") or []
        refs = refs if isinstance(refs, list) else [refs]
        cited = sorted({t for ref in refs for t in _turns_cited(ref)})
        criteria[name] = {"score": score, "note": str(pc.get("nota") or ""), "turns": cited}
        for t in cited:
            notes_by_turn.setdefault(t, []).append({"turno": f"zaelar@turn{t}", "gravedad": "criterio",
                                                    "problema": f"{name} {score}: {pc.get('nota') or ''}".strip()})
    stg = mech.get("sheet_timing") or {}
    named_ms = stg.get("sheet_named_ms")
    turns, k, first_mute, first_claim, lag_turn = [], -1, None, None, None
    for i, t in enumerate(transcript):
        who = t.get("who", "")
        if who == "tester":
            k += 1
        text = (t.get("text") or "").strip()
        at = float(t.get("at") or 0)
        row = {"i": i, "turn": k, "who": who, "text": text, "at": at,
               "rel_s": round(at - started, 1) if at and started else None, "markers": []}
        if t.get("corr_id"):
            row["corr_id"] = str(t["corr_id"])
            if _eng:   # the agent's own ◷ viewer, opened on this turn's flow (`?trace=`)
                row["viewer"] = f"{_eng}/?trace={urllib.parse.quote(row['corr_id'], safe='')}"
        if who != "tester":
            if not text or text == "(sin respuesta)":
                row["markers"].append({"kind": "mute", "text": "mute turn — the agent said nothing"})
                if first_mute is None:
                    first_mute = k
            if k in claim_turns:
                row["markers"].append({"kind": "claim", "text": "claim with no rows behind it"})
                if first_claim is None:
                    first_claim = k
            if k in named_turns:
                row["markers"].append({"kind": "named", "text": "names candidates from the sheet"})
            if named_ms and at and lag_turn is None and at * 1000 >= named_ms:
                lag = stg.get("delivery_lag_s")
                row["markers"].append({"kind": "delivery", "text": "first turn after the rows existed"
                                       + (f" · lag {lag} s" if lag is not None else "")})
                lag_turn = k
            ta = turn_actions.get(k)
            if ta:
                row["action"] = ta.get("action", "")
                row["asked"] = ta.get("pedido") or []
                row["executed"] = ta.get("ejecutado", "")
            if ops_by_turn.get(f"t{k}"):
                row["widget_ops"] = ops_by_turn[f"t{k}"]
            if open_by_turn.get(f"t{k}") is not None:
                row["open_cards"] = open_by_turn[f"t{k}"]
            row["notes"] = notes_by_turn.get(k, [])
        turns.append(row)
    wd = list(run.get("watchdog_log") or [])

    kk = (ledger_row or {}).get("kk") or {"n": 0, "pass": 0, "settled": "UNSETTLED"}
    code = r.get("code") or {}
    repro = f"python -m tests.use_cases.e2e.agent.run --scenario {sid} --sandbox"
    out = {
        "schema": 1, "readable": True, "file": file, "idx": idx, "pending": bool((report or {}).get("pending")),
        "scenario": sid, "locale": loc, "tier": r.get("tier"), "channel": r.get("channel", ""),
        "stamp": (report or {}).get("stamp", ""), "started_at": started, "finished_at": _last_turn_at(r),
        "state": state, "infra_reason": r.get("_infra_reason") or (ledger_row or {}).get("infra_reason"),
        "data_limit": r.get("data_limit") or mech.get("data_limit"),
        "overall": v.get("overall"), "scores": v.get("scores") or {}, "criteria": criteria,
        "blocker": v.get("veredicto") or "",
        "judge": v.get("_judge_model") or "", "gates": v.get("gates"),
        "drive_model": r.get("drive_model", ""), "brain": mech.get("brains") or {},
        "code": code, "machine": r.get("machine") or {}, "reproduce": repro,
        "sandbox": sb and {"name": sb["name"], "path": sb["path"], "alive": sb["alive"], "port": sb["port"],
                           "engine_url": (sb.get("engine") or {}).get("url") or f"http://127.0.0.1:{sb['port']}",
                           "has_db": sb["has_db"], "matched_by": sb["matched_by"]},
        "settle": {**kk, "stale": (ledger_row or {}).get("stale"), "rounds_n": (ledger_row or {}).get("rounds_n", 0),
                   "ledger_sha": (ledger_row or {}).get("sha", ""), "head": scoreboard(root)["head"]},
        "checks": mechanism_checks(r),
        "signals": {"expected": mech.get("expected_signals") or [], "missing": mech.get("missing_signals") or [],
                    "observed": mech.get("families_observed") or [], "forbidden": mech.get("forbidden_signals") or [],
                    "overreach": mech.get("overreach_signals") or []},
        "turns": turns, "n_turns": k + 1, "first_mute": first_mute, "first_claim": first_claim, "lag_turn": lag_turn,
        "findings_unanchored": unanchored, "improvements": v.get("improvements") or [],
        "watchdog": wd, "blind_turns": (ledger_row or {}).get("blind_turns"),
        "links": {"report_json": _rel(root, path) if path else "",
                  "report_md": f"use_cases/report_{(report or {}).get('stamp')}.md" if (report or {}).get("stamp") else "",
                  "flow_api": (f"{(sb.get('engine') or {}).get('url')}/api/observability/flows?limit=30"
                               if sb and sb.get("alive") else "")},
        # What THIS round does not carry because it was written before the harness emitted it (V2-856) — said on
        # the screen instead of painting a hole; the screen then falls back to matching by time or text.
        "missing": [m for m, has in (
            ("the workspace it ran in (matched by time instead: `sandbox.matched_by`)", bool(run.get("workspace"))),
            ("the corr_id of each turn (the brain screen matches the turn's text instead)",
             any(t.get("corr_id") for t in transcript)),
            ("the turns behind each score (`por_criterio`)", bool(v.get("por_criterio")) or not v.get("scores")),
            ("the first event behind each signal (`signal_evidence`)", "signal_evidence" in mech or not mech),
        ) if not has],
    }
    return out


# ═══ 8 · THE BRAIN SCREEN — one turn, the stations it crossed ════════════════════════════════════════════════
# MIRRORED: a private operator console keeps a copy of this section (CONV_STATIONS with its _conv_* readers) and of
# dashboard/brain.js in its `brainMap.js`. A change to a station, to the events that light it or to the state it shows
# is made in BOTH places in the same batch. (The old turn pipeline's picture, `STATIONS`, went with it, INI-078 L1.)


def _payload(row: dict) -> dict:
    p = row.get("payload")
    if isinstance(p, str):
        try:
            p = json.loads(p)
        except json.JSONDecodeError:
            p = {}
    return p if isinstance(p, dict) else {}


def _open_ro(db: Path) -> sqlite3.Connection | None:
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=1.0)
        con.row_factory = sqlite3.Row
        return con
    except sqlite3.Error:
        return None


def _flow_rows(con: sqlite3.Connection, corr_id: str, limit: int = 1500) -> list[dict]:
    try:
        cur = con.execute("SELECT id, ts_ms, cat, kind, label, span, ms, model, payload FROM events "
                          "WHERE topic='observer' AND corr_id=? ORDER BY id ASC LIMIT ?", (corr_id, limit))
        return [dict(x) for x in cur.fetchall()]
    except sqlite3.Error:
        return []


def _find_turn(con: sqlite3.Connection, text: str, at: float, emitted: str | None = None) -> tuple[str, str]:
    """The `corr_id` of a turn: the one the round recorded (`corr_id` on the transcript row, V2-856); for older rounds,
    the root trace that carries this exact tester line, then by time (±8 s). Returns (corr_id, matched_by)."""
    if emitted:
        return str(emitted), "emitted"
    try:
        rows = con.execute("SELECT corr_id, ts_ms, payload FROM events WHERE topic='observer' AND cat='flash' "
                           "AND kind='trace' AND label='turno' ORDER BY id ASC").fetchall()
    except sqlite3.Error:
        return "", "none"
    want = (text or "").strip()
    for row in rows:
        if want and (_payload(dict(row)).get("text") or "").strip() == want and row["corr_id"]:
            return str(row["corr_id"]), "text"
    if at:
        near = [(abs(float(row["ts_ms"]) / 1000 - at), row) for row in rows if row["corr_id"]]
        near.sort(key=lambda x: x[0])
        if near and near[0][0] <= 8:
            return str(near[0][1]["corr_id"]), "time"
    return "", "none"


def _kv(k: str, v: Any) -> dict:
    return {"k": k, "v": v if isinstance(v, (int, float, bool)) or v is None else str(v)[:220]}


#: The conversation package's pipeline (`conversation/`, V2-941): a SECOND picture, chosen when the flow carries
#: `conv_*` events, so the sessions of the old path keep painting with the stations above. Each station is lit by its
#: `conv_*` kind (`conversation/telemetry.py` is the only source of kinds and labels); the run's `prompt` label is
#: the composer's, every other `conv_run` label is the run's.
CONV_STATIONS: tuple[dict, ...] = (
    {"id": "ear", "label": "Ear", "module": "conversation/ear", "hint": "words · end of turn · reopen"},
    {"id": "inbox", "label": "Inbox", "module": "conversation/inbox", "hint": "accepted · held · coalesced · accounted"},
    {"id": "compose", "label": "Composer", "module": "conversation/composer", "hint": "the prompt, read from the store"},
    {"id": "model", "label": "Run · model", "module": "conversation/manager/run.py", "hint": "first token · command · superseded"},
    {"id": "gateway", "label": "Effect gateway", "module": "conversation/gateway", "hint": "sealed · claimed · submitted · receipt"},
    {"id": "ledger", "label": "Ledger", "module": "conversation/ledger", "hint": "items opened · attached · moved"},
    {"id": "mouth", "label": "Mouth", "module": "conversation/mouth", "hint": "said · heard · cut"},
    {"id": "close", "label": "Close", "module": "conversation/manager/loop.py", "hint": "answered · handed off · silent · stalled"},
)
CONV_STATION_IDS = tuple(s["id"] for s in CONV_STATIONS)
#: The payload fields a `conv_*` event carries that say its state (plan F0 §8.2), shown in this order when present.
_CONV_FIELDS = ("closed_by", "eot_prob", "eot_source", "wait_ms", "surfacing", "held_behind", "queue_age_ms",
                "prompt_tokens", "ttft_ms", "command", "superseded_by", "port", "tool", "effect_class", "authority",
                "by", "item", "item_kind", "from", "to", "decided_by", "waiting_on", "channels", "chars",
                "heard_chars", "outcome", "total_ms", "speech_end_to_first_audio_ms", "steps", "ms", "state", "reason")


def is_conv_flow(rows: list[dict]) -> bool:
    return any(str(r.get("kind") or "").startswith("conv_") for r in rows)


def _conv_station_of(row: dict) -> str:
    kind, label = str(row.get("kind") or ""), row.get("label") or ""
    if kind == "conv_run":
        return "compose" if label == "prompt" else "model"
    sid = {"conv_effect": "gateway", "conv_close": "close"}.get(kind, kind[len("conv_"):])
    return sid if kind.startswith("conv_") and sid in CONV_STATION_IDS else ""


def _conv_station_state(rows: list[tuple[dict, dict]]) -> list[dict]:
    """One line per event: its label, then the state fields it carried. The run's `input` shows what it read."""
    st: list[dict] = []
    for row, p in rows:
        if row.get("label") == "input":
            st.append(_kv("heard", " | ".join(p.get("text") or [])))
            continue
        words = p.get("words")
        bits = [f"{len(words)} words"] if isinstance(words, list) else []
        bits += [f"{k} {p[k]}" for k in _CONV_FIELDS if p.get(k) not in (None, "", [])]
        st.append(_kv(str(row.get("label") or ""), " · ".join(bits)))
    return st[:24]


def _conv_light(stations: dict) -> None:
    """The dark conversation stations that should have fired: a request the ear or the inbox opened owes ONE close
    (I-limbo, §8.2 rule of closing), and a close that says `answered` owes the mouth's line."""
    def expect(sid: str, why: str) -> None:
        if not stations[sid]["lit"]:
            stations[sid]["expected"] = True
            stations[sid]["why"].append(why)

    if (stations["ear"]["lit"] or stations["inbox"]["lit"]) and stations["model"]["lit"]:
        expect("close", "a request ran and no conv_close followed — every request closes once (I-limbo)")
    if any(e["label"] == "answered" for e in stations["close"]["events"]):
        expect("mouth", "the request closed as answered and the mouth said nothing")



def light_flow(rows: list[dict], turn_action: dict | None = None) -> dict:
    """The stations of ONE flow (rows in time order, the observer's columns): the picture is chosen by the flow —
    the conversation manager's `CONV_STATIONS` — then lit and stated."""
    picture = CONV_STATIONS
    stations = {s["id"]: dict(s, lit=False, expected=False, why=[], state=[], n=0, first_ms=None, events=[])
                for s in picture}
    grouped: dict[str, list[tuple[dict, dict]]] = {sid: [] for sid in stations}
    t0 = float(rows[0]["ts_ms"]) if rows else 0.0
    for row in rows:
        p = _payload(row)
        sid = _conv_station_of(row)
        if not sid:
            continue
        grouped[sid].append((row, p))
        s = stations[sid]
        s["lit"] = True
        s["n"] += 1
        if s["first_ms"] is None:
            s["first_ms"] = int(float(row["ts_ms"]) - t0)
        if len(s["events"]) < 8:
            s["events"].append({"id": row["id"], "rel_ms": int(float(row["ts_ms"]) - t0), "label": (row["label"] or row["kind"] or "")[:80],
                                "cat": row["cat"], "kind": row["kind"], "span": row.get("span") or ""})
    for sid in stations:
        stations[sid]["state"] = _conv_station_state(grouped[sid])
    _conv_light(stations)
    order = sorted((s for s in stations.values() if s["lit"]), key=lambda s: s["first_ms"] or 0)
    return {"stations": list(stations.values()), "order": [s["id"] for s in order], "n_events": len(rows),
            "span_ms": int(float(rows[-1]["ts_ms"]) - t0) if rows else 0}


def turn_flow(root: Path, file: str, idx: int, turn: int) -> dict:
    """ONE turn of ONE round through the turn pipeline: the stations the signal crossed, lit in order with the state
    each carried, and the dark ones that should have fired. Read from the sandbox's own DB (read-only), by the
    turn's `corr_id` (the trace that is born with the turn, `voice/trace.py`)."""
    r, report, path = load_round(root, file, idx)
    base = {"schema": 1, "file": file, "idx": idx, "turn": turn, "stations": [dict(s, lit=False, expected=False,
            why=[], state=[], n=0, first_ms=None, events=[]) for s in CONV_STATIONS]}
    if not r:
        return {**base, "readable": False, "why": "no such round"}
    run = r.get("run") or {}
    transcript = list(run.get("transcript") or [])
    testers = [t for t in transcript if t.get("who") == "tester"]
    if not (0 <= turn < len(testers)):
        return {**base, "readable": False, "why": f"the round has {len(testers)} turns"}
    loc = _locale_of_result(r)
    started = _first_turn_at(r)
    sb = _sandbox_of_round(root, r, loc, started)
    base.update({"scenario": r.get("scenario"), "locale": loc, "n_turns": len(testers),
                 "heard": (testers[turn].get("text") or "").strip(), "at": testers[turn].get("at"),
                 "sandbox": sb and {"name": sb["name"], "path": sb["path"], "alive": sb["alive"], "has_db": sb["has_db"],
                                    "engine_url": (sb.get("engine") or {}).get("url") or f"http://127.0.0.1:{sb['port']}"}})
    reply_row = next((t for t in transcript[transcript.index(testers[turn]) + 1:] if t.get("who") != "tester"), None)
    base["said"] = ((reply_row or {}).get("text") or "").strip()
    if not sb or not sb["has_db"]:
        return {**base, "readable": False, "matched_by": "none",
                "why": ("the workspace this round names is gone (pruned)" if (run.get("workspace") and not sb)
                        else "no kept sandbox with a DB matches this round")}
    con = _open_ro(Path(sb["path"]) / "memory" / "_data" / "sandbox.db")
    if con is None:
        return {**base, "readable": False, "matched_by": "none", "why": "the sandbox DB could not be opened"}
    try:
        corr, how = _find_turn(con, base["heard"], float(testers[turn].get("at") or 0), testers[turn].get("corr_id"))
        if not corr:
            return {**base, "readable": False, "matched_by": "none",
                    "why": "no root trace in the sandbox DB carries this turn's text or time"}
        rows = _flow_rows(con, corr)
        # the other turns' corr_ids, so the strip across the round is one query per turn, cheap
        strip = []
        for i, t in enumerate(testers):
            c, h = _find_turn(con, (t.get("text") or "").strip(), float(t.get("at") or 0), t.get("corr_id"))
            lit = set()
            if c:
                for row in _flow_rows(con, c, limit=800):
                    sid = _conv_station_of(row)
                    if sid:
                        lit.add(sid)
            strip.append({"turn": i, "corr_id": c, "matched_by": h, "lit": [s for s in CONV_STATION_IDS if s in lit]})
    finally:
        con.close()
    turn_action = next((t for t in ((run.get("mechanism_report") or {}).get("turn_actions") or [])
                        if isinstance(t, dict) and int(t.get("turn", -1)) == turn), None)
    flow = light_flow(rows, turn_action)
    engine = (sb.get("engine") or {}).get("url") if sb.get("alive") else ""
    base.update({"readable": True, "corr_id": corr, "matched_by": how, **flow, "turn_action": turn_action, "strip": strip,
                 "links": {"flow_api": f"{engine}/api/observability/flow/{corr}" if engine else "",
                           "viewer": f"{engine}/?trace={urllib.parse.quote(corr, safe='')}" if engine else "",
                           "engine_url": engine, "db": str(Path(sb["path"]) / "memory" / "_data" / "sandbox.db")}})
    return base



def replay_rows(root: Path, name: str) -> list[dict]:
    """The events of one replay (`python -m conversation.replay <signals> --events <runs>/conversation/replays/
    <name>.events.jsonl`), in the observer's columns. An event with no trace of its own (the mouth's
    `voice_unavailable`, a duck) belongs to the trace of its run. A name, never a path."""
    if not name or not name.replace("-", "").replace("_", "").isalnum():
        raise ValueError(name)
    path = root / "conversation" / "replays" / f"{name}.events.jsonl"
    if not path.is_file():
        return []
    rows, trace_of_run = [], {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        e = json.loads(line)
        extra = e.get("extra") or {}
        run = (extra.get("refs") or {}).get("run")
        trace = e.get("trace") or trace_of_run.get(run, "")
        if run and trace:
            trace_of_run.setdefault(run, trace)
        rows.append({"id": e.get("i"), "ts_ms": e.get("t_ms") or 0, "cat": "conversation", "kind": e.get("kind"),
                     "label": e.get("label"), "span": e.get("piece") or "", "corr_id": trace, "payload": extra})
    return rows


def replay_flow(root: Path, name: str, trace: str = "") -> dict:
    """ONE request of a replayed session through the conversation pipeline — the brain screen's other source, for
    the package before it runs live (plan F0 §8.4). `trace` = the request's root intervention; empty = the first."""
    rows = replay_rows(root, name)
    traces = list(dict.fromkeys(r["corr_id"] for r in rows if r["corr_id"]))
    base = {"schema": 1, "replay": name, "scenario": f"replay {name}", "n_turns": len(traces),
            "stations": [dict(s, lit=False, expected=False, why=[], state=[], n=0, first_ms=None, events=[])
                         for s in CONV_STATIONS]}
    if not traces:
        return {**base, "readable": False, "why": "no such replay, or it carries no request"}
    corr = trace if trace in traces else traces[0]
    mine = [r for r in rows if r["corr_id"] == corr]
    strip = [{"turn": i, "corr_id": t, "matched_by": "trace",
              "lit": [s for s in CONV_STATION_IDS if any(_conv_station_of(r) == s for r in rows if r["corr_id"] == t)]}
             for i, t in enumerate(traces)]
    heard = next((" | ".join(r["payload"].get("text") or []) for r in mine if r["label"] == "input"), "")
    said = " · ".join(f"{r['payload'].get('chars')} chars" for r in mine if r["kind"] == "conv_mouth" and r["label"] == "say")
    return {**base, **light_flow(mine), "readable": True, "corr_id": corr, "matched_by": "trace",
            "turn": traces.index(corr), "heard": heard, "said": said, "strip": strip, "turn_action": None,
            "links": {"flow_api": "", "viewer": "", "engine_url": "",
                      "db": str(root / "conversation" / "replays" / f"{name}.events.jsonl")}}
