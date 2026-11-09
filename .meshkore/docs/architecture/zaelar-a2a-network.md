---
title: Zaelar — The A2A network: your agent reaches your friends' agents
category: architecture
owner: ricart
status: planned (V2-866, 2026-11-09) — the theory is fixed, nothing is built; §9 says what exists
---

# The A2A network — a third surface of the mesh

The MeshKore network reaches the engine through two surfaces today (`zaelar-meshkore-network.md`): **live agents**
(an errand asks an external specialist) and **clusters** (peers talk, open-ended). The A2A network is a **third**
one, and the sentence that tells it apart is: **a live agent serves an errand, a cluster holds a conversation, an
A2A contact is a PERSON you know whose agent can be reached by yours.**

| | live agents | clusters | **A2A contacts** |
|---|---|---|---|
| other side | an external agent that does a thing | peers that talk | the agent of a person in your contacts |
| relationship | none | membership in a cluster | a **mutual, accepted** relationship with per-contact scopes |
| transport | HTTP request/response | WebSocket, real time only | **mailbox** on the server (store-and-forward), signed envelopes |
| trust class | none needed | `untrusted` | **`contact`** — data, never an order |
| cost at rest | 0 | one socket per cluster, 24 h | **0 sockets, 0 processes, 0 tokens**: an hourly heartbeat and a pull |
| code | `nucleo/mesh_agents.py` | `connectors/meshkore/` | **`a2a/`** (reuses only `connectors/meshkore/identity.py`) |

This document is the **theory**: what every word means, how a connection is born, lives and ends, what crosses and
what never does, what it costs, and — §8 — **the one event every step leaves**, so that a test, the viewer and the
operator console read the same story. The plan with its tasks and open decisions is the initiative
`roadmap/initiatives/V2-866-…` (local); the product half lives in the private workspace.

---

## 1 · Vocabulary (one meaning each; the glossary carries the short form)

- **Agent identity**: the Ed25519 key already minted by `connectors/meshkore/identity.py`, expressed as a `did:key`.
  One per install (phone and desktop are the same agent). A factory reset mints a new one and loses every relationship.
- **People directory** (server): a **private** table `{hash → did}` where each agent publishes **its owner's own**
  email/phone hashes. Never in the public agent card.
- **Hash**: `HMAC-SHA256(network_salt_vN, normalised value)`; email lowercased, phone as E.164. The salt is public
  and versioned; privacy comes from the **mutual rule**, not from the salt.
- **Mutual rule**: the directory returns B to A only if B's row also contains one of A's hashes — people who have
  each other. One-sided lookup is an enumeration tool and does not exist (lab flag `A2A_MUTUAL=0`).
- **Match**: a directory answer `{hash, did, agent_id}` for one of my contacts. A match is a FACT, not a relationship.
- **Proposal**: the card the automatic triggers show the owner on a match («Marta's agent is in the network, matched
  by phone. Ask to connect?»). The automatic path **proposes, never sends** (D10).
- **Request** (`connect.request`): the first envelope between two agents; the only kind accepted from a stranger,
  rate-limited per sender.
- **Relationship**: one row in `config/a2a.json` per peer DID: `status ∈ {proposed, outgoing, incoming, accepted,
  declined}`, `cid` (the contact it is linked to), `scopes`, `since`, `declined_until`, `matched_by`.
- **Scope**: what B's agent will answer to A: `messages` · `calendar.freebusy` · `profile.public` ·
  `favorites.<category>`. A scope is a **rules row** `subject:<cid>/a2a/<scope>` → `allow | ask | never`, read by
  `consent.decide_act` — the same gate as every other act.
- **Envelope**: `{v:"a2a/1", id, rel, from, to, kind, ts, body, sig}` — Ed25519-signed by the sender; body
  end-to-end encrypted from F2 (X25519 derived from the same keys). `kind` ∈ `connect.request | connect.accept |
  connect.decline | msg.text | query.freebusy | query.profile | query.favorites | reply.* | reply.denied | external.*`.
