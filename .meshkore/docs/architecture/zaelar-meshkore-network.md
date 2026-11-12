---
title: Zaelar — The MeshKore network as a capability (live agents + clusters)
category: architecture
owner: ricart
status: current
---

# The MeshKore network — two surfaces, one mesh

Zaelar reaches the outside world through **external services it orchestrates**: the agents published on
the MeshKore network, external MCP servers, and third-party APIs. Between them they give the engine access
to bookings, travel, events and thousands of other external services. None of those services live in this
repository — Zaelar discovers them, calls them and folds their answers into the conversation.

The MeshKore network reaches the engine through **two surfaces that are built differently, entered from
different code, and must not be confused with each other**:

| | **live agents** | **clusters** |
|---|---|---|
| what is on the other side | an external agent that **does a thing** on request | peers that **talk** |
| who drives it | a **Brain Worker**, mid-errand | the engine itself, continuously |
| direction | zaelar asks, once, and gets data back | both ways, open-ended, long-lived |
| entered at | `nucleo/mesh_agents.py` → bridge `hbmesh` | `connectors/meshkore/` → FlashBrain, UNTRUSTED profile |
| trust | none needed: read-only data, nothing of ours crosses | the whole security model of `zaelar-security.md` |
| detail | §1 below | `zaelar-cluster-channel.md` (end-to-end algorithm) |

A **third** surface is planned (V2-866): **A2A contacts** — the agent of a PERSON you know, reached through a
server mailbox rather than a socket, with its own trust class and per-contact scopes. Its theory and event catalogue:
`zaelar-a2a-network.md`; it is not a cluster and not a live agent.

A single sentence tells them apart: **an agent serves an errand, a cluster holds a conversation.** Asking a
hotel agent for rooms needs no relationship, no memory and no permissions; a peer that speaks to us every
day needs all three, which is why one is a small client and the other is a module.

---

## 1 · Live agents — external specialists before the browser

### 1.1 Why this exists

A specialist agent that publishes a service *wants* to be called: one HTTP round-trip, about a second, and a
structured answer. That makes it the preferred route for a web errand. So the order in a Brain Worker's
method is: ask the network first, use an external API or MCP server when one fits, and open the real browser
for everything else.

### 1.2 The contract

Discovery is `POST https://meshkore-oracle.rjj.workers.dev/v1/search`; contact is a `POST` to the agent's own
endpoint. Both hops read the errand from a field called **`prompt`**.

> The Oracle has **two modes and picks by field**. `query` alone is a BM25 keyword match over the catalogue;
> `prompt` runs its own natural-language parse first (intent, places, dates). Zaelar sends both, and sends
> the errand in the **operator's own words** — the Oracle handles the language.
>
> | body | intent |
> |---|---|
> | `{"query": "vuelo de Madrid a Roma"}` | keyword match only |
> | `{"prompt": "vuelo de Madrid a Roma"}` | `bookings.flights`, with a parse of MAD→FCO |

