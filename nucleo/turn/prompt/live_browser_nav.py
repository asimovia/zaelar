"""Moved to `widgets.navegador.live_nav` (INI-078 F2 step 8): this name is the same module until the engine restarts."""
import sys

import widgets.navegador.live_nav as _moved

sys.modules[__name__] = _moved
