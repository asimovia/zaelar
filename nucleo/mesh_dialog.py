"""nucleo/mesh_dialog.py — when an agent of the network ASKS its user something, and his answer goes back to it.

A live agent is not always a vending machine. Asked to book a table it may answer with a question instead of a
result: «if 21:00 is taken, which other time?», «you are eight: one table or two?», «the venue asks for a 20 € deposit
— accept?». Before this module every one of those was LOST: the reader of an error body looked for `need`/`error`/
`detail` keys, an agent's `questions` list matched none of them, and the worker was told «the agents did not answer».

This is the CLASS, not a booking feature — nothing here knows restaurants, and no agent is named:

  · **Reading** (`questions_in`) is STRUCTURAL: an answer that carries a list of `questions`, each with an id and a
    text (at the top or under `result`), or an A2A task in state `input-required`, is the agent asking its user.
    Status words are never read: what makes it a question is its shape.
  · **Answering** (`apply`) is the agent's own contract: a choice that declares the fields it `set`s (dotted paths)
    is written into the request, which is sent again whole; a question with a `field` takes the choice's value
    there; anything else is an answer `{id, choice}` to the job that asked (`mesh_call.reply`).
  · **His standing answers** (`remember`/`prefill`): a fully specified choice of a question that sets fields IS a
    preference («any table», «±15 min») — it is kept as HIS row of the rules table (personal layer, never in the
    genome), keyed by agent, skill and question, and applied the next time that agent asks the same question in the
    same shape. A question about one job («accept 15:15?») is never kept: it is about that day, not about him.
  · **Binding** is by IDENTITY: every open exchange is a THREAD (`mt_…`) that holds the agent, the skill, the request
    and the questions; his answer names the thread (and, for a job, the job id). Never a confidence floor, never
    «the latest question».

What an agent writes is a stranger's text: it is fenced by the caller before a worker reads it, and only a choice's
LABEL ever reaches his rules row.
"""
from __future__ import annotations

import copy
import json
import secrets
import time

from loguru import logger

_TEXT_MAX, _LABEL_MAX, _MAX_QUESTIONS, _MAX_CHOICES = 400, 160, 12, 12
_KV_THREADS = "mesh:threads"
_THREAD_TTL_S = 14 * 24 * 3600
_RULE_CLASS, _RULE_CHANNEL = "errand.mesh_serve", "mesh"


def _note(e: BaseException) -> None:
    import sys
    logger.debug(f"mesh_dialog: {sys._getframe(1).f_code.co_name} — {type(e).__name__}: {e}")


# ── reading ───────────────────────────────────────────────────────────────────────────────────────────────
def _text(v, n: int) -> str:
    return " ".join(str(v or "").split())[:n]


def _choice(c, i: int) -> dict | None:
    if isinstance(c, (str, int, float)) and str(c).strip():
        return {"n": i, "id": str(c), "label": _text(c, _LABEL_MAX)}
    if not isinstance(c, dict):
        return None
    label = _text(c.get("label") or c.get("text") or c.get("title") or c.get("id") or c.get("value"), _LABEL_MAX)
    if not label:
        return None
    out = {"n": i, "label": label}
    if isinstance(c.get("set"), dict):
        out["set"] = dict(c["set"])
    for k in ("id", "value", "needsValue"):
        if c.get(k) not in (None, ""):
            out["needs_value" if k == "needsValue" else k] = c[k]
    return out


def _question(q, i: int) -> dict | None:
    if not isinstance(q, dict):
        return None
    text = _text(q.get("text") or q.get("question") or q.get("prompt"), _TEXT_MAX)
    qid = str(q.get("id") or q.get("field") or f"q{i + 1}").strip()
    if not text:
        return None
    raw = q.get("choices") or q.get("options") or []
    choices = [c for c in (_choice(c, n) for n, c in enumerate(raw if isinstance(raw, list) else []))
               if c][:_MAX_CHOICES]
    out = {"id": qid, "text": text, "choices": choices}
    if q.get("field"):
        out["field"] = str(q["field"])
    sug = q.get("default_suggestion")
    if isinstance(sug, dict) and sug.get("label"):
        out["suggestion"] = _text(sug["label"], _LABEL_MAX)
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
        return [{"id": "input", "text": text[:_TEXT_MAX] or "?", "choices": [], "free_text": True}]
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


def _filled(choice: dict, value) -> dict | None:
    """A choice's `set` with the operator's VALUE in its open (null) slots; None when the value does not fit them."""
    fields = dict(choice.get("set") or {})
    holes = [k for k, v in fields.items() if v is None]
    if not holes:
        return fields
    if isinstance(value, dict):
        fields.update({k: value[k] for k in holes if k in value})
    elif isinstance(value, list) and len(value) == len(holes):
        fields.update(dict(zip(holes, value)))
    elif len(holes) == 1 and value not in (None, ""):
        fields[holes[0]] = value
    return None if any(v is None for v in fields.values()) else fields


def parse_value(raw: str):
    """A value as typed: JSON when it parses (an object, a list, a number, true), else the text itself."""
    try:
        return json.loads(raw)
    except Exception:  # noqa: BLE001 — plain text is a legitimate value
        return raw


