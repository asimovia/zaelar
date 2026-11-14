# Module · a2a — agent-to-agent network (V2-866)

Mechanism only. Theory and the full event catalogue: `docs/architecture/zaelar-a2a-network.md`. Wire protocol:
`a2a/PROTOCOL.md`.

## What it is

A separate top-level package (`a2a/`) that lets one owner's agent reach the agents of people they know, through a
store-and-forward mailbox, with zero open sockets and zero model calls in the protocol. One door: `A2AAgent`
(`a2a/agent.py`); `a2a.from_network()` builds it on the MeshKore network, `FakeNetwork` builds the lab.

| file | role |
|---|---|
| `identity.py` | Ed25519 key (the engine's MeshKore key, or `A2A_KEY_FILE`), network DID `did:key:<pubkey_b64>`, `MeshKore-Sig` headers, Ed25519→X25519 E2E (`seal`/`open`) |
| `envelope.py` | `a2a/1` envelope: signed, sealed, ≤ 16 KB, future-ts/expired/replay refused, kinds registry |
| `relationships.py` | one row per peer DID, the handshake state machine, mailbox cursor, replay set (file, survives restarts) |
| `items.py` | shareable items: typed resources a widget declares (`collection · stream · file · calendar · profile · widget-data`) with verbs and projections; never-shareable roots refused |
| `grants.py` | generic grants: item or selector × audience (`contact:` · `group:` · `network`) × verbs × expiry; default deny; store and policy are seams |
| `handlers/` | inbound gate (strangers dropped unread) + one handler per kind |
| `discovery.py` | HMAC hashes (`meshkore-people-v1`), people directory client |
| `transport/` | `base` contract, `fake` (in-process network reproducing the server rules), `http` signing, `mailbox`, `live` |
| `jobs.py` | pull idle/active, heartbeat, daily + contact-event discovery, beat rows, ⏻ |
| `server_api.py` | `WakeGate` for `POST /api/a2a/wake` (network key only), status access rule |
| `events.py` | `OPS`, the one table of observability rows; sinks; privacy guards |
| `__main__.py` | `python -m a2a` CLI for real agent-to-agent runs |

## Trust model in one paragraph

A contact is data: inbound text is stored with `trust="contact"` and handed to `on_message` as a card, never to a
prompt. Nothing exists before the owner's yes: the gate drops every kind but `connect.request` from a DID that is not
accepted, before decrypting it. An automatic match only proposes; `connect()` is the owner's yes. On accept the only
grant is `messages/append` (D7); every other item is an explicit, revocable grant. A live share is a temporary
`subscribe` grant that ends with the share.

## Grants are generic

Fixed scopes are only the first instances: `messages` (stream, append), `calendar` (projection `freebusy`,
intervals only), `profile` (public set), `activity.live` (stream, subscribe, temporary). A widget declares any
other item with `ItemRegistry.declare(Item(...))`; a grant may name an item id or a selector
(`kind:widget-data,widget:activity`, `schema:activity.route/1`, `*`). The engine replaces `JsonGrantStore` with an
adapter over the rules table and points `Grants.policy` at the consent gate.

## Engine surfaces (F3)

| piece | where | what |
|---|---|---|
| runtime holder | `a2a.set_runtime` / `runtime()` / `accepted()` | the running agent, reached by the turn and widgets without importing `server/` |
| consent cards | `server/a2a_cards.py` | `asker` keeps `request`/`propose` as durable cards; `POST /api/a2a/cards/{id} {yes}` answers; a message → one chat line |
| Network read | `GET /api/a2a/network` | relationships + grants, pending cards, recent rows (`events.recent`), declared items |
| turn tools | `nucleo/flash/tools_a2a.py` | `a2a_send · a2a_connect · a2a_grant · a2a_read`, offered only with `a2a_live` (on + an accepted contact); lines from `voice.a2a_*` |
| widget items | manifest `shareable: [{id, kind, schema, verbs, projections}]` | readers keyed `<widget>:<projection>` in `server/a2a_wiring.READERS`; no reader → not served |
| contacts | `widgets/contactos/a2a_actions.py` | `contact.saved` bus topic → `Jobs.contact_event`; `a2a` block on a contact; internal actions `a2a_request · a2a_accept · a2a_decline · a2a_grant · a2a_revoke` |
| consent classes | `nucleo/events/vocabulary.py` | `a2a.see · subscribe · append · edit · copy` |

## Cadence

| job | when |
|---|---|
| pull | every 15 min idle (`A2A_POLL_SECS`), every 30 s while an envelope arrived < 10 min ago, now on a verified wake |
| heartbeat | hourly |
| discover | daily; once per contact event (debounced 60 s); on the owner's order |
| beat | one row per `A2A_BEAT_PULLS` empty pulls |

## Observability — the OPS table

Every row: `kind=a2a · family=a2a · op · rel · cid · peer (8 chars) · dir · ok · ms · trace · agent · label`, plus the
op's own fields below. `tests/a2a/unit/test_events.py` asserts this table equals `a2a/events.py::OPS`.

<!-- OPS:BEGIN -->
| op | fields |
|---|---|
| `key_created` | `did` · `agent_id` |
| `registered` | `agent_id` · `roster` |
| `heartbeat` | `roster_state` |
| `pull` | `n` · `cursor_from` · `cursor_to` · `reason` · `status` |
| `beat` | `pulls` · `empty` · `avg_ms` · `max_ms` |
| `wake` | `sig_ok` · `wake_kind` |
| `publish` | `hashes` |
| `discover` | `trigger` · `hashes` · `matches` · `matched_by` |
| `propose` | `matched_by` · `batch` |
| `propose_answer` | `answer` |
| `request` | `matched_by` · `crossing` · `excerpt` |
| `request_card` | `answer` |
| `accept` | `scopes` · `crossing` |
| `decline` | `declined_until` |
| `disconnect` | — |
| `explain` | `lang` |
| `grant` | `item` · `verbs` · `audience` · `expires_at` · `how` |
| `revoke` | `item` · `audience` |
| `grant_notice` | `item` · `verbs` · `expires_at` |
| `msg` | `len` · `shown` · `excerpt` |
| `msg_blocked` | `reason` |
| `query` | `item` · `projection` · `args` |
| `reply` | `item` · `projection` · `n` · `fields` |
| `denied` | `item` · `reason` |
| `live_open` | `item` · `share` · `ttl_s` |
| `live_sample` | `share` · `seq` |
| `live_read` | `share` · `n` · `closed` |
| `live_close` | `share` |
| `dropped` | `reason` · `envelope_kind` |
| `send_failed` | `status` · `envelope_kind` |
| `error` | `where` · `exc_class` |
<!-- OPS:END -->

## The wake push: the one route reachable from outside

The network signs a tiny "you have mail" push to `POST /api/a2a/wake`. Every other `/api/*` route refuses a
peer that is not this machine (`server/api_guard.py`) and, on a session-routed deployment, a request without a
session (`server/ingress.py`). Both gates carry ONE exemption, `a2a.wake_exempt`, which only checks shape:

- the path the router dispatches on is exactly `/api/a2a/wake` (no prefix match, trailing slash or dot segments;
  the gates and the router read the same decoded path, so an encoded spelling reaches this handler or none),
- the method is `POST`, A2A is on (agent built), and
- a declared `Content-Length` of at most 256 bytes (a chunked body with no length is not exempt).

The same predicate lets it through `server/operator_gate.py` (a wake is nobody's click, and an unsigned one must
not cost a peer-process lookup). The exemption trusts nothing. The handler is the gate:

| step | answer |
|---|---|
| A2A off | 404 (and not exempt: the guards refuse it first) |
| network key not pinned at boot | 503, no crypto, no pull |
| body over 256 bytes while reading | 413 |
| `MeshKore-Sig` missing, not by the pinned network key, stale, replayed nonce, or body not `{kind: mail|live}` | 401 and one event, while within the failure budget (6 per source, 60 in all per 60 s); past it 429 and no event |
| verified, a pull ran < 5 s ago | 202 `{coalesced: true}`, no pull |
| verified | 202, one pull (off the event loop; pulls are serialised with the cadence thread) |

The signature is checked first and only failures are budgeted: behind a proxy every caller shares one peer
address, so a limit applied before the check would let anyone refuse the network's own wake. A nonce is stored
only after its signature verified (`identity.NonceWindow`), for as long as its timestamp can still pass the skew
check; the store is never cleared wholesale, and at its cap a new signature is refused. The key is pinned once at
boot from `A2A_API_BASE`, only over `https` (or from this machine) and only if it is a 32-byte key; otherwise
nothing is pinned and every wake answers 503 until the next start.

A wake never carries content: it only advances the next pull, which goes out with this engine's own credentials.
`status`, `network` and `cards/*` stay owner-only. Tests: `tests/a2a/unit/test_wake_admission.py` (includes the
disarms: without the signature check a forged wake pulls; with the nonce recorded before the check, junk burns it).

## Env

`A2A_API_BASE` (default `https://api.meshkore.com`) · `A2A_STATE_DIR` (default `<workspace>/.meshkore/credentials/a2a`) ·
`A2A_KEY_FILE` (a second identity on one machine) · `A2A_POLL_SECS` · `A2A_BEAT_PULLS` · `A2A_API_TOKEN`.

## Tests

`./.venv/bin/python -m pytest tests/a2a -q` — unit nodes 6.A1–6.A8, the two-plató run 6.A9 and the owner surfaces 6.A10 (`tests/a2a/suite.json`).
