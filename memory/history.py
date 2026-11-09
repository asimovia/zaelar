"""memory/history.py — where a remembered line CAME FROM, and the conversation record as a source (V2-802/V2-803).

Two reads, both direct SQL (no model, no embedding), both declared on the facade (`memory.api`):

  · `provenance(ids)` — for rows a recall returned: when each was written, at what level, of what kind, and from
    which source (`meta.source`: voice, a worker, whatsapp, email, conv…) and entity. A recall that only says
    «- text» cannot tell an inbound marketing email from a fact the operator dictated, so whoever reads it
    cannot say «it is on record» honestly (V2-802 failure 6).

  · `conversation(hours, query)` — the operator's own past conversation, verbatim, for a time window and/or a
    query: each line with its timestamp and who said it. This is the ONE reader for «what did I tell you
    yesterday» (V2-803 T-01/T-02); recall only sees the pills extraction chose to keep, and extraction can miss.

Why the conversation buffer (`kind='conv'`) and not the bus `events` log: the `transcript` events carry EVERY
final STT line, including ambient speech that was never addressed to zaelar (a TV in the room), and nothing on
the event itself says which lines were turns. The `conv` row is written once per turn the brain actually
answered (`turn_after.py`), with the operator's words and the reply as structured fields (`meta.u`/`meta.a`).
What it lacks is a work-session id; the transport layer adds that from observability (`server/memory_routes.py`),
so this module keeps reading only its own table. Its reach is the buffer's TTL (2 days today) — retention as a
declared setting is V2-803 T-03, not this reader.
"""
from __future__ import annotations

import json
from datetime import datetime

from . import db as _db
from .clock import now as _clock_now

#: The widest window `conversation()` accepts, in hours. The buffer itself keeps less; this only bounds a caller.
MAX_HOURS = 24.0 * 30
#: Lane names a provenance row is labelled with — the same three a recall can be filtered by.
LANE_MEMORY = "memory"
LANE_CONVERSATION = "conversation"
LANE_MESSAGE = "message"


def iso(ts) -> str:
    """Epoch seconds → local ISO time to the minute ('' when unknown)."""
    try:
        t = float(ts)
    except (TypeError, ValueError):
        t = None
    if t is None or t <= 0:
        return ""
    return datetime.fromtimestamp(t).astimezone().isoformat(timespec="minutes")


def _meta(raw) -> dict:
    m: dict = {}
    if raw:
        try:
            m = json.loads(raw) or {}
        except (TypeError, ValueError):
            m = {"_unreadable": True}
    return m if isinstance(m, dict) else {}


def lane_of(kind: str | None) -> str:
    """Which lane a row belongs to, by its kind — the same split `retriever.LANE_*` searches by."""
    if kind == "msg":
        return LANE_MESSAGE
    if kind == "conv":
        return LANE_CONVERSATION
    return LANE_MEMORY


def provenance(ids) -> dict[int, dict]:
    """{id: {id, created, created_ts, level, kind, slot, source, entity, lane}} for the given row ids.

    `created` is local ISO time; `source` is `meta.source` as the writer stamped it (None when the row predates
    the stamp — said as unknown, never guessed)."""
    want = [int(i) for i in (ids or []) if str(i).lstrip("-").isdigit()]
    if not want:
        return {}
    ph = ",".join("?" * len(want))
    rows = _db.get_db().query(
        f"SELECT id, created, level, kind, slot, meta FROM memories WHERE id IN ({ph})", tuple(want))
    out: dict[int, dict] = {}
    for r in rows:
        m = _meta(r["meta"])
        out[int(r["id"])] = {
            "id": int(r["id"]), "created": iso(r["created"]), "created_ts": r["created"], "level": r["level"],
            "kind": r["kind"], "slot": r["slot"] or "", "source": m.get("source"), "entity": m.get("entity"),
            "contact_id": m.get("contact_id"),   # V2-854 F3: the contact this row is about, when the writer knew it
            "lane": lane_of(r["kind"]),
        }
    return out


def is_kickoff(u: str) -> bool:
    """Is this operator line the FIRST-TURN kickoff — the prompt the engine speaks in HIS voice so the model greets
    him (`i18n` `kickoff_prompt`, every language)? It is written into the conversation buffer as his words, and it
    is not something he said: a ledger of the day must not open an episode with it. Best-effort: without the
    catalog, nothing is a kickoff."""
    t = " ".join((u or "").split())
    return bool(t) and t in _kickoff_prompts()


def _kickoff_prompts() -> frozenset[str]:
    global _KICKOFFS
    if _KICKOFFS is None:
        try:
            from i18n import langs as _langs
            _KICKOFFS = frozenset(" ".join(sp.kickoff_prompt.split()) for sp in _langs.supported() if sp.kickoff_prompt)
        except Exception:  # noqa: BLE001 — the catalog is not memory's to require
            _KICKOFFS = frozenset()
    return _KICKOFFS


