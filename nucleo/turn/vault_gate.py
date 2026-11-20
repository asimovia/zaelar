"""Moved to `memory.vault.gate` (INI-078 F2 step 8): this name is the same module until the engine restarts."""
import sys

import memory.vault.gate as _moved

sys.modules[__name__] = _moved
