# Where data lives — the stores, and nothing else

Every piece of data the engine reads or writes lives in ONE of the stores below. A new kind of data goes into one of
them; it never creates a store of its own (a JSON file beside a module, an in-process dict that must survive a
restart, a cache that is the only copy). If something does not fit, that is a design question, asked before the code.

## The three content stores

| Store | What it holds | Where | Who changes it |
|---|---|---|---|
| **The genome (DNA)** | What every install is born with: the initial rules, the style, the prompts' fixed parts, the action-map factory rows, the playbook seeds. | `nucleo/genesis.json` + `genome/` (the heritable gene shapes and their privacy check) | A release. The only runtime exception is the LEARNED genes (`source='learned'` rows of the action map and the playbook routes), which live in memory and are the shapes `genome/genes.py` allows. |
| **The language packs** | Everything the agent says or reads that depends on the language: lines, examples, the spoken-language rules, the action-map phrases per language. | `i18n/genesis/<lang>/` (+ the generated packs under `i18n/generated/`) | A release; a pack generated for a new language is written once and then read. |
| **The memory** | EVERYTHING dynamic created while the agent runs: the state, the facts and pills (short and long term), the conversation and its ledger, **the task queue** (`tasks`, one row per real task while it is pending, running or waiting; archived as a short-term pill when it ends), the widgets' data, the rules table, the contacts, the secrets vault, the observability events, the system key-values (`sys_kv`). | ONE SQLite file, `zaelar.db` (`memory/db.py`, `db_path()`; default `memory/_data/zaelar.db`, `ZAELAR_DB` overrides it) | The engine at runtime, each table through its one writer (the queue through `nucleo/queue.signal`, memory pills through `nucleo/memory_agent`, rules through `rules/`). |

There is no fourth content store. In-process state (the dispatcher's sessions, the send owner's draft text, caches)
is a cache or a private working copy of its owner: it is rebuilt from the memory on boot, and the status of anything
lives only in its memory row, read by id — never copied into a second place that someone else also writes.

## The settings store (separate on purpose)

| Store | What it holds | Where |
|---|---|---|
| **Settings** | How this install is configured, not what it knows: the settings he changes from the app, the connectors' activation, which model each piece uses, the identity file, the deployment's resource ratios. | `config/` — `settings.json`, `connectors.json`, `v2.json`, `identity.json`, `meshkore.json`; each `*.default.json` beside it is the shipped default a deployment may override. Each file has its owner module and a redacted public view. |

Settings are not memory: they are not learned, not recalled and not pruned. Nothing the end user configures goes in
`.env` (it is only a power-user fallback).

## Files that are not stores (third parties' own state, code, records)

| What | Where | Why it is a file |
|---|---|---|
| A connector's own session (e.g. WhatsApp) | `connectors/<name>/_session/` | It is the third-party library's own format; the engine never reads it as data. |
| The browser's profile | `widgets/_data/navegador/profile` | Chromium's own profile directory. |
| The widgets he creates or changes | `widgets/_user/<id>/` | They are CODE (a widget folder), and they shadow the built-in one of the same id. |
| Logs and session timelines | `.meshkore/logs/` | A record for debugging, never read back as state. |

These are never resettable by accident: a memory reset never touches connector sessions or credentials.

## The rule, in one line

DNA and language are born with the install and change with a release; memory is everything that happens; settings are
how it is configured. A datum has ONE home and one writer; everyone else holds its id.
