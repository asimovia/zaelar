"""nucleo/mesh_dialog.py — when an agent of the network ASKS its user something, and his answer goes back to it.

Before this, an agent's `questions` matched none of the error keys and the worker heard «the agents did not answer».
The CLASS, for any agent (none is named here):

  · **Reading** by SHAPE: a `questions` list (id + text, top or under `result`) or an A2A task `input-required`; never
    status words. An option that needs a value of his own is not offered: he answers by a declared option.
  · **Answering** by the agent's contract: a choice's `set` (dotted paths) rewrites a copy of the request; a `field`
    takes the value; else `{id, choice}` goes to the job that asked.
  · **His standing answers**: the VALUES of an option HE picked on his row, kept as his rules row (personal, never the
    genome) and applied only when the agent offers exactly those values again.
  · **Threads**: one exchange, one row (`sys_kv mesh:thread:<id>`), bound by id.
"""
from __future__ import annotations

import copy
import secrets
import time

_TEXT_MAX, _LABEL_MAX, _MAX_QUESTIONS, _MAX_CHOICES = 400, 160, 12, 12
_KV_THREAD = "mesh:thread:"
_THREAD_TTL_S = 14 * 24 * 3600
_RULE_CLASS, _RULE_CHANNEL = "errand.mesh_serve", "mesh"


# ── reading ───────────────────────────────────────────────────────────────────────────────────────────────
def _text(v, n: int) -> str:
    from nucleo import untrusted
    return untrusted.neutralize(" ".join(str(v or "").split())[:n])


def _choice(c) -> dict | None:
    """One declared option, or None when it is not one he can pick as it stands (it asks for a value of his)."""
    if not isinstance(c, dict) or c.get("needsValue") or None in (c.get("set") or {}).values():
        return None
    label = _text(c.get("label") or c.get("id"), _LABEL_MAX)
    return {"label": label, **{k: c[k] for k in ("set", "id", "value") if c.get(k) not in (None, "")}} if label else None


def _question(q, i: int) -> dict | None:
    if not isinstance(q, dict):
        return None
    text = _text(q.get("text") or q.get("ask"), _TEXT_MAX)
    if not text:
        return None
    raw = q.get("choices") or []
    choices = [c for c in (_choice(c) for c in (raw if isinstance(raw, list) else [])) if c][:_MAX_CHOICES]
    for n, c in enumerate(choices):
        c["n"] = n                                   # the index he picks is the index in what he was shown
    out = {"id": str(q.get("id") or q.get("field") or f"q{i + 1}").strip(), "text": text, "choices": choices}
    if q.get("field"):
        out["field"] = str(q["field"])
    return out


def questions_in(data) -> list[dict]:
    """The questions an agent's answer puts to its user, normalised; [] when it puts none. Structural only."""
    if not isinstance(data, dict):
        return []
    for node in (data, data.get("result") if isinstance(data.get("result"), dict) else {}):
        qs = node.get("questions")
        if isinstance(qs, list) and qs:
            out = [q for q in (_question(q, i) for i, q in enumerate(qs)) if q]
            if out:
                return out[:_MAX_QUESTIONS]
    status = data.get("status") if isinstance(data.get("status"), dict) else {}
    if str(status.get("state") or "") == "input-required":            # the A2A task state, a protocol name
        parts = ((status.get("message") or {}).get("parts") or []) if isinstance(status.get("message"), dict) else []
        text = " ".join(_text(p.get("text"), _TEXT_MAX) for p in parts if isinstance(p, dict) and p.get("text"))
        return [{"id": "input", "text": text[:_TEXT_MAX] or "?", "choices": []}]
    return []


# ── answering ─────────────────────────────────────────────────────────────────────────────────────────────
def set_path(body: dict, dotted: str, value) -> None:
    """Write `value` at a dotted path of `body`, creating the objects on the way."""
    node, keys = body, [k for k in str(dotted or "").split(".") if k]
    for k in keys[:-1]:
        if not isinstance(node.get(k), dict):
            node[k] = {}
        node = node[k]
    if keys:
        node[keys[-1]] = value


