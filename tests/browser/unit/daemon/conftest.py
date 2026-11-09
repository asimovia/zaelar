"""The daemon screen's rendered tests share one static server per module (see `harness.py`)."""
from tests.browser.unit.daemon.harness import server  # noqa: F401  (a fixture, re-exported for pytest)
