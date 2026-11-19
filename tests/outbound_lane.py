"""A test that drives the messaging card's own actions does so as HIS HAND on the card: the lane every order needs
to leave (`connectors/exit.py`). Import `his_hand` in a directory's conftest to declare it for the tests there — a
test of another road (the owner, a worker, an errand) names its own lane and is not served by this."""
import pytest


@pytest.fixture(autouse=True)
def his_hand():
    from connectors import exit as door
    from widgets.mensajeria.outbound import lane
    token = lane._lane.set(door.HAND)
    try:
        yield
    finally:
        lane._lane.reset(token)
