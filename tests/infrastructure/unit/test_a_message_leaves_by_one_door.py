"""A message leaves this machine by ONE door (`connectors/exit.py`), read off the product's own source.

Measured before the door existed: four bus publishers with six callers — two of them publishing around the outbound
queue and its secret scan — and seven places that wrote into the queues, each in its own way. A new road to a
connector could be added by one line anywhere, and nothing would say so.

Every rule below is an EXACT inventory (`file::function` → how many sites). A site that is not on its table fails —
and so does an entry the code no longer has: the tables only shrink, and a new road is added here, on purpose, with
its lane.

  TOPIC      the four outbound topics are emitted only by their own publisher;
  PUBLISHER  those publishers are named only by the exit door;
  LEAVE      `exit.leave` is called only by the queue's flush, the autoresponder and the calendar's mail invitation;
  QUEUE      the outbound queues are written only by the card's own acts and the two roads that queue directly;
  CLIENT     a connector's send is called only inside that connector;
  STAMP      a lane is stamped on a payload only by the doors that may name one;
  ASKS       every door that lets an act leave by another road asks the exit first.

The disarm runs here, on every pass, in memory: the same scanner is given the real source with ONE door taken out, and
it must report the site.
"""
from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]
_SKIP = {".venv", "tests", "node_modules", "__pycache__", ".git", ".meshkore", ".claude", "TMP", "mobile-app"}

TOPICS = {"TOPIC_SEND": "msg.send", "TOPIC_REPLY": "msg.reply", "TOPIC_GROUP": "msg.group",
          "TOPIC_GROUP_LEAVE": "msg.group_leave"}
PUBLISHERS = ("publish_send", "publish_reply", "publish_group", "publish_group_leave")
QUEUES = ("pending_send", "pending_reply", "pending_group", "pending_group_leave")
QUEUE_CALLS = ("enqueue", "enqueue_reply")
#: The names the card's outbound queue is reached by (`_d._outbound.enqueue`, `outbound.enqueue`, `queue.enqueue_reply`);
#: a bare `enqueue(...)` counts in a module that imports it from the card. Other `.enqueue` are other queues.
THE_OUTBOUND_QUEUE = {"_outbound", "outbound", "queue"}
CLIENT_CALLS = ("send_message", "send_media", "create_group", "leave_group")
EMITS = ("emit_sync", "publish", "emit")
EXIT = "connectors/exit.py"

# ── the inventories ────────────────────────────────────────────────────────────────────────────────────────────────
TOPIC = {
    "connectors/messaging/ingest.py::publish_send": 1,
    "connectors/messaging/ingest.py::publish_reply": 1,
    "connectors/messaging/ingest.py::publish_group": 1,
    "connectors/messaging/group_leave.py::publish_group_leave": 1,
}
PUBLISHER = {f"{EXIT}::_publish": 4}
LEAVE = {
    "widgets/mensajeria/owner/handle.py::_flush_queues": 4,
    "widgets/mensajeria/owner/apply.py::_auto_reply": 1,
    "widgets/agenda/invite.py::_mail_invitation": 1,
}
QUEUE = {
    "widgets/mensajeria/outbound/queue.py::enqueue_reply": 1,      # the queue itself: `pending_reply`
    "widgets/mensajeria/outbound/queue.py::enqueue": 1,            # the queue itself: `pending_send`
    "widgets/mensajeria/actions/send.py::_a_reply": 2,
    "widgets/mensajeria/actions/send.py::_a_send_draft": 2,
    "widgets/mensajeria/actions/send.py::_a_send_to": 1,
    "widgets/mensajeria/card_send.py::send": 1,                    # his hand on the card
    "widgets/mensajeria/actions/groups.py::_a_create_group": 1,
    "widgets/mensajeria/actions/leave.py::_a_leave_group": 1,
    "nucleo/send/deliver.py::_reply": 1,                           # the message owner, a threaded reply
    "nucleo/errands/wake.py::_send": 1,                            # an errand's reply
}
CLIENT = {
    "connectors/whatsapp/service/outbound.py": 3,
    "connectors/whatsapp/service/directory.py": 1,
    "connectors/whatsapp/service/leave.py": 1,
    "connectors/telegram/account_ops.py": 2,
    "connectors/email/mailbox/smtp.py": 1,
}
STAMP = {
    "nucleo/send/deliver.py::lane": 1,                             # the message owner
    "widgets/server_api.py::widget_action": 1,                     # his hand
    f"{EXIT}::by": 1,
}
ASKS = {
    "nucleo/errands/mandate.py::deliver",          # an errand's or a stream's reply
    "widgets/agenda/invite.py::run",               # an invitation through the calendar provider
    "widgets/agenda/invite.py::_mail_invitation",  # an invitation by mail
    "widgets/agenda/gcal.py::rsvp_google",         # the answer to an invitation
    "nucleo/send/deliver.py::check",               # the message owner, before he is asked
}