- **`rel`**: the relationship id = `sha256(sorted(did_a, did_b))[:16]`. **Every envelope and every event of a pair
  carries it**, on both machines — it is the trace that lets a reader follow one handshake across two engines.
- **Mailbox** (server): a per-DID **log** — `POST /v1/mail/:to_did` (sender-signed) · `GET /v1/mail?after=<cursor>`
  (owner-signed) · `POST /v1/mail/ack`. Cursor + ack + retention: Kafka semantics from day one, so the backend
  (D1 → Queues → Kafka) is a server decision no agent notices.
- **Personas cluster** (server): a dedicated cluster with a **persistent roster** — every personal agent listed,
  `online · reachable by mailbox · away`, derived from the hourly heartbeat. Visible means a row, not a socket.
- **External lane**: envelopes `external.*` from a registered business agent to a person who has NOT accepted it
  (offers, questions). Refused **server-side** unless the owner's policy row opens it (`global/a2a/external` →
  `never | ask | allow`, default `never`). Designed, built later (F7).
- **Contact (trust class)**: the third class between `operator` and `untrusted`. A contact's text is a card, a notice
  or a memory pill with `trust="contact"`; never an identity slot, never `state`, never an order to the brain.

---

## 2 · How a connection is born — three triggers, one yes

```
                    ┌──────────────────────────┐
  daily job ───────►│                          │── match ──► PROPOSAL card to the owner ──► yes ──┐
  contact saved ───►│ discovery.lookup(hashes) │                      (Ask · Not now · Never)      │
  (emails/phones    │  mutual rule, one HTTP   │                                                  ▼
   changed)         │                          │                                        connect.request
  owner: «conecta ─►│                          │── match ──► no card: his words are the yes ──────┘
   con Marta»       └──────────────────────────┘── no match ──► «Marta is not in the network yet» (owner path only;
                                                                 the automatic paths stay silent)
```

| trigger | hashes looked up | when | why it exists |
|---|---|---|---|
| **daily job** (`A2A_DISCOVERY_CRON`, 09:00) | every contact's | once a day | the match depends on the OTHER side joining; a contact saved in May may appear in October |
| **contact created / edited** (`widgets/contactos` emits when `emails[]`/`phones[]` change) | that contact's 1–3 | at once, debounced 60 s | a new contact is tried today, not tomorrow at 9 |
| **the owner asks** (Flash tool `a2a_connect`, contactos action) | that contact's | now | the explicit path; his order IS the yes |

**D10 — the automatic paths propose, they never send.** With the mutual rule A and B usually discover each other the
same day; two agents sending on their own would each read the other's request as the answer to its own, and two people
would be connected with no human in the loop. So: one batched card a day (every new match, zero model calls), through
the one asker (`consent_ask`). «Never» → `declined_until=∞`; «Not now» → the 30-day rule may propose again.

**Crossing requests.** A `connect.request` arriving while my own request to the same `rel` is `outgoing` IS its accept
(my owner already said yes): `status=accepted`, `scopes={messages}`, one notice, no second card.

---

## 3 · The handshake — a state machine, nothing before yes

```
            propose (card)      yes            send
  (none) ──────────────► proposed ──────► outgoing ──────────────────────────► accepted
    │                       │ not now / never                ▲ connect.accept     ▲
    │                       ▼                                │                    │ crossing request
    │                    declined (declined_until)           │                    │
    │ connect.request arrives                                │                    │
    └──────────────────► incoming ── owner: accept ──────────┴────────────────────┘
                            │ owner: decline → connect.decline sent → declined
                            │ owner: «what does it imply?» → static i18n explainer (no model)
```

- `incoming` shows ONE card: «Ana's agent wants to connect (matched by phone). Accept? · What does it imply?» —
  through the asker, so a voice yes or a button both bind to the same row.
- Accept grants **`messages` only** (D7). Every other scope is a grant per contact, revocable, visible in Settings as
  a rules row.
