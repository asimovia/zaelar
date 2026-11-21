"""Moved to `memory.vault.spoken` (INI-078 F2): this name is the same module until the engine restarts."""
import importlib
import sys

sys.modules[__name__] = importlib.import_module("memory.vault.spoken")
