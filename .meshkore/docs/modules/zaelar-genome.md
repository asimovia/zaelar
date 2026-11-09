# The genome — the agent's DNA: a name, a generation, and only structured genes cross

**Module:** `genome/` (`__init__.py` identity · check · last good generation · boot; `genes.py` the closed shapes;
`privacy.py` the filter; `diff.py` + `__main__.py` the command; `absorb.py` the generation change)
**Initiative:** V2-859 (T562 one playbook, T563–T566 this module, T567 the `gene` event).
**Sibling docs:** `zaelar-playbook-routes.md` (the learned route), `zaelar-action-map.md` (the learned alias).

## What the genome is

Two places that already existed, read as one thing — nothing moved:

| Part | Lives in | What it carries |
|---|---|---|
| universal genes | `nucleo/genesis.json` | knobs, consent classes, playbook end states and needs, the `genome` section |
| culture | `i18n/genesis/<lang>/*.json` | playbook prose, action aliases, small talk, voice |

`genome.identity()` → `{generation, hash, langs}`. The hash is sha256 over canonical JSON with every documentation
key (`_comment`, `_*`) stripped at every depth, plus each pack under its `lang/file` name — a comment edit is the
same genome, a value edit is not. `generation` (was `version`) is one integer for the whole genome; a release that
changes a gene bumps it.

## Three layers, decided by WHERE a value lives

| Layer | Where | Heritable |
|---|---|---|
| factory | the genome files | it IS the inheritance |
| learned | `source='learned'` rows of `action_map` and `playbook_routes` | candidates, through `genome diff` |
| personal | `rules/`, `config/*.json`, memory, contacts, the library, an `operator`-pinned route | never |

## Boot: the check and the last good generation

`server/boot/brain.py` calls `genome.boot()` once: identity, then — if the genesis passed `genome.check()` — a
snapshot at `<workspace>/config/genome/last_good.json`, then the absorption. Readers of the universal genes read
`genome.genesis()` (re-read on mtime change): a genesis that fails the check (unreadable, no integer
`generation ≥ 1`, a section that is not an object, a playbook that is not an object) is refused LOUD (error log +
`alert` event) and the reader gets the last generation that passed; with no snapshot yet, `{}` and each reader's
own code default. Never half a file.

Readers through `genome.genesis()` today: `nucleo/errands/playbooks.py`, `rules/defaults.py`, `library/paths.py`,
`widgets/directory.py`. **Still reading the file directly:** `nucleo/circuit/__init__.py` (open — it should read
through the same door). A culture pack that does not parse is logged as an error at boot; the packs have no
fallback of their own yet (their reader is `i18n/packs.py`).

## Genes: the closed shapes (`genes.py`)

| type | key | value | evidence (from `genesis.json#genome.evidence`) |
|---|---|---|---|
| `alias` | `{lang, phrase}` | an action the executor declares | `agree > disagree`, `hits ≥ alias_hits` (3) |
| `route` | `{domain}` | ordered channel KINDS | closures ≥ `route_closures` (1) |
| `nothing_serves` | `{domain, channel}` | `null` | answers ≥ `nothing_serves_answers` (1) |
| `threshold` | `{knob}` | a number inside its bounds | `measured`; the knob must be listed in `genesis.json#genome.thresholds` |

Prose is never a gene. A route carries `connector · mesh · browser · worker`, never the row's `target` (a site, a
company or an agent's id).

## The privacy filter (`privacy.py`)

At export, deterministic: a gene is dropped if any string in its key or value contains a name this agent knows
(every name of every contact via `widgets.directory`, each of its words of 3+ letters, the memory's concept hubs)
or a shape only a particular thing has: email, URL, phone, numeric date, a number of 3+ digits. Dropped genes are
counted by KIND, never listed. Every doubt drops.

## `python -m genome diff`

Prints the identity, then one JSON line per heritable learned gene that differs from the generation (a learned
alias the pack ships identical is not a difference), then `refused:` and `dropped (privacy):` counts. `--json`
for one document. `identity` and `check` (exit 1 when the genesis on disk would be refused) are the other commands.
Offline, read-only, sends nothing.

## Absorption on a generation change (`absorb.py`)

On the first boot whose identity hash differs from the one in `sys_kv['genome.identity']`: every ACTIVE learned
alias the pack now ships identical becomes the factory row (`source='seed'`, same id and counters, one `gene`
event `cause: absorbed`). A learned row that differs stays; a learned row he disabled stays his; a seed he
disabled stays disabled (absorption never writes a seed; the importer is `INSERT OR IGNORE`); the personal layer is
not read. Routes have no factory layer, so nothing is absorbed there today. The same generation booted again
absorbs nothing.

## Tests

`tests/agent_headless/unit/genome/` — identity/check/fallback and the in-place route table rename (T563), the
closed shapes and a contact-naming gene dropped for every type (T564), the diff and its command (T565), the
absorption keeping what is his (T566). Thirteen disarms, each seen red.

## Open

- `nucleo/circuit/__init__.py` reads `genesis.json` directly (outside this change's files).
- The learned alias still has no writer (V2-859 §Open): `genome diff` lists nothing for aliases on a real install.
- `nothing_serves` has no repeat counter on the row; its evidence is one answer until the table counts them.
- The route's key is still the lexical `domains.domain_of`; a `playbook` column on the route is not added.
