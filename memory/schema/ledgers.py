"""Process state that shares the file but is never a memory pill: the action map, playbook routes, errands, tasks,
notices and push devices. Each table has one owner module that holds every rule; these are only its DDL."""

# ── Action map (V2-539) ──────────────────────────────────────────────────────────────────────────────────
# Known command phrases → verified direct actions, matched BEFORE the fast LLM (`nucleo/actionmap/`). One row
# per (lang, normalized phrase); `action` is opaque JSON validated by the executor's allowlist at load, never
# here. `source`/`status` carry provenance and the user's vetoes: a seed row the user disabled must survive a
# seed re-import (the importer respects status != 'active' and hits > 0). Runtime only ever loads ONE lang.
ACTION_MAP = """
CREATE TABLE IF NOT EXISTS action_map (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  lang        TEXT NOT NULL,
  phrase      TEXT NOT NULL,
  action      TEXT NOT NULL,
  source      TEXT NOT NULL DEFAULT 'seed',
  status      TEXT NOT NULL DEFAULT 'active',
  hits        INTEGER NOT NULL DEFAULT 0,
  agree       INTEGER NOT NULL DEFAULT 0,
  disagree    INTEGER NOT NULL DEFAULT 0,
  created_at  INTEGER NOT NULL,
  last_hit_at INTEGER,
  UNIQUE(lang, phrase)
);
"""
ACTION_MAP_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_action_map_lang ON action_map(lang, status)",
]


# V2-594 · PLAYBOOK_ROUTES — for a DOMAIN of errand, the ORDER of external channels to try (one row per (domain,
# channel)). Not a second action_map, which maps a PHRASE to a LOCAL widget action. The row that matters most is
# the NEGATIVE one (`status='none'`, «the mesh has nothing for X»): it saves the Oracle round trip for every
# uncovered errand, and it EXPIRES on purpose so a new agent on the mesh can change the answer.
PLAYBOOK_ROUTES = """
CREATE TABLE IF NOT EXISTS playbook_routes (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  domain      TEXT NOT NULL,
  channel     TEXT NOT NULL,
  rank        INTEGER NOT NULL DEFAULT 100,
  status      TEXT NOT NULL DEFAULT 'active',
  source      TEXT NOT NULL DEFAULT 'seed',
  target      TEXT,
  evidence    TEXT,
  hits        INTEGER NOT NULL DEFAULT 0,
  ttl_s       INTEGER NOT NULL DEFAULT 604800,
  checked_at  INTEGER,
  created_at  INTEGER NOT NULL,
  last_hit_at INTEGER,
  UNIQUE(domain, channel)
);
"""
PLAYBOOK_ROUTES_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_playbook_routes_domain ON playbook_routes(domain, status, rank)",
]


# V2-683 · ERRANDS — an errand with a THIRD PARTY that outlives the turn, the worker and the restart (somebody
# may answer in ten hours). PROCESS state, never a pill: nothing here is a fact about the operator. A TABLE and
# not a `sys_kv` row because every inbound message asks «does this chat belong to an errand?», and that must be
# an indexed lookup by (platform, chat_id), not a scan of every open errand.
ERRANDS = """
CREATE TABLE IF NOT EXISTS errands (
  id            TEXT PRIMARY KEY,
  kind          TEXT NOT NULL DEFAULT 'generic',
  title         TEXT,
  objective     TEXT NOT NULL,
  mandate       TEXT,
  state         TEXT NOT NULL DEFAULT 'contacting',
  unknowns      TEXT,
  done_when     TEXT,
  last_inbound  TEXT,
  wake_count    INTEGER NOT NULL DEFAULT 0,
  trace_id      TEXT,
  deadline      INTEGER NOT NULL,
  expires_at    INTEGER NOT NULL,
  created_at    INTEGER NOT NULL,
  updated_at    INTEGER NOT NULL,
  closed_at     INTEGER,
  outcome       TEXT
)
"""
# ONE errand per conversation, by construction: a thread licensed to two errands gets a reply answered twice, by
# two objectives. The primary key makes it impossible; the second errand is refused naming the open one.
ERRAND_THREADS = """
CREATE TABLE IF NOT EXISTS errand_threads (
  platform   TEXT NOT NULL,
  chat_id    TEXT NOT NULL,
  errand_id  TEXT NOT NULL,
  contact_id TEXT,
  bound_at   INTEGER NOT NULL,
  PRIMARY KEY (platform, chat_id)
)
"""
ERRANDS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_errands_state ON errands(state, expires_at)",
    "CREATE INDEX IF NOT EXISTS idx_errand_threads_errand ON errand_threads(errand_id)",
]


