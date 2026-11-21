# The conversation and turn manager (`conversation/`, V2-941)

One package that decides, for one account, when the person finished speaking, what reaches the model, which run is
current, what may act in the world, what our voice says and what the person actually heard — with every step written
to a store before it counts and every step said as an event. Built and tested **isolated** in F0; F1 wires it behind
adapters (`zaelar-conversation-adapter.md` is the speech half of that contract) and a switch that is off by default.

## The switch and the host

`nucleo/conversation_host/` is the engine side. Its switch decides once, when a session opens, whether that session
goes by the manager: the session (`conv=1` / `conv=0`), then the account (`conversation_manager` in
`config/settings.json`, false by default), then `ZAELAR_CONVERSATION=1` for development. The value `text` takes his
typed lines only: every voice session stays on the old path (a choice, never alerted as a refusal), and a room's bare
`conv=1` does not override it — `conv=voice` asks for the voice explicitly. A voice session nobody decided (the
embedded voice) is asked the voice question. It fails closed — switched on,
a session takes the manager only with every outside write held (`ZAELAR_HOLD_OUTBOUND=all`), its language chosen and
the manager's configuration passing; otherwise it takes the old path and says why. Off, nothing of the engine imports
the host: every import of it is inside a function. One `Conversation` runs per account, in its own thread, while a
switched session holds it.

What is not mechanism comes from data: the publication graces are genome thresholds (genesis
`conversation.thresholds`, each inside its declared bounds, refused out of them or out of their order), and whether a
typed line with the voice live is answered by voice too is his rule (`reply_voice_to_text`, a factory row he can
override), read at each reply through the `Prefs` port. That row and its knob exist only for an account with the
manager switched on: off, the rules panel and the rule shaper see nothing new. `GET /api/debug/conversation/<session>` reads the proof of a
switched session: the runs the manager started, and what would mean another owner of the turn, which must stay at 0.

Every line of a switched session enters by one funnel (`entry.py`). A typed line — the voice holder's data channel,
`/api/chat` from another screen, the text channel — is handed to the account's conversation in its thread, and not to
the old typed lane: the inbox is its only order, so there is no second wait behind a voice. The text channel answers
in its own shape with the request's ids. The guards every entry shares live there once: a `LOG:` line is a note, a
stopped engine takes nothing — checked off the caller's loop, since reading the engine's state can wait on the shared
database lock; for the same reason the account's conversation opens on a thread of its own, and lines handed while it
opens wait in order. And a net: a line that still reaches the old turn's reply in a switched session opens
no turn — it is counted, said as an alert, and handed to the funnel. Until the voice half of the mouth, a reply is
shown on the chat wall.

The live passes run on a disposable engine with the switch on (`tests/conversation/e2e/sandbox.py`): the text suite
T1–T12 in both languages (`e2e/text_suite.py`, its cases frozen in `fixtures/suite/text.v1.json`), the bench of the
model's own `complete` reading (`benchmarks/complete_bench.py`), the frozen corpus and the simulated person. The text
channel's answer carries what each pass judges: the request's close, the reads its run made with their arguments, the
reads refused, and its trace. They run by request, never in the gate; what they compute is tested deterministically. Between two cases the sandbox resets (`conversation_host/sandbox.py`; only with the environment AND the file the
launcher writes in its workspace, refused on a real engine; the conversation closes before the memory's queue drains): the conversation's rows go and its lease is fenced at its epoch, so the next manager mints ids of its own
and no id names two conversations of one engine; what the cases wrote to memory, and the notices they left, are
forgotten from the mark the first reset takes (the seed stays). A flow read by an id is its newest rows, in order, from `since` on.

A run answers a BATCH, so one answer closes every request in it: `conv_close` comes once per request, each with its
`req`, and the run's `ended` says how many it closed (`requests`) — a reader counts requests, never closes per
intervention. An entry with no words is never an item for the model; a batch with nothing said fails with its line.

A typed line waits for nothing (`collect_ms`, a genome threshold, is 0: his gaps between lines are seconds), and a
burst is handled by a newer line superseding the run — which costs a model's first answer per piece. Debt, a client
change: a «typing» signal from the screen (the text's equivalent of his voice's onset) would let a batch wait for the
line he is still writing. A reply is sized by its channel: the prefix declares each channel's length as data (genesis
`conversation.reply_budget`) and the host gives each a generous ceiling (`conversation.max_tokens`).

