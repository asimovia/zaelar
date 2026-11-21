# Criteria — the standing rules of the engine

**What this is.** The rules the engine obeys TODAY, one line each, and nothing else: no history, no incident
narrative, no superseded version. When a rule changes, its line changes here and the old text is gone — the
story of how it changed is the diary's job (`.meshkore/docs/decisions.md`, then `decisions-archive.md`). An
agent that has read this file knows what the engine must do; an agent that wants to know why reads the diary.
The diary is local-only (gitignored): on a clone it does not exist, and this file is the whole public canon.

**How to read a line.** `CRIT-<group><n>` · the rule · `— since <date> · nodes <ids>` where the ids are nodes
of `tests/run_testmap.py` that guard it, and, when it helps, the code seam that implements it. A line marked
`⚠ sin test` ("no test yet") names a rule no node guards yet; it is a debt, not a decoration.

**How to change one.** Edit the line (never append a second line on the same topic), move the date, cite the
node of the test that proves the new behaviour, and write the WHY as a diary entry. The ratchet
(`tests/infrastructure/unit/test_the_criteria_are_one_and_current.py`) keeps every line dated and tested and
the contradictions table empty.

**The base, above all of these:** `.meshkore/context/principles.md` — mechanisms, not rules. A change that
bounds a CONSEQUENCE is a mechanism and stays; one that bounds JUDGEMENT is a rail and goes. Every criterion
below is the first kind, or it names the mechanism that replaced the second.

---

## 1 · What the mouth says (voice)

- **CRIT-V3 · A «yes» is answered with a START, never with a completion.** The outcome is reported when the work
 settles (`op_receipt`), witnessed against the widget's own view; a pool timeout is not an outcome; an op that
 could not start or whose dispatch raised is said as not done, never left behind «Done.». — since 2026-09-30 ·
 nodes 2.17, 3.35, 2.201.
- **CRIT-V5 · A claim is not a fact.** A delivery claimed over an empty sheet becomes a follow-up; «still on it»
 is said only about live work on THIS request; a result already spoken is not news on the next turn — nor an
 object our PREVIOUS reply (read from the conversation window, never a global) or a card's own sentence already
 named beside the model's words (V2-834 T08/T12). — since 2026-09-19 ·
 nodes 3.35, 2.86, 2.850.
- **CRIT-V6 · The agent's language, always.** Every spoken line is in the agent's language; an internal system
 note never sets the reply language (none rides a turn since the notes mailbox went, V2-851 F5); a stage direction
 the model writes is not read aloud. — since 2026-09-26 ·
 nodes 2.123, 2.152.
- **CRIT-V7 · The chat wall is the conversation, and the engine is its one writer.** Every line has ONE writer and
 is an action with an id: his spoken line is the ear's (pending where his voice rose, final with the words the inbox
 accepted), his typed line the keyboard's (its `cid`), our line the mouth's (live when its voice starts, showing only
 what sounded), a notice's 🔔 line, an answered question's record line and an errand's box the engine's
 (`wall_notes`); a line's place is where it STARTS, so his line stands above the reply it caused. The screen paints
 only `wall` events; the still-listening nudge is never said into a closed mic (2026-11-17). — since 2026-09-22,
 one writer since 2026-11-21 (INI-078) · nodes 4.572, 4.580, 4.615, 13.165 · `nucleo/conversation_host/wall.py`,
 `nucleo/conversation_host/wall_notes.py`, `frontend/app/services/wall-bridge.js`.
- **CRIT-V22 · A typed line barges in like a spoken one.** Any line he types while our speech is in course cuts it,
 then his line is answered: the line enters the conversation manager's inbox, and the voice process's `/voice/reply`
 with `cut` interrupts the speech in course on the session loop and then queues the reply, in one request, even when
 the cut itself fails (`voice/remote_session.CUTS_IN_VOICE_PROCESS`); our own voice stops through the same door, `cut`
 and no text (`conversation_host/voice_mouth.stop`). A stop the model orders ends what is playing through each card's
 declared suspension (`widgets/producers.suspend_all`) and, for everything, his errands in course through the row's
 cancel door (`conversation_host/stops.py`); what each app DECLARES running says what a stop ends
 (`state.report.<f>.stop`), validated when the manifest loads (`widgets/state_decl.problem`). — since 2026-11-14
 (rewritten 2026-11-21, INI-078 L1) · nodes 3.232 · `voice/engine/pipeline/child.py`,
 `nucleo/conversation_host/stops.py`.
- **CRIT-V23 · Several entries named and one written is said, and a cut turn's words reach the model.** How many NEW
 entries his words name is a question of the call door (`items_asked`, one trip with `acts_asked`): sure of several,
 with exactly one write holding at most one row in the slots its card declares as rows, landed as the turn's only
 op, the mouth says only part was done, in place of the canned ack; a refused write
 did nothing and is never «part». A turn cut before its first word owes its sentence
 to the next one, and the model is handed what the verdict judged: the owed sentences and this turn's as ONE user
 message. When every op of a turn was refused with a card's `error`, the mouth
 says its plain line: the `error` is the model's and is never said nor composed. A typed
 line the engine has no session for asks for a new room when the page holds one the agent left
 (`voice-arrival.onNoSession`) or its typed door stayed closed, and leaves one trace of its wait. — since 2026-11-16 · nodes 2.1790, 4.556, 4.560.
- **CRIT-V8 · The assistant's own name changes by the model's act, never by a regex, and fails CLOSED.** The new name
 is the declared argument of `rename_yourself` (`conversation_host/acts_self._rename` → `nucleo/self/identity.py`):
 the wake word tracks it at once and it is stored as `state.assistant_name`; nothing is read from his words. The
 memory processor files an `assistant.name` atom only for the name he ordered a moment ago (`identity.rename_heard`):
 a search term or a quoted name never renames the assistant. — since 2026-11-21 · nodes 13.129.
- **CRIT-V8c · The default name is DATA, and every spelling of it is his word.** An agent nobody named goes by the
 genome's per-language catalogue (`nucleo/genesis.json › persona.name`, `*` for any other language — «Johnny» today),
 read through one door (`genome/persona.py`); the memory never stores that default as a choice (a row an older engine
 stamped with the legacy default reads as unnamed), and the spellings an STT writes for the name (`persona.heard_as`)
 open the wake-word gate — server and browser ear alike — only while it is the name. A name he gives always wins.
 — since 2026-11-17 · nodes 2.1795.
- **CRIT-V8d · Word activation is knowledge and a switch, never a rail.** What it is, under the names people use for
 it («palabra de activación», «word activation», wake word), what it is for and that its button is on the desktop and
 the phone is self-knowledge, answered by `about_self` from its catalogue entry (`wake_word`); his voice switches it
 through the model's `set_attention` act, which writes where the button writes (`self.identity.persist_attention_mode`
 → `config.settings.update`), and the change reaches both shells through `orb:attention`
 (`voice/attention.on_mode_change`), applied by the one SSE reader they share (`frontend/app/services/sse.js`). —
 since 2026-11-17 (rewritten 2026-11-21, INI-078 L1) · nodes 3.237 · `nucleo/conversation_host/acts_self.py`.
- **CRIT-V8b · His own speaker and ⏻ are reachable by voice through their BUTTONS.** «Mute the speaker» (it keeps
 listening), «unmute», «switch yourself off» are one `controls` act (`nucleo/acts/self_controls.py`) reached by the
 action map's seeds or the model's `agent_controls` call — never a word table over his sentence, so a remark about the
 speaker does nothing; the act lands only on the screen that heard him (`origin_dev`), which runs its own 🔊 / ⏻ door.
 — since 2026-11-11 · nodes 4.487.
- **CRIT-V8e · His controls by voice name a STATE, run in his order, and a one-way act says the way back.** Mute/unmute
 read the 🔊 first (a state already reached is left alone) and the screen shows what the button holds afterwards; his
 voice's volume (`volume_up` · `volume_down` · `volume_set` 0-100) is the agent's own output on that screen, kept per
 device, never the system volume; `mic_off` and `off` cannot be undone by voice, so their line names the button, is
 said over the model's words and with acks off, and the screen acts once it was heard; several acts in one turn run
 in order, and a stop's one-word remainder that is a declared order («cállate y apágate») keeps its turn.
 — since 2026-11-17 · nodes 4.571.
- **CRIT-V8f · The agent answers about ITSELF from its own catalogue and its live facts, never from its prior.** A
 question about what it is, what it can do, how something of its own is done or its state («¿me ves?», «¿dónde
 vives?») is the model's `about_self(topic)` call — `topic` an id of `nucleo/self/catalog.json`, any language — and
 the answer pass reads that entry in his language (what it is, by voice, on screen, what it does NOT do) and only the
 live facts it names (`nucleo/self/snapshot.py`, one reader per truth; an unread fact is absent, never guessed). The
 camera's state is a flag on the screen's beat, never an image; the live tail says it is on only while it runs.
 Every act, tool, voice-named surface, Settings section, built connector and shipped widget is covered by an entry.
 — since 2026-11-17 · nodes 2.1802, 7.134.
- **CRIT-V21 · The introduction is ONE phase of genesis, run once, and the first turn is a system note.** The first
 turn's text is the i18n `kickoff_prompt`, one line per language: recognised by catalog at
 the gate, never substituted, never kept in the window or the short-term buffer as his words; the greeting's content
 is the introduction block, a system section carrying the name-and-voice offer — and, on an install's first turn,
 the PRESENTATION (the language's `introduction.presentation`: its name, word activation, that
 its name is his to change, one operator, his name), said once and marked `intro_presentation_said` by the turn whose
 reply named the agent; it carries the offer, so the offer is told with it (node 3.236, since 2026-11-17). The phase's watcher subscribes at
 boot whatever the language, and reads its condition per turn; the block reads THE TURN — when he just answered something we asked (the answer rule, or a sure `answer` verdict
 even if our reply did not end on the question) it says, CONDITIONALLY, that what he said is known before memory
 writes it, never guessing which goal it was (I1); it closes on his name AND the offer told (`intro_offer_told`,
 written by the close of the very turn whose prompt carried it — bound by trace — when that turn replied, or moot
 once he renamed us; declared residual: a reply that skipped the offer still counts it told), and then the block
 is gone. On ANY turn after a reply of ours
 that ended on a question, the state's closing line says what we asked (`build_flash_system` ← `answer_frame.asked_before`,
 the memory agent's own frame) instead of «the request that follows»: a bare answer reaches the model as an answer,
 and nothing of his line is read. — since 2026-11-12 · nodes 2.1734,
 3.206.
- **CRIT-V10 · The microphone is only parked over an ear that has HEARD.** In a wake-word mode the browser's
 recogniser may close the paid tap only after it has returned a result; its `onstart` proves nothing, and
 runs that keep ending empty within seconds give the licence back (`frontend/app/services/wakeword.js`).
 — since 2026-10-23 · nodes 4.208.
- **CRIT-V15 · Inside the attention window a line is still judged, and only an addressed line keeps it open.** In
 `always` the window admits without waiting (deafness inside a conversation is the worse failure), and the line is
 judged beside the turn by the same judge, which answers two questions — addressed? a clear request?
 (`attention.open_line`). A line judged not addressed renews nothing: its admission is given back and neither the
 reply's chunks nor its falling edge re-anchor (an armed delivery still does). A worker, or an act with a consent
 class or from `sensitive` up, started from a line that was not a clear request asks first — `consent.decide`
 (`licensed`, step 0; `his_yes` and `allow` do not clear it) and the one worker door
 (`dispatch_confirm.unlicensed_gate`, an `offered` question in his language; his yes licenses the line). A wake
 word, a typed line or a judge that failed license nothing new and keep today's path. — since 2026-10-26 ·
 nodes 8.26 · `voice/attention.py`, `nucleo/consent.py`, `nucleo/dispatch/confirm.py`.
- **CRIT-V16 · The STT boosts a place only where one is expected.** Keyterms bias every word of a session, so the
 national list of mis-heard towns is never sent on its own; only his own places (memory, behind
 `ZAELAR_STT_BOOST_FROM_MEMORY`, off by default) are boosted, spelled by that list. Re-measure
 (`gazetteer.expected_terms`) before boosting anything wider. — since 2026-10-26 · nodes 3.13 ·
 `voice/engine/speech/stt/gazetteer.py`.
