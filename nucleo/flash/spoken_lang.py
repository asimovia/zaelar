"""Moved to `i18n.spoken_lang` (INI-078 F2 step 8): this name is the same module until the engine restarts."""
import sys

import i18n.spoken_lang as _moved

sys.modules[__name__] = _moved
