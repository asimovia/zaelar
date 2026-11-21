---
title: The contacts connector — one address book, two copies, one rule
category: modules
updated: 2026-09-15
owner: ricart
status: current
---

# `connectors/contacts/` — one address book, two copies, one rule

**Related:** `zaelar-widget-header-standard.md` (the bars and the plug button this is reached through) ·
`zaelar-google-connector.md` (the shared OAuth app) · `widgets/directory.py` (who a name is, and how to
reach them — the ranking, groups and contacts in memory: `zaelar-architecture.md` §5h-ter).

```
connectors/contacts/
├─ providers.py      where a contact can come from, and what each tier costs in consent
├─ oauth.py          PKCE, tokens in .meshkore/credentials/contacts_oauth.json
├─ google_people.py  the People API, and the two shapes: person→contact, contact→person
├─ service.py        fetch() and push() — never touches the widget's store
└─ server_api.py     /api/contacts/{status,connect,callback,disconnect}

widgets/contactos/
├─ gcontacts.py      the GLUE (the agenda's gcal.py, one for one): providers(), sync(), sync_state()
└─ data.py           _merge_imported() — the MERGE, because this is the store's own judgement
```

## The boundary, and why it is where it is

**The connector FETCHES and PUSHES. The widget MERGES.** `connectors/contacts/service.py` never opens
`widgets/_data/contactos/state.json`; the widget is the only module that knows which fields the operator
typed himself, and a connector reaching into that store would be a second writer of a record with no
arbitration.

So «did it sync?» is always a COUNT the widget produced, never one claimed from the connector.

## Who wins — the one rule

The link is two-way: a name or a phone changed in the agent is changed in Google too, the same way the
agenda mirrors Google Calendar.

That makes «who wins» a question every pass has to answer, and the answer is **whoever touched the row
last** — which each row's `updated` records.

```
  ┌── PUSH ──┐  rows whose `touchedAt` is newer than their `pushedAt` — he changed it, Google has not
  │          │  been told · plus `sync.pendingDeletes`, the rows he removed HERE
  │          └→ update_person (read-modify-write) · create_person · delete_person
  │
  └── PULL ──┐  what the SYNC TOKEN says changed (or everything, on the first pass and after an expiry)
             └→ _merge_imported · _drop_deleted
```

## It stays on

Sync is not a one-off import: linking the account IS the ask (2026-11-21). The consent reads it at once
(`sources.import_linked`, the one door, also called at a start with an empty directory), and from then on the
inbound half stays on with no switch: `widgets/background.py` calls `data.tick` on the manifest's cycle. The one
control on the card is the outbound half — «Sync with Google» (`sync_contacts`) sends what he changed here. The period lives in `gcontacts.PERIOD`,
not in the manifest — the scheduler wakes the module far more often than it should talk to Google, so a
card reopening never triggers a pass and the interval can change in one place. The card reads it from
`sync_state().every` rather than carrying a number nobody keeps in step.

⚠️ **It is a POLL because the People API has no push for a personal account.** «Permanently connected» is,
physically, a cheap question asked on a timer — and the SYNC TOKEN is what makes it cheap. A large address
book spans several pages; a full re-read every minute is a request budget spent to learn that nothing
happened. With a token a quiet minute is ONE round-trip that returns no people. A change lands within one
period rather than instantly.

Two rules of Google's govern the token, and both are load-bearing:

- **`sortOrder` may not be combined with a sync request** — it is «only used if sync is not requested». The
  sort was the half worth losing; the merge matches on identity, not on arrival order.
- **«When the syncToken is specified, all other request parameters must match the first call.»** So there
  is exactly ONE parameter set in `list_people`, not a full one and an incremental one that can drift.

An expired token (429 `EXPIRED_SYNC_TOKEN`, or 410 on older deployments) is retried once as a full read —
Google's own documented remedy — and the operator never sees it. A **truncated** read throws its token
away: a pass that stopped at `max_pages` never saw the last pages, and a token stamped there would make
everything it skipped invisible forever, with the card honestly reporting «sin cambios» about a question it
never asked.

### The clock that stops the storm

⚠️ **`updated` is a DATE, and a date cannot say «he changed it after we last sent it».** It says «today»
for the rest of the day. On a timer, a date rule would mean a PATCH per edited contact per minute — each one
succeeding and writing the same values. So a local write stamps `touchedAt` and a successful push stamps
`pushedAt`, and «ours» is one comparison of two clocks. Rows written before either existed fall back to the
date rule ONCE, and the push that follows moves them onto the precise path.

⚠️ **An import filling in a blank must NOT stamp `touchedAt`.** It is Google's doing, not his — stamping it
there sends Google its own value straight back, every minute, forever.

### A change made on his phone

