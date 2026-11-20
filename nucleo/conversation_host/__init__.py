"""The host of the conversation & turn manager (V2-941): the engine side of the `conversation` package's ports.

  store.py    the `Store` port over `zaelar.db` (`memory.api.conv`, the `conv_*` tables)
  runtime.py  the conversation's own thread and event loop: its one writer, and the hourly prune
  clock.py    the `Clock` port on the machine's time

Nothing of the engine imports this package while the conversation is switched off.
"""
