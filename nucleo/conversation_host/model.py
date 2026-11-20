"""The `Model` port over the engine's fast client (V2-941, the F1 plan §4.7): the voice's model from the routing
table (`deepseek-flash`), chosen per invocation, never a global model env.

`PromptParts` → messages: `[system: prefix] + conversation + [system: state] + [user: input] + steps`. The model's
two orders are tools of its own (`reply`, `no_reply`) offered beside the catalogue, so they arrive as structured
calls. Text deltas → `TextDelta`; the end → `Done` with what the client measured; then each call it gathered: an
order → `Command`, any other → `ToolCall`. A failure is the provider's when it carries an HTTP status or is a transport error, ours when it
is one of Python's programming errors (`provider_failure.is_engine_fault`, criterion R1): `Failed(whose=…)`.

The client's own retry and relay act only BEFORE anything was emitted (a blip, or a stand-in for the same request),
so nothing said is said twice; once it gives up, the run says the failure and the proof counts it.
"""
from __future__ import annotations

import itertools
import json
from typing import Any, AsyncIterator

from conversation.ports import Command, Done, Failed, PromptParts, TextDelta, ToolCall, ToolResult, ToolSpec

#: the manager's orders, as the model sees them
ORDERS = {
    "reply": {"type": "object", "required": ["text"], "properties": {
        "text": {"type": "string"},
        "claims": {"type": "array", "items": {"type": "object", "properties": {
            "entity": {"type": "string"}, "period": {"type": "string"}, "metric": {"type": "string"},
            "direction": {"type": "string"}, "value": {"type": "number"}, "evidence_id": {"type": "string"}}}},
        "complete": {"type": "boolean"}}},
    "no_reply": {"type": "object", "required": ["reason"], "properties": {
        "reason": {"type": "string"}, "complete": {"type": "boolean"}}},
}


#: what the client measured that the run's `model_done` carries: which model and provider ANSWERED (after a relay,
#: the stand-in — `relayed_from` names the one that failed), so latency can be read by provider
DONE_KEYS = ("model", "provider", "relayed_from", "relayed_to", "relay_reason", "prompt_tokens_est",
             "finish_reason", "usage")


def _fn(name: str, schema: dict) -> dict:
    return {"type": "function", "function": {"name": name, "parameters": schema or {"type": "object",
                                                                                     "properties": {}}}}


def tools_for(catalog: list[ToolSpec]) -> list[dict]:
    return [_fn(t.name, t.schema) for t in catalog] + [_fn(n, s) for n, s in ORDERS.items()]


def _result(res: ToolResult) -> str:
    return json.dumps({"status": res.status, "data": res.data, "evidence": [e.to_json() for e in res.evidence]},
                      ensure_ascii=False, default=str)


def messages(p: PromptParts) -> list[dict]:
    out = [{"role": "system", "content": p.prefix}]
    out += [{"role": "user" if t.role == "user" else "assistant", "content": t.text} for t in p.conversation]
    if p.state:
        out.append({"role": "system", "content": p.state})
    out.append({"role": "user", "content": p.input})
    for call, res in p.steps:
        out.append({"role": "assistant", "content": "", "tool_calls": [{
            "id": call.call_id, "type": "function",
            "function": {"name": call.name, "arguments": json.dumps(call.args, ensure_ascii=False)}}]})
        out.append({"role": "tool", "tool_call_id": call.call_id, "content": _result(res)})
    return out


class FastModel:
    """`client` is the engine's `FastClient` (or a double with its `stream`); `spec()` the routing table's voice
    model, read per call."""

    def __init__(self, client=None, spec=None) -> None:
        self._client, self._spec = client, spec
        self._ids = itertools.count(1)

    def _parts(self):
        client = self._client
        if client is None:
            from nucleo.llm.fast_client import FastClient
            client = self._client = FastClient()
        spec = self._spec() if callable(self._spec) else self._spec
        if spec is None:
            from nucleo.llm.model_spec import spec_from_config
            spec = spec_from_config()
        return client, spec

    async def stream(self, prompt: PromptParts, tools: list[ToolSpec], *, run_id: str,
                     model_id: str) -> AsyncIterator[Any]:
        calls: list[tuple[str, dict]] = []
        metrics: dict = {}
        try:
            client, spec = self._parts()
            async for chunk in client.stream(messages(prompt), spec=spec, tools=tools_for(tools),
                                             on_tool_call=lambda name, args: calls.append((name, args)),
                                             metrics=metrics, role="voice"):
                if chunk:
                    yield TextDelta(chunk)
        except Exception as e:  # noqa: BLE001 — every failure becomes an event the run handles, whose it is said
            from nucleo.llm import provider_failure
            yield Failed(f"{type(e).__name__}: {str(e)[:160]}", "ours" if provider_failure.is_engine_fault(e)
                         else "provider")
            return
        # the stream is over: what it measured is said BEFORE the calls it gathered — an order ends the run, and what
        # came after it would never be read
        yield Done({k: metrics[k] for k in DONE_KEYS if k in metrics})
        for name, args in calls:
            if name in ORDERS:
                yield Command(name, args if isinstance(args, dict) else {})
            else:
                yield ToolCall(f"{run_id}:c{next(self._ids)}", name, args if isinstance(args, dict) else {})
