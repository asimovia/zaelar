"""Two implementations of the `Store` port with one contract (node 13.19): in memory for fast tests, sqlite in a file
of its own as the reference adapter. Any production adapter passes the same battery."""
from conversation.store.memory import MemoryStore as MemoryStore
from conversation.store.sqlite import SqliteStore as SqliteStore