_KICKOFFS: frozenset[str] | None = None


#: Silence that closes the LIVE episode, in minutes: the newest turns count as «in the dialog window» only while
#: they chain to now with gaps under this. The same figure cuts the day into episodes (`reads.EPISODE_GAP_MIN`).
LIVE_GAP_MIN = 12.0


def live_conv_ids(n: int, gap_min: float | None = LIVE_GAP_MIN) -> set[int]:
    """The ids of the conversation rows the LIVE dialog window holds (V2-865): the newest `n`, but only those that
    chain to now — each less than `gap_min` of silence from the next, the newest from now. A fresh session after a
    night's sleep has an EMPTY window, so nothing is skipped; a session running for two hours skips its last `n`
    turns. Measured 2026-11-09: skipping «the newest five» unconditionally hid a request made at midnight from the
    morning's day schema while the window did not hold it either — it was in neither place.
    `gap_min=None` keeps the plain «newest n» reading."""
    if n <= 0:
        return set()
    rows = _db.get_db().query(
        "SELECT id, created FROM memories WHERE kind='conv' AND valid=1 ORDER BY created DESC, id DESC LIMIT ?",
        (int(n),))
    if gap_min is None:
        return {int(r["id"]) for r in rows}
    out: set[int] = set()
    ref = float(_clock_now())
    for r in rows:
        ts = float(r["created"] or 0)
        if ref - ts > float(gap_min) * 60:
            break
        out.add(int(r["id"]))
        ref = ts
    return out


def _newest_conv_ids(n: int) -> set[int]:
    """The ids of the newest `n` conversation rows, whatever their age (kept for callers that mean exactly that)."""
    return live_conv_ids(n, gap_min=None)


#: Turns of ONE episode a relevance pick may take: the turns of an episode share their words, so the top of the
#: ranking is one episode said five ways while the turn that answers, three hours older, waits below (2026-11-09).
EPISODE_ROWS = 2


def _episodes_of(rows) -> dict[int, int]:
    """Episode index of each row (any order in): consecutive turns less than `LIVE_GAP_MIN` apart share one."""
    ordered = sorted(rows, key=lambda r: (float(r["created"] or 0), int(r["id"])))
    out: dict[int, int] = {}
    ep, last = -1, None
    for r in ordered:
        ts = float(r["created"] or 0)
        if last is None or ts - last > LIVE_GAP_MIN * 60:
            ep += 1
        out[int(r["id"])] = ep
        last = ts
    return out


def _oldest_repeat(rows, query_words: set[str], match: dict | None) -> int | None:
    """The id of the oldest row whose operator words repeat the query, when that row is also the oldest row that
    matches the query at all — the original request. None when an older matching turn exists (the repeat is then
    a later attempt) or nothing repeats."""
    oldest_match: tuple[float, int] | None = None
    oldest_rep: tuple[float, int] | None = None
    for r in rows:
        if match is not None and int(r["id"]) not in match:
            continue
        key = (float(r["created"] or 0), int(r["id"]))
        if oldest_match is None or key < oldest_match:
            oldest_match = key
        m = _meta(r["meta"])
        u = (m.get("u") or "").strip() or (r["text"] or "").strip()
        if _is_repeat(_words(u), query_words) and (oldest_rep is None or key < oldest_rep):
            oldest_rep = key
    return oldest_rep[1] if oldest_rep and oldest_rep == oldest_match else None


#: Two sentences this alike are the SAME request said again: the word sets overlap at least this much.
REPEAT_OVERLAP = 0.6


def _is_repeat(words: set[str], query_words: set[str]) -> bool:
    """He is repeating himself: the row's words and the query's are mostly the same set. A row he had to repeat is
    the earlier attempt, and the answer it carries did not satisfy him — recycling it as evidence is how the
    model named the wrong artist twice (measured 2026-11-09). Only for queries with substance (4+ words)."""
    if len(query_words) < 4 or not words:
        return False
    inter = len(words & query_words)
    union = len(words | query_words) or 1
    return inter / union >= REPEAT_OVERLAP


def _matching_conv_ids(query: str, since: int) -> dict[int, int] | None:
    """Conversation rows in the window that match `query` through the SAME lexical channel recall uses (FTS5 with
    the retriever's stemming), as `{id: hits}` — `hits` = how many DISTINCT terms of the query the turn carries.
    Not bm25: it crowns the shortest row that repeats one word («Which of these tasks… which…»), measured
    2026-11-09 against the model's own query. None = the query carries no searchable term (read the whole window)."""
    from .retriever import _fts_query
    q = _fts_query(query or "")
    if not q:
        return None
    terms = {t.strip('"').rstrip("*").lower() for t in q.split(" OR ") if t.strip()}
    db = _db.get_db()
    if db.fts_available:
        rows = db.query(
            "SELECT m.id AS id, m.text AS text FROM fts_memories f JOIN memories m ON m.id = f.rowid "
            "WHERE fts_memories MATCH ? AND m.kind='conv' AND m.valid=1 AND m.created >= ?", (q, since))
    else:   # no FTS on this build: plain containment over the same terms, so the reader still answers
        rows = db.query("SELECT id, text FROM memories WHERE kind='conv' AND valid=1 AND created >= ?", (since,))
    out: dict[int, int] = {}
    for r in rows:
        words = _words(r["text"] or "")
        hits = sum(1 for t in terms if t and any(w == t or w.startswith(t) for w in words))
        if hits or db.fts_available:
            out[int(r["id"])] = max(hits, 1)
    return out