What his voice says reaches the manager as facts of the ear (`voice/engine/pipeline/ear_feed.py`: words, the
provider's end with its confidence, the watermark, the edges of his voice), on a lane of the voice process's line to
the body that loses nothing: carried until the body answers, and past its ceiling a hole DECLARED, never silent — what
the ear was hearing then ends incomplete and is asked for again.

What the engine owes him lives in ONE ledger, `notices`. While a session of the manager holds the voice, `notify`
paints a line and CLAIMS it for that voice (`nucleo/pulse/notice_claim.py`) — no push, no «shown» — so the retry and
the drain to the next screen, which read `owed`, never touch it. The manager takes each claimed line once and says it
as it is when it is free and nobody speaks: said, it is `spoken`; not, it goes back to `owed` and its other ways run.
A claim past its deadline goes back by itself on the retry pulse; every move compares the state. A run that fails
owes the language's own «I lost that» line through the same ledger.

The model is the voice's model from the routing table, called through the engine's fast client (`model.py`); its
two orders, `reply(text, claims, complete)` and `no_reply(reason, complete)`, are tools of its own beside the
catalogue. Its prefix (`prefix.py`) only declares: who is who (the assistant by its name, never the person's; the person by his,
if known), the language of each reply (that of the person's entries it answers), what each read is for, the acts that
exist and are held in this phase (the event vocabulary's names, refused if called), and the fields of its orders —
one line each, byte-identical between turns, under 600 tokens. Every answer is an order: the provider is told a tool
call is required, and text with no order is never said. An entry reaches the model with its id, channel and time; a
figure that still matches nothing after the one repair gets the language's own line, never silence. Each close says
where its time went (queue, model, tools, grace, publish), and each port is slow by its own budget. The turns before
the last long silence (`session_gap_ms`) reach the model marked as an earlier session, with their age: a question
asked again another day is answered again, never taken for one already answered. Two rounds of text with no order,
or a run that reads to its cap, end in the language's own «I lost that» line — never in silence. Its `model_done` says
which model and provider answered, after a relay too.

A figure of data in a reply is published only against its evidence (D9). Evidence is what a read of this conversation
returned while still valid (one session, `evidence_ttl_ms`, counted `evidence_earlier_run` when it is not this run's)
and his own entries, read as text (counted `evidence_his_words`) — never a line of ours. Against STRUCTURED evidence the
whole claim matches; against a TEXT evidence its value is among the figures of that text, which the host's adapter
reads by walking characters, both ways numbers are written, and a duration in every unit it names («1 h 20 min» is
also 80 minutes; the unit names are the language packs' `duration_units`). A figure is matched as a person says it:
itself, rounded to fewer significant digits within 5 %, or in a scale («123.8 million», two significant digits at
least). A known limit: against a text the entity, the period and the metric are not compared. A DERIVED figure cites
EVERY evidence its operands are in, names its operation (count, sum, difference, mean, ratio, percent, product) and its
operands — each a figure of what it cites, used once — and its value is what the operation gives, rounded to two
significant digits at least and never read in a scale; a value the reply already had refused cannot come back as
derived. A figure that fails its repair gets the language's honest line; when that line was our last answer, its
second wording (`unverified_fact_alt`) — never «say it again» for a clear question. The figures of a reply that carry
no claim are counted on its `command` event: a measure, never a gate.

A switched session reads (`tools_read.py`): the world through the search service (with the model's proposal
and no judge — the turn's classifier is never asked), a widget, his memory (no reinforcement), the agent itself, and
the catalogue, his state by topic. And it carries out LOCAL acts (`acts.py`, F2 step 1): open, close, minimize, full screen and arrange a
widget, and the side panel's tabs — declared data (`declared.json`, `acts`) carried to the doors that already do them,
`nucleo/acts/canvas.apply` with the reservation as provenance (`turn:<effect>`) and the `panel` event; the widget an
act names is resolved against the catalogue of manifests, so a new widget needs no code. Acting INSIDE a widget is one
generic act, `widget_action(widget, action, payload)`: the action must be one the manifest declares (the widget in
front and `read_widget` give them with their fields), it runs through the data-op door every tap takes
(`data_ops.dispatch_and_report`, on the engine's loop) by the mode it declares — a `confirm` act asks his yes on its
row through the one asker — and an act whose output lives in its card brings the card. Music and video are widgets
like any other: playing is their cards' own declared actions. A message, or any act that leaves, is held here.
His errands are acts too (`acts_tasks.py`): start one by the one errand gateway, resume the pending ones TASKS lists by
id, reopen a finished one, stop one by the one cancel door, cancel a scheduled job, open the browser for him to sign
in. And before the model is called, his words are offered to the host's `Route` (`routing.py`): with a process of his
in course or a row waiting on his answer, the switchboard decides whether they are for it — a door that takes them
answers with its line and no model is paid; with nothing open it costs nothing. A message has ONE owner (`nucleo/send`):
with a draft open his sentence is read against it first; the model's `send_message` — or a widget's message act — is
handed to the owner with his words, and the owner's line is what he hears. Nothing leaves before his yes over one
person and a text, by the owner's lane: the switch lets the manager run with every other outside write held
(`ZAELAR_HOLD_OUTBOUND=all,-owner`; `declared.json` `sends_by`). His words of every answered batch are filed by the
memory agent (`record.py`, typed or voice as they came; a batch closed silent is never filed), and a note he leaves for
support is an act of its own (`note_for_support`): his words kept on the timeline, nothing else done. The agent
itself is changed by its own doors (`acts_self.py`): its name, how it listens, the rules and the style he dictates
(shaped once into the one rules table) and its own controls — and the live conversation's prefix is built again, so
STYLE, whose one source is the language pack's `speech_style` and the turn's shape as genesis and his rows set it,
reads as it stands. A widget's life — built or changed (an errand of kind code, asked at the dispatch door), deleted or
restored (his yes on its row), a name it opens by — and pictures shown go through theirs (`acts_life.py`). His network
too (`acts_network.py`): a cluster joined after his yes on the Clusters tab's row, a message to a cluster by the bridge's
tag door (said as sent only when it left), a collaboration's goal, his friends' agents by name — a message into a
cluster or to a friend's agent is a leaving type (`cluster.send`, `a2a.message`) and stays held at the gateway while
only the owner's lane is let go; what the network holds
is the `network` topic of `read_state`. A listings hunt is the one hunt the old turn runs too
(`search_listing.hunt`): the rows on his results sheet, the deep search started by itself when they are too few, and
the fact — how many, the rows with their evidence — said by the model. The first-run presentation (once per install,
language data, `nucleo/self/presentation.py`) rides every run as a PRESENT block while it is owed, and the batch whose
reply named the agent settles it; the rest of the old introduction phase (its prose, its judge, the greeting) is not
carried. A process of his in course or waiting on him is not routed before the model: it sees it in TASKS and answers it with
`task_answer`, by the one delivery door (R-3); only an open message draft reads his words first. An errand the model starts carries what it decided — its kind, its consent class, the surface he will look
at and the declared action it starts with, `start_task`'s arguments whose choices are read from the modules that own
them — with his words; a widget it orders built is his sure order (C4). Before the open doors, a phrase the action map knows VERBATIM (`Shortcut`, `shortcut.py` over
`nucleo.actionmap`, V2-942) runs its direct act with no model and the run ends with origin `actionmap`; a run that
answered with one declared canvas act and read nothing is the map's candidate (`actionmap.watch.candidate`), so the
map keeps learning from the manager. A pill of his memory is forgotten (soft, undoable) or corrected (through the
memory's one writer, the old pill superseded) by its id, which `recall` gives the model — no word of his is matched
(`acts_memory.py`). Each tool's class is derived
from what it declares, never listed; a door that fails is a result the model sees. The state comes from the engine's
own readers, each bounded within `state_tokens`, writing nothing. Every run carries what is open first (the tasks,
a message draft), the next days beside NOW, the widget in front (at full screen, in front on a phone, else the newest
opened) with its actions, their fields and what it holds, the facts memory knows of him, and a short index of the
widgets (id and mission from each manifest). The rest is READ when the model names it: another widget by
`read_widget` (resolved by its declared names and aliases, with its actions), and the topics `declared.json` declares
(`state_topics`: the connectors, what was done, the browser, every open widget) by `read_state`; the notices owed are not in it — the manager says them itself. Each answered batch owes one pair to the engine's conversation record (`kind='conv'`), at
least once, so «what did I tell you» finds a switched session too. And when his voice was lost — no word, a guard,
incomplete — and he types within a minute, that text's prompt says so, how long ago and why.

## Reading, answering, and never silence

A run reads at most `max_reads` times and for at most `read_wall_ms` in all (genome thresholds); past either budget
every read it asks for is refused with the reason to answer with what it has, and it is told once — the catalogue
itself is never cut. A provider deadline with nothing from the model sends the same step once to the stand-in
(`ports.RELAY`); a disposable engine can hold the titular and shorten the deadline to drive it live. A step with no
order — text instead, or an order the client could not read — is asked for its order once per run; a second with none
says «I lost that». A run never ends with a request of his open (`unended`). A `no_reply` to a typed line, or after
reads, is asked once for the reply. Half a thought whose rest never came within its grace gets the language's
`listening` line once, never twice in a row. «I lost that» said in place closes `recovered`. NOW is his local time
with its zone's name and offset (the `Clock` port's `zone`).

## In front of the ear

The host's guards are asked by the ear at every close with words (`Ear.guard`): a closed microphone; our own line
heard back — his voice rose while one of our last lines sounded or right after it AND his words are, in order, words
of that line (`voice/echo_text.py`), never after a question of ours ended; a turn every segment of which the browser
judged another voice, with «stick to my voice» on and a voice enrolled (`voice_lock`); and a turn the attention mode
says was not said to us, judged in the body with the body's attention fed from the ear lane (his voice's edges, our playback, our
reply re-anchoring the window as it starts). A cold turn let in notes why the conversation began (`attention_opening`), as the old gate does — but only the old
turn's prompt reads that note today (`why_listening`); the manager's prompt does not. A voice entry the model then closes
with no reply gives back the window its admission renewed (never a typed one, nor one whose voice cut ours). What they
throw away is a discard with its reason; what was set aside as
ambient comes back in front of the entry that called the agent by name — only what he said within `reclaim_tail_ms`
before it, in the same breath. In the voice process our own echo never cuts our line: the local cut rule cuts on his
words only when they are not ours (compared with what was SENT to say, a word cut short included). With no word, it
cuts only when his device declared echo cancellation (the browser's own `echoCancellation`, carried with his
microphone's switch): off or unknown, a rise alone cannot tell our echo from his voice — **a stop then needs words the
provider writes, or the button**. The agent's name and its spellings are key terms of the speech provider.

**A stop is an order the model chooses** (plan v3.2 §3): no word of his is read for it on this path. Beside reply and
no_reply the model has `stop_voice`, `stop_media`, `stop_run` and `stop_all`, valid as its first order before any read
it asked for (a no_reply the manager pushed back on does not spend it). Our voice stops at once and the line it cut is
never resumed; the host closes the attention window, stops what plays (each card's declared suspension) and, for
`stop_all` only, cancels his errands in course. A stop and a question are answered; a stop alone is silence (a typed
one gets the pack's `stopped` line). A batch that cut our voice and then fails says so on the screen only, never by
voice, owed or not. His voice rising over ours still cuts it at once, by the voice process's own rule; a button's stop
is still a control.

**Debt:** a figure written in words («trescientas libras») is not a figure; that would be the language packs' number
words, as the duration units are. An errand cancelled by `stop_all` cannot be resumed: he asks again (the manager
reads only, and `pending_work` offers no cancelled row).

## Why a package of its own

The turn used to be decided in several places at once (the speech plugin's endpointing, the voice pipeline, the turn
gate, the mouth), each with its own clock and its own idea of «the turn». The package keeps one of each: one arbiter
closes an intervention, one inbox orders everything that arrives, one ledger holds every request and the reservation
of every effect, one gateway is the only door out, one manager runs one batch at a time. It imports nothing of the engine (node 13.1):
stdlib only, no regex, no word tables (the person's words are never read by code here — only by the model).

## The pieces

| Piece | Path | What it owns |
|---|---|---|
| Ear | `ear/` | Speech signals → interventions. An intervention CLOSES only on the provider's end of turn + full coverage + the watermark past the voice's fall, or at a cap; an eager hint never closes it. Once ended it never changes: voice that follows is another intervention that amends it. If the voice is still up when the provider ends (another voice in the pause, a background), it closes on its coverage and the next one is born there; one born that way that falls at once with no word is discarded. A stream that stops beating is `incomplete`, and so is one longer than `intervention_max_ms` (`too_long`). The ear does not tell speakers apart. |
| Inbox | `inbox/` | The person's entries — a voice utterance (whole, or incomplete with what was heard), a text, a control — accepted durably and deduplicated by producer id, ordered by onset across devices and channels, collected into batches; every one ends accounted (told · silent · expired · applied · failed). An EVENT of the world (a message, a cron, a cluster, a worker) enters too, already routed by the host's router, with its source's authority, never his: it opens a request of its own, never joins nor goes ahead of his words (with his entry queued or his voice open it waits), and runs alone — no model — by the host's `Events` door, which carries its route out; it closes answered, silent, or failed owing him nothing. The pump routes every event by the one router (`nucleo/events/route.py`); with the manager on it hands it over (`conversation_host/events_in.py`), and the door obeys the route by the pump's one body (`pump.obey`) on the engine's loop; off, or when the conversation cannot open, the pump obeys it. A peer's turn on a cluster has its own composer (`connectors/meshkore/compose.py`: its system as language data, one relayed call, only the errand its permission grants) and enters the same way, its work started there and its reply handed back to the bridge (`events_in.run_as_event`). What the engine owes the person is not an entry: it is a line in its own ledger (`Owed`), said as it is, by voice, when the manager is free. |
| Ledger | `ledger/` | Two items with ONE transition table: the person's request, and the reservation of an effect. The host's tasks, questions, what it owes and its mandates have their own rows and writers: referred to by id, never copied. |
| Composer | `composer/` | A pure function from the store to the prompt: a cacheable prefix, the state, the last turns (cut to what was heard), the input. |
| Gateway | `gateway/` | The only door out, by the class the host derives from the tool's declared act (`ToolSpec.act`): a read passes; a local act is RESERVED — it rests on the person's entries, seals and reserves one row per operation in one transaction, is written ahead before the call, never sent twice, and an unknown outcome is reconciled by looking, never resent; an act that leaves is refused (held) until its owner's door is wired; every act is refused while he speaks. |
| Mouth | `mouth/` | Two verbs, say and stop. What was heard comes back with its source — the voice process's estimate, a text shown on a screen, or unknown; a line nobody acknowledges ended «unknown». Cutting our voice when the person talks over it is the voice process's local rule. The conversation the model reads is the person's entries and our lines, cut to what was heard. |
| Manager | `manager/` | Linear: three states (free, running, speaking), the policy table (eight inputs × four columns, eleven operations), one run at a time, checkpoints where a stop, a new sentence or a resumed voice takes effect, and a deadline with its exit on every wait — swept by the clock's turn. Half a thought is not answered: after a voice closes with no sentence mark (the provider says so, as a boolean) the batch waits a moment before it may run and its reply waits a longer grace; after one with a mark the run starts at once and its reply waits a shorter one; if his voice comes back on any device that contributed, within the grace, the reply is never said and both travel together. When the model says, with its order, whether the thought is answerable (`complete`), its reading replaces the two graces: an answerable one goes out after a short grace from the last voice close, one with something missing after a long one — and a silent order read as incomplete closes only then. No field, or one that is not a boolean, leaves the marks' graces; on a text the field changes nothing. A silent close that waited looks for his voice right before closing, as a reply does before sealing. The graces only bound each other in one order — complete ≤ with a mark ≤ with no mark ≤ incomplete ≤ the hold for his voice — and `Config.misordered()` names the pairs out of it, for the host to refuse. A voice that cut our line and brought no word resumes that line once, from the last sentence heard. |

Ports (`ports.py`) are the seams to the outside: `Clock`, `Telemetry`, `Model`, `Tools`, `Memory`, `Mouth`, `Owed`, `Tasks`,
`Store`, and the host's doors before the model (`Shortcut`, `Route`) and for an event (`Events`). A control by id with no handler here (without `Tasks`, cancelling a task too) is refused when it is accepted.
A run reads a WINDOW, never the account's history: the open items by state, the newest entries, lines and
interventions, the newest evidence — each one indexed query on `zaelar.db` (measured flat: p95 0.2 ms with 6000
exchanges, 0.6 ms with 60 000). An idle conversation opens no write transaction: its timer looks by reading, and
writes only when something changes. Every write of `conv_meta` (the lease) goes through the exclusive transaction.
From SQL a row's fields are read with `json_extract(row, '$.field')`.

Two stores keep the same contract: the package's in memory (its tests) and the host's on `zaelar.db` (`nucleo/conversation_host/store.py`, rows `conv_rows` + `conv_meta` of schema v12, through `memory.api.conv`). The host runs the conversation in a thread of its own, with its own event loop: entries are handed over to it, its timer and an hourly prune run there, and it is the only writer of those rows. A transaction is exclusive on the shared connection: inside it no other store can be reached. The prune drops what is final and old, never a row in course. A transaction inside another
is refused at once; a reader that sweeps reads by state (what is in course), so nothing is archived to keep a table
small. A new owner of the account recovers what a dead one left — a dequeued batch back to the queue, an effect left
`submitting` as `submission_unknown`, and a voice it was hearing ended incomplete (`restart`), so its run asks again.

## The invariants

I1 an effect rests on a sealed intervention · I2 every final word belongs to one intervention · I3 a sealed
intervention — or one whose request is final — never changes · I4 a discard says its text and reason · I5 one writer
per account, fenced by an epoch · I6 every accepted envelope ends accounted · I7 the model always sees the core tools
and nothing runs it did not ask for · I8 a read, or a local act through its one reservation on the person's entries, is all that reaches the tools ·
I9 every request closes exactly once, within its liveness — counted from the close of the last entry of his that travels in its batch: waiting for him to finish a thought said in pieces is not stalling.

## How it is tested

Domain 13 of `tests/run_testmap.py`: one node per contract (13.1–13.34), each seen red with its mechanism disarmed.
The three wide checks: **P3** (13.22, 2,000 seeded random conversations in the gate; 13.26, 100,000 on request) judges
I1–I9 on what each case left, with crashes, hangs, lost acks, forged producers and races thrown in; **P2** (13.20)
replays recorded sessions as tokens and scores the boundaries whose evidence is firm; **P8** (13.23) kills the process
at every transition of a sentence and of the reservation, and restarts on the same store.

## Observability

A turn's `flow end` is the conversation's (`cat: conversation`, never the `flow` kind's default), with the real steps
its run made — its reads, its acts and its answer, never the run's own repair steps — and the tasks it opened (the
declared `task_acts`). A run's acts run in its turn's trace, so an errand it starts carries the order's flow. An event's
run opens a trace of its own with its origin; it is a flow only when it did something, and one with nothing to do is
counted apart (`discarded`), like an ear's discard (`turns.py`).

Seven kinds, `conv_ear`, `conv_inbox`, `conv_run`, `conv_ledger`, `conv_effect`, `conv_mouth`, `conv_close`
(`telemetry.py` is the only source of labels), in the observer's `conversation` family. Every event carries its
cause, owner, epoch and refs, and every event is in a flow: a turn's trace is its request's root intervention, a run's events carry the trace it started with (a request answered in another's batch closes in that run's flow), a line owed carries its key, a stop the line it cuts, a control by id what it references. The test observatory's brain screen paints
a conv flow with its own stations (`CONV_STATIONS`), and `python -m conversation.replay <signals> --events <file>`
produces a flow for it to read.

## Not done yet

The package runs behind the switch, for his text and his voice. It READS, STOPS and carries out the canvas and panel
acts, a widget's declared actions (music and video included), his errands, his messages, the agent itself and a
widget's life, his network and the listings hunt (F2 steps 1-7c); the other acts that leave stay listed as held;
they come one by one through the existing single doors (the widget action runner, dispatch, the send owner), never
rebuilt.
The public architecture diagrams show the package and mark those acts as next.