# V2-728 · TASKS — the durable record of a user commission: ONE thing that survives the turn, the worker and the
# restart, so the operator can hand it over and forget it. The split of responsibilities is the design:
#   · this table holds what is TRUE ABOUT THE TASK and changes rarely (name, ask, state, times, where the result is);
#   · `dispatch._SESSIONS` keeps the worker's HOT detail (phase, steps, pct) in RAM — it churns every second;
#   · `errands` keeps the third-party state machine and gains `task_id` rather than being absorbed: an errand's
#     silence is not a stalled worker.
# `id` is TEXT and must be STABLE ACROSS RESTARTS: a per-process counter repeats between runs (V2-259), and a row
# that outlives the process cannot be keyed by one.
TASKS = """
CREATE TABLE IF NOT EXISTS tasks (
  id          TEXT PRIMARY KEY,
  title       TEXT,                           -- the NAME (V2-530): provisional first, composed when ready
  goal        TEXT NOT NULL,                  -- the operator's own words, verbatim (dedup compares THESE)
  kind        TEXT NOT NULL DEFAULT 'generic',-- web | code | generic | memory | dev | errand | reminder ...
  mode        TEXT NOT NULL DEFAULT 'now',    -- 'now' | 'scheduled' (fires once) | 'recurring' (a cron)
  state       TEXT NOT NULL DEFAULT 'pending',-- pending | running | waiting | done | failed | cancelled
  visible     INTEGER NOT NULL DEFAULT 1,     -- is this the OPERATOR's commission? (see `origin`)
  origin      TEXT NOT NULL DEFAULT 'voz',    -- voz | agenda | api | worker | cron | cluster
  schedule    TEXT,                           -- JSON {type, spec, next_run, display, fire_count} when timed
  surface     TEXT,                           -- nucleo/surfaces.py closed vocabulary, sealed once
  sheet       TEXT,                           -- the results sheet this task writes into, if any
  trace_id    TEXT,
  parent_id   TEXT,                           -- a RELAY continues its parent instead of opening a second task
  outcome     TEXT,                           -- one human line saying how it ended
  created_at  INTEGER NOT NULL,
  started_at  INTEGER,
  due_at      INTEGER,                        -- next fire time for scheduled/recurring (mirrors schedule.next_run)
  finished_at INTEGER
)
"""

# The RESULT belongs to the task, not to the widget sheet (capped at 8 and pruned by mtime, so the ninth search
# deleted a paid-for report). One row per SLOT, not one blob: the parts are asked for separately, and the
# criteria are what `jev.select_many` scores a later question against.
TASK_ARTIFACTS = """
CREATE TABLE IF NOT EXISTS task_artifacts (
  task_id    TEXT NOT NULL,
  slot       TEXT NOT NULL,                   -- 'result' | 'considered' | 'criteria' | 'sources'
  payload    TEXT NOT NULL,                   -- JSON
  created_at INTEGER NOT NULL,
  PRIMARY KEY (task_id, slot)
)
"""

# v7 → v8 (V2-776 D1): the worker's LIVE STATE, durable (it lived only in RAM, so a durable reader saw `pending`
# for a whole run). Written by the pulse's 15-second beat, never per event.
#   · `phase`        the worker's readable phase
#   · `progress`     JSON {done, total, pct, note, plan, waiting_on, ask, backend}
#   · `heartbeat_at` last event of ANY kind from the worker (its stream, a tool call, a report)
#   · `reported_at`  last report the worker made ITSELF (`hbnote`) — the obligation D2 enforces
#   · `error_class`  why it failed, in the A5 vocabulary (network | credit | auth | rate | stalled | ours)
#   · `attempts`     restarts the pulse gave it (a stalled worker is restarted ONCE, then failed honestly)
TASKS_STATUS_COLUMNS = [
    ("phase", "ALTER TABLE tasks ADD COLUMN phase TEXT"),
    ("progress", "ALTER TABLE tasks ADD COLUMN progress TEXT"),
    ("heartbeat_at", "ALTER TABLE tasks ADD COLUMN heartbeat_at INTEGER"),
    ("reported_at", "ALTER TABLE tasks ADD COLUMN reported_at INTEGER"),
    ("error_class", "ALTER TABLE tasks ADD COLUMN error_class TEXT"),
    ("attempts", "ALTER TABLE tasks ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0"),
]

