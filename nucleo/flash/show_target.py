"""Moved to `nucleo.acts.show_target` (INI-078 F2 step 8): this name is the same module until the engine restarts."""
import sys

import nucleo.acts.show_target as _moved

sys.modules[__name__] = _moved
