# Chat references — an errand's deliverable stays reachable from the conversation (V2-862)

**What it is.** When a Brain Worker errand delivers into a card (a report in `documento`, a results sheet, pictures in
`imagenes`, a card it builds or fills), that card is where the content goes — not the chat. To keep it reachable once
he has closed that card, the chat wall shows **one reference box per errand**: glyph, title, state, and a click that
reopens THAT deliverable. The box is drawn when the errand starts, so it stays in the thread even if the work ends half
done.

**Why it exists.** Operator, 2026-11-08: a long report correctly went into the document card instead of the chat, but
when he closed it nothing in the conversation said it had ever existed. His terms: mechanical and deterministic, for
every kind of content a worker makes, and the reference stays even if the work is left half done.

## The mechanism — one decision, one event, one door

| Step | Where | What |
|---|---|---|
| **Born** | `nucleo/dispatch/listener.py` → `nucleo/chat_refs.opened(rec, ctx)` | At the dispatcher's single door, right after the surface is sealed (`surfaces.set_once`) and the durable row exists (`rec.uid`). Every door into the dispatcher passes there. |
| **Decided** | `chat_refs.not_his` | The **surface** decides: one that names a card (`lista`, `item`, `informe`, `imagenes`, `widget`) draws a box; `voz` / `silenciosa` (`surfaces.delivers_no_card`) do not. Also no box for an errand that is not his: a child errand (`depth`/`parent_task_id` — its parent already has one), one born from an arriving event (`origin == "event"`, the stream worker), work a cluster peer asked for (`src == "cluster"`), or one with no durable row (nothing to reopen). No model, no reading of his words, no table of content types. |
| **Named** | `nucleo/dispatch/prepare.py` → `chat_refs.retitled` | The errand's composed name reaches the box. |
| **Card learnt** | `nucleo/acts/canvas.apply` → `chat_refs.note_show` | A `widget` errand's card is not known in advance; the canvas door tells the module which card a `worker:<key>` showed. |
| **Closed** | `nucleo/dispatch/session_steps.py` (and the never-ran path in `session.py`) → `chat_refs.closed` | Where the errand's sheets are already closed. `state`: `done` · `partial` (failed, cut, or done without ok — what it wrote is kept) · `cancelled`. A parked or resuming errand is not closed: its box still says «in progress». The card that held the deliverable is kept on the task (`task_artifacts` slot `card`). |
| **Kept** | `nucleo/docsheet.doc_close` → `widgets/documento/data.keep_task` | A report is kept whole or half done: as a file on the library's documents shelf (`library.index.save_text`, one owned file — keeping again updates it) and as the task's `document` artifact. The document card holds ONE document and the next report overwrites it; the artifact is what lets a reference reopen *its* report. |
| **Reopened** | `components/ChatRef.js` → `POST /api/tasks/reopen` → `nucleo/turn/task_recall.reopen` | The one reopen door the voice already used (`reopen_task`): the results sheet from the task (`widgets/results/rehydrate`), else the kept document (`documento.restore`), else the kept card. The frontend opens the instance through `hb:open-card`, like every other click. Nothing kept and no card known → the box says so instead of opening a blank card. |

## The event — `artifact`, family `worker`

One kind, emitted through `voice.observer.emit` under the errand's trace, so the SAME event is the observability
record and what the chat wall receives over SSE:

- `opened` / `retitled` / `closed` — `extra = {ref (task row id), task_id (session key), surface, card, title, state, file?}`.
- `skipped` — `extra = {..., reason}` with `reason ∈ no_card · child · event · cluster · no_row`. Draws nothing.

**Every errand leaves exactly one decision on record.** «Was the box made for this errand, and if not, why?» is one
query of the `artifact` kind by the errand's trace or `task_id` — never an inference from silence. «Did it close, how,
and which file?» is the `closed` row.

The kind is in `ALL_SCREENS` (`frontend/app/services/event-scope.js`): the chat is the same conversation on every
screen; a click opens the card on the screen that clicked.

## The frontend

- `store.upsertChatRef(d)` — ONE row per task (`{role: "ref", ref, text: title, surface, card, state, file}`): the
  first event inserts it where the conversation is; every later one updates it in place, so a relay, a retitle or the
  close never doubles it or moves it down the thread. The row is part of the persisted chat history like any other.
- `components/ChatRef.js` — the one view, drawn by the desktop wall (`ChatWall.js`) and the phone's chat sheet
  (`ChatSheet.js`). Styles in `core/components.css` (`hb-ref*`, tokens only). Strings `chat.ref.*` in the `ui` pack.

## What it does NOT do (yet)

- Pictures are not copied into the library: the `imagenes` viewer is reopened, and it shows whatever it holds now.
- A results sheet is not written as a file: it already belongs to its task (`task_artifacts` `result`).
- The chat history is per browser (localStorage, capped): a box that ages out of the wall is still reachable from
  the processes panel and, for a report, from Archivos.

## Tests

Nodes **2.1635** (the decision, the event, the hooks), **4.412** (one box that updates in place; both shells; the
reopen door; ES/EN strings) and **4.413** (a report kept whole or half done, and its reference reopening IT after
another report overwrote the card).