# v8 → v9 (V2-776 M): every request is a row, and every row ends with the CIRCUIT's verdict — never a
# word parsed out of `outcome`. `met | unmet | gave_up | unverifiable | undeclared | skipped` (nucleo/circuit.py).
TASKS_V9_COLUMNS = [
    ("verdict", "ALTER TABLE tasks ADD COLUMN verdict TEXT"),
]

# v10 → v11 (V2-851 F1a): the row is the agent's STATE — what a task waits for and how it is resumed live here, not
# in a RAM registry a restart empties (the session is a cache; the row and the memory are the truth):
#   · `session_id`, `cwd`        the worker harness's resumable session and its working directory (a harness resumes
#                                by id but does not keep the cwd)
#   · `waiting_for`              user_answer | reply | worker | send_echo | time | event:<topic>, set with `state='waiting'`
#   · `waiting_since`, `deadline` when the wait began, and when it ends (the pulse settles it `cancelled` past it)
#   · `ask_id`, `ask`            the durable question the task waits on: its id and its text
#   · `playbook`                 the skeleton the task follows
TASKS_V11_COLUMNS = [(c, f"ALTER TABLE tasks ADD COLUMN {c} {t}") for c, t in (
    ("session_id", "TEXT"), ("cwd", "TEXT"), ("waiting_for", "TEXT"), ("waiting_since", "INTEGER"),
    ("deadline", "INTEGER"), ("ask_id", "TEXT"), ("ask", "TEXT"), ("playbook", "TEXT"))]

# v12 → v13 (INI-078, the orchestrator): his real tasks are ONE queue in this table, with one writer (`nucleo/queue`):
#   · `owner`     worker | send | processor — who runs it; NULL = not a task of the queue (a cron's mirror, an event
#                 flow, an inline row, an internal escalation)
#   · `priority`  1 = urgent («do it now»): first in its lane
#   · `position`  the order inside a priority: a new one is the lane's max + 1, a move is the midpoint of its neighbours
#   · `num`       the task's short number (#7), one per install and NEVER reused — the model and his screen name it alike;
#                 its counter is `sys_kv[tasks.next_num]`, since an archived row is deleted and MAX(num) would come back
TASKS_V13_COLUMNS = [(c, f"ALTER TABLE tasks ADD COLUMN {c} {t}") for c, t in (
    ("owner", "TEXT"), ("priority", "INTEGER NOT NULL DEFAULT 0"), ("position", "REAL"), ("num", "INTEGER"))]
# v13 → v14 (INI-078 #5): `lives_until` — the instant an OPEN task of the queue stops living (from his order, or set by
#   its owner); past it the pulse archives it, said once. NULL = it lives until it ends. An ended task is ARCHIVED in
#   place (its ending state), no longer deleted.
TASKS_V14_COLUMNS = [("lives_until", "ALTER TABLE tasks ADD COLUMN lives_until INTEGER")]
#: after the columns exist: the pulse's read «the next pending of this lane» is one index range; a number names one task
TASKS_V13_INDEXES = ["CREATE INDEX IF NOT EXISTS idx_tasks_queue ON tasks(owner, state, priority DESC, position)",
                     "CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_num ON tasks(num) WHERE num IS NOT NULL"]

TASKS_INDEXES = [
    # The hot read is the tab: «live, mine, in this mode». Composite for the same reason `idx_mem_lvu` is —
    # three single-column indexes do not serve one composite query.
    "CREATE INDEX IF NOT EXISTS idx_tasks_live ON tasks(state, mode, visible)",
    # The loop asks «what is overdue» once a second. Without this it is a full scan of every task ever.
    "CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(due_at)",
    "CREATE INDEX IF NOT EXISTS idx_tasks_finished ON tasks(finished_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_tasks_parent ON tasks(parent_id)",
    "CREATE INDEX IF NOT EXISTS idx_task_artifacts_task ON task_artifacts(task_id)",
]

