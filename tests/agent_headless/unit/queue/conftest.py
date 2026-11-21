"""The queue's lanes keep their gates in the process: a test that sets one gives it back."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _the_lanes_gates_are_given_back():
    from nucleo.queue import lanes
    kept = dict(lanes._gates)
    yield
    lanes._gates.clear()
    lanes._gates.update(kept)