**Who is asked, and for how long (V2-798).** Only agents the Oracle row does not call down: `online: false`,
`operational: false` (the Oracle's own probe of the skills, standard §27) or a card whose `availability.now` is
`false` keep an agent out — a missing field is not a statement and drops nothing. A learned route to an agent the
Oracle just called down is skipped. The skill call's timeout is the **agent's**: a latency it declares
(`latency_p95_ms`, `latency_ms`, `expected_latency_s`, … on the row, the card or its `operational` object) ×2,
never below a 60 s floor, never above 90 s; the Oracle hop keeps its own short timeout. One `serve` has ONE budget
(100 s, so the command stays under a shell tool's usual two-minute limit): a second candidate gets only what is
left, and none is started with under 20 s. A timeout is reported naming the agent and the seconds waited, not as
«nobody answered»; `200` with zero rows is `ok: true, empty: true`, with the agent's own `hint` lifted to
`agent_hint` so the worker can ask again its way. Each outcome is also recorded per agent for the next errand
(`zaelar-playbook-routes.md` §«outcomes record»).

### 1.3 Coverage

Coverage is whatever the network publishes: travel (hotels, flights), live events, and every new domain a
publisher adds. The engine needs no change to use a new agent — see §1.5.

### 1.4 Money — free only, enforced in code

`_is_free` reads the price the Oracle or the agent's own card reports and **treats unknown as not free**.
Skipping a free agent we could not price costs one fallback; calling a paid one would spend money nobody
authorised. A `402 Payment Required` challenge is reported to the caller as a fact — never paid, never
retried. `nucleo/mesh_agents.py` owns this rule for `serve`; for one declared skill (§1.8) the rule reads «free,
or priced through a deployment's relay that can put its cost on the account» — still never paid by the engine.

### 1.5 There is no catalogue, and that is the design

There is **no list of known agents in the engine**. Not in a config file, not in a constant, not in a prompt.
Support for a new domain requires no edit: the Oracle is asked at the moment the task is planned, and
whatever is live and free that day is what comes back.

What *is* remembered is the **route** — «for this kind of errand, this agent answered» — keyed by the intent
the Oracle itself resolved, cached in `sys_kv` with a 7-day TTL. Same idea as `nucleo/flash/site_catalog.py`
for websites: the first flight search pays the discovery, the next one goes straight there.

Two rules keep that cache accurate: it **expires**, so a publisher that disappears costs one call rather than
a permanently wrong route; and it is **never keyed on `general`**, the Oracle's bucket for «could not
classify», because that bucket mixes unrelated errands.

### 1.6 Where it enters the engine

```
workers.prompts._web_prompt()    step 0 — before the browser, ask the network
        │
        └─ Brain Worker runs:  hbmesh find "<errand>"   /   hbmesh serve "<errand>" --prompt "<ISO dates>"
                                       │
                     nucleo/cli/mesh.py ──> nucleo/mesh_agents.py ──> Oracle ──> the agent
```

`hbmesh` is allowlisted for workers in `nucleo/workers/providers/claude.py::_BRIDGES`, alongside `hbmem`,
`hbnote`, `hbweb` and `hbwidget`. It is a **worker** capability: a voice turn answers in under a second, and
discovery plus contact is two network hops, so the FlashBrain hands the errand to a worker.

Three rules the caller owns:

1. **Absolute ISO dates.** Relative dates («tonight») are resolved by the engine before the call.
2. **Check the domain of what comes back.** An agent answering a different domain than the one asked is a
   fallback, not a result.
3. **Check the results, not just the status.** An `ok:true` whose items don't match the request is rejected
   and said so — never presented as an answer.

### 1.7 Fail-open, always

Network down, no agent, a mute agent, a malformed answer — every one of them degrades to the next route.
`mesh_agents` never raises; a failure is `{"ok": false, "reason": …}` and the reason is written to be said out
loud.

### 1.8 A conversation with an agent — one skill, its questions, its jobs, a step handed back (V2-895)

`serve` is discovery plus a free-text ask of an agent's FIRST declared skill: blind for an agent that does several
things. A booking is a different shape, with its own two verbs:

```
hbmesh find "<errand>"                                   → agents, each with its card's skills {id, free, describes}
hbmesh call <agent_id> <skill> --json @req.json --errand "<his words>"   → result · question · job · step handed back
hbmesh report <thread> <outcome>                         → how a step the agent handed back ended
```

**One skill, its price** (`nucleo/mesh_call.py`). The skill must be DECLARED by the card; price is per skill (its own
`pricing`, else the card's; unknown is not free). Free → direct. Priced → only through a deployment's mediated egress
(`<egress>/p/mesh/<agent host><path>`, the account's own credential) AND only with a price for it: a row of the tariff
family `agent`, keyed `<agent_id>.<skill_id>`, delivered with the lease. Otherwise refused before anything leaves. Which
agents a relay covers and how it books them is the relay's business; the engine only debits its lease when a job is
born. A `402` is never paid. A served skill teaches the playbook route `<agent>/<skill>` (genome learned layer).

**One order, one key, one step at a time.** The request key (`idempotency_key`, only where the skill's own examples
use one) is the engine's, derived from the task and the request — never taken from the body or the card — so a retry of
an order whose answer never came carries the same key. While an order has a step whose outcome is unknown (no answer,
an open job, a handed-back step not reported) no OTHER skill of that agent is called for it.

**An agent that asks is not an agent that failed — and it asks ONE way** (`nucleo/mesh_dialog.py`, `mesh_jobs.py`). An
answer whose SHAPE is a question (a `questions` list, or A2A `input-required`) — at once, or later from a job — goes on a
task row through THE asker (`clarify`: dialogue, never a card), one question at a time, with its declared options;
options that need a value of his own are not offered. The exchange (thread `mt_…`) records WHICH question it waits on
(its `ask_id`); an answer to any other is refused, words never answer a question with options (it is asked again). His
option is applied by the agent's own contract (a choice's `set` into a copy of the request, sent again whole; a
`field`; or `{id, choice}` to a job's `answers`), with no model, and the worker that asked is resumed with what came of
it. Only then are its VALUES kept as his standing answer (his rules row, scope `errand/mesh/mesh_serve`, key
`mesh.mandate:<agent>/<skill>/<question>`, personal layer): applied next time only when the agent offers exactly those
values — an agent cannot redefine what he chose.

```
call → questions → prefill (his values) → on the worker's row (asker) → worker ends its turn
     → his option (screen or voice, bound by ask_id) → request rewritten + sent whole → worker resumed with the outcome
202  → job: own row (born from the worker's) waiting remote_job → pulse polls → final? → worker resumed with the result
                                                                   → question? → asker on that row → job's answers
```

**A job is owned by a row, not by a worker.** The pulse polls it with back-off and reads its END first and only from
the agent's own `final` (a job that does not say it ended has not; 48 h bound it). A job reached through the relay goes
with the account's credential AND the job's own token (`X-Job-Token`): one account can never read another's job. Its
result is bounded leaf by leaf (a fact at its tail is never cut away) and fenced; the rebrief never says «it did not
happen» for an outcome the agent calls uncertain, and a job given up is told as UNKNOWN. With no session to tell it, the
row ends FAILED. A row he ended releases the question it held.

**A step handed back is a stranger's DATA** (`nucleo/mesh_handoff.py`). An agent that cannot finish answers with a
`handoff`. `call` keeps what can be checked (the link and its domain, the phone, what the link carries, the NAMES of the
fields the form asks, the agent's own outcomes) and puts its prose under `agent_says`, fenced; its VALUES are dropped —
a form is filled from the order he gave (`your_order`), a field it lacks is asked to him. The rules are ours alone; the
agent's note can only make the worker do less. `hbmesh report` answers in the agent's own `reportOutcome` shape.

---

## 2 · Clusters — the mesh as conversation

`connectors/meshkore/` connects zaelar to MeshKore **clusters**, where agents hold ongoing conversations with
each other. The end-to-end algorithm — handshake, permissions, memory of a relationship, outbound guard — is
`zaelar-cluster-channel.md`; the threat model is `zaelar-security.md`.

**One mind, two keyrings.** There is no separate «cluster brain». The same FlashBrain drives voice, chat and
cluster; what changes is the profile. A peer is UNTRUSTED by default: tools off in code, an identity-safe
system prompt that never exposes the operator's name, PII or widget catalog, and a memory that is **written
but never read back into a passive prompt**.

**Private and public clusters.** Private ones are joined with a token; public ones are tokenless and listed in
the ⚙ Clusters tab. The engine's `/api/status` reports both.

**Small private groups use the same mechanism.** A group of friends whose agents pass messages, agree on a
time or trade a recommendation is a private cluster with a handful of members — the same connector, the same
handshake, the same permission model, with a narrower permission class on top (agents that may speak to each
other without reading each other's operator).

**The relationship to §1:** a Brain Worker running for a cluster peer inherits the UNTRUSTED profile, and
reaches the network through the same `hbmesh` bridge. That is safe by construction: the call carries no
operator data, and a peer can never spend the operator's money.

---

## 3 · Capabilities

| capability | where |
|---|---|
| Discovery through the Oracle (free agents only) | `nucleo/mesh_agents.py` |
| Worker bridge `hbmesh` (`find` / `serve`) | `nucleo/cli/mesh.py` |
| «Ask the network before the browser» in every web errand | `nucleo/workers/prompts/` |
| Learned route cache (7-day TTL, never on `general`) | `mesh_agents.route_for` |
| Paid agents: reported, never paid without authorisation | §1.4 |
| One declared skill per call (`hbmesh call`), priced only through a relay with an `agent` tariff row | §1.8 · `nucleo/mesh_call.py` |
| An agent's question on his row, his option back, his standing answers | §1.8 · `nucleo/mesh_dialog.py`, `mesh_jobs.py` |
| An agent's job owned by a durable row (poll, ask, end) | §1.8 · `nucleo/mesh_jobs.py` |
| A step an agent hands back: done once, its outcome reported | §1.8 · `nucleo/mesh_handoff.py` |
| Cluster channel (public + private, UNTRUSTED profile) | `zaelar-cluster-channel.md` |