def apply(body: dict, question: dict, n: int | None, words: str = "") -> tuple[dict | None, dict | None, str]:
    """His answer to `question` → `(new_body, job_answer, why_not)`. A question with options takes ONLY an option (`n`);
    one without options takes his words. A choice's `set` rewrites a copy of the request; a `field` takes the value
    there; anything else is `{id, choice|value}` for the job that asked."""
    choices = question.get("choices") or []
    choice = choices[n] if choices and n is not None and 0 <= n < len(choices) else None
    if choices and choice is None:
        return None, None, f"question {question.get('id')} is answered by one of its options"
    if not choices and not str(words or "").strip():
        return None, None, f"question {question.get('id')} needs his words"
    if choice is not None and choice.get("set"):
        out = copy.deepcopy(body or {})
        for path, v in choice["set"].items():
            set_path(out, path, v)
        return out, None, ""
    if question.get("field"):
        out = copy.deepcopy(body or {})
        set_path(out, question["field"], choice.get("value", choice.get("id", choice["label"])) if choice else words)
        return out, None, ""
    if choice is not None:
        return None, {"id": question.get("id"), "choice": choice.get("id") or choice["label"]}, ""
    return None, None, f"question {question.get('id')} has no option to send back"   # a job is answered by an option


# ── his standing answers (the personal layer: HIS rules rows, never the genome) ─────────────────────────────
def _rule_key(agent_id: str, skill_id: str, qid: str) -> str:
    return f"mesh.mandate:{agent_id}/{skill_id}/{qid}".lower()


def remember(agent_id: str, skill_id: str, question: dict, n: int) -> bool:
    """Keep the VALUES of the choice he picked (a `set`) as his standing answer for this agent, skill and question."""
    choices = question.get("choices") or []
    choice = choices[n] if 0 <= n < len(choices) else None
    if not choice or not choice.get("set"):
        return False
    import rules
    rules.add(rules.class_scope(_RULE_CLASS, _RULE_CHANNEL), "pref", _rule_key(agent_id, skill_id, question["id"]),
              {"set": dict(choice["set"])}, text=choice["label"][:_LABEL_MAX], source="user", origin="mesh")
    return True


def prefill(agent_id: str, skill_id: str, questions: list[dict], body: dict) -> tuple[dict, list[dict], list[str]]:
    """Answer from his standing answers every question whose options include EXACTLY the values he chose before →
    `(body, still_open, labels_applied)`. The agent's option is only used when its values are his."""
    import rules
    out, still, applied = copy.deepcopy(body or {}), [], []
    anchors = rules.path(cls=_RULE_CLASS, channel=_RULE_CHANNEL)
    for q in questions:
        kept = rules.value(anchors, _rule_key(agent_id, skill_id, q.get("id") or ""))
        mine = kept.get("set") if isinstance(kept, dict) else None
        choice = next((c for c in q.get("choices") or [] if mine and c.get("set") == mine), None)
        if choice is None:
            still.append(q)
            continue
        out, _j, _w = apply(out, q, choice["n"])
        applied.append(f"{q['id']}: {choice['label']}")
    return out, still, applied


# ── threads: one open exchange with one agent, ONE row each (`sys_kv mesh:thread:<id>`) ───────────────────────
def _key(tid: str) -> str:
    return _KV_THREAD + str(tid or "").strip()


def save(thread: dict) -> str:
    """Store (or update) ONE thread under its own key — two processes never rewrite each other's. Returns its id."""
    from memory import api as memory                 # the KV doors never raise (an unreadable row is the default)
    thread["id"] = thread.get("id") or f"mt_{secrets.token_hex(5)}"
    thread.setdefault("created", time.time())
    thread["updated"] = time.time()
    memory.kv_set(_key(thread["id"]), thread)
    return thread["id"]


def thread(tid: str) -> dict | None:
    """The thread `tid`, or None."""
    from memory import api as memory
    t = memory.kv_get(_key(tid)) if tid else None
    return dict(t) if isinstance(t, dict) else None


def all_threads() -> list[dict]:
    """Every live thread; one older than its TTL is deleted on the way."""
    from memory import api as memory
    out = []
    for k in memory.kv_keys(_KV_THREAD):
        t = memory.kv_get(k)
        if isinstance(t, dict) and time.time() - float(t.get("updated") or 0) < _THREAD_TTL_S:
            out.append(t)
        else:
            memory.kv_del(k)
    return out
