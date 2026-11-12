"""A node id names ONE node of the test map.

Two writers working at once each take the next free id on their own branch, and both land: measured on 2026-11-12,
twice in one evening (4.490, then 4.494). Python keeps both rows of the list, so nothing failed — but «is node 4.494
green?» then answers for whichever row a reader happens to find first, and the other file is reported under a title
that is not its own.
"""
import collections
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tests.run_testmap import DOMAINS  # noqa: E402


def _repeated(domains) -> dict[str, int]:
    seen = collections.Counter(node["id"] for domain in domains for node in domain["nodes"])
    return {nid: n for nid, n in seen.items() if n > 1}


def test_no_node_id_is_used_twice():
    assert not _repeated(DOMAINS), f"node ids used by more than one node (take the next free id): {_repeated(DOMAINS)}"


def test_the_check_sees_a_repeat_across_two_domains():
    a = {"id": "x", "nodes": [{"id": "4.1"}, {"id": "4.2"}]}
    b = {"id": "y", "nodes": [{"id": "4.2"}]}
    assert _repeated([a, b]) == {"4.2": 2}
