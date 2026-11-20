"""The `Model` port over the engine's fast client (V2-941, the F1 plan §4.7): the voice's model from the routing
table (`deepseek-flash`), chosen per invocation, never a global model env.

`PromptParts` → messages: `[system: prefix] + conversation + [system: state] + [user: input] + steps`. The model's
two orders are tools of its own (`reply`, `no_reply`) offered beside the catalogue, so they arrive as structured
calls. Text deltas → `TextDelta`; the end → `Done` with what the client measured; then each call it gathered: an
order → `Command`, any other → `ToolCall`. A failure is the provider's when it carries an HTTP status or is a transport error, ours when it
is one of Python's programming errors (`provider_failure.is_engine_fault`, criterion R1): `Failed(whose=…)`.

The client's own retry and relay act only BEFORE anything was emitted (a blip, or a stand-in for the same request),
so nothing said is said twice; once it gives up, the run says the failure and the proof counts it. A cut MID-BODY the
client does not re-send (its voice path may have spoken); here nothing leaves before the stream ends but text, so a
transport cut with no text yielded is re-sent whole, `RESENDS` times, and `Done` says it (`resent`).
"""
from __future__ import annotations

import itertools
import json
from typing import Any, AsyncIterator

from conversation.ports import (RELAY, UNCLAIMED, Command, Done, Failed, PromptParts, TextDelta, ToolCall, ToolResult,
                                ToolSpec)

from conversation.manager.claims import OPS       # the package's own operations, never a second list
from nucleo.conversation_host.declared import declared

#: the shapes of a claim (`declared.json`, data the code reads): a figure that IS in the evidence, and one computed
#: from it — its operation (the package's own, never a second list) and operands part of the claim, never optional
FACT = declared()["fact"]
DERIVED = {**declared()["derived"],
           "properties": {**declared()["derived"]["properties"], "op": {"type": "string", "enum": sorted(OPS)}}}
#: the manager's orders, as the model sees them
ORDERS = {
    "reply": {"type": "object", "required": ["text"], "properties": {
        "text": {"type": "string"},
        "claims": {"type": "array", "items": {"anyOf": [FACT, DERIVED]}},
        "complete": {"type": "boolean"}}},
    "no_reply": {"type": "object", "required": ["reason"], "properties": {
        "reason": {"type": "string"}, "complete": {"type": "boolean"}}},
    **{name: {"type": "object", "properties": {}} for name in declared()["stops"]},   # each stop takes no argument at all
}


#: what the client measured that the run's `model_done` carries: which model and provider ANSWERED (after a relay,
#: the stand-in — `relayed_from` names the one that failed), so latency can be read by provider
DONE_KEYS = tuple(declared()["done_keys"])


def _measured(args: dict) -> dict:
    """A reply's figures that carry no claim, counted over OUR output (`figures.py`): a measure, never a gate in F1."""
    if not isinstance(args.get("text"), str):
        return args
    from nucleo.conversation_host.figures import figures
    values = [c.get("value") for c in args.get("claims") or () if isinstance(c, dict)]
    claimed = [float(v) for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    loose = [f for f in figures(args["text"]) if not any(abs(f - v) <= 0.005 * max(1.0, abs(v)) for v in claimed)]
    return {**args, UNCLAIMED: len(loose)}


def _fn(name: str, schema: dict, about: str = "") -> dict:
    fn = {"name": name, "parameters": schema or {"type": "object", "properties": {}}}
    if about:
        fn["description"] = about
    return {"type": "function", "function": fn}


def tools_for(catalog: list[ToolSpec]) -> list[dict]:
    stops = declared()["stops"]                     # a stop says what it stops: the model chooses it from his words
    return [_fn(t.name, t.schema, t.about) for t in catalog] + [_fn(n, s, stops.get(n, "")) for n, s in ORDERS.items()]


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


#: a provider cut mid-body with nothing yielded yet is re-sent this many times (the guard's deadline still bounds it)
RESENDS = 1
#: a disposable engine only (`sandbox.is_sandbox()`): the titular holds its stream and sends nothing, so the run's
#: deadline sends the step to the stand-in — the relay driven live
HANG_TITULAR = "ZAELAR_CONVERSATION_HANG_TITULAR"


def _hangs() -> bool:
    import os

    from nucleo.conversation_host import sandbox
    return (os.getenv(HANG_TITULAR) or "").strip() == "1" and sandbox.is_sandbox()


def max_tokens(channel: str) -> int | None:
    """A generous ceiling on what the model writes for this channel (genesis `conversation.max_tokens`): never a
    cutting one — an order carries its claims too. None: the client's own default."""
    import genome
    got = ((genome.genesis().get("conversation") or {}).get("max_tokens") or {}).get(channel)
    return max(int(got), ORDER_ROOM) if isinstance(got, int) and got > 0 else None


#: the least a call may write: an order carries its text AND its claims — a ceiling below this cuts the order itself
ORDER_ROOM = 512


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
        for attempt in range(1 + RESENDS):
            calls.clear()
            metrics.clear()
            said = False
            try:
                client, spec = self._parts()
                if model_id != RELAY and _hangs():
                    import asyncio
                    await asyncio.sleep(3600)       # cut by the run's own deadline, never by this
                if model_id == RELAY:               # the run's deadline passed on the titular: its stand-in, or none
                    from nucleo.llm.fast_client import relay_spec_for
                    spec = relay_spec_for(spec, "voice")
                    if spec is None:
                        yield Failed("no stand-in", "provider")
                        return
                # every answer is an ORDER (a read, `reply` or `no_reply`): the provider is told a tool call is required
                async for chunk in client.stream(messages(prompt), spec=spec, tools=tools_for(tools),
                                                 on_tool_call=lambda name, args: calls.append((name, args)),
                                                 metrics=metrics, role="voice", tool_choice="required",
                                                 max_tokens=max_tokens(prompt.channel)):
                    if chunk:
                        said = True
                        yield TextDelta(chunk)
                if attempt:
                    metrics["resent"] = attempt
                break
            except Exception as e:  # noqa: BLE001 — every failure becomes an event the run handles, whose it is said
                from nucleo.llm import fast_client, provider_failure
                if not said and attempt < RESENDS and fast_client._is_transient(e):
                    # nothing left this port yet — the gathered calls are yielded only once the stream is over — so
                    # the provider's cut mid-body is re-sent whole, as the client already does before the first chunk
                    continue
                yield Failed(f"{type(e).__name__}: {str(e)[:160]}", "ours" if provider_failure.is_engine_fault(e)
                             else "provider")
                return
        # the stream is over: what it measured is said BEFORE the calls it gathered — an order ends the run, and what
        # came after it would never be read
        dropped = [{"name": d.get("name"), "reason": d.get("reason"), "chars": d.get("chars")}
                   for d in metrics.get("dropped_tool_calls") or () if isinstance(d, dict)]   # never their words
        yield Done({**{k: metrics[k] for k in DONE_KEYS if k in metrics}, **({"dropped": dropped} if dropped else {})})
        if metrics.get("finish_reason") == "length":   # cut by the ceiling: a half order is never one to carry out
            yield Failed("length: the answer was cut by its token ceiling", "provider")
            return
        for name, args in calls:
            if name in ORDERS:
                yield Command(name, _measured(args if isinstance(args, dict) else {}))
            else:
                yield ToolCall(f"{run_id}:c{next(self._ids)}", name, args if isinstance(args, dict) else {})
