# Messaging history — how much of an account's past is copied, and how much media stays

`connectors/messaging/history.py` · `config/messaging.default.json` · `connectors/messaging/archive/` ·
`connectors/telegram/backfill.py` · `widgets/mensajeria/media.py` · `widgets/mensajeria/views/deeper.py`

A linked account has years behind it. The engine needs today's conversations whole and everything that arrives
from now on; it does not need a copy of the account. Text is cheap (measured: about 500 bytes a message on disk,
index included) and media is not (measured: fourteen days of one account's media were 1.9 GB, one file 136 MB),
so each has its own bounds.

## Four ways a message reaches the archive

| Way | When | Bound |
|---|---|---|
| **Live** | every message that arrives or leaves, from the moment the account is linked | none — never dropped, never sampled |
| **First import** | once per account | days AND conversations AND messages per conversation AND a total |
| **On demand** | a search names a conversation and finds nothing, the conversation is opened, «load previous», an errand | one conversation, a bounded stretch per ask |
| **Where it lives** | a mailbox is searched in place; only what a search returns is archived | nothing is walked |

Each platform's mode is declared once (`history.MODES`):

- **walk** (Telegram) — the account pages its own history exactly and silently, so both the first import and the
  on-demand asks are served by the walker, one page per tick on its own task.
- **at_link** (WhatsApp) — a linked device gets the past only from the phone, once, when it is paired; every later
  ask for history is a notification on that phone. The pairing history is trimmed to the day bound; nothing is
  walked; an on-demand ask is ONE page of a conversation the card already holds, made only for a conversation
  somebody named.
- **on_demand** (mail) — the provider keeps and searches everything; a search the archive cannot answer is asked
  of the mailbox.

## The numbers (`config/messaging.default.json`)

A deployment overrides any of them in `config/messaging.json` (same keys; 0 switches a bound off).

| Key | Default | Why |
|---|---|---|
| `initial_days` | 90 | holds the person who wrote two months ago |
| `initial_chats` | 150 | the newest conversations; a busy account's ~100 active ones fit with room |
| `initial_per_chat` | 300 | weeks of a busy chat, the whole of a quiet one |
| `initial_messages` | 30 000 | the whole first import: about 15 MB on disk |
| `deep_messages` | 1 000 | one on-demand ask copies this much further back |
| `deep_per_chat` | 20 000 | a conversation is never copied past this |
| `media_file_mb` | 20 | a larger file is not downloaded by itself; its type travels, the bytes stay at the source |
| `media_budget_mb` | 4 096 | absolute bound on downloaded media |
| `media_disk_ratio` | 0.15 | …and never more than this share of the disk that holds it; the smaller of the two rules |

The bounds are caps spent newest first, which is what makes them adapt: a quiet account reaches the day bound
with a handful of conversations and copies little; a busy one reaches the conversation and message bounds.

## The first import (walk)

`Walker._list` reads the dialogs, sorts them newest first (the platform floats pinned ones to the top whatever
their age), keeps the first `initial_chats` that have something inside the day bound, and drops broadcast
channels. `Walker._page` copies one page of the first conversation in the queue: it asks for no more than the
conversation's and the import's remaining room, keeps what is inside the day bound
(`history.within_first_import`), and closes the conversation (`backfill.done`) at its beginning, the day bound
or its message bound. Past the total the import stops asking the platform anything.

## On demand

`archive.want(platform, chat_id)` or `archive.want(platform, name=…)` writes the ask on the `backfill` row
(`want`); it survives a restart and is idempotent while pending. The walker serves asks before the first import:
by id, or — for a conversation the archive holds nothing of — by finding the one dialog whose name is, or
contains, the name used. It copies pages until `deep_messages` are in, the conversation's beginning is reached or
`deep_per_chat` is held, then closes the ask (`archive.served`). An ask no dialog answers is closed, not retried.

Who asks:

- `search_archive` with a `chat` or `sender` and no match (or with `deeper: true`): `views/deeper.ask`. The answer
  carries `asked_history` and says to repeat the search in a moment, so «nothing found» is never said over a
  stretch that was simply not copied.
- opening a conversation from the chat list, and «load previous» — the card's own `load_more`, unchanged.

## Media

Scrollback and imports never download media: only its type travels. Live media is downloaded unless the file is
over `media_file_mb` — checked from the size the platform declares, before any byte is pulled (Telegram in
`service/inbound._capture_media`, WhatsApp in the bridge through `ZAELAR_MEDIA_MAX_BYTES`).

`media.sweep` runs hourly. It deletes downloaded files older than the operator's window (7 / 14 / 30 / 90 days or
«always») and then, whatever the window, the OLDEST files until what is left fits
`history.media_budget_bytes(folder)`. A message whose file left keeps its text, its media type and a `mediaGone`
mark. Only connector downloads and uploads are touched (`media.PREFIXES`); the archive, the store and the
connector sessions are never candidates.

## The directory is not bounded by the window

Who is a contact does not depend on what was copied: a contacts pass reads the platform's own book — its address
book and every named one-to-one conversation it lists (`zaelar-contacts-sync.md`). And a message arriving from an
account no row holds marks that source as owed a read (`contactos/sources.nudge`), so the person is in the
directory within one sync interval instead of at the next daily pass. It never creates a contact by itself.

## What is not bounded

Live text accumulates with no retention: at ~500 bytes a message that is on the order of 0.2 GB a year for a
thousand messages a day. There is no eviction of archived text.
