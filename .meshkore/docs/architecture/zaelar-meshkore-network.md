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

### 1.8 A conversation with an agent — one skill, its questions, its jobs (V2-895)

`serve` is discovery plus one free-text ask of an agent's FIRST declared skill: right for «who has hotels in Madrid»,
blind for an agent that does several things. A booking is a different shape, and it has its own two verbs:

```
hbmesh find "<errand>"                                  → agents, each with its card's skills {id, free, describes}
hbmesh call <agent_id> <skill> --json @request.json     → the answer · a question (thread) · a job being watched
hbmesh reply <thread> --answer <question id>=<n>        → his answers back to the SAME exchange
```

**One skill, chosen from the card** (`nucleo/mesh_skills.py`). The worker calls a skill the card DECLARES; price is
per skill (its own `pricing`, else the card's; unknown is not free). A served skill teaches the playbook route of
that kind of errand as `<agent>/<skill>` (the genome's learned layer, V2-859), and the next `find` names it.

**Free, or through the relay — never paid by the engine** (`nucleo/mesh_relay.py`). A free skill goes direct. A
priced one goes only through a deployment's mediated egress (`<egress>/p/mesh/<agent host><path>`, with the
account's own egress credential), and only when the account holds a price for it — a row of the tariff family
`agent`, keyed `<agent_id>.<skill_id>`, that arrives with the lease like every other tariff. No relay, or no price:
refused before anything leaves, said in one line. Which agents a relay covers and how it books them is the relay's
business; the engine only debits its local lease when such a job is born. A `402` is still never paid.

**An agent that asks is not an agent that failed** (`nucleo/mesh_dialog.py` — the class). An answer whose SHAPE is a
question — a `questions` list at the top or under `result` (`{id, text, choices: [{label, set?}]}`), or an A2A task in
`input-required` — comes back as `agent_asks_user` with a thread id. Status words are never read. Before this, a
`422` carrying questions reached the worker as «the agents did not answer».

```
agent asks ──► hbmesh: agent_asks_user + thread ──► worker: bridge ask (choices as options), ends its turn
                                                                │
he answers ──► worker resumed with his answer ──► hbmesh reply <thread> --answer qid=n ──► request rewritten
               (THE asker: dialogue, never a card)                                          and sent again WHOLE
```

  · **Applying** an answer is the agent's own contract: a choice that `set`s dotted paths writes them into a copy of
    the request; a needed value (`needsValue`) fills only the choice's open slots, never a guess; a question with a
    `field` takes the value there; anything else is `{id, choice}` for a job.
  · **His standing answers.** A fully specified choice of a question that sets fields («any table», «±15 min») is a
    preference: kept as HIS rules row (scope `errand/mesh/mesh_serve`, key `mesh.mandate:<agent>/<skill>/<question>`,
    personal layer — never in the genome) and applied the next time that agent asks the same question in the SAME
    shape (same position, same fields). A question about one job («accept 15:15?») is never kept. What was applied
    from his standing answers is listed in the outcome (`applied_his_standing_answers`).
  · **Binding is by identity**: the thread (`mt_…`, `sys_kv mesh:threads`) holds the agent, skill, request, questions
    and job; his answer names it. The request key (`idempotency_key`, when the skill's own examples use one) IS the
    thread id: a resend can never become a second order.

**A job is owned by a row, not by a worker** (`nucleo/mesh_jobs.py`). A `202` that names a job is recorded on its
thread; the pulse (every reconcile beat) gives it a row of its own — born from the worker's row, with its session —
waiting `remote_job`, and polls it with back-off. A question the job raises goes on that row through THE asker
(`clarify`), its options declared, bound by `remote: {thread, question}`; his option goes back to the job's own
`answers` endpoint by INDEX, with the job's own token and no model. When the job ends (read by shape: `final: true`,
or a `result` with no question) the worker session that started it is resumed with the result, and the rebrief
forbids telling him «it did not happen» for an outcome the agent calls uncertain. A `409` (the agent refusing to
repeat or to act) is said as what it is and never retried.

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
| One declared skill per call (`hbmesh call`), its questions and his answers (`hbmesh reply`) | §1.8 · `nucleo/mesh_call.py`, `mesh_dialog.py` |
| A priced skill through a deployment's relay, priced by an `agent` tariff row | §1.8 · `nucleo/mesh_relay.py` |
| An agent's job owned by a durable row (poll, ask, end) | §1.8 · `nucleo/mesh_jobs.py` |
| Cluster channel (public + private, UNTRUSTED profile) | `zaelar-cluster-channel.md` |
