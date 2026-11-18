"""nucleo/send — the ONE owner of «send a message to somebody», from his words to the connector's receipt.

Measured on his engine for three weeks (2026-10-28 → 2026-11-18): a send had no owner. Its decisions were spread over
the attention, a switchboard that routed his words into a background worker, the worker itself, verdicts, the fast
model's own tool calls and prose questions, an ask-outside-the-door row, the exit door and the receipt watcher — about
two dozen points, each able to ask, veto or claim the send. The same morning a disambiguation he answered launched a
worker with nobody chosen, every following sentence («that's not it», «which Raquels do you have?», «why so slow?»)
was swallowed by that worker with «got it», and the message never left.

Now ONE module owns a send, synchronously, inside the conversation:

  · `owner.intake` — the turn hands it his words (and the model's call, as a hint) and nothing else: the fast model
    never asks about a send, never resolves who it goes to and never says it went;
  · `draft` — the ONE state of the send: who he said, who it resolves to (or the people it could be), the text, what
    it last asked him;
  · `read` — ONE model read of each sentence he says while a draft is open, against that draft: is it about this
    message (who, what it says, send it, drop it, which people he has by that name) — and if so, the whole new state;
  · `people` — who a said name is: the conversation he has open first, then his contacts ranked
    (`widgets/contactos/who`). Several or partial is a question with names, never a pick;
  · `owner.take` — at the turn's gate, BEFORE anything else routes his words: a sentence about the draft is the
    owner's (it answers at once, in one line); anything else is NOT, and the conversation answers it as always.
    A sentence is never swallowed: an unreadable read is the conversation's;
  · the send — on his explicit yes only — through the messaging card's own act with the person's row id, then
    followed to the connector's receipt; the final line is the receipt's.

Every line he hears from a send is the owner's, worded from a fact (`nucleo/wording.py`), and every step is one
`send` event on the timeline with the draft as it stands.
"""