The phone writes to Google, Google hands it to us through the token, and the merge takes it: a row that
arrived through a sync token is one Google CHANGED, and if we have nothing pending on it then Google
touched it last. That is the one case where the pull may REPLACE a value instead of only filling a blank,
and it is exactly what makes this a sync rather than a repeated import. A **full** re-read is never
authoritative — there «changed» is unknown, and treating every row as fresh would undo his corrections
wholesale on the first pass after an expiry.

### Deletions, in both directions, with a breaker

A mirror that reflects every change except a deletion is not a mirror: the row comes back on the next full
re-read and he has no way to tell why.

- **Google → here**: the token returns deleted people as a person carrying `metadata.deleted` and nothing
  else — no name, no email — so `list_people` separates them out. Handing one to the shaper returns None
  and the deletion vanishes silently.
- **Here → Google**: a pull can never carry this half. Once the row is gone from the store there is nothing
  left to compare, so `remove_contact` writes the intention into `sync.pendingDeletes` and the next push
  spends it. The queue is cleared only on a pass that actually reached Google.
- **A row he edited since we last sent it is not Google's to delete.** He touched it last — the same rule
  as every other conflict, applied to the direction that cannot be undone.

⚠️ **`_DELETE_CAP_SHARE` / `_DELETE_CAP_ROWS` are a circuit breaker around OUR OWN code, not a theory about
how many contacts a person deletes in a minute.** The failure mode of a sync token gone wrong is
«everything looks deleted», and the difference between a bug and a catastrophe is whether anything acted on
it. When it trips, nothing is removed and the card SAYS SO — a guard that protects silently is one he
cannot trust and cannot act on.

⚠️ **PUSH runs before PULL, and the order is load-bearing.** Pulling first would fetch a stale Google row,
merge it in, and then push the result back — laundering a stale value into a fresh one.

⚠️ **The pull never overwrites a non-empty local field.** A pass that undid a correction he had made would
leave him unable to tell which of the two surfaces was lying. The ★ travels one way only: starring in
Google stars here; un-starring there never un-stars the favourite he set on this card.

## How a person from any source is matched to a row here

One definition for every importer — Google and the messaging apps alike (`widgets/contactos/identity.py`). In
descending order of how much each PROVES:

1. **the same account** — the Google resource, the chat id, the handle this source gave last time. Survives him
   renaming the person here, and keeps a hidden person hidden.
2. **a phone or an address shared with a row** — ANY of the ones either side holds, a phone compared as an account
   (its last nine digits). The exception is a line, not a person: two rows of the SAME source, each with a real
   name, neither name contained in the other, on one phone or address (a home landline, a switchboard) stay two.
3. **name + city** — `add_contact`'s own rule, so the two doors agree.
4. **the name ALONE, only when exactly one contact here carries it.** This is what makes a re-import
   idempotent: Google routinely knows a city he never typed, so name+city alone would import a second
   «Marta Ruiz» on every pass. When two contacts share the name it stops.

A name is never a key. What only he knows he says once: `merge_contacts`.

## One person is one row

- **Folding.** Rows that rungs 1–2 prove to be one person are folded (`fusion.fold`) after every pass, and once
  over what was already stored when the store migrates. Nothing is thrown away: phones, addresses, channels, labels
  and ids are joined; the folded row is kept whole in `merged`, its id keeps resolving to the row that holds the
  person, and `split_contact` restores it — the two are then never joined again.
- **Names.** The shown name is the one he typed here, else his address book's, else the chat's. Every other name a
  source knows the person by is kept in `knownAs` with its source (the name she chose in a chat app, a nickname of
  his address book, the name she had before a rename) and finds her like a name. They are not his words: `aliases`
  are, and only those name a person outright.
- **Staying in step.** A change on the platform arrives by itself: PUSHED when the connector can tell — the
  WhatsApp bridge reports renames and the phone it learns behind a linked id, and a push only refreshes people
  already here — and PULLED on every pass of a linked source (the Google pass is pull-only; only his button sends).