- A `connect.request` from an unknown DID creates **no contact** until accepted; then the contact is created or linked
  by `matched_by`.
- Any envelope from a DID with no `accepted` relationship is **dropped on arrival, unread, with one event**. The only
  exception is `connect.request` itself (1 per DID per 24 h).

---

## 4 · What crosses, by scope — and what never does

| scope | A asks | B's agent answers | reads | never |
|---|---|---|---|---|
| `messages` (default) | `msg.text` | shows it to B's owner as a card; speaks it on request | — | the text never enters the passive prompt as an instruction |
| `calendar.freebusy` | `query.freebusy{from,to}` | `reply.freebusy{busy:[{from,to}]}` | `widgets/agenda/free.py::busy` | titles, places, attendees |
| `profile.public` | `query.profile{fields}` | only the fields B's owner marked **public** | `a2a/profile.py` over identity slots + an explicit public set | anything not in the public set; the set is empty by default |
| `favorites.<cat>` | `query.favorites{categories}` | entries of granted categories (wine, restaurants, doctors, clothing size, colour…) | the typed favourites collection (blocked on INI-026 A4) | ungranted categories |

- A query for an ungranted scope → `reply.denied{scope}` — never silently, never with data.
- Outbound text passes `connectors/meshkore/security.scan_outbound` (secrets, identity terms) before it leaves.
- Inbound text is a `contact` pill — readable on demand («¿qué me dijo Marta?»), never an identity slot, never `state`.
  Same lesson as `remember_external` (incident 2026-07-14), one class up.

---

## 5 · Where the engine already has the pieces

| piece | reused for |
|---|---|
| `connectors/meshkore/identity.py` (Ed25519 did:key) | signing envelopes, directory registration |
| `connectors/meshkore/store.py` `SecureJsonStore` pattern | `config/a2a.json` relationships |
| `widgets/contactos` `emails[]`/`phones[]`, `agents[]` (V2-854) | hashes; the contact ↔ DID link |
| `widgets/directory.resolve/subject_of` | «dile a Marta…» → `cid` → subject rung |
| `rules/` + subject rung (V2-806, V2-857), `consent.decide_act(subject=)` | scopes as rows, one gate |
| `nucleo/request/consent_ask.py`, `nucleo/circuit/asker.py`, `TaskAsk.js` | the proposal and the accept cards |
| `nucleo/pulse/notices.notify` | request / accept / message while away |
| `nucleo/pulse/loop.py` throttled supervisors, `scheduler.py` | the jobs (no new thread, no new process) |
| `nucleo/events/vocabulary.py` | topics `a2a.request / a2a.accepted / a2a.msg / a2a.query` |
| `widgets/agenda/free.py::busy` | free/busy without titles |
| `memory/slots.py` identity slots | the public profile set |

New code lives in **`a2a/`** only: `identity.py, envelope.py, relationships.py, scopes.py, discovery.py,
handlers/{connect,messages,freebusy,profile,favorites,external}.py, profile.py, transport/{base,fake,mailbox,
cluster_lane}.py, jobs.py, server_api.py, explainer.py, events.py`. Nothing in `connectors/meshkore` imports `a2a`.

---

## 6 · Cost — the budget the design is measured against

| job | cadence | cost |
|---|---|---|
| `heartbeat` | hourly | 1 POST (also refreshes the Personas roster row) |
| `pull` | 15 min idle · 30 s while a conversation is fresh (< 10 min) · 0 with server wake | 1 GET (204 when empty) |
| `discover` | daily | 1 POST with N hashes |
| `discover(contact)` | on a contact event, debounced | 1 POST with ≤ 3 hashes |
| `wake` | on demand | the server's signed push → one pull |

Idle: ≈ 121 HTTP calls/day, **0 model calls, 0 sockets, 0 processes**; ⏻ stopped → nothing runs; restart → overdue
jobs fire once. A hosted engine woken by the server can run `A2A_POLL_SECS=0` (pull on wake + hourly safety pull).

---

