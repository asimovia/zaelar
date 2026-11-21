"""The host of the conversation & turn manager (V2-941): the engine side of the `conversation` package's ports.

  store.py    the `Store` port over `zaelar.db` (`memory.api.conv`, the `conv_*` tables)
  runtime.py  the conversation's own thread and event loop: its one writer, and the hourly prune
  clock.py    the `Clock` port on the machine's time
  switch.py   does this session go by the manager: session > account > environment, failing closed
  sessions.py one `Conversation` per account, in its runtime, while a switched session holds it
  config.py   the account's `Config` from the genome, refused out of bounds or out of order; the `Prefs` port
  proof.py    who opened the turns of a switched session, and the exit gate over it
  model.py    the `Model` port over the engine's fast client: the voice's model, its two orders as tools
  prefix.py   the model's stable prefix: declared lines only (language, reads, acts, the orders' fields)
  tools_read.py the `Tools` port of a switched session: reads only, each class derived, each result with its evidence
  figures.py  the figures a tool's output carries, as numbers: what a text evidence holds
  memory_read.py the `Memory` port: the state the way the rest of the engine reads it, writing nothing
  record.py   the `Record` port: each answered pair in the engine's `kind='conv'` record
  telemetry.py the `Telemetry` port: every event to the engine's observer (a relay on the architecture map)
  mouth.py    the `Mouth` port, its text half: a line on the chat wall, acknowledged as shown
  boot.py     the account's conversation, built with the engine's ports, in its own thread
  entry.py    the funnel: a typed line of a switched session enters here, with the guards every entry shares
  wall_notes.py the engine's other lines on the chat wall: a notice's 🔔 line, a record line, an errand's box
  owed.py     the `Owed` port: the lines claimed for the manager's voice in the one ledger, `notices`

Nothing of the engine imports this package while the conversation is switched off.
"""
