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

Nothing of the engine imports this package while the conversation is switched off.
"""
