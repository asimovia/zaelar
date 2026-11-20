# The conversation and turn manager (`conversation/`, V2-941)

One package that decides, for one account, when the person finished speaking, what reaches the model, which run is
current, what may act in the world, what our voice says and what the person actually heard — with every step written
to a store before it counts and every step said as an event. Built and tested **isolated** in F0; F1 wires it behind
adapters (`zaelar-conversation-adapter.md` is the speech half of that contract) and a switch that is off by default.

## The switch and the host

`nucleo/conversation_host/` is the engine side. Its switch decides once, when a session opens, whether that session
goes by the manager: the session (`conv=1` / `conv=0`), then the account (`conversation_manager` in
`config/settings.json`, false by default), then `ZAELAR_CONVERSATION=1` for development. It fails closed — switched on,
a session takes the manager only with every outside write held (`ZAELAR_HOLD_OUTBOUND=all`), its language chosen and
the manager's configuration passing; otherwise it takes the old path and says why. Off, nothing of the engine imports
the host: every import of it is inside a function. One `Conversation` runs per account, in its own thread, while a
switched session holds it.

What is not mechanism comes from data: the publication graces are genome thresholds (genesis
`conversation.thresholds`, each inside its declared bounds, refused out of them or out of their order), and whether a
typed line with the voice live is answered by voice too is his rule (`reply_voice_to_text`, a factory row he can
override), read at each reply through the `Prefs` port. `GET /api/debug/conversation/<session>` reads the proof of a
switched session: the runs the manager started, and what would mean another owner of the turn, which must stay at 0.

The model is the voice's model from the routing table, called through the engine's fast client (`model.py`); its
two orders, `reply(text, claims, complete)` and `no_reply(reason, complete)`, are tools of its own beside the
catalogue. Its prefix (`prefix.py`) only declares: the language it writes in, what it may read, that it may not act,
and the fields of its orders — one line each, byte-identical between turns, under 600 tokens. A numeric claim binds
only to structured evidence (one with a value); a figure from an unstructured read carries none. Its `model_done`
says which model and provider answered, after a relay too.

