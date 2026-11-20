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
| `legacy:<source>` | the old path (`services/wall-legacy.js`): FlashBrain, notices, errands' boxes, A2A, task questions | its lines, as actions with ids |

The old path's lines are the old rules, moved unchanged into `wall-legacy.js` and turned into actions: our voiced line
is owed until the voice starts it, crawls as it is heard, and settles to what was heard (it waits `IDLE_GRACE_MS` for
its last caption after the voice goes quiet, because a final line never grows); his spoken line in course is one line
from his first partial to the attention gate's verdict, final in place or gone. Its one hand outside `legacy:` is the
acknowledgement of a typed line by its `cid` (the keyboard that wrote it).

## Never two writers for one line

A session of the manager writes its own lines; the engine marks every event of the old wall it still emits for that
session (`conv`: his line as the record writes it, the provider's replayed words, a typed line's announcement on a
manager's text door, our line owed and written, a notice card the manager's mouth paints), and the router leaves them.
A typed line's announcement always carries its `cid`, so the screen that typed it reads it as its own line with the
switch off too.

A line the manager left open when the session leaves it (a fallback to the old path, a reset) is deleted then; the
bridge also deletes a line of his that had no news for `STALE_MS`.

## Kept across a reload

`services/wall-storage.js`: the final lines, in localStorage (`hb_wall_lines`), 100 lines and a byte budget. The old
wall's history (`hb_chat_log`) is moved over once and its key removed. One divider after the restored lines says they
were said earlier.
