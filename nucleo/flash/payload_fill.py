"""Moved to `nucleo.acts.payload_fill` (INI-078 F2 step 8): this name is the same module until the engine restarts."""
import sys

import nucleo.acts.payload_fill as _moved

sys.modules[__name__] = _moved
