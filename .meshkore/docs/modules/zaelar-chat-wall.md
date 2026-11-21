# The chat wall — a component, one bridge, writers with names

The chat column is a component of its own (`frontend/chat-wall/`) that imports nothing from outside its folder. It
holds lines and one door that changes them; who writes a line owns it. Zaelar reaches it through ONE file,
`frontend/app/services/wall-bridge.js`, on the desktop (`components/ChatWall.js`) and on the phone
(`mobile/app/shell/ChatSheet.js`) alike.

## A line

`{ id, owner, role, state, re, n, at, text, heard, kind, data }` — `role`: `you` · `agent` · `box` · `note`; `state`:
`pending` (not judged yet: hidden with no words, dimmed with words) · `live` (being said) · `final`. `n` is the order:
set when the line is appended, never changed. A line's place is where it STARTS — his first word, our voice's start —
and nothing is ever inserted above another line. `re` names the lines ours answers.

Four actions through a writer: `append`, `update`, `replace` (boxes only), `delete` (not a final line). Every refusal
changes nothing and is counted. The invariants (each with its test, `tests/browser/unit/chat_wall/`): append-only
order; a writer touches only its own lines; his final line never changes; our final line only shortens to what
sounded; nothing is found by text, prefix, position or time; only final lines come back after a reload.

## The writers

| Writer | Who | Lines |
|---|---|---|
| `ear:<device>` | the conversation manager's ear (`nucleo/conversation_host/wall.py`) | his spoken line, id = its intervention: pending at his first words, final when accepted, deleted when discarded |
| `keyboard:<device>` | the screen that typed (the component's own composer door, `submit`) and the engine's acknowledgement | his typed line, id = the screen's `cid`, the same line on every screen |
| `mouth` | the manager's mouth | our line, id = its say id, live while its voice says it, final with what sounded |
| `notice` | the engine (`nucleo/conversation_host/wall_notes.py`), where a notice paints itself apart from the mouth | a notice's 🔔 line, id `notice_<key>`; not the question of an open card, not what the last line already says |
| `record` | the engine, when he answers a confirmation question (`nucleo/circuit/ask_trace.py`) | the question's record line, a note of kind `record` |
| `ref` | the engine, at every event of an errand that delivers into a card (`nucleo/chat_refs.py`) | the errand's box, id `ref_<row>`, replaced in place; the replace carries its role, so a screen that lacks the box appends it |
| `upload` · `a2a` | this screen's own components (`main.js`, `A2AView.js`), through the bridge's `writeLine` | a file added, an A2A card or a contact's message |

The engine is the wall's one writer for every line of the conversation (INI-078): there is no client-side writer that
reads the stream and decides a line (the old path's `wall-legacy.js` and its attention hold went). The open questions
are the cards at the wall's foot (`TaskAsk.AskWall`), never lines of it.

## Never two writers for one line

Each line has one writer, and the router paints only `wall` events: the stream's other events about a line (his
`transcript` and `interim`, a `notify` card, an `artifact`, an `ask_resolved`) paint nothing on the wall. A typed line
is the screen's (`keyboard:<device>`, by its `cid`) and the engine's acknowledgement of it is the same line.

A line the manager left open when the session leaves it (a fallback to the old path, a reset) is deleted then; the
bridge also deletes a line of his that had no news for `STALE_MS`.

## Kept across a reload

`services/wall-storage.js`: the final lines, in localStorage (`hb_wall_lines`), 100 lines and a byte budget. The old
wall's history (`hb_chat_log`) is moved over once and its key removed. One divider after the restored lines says they
were said earlier.