## 7 · Invariants (each with a test in F1; the list the two-plató run is judged by)

- **I1 · A contact is data.** No inbound envelope reaches the speaker or the passive prompt as an instruction.
- **I2 · Nothing before yes — in either direction.** No scope before accept; no `connect.request` leaves without the
  owner's yes or his own order (D10); strangers' envelopes are dropped unread.
- **I3 · The protocol costs no tokens.** Provider-call count in the two-plató test is 0.
- **I4 · Name alone never discovers.** Only hash matches; a name confirms.
- **I5 · One rule.** Every A2A act goes through `consent.decide_act` with the contact as subject.
- **I6 · Fail open, never break.** Dead mailbox, bad signature, unknown kind: one event, same cadence, nothing on the
  voice path.
- **I7 · Outbound passes the scanner.**
- **I8 · Separate code.** `a2a/` ↔ `connectors/meshkore`: one import, one direction.
- **I9 · External is refused before it is read.** The server refuses `external.*` for a closed policy; the engine
  never downloads it.
- **I10 · No step without its row.** Every handler, every job, every drop emits exactly one observability row
  (§8), carrying `rel`; a step the viewer cannot show did not happen — the test counts them.

---

## 8 · Observability — 100 % of every flow, on both surfaces

**The rule (two surfaces, one datum).** Capture lives in the engine (`observability/` + the bus sink) and is read by
the local viewer (◷) and by the operator console. Capture never switches off; adding a row, a field or a filter on one
side only fails silently (empty), so every row below is declared ONCE — in `a2a/events.py::OPS` — and `_CAT`, the
viewer catalogue (`GET /api/observability/catalog`) and the console read that table. A test asserts the table in this
document equals `OPS` (like the test that keeps `criteria.md` and the test map aligned).

**Shape.** One kind, **`a2a`**, family **`a2a`** (its own row in the viewer's catalogue, **on by default**: it is a
user-facing surface, not plumbing). Every row carries: `op` (below) · `rel` · `cid` (the contact id, when linked) ·
`peer` (first 8 chars of the peer DID — never the whole DID, never in the label) · `dir ∈ in|out` · `ok` · `ms` ·
`trace` (the stimulus: the cron, the contact event, his turn, the wake). The **label** names the contact, never the
DID: `🤝 Marta · request · out`. Free text that came from outside is a **bounded, scrubbed excerpt**
(`observability/scrub`, `calls.EXCERPT`); a body, a key or a hash **never** enters a row.