# ── the scanner ────────────────────────────────────────────────────────────────────────────────────────────────────
def sources() -> dict[str, str]:
    out = {}
    for p in ENGINE.rglob("*.py"):
        rel = p.relative_to(ENGINE)
        if not (set(rel.parts) & _SKIP) and not any(x.startswith(".") for x in rel.parts):
            out[rel.as_posix()] = p.read_text(encoding="utf-8")
    return out


def _name(node) -> str:
    return node.attr if isinstance(node, ast.Attribute) else getattr(node, "id", "")


def _receiver(node) -> str:
    return _name(node.value) if isinstance(node, ast.Attribute) else ""


def _exit_aliases(tree: ast.AST) -> set[str]:
    """The names this module binds `connectors.exit` to (`from connectors import exit as door`)."""
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module == "connectors":
            out |= {a.asname or a.name for a in n.names if a.name == "exit"}
        elif isinstance(n, ast.Import):
            out |= {a.asname or "connectors" for a in n.names if a.name == "connectors.exit" and a.asname}
    return out


def _dunder_exit(call: ast.Call) -> bool:
    """`__import__("connectors.exit", fromlist=[...])` — the same module, named without an import line."""
    return (isinstance(call.func, ast.Name) and call.func.id == "__import__" and bool(call.args)
            and isinstance(call.args[0], ast.Constant) and call.args[0].value == "connectors.exit")


class _Scan(ast.NodeVisitor):
    def __init__(self, path: str, tree: ast.AST) -> None:
        self.path, self.stack = path, []
        self.door = _exit_aliases(tree)
        self.queue_names = {a.asname or a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
                            and str(n.module or "").startswith("widgets.mensajeria") for a in n.names
                            if a.name in QUEUE_CALLS}
        self.found = {k: Counter() for k in ("TOPIC", "PUBLISHER", "LEAVE", "QUEUE", "CLIENT", "STAMP", "ASKS")}

    def _where(self) -> str:
        return f"{self.path}::{self.stack[-1]}" if self.stack else f"{self.path}::<module>"

    def _fn(self, node) -> None:
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_FunctionDef = visit_AsyncFunctionDef = _fn

    def _on_door(self, func) -> bool:
        """Is this `<the exit module>.<something>`?"""
        if not isinstance(func, ast.Attribute):
            return False
        v = func.value
        return (isinstance(v, ast.Name) and (v.id in self.door or (self.path == EXIT and v.id == "self"))) \
            or (isinstance(v, ast.Call) and _dunder_exit(v))

    def visit_Call(self, node: ast.Call) -> None:
        name = _name(node.func)
        if name in EMITS and node.args:
            a = node.args[0]
            if _name(a) in TOPICS or (isinstance(a, ast.Constant) and a.value in TOPICS.values()):
                self.found["TOPIC"][self._where()] += 1
        if name in QUEUE_CALLS and (_receiver(node.func) in THE_OUTBOUND_QUEUE if isinstance(node.func, ast.Attribute)
                                    else name in self.queue_names):
            self.found["QUEUE"][self._where()] += 1
        if name == "setdefault" and node.args and isinstance(node.args[0], ast.Constant) \
                and node.args[0].value in QUEUES and getattr(node, "_appended", False):
            self.found["QUEUE"][self._where()] += 1
        if name == "append" and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Call):
            node.func.value._appended = True          # `db.setdefault("pending_x", []).append(...)` is a write
        if name in CLIENT_CALLS and isinstance(node.func, ast.Attribute):
            self.found["CLIENT"][self.path] += 1
        if self._on_door(node.func):
            if name == "leave":
                self.found["LEAVE"][self._where()] += 1
            elif name in ("stamp", "by"):
                self.found["STAMP"][self._where()] += 1
            elif name in ("check", "held"):
                self.found["ASKS"][self._where()] += 1
        elif self.path == EXIT and name in ("stamp",) and isinstance(node.func, ast.Name):
            self.found["STAMP"][self._where()] += 1
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr in PUBLISHERS and isinstance(node.ctx, ast.Load):
            self.found["PUBLISHER"][self._where()] += 1
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in PUBLISHERS and isinstance(node.ctx, ast.Load):
            self.found["PUBLISHER"][self._where()] += 1