A switched session only reads (`tools_read.py`): the world through the search service (with the model's proposal
and no judge — the turn's classifier is never asked), a widget, his memory (no reinforcement), the agent itself, and
the catalogue. Each tool's class is derived from what it declares, never listed; a door that fails is a result the
model sees.

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
| Inbox | `inbox/` | The person's entries — a voice utterance (whole, or incomplete with what was heard), a text, a control — accepted durably and deduplicated by producer id, ordered by onset across devices and channels, collected into batches; every one ends accounted (told · silent · expired · applied · failed). What the engine owes the person is not an entry: it is a line in its own ledger (`Owed`), said as it is, by voice, when the manager is free. |
| Ledger | `ledger/` | Two items with ONE transition table: the person's request, and the reservation of an effect. The host's tasks, questions, what it owes and its mandates have their own rows and writers: referred to by id, never copied. |
| Composer | `composer/` | A pure function from the store to the prompt: a cacheable prefix, the state, the last turns (cut to what was heard), the input. |
| Gateway | `gateway/` | The only door out. In F1 a read passes and everything else is refused, with its event; whether a tool only reads is the class the host derives from the tool's declared act (`ToolSpec.act`). The reservation stays for F2, exercised by its own tests: it rests on the person's entries, seals and reserves in one transaction, is written ahead before the call, and an unknown outcome is reconciled by looking, never resent. |
| Mouth | `mouth/` | Two verbs, say and stop. What was heard comes back with its source — the voice process's estimate, a text shown on a screen, or unknown; a line nobody acknowledges ended «unknown». Cutting our voice when the person talks over it is the voice process's local rule. The conversation the model reads is the person's entries and our lines, cut to what was heard. |
| Manager | `manager/` | Linear: three states (free, running, speaking), the policy table (seven inputs × four columns, eleven operations), one run at a time, checkpoints where a stop, a new sentence or a resumed voice takes effect, and a deadline with its exit on every wait — swept by the clock's turn. Half a thought is not answered: after a voice closes with no sentence mark (the provider says so, as a boolean) the batch waits a moment before it may run and its reply waits a longer grace; after one with a mark the run starts at once and its reply waits a shorter one; if his voice comes back on any device that contributed, within the grace, the reply is never said and both travel together. When the model says, with its order, whether the thought is answerable (`complete`), its reading replaces the two graces: an answerable one goes out after a short grace from the last voice close, one with something missing after a long one — and a silent order read as incomplete closes only then. No field, or one that is not a boolean, leaves the marks' graces; on a text the field changes nothing. A silent close that waited looks for his voice right before closing, as a reply does before sealing. The graces only bound each other in one order — complete ≤ with a mark ≤ with no mark ≤ incomplete ≤ the hold for his voice — and `Config.misordered()` names the pairs out of it, for the host to refuse. A voice that cut our line and brought no word resumes that line once, from the last sentence heard. |

Ports (`ports.py`) are the seams to the outside: `Clock`, `Telemetry`, `Model`, `Tools`, `Memory`, `Mouth`, `Owed`, `Tasks`,
`Store`. A control by id with no handler here (without `Tasks`, cancelling a task too) is refused when it is accepted.
Two stores keep the same contract: the package's in memory (its tests) and the host's on `zaelar.db` (`nucleo/conversation_host/store.py`, rows `conv_rows` + `conv_meta` of schema v12, through `memory.api.conv`). The host runs the conversation in a thread of its own, with its own event loop: entries are handed over to it, its timer and an hourly prune run there, and it is the only writer of those rows. A transaction is exclusive on the shared connection: inside it no other store can be reached. The prune drops what is final and old, never a row in course. A transaction inside another
is refused at once; a reader that sweeps reads by state (what is in course), so nothing is archived to keep a table
small. A new owner of the account recovers what a dead one left — a dequeued batch back to the queue, an effect left
`submitting` as `submission_unknown`, and a voice it was hearing ended incomplete (`restart`), so its run asks again.

## The invariants

I1 an effect rests on a sealed intervention · I2 every final word belongs to one intervention · I3 a sealed
intervention — or one whose request is final — never changes · I4 a discard says its text and reason · I5 one writer
per account, fenced by an epoch · I6 every accepted envelope ends accounted · I7 the model always sees the core tools
and nothing runs it did not ask for · I8 nothing but a read reaches the tools (F1; F2 adds the person's authority) ·
I9 every request closes exactly once, within its liveness — counted from the close of the last entry of his that travels in its batch: waiting for him to finish a thought said in pieces is not stalling.

## How it is tested

Domain 13 of `tests/run_testmap.py`: one node per contract (13.1–13.34), each seen red with its mechanism disarmed.
The three wide checks: **P3** (13.22, 2,000 seeded random conversations in the gate; 13.26, 100,000 on request) judges
I1–I9 on what each case left, with crashes, hangs, lost acks, forged producers and races thrown in; **P2** (13.20)
replays recorded sessions as tokens and scores the boundaries whose evidence is firm; **P8** (13.23) kills the process
at every transition of a sentence and of the reservation, and restarts on the same store.

## Observability

Seven kinds, `conv_ear`, `conv_inbox`, `conv_run`, `conv_ledger`, `conv_effect`, `conv_mouth`, `conv_close`
(`telemetry.py` is the only source of labels), in the observer's `conversation` family. Every event carries its
cause, owner, epoch and refs, and every event is in a flow: a turn's trace is its request's root intervention, a run's events carry the trace it started with (a request answered in another's batch closes in that run's flow), a line owed carries its key, a stop the line it cuts, a control by id what it references. The test observatory's brain screen paints
a conv flow with its own stations (`CONV_STATIONS`), and `python -m conversation.replay <signals> --events <file>`
produces a flow for it to read.

## Not done in F0

No adapter: the engine does not run the package. The speech adapter's needs are measured (adapter doc A1–A10) on
synthetic speech only. Public architecture diagrams are unchanged until something runs live.
