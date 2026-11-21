"""The queue's lanes keep their gates and their waiters in the process: every test starts with its own and gives the
gates back."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _the_lanes_are_given_back():
    from nucleo.queue import lanes
    kept = dict(lanes._gates)
    lanes._waiters.clear()
    lanes._told.clear()
    yield
    lanes._gates.clear()
    lanes._gates.update(kept)
    lanes._waiters.clear()
    lanes._told.clear()