def scan(srcs: dict[str, str]) -> dict[str, dict[str, int]]:
    total = {k: Counter() for k in ("TOPIC", "PUBLISHER", "LEAVE", "QUEUE", "CLIENT", "STAMP", "ASKS")}
    for path, src in srcs.items():
        if not any(w in src for w in ("exit", "pending_", "enqueue", "msg.", "TOPIC_", "publish_", *CLIENT_CALLS)):
            continue
        tree = ast.parse(src)
        s = _Scan(path, tree)
        s.visit(tree)
        for k, c in s.found.items():
            total[k].update(c)
    # a connector's own client module DEFINES its sends; calling them from inside itself is not a road
    total["CLIENT"] = Counter({p: n for p, n in total["CLIENT"].items() if not p.endswith("/client.py")})
    return {k: dict(v) for k, v in total.items()}


def _diff(found: dict[str, int], table: dict[str, int]) -> list[str]:
    out = [f"NEW  {k} ×{n} (the table says {table.get(k, 0)})" for k, n in sorted(found.items()) if n > table.get(k, 0)]
    out += [f"GONE {k} ×{table[k]} → ×{found.get(k, 0)}: shrink the table" for k in sorted(table)
            if found.get(k, 0) < table[k]]
    return out


FOUND = scan(sources())


# ── the rules ──────────────────────────────────────────────────────────────────────────────────────────────────────
def test_the_outbound_topics_are_emitted_only_by_their_publishers():
    assert not _diff(FOUND["TOPIC"], TOPIC), "\n".join(_diff(FOUND["TOPIC"], TOPIC))


def test_the_publishers_are_named_only_by_the_exit_door():
    assert not _diff(FOUND["PUBLISHER"], PUBLISHER), "\n".join(_diff(FOUND["PUBLISHER"], PUBLISHER))


def test_the_exit_door_is_called_only_from_the_declared_sites():
    assert not _diff(FOUND["LEAVE"], LEAVE), "\n".join(_diff(FOUND["LEAVE"], LEAVE))


def test_the_outbound_queues_are_written_only_by_the_declared_roads():
    assert not _diff(FOUND["QUEUE"], QUEUE), "\n".join(_diff(FOUND["QUEUE"], QUEUE))


def test_a_connectors_send_is_called_only_inside_that_connector():
    assert not _diff(FOUND["CLIENT"], CLIENT), "\n".join(_diff(FOUND["CLIENT"], CLIENT))


def test_a_lane_is_stamped_only_by_the_doors_that_may_name_one():
    assert not _diff(FOUND["STAMP"], STAMP), "\n".join(_diff(FOUND["STAMP"], STAMP))


def test_every_other_road_out_asks_the_exit_first():
    missing = sorted(ASKS - set(FOUND["ASKS"]))
    assert not missing, f"these doors let an act leave without asking `exit.check`/`exit.held`: {missing}"


# ── the disarm, on every pass ──────────────────────────────────────────────────────────────────────────────────────
def _mutated(path: str, old: str, new: str) -> dict[str, dict[str, int]]:
    srcs = sources()
    assert old in srcs[path], f"the disarm no longer finds its line in {path}: rewrite it against the code"
    return scan({**srcs, path: srcs[path].replace(old, new, 1)})


def test_taking_the_door_off_one_lane_is_seen():
    """The flush publishes a send itself, around the door: one fewer `leave`, one publisher named outside the exit."""
    got = _mutated("widgets/mensajeria/owner/handle.py", "door.leave(door.SEND, ", "ingest.publish_send(")
    assert any(d.startswith("GONE widgets/mensajeria/owner/handle.py::_flush_queues") for d in _diff(got["LEAVE"], LEAVE))
    assert any(d.startswith("NEW  widgets/mensajeria/owner/handle.py::_flush_queues")
               for d in _diff(got["PUBLISHER"], PUBLISHER))


def test_a_new_road_into_the_queue_is_seen():
    got = _mutated("nucleo/errands/mandate.py", "def hold(", '''def _around(db, order):
    db.setdefault("pending_send", []).append(order)


def hold(''')
    assert _diff(got["QUEUE"], QUEUE) == ["NEW  nucleo/errands/mandate.py::_around ×1 (the table says 0)"]


def test_a_topic_emitted_by_hand_is_seen():
    got = _mutated("widgets/mensajeria/owner/apply.py", "from connectors import exit as door\n",
                   'from connectors import exit as door\n            bus.emit_sync("msg.reply", {})\n')
    assert _diff(got["TOPIC"], TOPIC) == ["NEW  widgets/mensajeria/owner/apply.py::_auto_reply ×1 (the table says 0)"]


def test_a_stamp_put_by_another_door_is_seen():
    got = _mutated("widgets/server_api.py", "    wid = _safe(wid)\n    from nucleo import consequence as _consequence",
                   '    wid = _safe(wid)\n    payload = __import__("connectors.exit", fromlist=["x"]).by("hand", payload)\n'
                   "    from nucleo import consequence as _consequence")
    assert _diff(got["STAMP"], STAMP) == ["NEW  widgets/server_api.py::brain_action ×1 (the table says 0)"]