# STANDALONE FTS5, not `content='tasks'`: an external-content table needs ONE writer keeping it in sync on every
# UPDATE, and `tasks` is updated from several places — a silently drifting index is worse than a copy of two
# short strings. It turns «the task I told you about» into ≤5 candidates WITHOUT a model.
FTS_TASKS = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS fts_tasks "
    "USING fts5(task_id UNINDEXED, title, goal, tokenize=\"unicode61 remove_diacritics 2\")"
)


# V2-796: A NOTICE IS A ROW, and the row says how it ended (a reminder nobody heard used to vanish into the next
# turn's prompt). `nucleo/pulse/notices.py` is the only writer. `dedupe_key` is UNIQUE so the same notice can never be
# delivered twice (a restart re-firing a job, two doors announcing the same finish).
#   · state  owed | spoken | pushed | shown | covered | seen | expired
#   · channel  voice | push | screen | google (who took it)
NOTICES = """
CREATE TABLE IF NOT EXISTS notices (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  dedupe_key   TEXT NOT NULL UNIQUE,
  kind         TEXT NOT NULL DEFAULT 'reminder',   -- reminder | done | approval | info
  title        TEXT NOT NULL DEFAULT '',
  body         TEXT NOT NULL DEFAULT '',
  url          TEXT NOT NULL DEFAULT '',
  state        TEXT NOT NULL DEFAULT 'owed',
  channel      TEXT NOT NULL DEFAULT '',
  attempts     INTEGER NOT NULL DEFAULT 0,
  next_try_at  INTEGER,
  created_at   INTEGER NOT NULL,
  delivered_at INTEGER,
  seen_at      INTEGER,
  detail       TEXT
)
"""

# One row per browser that agreed to receive Web Push. `id` is a hash of the endpoint (the endpoint itself is a
# capability URL: whoever holds it can push to that browser, so it is never logged or returned to a client).
PUSH_DEVICES = """
CREATE TABLE IF NOT EXISTS push_devices (
  id          TEXT PRIMARY KEY,
  endpoint    TEXT NOT NULL,
  p256dh      TEXT NOT NULL,
  auth        TEXT NOT NULL,
  dev         TEXT NOT NULL DEFAULT '',
  platform    TEXT NOT NULL DEFAULT '',
  installed   INTEGER NOT NULL DEFAULT 0,
  created_at  INTEGER NOT NULL,
  last_ok_at  INTEGER,
  fail_count  INTEGER NOT NULL DEFAULT 0
)
"""

NOTICES_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_notices_owed ON notices(state, next_try_at)",
    "CREATE INDEX IF NOT EXISTS idx_notices_created ON notices(created_at DESC)",
]


# ── the conversation & turn manager (V2-941, v3.1 B1) ────────────────────────────────────────────────────────────
# The rows of the `conversation` package's `Store` port: one row per (account, logical table, key) — its tables are
# the package's, not the engine's (inbox, items, says, interventions, voice_open, evidence, flags, effect_ops). Its ONE
# writer is the conversation's own thread (`nucleo/conversation_host/runtime.py`), through
# `memory/conversation_store.py`. The row is JSON; `state` is lifted out so a sweep reads what is in course and never
# the history; `uniq` is the dedupe key where the port asks for one; `updated_ms` lets the hourly prune drop what is
# final and old. `conv_meta` holds the lease (the epoch that fences a second process) and the counters.
CONV = [stmt.strip() for stmt in """
CREATE TABLE IF NOT EXISTS conv_meta (account TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL,
    PRIMARY KEY (account, key));
CREATE TABLE IF NOT EXISTS conv_rows (account TEXT NOT NULL, tbl TEXT NOT NULL, key TEXT NOT NULL, state TEXT,
    uniq TEXT, updated_ms INTEGER NOT NULL DEFAULT 0, row TEXT NOT NULL, PRIMARY KEY (account, tbl, key));
CREATE UNIQUE INDEX IF NOT EXISTS idx_conv_rows_uniq ON conv_rows(account, tbl, uniq) WHERE uniq IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_conv_rows_state ON conv_rows(account, tbl, state);
-- a run reads the newest rows of a table (the conversation window), never the whole history
CREATE INDEX IF NOT EXISTS idx_conv_rows_recent ON conv_rows(account, tbl, updated_ms);
-- the hourly prune: what is final and old, by table — an index that starts by the table, not a scan
CREATE INDEX IF NOT EXISTS idx_conv_rows_prune ON conv_rows(tbl, state, updated_ms);
""".split(";") if stmt.strip()]   # one SQL script, its statements in order
