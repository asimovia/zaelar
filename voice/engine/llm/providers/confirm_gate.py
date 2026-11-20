"""Moved to `widgets.confirm_gate` (INI-078 F2 step 8): this name is the same module until the engine restarts."""
import sys

import widgets.confirm_gate as _moved

sys.modules[__name__] = _moved
