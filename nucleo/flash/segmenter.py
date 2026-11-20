"""Moved to `nucleo.input.segmenter` (INI-078 F2 step 8): this name is the same module until the engine restarts."""
import sys

import nucleo.input.segmenter as _moved

sys.modules[__name__] = _moved