- **A linked source feeds the directory by itself** (2026-11-18, one door since 2026-11-21). Linking the account
  is the ask: `sources.import_linked` reads it when the account is first seen connected with its book never read
  (`linked_now`, told by the connector's status), at the Google consent, and at a start with an empty directory;
  then every 15 minutes (`sources._due`). There is no switch for the inbound half. An arriving person that a row
  already proves becomes a CHANNEL of that row — the row now «has WhatsApp» — and only the others become rows.
- **The names a conversation carried.** Before a pass is folded in, each arriving person gains the names its own
  conversation has had in the message log (`sources._names_seen`, over `connectors.messaging.archive.chats`), by
  conversation id or by the phone that id is. A name several accounts carry is dropped (the log files his own name
  under every conversation he wrote in). A FULL name (two words or more) the source has for the account, when
  exactly one row is called that, is that row (`imports.match`): the account that shows the name she chose joins
  the row of his address book that had only an address.
- **Two entries of one address book.** Two rows of the SAME source on one phone or address are one person when
  their names start with the same given name, by sound, or one is a single word that is a stem of a word of the
  other (`identity.akin`): the nickname row and the full-name row. A shared surname proves nothing — a family on
  one landline stays apart — and neither does a line shared by people with different names.

## Whatever order the sources arrive in

Every importer ends in the same look back (`identity.unify`), and so does every start of the engine. It folds
what a key proves and then (`identity.by_name`) the pairs that only a FULL name joins: exactly two rows carry
that name — as the shown name or as one a source knows the person by — from two different sources, both in
sight, never taken apart. So the account that shows the name she chose and knows the one he saved, and his
address book's row under that saved name, are one row whether the chats or the address book were read first.
Once folded, the shown name is his address book's and the chat's name is one she is known by.

## Who is in sight

A source hands over two kinds of people: the ones it lists as HIS (its address book, his conversations) and the
members of his groups. A member nobody else knows is not a contact: the row is kept — the group counts him, the
mapping stops a later pass making him twice — with `hidden` and `keptBy: "member"`. So is an account whose only
name is a phone number (`keptBy: "no_name"`): a number never shows, names or renames a row. A kept-back row is
never a candidate of a lookup and is not listed among the rows HE hid. It comes back by itself
(`identity.surface`) when a source lists the person as his, his address book holds them, or the platform names
the account; a pass also keeps back the member-only rows an EARLIER pass made — never one he edited, starred,
named, wrote to, or that carries a phone or an address. The start step asks every source that gave groups with
members for one such pass (`sources.owe_members`, once per store).

## Who a said name is

`widgets/contactos/who.py` scores a NAME (never a sentence) against every row with no model and no table of names:

| A said word against a word of the name | Worth |
|---|---|
| the same word | 1.0 |
| the same sound (`directory.sound`: c/k/q, b/v, ll/y, soft g/j, a silent h, accents) | 0.9 |
| a stem («Salva» of «Salvador») | 0.75 |
| inside a name written joined | 0.7 |
| one slip of spelling — a letter missing, added, changed, or two swapped | 0.6 |

Said words are matched in any order, each to a different word of the name, against every name the row is known by;
his own word for the person (`aliases`) is the person outright; and what he said, joined, sounding like the part
before the @ of an address the row holds is a `likely` match. A row is `sure` (every word, by word or sound),
`likely` (every word, some by stem or slip) or `partial` (one word is on the row and another is not).

`who.find(name)` answers `one`, `several`, `partial` or `none`. Full matches hide partial ones. With no full match
the partial rows come back closest first, with `unmatched` = the said words NO row carries: a question with names,
never a match. Readers:

- `directory.resolve` (every outbound door) asks it when nothing matched word for word; a near spelling of several
  words never names a row that lacks one of them, so a door never sends on part of a name.
- the question door (`lookup.read_query`): ONE word several people carry — as said, by sound, or under an ending
  («the Odiles») — names every carrier, the ranking's leader first; the leader alone is who a send goes to, never
  the answer to «which … do I have».
- the turn's people block (`digest.people_named`): a first name plus one more word that no row spells that way is
  read by sound over the people of that first name (at most two pairs a sentence).
- the send worker's `find_contact` (`nucleo/request/send_contact.py`) returns the ranked rows with `confidence`,
  `match` and `unmatched`; the conversation he has open is still the first reading (`in_front`), and when it only
  SHARES part of the name it is the one to ask about first (`shares`).

Cost: one pass over the directory in memory (about 15 ms over 2 700 rows); nothing is sent to a model.

## Two People API rules the code is built around

⚠️ **An update needs the person's current `etag`**, and that is a feature: it is what stops us overwriting
an edit he made on his phone since we last read. Every update is a READ-MODIFY-WRITE — the same shape the
calendar RSVP uses, because a PATCH carrying an array silently replaces it.

⚠️ **`updatePersonFields` is a whitelist and everything listed is REPLACED.** A field we name but do not
send is CLEARED on Google's side. So the body is built from the values present and the mask from the body,
never from a constant — a constant mask would delete, on Google, every field that happens to be empty here.

## Scopes

| Tier | Scopes | Google's tier |
|---|---|---|
| `saved` (default) | `contacts.readonly` | sensitive |
| `saved+other` | `+ contacts.other.readonly` | sensitive |
| `sync` | `contacts` (read-write) | sensitive |

Read-only is the default on purpose: nobody gets write without choosing it. `service.can_write()` reads the
flag off the **granted** tier, never off a guess — the widget has to be able to say «solo puedo traer»
honestly.

⚠️ **The `sync` tier needs the `contacts` scope on the consent screen.** The Google OAuth client in use must
list `https://www.googleapis.com/auth/contacts` (Google Cloud console) before anyone can consent to it; when
it is absent the card says so rather than offering a write Google would refuse.

## Extension point

The provider strip already reserves places for **iCloud and CardDAV** (see the header standard); a new source
plugs in as a provider in `connectors/contacts/providers.py` behind the same fetch/push boundary.
