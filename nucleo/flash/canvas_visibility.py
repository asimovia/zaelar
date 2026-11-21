"""Moved to `nucleo.acts.visibility` (INI-078 F2 step 8): this name is the same module until the engine restarts."""
import sys

import nucleo.acts.visibility as _moved

sys.modules[__name__] = _moved