def _words(text: str) -> set[str]:
    """The lowercased words of a row, split on anything that is not a letter or a digit."""
    return set("".join(c if c.isalnum() else " " for c in text.lower()).split())


def conversation(hours: float = 24.0, query: str = "", limit: int = 40, max_chars: int = 6000, *,
                 skip_newest: int = 0, by: str = "recency") -> list[dict]:
    """The operator's own past conversation, VERBATIM, oldest first: `[{id, ts, at, who, text}]` where `who` is
    'operator' or 'assistant' and `at` is local ISO time.

    Bounded twice — by `hours` (clamped to `MAX_HOURS`) and by size (`limit` turns, `max_chars`); when the bound
    bites, the NEWEST turns are the ones kept. With a `query`, only turns matching it (lexically, as recall does)
    are returned; a query with no match returns [] — «not found» is an answer. Only valid rows: a reset that
    cleared the conversation (`clear_conversation`) stays cleared here too.

    `skip_newest` (V2-865) leaves out the newest N turns — the ones the live dialog window already carries, so a
    reader asked «what did he say EARLIER» is not answered with the thread it is in. `by="relevance"` picks, with a
    `query`, the BEST-matching turns first (FTS5 rank) instead of the newest: measured on 2026-11-09 with the
    model's own query «artist from a TV show…», recency kept twelve turns of the live complaint and trimmed the
    one turn, three hours old, that held the answer. The output stays chronological either way."""
    try:
        h = float(hours)
    except (TypeError, ValueError):
        h = 24.0
    h = min(max(h, 0.0), MAX_HOURS) or 24.0
    since = int(_clock_now() - h * 3600)
    match = _matching_conv_ids(query, since) if (query or "").strip() else None
    if match is not None and not match:
        return []
    skip = live_conv_ids(int(skip_newest or 0))
    qwords = _words(query) if (query or "").strip() else set()
    rows = _db.get_db().query(
        "SELECT id, text, meta, created FROM memories WHERE kind='conv' AND valid=1 AND created >= ? "
        "ORDER BY created DESC, id DESC", (since,))
    if by == "relevance" and match:
        # Most query terms first, the newest among equals; the trim below then keeps the turns that answer.
        rows = sorted(rows, key=lambda r: (-match.get(int(r["id"]), 0), -float(r["created"] or 0), -int(r["id"])))
    episode_of = _episodes_of(rows) if by == "relevance" and match else {}
    # The repeats of THIS request are his later attempts and are dropped — unless the oldest of them is the oldest
    # matching turn there is: then it is the ORIGINAL request, said again almost word for word, and dropping it
    # would drop the turn that answered it. The first time the subject came up is the original.
    original_repeat = _oldest_repeat(rows, qwords, match) if qwords else None
    per_episode: dict[int, int] = {}
    picked: list[tuple] = []
    used = 0
    for r in rows:                                     # best/newest → worst/oldest; trimmed, then reversed
        if match is not None and int(r["id"]) not in match:
            continue
        if int(r["id"]) in skip:
            continue
        m = _meta(r["meta"])
        u, a = (m.get("u") or "").strip(), (m.get("a") or "").strip()
        if not u and not a:                            # an old row without structured fields: its text as is
            u = (r["text"] or "").strip()
        if qwords and int(r["id"]) != original_repeat and _is_repeat(_words(u), qwords):
            continue                                   # his later attempt at THIS request: not the referent
        ep = episode_of.get(int(r["id"]))
        if ep is not None and per_episode.get(ep, 0) >= EPISODE_ROWS:   # the rest of that episode says the same
            continue
        seg = len(u) + len(a)
        if picked and (used + seg > max_chars or len(picked) >= int(limit)):
            break
        picked.append((int(r["id"]), r["created"], u, a))
        used += seg
        if ep is not None:
            per_episode[ep] = per_episode.get(ep, 0) + 1
    out: list[dict] = []
    for mid, ts, u, a in sorted(picked, key=lambda t: (float(t[1] or 0), t[0])):   # chronological, whatever the pick
        if u:
            out.append({"id": mid, "ts": ts, "at": iso(ts), "who": "operator", "text": u})
        if a:
            out.append({"id": mid, "ts": ts, "at": iso(ts), "who": "assistant", "text": a})
    return out