def apply(body: dict, question: dict, n: int | None, value=None) -> tuple[dict | None, dict | None, str]:
    """His answer to `question` (choice `n`, and/or a free `value`) → `(new_body, job_answer, why_not)`.

    A choice that SETS fields rewrites the request (`new_body`); a question with a `field` takes the value there; any
    other answer is `{id, choice|value}` for the job that asked (`job_answer`). `why_not` says what is missing."""
    choices = question.get("choices") or []
    choice = choices[n] if n is not None and 0 <= n < len(choices) else None
    if n is not None and choice is None:
        return None, None, f"question {question.get('id')} has no choice {n}"
    if choice is not None and choice.get("set") is not None:
        fields = _filled(choice, value)
        if fields is None:
            return None, None, f"choice {n} of {question.get('id')} needs a value ({choice.get('needs_value') or 'value'})"
        out = copy.deepcopy(body or {})
        for path, v in fields.items():
            set_path(out, path, v)
        return out, None, ""
    picked = (choice or {}).get("value", (choice or {}).get("id", (choice or {}).get("label"))) if choice else value
    if picked in (None, ""):
        return None, None, f"question {question.get('id')} needs a choice or a value"
    if question.get("field"):
        out = copy.deepcopy(body or {})
        set_path(out, question["field"], picked)
        return out, None, ""
    return None, {"id": question.get("id"), ("choice" if choice else "value"): picked}, ""


# ── his standing answers (the personal layer: HIS rules rows, never the genome) ─────────────────────────────
def _rule_key(agent_id: str, skill_id: str, qid: str) -> str:
    return f"mesh.mandate:{agent_id}/{skill_id}/{qid}".lower()


def _signature(choice: dict) -> list[str]:
    return sorted((choice.get("set") or {}).keys())


def standing(choice: dict | None) -> bool:
    """Is this a choice that can stand as his preference? It sets fields and needs nothing from him."""
    return bool(choice and choice.get("set") and not choice.get("needs_value")
                and all(v is not None for v in choice["set"].values()))


def remember(agent_id: str, skill_id: str, question: dict, n: int) -> bool:
    """Keep his answer `n` to `question` as his standing preference for this agent and skill. True when kept."""
    choices = question.get("choices") or []
    choice = choices[n] if 0 <= n < len(choices) else None
    if not standing(choice):
        return False
    try:
        import rules
        rules.add(rules.class_scope(_RULE_CLASS, _RULE_CHANNEL), "pref", _rule_key(agent_id, skill_id, question["id"]),
                  {"n": n, "keys": _signature(choice), "label": choice["label"]},
                  text=choice["label"][:_LABEL_MAX], source="user", origin="mesh")
        return True
    except Exception as e:  # noqa: BLE001 — not kept is asked again next time; never a wrong preference
        _note(e)
        return False


def _kept(agent_id: str, skill_id: str, qid: str) -> dict | None:
    try:
        import rules
        v = rules.value(rules.path(cls=_RULE_CLASS, channel=_RULE_CHANNEL), _rule_key(agent_id, skill_id, qid))
        return v if isinstance(v, dict) else None
    except Exception as e:  # noqa: BLE001
        _note(e)
        return None


def prefill(agent_id: str, skill_id: str, questions: list[dict], body: dict) -> tuple[dict, list[dict], list[str]]:
    """Answer from his standing preferences every question asked in the SAME shape he answered before (same id, a
    choice at the same position setting the same fields) → `(body, still_open, labels_applied)`."""
    out, still, applied = copy.deepcopy(body or {}), [], []
    for q in questions:
        kept = _kept(agent_id, skill_id, q.get("id") or "")
        choices = q.get("choices") or []
        n = kept.get("n") if kept else None
        choice = choices[n] if isinstance(n, int) and 0 <= n < len(choices) else None
        if choice is None or not standing(choice) or _signature(choice) != list(kept.get("keys") or []):
            still.append(q)
            continue
        new, _ans, why = apply(out, q, n)
        if new is None:
            still.append(q)
            continue
        out = new
        applied.append(f"{q['id']}: {choice['label']}")
    return out, still, applied


# ── threads: one open exchange with one agent, bound by its id ───────────────────────────────────────────────
def _threads() -> dict:
    try:
        from memory import api as memory
        got = memory.kv_get(_KV_THREADS, {}) or {}
        return got if isinstance(got, dict) else {}
    except Exception as e:  # noqa: BLE001
        _note(e)
        return {}


def save(thread: dict) -> str:
    """Store (or update) a thread; returns its id. Threads older than their TTL are dropped on the way."""
    now = time.time()
    tid = str(thread.get("id") or f"mt_{secrets.token_hex(5)}")
    thread.update(id=tid, updated=now)
    thread.setdefault("created", now)
    all_ = {k: v for k, v in _threads().items()
            if isinstance(v, dict) and now - float(v.get("updated") or 0) < _THREAD_TTL_S}
    all_[tid] = thread
    try:
        from memory import api as memory
        memory.kv_set(_KV_THREADS, all_)
    except Exception as e:  # noqa: BLE001
        _note(e)
    return tid


def thread(tid: str) -> dict | None:
    """The open thread `tid`, or None."""
    t = _threads().get(str(tid or "").strip())
    return dict(t) if isinstance(t, dict) else None


def with_job(job_id: str) -> dict | None:
    """The thread that owns job `job_id` — how a job's later question finds its way back to the same exchange."""
    for t in _threads().values():
        if isinstance(t, dict) and str((t.get("job") or {}).get("id") or "") == str(job_id or "") and job_id:
            return dict(t)
    return None


def open_jobs() -> list[dict]:
    """Every thread whose job has not ended — what the pulse's sweep advances."""
    return [dict(t) for t in _threads().values()
            if isinstance(t, dict) and (t.get("job") or {}).get("id") and not t["job"].get("done")]
