"""Moved to `widgets.navegador.live_lines` (INI-078 F2 step 8): this name is the same module until the engine restarts."""
import sys

import widgets.navegador.live_lines as _moved

sys.modules[__name__] = _moved
