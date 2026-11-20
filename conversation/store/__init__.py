"""The `Store` port's double: in memory, for the package's own tests. The one implementation over sqlite is the
engine's (`nucleo/conversation_host/store.py`, the `conv_*` rows of `zaelar.db`); both pass the same contract battery
(node 13.19)."""
from conversation.store.memory import MemoryStore as MemoryStore