| flow | `op` | emitted at | fields beyond the common ones | evidence (what the outside world said) |
|---|---|---|---|---|
| **identity** | `key_created` | `a2a/identity.ensure` (once per install) | `did` (full, this is OURS), `agent_id` | — |
| | `registered` | `transport.mailbox.register` | `agent_id · roster` | server status |
| **jobs** | `heartbeat` | `jobs.heartbeat` | `roster_state` | status · ms |
| | `pull` | `jobs.pull` — one row per pull **that brought something or failed**; empty 204 pulls are summed into `beat` like the pulse's quiet seconds | `n · cursor_from · cursor_to · reason ∈ idle|active|wake|boot` | status |
| | `beat` | `jobs` every `A2A_BEAT_PULLS` empty pulls | `pulls · empty · avg_ms · max_ms` | — |
| | `wake` | `server_api.wake` | `sig_ok` (an unsigned wake is `ok:false`, 401, no pull) | — |
| **discovery** | `discover` | `discovery.lookup` | `trigger ∈ daily|contact|owner · hashes · matches · cid` (contact/owner) | the directory's answer: `matches` as count + per match `matched_by ∈ email|phone` (never the hash) |
| | `propose` | `discovery` → asker | `cid · matched_by · batch` (how many in today's card) | — |
| | `propose_answer` | asker callback | `answer ∈ ask|not_now|never` | — |
| **handshake** | `request` | `handlers.connect` | `dir · matched_by · crossing:bool` | excerpt of `note` |
| | `request_card` | `handlers.connect_request` → asker | `cid|unknown` | — |
| | `accept` | `handlers.connect` | `dir · scopes · crossing:bool` | — |
| | `decline` | `handlers.connect` | `dir · declined_until` | — |
| | `explain` | `explainer` | `lang` | — (static text; no model) |
| **scopes** | `grant` | `scopes.grant` | `scope · level ∈ allow|ask|never · how ∈ card|voice|settings` | — |
| | `revoke` | `scopes.revoke` | `scope` | — |
| **messages** | `msg` | `handlers.messages` | `dir · len · shown ∈ card|notice|spoken` | excerpt |
| | `msg_blocked` | `send_gate`/`scan_outbound` | `reason` | the scanner's term class, never the match |
| **queries** | `query` | `handlers.freebusy|profile|favorites` | `dir · scope · args` (field NAMES, interval bounds, categories) | — |
| | `reply` | same | `dir · scope · n` (intervals · fields · entries) | **what left**: field names and counts only — never values |
| | `denied` | same | `dir · scope · level` (why: `ask` pending / `never` / no row) | — |
| **drops** | `dropped` | `handlers.dispatch` | `reason ∈ stranger|bad_sig|unknown_kind|rate_limited|expired|replay` · `kind` | — (nothing from a dropped envelope is kept, not even an excerpt) |
| **external** (F7) | `external` | `handlers.external` | `dir · category · sender_kind · policy ∈ never|ask|allow` | excerpt only when policy ≠ never |
| | `external_refused` | server-side counter mirrored on `pull` | `n` (the engine never sees the bodies) | — |
| **errors** | the engine's `error` / `alert` rows (family already on) with `piece: a2a` | any `except` in `a2a/` | `where · exc_class` | — |

**Flows a reader must be able to follow end to end, with ONE filter:**

| read | filter | what appears (both engines in the two-plató run) |
|---|---|---|
| «did Marta's agent find me?» | `op=discover` | one row per trigger with `matches`, `matched_by` |
| «why was I asked / why wasn't I?» | `rel=<id>` | `discover → propose → propose_answer → request(out)` on A; `request(in) → request_card → accept(out)` on B; `accept(in)` on A — the same `rel` on both machines |
| «what did Marta's agent get from mine?» | `cid=<Marta> dir=out op∈reply,msg` | every reply with `scope · n` and the field names; every message with its excerpt |
| «what was refused?» | `op∈denied,dropped,msg_blocked` | the reason, never the content |
| «what does A2A cost today?» | `family=a2a` + `beat` | pulls · heartbeats · model calls (must read 0) |

**The console half.** The operator console shows the SAME rows by `rel`, `cid` and `op`, with a per-agent A2A
summary (relationships, scopes granted, envelopes in/out today, drops) — one datum, two views; a row added here is
added there in the same change (the private counterpart of V2-866 carries that task).

**Tests of this section (T590).** (a) the two-plató run asserts the multiset of `op`s observed equals the declared
expectation of the scenario; (b) every `op` emitted is in `OPS` and every `OPS` row is in this table; (c) a mutation
that silences one handler's emit turns (a) red (the disarm); (d) no row contains a 32-hex hash, a full peer DID, a
`sig` or a body longer than the excerpt budget.

---

## 9 · Status (what exists; nothing below is live until this table says so)

| capability | state |
|---|---|
| Ed25519 identity | exists (`connectors/meshkore/identity.py`), not yet used for signing |
| `a2a/` library (offline, fake transport) | **planned** F1 |
| people directory · mailbox · roster · wake (server side) | **planned** — contract MK-1…MK-9, built in the MeshKore repo |
| three discovery triggers, proposal card, handshake, scopes | **planned** F1–F3 |
| free/busy · public profile · favourites | **planned** F4 (favourites blocked on INI-026 A4) |
| external lane | **designed** F7, not scheduled |
| observability table above | **planned** T590, with F1 (the fake transport already emits) |
| verified live between two real owners | **no** |
