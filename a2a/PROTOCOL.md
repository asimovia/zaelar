# A2A protocol `a2a/1`

The wire contract between two agents. Everything here is code: no step needs a model (I3).

## 1 · Identity

- Key: Ed25519. DID: `did:key:<base64(raw 32-byte pubkey)>` (standard base64, with padding).
- HTTP to the network: header `MeshKore-Sig: v1 <pubkey_b64> <ts> <nonce> <sig_b64>`, Ed25519 over
  `MK1\nMETHOD\npath\nsha256hex(body)\nts\nnonce`; ±120 s; single-use nonce. `path` is the URL path exactly as sent
  (a DID in it is percent-encoded with `encodeURIComponent` semantics); the query string is not signed.

## 2 · Envelope

```json
{"v": "a2a/1", "kind": "msg.text", "id": "<32 hex>", "ts": 1800000000,
 "from": "did:key:…", "to": "did:key:…",
 "sealed": {"alg": "x25519-chacha20poly1305", "n": "<b64 12-byte nonce>", "ct": "<b64>"},
 "sig": "<b64 Ed25519 by from over canonical(envelope without sig)>"}
```

- `canonical` = JSON, keys sorted, no whitespace, UTF-8.
- `sealed` decrypts to the `body` object. Key: HKDF-SHA256(X25519(from_x, to_x), salt = `id`, info = `a2a/1 envelope`),
  where each X25519 key is the birational image of the Ed25519 key (RFC 7748 / RFC 8032 expanded scalar). AAD =
  canonical(`{v, kind, id, ts, from, to}`). Only `kind` is readable by the network (it needs it for its lane rules).
- Size ≤ 16 KB on the wire. Refused: bad signature, transport sender ≠ `from`, `ts` > now + 5 min, `ts` older than
  30 days (`expired`), an `id` already processed (`replay`), oversize, unknown `kind`.

## 3 · Kinds

| kind | body | allowed from |
|---|---|---|
| `connect.request` | `{rel, name, note ≤ 280, matched_by}` | anyone (the only stranger kind; ≤ 1 honoured per DID per 24 h) |
| `connect.accept` | `{rel, name}` | a DID we asked |
| `connect.decline` | `{rel}` | a DID we asked |
| `connect.revoke` | `{rel}` | an accepted peer — ends the relationship and every grant |
| `msg.text` | `{text}` | accepted + the receiver's grant `messages/append` |
| `grant.notice` | `{item, verbs, expires_at}` | accepted — informs what the sender now shares |
| `grant.revoked` | `{item}` | accepted |
| `query` | `{qid, item, projection, args}` | accepted — answered by the receiver's grant `<item>/see` |
| `reply` | `{qid, item, projection, data}` | accepted, only for a `qid` we asked |
| `denied` | `{qid, item, reason}` | accepted; reason ∈ `no_row · expired · verb · policy_ask · policy_never · condition · unknown_item · too_big` |
| `live.offer` | `{share_id, item, schema, expires_at}` | accepted — the samples go through the live ring |
| `live.closed` | `{share_id}` | accepted |

Anything else, or anything from a DID that does not meet «allowed from», is dropped **unread** (not decrypted).

## 4 · Relationship

`none → outgoing | incoming → accepted | declined → revoked`. Crossing requests resolve to `accepted` without a
second card. The requester's `rel` id is adopted by the receiver, so both machines log the same id. A decline holds
30 days. The network's own rule matches: a peer may write anything only after the recipient has written to it
(accepting = replying).

## 5 · Items and grants (generic)

An item is a typed resource a widget declares: `{id, kind ∈ collection|stream|file|calendar|profile|widget-data,
owner_widget, schema, verbs, projections}`. A grant is `{item | selector, audience ∈ contact:<id>|group:<id>|network,
verbs ⊂ see·subscribe·append·edit·copy, expires_at, conditions}`. No row → denied. Unknown conditions → denied.
`copy` leaves a copy the owner cannot recall. Never declarable: memory, diary, vault, credentials, rules, state.

First instances: `messages` (stream · append, granted on accept), `calendar` (projection `freebusy`: intervals only),
`profile` (the public set), `activity.live` (stream · subscribe, temporary — a live share).

## 6 · Discovery

`HMAC-SHA256(key="meshkore-people-v1", msg=value)` lowercase hex; email trimmed + lowercased; phone E.164. A name is
never a key. Only mutual matches come back (each side published a hash the other looked up within 30 days). A match
proposes; the request is sent only on the owner's yes. A contact is proposed at most once per 30 days; `never` is kept.

## 7 · Network endpoints used

| call | auth |
|---|---|
| `POST /v1/mail/:to_did` → `201 {seq}` · `GET /v1/mail?after=&limit=` → rows or `204` · `POST /v1/mail/ack {upto}` · `PUT /v1/mail/me/policy` | MeshKore-Sig |
| `PUT /v1/people/me {hashes ≤ 16}` · `DELETE /v1/people/me` · `POST /v1/people/lookup {hashes ≤ 100}` | MeshKore-Sig |
| `POST /v1/live/:to_did {ttl_s, ring}` · `GET /v1/live` | MeshKore-Sig |
| `POST /v1/live/s/:id/samples` (≤ 2 KB) · `GET /v1/live/s/:id?after=` · `DELETE /v1/live/s/:id` | Bearer capability token |
| `GET /v1/a2a/server-key` | public |
| inbound `POST <endpoint>/api/a2a/wake {kind: mail|live}` | MeshKore-Sig by the network key; anything else → 401, no pull |

Live samples are sealed like an envelope body (salt = `share_id`): `{"sealed": {...}}`.

## 8 · Errors

Transport failures surface as `TransportError(status)` (`0` = unreachable). 5xx is retried once with backoff; 4xx is
not. Every failure is one observability row and the cadence goes on (I6).
