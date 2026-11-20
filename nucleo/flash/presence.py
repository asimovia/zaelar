"""Moved to `nucleo.self.presence` (INI-078 F2 step 8): this name is the same module until the engine restarts."""
import sys

import nucleo.self.presence as _moved

sys.modules[__name__] = _moved