- **CRIT-V14 · The microphone is conditioned per platform, and the agent-side filter is one setting that fails
 open.** A phone or tablet opens its mic with the full profile (echo cancellation + noise suppression + gain
 control), a desktop Mac with «isolate» (echo cancellation only, so macOS Voice Isolation works without the
 browser's suppression on top); `voiceIsolation` is asked only where `getSupportedConstraints` reports it
 (`frontend/app/services/mic-profile.js`). Agent-side voice isolation is `ZAELAR_VOICE_ISOLATION` = off | nc | bvc,
 default bvc (operator, 2026-10-26: on by default on desktop and phone, `off` is the flag): it attaches `livekit-plugins-noise-cancellation` to the room's audio input only on a LiveKit Cloud
 project; elsewhere (a self-hosted livekit-server refuses it) or with the plugin missing the session runs as with
 off and one warning says why (`voice/engine/pipeline/voice_isolation.py`). A self-hosted server skips it with one info line.
 `tests/voice/bench/voice_isolation_bench.py` measures WER with and without it; a result that raises WER on clean
 speech turns the default back to off. — since 2026-10-26 · nodes 3.138, 4.299.
- **CRIT-V18 · A late line is said in its own turn or not at all.** Nothing speaks for a turn after its reply: a
 tool round is said inside its turn, a door's line
 through the turn's mouth while it is live and out of turn only with its key (`turn/mouth`), and no model runs after
 the main stream. — since 2026-11-01, narrowed 2026-11-05 · nodes 2.1071.
- **CRIT-V19 · What a worker is told is never what he asked.** A relaunch (context handoff, stall restart) keeps his
 own words as the errand's request and goal; the brief written for the next worker rides in
 `context["worker_brief"]`, read by the worker prompt alone (`handoff.with_worker_brief`), so no title, chat box,
 status line or report can render it. It is worker-facing prose, in English like every prompt, never in i18n
 (V2-877 #1, the V2-652 rule on a new road). — since 2026-11-11 · nodes 2.1670 · `nucleo/workers/handoff.py`,
 `nucleo/workers/relay.py`.

## 2 · Consent — act or ask

- **CRIT-C1 · One consent rule.** A missing datum → ask for the DATUM; a doubt between two → ask which; a radius
 → ask; otherwise act. Genesis asks at `critical`; a spoken rule moves it in both channels, understood ONCE when
 written by one structured call (`rules/shape.py`: «pregúntame siempre antes» → `ask_at` sensitive, «no me pidas
 confirmación para los correos» → a gate at that channel's scope); every field is validated against declared data,
 removal is by id, and with no answer nothing is guessed into a gate. A question only clarifies WHAT he wants,
 never asks permission: when the verdict is sure of the order and its action at `consent.intent_act_at` (genesis
 0.6 since V2-886 D2, the operator's figure), the engine acts even if the model asked — below it the question
 stands. A verdict that disagrees with the model's call below the veto is a recorded doubt and the call runs
 (`verdicts.against_the_model`), never a «which one?». A question asking for a datum or a
 choice is DIALOGUE: it waits on its row like any other but is said in the conversation and never drawn as a card;
 only a question of consent (an act waiting for his yes) is a card (`asker.kind_of`, V2-886 D1). A clarify ends with
 its conversation: answered, it goes on; when his next turn surely answers none of the waiting questions (`none` at
 VETO) a clarify our last reply put closes, by its id (`circuit.asked_last`); unanswered past `clarify_wait_minutes`
 (30) the pulse closes it — each close cancels its row and says so in ONE `ask_closed` event, no line, never re-asked
 (`request/clarify_end.py`). — since 2026-10-26 · nodes 4.188, 4.185, 2.811, 2.1693 · `nucleo/consent.py`, `rules/shape.py`.
- **CRIT-C2 · A «yes» answers ONE proposal** and spends only that proposal's authority; an order that starts with
 «ok» is not a yes to a different pending action; every pending confirmation can be answered in words. A line
 that follows a question of OURS is his reply whether the verdict reads it as `answer` or `order` — the label only
 excludes (his own question, a comment, a complaint), it never licenses; one definition
 (`prior_line.answers_our_question`), read by the fragment guard and the stop. — since 2026-10-28 · nodes 2.156, 2.125.
- **CRIT-C3 · The agenda goes DIRECT.** Deleting or adding an item never asks; a bounded trash and `restore` put
 the row back in its slot (an appointment: `restore_meeting`, also for one skipped day or a series cut short); sweeps (clear or delete a list, clear all or a range) still ask. A row's content is
 never an order («add a task: buy bread» buys nothing) — the danger gate is repaired by SUBTRACTING, never by
 adding a pattern. — since 2026-09-21 · nodes 4.206, 4.188, 2.67, 2.238 · `widgets/agenda/data.py`, `nucleo/danger.py`.
- **CRIT-C3b · Two appointments of one title on one day are two rows.** Every verb that finds a row narrows by
 `currentTime` (its hour NOW), carried from an `item` that names its hour; still two at different hours with no
 conversation on one → the act asks with the hours, never the first in the list; a move that changes nothing refuses
 `no_change`; a moved row's line says where it was. A sure `corrects_last` onto ANOTHER row of the card's last act
 runs the card's own undo first (`undo_of`), once. — since 2026-11-12 · nodes 2.1725 · `widgets/agenda/edit.py`,
 `widgets/agenda/sweep.py`, `widgets/ref_day.py`.
- **CRIT-C3c · A correction onto the other row is ONE unit, whatever the model emitted.** The card's last act being
 corrected is recorded at the door and one door question asks which kind of correction it is (`correction_kind`:
 another item · a different change · undo only, asked only on that turn); once the turn's acts landed the card's END
 STATE says what is still owed (`correction_owed`: the move back, the same move on the other row). A sure «another
 item» runs it through the same door; a card that cannot name the other row, or a verdict not sure enough to act,
 says only part was done — never a completion nobody attested. A move already put back is never undone again. —
 since 2026-11-12 · nodes 2.1727 · `widgets/agenda/edit.py`.
- **CRIT-C4 · Building or rewriting a card of his asks first**, at the one door a worker is lit
 (`dispatch._run_session`, `kind == code`) — only when the order is in DOUBT. The conversation manager's build act
 carries his SURE order as a fact of the errand (`kind.SURE`, `conversation_host/acts_life.py`) and that errand starts
 with no question (`kind.sure_order`); anything else asks ONE question, worded for him (`kind.asked`). The cluster
 dev-worker is exempt. A start gate's question is on its row BEFORE it is said (`confirm.park`): his answer has
 somewhere to go from the instant the gate decides to ask. ONE act, ONE question: a send asks once, at its exit door,
 never also at its start (CRIT-C14). A yes he gives BEFORE the question exists — the send is still being prepared — or
 a go-ahead he gives WITH the order («send her a message, and I already confirm you can send it») is read once at the
 exit door from his own words on the row, by a model (`switchboard/act.read_his_go_ahead`, off the loop; an order to
 send is not a go-ahead; unread or unsure, he is asked), kept in one slot (`EARLY_YES`), taken once (`took_early_yes`)
 and valid only for a text made of his own words (`_his_own`: what the worker wrote is in what he said), never for one
 the agent composed. A send the engine took to its receipt is never judged unmet nor relaunched by its session's close
 (`send_receipt.owns_the_verdict`, `circuit._close`). The local ear's wake backstop never answers words the paid ear
 already delivered as a turn (`agent_events.heard_by_the_paid_ear`). — since 2026-09-23, narrowed 2026-11-17 and
 2026-11-18 (rewritten 2026-11-21, INI-078 L1) · nodes 2.76, 2.1170.
- **CRIT-C4q · ONE live confirmation question per act, and one line when he answers it — any act that asks.** A
 question's identity is its act and its terms (`ask_trace.terms_of`); the row keeps one question at a time, so a new
 one over it SUPERSEDES the one before (`asker.ask` → `ask_trace.superseded`): said on the timeline, its card
 replaced on screen, its id refused by the answer door — no yes can reach a question whose terms changed. His yes or
 no to a consent question never just vanishes: the answer door leaves ONE record line, worded from the fact with his
 name (`ask_trace.resolved`, «<his name> confirms …»; «the operator» when the state has no name), which the wall
 paints as a `record` row — the question card's own surface and accent edge, neither bubble, in both themes and on
 both shells (`shared-surfaces.css`, node 4.577) — and keeps in its place. A clarification is dialogue and leaves none. — since 2026-11-18
 (V2-931) · nodes 2.1808 · `nucleo/circuit/ask_trace.py`, `nucleo/circuit/asker.py`, `nucleo/cli/worker_api_answer.py`,
 `frontend/app/services/sse.js`.
- **CRIT-C4w · What the engine tells him is a FACT worded by a model, never a fixed sentence.** The engine decides the
 fact («the message is ready», «sent and confirmed», «could not be sent: why», «stopped»); `nucleo/wording.word` hands
 it to a small warm model with the voice's rules — one short sentence, different every time, about WHAT HE ASKED FOR
 in his terms, never «tasks», «processes» or «flows», nothing the fact does not state — and the language's own line as
 an example. The plain line is said only when no sentence comes back inside the line's budget: never silence. A line
 is worded off the loop that carries the voice. — since 2026-11-18 (V2-933) (rewritten 2026-11-21, INI-078 L1) · nodes
 2.1806 · `nucleo/wording.py`, `nucleo/send/ask.py`, `nucleo/request/send_receipt.py`.
- **CRIT-C4x · While something he asked for is being worked on and nobody is talking, he is told it goes on — and it
 is his to silence.** The pulse says one short worded line (`nucleo/pulse/still_on_it.py`: that it goes on, and the
 step the errand reported) after a silence drawn at random between 5 and 40 s since the last thing said in the
 conversation (his turn, ours, a filler, a notice — never bare voice activity), a new draw every time somebody
 speaks; only while an errand RUNS (not waiting on him, not queued, not paused), with a live voice session and
 nobody speaking. It is a courtesy, never a debt: a line that could not be said is dropped
 (`notices.notify(ephemeral=True)`: not pushed, not owed, state `dropped`). The genesis style knob
 `still_working_lines` is a `voice` row of the rules table: a rule of his («no need to tell me you are still on it»)
 turns it off, and removing the rule turns it on again. An errand that has NOT started (held at the gate) is never
 told as «still on it»: after 20 s of hold he hears that it has not begun, why, and that he can have it started
 anyway, then again at intervals that double up to ten minutes (`held_due`); and the turn's own facts say «NO HA
 EMPEZADO», never «stuck», so a turn cannot promise to relaunch what it cannot start. — since 2026-11-18 (V2-935) · nodes 2.1813 ·
 `nucleo/pulse/still_on_it.py`, `nucleo/style_policy.py::still_working_lines`.
- **CRIT-C4c · Every appointment he writes carries its notice**: a timed one ~2 h before, an all-day one at 09:00 that
 day; an asked `remind` wins; items synced from Google stay silent. — since 2026-10-10 · nodes 2.250.
- **CRIT-C4d · A notice is a ROW and reaches him exactly once.** Every reminder, finished job and pending approval goes
 through `nucleo/pulse/notices.py`: voice when he is at a screen, Web Push to his devices when not, `owed` (retried, then
 shown on the next screen) when nothing could take it — the same `dedupe_key` never twice. A DEFAULT appointment
 notice that Google Calendar alarms itself is `covered` (read at fire time); an asked one is always ours. ⏻ silences
 the voice, never the push. Two appointments with the same words at the same instant share ONE scheduled notice
 (`agenda.reminders._schedule_reminder` answers with the pending twin), kept while any row still carries it. — since
 2026-10-25, twins 2026-11-12 · nodes 2.800, 2.801, 2.802, 4.271, 3.205 · `nucleo/pulse/notices.py`,
 `nucleo/pulse/webpush.py`, `nucleo/pulse/wake.py`.
- **CRIT-C4e · A named weekday that is today is TODAY** while the hour he said is still ahead (or he said none);
 otherwise the next one. One rule, `widgets/agenda/when.coming_offset`, read by the widget's date resolver with the
 act's own hour (add and move); the prompt's day list starts today, marked. A «next»/«que viene» weekday keeps its
 strict rule in the said-day guard. — since 2026-11-11 (V2-886 0c) · nodes 2.1694 · `widgets/agenda/when.py`.
- **CRIT-C4f · An action's end state is rendered over what the card STORES**, never over the call's raw words: a card's
 data module may declare `spec_call(action, payload) → (action, payload)` — the act whose end state the call owes and
 its values normalised as the row keeps them — and `nucleo/circuit/spec.render` reads it (`circuit/card_call.py`). — since 2026-11-11
 (V2-886 fila 5) · nodes 2.1695 · `nucleo/circuit/spec.py`, `widgets/agenda/spec_call.py`. Where the app declares
 `state`, a clause names `report.<field>` and is read from what its surface REPORTS on the screen it lives on, never
 from the order (`nucleo/circuit/reported.py`): a field the surface has not acked WAITS (the op's ending leaves it, and
 the mouth names it as asked — «On it: «title»», a bare ack «asked» — never «Done», `reply_receipts.unconfirmed`); nothing acked within `PENDING_S`, or no surface at all, settles `unverifiable` with the reason
 `no_ack` — asked, never done nor failed, no spoken correction; an acked contrary report is unmet only at
 `INLINE_GRACE_S`, and not corrected again when the app's own late tell said it. — since 2026-11-13 (V2-884 1b, A6) ·
 nodes 4.411, 4.520. A contrary reading of a report the surface made BEFORE the act was born is no verdict on it
 either: inside the grace it waits as asked (`reported.unheard`), and the mouth says the short asked line, never
 «it isn't on the widget, so it's not done». — since 2026-11-18 (V2-934) · nodes 2.1810.
- **CRIT-C4b · A worker never deletes a card.** Deleting is a confirmed act (`pending_confirm`, the UI's Yes/No);
 the first verb of a request names its act, so a build that mentions deleting its own entries builds. — since
 2026-10-09 · nodes 2.246.
- **CRIT-C5 · An act that LEAVES runs only when the verdict backs it and its recipient is certain.** A send, a
 forward or a meeting invitation (`external.send`) runs when the verdict does not name another action; unbacked, it
 is DROPPED with a note to the model — never turned into a question, because the next «ok» would answer it. Its
 recipient is never a doubt: one he did not name (this turn or his last 15 min) is asked «¿se lo mando a X?», a
 spelling-only near contact is named back, never written to, and the engine never turns a draft into a send to
 somebody he did not name. When it was asked, the yes is HIS words (a plain yes, or the judge's YES), never the
 model's `confirmed=true` over a sentence about something else. A WORKER's send is never dropped or run on a reading of whose
 words named the person: it is asked, once, at its exit (CRIT-T2b), and no send worker is born from a lean alone
 (`message_channel.backs_a_send`). — since 2026-09-29 ·
 The question names the person as he knows her (`directory.shown_as`) and the card carries its row's title
 (`asker.title_of`) — never a raw id, never «a process» (V2-886 D5). —
 nodes 2.106, 2.730, 2.1691 · `nucleo/acts/message.py` (`asked_if_leaving`), `widgets/mensajeria/outbound/`,
 `widgets/confirm.py::backs_a_yes`.
- **CRIT-C6 · An action does not manufacture permission for its own side effects**; the confirm gate asks
 SOMEONE, and its «yes» returns to the click it stopped. — since 2026-09-18 · nodes 4.21.
- **CRIT-C7 · A transactional op never enters the task list** (deleting an item, sending a message); the list is
 for work that takes time and that he may come back to; its row ends only through `circuit.settle`. — since
 2026-09-21 · nodes 3.82, 2.1013, 7.91.
- **CRIT-C9 · A send held for his word is a ROW, and it is asked once, in one place.** A message he wants to review
 first is a draft of the mail card (a NEW one to a person: `draft` with `contact`, keyed by who it goes to); a send
 for later is a scheduled row (`send_draft` with `at`/`in_minutes`, shown on the card, `cancel_send` until it leaves).
 The send itself is its owner's (CRIT-T2b): his yes over one person and a text is asked in the conversation, never
 also on the card. A channel refines a send's class (`messaging.send_new@email`), so his rule for one channel governs
 that channel only, and his yes never clears his own «ask» rule for that class (`nucleo/consent.decide`). The
 confirmed act owes its declared end state (`send_draft.done_when`: a sent row for that recipient), so «confirmed» and
 «done» are judged apart. — since 2026-10-26 (rewritten 2026-11-21, INI-078 L1) · nodes 2.806, 2.807 ·
 `widgets/mensajeria/held.py`, `nucleo/consent.decide`.
- **CRIT-C10 · Every act that reaches the real world reads ONE door, and his rules override its defaults.** A widget's
 act through `frontend.action_verdict`; a cluster message, an errand's reply and a worker's click through
 `consent.decide_act(class, channel)` — `messaging.send_new@<channel>`, `web.commit`, `payment.authorize`, defaults
 in genesis (each as it was before). A spoken rule that names a channel by the connector catalog's own vocabulary
 moves that channel only («no me pidas confirmación para mandar correos» → `@email: allow`); one that names none
 moves `ask_at`. An act that leaves and runs FAST by its manifest still stops on his `ask`/`never`. An errand
 replies only inside its mandate (`may: message`, its channels) — outside it the reply is a held draft row, inside it
 his channel rule still stops it. A held cluster send is one pending row; voice, chat and the Clusters tab resolve it
 through the same reader. A page that cannot be read keeps asking; the agenda's invitation is decided once, at the
 door. — since 2026-10-26 · nodes 2.808, 2.806 · `nucleo/consent.py::decide_act`, `nucleo/errands/mandate.py`,
 `connectors/meshkore/send_gate.py`, `widgets/navegador/click_gate.py::consent_verdict`. A worker's
 `mesh serve` (the request to an agent that serves it) is a query to a provider, not a message: outbound scan, his
 `errand.mesh_serve` rule (never refuses, ask asks), then the taint on what leaves (asked after untrusted reads when
 the scan redacted something of his, unless a mandate names `mesh`); every outcome is a `consequence` event on door `mesh.serve` (V2-852 T14 · nodes 2.1400 ·
 `nucleo/workers/exit_gate.py::mesh`).
- **CRIT-C8 · A search is never gated as a charge.** A negated act («do not buy») and a first-person wish beside
 a lookup order («I want to buy X, give me the link») are subtracted before the money verbs are read — a
 negation only subtracts the act it governs, inside its own clause («don't forget to pay», «no compres el barato,
 compra este» still park); the pay click is where money stops. The core guard reads whole words only. — since
 2026-09-30 · nodes 2.181, 2.200, 3.29 ·
 `nucleo/danger.py`, `nucleo/protected_core.py`.
- **CRIT-C8b · A browser click that sends nothing never asks.** The click gate judges what the click DOES: a payment
 or password form, a checkout page, a submit that hands his identity to a site (and, while the worker is tainted, a
 submit that leaves) ask; a button's label counts only on a click that sends a form's data (in a form whose method
 is not `get`; unread counts as sending). Removing a filter chip, clearing filters, paging and
 navigating run, tainted worker or not. — since 2026-11-05 · nodes 2.1352 · `widgets/navegador/click_gate.py`.
- **CRIT-C11 · One vocabulary of events.** What arrives and what leaves is an event type `<family>.<act>` declared ONCE
 (`nucleo/events/vocabulary.py`), its channel and subject on the instance. The topics a rule subscribes to, the scopes a
 rule may name, the grants a mandate holds, the level a leaving class asks at when the caller measured none and the
 effect a manifest action carries by its class are READ off that table — a class the code names and the table does
 not declare is nobody's event (the ratchet fails by name). Every `decide_act` is one `consent` event on the timeline
 with the type, the verdict, the level and where it came from. `consequence.DOORS` stays the turn's own table of
 dry-run funnels. — since 2026-11-06 · nodes 2.1610, 2.1611 · `nucleo/events/vocabulary.py`, `nucleo/consent.py`,
 `rules/vocabulary.py`, `rules/subscriptions.py`, `widgets/effects.py`.
- **CRIT-C12 · His exception for ONE person is a rule, not a note.** The cascade has a `subject:<contact id>` rung
 between the act and the item (`subject:<id>` any act with her; `subject:<id>/<domain>/<channel|*>/<act>` one act): the
 shaper is handed the people his sentence names with their ids and writes «X without asking, except to Y» as two rows;
 a door passes the subject only when the recipient means exactly ONE person (the directory's one ranking, or the
 conversation's contact), and the `consent` event names it. A per-person note the model did not shape is said as
 kept-not-applied with how to say it so it applies, never «I can't». — since 2026-11-06 · nodes 2.1612 ·
 `rules/scope.py`, `rules/vocabulary.py`, `rules/shape.py`, `nucleo/acts/act_policy.py`, `nucleo/errands/mandate.py`.
- **CRIT-C13 · An irreversible act of a card waits for his yes ON ITS ROW.** A `confirm:true` data-op (or the one
 rule's ASK_CONSENT) is a durable question of the request's inline row through the one asker
 (`consent_ask.ask_consent`): its two answers are DECLARED candidates in the language (`answer_yes`/`answer_no`), the
 model picks one with `task_say(is: yes|no)` through the one delivery door (`switchboard/act.deliver` →
 `worker_api.answer_soon`), the card's button answers the same `ask_id`, and the yes re-runs the retained act through
 its own door once (`inline_ask.take`); his no cancels the row. A card's delete/restore, a cluster connect or held
 send and a parked errand's start ask the same way (`consent_ask.ACTS`, `dispatch.confirm.make_durable`); his words
 are read only when an answer arrives with no pick (`worker_api_answer.says_yes`), and `widgets/confirm.py` holds a
 question only when no row could be opened (said by its own event). Every question card carries a ✕: closing it is his
 no — the row ends through his cancel door, once, never re-asked (V2-886 D7, `POST
 /api/tasks/<row>/asks/<ask_id>/dismiss`); a card sits under the turn that opened its row (the row's trace), never
 pinned at the foot of the chat (D6, node 4.359). — since 2026-11-06 (rewritten 2026-11-21, INI-078 L1) · nodes
 2.1613, 2.1616, 2.1624, 2.1692 · `nucleo/request/consent_ask.py`, `nucleo/request/inline_ask.py`,
 `widgets/confirm_answer.py`.
- **CRIT-C14 · Consent is decided at the EXIT, never at an errand's birth from its words.** An errand's class is the
 model's own argument (`start_task(class)`, carried at full confidence by `acts_tasks.errand_context`; read by
 `errand.class_of` at the licence, else «none» — the money vocabulary no longer fills it), said once as a `task`
 event; only a CRITICAL class (money leaving, one of his accounts) read SURE (≥ `jev.VETO`) asks before it starts
 (`errand.asks_first`), on its row through the asker, and its question is chosen by the class — a critical class read
 unsure starts, and its exit asks (V2-873, node 2.884; every critical event keeps a door that emits it, node 2.1663).
 A send is asked ONCE, at its exit (`messaging.send_new@<channel>`, with his channel and person rules) — never also at
 birth. — since 2026-11-06 (rewritten 2026-11-21, INI-078 L1) · nodes 2.1614 · `nucleo/acts/errand.py`,
 `nucleo/danger.py`, `nucleo/dispatch/session.py`.
- **CRIT-C21 · Leaving a messaging group is ONE declared act: found first, asked once, verified by its receipt.**
 `mensajeria:leave_group` (event type `messaging.leave_group`, sensitive; genesis `ask`) leaves each named group and
 removes its chat from his list — it cannot be undone. Every name is resolved against HIS group chats before
 anything is asked or queued (an exact name before a partial one; one name missing or ambiguous refuses the whole
 call with the candidates, `would_refuse` first); the exit door asks ONE question for all of them, naming them as
 FOUND (the card fills the blank: a data module's `confirm_values(action, payload)`, read by `exit_risk`); his yes
 runs the retained act at once; one order per platform goes to its connector (`msg.group_leave`), which answers the
 chats that are gone (`connector.chats_gone`) and ONE failure naming the ones that stayed; the order's outbox row
 says sent only when every chat is gone, and only then is it told as done. `dismiss` only hides a row here and says
 so. An end state reads a call that names several plain values (`spec._fill`: told as one, as the row keeps them).
 — since 2026-11-18 (V2-935) · nodes 2.1814, 2.1815, 4.590 · `widgets/mensajeria/actions/leave.py`,
 `connectors/messaging/group_leave.py`, `connectors/whatsapp/service/leave.py`, `nucleo/workers/exit_risk.py`.
- **CRIT-C16 · A task is opened only by the model's call, never by his words.** A task starts when the conversation
 manager's model calls `start_task` (or `plan_task`), one call per thing he asks; no door reads his sentence to open
 one, and nothing folds a new task into an open one. — since 2026-11-21 (rewritten, INI-078 L1) · nodes 13.161 ·
 `nucleo/conversation_host/acts_tasks.py`.
- **CRIT-C19 · His «no» to the act a task asked about ends that act's goal; it is never retried.** The answer is
 recorded on the row (`worker_api_answer._declined`, artefact `declined`) and the circuit reads it as the task's
 decision: the ending is `skipped`, and the harness never relaunches a worker to do what he refused (an unmet goal
 «the message appears as sent» after his no is not a shortfall). — since 2026-11-06 · nodes 2.1625 ·
 `nucleo/cli/worker_api_answer.py`, `nucleo/circuit/__init__.py`.
- **CRIT-C20 · The answer to a waiting question is yes, no or NEITHER.** His line while a parked errand or a held click
 waits is read by its two declared answers: the answer words decide only a reply made of them, and a yes/no word
 inside a longer sentence is neither (a question that waits on a ROW is the switchboard's, CRIT-T3). A
 yes/no word that answered nothing is said: «X is still waiting for your yes or no» (`errand_still_waiting`) — never
 a lost turn. — since 2026-11-10 (V2-873) · nodes 2.1659 · `widgets/confirm.py`.
- **CRIT-C15 · Every act of a worker that leaves crosses ONE declared exit door.** The bridge acts that leave are
 declared once (`exit_gate.EXITS`: the door each crosses and how its event type is read — the card's own class refined
 by its hook, or a fixed type); the bridge and the retained act his yes runs ask `exit_gate.leave(rec, action, payload)`
 and nothing by action name; an undeclared act crosses no door. Every exit records one `task` event with the event
 type, the person it reaches (the subject), the channel and its verdict. Inside the door of a card's send there is
 one rule (CRIT-T2b): the card's own refusal, then one confirmation. — since 2026-11-06 · nodes 2.1615 ·
 `nucleo/workers/exit_gate.py`, `nucleo/cli/worker_api.py`, `nucleo/cli/worker_api_answer.py`.

## 3 · The canvas — whose card, what runs

- **CRIT-K46 · An app's provider is a preference, its end state is real, and it iterates before «unmet».** An
 unavailable provider falls to the next one and anything needing his choice is an offer; `done_when` is THIS call's
 outcome on our side (never stale, never another actor's), every field it names is a value of the view; an unmet end
 state runs the app's declared `on_unmet` steps (bounded) before it is said; a named source is honoured for that call.
 Reviewed across every app at once. The end state is read from what the card REPORTS — what the page's player says
 it plays (`musica.here`, YouTube's `report.playing_id` through the state door), the period the chart shows, what the screen's canvas holds after a
 close, minimise or full screen — never from the order sent; a refused song is skipped by our own pick and never
 said to sound; an action that names no value it needs is refused with its field (V2-873). — since 2026-11-08 ·
 nodes 4.395, 4.396, 4.408, 5.74, 5.75, 4.440, 4.441, 4.411, 4.218, 2.1661 ·
 `nucleo/circuit/__init__.py::_next_step`, `widgets/*/manifest.json`, `zaelar-widgets-workflow.md` §2b.

- **CRIT-K1 · A verb table is not a router.** A grammar may PROPOSE (free, instant); the choice is made among DECLARED
 options — the conversation model calls one of the acts the host declares (`nucleo/conversation_host/declared.json`)
 on a widget resolved against the catalogue by id, name or declared alias (`widgets.runtime`), and a door that needs a
 decision asks the decision model among its declared choices (`nucleo/jev/`); no word table read after the model eats
 or replaces its call. — since 2026-09-22 (rewritten 2026-11-21, INI-078 L1) · nodes 2.72 ·
 `nucleo/conversation_host/acts.py`, `nucleo/jev/`.
- **CRIT-K3 · The verdict's action lands on the LIVE card**, never a bare phantom; with several cards of one type
 «close» goes to the one his last turn touched; «it» / «that» is the card his last turn acted on. — since
 2026-09-29 · nodes 2.85 · `nucleo/canvas_focus.py`.
- **CRIT-K4 · An order NAMES its target.** A show resolves the widget by the name he used (`runtime.identify_named`,
 `named_only` in `conversation_host/acts._resolve`), never by the card that happens to be open; a name nothing matches
 is a `failed` result naming the widgets there are, and two candidates are a question — never a contextual guess. —
 since 2026-09-29 (rewritten 2026-11-21, INI-078 L1) · nodes 4.160 · `nucleo/conversation_host/acts.py`.
- **CRIT-K5 · A canvas mutation needs the operator's words.** The room is not the operator: ambient speech
 reaches neither the chat nor the canvas (a turn not said to us is the ear's discard, its line deleted); no system
 note rides a turn (the notes mailbox went in V2-851 F5), so none can name a card to close or veto a show. — since
 2026-09-09 · nodes 13.91.
- **CRIT-K6 · The canvas that counts is the tab holding the voice session**; a fullscreen card covers everything
 and always has an exit; leaving fullscreen is its own, idempotent order. — since 2026-09-24 · nodes 2.91, 2.78.
- **CRIT-K7 · A descriptor is written under the cut and measured against its NEIGHBOURS** (`MAX_DESC_CHARS`); a
 homograph is closed by naming it; a number he said is a READING, not an invention, and a question asked twice
 keeps its answer. — since 2026-09-23 · nodes 2.74, 4.204.
- **CRIT-K8 · Closing a card is a TOOL, like opening one.** The manager closes a card with `close_widget`, naming it
 by its card; several cards named are several closes in one run; a close with nothing to name asks which, and
 never closes every card. — since 2026-11-21 (rewritten, INI-078 L1) · nodes 13.127 ·
 `nucleo/conversation_host/acts_widget.py`.
- **CRIT-K8b · A close that names no card closes the OTHERS, never nothing, and never in silence.** The card in use
 (the newest card a data-op ran on, still open, or one the turn kept) is spared unless his words name it; when
 sparing would leave nothing to close, everything closes; every bulk close leaves one short line in his language —
 what it closed, what is still on screen, cards by name — spoken by the doors with no model reply (hard interrupt,
 action map). — since 2026-10-26 · nodes 3.133, 3.135.
- **CRIT-K8d · «Close all» closes ALL, and a close with no model stays in the conversation.** A close whose words
 quantify the canvas (the grammar's own reading, `interrupt_grammar.close_scope`) spares nothing — the K8b spare is
 only for a close with no total; and a turn answered without the model writes his line and its receipt into the
 dialog window like a model turn (`dialog.record_turn_without_model`), so a repair («I said all») finds what it
 repairs. — since 2026-10-28 · nodes 3.148.
- **CRIT-K10b · A card is named by what it shows, never by its id.** Every «which card?» names an instance by its
 content (title, what it was looking for, its first row), else by its kind, and two that still collide by their
 place among the open cards (`instances_nth`); the last door before the question (`widgets/instances._no_ids`)
 replaces any label carrying an open card's id, whatever the widget's `card_face` returned. — since 2026-10-26 ·
 nodes 3.137 · `widgets/instances.py`, `widgets/results/sheet_names.py`.
- **CRIT-K11 · A close order answered with a player's pause is the card's CLOSE** («cierra la música» →
 `musica:pause` closes the card, both channels through `card_close.data_close`, and the receipt says closed).
 — since 2026-10-11 · nodes 2.430.
- **CRIT-K12 · A redo is not a drag.** A re-emitted op is context-bleed only when the previous one LANDED and the
 turn did not ask for it again: the card reporting afterwards that it did not happen (`late_report.falsified_since`),
 his turn naming that card as its target (never one named to be left alone), or the redo verdict on that card make
 it a redo that runs — with or without a verdict, no phrase table. — since
 2026-10-24 · nodes 2.793.
- **CRIT-K13 · What an order changes ends where he can see or hear it, or the card says why not.** An answer that
 fills a card's list brings that face forward; a video ordered to be watched wants sound unless he muted it, and
 what the player really lets be heard is the player's own report (`audio_blocked`: the hint stays, the brain reads
 it, an agent order is told); what it shows carries the fact he needs to check it (a video's publication date).
 The state the brain reads is the player's report for the loaded video, never the order, in one line with that
 video; a late tell waits `late_report.SETTLE_S` and the card's contrary report withdraws it (V2-886 fila 6).
 — since 2026-10-24 · nodes 2.791, 2.792, 2.1696 · `widgets/youtube/sound.py`, `widgets/youtube/library._fill_list`.
- **CRIT-K15 · A skip says what sounds now.** A list is handed to a provider whose skip lives in its context
 (`plays_lists_as_context`, Spotify) as ONE play, and a skip reports the song the player shows afterwards or says that
 nothing changed. — since 2026-10-24 (rewritten 2026-11-21, INI-078 L1) · nodes 5.63 · `connectors/music.play_list`.
- **CRIT-K16 · A player's capability is a declared op of its card, and a provider's limit is said, not faked.** List management, the queue, play modes, mute and the catalogue are ops of the music card reached through the generic widget door; what the card fires about itself (`played`, `ended`, `enrich_art`) is `"internal": true` and never offered to the model. The catalogue asks the connected account first and the free metadata next (played by its words), never coming back emptier than a play; a queue the provider cannot edit is shown read-only and an edit answers `unsupported`. The card's effects say the REAL state: the meter animates only while the player reports sounding, a paused current song wears a still marker. — since 2026-10-24 · nodes 4.264, 4.265, 5.64 · `widgets/musica/player.py`, `widgets/musica/browse.py`, `connectors/music/catalog.py`.
- **CRIT-K17 · One agent, many screens: what a request does to a screen happens on the screen that asked.** Every event carries `origin_dev` (the voice holder for a spoken turn, the typing screen for a typed one, the commissioning screen for an errand's cards, by trace within a turn — `voice/screens.py`); `event-scope.js` is the one table of what is origin-scoped (a card opening, full screen, the panel) and everything else reaches every screen; another screen gets a chip, never the card. Voice in and out live on one screen and the loser stands down on the hand-over event; any screen types (`POST /api/chat`); every widget declares `"screens"` — `shared` (a reflection, open anywhere) or `single` (takes the device's sound or picture: lives on one screen, and asking for it from another screen moves it), with `runtime.output` ⇒ `single` (`widgets/screen_policy.py`); the brain sees the canvas of the current turn's screen. — since 2026-10-25 · nodes 4.266, 4.267, 4.268, 4.269, 4.270 · a widget is done only after the two-screen test (`.meshkore/docs/ops/zaelar-two-screen-test.md`).
- **CRIT-K49 · A refused pick is replaced a bounded number of times, then said with its fallback.** Our own pick the page player refuses (IFrame API 101/150/100/2/5) is replaced by the next candidate of the same order at most `availability.WALK_MAX` refusals per order — one walk per order, shared by the music and video cards (`walk_step`/`walk_put`/`walk_spent`); past it the card keeps `player_error`, carries where it can still be heard (the watch URL, `yt.refused_at`) as data in the brain's digest, and returns a `tell` naming what the ORDER put on, in his language, said only when an agent order is contradicted (`widgets/late_report.py`). — since 2026-11-13 · nodes 4.532 · `widgets/youtube/availability.py`, `widgets/musica/sound.py`.
- **CRIT-K17b · Music plays where he asked, and «playing» is read back.** Since 2026-11-01 (operator's rule, V2-833 F2) a start ALWAYS plays in the page of the screen that asked — phone, computer or no known screen — whatever Spotify session is open elsewhere; a connected catalogue that plays only on its own devices (Spotify) IDENTIFIES the song (a search, no device) and the page player plays what it identified; where it went (`placed`) and who named it (`identified_by`) ride the event. With no page player installed, the active provider plays and a start on a device elsewhere is true only once the player reports it sounding (`confirm`). The same words again while it sounds are not re-sent. The page player (the hidden embed and the `<audio>`) REPORTS through the card's state door whether it plays, which song, its sound and volume (V2-884 step 2, the protocol every card's player shares); sound wanted and the player silent or not playing is the fact `audio_blocked` — never stored: the card shows the tap, the app's state line says it, an agent start is told against; «what sounds here» (`here`, the end state of every start) is what that report says. — since 2026-10-26 · nodes 5.65, 4.297, 4.440 · `connectors/music/__init__.py`, `connectors/music/placement.py`, `connectors/spotify/provider.py`, `widgets/musica/sound.py`.
- **CRIT-K16b · The brain sees what a card shows, and controls reach the player that sounds.** No rows is not «empty»: a card whose published interior (`prompt_digest`) says something is not reported EMPTY (`refs.items_line`). The music card publishes its live state — song, which player and where; on a provider's device, playing or paused and the volume as the provider says; the page player's own state is its report (the app's state line), never painted from the order. Pause, volume, next, the queue and the reading go to the provider the last start was recorded on (`music.sounding_provider`), the first connected one only when nothing was started. — since 2026-10-26 · nodes 4.298 · `widgets/refs.py`, `widgets/musica/data.py`, `connectors/music/__init__.py`.
- **CRIT-K18 · Each screen shows its own state, the same on the desktop eye, the desktop bar and the phone.** One derived state per screen (`store.screenState`): stopped → the grey ⏻; holder → the grey orb; speaking → the ORANGE orb, only on the screen that holds the voice (`services/orb-colour.js`, replacing «orange = listening»); voice elsewhere → the grey orb with the slashed mic, never orange, and a tap on it brings the voice here — it never stops the agent. The ⏻ means power only. Icons are lilac when on/open and grey when off/closed; the mic and the speaker only when really live on this screen. Switching the agent on goes through ONE door for both shells, the server first (`services/power.js`). — since 2026-10-25 · nodes 4.147, 4.266.
- **CRIT-K19 · ⚙ Settings is one left menu, everything reads from the left, and «Back» goes where he came from.** Settings (its sections listed under it), Appearance, Connectors and Widgets are the groups of ONE side menu, no top tabs; on a phone the menu is the first page and a section opens with «← Menu». Content is never centred: a row is a label column then a control column, both from the left, and a form's actions sit on the left, primary first. A connector page is built from the same pieces on every step and ends on «Back to <whoever opened it>» · «Close»; a card that opens a connector names itself (`openConnector` → `from`), and its «Back» closes the panel instead of landing on the list. A message about how the deployment is configured never reaches the end user. — since 2026-10-25 · nodes 2.219, 2.803 · `frontend/app/components/ConfigPanel.js`, `frontend/app/components/ConnectorWizard.js`.
- **CRIT-K20 · A result card is laid out by the space it really has; length is never the data's fault.** The results sheet stores a field whole up to a storage cap and never budgets characters for the layout; every card is a container, its text clamped to its lines for its real width with the whole text one click away («Ver todo») and in the hover title; the grid reflows by width; every card of a photo layout keeps a fixed-aspect plate (a monogram for a missing or dead photo); the list shows the declared `meta` chips (else the first facts) and the record keeps everything else; the presentation audit reports data quality (shape, links, `columns`), never a length. Tokens come from the design system, the card one rung above its sheet. — since 2026-10-26 · nodes 4.274, 4.10, 2.685 · `widgets/results/widget.js`, `widgets/presentation.py`.
- **CRIT-K40 · A result is a NAMED row, and the list's shape follows MOST of its rows.** The results sheet's door strips markup from every text slot and keeps only rows with a name — a title that is its own price, or leads with an amount (a number next to a currency sign), is a price option folded into the named row before it as a fact, else dropped; bare digits stay a name (structural, no vocabulary). A photo layout needs MOST rows to carry a photo; otherwise the list is rows and no card paints a monogram. Inside the layout a card may be drawn by its item template — `offer` (price-led, a logo at most, ≤2 chips, never a plate), `video` (16:9 thumbnail beside its text), `link` (site icon + host over a snippet) — declared in one word (`kind` on the item or the list) or, in a rows list, inferred from the fields. A push that names its errand but no sheet owns the shared sheet: another errand's rows are replaced, not appended to. — since 2026-10-28 · nodes 4.322, 4.323, 4.324 · `widgets/results/clean.py`, `widgets/results/intake.py`, `widgets/results/js/parts.js`, `widgets/results/js/card.js`.
- **CRIT-K21 · A card says where he is, and the messaging card's mail section is a mail client.** A house left of the card's title is lit with the title on its home and dims inside a section, whose name follows as the current crumb; every screen below has a way back one level. The messaging home holds only what is addressed to him — a held draft or a scheduled send lives in its own channel (email's in Drafts). The mail section is ONE left rail and a list — no folder row under the header, which names only where he is: Compose, the Inbox split into the categories the PROVIDER returns (only when the server advertises them, `X-GM-EXT-1`; never invented), each with the provider's own unread figure (the Inbox badge is its first category's, as in Gmail), then every folder the server declares (RFC 6154 roles, never read from a folder's name); the rail folds to icons, then to a drawer, by the card's own width. Pages come a page at a time, read-only; a draft is the WHOLE card and its only content — recipient, subject, text and Send · Save · Discard, found by state for «abre el borrador» — STATE that survives the card mounting after the order and an order that only names the section; on any list (and in a channel's strip) a held draft is one line that opens it, never its body or a Send button; «back» returns to the list it was opened from; each button is ONE order whose outcome the screen reads back from the state. — since 2026-10-26 · nodes 4.275, 4.278, 4.279 · `widgets/mensajeria/mailbox.py`, `widgets/mensajeria/mail_actions.py`, `connectors/email/folders.py`, `connectors/email/categories.py`.
- **CRIT-K22 · The mail card mirrors the server's membership, not only its flags.** Of the messages on screen (the pending Inbox items, the first page of a folder he entered in the last 15 min), each poll tick asks the folder which it still holds: what it no longer holds (archived, deleted or moved in his own client) leaves the card, and a folder whose size changed has its first page read again, so mail moved back reappears. One login per folder per tick, no connection held open (no IMAP IDLE); an unanswered check removes nothing. — since 2026-10-26 · nodes 4.277 · `connectors/email/membership.py`, `connectors/email/service/`, `widgets/mensajeria/mailbox.py`.
- **CRIT-K23 · His mail categories are criteria he reorganises by voice, rows of the rules table — the default is the provider's own sorting.** With no row the card lists the provider's categories as they are. «Los de Amazon que vayan a Principal» / «no me enseñes Social» is the turn model's verdict over what is declared (the categories the provider returned, a sender he named) → `mail_sort` → a `pref` row at `widget:mensajeria` (`mail_route:<sender>` = category, `mail_hide:<category>`) in his words; code composes routes into the provider's own query, so the list and its count follow, and hides an entry from the rail. Listed and removable by id in the card, by voice and in ⚙ Settings → Rules; a category the provider never returned and a sender that is not an address, a domain or a word are refused; nothing moves in his real mailbox. — since 2026-10-26 · nodes 4.280 · `widgets/mensajeria/mail_rules.py`, `widgets/mensajeria/mailbox.py`, `connectors/email/categories.py`.
- **CRIT-K35 · A repaint never moves him.** Every repaint of a card goes through one door that keeps where he is: a scroller that declares itself (`data-scroll-key`) keeps its bottom if he was on it, else the same row at the same offset; a chat opens on its latest message (`data-open="bottom"`); the focused field (`data-keep`) gets its focus and caret back, its value being its own buffer's job. — since 2026-10-27 · nodes 4.305 · `widgets/mensajeria/widget.js` (`_captureWhere`/`_restoreWhere`).
- **CRIT-K36 · A send from his own hand is his order, and it is answered.** The card's Send is ONE order with the box's text naming its conversation (never «the most recent draft»); what cannot leave is refused before it is queued; every connector's reply drain echoes the order's `ref` on success and publishes `msg.send_failed` with the reason on failure, the owner settles the card's outbox row, and the box keeps his text until the row says it left — refused, failed or unconfirmed, the text stays and the reason is shown. — since 2026-10-27 · nodes 4.304 · `widgets/mensajeria/card_send.py`, `widgets/mensajeria/sent.py`.
- **CRIT-K37 · A conversation is named by his contacts first, through one resolver.** `directory.namer`: the contact holding the conversation, then the contact whose phone (a phone JID only) or address its id carries — unique, or nobody — then the platform's own display name, then the bare id; applied once to the whole messaging view and to the voice lookup. His own downloaded media plays in the thread like what he receives (`store.with_media`, both doors). — since 2026-10-27 · nodes 4.306, 4.307 · `widgets/directory.py`, `widgets/mensajeria/names.py`, `connectors/messaging/store/`.
- **CRIT-K38 · A header that stays put is not in the scroller.** A card's own fixed band (title, sub-header, tab bar) is a `flex:none` child of a root that fills the card, and ONE region below it scrolls, starting at the band's bottom edge — never `position:sticky` against the card's padded scroller, whose inset is a window the content scrolls through. That region declares itself (`data-hb-scroller`) and both hosts' `ctx.top`/`ctx.scroll` move it (else the card's own scroller); a data repaint keeps its offset. — since 2026-10-27 · nodes 4.309 · `widgets/results/widget.js`, `frontend/app/widgets/desktop.js` (`_scrollerOf`), `frontend/mobile/app/shell/Deck.js` (`scrollerOf`).
- **CRIT-K39 · An app's page says only what its manifest declares, on the desk and on the phone alike.** The launcher lists the catalogue the Apps tab reads (System · Custom) and shows the selected app's page, built ONCE (`apps-catalog.js`) for both shells. Desk: the rail's corner icon opens a window; one click shows the page, a double click or «Open» opens the app and closes the window. Phone: an «Apps» entry in the ☰ menu; a tap shows the page (no double click on touch), «Open» opens the app on the deck and closes the menu; every control ≥ 44px. Opening is `hb:open-card`, which both hosts (desktop.js, Deck.js) listen on. The page is `/widgets/<id>/about`: owner, created, licence, what it does (`widgets.<id>.about` in his language, else the manifest `description`) and the live connectors serving its declared `connector_families` (read with `serves`); a field the manifest does not declare is absent, never a placeholder. — since 2026-10-27 · nodes 4.315, 4.316, 4.317 · `widgets/about.py`, `frontend/app/components/apps-catalog.js`, `AppsWindow.js`, `frontend/mobile/app/shell/AppsPane.js`.
- **CRIT-K24 · A message to someone has ONE body: its held row.** An action that writes free text on a card declares the field (`text_field`); a card that holds outbound messages declares `claims_text` and answers `claim_text(text, title)`. At the one door (the turn's data door and `server_api._dispatch`) a text that is a version of a held draft — most of its content, or a good part of it while naming the draft's own recipient address; overlap measured, no word read for its meaning — is written to that row (`save_draft`), the draft card comes up through the canvas door, and the redirect is on the timeline. A document that only mentions the address stays a document. — since 2026-10-26 · nodes 4.281 · `widgets/text_home.py`, `widgets/mensajeria/held.py`.
- **CRIT-K25 · A held draft is part of the agent's state while it exists, whichever cards are open.** It reaches the prompt from ONE source, its pending-work row (`pending_rows` → `nucleo/pending_work.py`): recipient, subject, a bounded excerpt and the actions that act on it (`open_draft` / `draft` / `send_draft` / `discard_draft`, only those the card declares) with the payload that names it. The card's digest does not repeat it. — since 2026-10-26 · nodes 4.282 · `nucleo/pending_work.py`, `widgets/mensajeria/data.py`.
- **CRIT-K26 · A worker never runs the operator's own controls of a card.** An action a widget declares
 `"worker": false` (its view navigation and settings) is DENIED to a Brain Worker at its one door
 (`worker_policy.operator_only`); the same widget's other declared acts still pass. — since 2026-11-21 (kept from
 2026-10-26, INI-078 L1) · nodes 2.5 · `nucleo/cli/worker_policy.py`.
- **CRIT-K27 · What was sent is read from the record of what left.** A widget's `recent_facts` lines reach every turn through `nucleo/pending_work.fact_lines`; the mail card's are its sends of the last half hour as the connector sent them (head and tail of the body, so the signature is there) and what is still leaving, marked as not left yet. The timeline records the body a send of this card left with (`widget/sent` on `mensajeria`, from the connector's echo), never what he typed in his own app. — since 2026-10-26 · nodes 4.283 · `widgets/mensajeria/inbox_read.py`, `widgets/mensajeria/sent.py`, `widgets/mensajeria/owner/`.
- **CRIT-K48 · A mail is named once: the card's veto and its action resolve it alike, and «held» means holding THAT message.** An `open` by `n` or `name` resolves through ONE resolver (`actions/open.resolve_ref`: the list on screen, the conversations held, then what the card last found, by a shared word) that both the backed route's read-only veto (`answers._open`) and the action ask — a veto never refuses what the action would open. The card holds a mail only when a pending row or a thread message carries its id; an empty thread under the same address does not, so the found mail is asked back (`found_mail._held_mail`), and opening it while it is on its way keeps the conversation open (`opening`) instead of auto-closing on nothing. — since 2026-11-13 · nodes 4.531 · `widgets/mensajeria/actions/open.py`, `widgets/mensajeria/answers.py`, `widgets/mensajeria/found_mail.py`.
- **CRIT-K28 · Reading a card answers from what its screen holds.** With a draft or one mail open on the mail card, its `read_query` returns that object (recipient, subject, body — a stranger's words fenced) and does not search the inbox; with a list on screen the inbox is searched as before. — since 2026-10-26 · nodes 4.284 · `widgets/mensajeria/inbox_read.py`.
- **CRIT-K30 · Only the engine changes the canvas, and every change says who made it.** The browser never opens, closes or moves a card from words (interim, spoken or typed); a card opens from an engine `widget show` (verdict, action map, tool). Each host names a cause for every show/close at its call site (`by`), the canvas report carries it, and only a gesture of his hands keeps `user` provenance — client code is `client:<cause>` (unnamed: `client`) on the timeline and to the arbiter, and no screen obeys either back. The observability stamp is CRIT-R12. — since 2026-10-26 · nodes 4.115, 2.813 · `frontend/app/services/sse.js`, `voice/canvas_src.py`, `server/canvas_api.py`, `version.py`.
- **CRIT-K31 · A phone shows every card whole: the shell's touch floor, its two exceptions, and the keyboard.** On the phone every control in a card is at least 44px and a text field 16px (below that iOS zooms); a row that directly holds controls wraps rather than push the card sideways — EXCEPT a row that manages its own width (a tab strip `role="tablist"` that scrolls sideways, a thumbnail rail or a title that ellipsizes beside its close, `data-strip`) and a box that directly holds a text field, which is one control: it never wraps and grows with its field. While a field inside a card has focus and the visual viewport is shorter than the screen, the deck covers only the visible part and the dock steps aside. Hover-only affordances do not hold space on a touch screen, and one tap opens what a double-click opens. Each app is checked in the REAL shell on iPhone 14 (WebKit) and Pixel 7 (Chromium) and its screenshots are looked at. — since 2026-10-26 · nodes 4.300, 4.301 · `frontend/mobile/app/styles.css`, `frontend/mobile/app/shell/keyboard.js`, `tests/browser/e2e/mobile/phone_pass.py`.
- **CRIT-K32 · The phone's deck has a HOME, a top bar and one-finger paging.** Page zero is the home, and it draws NOTHING — no greeting, today, hint or tiles: the agent's face on the dark ground, or the dark ground alone with the face off (V2-928, operator 2026-11-19; node 4.595); the open apps are a swipe or a pip away. Every card wears ⌂ · ‹ · name with k/n · › · × as 44px targets; the pips above the dock count the home plus every card, the current one lit. One finger pages anywhere when the swipe is clearly sideways (48px, 2:1) and did not start on something that scrolls or drags sideways on its own (unless from the screen's edge); two or three fingers still page; a finger that commits to going down first is the widget's. The engine's `minimize` lands on the home; the Android back goes home before it leaves. The dock is 64px plus the safe area once, the orb rises above its edge, and a card ends exactly at the dock's top; with the keyboard up the surface holding the field (card or sheet) covers the visible part and the dock is gone. — since 2026-10-26 · nodes 4.19, 4.87, 4.300 · `frontend/mobile/app/shell/Deck.js`, `frontend/mobile/app/styles.css`, `frontend/mobile/app/shell/keyboard.js`.
- **CRIT-K50 · A card brought to the front is SEEN.** Both hosts knock on ONE door (`frontend/app/widgets/card-front.js`)
 for every show that is not a background or restore one, and for a full screen; whatever covers the screen gives way —
 on the phone every page over the deck closes (chat, menu, widgets, settings…), on the desktop a FLOATING chat wall
 covering ≥35 % of the window folds (a docked column never covers a card and stays). A worker's background show never
 takes the screen. — since 2026-11-16 · nodes 4.317, 4.246 ·
 `frontend/app/widgets/card-front.js`, `frontend/mobile/app/shell/pages.js`, `frontend/app/components/ChatWall.js`.
- **CRIT-K51 · A widget's name is the same name in the plural.** `widgets/runtime.identify` answers by exact name/alias
 first; only when that names nothing at all does a second pass fold grammatical number on both sides (EN/ES,
 `_sing`/`_canon`), still word-aligned — an exact name always wins. — since 2026-11-16 · nodes 4.551 ·
 `widgets/runtime.py`.
- **CRIT-K52 · The phone's ☰ is the person, its chat is the agent — as the desktop's top bar and wall.** ☰ = account
 (on the web) · Energy · Settings · Voice · Connectors · Feedback · the computer (read only) · desktop version ·
 delete (in the app); the chat page = Chat · Processes, the live count on 💬. The connectors list is ONE component
 both shells draw (`frontend/side/conectores/conectores.js`); its «Connect» on the phone opens the desktop's settings panel on
 that connector by link (`core/config-link.js`, `?config=…&back=m`, never a sticky shell choice). The dock is three a
 side: ≡ · 💬 · ▦ | orb | 🎤 · 🔊 · 🤖. — since 2026-11-16 · nodes 4.317,
 4.492 · `frontend/mobile/app/shell/MenuSheet.js`, `ChatSheet.js`, `ConnectorsSheet.js`, `DockBar.js`.
- **CRIT-K33 · An errand runs behind the screen.** A card action that a rung runs instead of a worker (the catalogue rung, the card that answers a search, the order carried out after a read) brings its card up only when its output exists only on screen (`present.mount`), when it is a lens (`data.read`) over a closed card, or when the turn's verdict says `canvas = show`; otherwise it runs and the visibility flag stays where he left it, and the refusal is emitted. A lens is never such an action for an errand whose deliverable has its own box (a document, pictures — the surface verdict when it is sure, else the `surface` the escalation itself declared) unless the verdict says `canvas = show`: the catalogue rung leaves it to the worker (`a_view_is_not_the_deliverable`; V2-851 F2: the promise-pass clause died with the promise repair), so talking about a card's content, or an errand that will read it, does not open it. A browser card — the base one included — with no live task behind it is never restored on reload, on either host. — since 2026-10-27 · nodes 4.87 · `::a_view_is_not_the_deliverable`, `frontend/mobile/app/shell/Deck.js`, `frontend/app/widgets/desktop.js`.
- **CRIT-K44 · A refused card action hands back its declared shape.** At the one door every caller shares (`widgets/server_api.brain_action`) a refusal carries the action's DECLARED `payload` and, when the card named no field, the first declared key the call left out as `field` — level 2 of the action, given only on a refusal, never added to a prompt up front; a worker's bridge forwards it beside `detail/options/field`. Manifest payloads are prose, so nothing is coerced. — since 2026-11-08 (V2-860 T2.7) · nodes 2.1633 · `widgets/action_shape.py`, `nucleo/cli/worker_api_exec.py`.
- **CRIT-K45 · An action alias belongs to ONE language.** The action map indexes only the install's language (`store.index` seeds and reads `active_lang` alone): an exact phrase of another language is not a miss of the map, it goes to the model like any novelty. An alias is a gene of its language's lineage (`i18n/genesis/<lang>/actionmap.json` is the factory layer, `source='learned'` rows the learned one, V2-859) and is never lent to another. — since 2026-09-03 (V2-539 §3.2), both ways pinned 2026-11-08 · nodes 2.41 · `nucleo/actionmap/store.py`.
- **CRIT-K47 · A periodic job is an object with one reader and one door by reference.** The scheduler's rows are read as a card's items (`scheduler.ref_index`: `{id, label, field, hint}`, a short label) by the turn's live record and by a worker (`act schedules`); `cron.cancel` takes an id or the label he says, resolved by the cards' resolver (`widgets.refs.match`, a stale id is no row), and its answer is the end state — the job is no longer listed — so a miss is said with the jobs that exist, never «cancelled». An order over a job is a turn act: the door declares it once (`scheduler.TURN_ACTS`) and the escalate and capability-gap questions read it. Jobs are created by asking, never by a hand-filled form (V2-883) — since 2026-11-11 · nodes 4.486, 4.193 · `nucleo/pulse/scheduler.py`.
- **CRIT-K53 · The agent has a face, behind every card, and the eye is hidden.** The desk draws the chosen face (Porcelain by default) above its backdrop and under every card, never catching a click; it moves its lips from the agent's own audio stream (observed, never played again), is never a statue (random idle actions, accents on its speech) and exists only while presence is on — off means no canvas, no loop, no audio graph. The orb lives in the bottom bar (the eye is hidden, not deleted) and the bar's swap, the top bar's ☺, Settings ▸ Presence and the voice (`controls` presence_on · presence_off · presence_settings) all go through ONE door, `presence/state.js`; the choice is kept per account in `/api/settings` `presence`, sanitised. On the phone the home draws nothing, so the face is all there is on it (it stops drawing under a card or a page), switched from the ☰ page, chosen on its own Presence page; «open the presence settings» opens the page of the shell that heard it (`state.openPresencePage`). — since 2026-11-17 · nodes 4.133, 4.566, 4.567, 4.569, 4.595 · `frontend/app/presence/`, `frontend/mobile/app/shell/PresenceSheet.js`, `config/settings.py`.
- **CRIT-K54 · «Look at me» runs on the device and only while asked.** The face turns its head and eyes toward the person the front camera sees (an on-device detector, vendored picojs: no model, no API, no frame, box or number ever leaves the page), or inside the iPhone app toward where the AirPods say the head turns (the app's `window.ZaelarNative.headMotion`, the contract in `presence/head-motion.js`); a lost person hands the head back to the idle life. Each source has ONE switch per device, OFF by default, and the camera runs only while its switch is on, the face is on, the tab is visible and the face is not covered — with a badge on screen that turns it off; a refusal turns the switch back off and says why. — since 2026-11-17 · nodes 4.570 · `frontend/app/presence/look*.js`, `LookAtMe.js`, `head-motion.js`.

## 4 · Errands and workers

- **CRIT-E1 · The TASK is the unit.** One durable row per errand; the worker reports or the pulse demands it; a
 task is born from four sources only, never from a loop having a tick. — since 2026-09-27 · nodes 3.82, 3.83,
 3.84, 2.18.
- **CRIT-E2 · There are no task lists**: several things asked at once are several independent tasks, and no door
 opens a list; an unfinished list found at boot is archived with its steps. — since 2026-11-21 · nodes 13.159,
 13.160.
- **CRIT-E3 · Resources pinned, reasoning open.** A worker's prompt carries formulas, resources and ways of
 solving, never a script; a fix shaped like the scenario is scaffolding (change one word of the request: does it
 stand?); in doubt it is a RESOURCES problem. — since 2026-08-20 · nodes 2.82, 4.32 ·
 `.meshkore/docs/architecture/zaelar-brain-worker-doctrine.md`.
- **CRIT-E4 · The rungs, cheapest first**: a declared widget action, then the network (an agent), then the
 browser, which is the LAST resort; a delivered hunt is not re-hunted; one widget per errand, the browser inside
 its process entry in the processes panel (V2-822). — since 2026-09-21 · nodes 2.43, 4.109.
- **CRIT-E5 · A report is a DOCUMENT**, and a fast listing pass serves the turn or hands off with its sheet inside
 its budget — a turn is never left mute. — since 2026-09-29 · nodes 4.143, 2.43.
- **CRIT-E6 · An errand with a third party offers the model NO tools**: it returns one JSON object and the engine
 executes what the mandate allows — the template of every rail on consequences; a reply the mandate does not cover
 is held for his word (CRIT-C10). — since 2026-09-13 · nodes 3.44, 2.808 · `nucleo/errands/party.py`,
 `nucleo/errands/mandate.py`.
- **CRIT-E7 · A worker's endpoint comes from its spec or the provider chain**, never from the inherited shell; a
 worker never depends on ONE provider. — since 2026-09-19 · nodes 2.82, 4.27.
- **CRIT-E8 · A parked errand is still the errand.** The dedup compares against the errands waiting on his
 yes/no as well as the live ones; a repeat folds into the parked one, the yes carries what he added, and the
 brain repeats the QUESTION, not the work. — since 2026-09-29 · nodes 2.182 ·
 `nucleo/dispatch/confirm.py`.
- **CRIT-E9 · Every request that acts is ONE row, and it ends in a verdict of the one vocabulary**
 (`nucleo/circuit/verdict.py`): its endings are `met` (its end state was attested), `unmet` (attested false after
 its grace, or no tries left — corrected out loud when he ordered it), `unverifiable` (nothing readable could say),
 `undeclared` (the action declares no end state) and `cannot` (nothing could act). Each value declares once whether
 it delivered, its rank, the row state it leaves and its event; a non-ending (`started`, `asked`, `skipped`) never
 settles a row, and every settle emits with the row's trace. A later op never improves a failed row; a worker's
 verdict comes from `circuit.close`; the prompt's recent state reads these rows, facts
 only. An inline row carries its spec, and a live one left by a previous boot is judged once from it (`met`) or
 closed as interrupted, silently. — since 2026-10-28 · nodes 2.194, 2.196, 2.198, 2.829, 3.105, 3.106, 3.113 ·
 `nucleo/circuit/verdict.py`, `nucleo/circuit/` (`settle`, `spec.py`, `ledger.py`), `nucleo/request/model.py`.
- **CRIT-E9b · A relaunch is judged by its commission's end state, and a state true at birth proves nothing.** Every
 relaunch that carries a `task_uid` (provider failover, context handoff, stall restart, rate retry, harness retry)
 passes `ledger.opened` → `spec.born`, which takes the end state and its `tries` from the task ROW — never from a
 field each caller must remember to copy. A NEW commission born on a sheet another commission filled (inherited by
 the continuity decision) whose end state reads that sheet and is already true (`met_at_birth`) is never attested as
 met — `unverifiable`, never «met and verified»; an idempotent order on its own card and `existing` stay met. — since 2026-11-02 · nodes 2.1001 ·
 `nucleo/circuit/continuation.py`, `nucleo/circuit/spec.py::born`, `nucleo/circuit/ledger.py::opened`.
- **CRIT-E9f · «Met» only when the row ends, and the end state is the request's.** A worker row's end state is
 attested ONCE, when its ending is judged (`circuit.close` → `settle`); the pulse never reads it mid-run, so a card
 that fills while the worker works is progress, never a verdict. An errand's end state comes from the request (the
 escalation's readable clauses) or from the worker at checkpoint 1 (`cli.report goal`, which becomes the row's spec
 with its `tries` kept); an unreadable clause is dropped, never rewritten into a card's state; a presence-only spec (a card
 not empty, visible, a bare collection: `spec.presence_only`) is never born as a row's end state, from the
 escalation, the inference or the worker; and the inference is not offered a card's emptiness. An open spec says «not met yet» when what is missing changes, not at every read.
 The ending is judged on what the errand DELIVERED (2026-11-17): a results surface that keeps no row, or a worker that
 reported it kept none, is `unmet` with the reason (`breadth.delivered_nothing`), however true the card's end state
 reads — a search attempt is not a delivery. It is read after the brief's own gap (the judge's next step is what a
 relaunch carries), only for a worker that said it delivered and a sheet somebody DECLARED (`surfaces.guessed`: a
 sheet derived from the kind is where an errand that acts lands too), and an emptiness the breadth judge called
 enough is the answer. —
 since 2026-11-05 · nodes 2.1351, 2.185, 2.1792 · `nucleo/circuit/__init__.py::tick`, `nucleo/circuit/spec.py`,
 `nucleo/circuit/breadth.py`.
- **CRIT-E9c · An act that LEAVES the machine is done only when the world's echo of it lands.** Every action that
 declares `external.send` declares either a `done_when` or a `done_when_unreadable` reason. A send's end state is a
 NEW row of what left (`expect: added` over `mensajeria.sent`, `queued` false): an older message with the same words
 and a row still in the queue are not it. The mouth reads a queued send as `started`, never `met`; an act that leaves
 with no end state to check settles `unverifiable` (never `undeclared`, which says «It is done.»); no echo past the
 grace is said as unconfirmed, never as failed. No connector tells the model a send happened — the echo settles the
 row and the mouth says the verdict — a group's creation included: its success is the echo, never a connector note (2.1794). A send the card REFUSES never left: its row ends `unmet`, the mouth says the
 card's sentence once and no model runs again to correct it (V2-851 F2, door test at `data_ops.dispatch_and_report`).
 **Every order a widget queues to a connector has a receipt, and the receipt is its end state** (V2-919 M3): the
 order opens its outbox row by `ref`, the connector's echo bound to that `ref` settles it `sent` and its failure
 (`msg.send_failed`) `failed` with the reason; «the connector reports it» is a readable receipt, never a
 `done_when_unreadable` reason — and checkpoint 1 is never relaxed for an act with no readable end state.
 — since 2026-11-04 (the receipt rule 2026-11-16, node 2.1784) · nodes 2.1008, 2.1784, 2.1794 · `nucleo/circuit/verify.py`, `nucleo/circuit/baseline.py`,
 `nucleo/circuit/__init__.py::tick`, `widgets/effects.py`.
- **CRIT-E9d · A send reaches the person his words name, or it asks.** When a call names nobody (`reply {n}`), the card
 answers who it reaches (`recipients_of`, read by `on_his_behalf.who_of`); a person his words do not name, and not
 the conversation open on a visible card, makes the send ask. «He named this recipient» has ONE reading
 (`acts.message.is_his`): the whole name in his words, or a word of his that the directory gives to that person
 alone. A feed (status, broadcast, channel) is never a conversation, at the ingest door and in an older store.
 — since 2026-11-04 · nodes 2.1009 · `widgets/mensajeria/consent_hooks.py`, `nucleo/on_his_behalf.py`,
 `nucleo/acts/message.py`, `connectors/messaging/ingest.py`.
- **CRIT-E9e · A recipient he never said goes back to his word, and the card asks.** A call whose `contact` his words
 never name (the model's «Odila Varn» for his «odile») carries his word instead (`acts.message.his_recipient`, on
 every data-op), so the card asks which and keeps the answer. Our own «which one?» — the reply names two or more of
 the people his word reaches — is a question, and is kept like the card's (`message.asked_which`, asked at the voice
 turn's end when nothing acted). The question he hears names the closest ones (`say_args`); a draft held for his review
 brings its card (`present.mount`); a send whose echo lands after the turn is said sent (`circuit.SENT`).
 — since 2026-11-04 · nodes 2.1010, 2.1008 · `nucleo/acts/message.py`,
 `nucleo/circuit/__init__.py`.
- **CRIT-E15 · A collection put together for him is an errand, and it ends in the card that holds it.** The
 escalate question reads «put together several items chosen to fit what he describes» as background work and ONE
 named item into a list as inline (measured live, 22/22); a card that holds such collections declares the op that
 appends several items, mapping each to a usable one through its connected providers in priority order, and the
 end state it leaves (the music card's `add_tracks`); an errand whose end state is rows a card of his declares
 opens no empty sheet (`surfaces.own_card`); the worker delivers into the card its end state names, in batches.
 — since 2026-10-24 · nodes 4.263 · `widgets/musica/curated.py`.
- **CRIT-E16 · One errand, one card, and a resumed errand keeps it.** Starting an errand opens no card: its card is its
 deliverable (the sheet; its browser is told in the processes panel, CRIT-E21), opened when the surface is sealed or when the first rows
 land; when he must act in the page (a wall, a login) the errand's sheet is raised — opened then if it had none — and the
 browser's monitor card is only for a tab no errand drives or an errand whose deliverable is not a sheet; a refresh never
 restores an errand's tab beside its card. A resumed or relayed errand reopens the sheet of its DURABLE row (`task_uid`),
 never one named after the new boot, with what it had delivered still in it. — since 2026-10-26 · nodes 4.273, 4.109 ·
 `nucleo/errand_card.py`, `nucleo/sheets.py::row_sheet`.
- **CRIT-E17 · What a source did to one errand is known to the next, with a date, and it expires.** A wall
 (403/CAPTCHA/login), an extract with no named row, a provider's quota and a network agent's timeout, empty answer
 or rows are recorded per SOURCE (host, agent id, `search:<provider>`) by the door that observed them; the newest fact
 wins, a later success resets the repeats, every failure expires on its own clock (a repeat lives up to ×3) and the
 quota at the provider's stated reset. The worker's step 0 carries ONE dated line (≤6 sources) and nothing when nothing
 is current; it orders mesh candidates (a hard failure asked last) and never drops one. — since 2026-10-26 · nodes
 2.804 · `nucleo/workers/source_outcomes.py`, `nucleo/cli/nav.py::_note_source`, `nucleo/mesh_agents.py::_note_answer`.
- **CRIT-E18 · A network agent gets its own time, inside one budget, and only if it is operational.** The skill call
 waits the agent's declared latency ×2, never below 60 s nor above 90 s; one `serve` is bounded by one budget and a
 second candidate gets only what is left; an agent the Oracle or its card states is not online/operational is not
 asked, a learned route to it included, and silence is not a statement; a timeout names the agent and the seconds; zero
 rows with the agent's hint is `ok` with `agent_hint`, never a failure. — since 2026-10-26 · nodes 2.805 ·
 `nucleo/mesh_agents.py::agent_timeout`, `::_ask_in_turn`, `::_is_live`, `::_mark_empty`.
- **CRIT-E19 · What is pending is STATE, and the model resumes it by id.** His tasks are the queue's, listed by `#n`
 in OPEN (`conversation_host/open_block.py`); the rows a widget holds for his word are declared by the widget itself
 (`pending_rows`, such as a draft held for his OK), read by ONE reader (`nucleo/pending_work.py`) and listed beside
 OPEN by id (`conversation_host/memory_read._open`); the model resumes them with `resume_task(ids)` — an id that is
 not a pending row fails and gives the rows back. Each row resumes from itself, through its own declared action and
 confirm gate (`request/resume`). A browser card's title is the errand's name (`navegador.tasks.set_title`). A task
 that WAITS (for his answer, a worker, an echo, a time, an event) is `state=waiting` on its row with what for, since
 when and its question; a restart keeps it waiting, and only its deadline or his answer moves it. — since 2026-10-26
 (rewritten 2026-11-21, INI-078 L1) · nodes 2.807, 2.1014.
- **CRIT-E20 · An errand's process moves with the worker, in ONE place.** Every recorded line, declared plan and step done tells the processes panel (`sheets.notify_process` → SSE `task process`), never a card; the record carries the worker's own plan and how much of it is done — its words, never steps the engine invents. — since 2026-10-27 (V2-820, moved to the panel by V2-822) · nodes 3.141 · `nucleo/sheets.py`, `nucleo/workers/reports.py`.
- **CRIT-E21 · An errand opens only its deliverable; its progress lives in the processes panel.** When the errand's surface names a card (`surfaces.deliverable_card`: the results sheet for `lista`/`item`, the document for `informe`, the viewer for `imagenes`), a show of any other card that comes from the errand — its worker's `show_widget`, or a search filling the errand's sheet — is refused at the canvas door (`circuit.not_the_deliverable`, read from the Request's surface, never the worker's words) and told as a `step` event instead; the worker is answered with the way through — read it without opening it, deliver into the deliverable; reads and writes are untouched. An errand told by voice or done silently (`voz`/`silenciosa`) opens NO card — only one its own end state (`done_when`) names; a question answered inline is no process at all (its request row is `kind=inline`, off the board, the count and pending work). The results sheet has no process tab: its Results tab carries the loader while the errand works and the errand's page shows on it only when the page needs HIM (a wall, a login, a question); the document card shows «being created» (or «not written» when the errand ended without it) and points to the panel. The running process's entry in the processes panel — the desktop's tab and the phone's menu — paints ONE record (`GET /api/tasks/<id>/process`, `nucleo/process_view.py`, derived from the live registry): collapsed, the plan around its step (✓ ▸ ·); expanded by him, the whole plan, the page and its capture, the harvest and the narration newest first; in both, its LAST line says what it waits on him for (signing in, blocked with no window, the page). «Proceso» said to the results sheet opens that panel through the sheet's own `tab` action. — since 2026-10-27 (every door: 2026-10-28, refactor2710-15) · nodes 3.143, 3.144, 4.310, 4.311, 4.312, 4.143, 2.893 · `nucleo/circuit/__init__.py::not_the_deliverable`, `nucleo/acts/canvas.py::apply`, `nucleo/process_view.py`, `frontend/app/components/ProcessEntry.js`, `widgets/results/widget.js`, `widgets/documento/widget.js`.
- **CRIT-E22 · Where a browser window for him can open is ONE answer, read by everything that offers one, and «nowhere» blocks the process.** `nucleo/browser_window.reach`: a GRAPHICAL SERVER this process can reach (an X/Wayland socket that answers — the env's, else a desktop session's, whose DISPLAY the headed launch is given; a window-server session on macOS; a non-service session on Windows) → the window opens here and the process watches it; none → only through a connected daemon that DECLARES `browser.auth` (registered by its transport, never guessed); neither → a sign-in he must do BLOCKS the process (`needs_input` + `blocked: no_window`, not failed, no question open). The voice catalogue offers `authenticate_web` only where `reach` is non-empty; a wall note names no login (a worker driving the tab owns the wall and the conversation is only informed); the browser agent promises no manual sign-in; a headed launch that fell back to headless is labelled headless and its sign-in is blocked like «nowhere»; he is told that without the daemon it cannot continue once per run, by voice and in the chat. A login wait ends with its task (any ended state clears `awaiting_login`), with its tab, or after `NAVEGADOR_LOGIN_TIMEOUT` (the task fails); every ending but a sign-in closes the window and resumes the other paused tasks, never the one that needed the login. — since 2026-11-02 (V2-835) · nodes 4.314, 4.350, 4.351, 4.352 · `nucleo/browser_window.py`, `widgets/navegador/tasks/announce.py`, `widgets/navegador/owner_login/`.
- **CRIT-E23 · The count of running processes is one number on every screen.** The desktop's bar and the phone's dock mount ONE component (`ProcessCount.js`) reading ONE number (`store.liveProcessCount`: his live commissions from the engine's board, moved by SSE `task` events and re-read from the board when a process starts or ends); hidden at zero; a tap opens the processes view. — since 2026-10-27 (V2-822) · nodes 4.313 · `frontend/app/components/ProcessCount.js`, `frontend/app/core/store.js`.
- **CRIT-E24 · One request, one errand, one sheet.** What he adds to an errand parked on his yes is kept with it (`absorb_refinement`, at the switchboard and at the dispatcher's dedup) and relaunches nothing; a listing that is an open flow's request said again lands in the sheet its errand id names (`sheets.sheet_of_flow`, `open_flows.join`); a new hunt is an errand born before it runs and its sheet is that errand's (`errand.born`, CRIT-E26), which the worker never opens fresh; a launch folded into a parked errand gives it its sheet or closes the duplicate. — since 2026-11-02 (V2-843) · nodes 2.1002 · `nucleo/acts/search_listing.py`, `nucleo/dispatch/listener.py::_absorb_into`.
- **CRIT-E25 · Who owns a surface is measured before it is enforced.** The turn's own fast pass signs a box no errand owns as the turn's (`turn:<trace>`, arbiter `turn-owned`), never as a task's; every show at the canvas door and every turn write into a sheet is recorded in shadow (`owner` events, read by `/api/observability/shadow?kind=owner`) with its would-be owner (`errand:<uid>` when an errand's row owns it) and the violations per class — non-owner show/write, duplicate open for one joined request, orphan, a discarded turn's launch, a fragment as an errand's goal, the flow door and the dispatcher disagreeing. Nothing is refused on it yet. — since 2026-11-02 (V2-844 F0) · nodes 2.1003 · `nucleo/acts/surface_owner.py`, `nucleo/acts/search_sheet.py`, `nucleo/acts/canvas_arbiter.py`.
- **CRIT-E26 · An errand is born in its turn, with his whole request.** Where a turn decides an errand — a new hunt before its fast pass runs, any escalation at the portal — its durable row is written (`starting`, off the board, by one ordered writer) under the uid that also names its sheet; nothing mints a box under a counter id of its own. Its request is the joined request of a turn that arrived CUT (a sentence his barge-in left unanswered, joined with what he said next — `turn_marks.cut`) when the door's words are only that turn's tail — the literal tail, or words with no content of their own (`errand.whole_request`); never a subset rule, never for one part of a turn that asked for several things. The dispatcher's row for it is that same row; a first-rung delivery closes it, a hand-on that did not become a worker of its own forgets it, the pulse forgets one nobody adopted. — since 2026-11-02 (V2-844 F1a) · nodes 2.1004 · `nucleo/acts/errand.py`, `nucleo/circuit/ledger.py`, `nucleo/acts/search_listing.py`, `nucleo/acts/search_sheet.py`, `nucleo/dispatch/listener.py`.
- **CRIT-E27 · Whose his words are is decided ONCE, by the conversation model; nothing routes a request a second
 time.** Nothing reads his words before the model (`conversation_host/routing.HostRoute` keeps the batch and takes
 none): with a process open, the model reads it in OPEN and his words reach it only by its `task_say(#n)` (CRIT-T3);
 what the model commissions with `start_task` is NEW — one call per thing he asks — and is born through the one errand
 gateway (`acts.errand.escalate_to_slowbrain`). Behind it the dispatcher's own dedup still asks whether an escalation
 is the errand already running (`nucleo/dispatch/dedup_flow.py`). An EVENT has its own door: an inbound message or
 mail, a due job, a worker that ended or asked is a request whose origin is its source (`nucleo/events`, one topic per
 source, one subscriber — the pulse's pump), and `nucleo/events/route.route` answers one of three, in order — a row
 waiting for it or the claimant that owns it resumes; a rule subscribed to it (CRIT-T11) hands it to its stream
 worker; else nothing, and the source's own handling stands; with the conversation manager on, the routed event enters
 it as an EVENT (`conversation_host/events_in`) and its door obeys the route there. — since 2026-11-02 (V2-844 F2),
 events 2026-11-05, one decision 2026-11-18 (V2-931) (rewritten 2026-11-21, INI-078 L1) · nodes 2.1172 ·
 `nucleo/conversation_host/routing.py`, `nucleo/events/pump.py`, `nucleo/acts/errand.py`.
- **CRIT-E41 · Same subject is not same errand: a card's act is the card's.** An order whose one act (`acts_asked` not sure of several — asked at the turn's first model call, so before it lands it reads «not sure», since 2026-11-12) is to be done, not told (`wants_words=act`), and that the catalogue gives to a card at VETO, is that card's (`stop.card_act_named`, read by the one owner rule `card_owns_the_turn`): the relay door sends nothing to the errand on its subject. Never a process banner (`transient`), the card a running errand delivers into, or any card while an errand builds one; a paid stop verdict that ends the errand keeps it. — since 2026-11-11 · nodes 4.482.
- **CRIT-E42 · What can be reopened belongs to one conversation and is declared by how it ended.** The just-ended pool (`nucleo/workers/ended`) is bound to the observability session: a new session empties it and an errand born before it never enters it; each end stays reopenable for `REOPEN_GRACE_S[end_of(row)]` (delivered 900 s; done, error, cancelled, relevada 300 s), and an end not declared there is final. — since 2026-11-11 · nodes 4.483 · `nucleo/workers/ended.py`.
- **CRIT-E13 · A worker's request is never his click.** On a self-hosted engine every mutation is the operator's
 unless it is a named worker door (`/api/worker/*`, the agent report, the browser bridge, memory with the per-task
 token, search); it is admitted for his screen's per-boot HttpOnly cookie or a process the engine did not spawn,
 and refused for a worker (engine ancestry, a remembered worker session, worker env), the engine itself or a
 socket nobody here owns. The CSRF/rebinding rules of CRIT-E11 also cover mutations outside `/api/`. — since
 2026-10-14 · nodes 2.620, 2.621, 2.622, 2.623, 2.624 · `server/operator_gate.py`, `server/peer_process.py`,
 `server/ui_session.py`, `nucleo/workers/providers/spawned.py`.
- **CRIT-E12 · What a stranger wrote is data, and it cannot send on its own.** Every body of a mail, a chat or an
 agent's answer reaches the model fenced (⟦ ⟧, unforgeable); with such text in the context, an act that leaves runs
 without a question only when the verdict surely names that send — both channels. — since 2026-10-02 · nodes 2.205 ·
 `nucleo/untrusted.py`, `nucleo/acts/message.py` (`asked_if_leaving`).
- **CRIT-E11 · A web page cannot drive the engine.** On a self-hosted engine every `/api/*` call names this engine in
 `Host` and comes from this machine, and a mutation from another site (`Origin`, `Sec-Fetch-Site: cross-site`) is
 refused; `ZAELAR_API_TOKEN` is the only door for a caller elsewhere. On a hosted deployment a mutation comes from the
 deployment's own site. — since 2026-10-02 · nodes 7.62 · `server/api_guard.py`, `server/__init__.py`.
- **CRIT-E10 · A worker that may write writes only inside its own workdir.** Every trusted worker with `Write` gets
 the writes-only jail (a PreToolUse hook: Write/Edit outside the workdir denied, reads free); the dev-worker keeps
 its full jail; a jail that cannot be armed takes the writing tools away, never the jail. — since 2026-10-01 ·
 nodes 3.112, 2.5 · `nucleo/dev_worker_guard.py`, `nucleo/dispatch/session.py`.
- **CRIT-E14 · A worker reaches its own engine behind session admission.** Where every request must carry a
 session, a loopback call to one of the worker doors (`operator_gate.WORKER_DOORS`) is served without one — each
 door verifies the worker itself; off the machine, or to any other route, the session is still required
 (`server/ingress.py::is_own_worker_door`). — since 2026-10-24 · nodes 7.77.
- **CRIT-E28 · An errand that delivers into a card leaves ONE reference box on his chat wall.** Decided at the
 dispatcher's single door by the sealed surface (a card-naming surface draws it; told/silent, a child errand, an
 arriving event or a cluster peer do not), drawn at the START so a half-done errand keeps it, updated in place to its
 ending, and every errand leaves `artifact opened|skipped` on record; a report is kept (library file + the task's
 copy) and the box reopens THAT deliverable through the one reopen door. — since 2026-11-08 · nodes 2.1635, 13.165,
 4.413 · `nucleo/chat_refs.py`, `nucleo/docsheet.py`.
- **CRIT-E29 · The daemon's acting routes answer only this computer.** `grant · revoke · pick · start · pair` on `/api/daemon/*` refuse a caller that is not on this computer, whatever token it presents; `status` off this computer never names a folder (V2-575 P1) — since 2026-11-09 · nodes 7.98 · `server/` daemon proxy.
- **CRIT-E30 · A sign-in window opens on the local daemon only when it declared `browser.auth` (measured) and this engine has no window of its own.** The daemon reports a COUNT of new cookies, never a cookie; with no daemon the reach is byte-identical (V2-575 P2) — since 2026-11-09 · nodes 7.97, 4.414 · `widgets/navegador/owner_login/daemon_link.py`, `daemon/browser/`.
- **CRIT-E31 · A daemon release is verifiable by a third party.** Each build signs its `SHA256SUMS-<suffix>` with a Sigstore keyless signature (the release workflow's OIDC identity) AFTER `release_names.py` rewrites it, verifies the bundle against its own identity before upload, and attests the build provenance of exactly what the sums list; `release_names.py` leaves no older signature behind. `get.sh`/`get.ps1` verify the bundle against `…/daemon-artifacts.yml@refs/tags/` when `cosign` is on PATH and refuse a bad or MISSING signature; without it they check the hash and say so in one line (V2-575 P4) — since 2026-11-09 · nodes 7.99 · `.github/workflows/daemon-artifacts.yml`, `daemon/packaging/`.
- **CRIT-E32 · The 🖥 screen is the daemon's settings, and every field it reads has a «not known» face.** Five cards in order — status · folders (the first granted is the default; Documents is suggested with none) · browser (polled every 2 s only while `browser.state` is `downloading`) · pairing (a one-time code with a running countdown; `relay_not_available` or no `relay` in the status hides it; loopback is «already linked») · tunnel (consent text; the switch per CRIT-E37) — each painted from `/api/daemon/status`, a missing or wrong-typed field drawn «not known», never an exception or a raw key; the install wizard ENDS on this view and does not close itself; the 🖥 icon is green on `relay.connected` or a local daemon that answers (V2-575) — since 2026-11-09 · nodes 4.415, 4.417, 4.418, 4.419, 4.432 · `frontend/app/components/DaemonSetup.js`, `frontend/app/components/daemon/`, `frontend/app/services/daemon.js`.
- **CRIT-E33 · A remote caller never names a directory on his disk.** A relayed `browser.open` loses `profile` before the handler runs (the window opens on the daemon's own profile); an unknown op is an error, a `deadline_ms` is honoured, a result over 20 MB is refused, and `bye revoked` forgets the relay credential (V2-575 P3) — since 2026-11-09 · nodes 7.104 · `daemon/relay/dispatch.py`, `daemon/relay/client.py`.
- **CRIT-E34 · A session leaves only from the daemon's own profile, for one site.** `browser.export_session` returns the registrable domain of `site` and nothing else, at most 2 MB, refuses a window open on any other profile and reads no other browser; the audit names the domain and counts. The engine re-filters to that domain on import (V2-575 P3) — since 2026-11-09 · nodes 7.105, 4.420 · `daemon/relay/session_export.py`, `widgets/navegador/owner_page.py`.
- **CRIT-E35 · From his phone no sign-in window opens anywhere.** `browser_window.reach("phone")` is nowhere whatever the display or the daemon; the sign-in blocks as `phone` and the errand's own question says to open the agent on a computer (V2-575 P3) — since 2026-11-09 · nodes 4.420 · `nucleo/browser_window.py`, `widgets/navegador/owner_login/authenticate.py`.
- **CRIT-E36 · The daemon updates itself only with bytes the publisher signed for, and a failure changes nothing.** It installs only from an `update-manifest.json` whose minisign signature verifies against the committed `daemon/update/PUBLIC_KEY` (or a `next_key` a verified manifest announced) and whose `tag` is the release it was found on; the downloaded asset must match the manifest's size and sha256 (and, with `cosign` present, the signed sums), the staged file is re-hashed before the swap, and on macOS the new bundle's signature must verify (same team on a Developer-ID install). Any failure → `state = failed` with the reason in `/health.update`, the installed program's bytes unchanged; `ready` is reachable only through `downloading`; never backwards (V2-869 §4) — since 2026-11-09 · nodes 7.110 · `daemon/update/`.
- **CRIT-E37 · The release signs what it has an identity for and says what it skipped.** Developer ID + notarization (macOS) and Authenticode (Windows) run after the smoke test and before the sums, each only when ALL its secrets exist, else a «unsigned: identity secrets absent» notice and the ad hoc build as before; the update manifest is written over the published names, agreeing with the signed sums, and minisign-signed when `MINISIGN_SECRET_KEY` exists (unsigned otherwise — and refused by every client); the workflow reads no secret outside the agreed names (V2-869 §5) — since 2026-11-09 · nodes 7.111 · `.github/workflows/daemon-artifacts.yml`, `daemon/packaging/`.
- **CRIT-E38 · The egress tunnel never reaches a private address.** Every destination is resolved ON THE DAEMON and EVERY address it returns must be public (loopback, RFC 1918, link-local, ULA, CGNAT, multicast/reserved, and any v4 embedded in a mapped/NAT64/6to4 v6 refused); one private answer refuses the name; the socket connects to a checked address, never to the name again, and the peer is re-checked; names that only exist inside his network (`localhost`, `.local`, `.lan`, `.internal`, `.home.arpa`) are refused before any lookup; ports 80/443/8080/8443 only; a per-site token bucket; an audit line per host and hour with counts and bytes, never a URL (V2-836) — since 2026-11-09 · nodes 7.121 · `daemon/security/egress_guard.py`, `daemon/egress/connect.py`, `daemon/egress/ledger.py`.
- **CRIT-E39 · The egress tunnel needs HIS switch, on his computer.** `config.egress.enabled` is off by default and on only with a recorded consent (a file edited to `enabled: true` reads off); it is switched from the tray or the screen of an engine on the same computer over loopback — never by a relay command; `egress.offer` is refused `egress_disabled` while off; `hello` carries `egress` only while on; switching off closes the tunnel and every stream at once and the switch is re-read for every new stream. An engine away from his computer shows the state and says where it is switched (V2-836) — since 2026-11-09 · nodes 7.122, 7.125, 4.432 · `daemon/config.py`, `daemon/egress/tunnel.py`, `daemon/http/routes.py`, `server/daemon_api.py`, `frontend/app/components/daemon/cards.js`.
- **CRIT-E40 · Without his tunnel the engine's traffic is byte-identical to before.** The engine's Chromium (navigator and search) launches with `--proxy-server` and its direct fetch with a proxy ONLY while a tunnel is up; with none the launch args and the fetch are the old ones. The tunnel exists only on an engine with an instance id, `ZAELAR_TUNNEL_ORIGIN` and a relay; its dial is admitted by its own token (`<instance>.<secret>`, ≤ 10 min, verified in constant time by the instance that minted it, 4401 otherwise), replayed by prefix on a shared hostname, with no cookie; a WebSocket there is admitted only on its allowlist (V2-836) — since 2026-11-09 · nodes 4.431, 7.123, 7.124 · `nucleo/daemon_egress/`, `server/daemon_tunnel.py`, `server/ingress.py`, `widgets/navegador/owner_page.py`, `search/browser.py`.

## 4b · A task

A request Flash identifies as work is a TASK: one row, one Brain Worker resumable by id, one writer of its ending.
Flash keeps the conversation; the row is what both brains read.

- **CRIT-T1 · The row is the task's state; the worker session is a cache.** Every task is ONE row of `tasks` with
 what it waits for and how it resumes: `session_id` and `cwd` (a harness resumes by id but keeps no working
 directory), `waiting_for` (`user_answer | worker | send_echo | time | event:<topic>`), `waiting_since`, `deadline`,
 `ask_id` + `ask`, `playbook`, and the trace of the turn that opened it. A task that waits is `state=waiting`; a
 restart keeps it waiting, never buries it. A resume never resumes blind: the session is relaunched by its id in its
 stored cwd with a re-brief built from the row (`nucleo/cli/worker_api_resume.rebrief`). «How is it going?» is read
 from the row; the worker does not wake. A worker that dies without finishing leaves its place and is resumed by id
 once. A worker is named by its row from birth: the dispatcher stamps the row id and registers the record before its
 first act, and every line about it is keyed by the row, never by the boot-local number. — since 2026-11-05 · nodes
 2.1012, 2.1014, 2.1030, 2.1111, 2.1356 · `nucleo/circuit/ledger.py`,
 `memory/tasks_store.py`.
- **CRIT-T2a · The playbook is the worker's; checkpoint 1 is held by the harness.** The conversation model routes and
 talks: it never picks a playbook. The worker's brief carries the playbook catalogue (each with its end state) and the
 engine's suggestion; at checkpoint 1 the worker names its playbook (`report playbook`) and records a readable goal
 (`report goal`, refused with why when it is prose, a card's mere presence or undeclared). An act that leaves the
 machine — a send, an agent call — is refused until checkpoint 1 is closed; a `message` also needs its end state on
 the row. Reads are never held. There is ONE catalogue: `meeting`/`booking` (a conversation that ends on his agenda)
 are names in it — not offered to a worker sent to do the job on a website — and the name the task gave rides the send
 that can open a follow-through, so the errand born from it inherits its kind; no word table over the objective
 decides it. — since 2026-11-05 (one catalogue: 2026-11-07, V2-859 T562) (rewritten 2026-11-21, INI-078 L1) · nodes
 2.1357, 2.1351, 2.60 · `nucleo/workers/prompts/playbook.py`, `nucleo/workers/exit_gate.py`,
 `nucleo/errands/playbooks.py`.
- **CRIT-T2c · The deliverable sheet declares what an end state reads.** The results sheet — the card every search
 errand delivers into — declares its `items` (read from its view, listed only), so a worker's goal on it is readable;
 a sheet INSTANCE (`results::<sheet>`) declares what its card declares and a rows clause is read on THAT sheet, never
 the base card (`widgets/rows.declared`, `verify.check_clause`); the goal door's refusal names what each card the
 clauses name declares — a fact from the manifests, never an example to copy; and every command a help text names
 is one the worker can run (`python -m nucleo.cli.widget …`, never an alias no module answers to: measured
 2026-11-06, 18 reads of the sheet's grammar held for an approval nobody could give). — since 2026-11-06 ·
 nodes 2.1358 · `widgets/results/manifest.json`, `widgets/rows.py`, `nucleo/circuit/spec_declares.py`,
 `nucleo/circuit/verify.py`, `nucleo/cli/report.py`, `nucleo/cli/widget.py`.
- **CRIT-T2d · The brief shows the shape the end state takes, and names each bridge with its argument.** The
 playbook block carries the grammar's SHAPE (`spec_declares.SHAPE`, one constant the goal door's help reads too;
 placeholders, no value a worker could copy) and what this playbook's deliverable card declares, from its manifest
 (`playbook.DELIVERABLE` → `spec_declares.said_of`), in the session's language; every bridge subcommand the block
 names whose parser requires a positional carries its placeholder (`cli.mem recall "<…>"`, `cli.report plan "<…>"`).
 Measured 2026-11-06: with only the prose «DONE WHEN» beside `report goal`, every first goal of eleven errands was
 prose and refused — a round trip and a late checkpoint 1 each. — since 2026-11-06 · nodes 2.1359 ·
 `nucleo/workers/prompts/playbook.py`, `nucleo/circuit/spec_declares.py`, `i18n/genesis/*/voice.json`.
- **CRIT-T2b · A message has ONE owner (`nucleo/send`), from his words to the connector's receipt.** Every way a
 message can be asked for is a HAND-OVER to the owner and decides nothing: the conversation model's `send_message` act
 and any widget act whose event type is a message or leaves toward a messaging platform (`send/turn.is_message`,
 `send/turn.owned`), carried with his words to `owner.intake` (`conversation_host/routing.send`); a worker's message
 the exit door would ask about (`send/worker.hand`, after the door's refusals and a mandate's release). The owner
 keeps ONE draft (`send/draft`) and decides by code over it: nobody resolved → the name resolved (`send/people`: the
 open conversation first, then `contactos/who.find`) — one person is that person, several or a word nobody carries is
 ONE question naming them, never a pick; no text → «what shall I tell her?»; both → ONE confirmation that reads the
 text. The model acts on the open draft only by its `#n` in OPEN (`draft_edit` · `draft_send` · `draft_drop`,
 `send/by_number`): it brings the fields and the owner decides; a number that is not the open draft fails and gives
 OPEN back. Nothing leaves before his yes over one person and a text — never at intake, whatever the order said; a
 go-ahead answers only a confirmation he HEARD, said last (`send/heard.answers`); what would stop it (a channel to
 choose, no way to reach her) is said BEFORE the confirmation; the confirmation is verified to carry his text verbatim
 and her name (`send/ask.confirm`); what the model called is read ONCE when it is handed over (`deliver.adopt`: a
 reply → its conversation's chat id, a forward → its source message id, a card draft → its text and person, a time →
 the moment, said in the confirmation and sent as the card's held draft); a second order while one is open waits its
 turn (`intake.open_the_next`); it leaves through the card's own act with the chosen row's id (`resolve_target`
 `contact_id`), and the final line is the connector's receipt (`send/receipt`). A draft nobody touches for 10 min is
 closed and reads nothing (`draft.IDLE_S`). — since 2026-11-18 (V2-938) (rewritten 2026-11-21, INI-078 L1) · nodes
 2.1801 · `nucleo/send/`, `nucleo/cli/worker_api.py`, `widgets/mensajeria/outbound/targets.py`. End to end: `python -m
 tests.agent_headless.e2e.send_owner.bench` (a sandbox engine, real models, a WhatsApp double).
- **CRIT-T2 · `circuit.settle` is the only writer of an ending.** `done | failed | cancelled` is written for every row
 — worker, inline, list, mirror — by `nucleo/circuit.settle` and nothing else; the move is said ONCE as a `task_state`
 event {task_id, state, writer, trace}
 and the bus topic `task.ended` {task_id, state, trace} (what the row left behind subscribes to it). The worker never closes its task: it asks `verify` through the bridge, which
 returns the circuit's verdict on the declared end state and writes no state. A stream's row is not ended by one
 item's run: it rests. A task ends for three causes only: its `done_when` met (verified), his stop (voice, text or
 the list's cancel button: `POST /api/tasks/{row or session id}/cancel` → the worker told, `settle(cancelled)`,
 one line), or a hard failure with its reason — never its age: no wall-clock budget, no «stop or keep
 going?» (the 15 s sign of life stays). — since 2026-11-05 · nodes 7.91, 2.1013, 2.1096, 2.1350, 2.1354, 2.1355 ·
 `nucleo/circuit/__init__.py::settle`, `nucleo/pulse/workers.py`.
- **CRIT-T3 · A question for him is durable, and what he says about an open process reaches it through ONE door.**
 Whoever asks — a worker through the bridge, a door's consent ASK on an inline act — goes through ONE asker
 (`nucleo/circuit/asker`): the row waits for `user_answer` with an `ask_id`, the act it retains is the row's `ask`
 artefact, and one `ask` event puts the question on screen with a way to answer. A screen answer carries its `ask_id`
 (`POST /api/tasks/{id}/answer`, 409 when that question is not open). Nothing routes his words before the model
 (`conversation_host/routing.HostRoute`): the model reads what is open — the queue's tasks by `#n`, each by what it
 DOES, its state and a waiting one's question word for word with its declared answers, a question open on something
 else by its key, and our own last question (`conversation_host/open_block.py` over the board
 `switchboard/board.open_processes`) — and his words about a process's MATTER go to it only by the model's
 `task_say(#n)`, through the one delivery door (`switchboard/act.deliver`): a waiting question takes them as its
 answer (a plain yes or no decides its retained act at once, as the button does), a parked STEP of a running process
 (its browser's click gate) takes his yes or no, a start question takes a detail as part of the errand (`_absorbed`),
 and a running worker takes them as his next words; a remark about the assistant itself is no process's (`task_say`'s
 declared purpose). A stop ends a process — or every open one — through the row's ONE cancel door
 (`dispatch.control.cancel_row`, the screen's button: a running worker is told to stop, a queued one never starts, a
 waiting question is closed), by the model's `stop_task(#n | all)` or its stop of everything
 (`conversation_host/stops.py`), never as words relayed to the worker. A process whose worker has NOT started — the
 admission gate holds it — is listed as `HELD` (`switchboard/held.py`). Every batch the model decides leaves one
 `route` event with what it saw and what it chose (`conversation_host/route.py`). One answer runs its retained act
 once. The worker's process ends after asking and the answer resumes THAT session (CRIT-T1). — since 2026-11-05, the
 switchboard since 2026-11-17 (V2-931) (rewritten 2026-11-21, INI-078 L1) · nodes 2.1030, 2.1110, 4.359 ·
 `nucleo/switchboard/board.py`, `nucleo/conversation_host/acts_tasks.py`.
- **CRIT-T4 · A wait for his answer ends at his rule, said once.** A `user_answer` wait is closed by the pulse at
 `waiting_since` plus his period — a `rules` row, scope `global`, key `answer_wait_days`, default 7 from genesis —
 through `circuit.settle(cancelled)`, with ONE line by the out-of-turn mouth; a rule he changes applies to the waits
 already open. Until then the question stays on screen (shown again after a restart) and the turn's prompt
 reads it from the row, with since when. — since 2026-11-05 · nodes 2.1015 ·
 `nucleo/circuit/waits.py::expired_waits` (re-exported by the ledger), `nucleo/pulse/workers.py`.
- **CRIT-T5 · A worker that read a stranger's text asks before anything leaves.** Taint is PROVENANCE, not permission:
 every untrusted read a worker session does (a web search, a page, a browser page, an inbound message or mail, a
 network agent's answer) marks THAT session (`nucleo/untrusted.py` per session, read through `nucleo/workers/taint.py`,
 shadowed on the row so a resumed session still asks), never his voice. Every exit door a worker reaches — a leaving
 `widget_data` act through the message door, a network errand (`mesh serve`), a browser submit — is the durable ask
 while the session is tainted, unless the rules' mandate covers that act; his yes clears it. The taint reads WHAT
 leaves (V2-852 T08/T14): a provider query the outbound scan found nothing of his in (no redaction) and a click that
 sends no form are not exits that carry him, so a search keeps searching after reading the web. Every act the worker
 policy admits has an executor. — since 2026-11-05 · nodes 2.1091, 2.1092, 2.1093, 2.1094 ·
 `nucleo/workers/exit_gate.py`.
- **CRIT-T6 · ONE mouth, two entries.** In a turn the turn's mouth speaks the verdict (`nucleo/turn/reply`); a door
 that speaks while its turn is live says it through that mouth (`nucleo/turn/mouth`). Out of a turn everything goes
 through `nucleo/pulse/notices.notify`, with the task's `task_id` or a notice `key` — deduped, said by voice when he
 is there, else shown, pushed or owed. A question's identity is its `ask_id` (`ask:<ask_id>`, whatever door words
 it), and an owed question whose ask is no longer open is closed `answered`, never pushed or painted later. No product file calls the speaking primitive (`voice/proactive.notify`) but the
 mouth itself. A task matter goes to its row and that mouth, never as a note into the next turn's prompt. — since
 2026-11-05 · nodes 2.1070, 2.1071, 2.1173, 2.1353.
- **CRIT-T7 · No model runs over a reply already said.** One run per batch of his words, for every channel
 (`conversation/manager/run.py`: compose → the one fast model → tools through the gateway → say → close); its steps
 (reads, then the answer) are bounded by `max_steps`, and what the run's checks refuse (a figure its evidence does not
 back, an empty reply, an order written as words) gets ONE repair round BEFORE anything is published; once a line is
 said nothing re-runs the model over it, and a failed run's line is worded by the host in his language (`Owed.owe`),
 never by the model that failed. — since 2026-11-05 (rewritten 2026-11-21, INI-078 L1) · nodes 3.175.
- **CRIT-T7b · A whisper is a typed slot filled BETWEEN requests, never a voice.** The whisperer (`nucleo/whisper/`)
 is OFF on every deployment and nothing subscribes it today (V2-942); its entry is `run.on_turn_closed`, on its own
 thread; a deterministic gate (`gate.py`) decides whether it is worth one reasoning call (`whisperer` row of the model
 table, metered); its output is a slot with declared, sourced fields and no instruction field (`slot.py`), judged
 against the next turn (fresh · stale · expired · late) and dropped past 90 s. In `shadow` (`ZAELAR_WHISPER`) it
 writes nothing but `whisper` events — its rendering is wired into no prompt, memory, task or reply. — since
 2026-11-12 (rewritten 2026-11-21, INI-078 L1) · nodes 2.1721.
- **CRIT-T8 · A worker gets its method and the headlines, never the whole catalogue.** The brief is composed in the
 session's language as a stable prefix (the shell's rules, the playbook's nine checkpoints with `done_when`, one
 headline per family of the catalogue) followed by what changes per task, under a measured ceiling; a family's full
 set comes on request through the bridge (`python -m nucleo.cli.bridge catalog <family>`). Which playbook
 (`errand | message | document`) is read from facts the engine has — the surface and the mandate — never from
 words. His rules reach the worker as data; the door stays their only authoritative reader. A
 worker's harness never reads the host user's own config. The families are ordered ours → outside → browser: the
 first is our `search` (the search service; what can be PLAYED is the `musica`/`youtube` cards, never the web), and
 the network is asked first only for a capability none of ours covers (V2-860 F3, 2026-11-08). — since 2026-11-05 ·
 nodes 2.1151, 2.1150, 2.1095, 2.1634 · `nucleo/workers/prompts/playbook.py`, `nucleo/workers/prompts/catalog.py`.
- **CRIT-T9 · What a worker does is kept on its task, at the door.** Every act through the bridge — denied, asked, run,
 and the act his yes ran — records its artefact on the task's row and emits ONE `worker_act` event {task_id, session,
 act, door, outcome}; files a worker produces are slots of its row. The worker cannot produce a deliverable that is
 not recorded. — since 2026-11-05 · nodes 2.1096, 2.1097 · `nucleo/workers/task_files.py`.
- **CRIT-T10 · The errand kind is the model's call.** Which kind of errand a request is (`web | code | generic`) is
 the conversation model's own `start_task(kind)`, carried in the errand's context at full confidence
 (`conversation_host/acts_tasks.errand_context`) and read by `kind.kind_of`; without one (a cron relaunch, a resumed
 row) the errand is `generic`. A card rewrite his order did not make sure still parks his question at
 `dispatch._run_session` before any worker starts (CRIT-C4). — since 2026-11-05 (rewritten 2026-11-21, INI-078 L1) ·
 nodes 2.1170 · `nucleo/request/kind.py`.
- **CRIT-T11 · A rule that says «when X arrives, do Y» is a subscription, served by ONE stream worker.** His spoken
 rule is read once into an `on_event` row ({topic, match, do, may, if}) matched IN CODE on the event's declared fields;
 a pre-condition is a declared verdict, never code. A subscribed event goes to the stream's worker — one always-on
 session per stream (`stream-<name>`, a `mode=recurring` row that waits for its topic between items), resumed by id
 per item, one item at a time, with a budget per event, recycled after a bounded number of items, held while the agent
 is stopped, under the mandate the rule grants (CRIT-T5 for the rest). — since 2026-11-05 · nodes 2.1172, 2.1011 ·
 `rules/subscriptions.py`, `nucleo/events/stream.py`.
- **CRIT-T12 · One stream task, two playbooks, chosen by what his rules GRANT.** A stream item whose rules grant only
 a reply (`may` = `message`, read through `mandate.acts`) takes the BOUNDED turn: one model turn holding no tools, the
 item marked untrusted data, and the ENGINE sends — only to the conversation the item came from, through
 `mandate.deliver` (sent · held as a draft · dropped by his «never»). Any other grant, or a model answer that
 `needs_hands`, takes the worker session; an unreadable answer sends nothing and the row rests `failed`. The choice is
 never read off his words. — since 2026-11-06 · nodes 2.1617, 2.1172 · `nucleo/events/stream_reply.py`, `nucleo/events/stream.py`.

## 5 · Memory and rules

- **CRIT-T14 · A shutdown is not a cancellation.** Only HIS cancel (or a wait's deadline) ends a task `cancelled`.
 The host stopping — the idle stop, a SIGTERM, a platform stop — is a declared stop reason (`nucleo/workers/ended.py`
 `SHUTDOWN`, read by `ended.his_cancel`), never a string compared in two places: a worker it stops leaves its place
 the way a crash does — its row waits on the worker with a deadline and no attempt spent, resumed by id by the pulse —
 and what it produced stays (the generator's partial folder and journal entry, with its row, which the resumed build
 rebuilds clean). The boot leaves that build to its row and never buries a row that waits on its worker; reopening it
 says it was interrupted, never «nothing was kept». — since 2026-11-11 (V2-877 #2) · nodes 2.1689 ·
 `nucleo/workers/session_finish.py`, `nucleo/dispatch/control.py::stop_all_async`, `widgets/generator.py`.
- **CRIT-T15 · One question is one ask; a confirmed errand is never asked twice.** His yes to an errand's start is a
 fact of its ROW (`dispatch.confirm.CONFIRMED_SLOT`, written by the start gate a confirmed launch crosses, read by both
 start gates), so a relay of the same row is never asked again. Every ask has its own id; a re-ask is a new open
 question. The bind door and the answer door read one refusal (`worker_api_answer.refusal`): an answer that would be
 refused is never reported bound, and a spent question is said once in his language. The notice that said a question
 settles when it is answered. — since 2026-11-11 (V2-877 #2) · nodes 2.1688 · `nucleo/dispatch/confirm.py`,
 `nucleo/dispatch/session.py`, `nucleo/cli/worker_api_answer.py`, `nucleo/pulse/notices.py::bind_ask`.
- **CRIT-M7 · Every standing rule and preference is ONE row of the `rules` table**, scoped (`global` ·
 `<domain>[/<channel>[/<act>]]` · `widget:<id>[/<action>]` · `item:<id>`, read from declared classes, channels and
 manifests) and read by a cascade over the request's path: the more specific row runs last and wins, at one level
 his row beats the default, an `except` scope is not covered, a row past its `until` is absent. Genesis defaults are
 rows built at read time. `consent.decide` reads the gate; the rails (a missing fact, a doubt, the radius) are code
 no row reaches. The style knobs (`voice`), a widget's preferences (`widget:<id>`) and the autoresponder (scoped to
 its platform) are rows too; each older store is imported once. Every row has an id: «what rules do I have?», «forget
 the email rule» and ⚙ Settings → Rules list, edit, switch off and delete BY ID (a default is overridden, never
 deleted); he never sees an id, a key or a scope — his own words, places named from declared data in his language. — since 2026-10-26 · nodes 2.809, 2.810, 2.811, 2.812 · `rules/`,
 `nucleo/consent.py`, `nucleo/style_policy.py`, `widgets/youtube/prefs.py`.
- **CRIT-M2 · Genesis is per domain** (`style`, `consent`, `library`, `errands`, `playbooks`); what he says over
 `style` and `consent` is a row of the rules table (CRIT-M7), the others keep their override file; a factory reset forgets the spoken rules and keeps credentials, settings and connectors; it never
 deletes under a live server. — since 2026-09-29 · nodes 2.173, 8.4, 3.94.
- **CRIT-M3 · A late recall DEGRADES durable memory, never deletes it**; the memory row says whose fact it
 shows. — since 2026-09-24 · nodes 3.79, 3.33.
- **CRIT-M4 · What the operator said survives a failing turn**, and a spoken correction reaches the pill it
 corrects. — since 2026-09-03 · ⚠ sin test.
- **CRIT-M5 · The whole prompt of every turn is on disk**, joined by trace; capture is never switched off. — since
 2026-09-20 · nodes 2.100.
- **CRIT-M6 · The memory state is written only when it changes.** The live-session projection's change key is
 computed with the clock frozen, so no clock-derived field (`age_s`, `unreported_s`…) can rewrite the state — and
 emit a `memory`/`state` event — on a tick where nothing happened (`dispatch.sync_state`). — since 2026-10-24 ·
 nodes 7.78.
- **CRIT-M8 · Memory keeps what HE said, and only that.** The distiller reads a pasted text whole (head and tail)
 and knows its channel (spoken or typed) and the assistant's own name; an identity claim rejected as «not about the
 operator» writes no trusted row (quarantined, like any rejected identity); «I already told you X» is not a fact;
 each row records its real channel; the words before a wake word count only when the paid STT could not hear them,
 so our own voice is never his. — since 2026-10-26 · nodes 1.3, 4.209 · `nucleo/memory_agent/processor/distill.py`,
 `nucleo/memory_agent/`, `voice/engine/pipeline/agent_events.py`.
- **CRIT-M9 · Inbound messages are their own lane, and recall says where each line came from.** A `msg` row is
 never promoted, never in the passive blocks, never ranked with his own facts (`query(lane="own")` is the
 default; `messages` and `all` are asked for); recall returns id, date, level, kind, source and session, and his
 own past conversation has one reader (`memory.conversation`, `mem_cli history`). — since 2026-10-26 · nodes 1.2,
 1.10 · `memory/retriever/`, `memory/history.py`, `server/memory_routes.py`.
- **CRIT-M10 · The memory viewer never paints more than the device can draw.** The overview shows totals (COUNTs,
 by type and by day) and charts; the «Cards» tab shows the NEWEST memories per layer, capped on the server and each
 text cut; the graph is aggregated on the server and bounded by the device's node budget — past it, only its top
 level (the concepts) is sent. No row list of a store, and nothing about the machine, ever reaches it; its canvas
 is fitted to its own panel. — since 2026-10-26, cards and top level 2026-10-27 · nodes 1.11, 1.12 ·
 `memory/viewer.py`, `server/memory_viewer_api.py`, `frontend/app/components/memory/`.
- **CRIT-M11 · A file added to the chat is a REFERENCE, streamed to disk and read once with bounded work.** The
 kind is decided by its bytes (image, PDF, text); size, files per message and the disk's free-space headroom are
 refused before a byte is written, from ONE declared table (`config/attachments.default.json`, measured); the
 body streams to disk, files are read one at a time, and the turn sees what he just attached as state — the
 reading made at upload, an image read by a model that receives it — and nothing when there is none. — since
 2026-10-26 · nodes 1.13, 2.814, 4.296 · `files/attachments.py`, `server/memory_routes.py`,
 `frontend/app/services/chat-files.js`.

- **CRIT-M12 · The person he means is ONE ranking, by sound, filtered by the act.** `directory.resolve` gives every
 contact the strongest reason it matches (a word he gave that person · the exact name, number or address · every
 word · a word inside a compound name · the same SOUND, any language in Latin letters — K/C/Q, B/V, a silent H —
 a short form inside a name — «Toni» of «Antonio» — and only when nothing else matched, a near spelling); a name in
 quotes is matched literally. The CLOSEST LEVEL any match is on decides first (`directory.nearest`, 2026-11-21): his
 favorite (or alias, relation), else a message either way within 7 days, else within 40 (`contacts.windows_days`),
 else the rest — when he last exchanged a message is read from the messaging archive, the one log every channel
 reaches; one person there is the answer, several there the question among them only. Inside a level the native scale
 the card's manifest declares ranks (favorites → family → friends → colleagues); an UNCLASSIFIED contact (no phone, no address, no channel, derived and never stored)
 is never a send target. The act filters first (a WhatsApp send keeps who is reachable there, a mail who has an
 address). The best is used alone only when it leads the next by `clear_margin` (a rule row of the contacts card);
 else ONE question naming at most `CANDIDATES_MAX`, closest first, and the word he then used is kept on that person
 (`directory.asked`/`answered`). A person named by who they are to him is looked up by the declared relation, never
 by a label in a name; the default channel is his choice, else the busiest, else a question. The send door (`contactos/who.find`) and the card's search read a name the same way. — since 2026-11-05 ·
 nodes 4.353, 4.354, 4.355, 4.356, 4.617, 2.1501 · `widgets/directory.py`, `widgets/contactos/`,
 `widgets/mensajeria/outbound/targets.py`.
- **CRIT-M12c · One person is ONE row, whatever source each row came from.** A phone (any the row holds, as its
 last nine digits), an address or a platform account PROVES a person; a name never does (`contactos/identity.py`).
 Two rows sharing one are folded — on every import, on the store's migration (the look back) and after each
 refresh — unless one source keeps two differently named rows on that line (a landline, a switchboard). Nothing is
 thrown away: the name not shown stays as a name the person is known by, with its source, and finds her; the folded
 row is kept whole, its id keeps answering, and `split_contact` restores it for good. The shown name is his own,
 else his address book's, else the chat's; a source renames only a row it named and he never did. What a platform
 changes arrives by itself: pushed when the connector can tell (a `refresh` never adds anybody), read on every
 pass of a linked source. Linking a source IS the ask (2026-11-21): ONE door, `sources.import_linked`, reads every
 linked source — on the link (the Google consent, a messaging account first seen connected with its book never
 read), and at a start with an empty directory (the one a reset ends in), agent running or not; then the inbound
 half runs on its cadence with no switch, and the one control left sends his changes TO Google (`sync_contacts`).
 A person it brings that a row proves is a channel of that row. One address book's two entries on one line are one person only when they start with
 the same given name or one is a one-word stem of the other; a shared surname proves nothing. A said NAME is
 scored word by word (`contactos/who.py`: sound, stem, one slip, any order, an address that sounds like it) with
 no model; a word nobody carries makes the answer `partial` — names to ask among, never a match — for the doors
 (`directory.resolve`) and the send worker (`find_contact`) alike (node 4.586). The ORDER the sources arrive in
 changes nothing: every import and every start end in one look back, which also joins the two rows of two
 sources that only a full name joins; a group's member nobody else knows and an account named by a number are
 kept mapped and out of sight until a source lists them as his or names them; one word several people carry
 answers a question with every carrier, never the ranking's leader alone (node 4.592). When nothing proves it, he says it once (`merge_contacts`). The
 conversation he has OPEN is the first reading of a name it carries at the send door; a word he gave somebody else
 is asked, the one in front first. The look back also runs — and is WRITTEN — at every start of the engine, as the
 card's declared start step (`"background": {"on_start": true}`, `widgets/start_steps.py`): idempotent, off the
 loop. — since 2026-11-18 (V2-934) · nodes 4.581, 4.582, 4.583, 2.1811 ·
 `widgets/contactos/identity.py`, `fusion.py`, `person_actions.py`, `widgets/mensajeria/outbound/in_front.py`,
 `connectors/whatsapp/`.
- **CRIT-M12d · The messaging past is copied inside declared bounds; live is never bounded.** Every message that
 arrives or leaves is archived. The FIRST import of an account is bounded by days AND conversations AND messages
 per conversation AND a total, newest first (`config/messaging.default.json`, read by
 `connectors/messaging/history.policy`); what a phone hands over at pairing is trimmed to the day bound. A
 conversation somebody names and the archive cannot answer about is asked of its platform ON DEMAND — that one, a
 bounded stretch per ask, by id or by the name used (`archive.want`) — and the search says it asked. A file over
 the per-file cap is never downloaded by itself; downloaded media leaves oldest first over its disk budget (the
 smaller of an absolute bound and a share of the disk), whatever the day window. Who is a contact is not bounded
 by any of this: a message from an account no row holds marks its source owed a read. — since 2026-11-18
 (V2-936) · nodes 4.588 · `.meshkore/docs/modules/zaelar-messaging-history.md`.
- **CRIT-M12b · His contacts are structured memory, and one person is one person.** Each record the contacts card
 manages is one structured pill in its own retriever lane (`nucleo/memory_agent/contacts.py`, slot `contact:<id>`,
 no phone or address in it); a NAME is the resolver's, a DESCRIPTION («the girl from the guitar course») is
 `contacts.who`, which returns contact ids with their evidence. A fact that names one person of his book writes her
 relation and learned name once, through the card's own door. REM links records of one person that share an
 identifier and whose names agree (`memory/rem/contacts.py` → `link_contact`, never a delete); the rest are proposals
 for him. Groups are rows with an id (natives + his own), a person or company may link agents, and a word of a
 person is never a card's alias (`widgets/aliases.py`). — since 2026-11-05 · nodes 2.1500, 2.1530, 2.1531, 2.1532,
 2.1533, 2.1551, 4.390 · `nucleo/memory_agent/contacts.py`, `memory/rem/contacts.py`, `widgets/contactos/groups.py`.
- **CRIT-M16 · The day is in the prompt's live tail, and recall reaches the conversation.** Every turn's live tail
 carries the day's EPISODES outside the live chain as a schema — when, what he opened with, the first reply, how it
 ended — under a fixed budget that drops the oldest first; a first-turn kickoff is the engine's words, never an
 episode. The live window and the day are cut by ONE silence: the window holds only the turns that chain to now, so
 a session after hours of silence starts with an empty window and the earlier session in the day. A reference to
 the conversation fires the recall; the recall reads the `conv` buffer beside the durable pills, his own words
 first, by relevance, without the live chain, his repeated attempts or more than two turns of one episode, and
 answers with the literal turns even when no pill matched; an order that needed the recalled fact is carried out.
 «I have no access to what was said earlier» is never the answer while the buffer holds it. — since 2026-11-09 ·
 nodes 2.1641, 2.1642, 2.1646, 2.1647 · `memory/_prompt/reads.py`,
 `memory/_prompt/compose.py`, `memory/history.py`.

- **CRIT-G1 · Only structured genes cross between agents.** A heritable gene is alias · route · nothing_serves · threshold (`genome/genes.py`) and passes the privacy filter (`genome/privacy.py`: a gene naming a known contact, an email, a phone, a URL, a number or a date is dropped); prose is never learned; a refused genesis reads as the last good generation; a new generation absorbs only what it ships identical and keeps what is his (V2-859 T563–T566) — since 2026-11-09 · nodes 2.1650, 2.1651, 2.1652, 2.1653 · `genome/`.

## 6 · Resilience

- **CRIT-M13 · His chats are people, linked by phone or email, found by every name.** The WhatsApp import reads the
 chat book (a linked device is told almost none of the phone's address book): a named one-to-one chat is a person,
 with its chat and when they last talked; a group, a feed or a number-only name is not. A `@lid` chat carries the
 phone its session mapping knows, so it joins the contact he already has by that phone, never by name; the name the
 chat shows rides on the channel (`directory.names`) and finds the person in the resolver, the people block, the
 contact record and the recipient check. A question about a first name many share answers «which one», closest
 three. — since 2026-11-04 · nodes 4.358, 2.1010 · `connectors/whatsapp/service/directory.py`,
 `connectors/whatsapp/bridge/bridge.js`, `widgets/directory.py`, `widgets/contactos/`.
- **CRIT-M14 · A podcast or a list plays ITSELF, never its namesake.** «Play X» asks the search service's media door (`search.media`) to compare his words with the NAME of every kind the connected catalogue answers (podcast, list, album, song — a song keeps a tie) and plays the whole they name by its uri where it can sound, else its OWN songs read by that uri (`music.play_whole`, the same rule a tap on the card takes); a podcast's episodes are never substituted — where only the provider's app can sound it and none is open, the answer is `needs_app` and nothing plays; a uri is never traded for a search of its name; a whole that could not sound is worded from what was found and why (`music_outcome`: its name, `needs_app` → open the app), never from the card's «now playing». — since 2026-11-07, rule of one door 2026-11-08 (V2-860 T2.1-T2.4, T4.1) · nodes 5.71, 3.177 · `search/media.py`, `connectors/music/__init__.py`, `widgets/musica/browse.py`.
- **CRIT-M15 · Two players, and a request names its candidates.** A start sounds on ONE of two players whatever the screen that asked: the connected provider's own app with that screen (the Spotify of THIS computer or phone), else our page player — never a device elsewhere (`music._choose`). The kind he names (song, list, album, podcast) rides `play_music.kind` to the media door, which prefers the best fit of that kind. A request said to the agent (play + words) opens the music card on its search, blank, and leaves there the numbered candidates with their owners and the one started; the open card's digest names them, «not this one» is answered from that list, and `play_result{item: number | name | owner}` picks one through the shared resolver (`widgets/result_refs.py`, the video card's too) — two rows carrying his words are asked, never guessed. A bare «open the music» leaves the card as it was. — since 2026-11-08 (V2-861) · nodes 5.72 · `connectors/music/__init__.py`, `search/media.py`, `widgets/musica/browse.py`. The same holds on every card that shows results he picks from: the results sheet's `choose` (by number or words, its real title kept), the file explorer (numbered rows, `open_file`/`open_folder` by number or name) and the gallery (a search's photos numbered in the digest) — node 5.73.
- **CRIT-R1 · A bug of ours is not a provider outage.** The exception decides (an HTTP status is theirs, a bare
 Python error is ours); the SAME request relays to the stand-in inside the connect loop; the panel names titular
 and stand-in, amber while the substitute serves. — since 2026-09-23 · nodes 2.77, 2.54, 4.27.
- **CRIT-R2 · The voice brain is a non-reasoner, model per invocation, and the provider order is
 CONFIGURATION** (`config/v2.json`, managed by the UI) — never a rule in a document. — since 2026-08-19 · nodes
 2.54.
- **CRIT-R3 · Embeddings have no failover model** (a stand-in answers in another vector space); the fall is made
 visible. — since 2026-09-23 · nodes 10.52.
- **CRIT-R4 · No language, no agent**: until the picker locks a language the agent is stopped; after ANY reset it
 comes up listening. — since 2026-09-24 · nodes 4.217, 8.4.
- **CRIT-R5 · The voice has a stand-in**: the models table's `tts.failover` is built beside the titular; a titular
 that cannot be built (no key) is replaced at boot, and LiveKit's `FallbackAdapter` switches on a synthesis that
 fails for good (a 402); the meter bills the provider that spoke. The ear has the same (`stt.failover`). Every
 switch alert names the titular's last ERROR (a socket of ours closed on silence must not pass for an outage); each
 STT/TTS metric is labelled and billed to the plugin that PRODUCED it; every provider the table can switch to has
 its own rate; an unused relay holds no audio back (its emitter is flushed per push); the voice process names who
 produced a metric before it crosses to the body; a voice marked down is probed with each stream's whole text, so a
 blip never keeps the stand-in for good; a provider that HANGS is bounded on its own clock (`relay_bound` in
 `config/resources.default.json`, shadow until the fleet's TTFB is measured). — since 2026-09-30, both
 families and the attribution since 2026-11-13 · nodes 2.202, 3.189, 3.231 · `voice/engine/speech/tts/__init__.py`,
 `voice/engine/speech/stt/__init__.py`, `voice/engine/speech/relay.py`, `voice/engine/speech/relay_bound.py`,
 `voice/engine/pipeline/metrics_tap.py`, `voice/engine/pipeline/child_session.py`.
- **CRIT-R6 · With `ZAELAR_USER_ID` set, no torrent client runs** unless `ZAELAR_TORRENT_IN_CLOUD=1` is also
 set; without it, the operator's switch decides. — since 2026-09-30 · nodes 5.61 · `connectors/torrent/service.py`.
- **CRIT-R7 · What leaves the machine is scrubbed.** The feedback evidence never carries `system` events (the
 forensic turn holds the whole prompt) and every string goes through one scrubber (vault detector + token
 shapes; a scrubber failure withholds, never passes); the full prompt capture is scrubbed, under the
 workspace, capped per session, and OFF when `ZAELAR_USER_ID` is set unless `ZAELAR_LOG_PROMPTS=1`. — since 2026-10-01 ·
 nodes 7.61 · `observability/scrub.py`, `server/feedback_api.py`, `voice/observer.py`.
- **CRIT-R34 · The server log wears the same mask as the stored events.** While his `obfuscate` switch is on, every
 loguru record passes `pii.tag` through ONE patcher installed at boot (`observability/log_mask.py`): an email, a phone,
 a known name leave as tags; off, the line is untouched; the masker never raises and never recurses. A phone, a date
 and a time are each read by their own shape (`observability/pii.py`): a date or a time is never a phone and a time or
 a small count is kept; a number said in groups (six digits or more, no ceiling) is a phone and a lone four-digit number is tagged — a
 year cannot be told from a PIN. — since 2026-11-11, shapes 2026-11-12 ·
 nodes 7.131, 2.1733 · `observability/log_mask.py`, `server/__main__.py`.
- **CRIT-R8 · Paid work asks the usage lease BEFORE it starts.** If a usage lease is configured and exhausted, a
 paid call is refused (`OutOfEnergy`, never a provider failure: no relay, no light), the fuse stops the agent, and
 the UI shows the exhausted state with a link to `ZAELAR_ACCOUNT_URL` when set; with no lease configured, every
 call is admitted. A boot probe never pays. — since 2026-10-22 · nodes 8.21, 4.247 · `nucleo/energy/lease.py::check`.
- **CRIT-R9 · A device that cannot capture or play is red on the orb, and said.** Each of the microphone and the
 speaker has ONE derived health (`store.micHealth` / `store.spkHealth`); a problem (no permission, dead or
 source-muted track, capture error, playback blocked or paused, remote track ended, output lost, the agent
 speaking with no received energy) paints its icon red with the reason in the title, is reported once as a
 `client` event, and clears by itself; a deliberate mute is never red except for a revoked permission.
 — since 2026-10-24 · nodes 3.119 · `frontend/app/services/device-health.js`.
- **CRIT-R10 · A spent lease is not an empty account.** Running the usage lease out — by amount or by clock — asks
 for another at once (bounded backoff) before any stop; only an answer carrying `ok: false` is a verdict (a 5xx,
 a timeout or a body without `ok` is a failed renewal). A stop carries its cause: `energy_denied` (the endpoint
 said no) is the only one told as an empty account with a top-up; `lease_unrenewed` says the agent could not
 confirm its Energy. The cause persists across a restart, boot asks for a fresh lease before any stop decision,
 and the notice never says «empty» next to a battery showing Energy. — since 2026-10-26 · nodes 8.25, 4.247 ·
 `nucleo/energy/lease.py::_renew_or_blow`, `frontend/app/core/account-link.js::noticeKind`.
- **CRIT-R11 · A worker we froze is not a silent provider.** The stall watchdog counts only time the worker's process
 RAN: while its backend is `paused` (the ⏻, the resource envelope, the self watchdog's shed — whoever froze it) the
 clock waits; released, silence counts again; an unreadable state keeps the clock. — since 2026-11-01 · nodes 3.164.
- **CRIT-R12 · Every event says what ran it.** At the stream's one gate (`stamp_identity`, which `bus.sse.publish`
 applies to every event, hand-built dicts included) each event gets `ver` = running build + commit — the commit
 baked into an image as the `ZAELAR_COMMIT` build arg, else the repository's HEAD — and `inst` = host, pid, boot
 second (+ region/image when the environment gives them), read once per process; nothing publishes on `observer`
 around the gate. — since 2026-11-02 · nodes 7.82 · `voice/observer.py::stamp_build`, `version.py`, `Dockerfile`.
- **CRIT-R13 · Every model call carries one usage shape** (`observability/usage.py`: model · provider · prompt /
 completion / cached tokens · prompt / reply chars · ms · ttft · finish_reason · outcome; no other names): each
 decision call and each read of it (+ `age_ms`, `nucleo/jev`), and each Brain Worker turn — once, on the call's own
 `model_call` row (since 2026-11-06; before, on the turn's first row). — since 2026-11-02 (rewritten 2026-11-21,
 INI-078 L1) · nodes 7.83, 7.94 · `nucleo/jev`, `nucleo/workers/session_events.py::_turn_usage`.
- **CRIT-R14 · A switch, a close and a pressure alert say why.** Every `run` event and every session end carry
 `cause` (the caller's, else the source that switched it) and `device` when a page sent it; every `alert` and
 `homeostasis` event carries one `pressure` block (RSS, free MB and ratio, live browsers and workers) stamped at
 the observer's door; the brief door emits `brief composed` with the brief's declared fields on every outcome.
 — since 2026-11-02 · nodes 7.84 · `nucleo/runstate.py::_emit`, `observability/pressure.py`,
 `nucleo/dispatch/brief_door.py`.
- **CRIT-R15 · Every navigation says what came back.** One listener on the browser context keeps each main-frame
 document's `status` (0 when the request failed), `ms`, declared `bytes` and `wall` (none · antibot · captcha · http,
 read through `walls.py`); the tab's next `screenshot` row carries it, once. — since 2026-11-02 · nodes 7.85 ·
 `widgets/navegador/page_outcome.py`.
- **CRIT-R16 · Every push through the results sheet's door is one `widget door` event**: handed, landed, the gate
 that turned each row away (every off row is tagged by its gate in `search/row_fit.split`; an untagged one is
 counted as `untagged`; read off the rows the gate files in Rejected, from `widgets/results/actions.py`), pages filed as sources, copies, rows past the cap and the pool. — since 2026-11-02 ·
 nodes 7.86 · `widgets/results/door_event.py`.
- **CRIT-R17 · Every row brings its picture, fetched only from the public web**: after a push is saved, a row whose template draws a photo with a `url` and no `image` gets the cover its page declares, and every remote picture is copied once into the results folder and served by `/widgets/results/asset/` (background, one fetch per page, public addresses only at every hop, pinned connection, byte cap, image types and signatures, no SVG); `offer`/`link` rows stay without one; the door event counts `no_picture`. — since 2026-11-02 · nodes 7.87, 7.88 · `widgets/results/media.py`, `search/public_fetch.py`.

- **CRIT-R18 · A held worker names its true reason.** Memory only while `admits` is false, the host while the body loop stalled within `loop_hold_s` for at least `loop_hold_min_s` in all (`waiting_host`: a paging host shows it in the loop, not in «available»; one short hiccup holds nothing, and a task resumed with his answer is never held for the host), the voice's shed as the voice, else what it queues behind; a shed names its source (`voice_loop` · `voice_audio` · `watchdog`) and ends when THAT source recovers, the seconds only a ceiling (V2-867 F0) — since 2026-11-09, narrowed 2026-11-17 · nodes 3.178 · `nucleo/workers/envelope.py`, `nucleo/dispatch/session.py`, `voice/lag.py`.
- **CRIT-R19 · Admission is a limit, not a delay.** A worker waits for room with no deadline start (the exit is his cancel) and is admitted one at a time, the next measured only once the previous runs; the floor is the deployment's own `free_floor` (V2-891, CRIT-R39): what its declared `pieces` need (ceilings + reserve), the ratio of the total only a CAP, never under the voice reserve — a block without `pieces`, and a policy without `budgets`, keep max(ratio × total, reserve); the host is SHORT under its `pressure_pieces` (+ reserve), capped by `pause_free_ratio` × total (2026-11-13: 20 % of a 48 GB laptop held every errand with 4.5 GB free); `max_parallel` is the ceiling (V2-867 F1) — since 2026-11-09 · nodes 3.178, 3.194 · `nucleo/workers/envelope.py`, `nucleo/dispatch/session.py`.
- **CRIT-R20 · A Chromium never launches outside the worker envelope.** Without room the newest running worker nobody else paused is paused first and resumed when room returns; room undoes only its own pauses; the operator's own window is never refused; the search browser waits like a worker through `search.hooks.room` (V2-867 F2) — since 2026-11-09 · nodes 3.179 · `nucleo/workers/room.py`.
- **CRIT-R41 · A remote browser is reached, never launched.** With `ZAELAR_BROWSER_CDP_URL` or `ZAELAR_BROWSER_LEASE=1` every browser consumer (the navigator, the search browser) connects over CDP and opens a fresh context; the engine launches no Chromium of its own, an unreachable endpoint is the named `RemoteBrowserUnavailable` (never a local fallback), the boot prewarm takes no browser, and a lease is renewed only when used. Nothing configured = local, unchanged (V2-918) — since 2026-11-16 · nodes 4.550 · `nucleo/remote_browser.py`.

- **CRIT-R21 · A LiveKit recycle never awaits the old worker unbounded.** The close is bounded and abandoned past `recycle_close_s`, the new worker is verified REGISTERED within `recycle_verify_s` and retried `recycle_attempts` times; a voice that stays dead `voice_dead_s` after a session was asked — counted from the FIRST ask it left unanswered, never re-stamped by a page that keeps asking (3.198) — is an alert plus a restart under a supervisor (self-host: retries and says so once); the cold-start window `boot_grace_s` is warm-up, never degradation (V2-871) — since 2026-11-09 · nodes 3.180, 3.198 · `nucleo/pulse/voice_recycle.py`, `nucleo/pulse/homeostasis.py`.
- **CRIT-R22 · «Voice on» is a live session, and a fresh session is never recycled.** The recycle guard reads `server.active.count` (a running `run_bot`), never the voice's index in `STATE`, and `safe_to_recycle` refuses within `session_grace_s` of the last session START whatever the timeline's mtime says (V2-872) — since 2026-11-10 · nodes 3.182 · `nucleo/pulse/homeostasis.py`, `nucleo/pulse/homeostasis_policy.py`, `server/active.py`.
- **CRIT-R23 · A starved CPU is not a dead worker.** Between two heartbeats the host's steal share (`/proc/stat`) over `steal_pct_starved`, or any cgroup throttling (`cpu.stat`), makes that window's LiveKit marks the host's: a `starved` event with the numbers, ONE on-screen notice per episode in his language, never a recycle; the pressure block carries `cpu_steal_pct` and `cpu_throttled_ms`, and a host without those files changes nothing (V2-872) — since 2026-11-10 · nodes 3.182 · `nucleo/pulse/starvation.py`, `observability/pressure.py`.
- **CRIT-R24 · A tab sleeps on its own and never reconnects without a gesture.** The browser never auto-reconnects the event stream: an error closes it, and `reconnectDecision` reopens it only while the tab is visible and a person touched it within `tab_sleep_min` (the stream's hello; 0 on an engine that never stops), with a 2 s → 60 s backoff; a hidden or untouched tab goes dormant, says so on the orb, sends no request until a gesture, and `engine.sleep` puts it to sleep (V2-872) — since 2026-11-10 · nodes 4.433, 2.830 · `frontend/app/services/presence.js`, `frontend/app/services/sse.js`, `nucleo/idle_stop.py`.
- **CRIT-R25 · Presence is a connected person; an engine woken for nothing stops in about a minute.** The idle stop counts a screen's input (a touch, a typed line, his turn) AND a visible tab with its stream open, which says so on open, on becoming visible and every minute (`voice/screens.present`, `POST /api/screens/beat {present}`) — never a stream open alone or a hidden/sleeping tab; until someone is present after boot or resume its window is `wake_grace_min` (1; `ZAELAR_WAKE_GRACE_MIN` overrides it), then the full `ZAELAR_IDLE_STOP_MIN` from the last presence or activity; workers and the next notice the engine can still FIRE keep their veto in both, and a job already past due at the check (⏻ held it) vetoes nothing (`nucleo/pulse/due.next_owed`); a widget's background tick is never real activity (`observability/identity.paced`) (V2-872) — since 2026-11-10 · nodes 2.830, 2.1658 · `nucleo/idle_stop.py`, `voice/screens.py`, `server/screens_api.py`, `widgets/background.py`.
- **CRIT-R25c · Nobody wakes the agent to leave it stopped.** The server keeps the ⏻ across a sleep and a resume
 (`nucleo/runstate.py`, persisted) and every page REFLECTS it — at boot and on coming back (`presence.reflectRunState`) —
 and never sends one: a stale «stopped» in a page's storage follows a running agent. Only a press stops it
 (`power.setPower` is the one client caller of `runStop`); an agent stopped on purpose stays stopped and still needs ⏻
 (INI-042 #46) — since 2026-11-19 · nodes 4.598 · `frontend/app/main.js`, `frontend/mobile/app/main.js`.
- **CRIT-R25d · A phone back from the background runs the new screen.** A page knows it runs an older frontend when
 `GET /api/update` answers another `ui_rev` than its first answer (V2-553); the desktop shows the reload bar, and the
 phone shell (`watch.reloadOnReturn`) reloads at once when it comes back to the foreground onto a newer one — nothing
 is in his hand then; the same frontend reloads nothing — since 2026-11-19 · nodes 4.600 · `frontend/app/update/watch.js`.
- **CRIT-R25b · The app on his phone is opened by a person, and leaving it is said.** In the native companion or a
 page installed on a PHONE's home screen (never a standalone window on a computer), coming to the foreground is a
 gesture (`presence.js::installedApp`); with music sounding in the page, putting it away is not leaving; it counts as
 input, wakes a sleeping tab and reopens its stream with `wake=1`, with nothing to press. Putting the app away says
 the person left (`POST /api/screens/beat {left}` → `screens.left`), and with no other screen on and no voice session
 open the idle stop counts its short `wake_grace_min` from that moment; a worker running or a notice due keeps its
 veto. Inside the native companion the shell leaves a hint cookie (`zaelar_app=1`) a deployment's edge may read. A
 browser tab coming to the foreground is still not a person (R24, R25). — since 2026-11-16 · nodes 4.553 ·
 `frontend/app/services/presence.js`, `voice/screens.py`, `nucleo/idle_stop.py`, `server/screens_api.py`.
- **CRIT-R26 · Nothing at boot starts the Chromium on a host that stops when idle.** `prewarm_browser` decides the search browser's warm-up (a declared value wins; undeclared, it is false under `ZAELAR_IDLE_STOP_MIN`), the first search starts the browser itself, the boot status probe leaves the browser rows `unprobed` while it is down, and loading the video card issues no search (V2-872) — since 2026-11-10 · nodes 3.183 · `nucleo/llm/prewarm.py`, `search/api.py`, `search/browser.py`.
- **CRIT-R27 · A passive tick follows presence.** With a screen open (or `background.always`) a passive widget keeps its declared cadence; with none it ticks at most every `background_idle_every_s`, the first tick a full idle period after boot; reminders are scheduler jobs and never depend on the tick (V2-872) — since 2026-11-10 · nodes 3.183 · `widgets/background.py`, `widgets/validator_actions.py`.
- **CRIT-R28 · An open the tab decided says it is a person.** Every event-stream open that `presence.js` decides (the first gesture on a sleeping tab, a retry while someone is there) carries `wake=1`; the boot open and a browser's own retry never do. The engine counts it as input (`voice/screens.touched`), so the unattended-wake grace ends with it; a hosted deployment's edge may start a stopped engine for a navigation or for this mark and for nothing else (V2-872) — since 2026-11-10 · nodes 4.433 · `frontend/app/services/presence.js`, `frontend/app/services/sse.js`, `server/voice_api.py`.
- **CRIT-R29 · A sleeping engine is woken for one instant, and listens only when something reacts.** The wake report is the earliest of the scheduler's next job, the pulse's own deadlines ahead of now (an errand's `expires_at`, a waiting row's `deadline`, an owed notice's retry when a device can take it) and — only while a connected channel that can be caught up (email, WhatsApp, Telegram; never a cluster, which keeps no backlog) has something reacting to it (a subscribed rule or an unread note that could subscribe, a row waiting for its event, a live errand's conversation, his notify or autoresponder preference) — the next pass on a `listen_every_min` grid; with none, `null`. The default triage alone is not a listener. The report goes stale by itself when its instant passes and every `_RECHECK_S` (V2-872 F2) — since 2026-11-10 · nodes 2.841 · `nucleo/pulse/wake.py`, `nucleo/pulse/listeners.py`, `nucleo/pulse/deadlines.py`.
- **CRIT-R33 · A voice room is given only once this engine's worker is registered, and the page is ready only with
 the agent in it.** `/api/token` answers 503 `voice_starting` while the embedded worker has no LiveKit id (a room born
 before it is never dispatched an agent); the page waits and asks again, leaves a room no agent joined within its
 bound and asks for a new one, and never says «ready» without the agent. — since 2026-11-10 (V2-873) · nodes 3.185 ·
 `nucleo/pulse/voice_recycle.py`, `server/livekit_api.py`, `frontend/app/services/voice-arrival.js`.
- **CRIT-R30 · An arrival is dealt with once, across processes.** The mailbox keeps a durable cursor (`UIDVALIDITY` + highest UID dealt with, trailing delivery by a poll): a new process hands over only what arrived since, asleep or not, and a renumbered folder voids it; the messaging widget asks its durable `taken` ledger BEFORE the classifier; the event router routes `<platform>:<chat>:<message>` once, so a re-delivery resumes no row and runs no rule twice. A series' notice hands over to the next occurrence right after it rings (the pulse runs `scheduler.AFTER_RUNG`) and at start (V2-872 F2) — since 2026-11-10 · nodes 2.842, 2.843 · `connectors/email/cursor.py`, `widgets/mensajeria/owner/apply.py`, `nucleo/events/once.py`, `widgets/agenda/reminders.py`.
- **CRIT-R31 · An idle engine asks to be suspended, and a resume is never a failure.** The stop flushes the wake report first (a report that fails keeps the engine up and retries in `WAKE_RETRY_S`), says goodnight (`engine.sleep`), then POSTs the sleep endpoint (`ZAELAR_SLEEP_URL`, else `CONTROL_PLANE_URL`/sleep with the service token): 202 waits `SLEEP_CONFIRM_S` to be suspended and exits cleanly if it was not, 200 is a resume already, anything else or no answer is the clean exit; every one of those decisions is taken on the pulse AFTER it looked for a resume (wall vs monotonic skew, or a long gap once a sleep was asked), and a resume starts the idle state over (the short grace again), marks the wake report stale and publishes `engine.resumed` (a system event); with no endpoint it is the clean exit, as before — since 2026-11-10 · nodes 2.1658 · `nucleo/idle_stop.py` (the decision), `nucleo/suspend.py` (the sleep and the resume), `nucleo/pulse/loop.py`, `nucleo/pulse/wake.py`.
- **CRIT-R31b · The loader moves on its own thread, from the first byte, and its words never cover it on a phone.**
 `core/preboot.js` starts the loader's animation in a worker on an OffscreenCanvas (`core/boot-worker.js`) before any
 module exists; `components/boot-anim.js` takes its size, colours and frame clock as an `env`, so it runs with no page
 and keeps moving while the page's thread loads the agent; `BootOverlay` drives that same animation (a browser without
 OffscreenCanvas draws on the page as before). On every screen — phone or desktop — the words live in a band at the
 foot (`CAPTION_BAND`) and the drawing in the screen above it. — since 2026-11-16 · nodes 4.554.
- **CRIT-R32 · One veil, one face, one press.** The screen is covered by ONE veil (`Veil.js`, both shells) whenever this screen cannot use the agent, with one face at a time by priority: stopped by him (`off`/`pausing`) over the engine's sleep (`engine.sleep`) over `starting` over the voice held by another screen (`moved`, with «use it here» and «continue here with text»); its one button wakes the engine (a gesture, so the stream reopens with `wake=1`), switches the agent on and claims the voice here — never two presses (V2-881) — since 2026-11-10, one veil since 2026-11-11 · nodes 4.434, 4.481 · `frontend/app/components/Veil.js`, `frontend/app/services/presence.js`, `frontend/app/services/power.js`.
- **CRIT-R32b · Stopped shades the whole width.** While the agent is stopped or in transit the docked chat wears the
 veil's own shade (a layer that takes its clicks) and the veil's box is centred in the window; the bottom rail and
 the top bar stay usable (the ⏻ is there). Asleep and «moved» are black over everything, the chat included.
 — since 2026-11-16 · nodes 4.555 · `frontend/app/core/shared-surfaces.css`.
- **CRIT-R36 · The voice runs in its own process; the body answers it over loopback.** `python -m voice.engine`
 (LiveKit, the VAD, the ear, the mouth; none of the brain); asked to embed it (`ZAELAR_VOICE_EMBEDDED=1`) the body
 refuses and says so (`server/boot/surfaces.voice_worker`). The body spawns it with a per-spawn token and its own pid,
 watches it like the embedded worker (`id`/`_closed`/`_connecting`) and its doors (`/api/voice/child/*`,
 `/api/turn/stream`) answer only that token from loopback. The conversation is the manager's: his words reach it
 through its ear (`conversation_host/ear_in`) and its lines are said through the voice's `/voice/say`
 (`conversation_host/voice_mouth`); a turn LiveKit still asks of the body (`/api/turn/stream`, NDJSON) replays the
 facts it carried and ends with nothing said (`remote_session.turn_lines`). The session's facts reach the body in
 order through one sender that drops a late batch instead of waiting and retries a session's start/close once; a
 request that must follow them takes the facts still queued and carries them (`body_link.ahead`; `back` when it never
 arrived) — the order is the request's own, never a wait on the sender; they are replayed through the SAME
 `agent_events` handlers against a session that answers over HTTP; what the body asks (say, reply to a typed line with
 the screen that typed it, mute, open/close the ear, clear a discarded turn, re-point the voice, close) goes to the
 voice's control routes. The ear's windows keep a p99 ≤ 50 ms while the body writes 1.5 GB and holds its interpreter
 (V2-891). A body it cannot reach is tried ONCE more a second later, then he hears «it's running slow» (i18n
 `brain_slow`), never «say that again», and his line rides the next turn as `prior`; while the body does not answer
 the sender opens at most one connection per `RETRY_GAP_S`, retrying transcripts and items at the front of the queue —
 never a new connection per batch. — since 2026-11-12 (rewritten 2026-11-21, INI-078 L1) · nodes 3.190, 3.191, 3.203 ·
 `voice/engine/pipeline/child.py`, `voice/engine/pipeline/child_session.py`, `voice/engine/pipeline/body_link.py`,
 `voice/engine/pipeline/remote_brain.py`, `voice/remote_session.py`, `voice/child_process.py`,
 `server/voice_child_api.py`.
- **CRIT-R37 · A read never waits on a LOCAL embedding past `embed_budget_ms`.** A local embedder (Ollama, fastembed) slower than the budget (300 ms) leaves the read to the lexical channel and says so; the abandoned embedding runs in a bounded pool; a remote embedder is bounded by the turn's own recall budget (V2-891) — since 2026-11-12 · nodes 3.192 · `memory/retriever/recall.py`.
- **CRIT-R38 · The engine gives memory back by a declared ladder.** Under pressure (free under the PRESSURE floor — `envelope.pressure_band`, the band the watchdog opens and closes on, never the admission floor — or the voice's lag or the body's own loop lag over its bound) the rungs of `shed_ladder` engage in order, one per heartbeat, whoever is short (`cause` engine|machine said, never a reason to stand still); recovered past the band's top (pressure floor × `pressure_band_ratio`, never over the admission floor) they release in reverse, one per heartbeat; every rung has a hand that undoes only its own (V2-891) — since 2026-11-12 · nodes 3.193, 3.201 · `nucleo/pulse/shed_ladder.py`, `nucleo/pulse/shed_actuators.py`, `widgets/background.py`.
- **CRIT-R39 · Budgets and priorities are data per deployment.** `budgets.{local,cloud}` declare the voice, the body, a worker and the browser (`mb`, `ceiling_mb`) and the free floor; `priorities` the nice and OOM score per role (a worker at an ABSOLUTE nice); an actuator reports what the host allowed and never raises; the voice's own process over its ceiling is recycled only BETWEEN sessions (V2-891) — since 2026-11-12 · nodes 3.194 · `nucleo/pulse/budgets.py`, `nucleo/pulse/priority.py`, `nucleo/workers/envelope.py`, `nucleo/pulse/voice_recycle.py`.
- **CRIT-R40 · A stalled host is not a stalled provider: the body measures its own loop.** A probe on the server loop
 (`nucleo/pulse/loop_lag.py`) reads every late wake; over `loop_lag_s` (declared beside the envelope) it is a STALL —
 recorded with its end, one `homeostasis` event «host stalled N s», a quiet shed (never a spoken line) and pressure
 for the ladder (R38), by origin (host · engine · unknown, `pulse/shed_actuators`); `GET /api/debug/loop` answers from
 the process. A host that stalled holds new workers until its loop runs again (`workers/envelope.host_stalled`), never
 blamed on a provider. Heavy work in a thread gives way every N rows and paces itself while the loop stalls
 (`loop_lag.give_way`). — since 2026-11-12 (rewritten 2026-11-21, INI-078 L1) · nodes 3.201, 3.202, 3.204 ·
 `nucleo/pulse/loop_lag.py`, `nucleo/workers/envelope.py`.
- **CRIT-R35 · A cluster wakes the brain only for what its subscription attends to.** Every subscription carries `attention` flags (`addressed_to_me`, `general_messages`, `generated_content`), written with the defaults of its kind whenever it is saved and migrated at boot: a public cluster attends only to messages addressed to us (`to` set; a broadcast arrives with `to: null`), a private one to everything. `_brain_turn(kind=…)` asks `attention.wakes` before opening anything; an unattended message is journaled and shown and touches no other state; a cluster is engaged by being subscribed or connected only with general attention, so the heartbeat never nudges a public one on its own — since 2026-11-11 · nodes 2.1707 · `connectors/meshkore/attention.py`, `connectors/meshkore/store.py`.

## 7 · Working here

- **CRIT-W1 · Mechanisms, not rules.** A change that bounds a CONSEQUENCE stays; one that bounds JUDGEMENT is
 removed; a sentence about how to behave is a rail — delete it and find the mechanism it stood for. — since
 2026-09-15 · nodes 7.32 · `.meshkore/context/principles.md`.
- **CRIT-W2 · English everywhere inside `engine/`** — code, tests, logs, docs, commits; product data in the
 user's language; the module logs in the operator's; Castilian comment lines only shrink. — since 2026-10-01 ·
 nodes 7.60.
- **CRIT-W3 · Never restart with someone inside or an errand alive** (recent `transcript`/`brain` events, or a
 non-empty `/api/tasks`). — since 2026-09-15 · ⚠ sin test.
- **CRIT-W4 · Commit with pathspec after `git diff --cached --name-only` is empty; push after every commit;
 never rewrite pushed `main` for an attribution; never touch another session's uncommitted work.** — since
 2026-08-20 · ⚠ sin test.
- **CRIT-W5 · A wide pass runs under `tests/watchdog.py`, never bare `pytest`**; while iterating, the touched
 file and its DISARM; a test is not a test until seen red; a disarm that stays green accuses the TEST; the
 harness clears `__pycache__` on restore. — since 2026-09-20 · nodes 7.53.
- **CRIT-W6 · A test never touches the operator's real state** (the root `conftest.py` sandbox, which pins
 `ZAELAR_WORKSPACE` and fails BY NAME the test after which his consent/style/library config changed); a red that
 does not reproduce alone is contamination, not a bug; no real identity sits in a tracked file; every connector token store follows
 `ZAELAR_WORKSPACE`, so an isolated engine never holds his tokens. — since 2026-09-30 · nodes 3.94, 3.115, 7.10, 7.55.
- **CRIT-W7 · A test outside the map does not exist**; every mechanism ships with its node; a node whose file is
 gone is red, and a file answers one deterministic node. — since 2026-09-30 · nodes 7.32, 7.56.
- **CRIT-W8 · Public and private.** `engine/` describes mechanism, never product; development history and
 planning are not published (planning notes, module logs, test reports stay local and untracked). — since 2026-10-01 · nodes 7.60.
- **CRIT-W10 · Fix the class, never the case.** A red test or a judge finding is the SYMPTOM of a class; the fix is
 named by the class it closes and its test carries a variant the failing case did not (the other language, a reworded
 request, another domain). Never: a word, regex or literal so one recorded case passes; a test id or a fixture's
 string in product code; an assertion weakened to go green (it changes only when the behaviour changed on purpose,
 said in the commit); a ratchet ceiling raised. Reach, in order: a decision already made (the model's own call, a
 declared answer) → a declared datum (manifest, worker brief, catalogue) → a structure (one door, one reader) →
 language data in `i18n/`. Too big for the batch: the test stays RED and the class is tracked as open work — an honest
 red beats a patched green. Product regexes and word tables only shrink. — since 2026-10-19 (rewritten 2026-11-21,
 INI-078 L1) · nodes 7.73 · `.meshkore/context/principles.md` §«Fix the class».
- **CRIT-W9 · Closing a batch:** the node in the map, the WHY in the diary, the operator's words in the module
 log — and a line HERE only when a rule changed. — since 2026-09-29 · ⚠ sin test.

---

## 8 · Search — the service

- **CRIT-S1 · A row on the results sheet is a CANDIDATE or the PAGE that lists candidates, never both.** A
 candidate names one thing and carries a datum of its own (price, rating, its own phone, a fact); a row without one
 whose title counts or ranks a category, or whose url is an article/policy page, goes to Sources with its reason
 and the reply says so. Applied once, at `present`/`append`. — since 2026-10-10 · nodes 12.1 · `search/candidacy.py`.
- **CRIT-S2 · A criterion NO row can show is said missing, never implied met.** When every row carries only a name
 and a link, the sheet's digest and `find.unshown` name the asked criteria (rating, availability, price) as not
 found. — since 2026-10-10 · nodes 12.2.
- **CRIT-S3 · The number the operator said is his; none said is undeclared.** «Las tres mejores» is three, «ponme
 veinte» twenty, «el mejor» one; an article («un piso», «a flat») and a vague quantity («a couple», «some») are no
 number, so the route carries `n_final: None` and its consumer names no number. No floor, no default, nothing about
 how many to evaluate; the research brief's breadth is the composer's (CRIT-S11). — since 2026-10-10, narrowed
 2026-11-02 · nodes 12.3, 12.8, 12.840 · `search/criteria.py`.
- **CRIT-S4 · ONE place says which search module a request goes to, and no verb table decides it.** In the
 conversation the model picks it among its DECLARED tools (`web_search` for a fact, `search_listings` for listings,
 `show_images`, `start_task` for a deep search: `conversation_host/declared.json`). `search/route.search_route` keeps
 the precedence for a caller that hands it answers (a sure `search_module` answer → the model's named tool → an unsure
 answer → escalate + surface → default fact), pure and without network; nothing in the product calls it today, and the
 routing bank measures it. — since 2026-10-10 (rewritten 2026-11-21, INI-078 L1) · nodes 12.4, 12.8 ·
 `search/route.py`.
- **CRIT-S5 · Every search provider is declared once, probed with one minimal real call, and reported by key
 NAME**: live · missing · exhausted · blocked · credential; a missing key is missing, never down. The use-case
 harness does not grade a batch when no provider can answer (exit 4, INFRA); the status panel shows the last probe
 and never probes on a poll. — since 2026-10-10 · nodes 12.5, 12.6, 12.9 · `search/providers/`, `search/health.py`.
- **CRIT-S14 · Reading a page has one door, `scrape.read`** — a plain GET, then the unlocker on a wall or an empty page;
 the listings read from what the page declares or carries in its script state, found by the shape of the values,
 the site's field map kept as data; one validator. `scrape/` imports none of the engine it serves. — since 2026-11-04 ·
 nodes 12.845, 12.846, 12.847, 12.848.
- **CRIT-S7 · A worker searches with `act use_tool "<query>"`** — a quoted sentence, no JSON, no file: the one form
 the confinement guard lets through — and gets the service's answer (chain dict + route + candidates + pages +
 unshown). The two fact doors of the turn call `find` too. An ADDRESS in the same form (`act use_tool
 "https://…"`) is a page READ through `scrape.read` (since 2026-11-04). No backend keeps a web tool of its own
 (Claude Code's WebSearch/WebFetch, Grok's `web_search`, Codex's native search are off), and what either door
 returns comes back neutralised under one label, `untrusted.fence_tree`. — since 2026-10-10 · nodes 12.9, 12.849
- **CRIT-S6 · The search service owes the conversation nothing.** `search/` imports, from `nucleo`, only the leaf
 helpers the whole engine shares (errors, workspace, the energy meter, lease and egress, the remote browser), and
 never `voice`, `widgets`, `server`, `memory`, `connectors` or `frontend`; what it needs from the host (status light,
 timeline) are hooks set at boot; the old `nucleo.*` import paths are aliases of the same modules. — since 2026-10-10
 (rewritten 2026-11-21, INI-078 L1) · nodes 12.8 · `search/hooks.py`.

- **CRIT-S8 · What he rules out is a DECLARED name, and a subject is his words or the brief's list.** An exclusion
 reaches the sheet as `criteria.excluded` (structured, accumulated by the `criteria` op) and rejects every row that
 names it in its title, subtitle, facts or link; a declared exclusion is never a subject. A criteria change is the
 turn's paraphrase: it adds specs, ceilings and ruled-out words, never a subject read from its capitals. A card on
 screen shows the turn the payload keys of its actions that declare a field contract (`how`), so the model composing the op sees `excluded`. A STANDING rule that
 rules something out is shaped once, by the shaping model, into a `rules` row `excluded: [names]` at the `search`
 scope (rows add up; anywhere else it stays a note); the sheet's door reads the rules active on its path on every
 present, append and recheck — a rule from an earlier session reaches a clean search, the sheet on screen meets it
 when written — and its rejected rows say «your rule: …». No negation verb is added to a word table for this.
 — since 2026-11-02 · nodes 12.835, 12.838 · `search/category.py`, `widgets/results/category_gate.py`,
 `rules/shape.py`, `widgets/brief.py`.

- **CRIT-S9 · A row's identity is its page, and an amount is a number that ends in a digit.** Two rows are the same
 item when they share a model code under one brand, or the whole title and price on the same page (host and path; the
 query is how a list was walked); another ad page is another item. A separator left dangling («44. €») is a list
 ordinal, never an amount. — since 2026-11-02 · nodes 12.836 · `search/row_dedupe.py`, `search/candidacy.py`.

- **CRIT-S10 · The results list is a selection; the hunt's candidates are its pool.** Every row that passes the door
 stays in `pool`; a `present` sets which of them the list shows and in what order, never deletes the rest; «more»
 starts from the pool (`append {from_pool: n}`, through the same door), and a correction rules rows out of the pool
 too. An explicit empty `present` is a search that found nothing and empties both. — since 2026-11-02 · nodes 12.837
 · `widgets/results/actions.py`.

- **CRIT-S11 · Breadth is the composer's, and the harness asks whether it was enough.** The brief's
 `breadth.min_candidates` and `deliverable.n_final` are what its composer reasoned for that request and market — no
 floor, no default count, a number he said wins; caps only for cost (candidates) and sheet size (rows shown) — and the brief names the market (country, category) and its candidate `sources`; discovery
 carries the market. When a research errand ends short of its brief's target, ONE model question (brief + progress +
 sources used) answers «enough? · why · next · more sources»: not enough → one more round of the SAME errand within
 `circuit.retries`; enough, or the budget spent → delivered with the reason on the sheet's summary; the model fails →
 delivered «not judged». Delivery is never blocked. — since 2026-11-02 · nodes 12.840 · `nucleo/circuit/breadth.py`.
- **CRIT-S12 · A correction on a finished search reopens that errand.** A `criteria` change on a sheet whose errand is
 finished is written into its brief and re-checked: already held → nothing moves; new → the same errand relaunches
 as a continuation on its sheet (pool, rejected, sources kept), the worker judging each row by its own facts. Every
 correction does it again. — since 2026-11-02 · nodes 12.840 · `nucleo/circuit/reopen.py`.
- **CRIT-S13 · Media first, after the information.** The worker's brief says that, after what was asked for, the
 candidate's photo, video or graphic goes in the row wherever it exists. — since 2026-11-02 · nodes 12.840 ·
 `nucleo/workers/prompts/research.py`.

- **CRIT-S17 · An errand is bound to its row.** Every errand-scoped store (the brief first) is keyed by `runtime_ids.errand_key` — the row id, else the boot-stamped id — never the per-boot `task_id`; a brief names its errand and the judge refuses a stranger's, never relaunching blind; a relaunch reuses a brief only for the resumed row (V2-868 D1–D2) — since 2026-11-09 · nodes 2.1654, 2.1655 · `nucleo/workers/brief_store.py`, `nucleo/circuit/breadth.py`.
- **CRIT-S18 · A sign-in it cannot do is a wait, not a result.** `awaiting_login` / `blocked` parks the errand on one question through the asker, stops its worker and writes nothing to a sheet; the same row resumes on a confirmed sign-in; on the phone the line says to open the agent on a computer; «not a research» owes no results contract (V2-868 D3) — since 2026-11-09 · nodes 2.1656 · `nucleo/request/sign_in_wait.py`.
- **CRIT-S19 · A result says where it was found.** A worker's row that states data needs a url or a source the sheet knows, else it lands in Rejected with its reason (V2-868 D4) — since 2026-11-09 · nodes 4.416 · `widgets/results/provenance.py`.

## 9 · The conversation and turn manager (`conversation/`, isolated — F0)

These hold for the package; the engine does not run it yet (V2-941 F1 wires it).

- **CRIT-CT1 · One arbiter closes an intervention**: the provider's end of turn with every word final and the
 watermark past the voice's fall, or the cap after the fall (or after the provider's end); an eager hint never closes
 one, a stalled stream makes it `incomplete`, never actionable. — since 2026-11-19 · nodes 13.3, 13.4, 13.27 ·
 `conversation/ear/arbiter.py`.
- **CRIT-CT2 · A closed intervention reopens only within `reopen_window_ms` of its close, never once sealed or once
 its request is final**; later voice is a new intervention (amending the previous one when we have not spoken since).
 — since 2026-11-19 · nodes 13.5, 13.27 · `conversation/gateway/seal.py`.
- **CRIT-CT3 · Every accepted envelope ends accounted and every request closes exactly once within its liveness**;
 what must be told is said even when the model is down (one retry, then the language's last-resort line, worded by
 the adapter). — since 2026-11-19 · nodes 13.6, 13.9, 13.22.
- **CRIT-CT4 · Nothing leaves without the person's authority or a mandate**: a read passes, a write rests on a batch
 that is all the person's or on a confirmed handle, a delegation or a grant; an effect is reserved, sealed and
 recorded before the provider is called and an unknown outcome is reconciled by looking, never resent; an act held
 while the person speaks waits for that voice. — since 2026-11-19 · nodes 13.32, 13.33, 13.23 ·
 `conversation/gateway/`.
- **CRIT-CT5 · What the person heard is what a device acknowledged**: a line with no acknowledgement is «heard:
 unknown» to the model, never heard. — since 2026-11-19 · nodes 13.16.
- **CRIT-CT6 · Never silence**: every request of his is answered, told the language's «I lost that» in place, or owed
 it; a step with no order is asked for it once, a run never ends with his request open, and half a thought whose
 rest never came gets «go on, I'm listening» once. — since 2026-11-20 · nodes 13.88, 13.103, 13.110.
- **CRIT-CT7 · A figure rests on evidence still valid**: a read of this conversation or his own words, never a line
 of ours; a derived figure cites every evidence its operands are in and its result is the operation's, rounded,
 never read in another scale. — since 2026-11-20 · nodes 13.42, 13.106, 13.108.
- **CRIT-CT8 · In front of the ear**: the guards judge at every close; our own echo is decided by timing and by its
 words being ours, and never cuts our line; his stop is a control and never a line for the model (the old path's
 voice cut by a typed line went with the unplug, 2026-11-21). — since 2026-11-20 · nodes 13.91.
- **CRIT-CT9 · A run reads and acts within its budget**: past `max_reads` or `read_wall_ms` every read is refused with
 the reason to answer with what it has; on the run's last step (`max_steps`) every call is refused the same way
 (`STEPS_DONE`), so a run that spends its steps ends with the model's answer, not the host's «part was done»
 (`lost_after_acts`, which states the fact and offers no continuation); the catalogue is never cut. — since
 2026-11-20, the steps since 2026-11-21 (INI-078) · nodes 13.107.

## Contradicciones (contradictions — this table must stay empty)

| topic | rule A | rule B | winner |
|---|---|---|---|
