"""The top bar's rendered tests share one static server per module (the daemon screen's harness)."""
from tests.browser.unit.daemon.harness import server  # noqa: F401  (a fixture, re-exported for pytest)
