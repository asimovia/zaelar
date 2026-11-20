"""The `Route` port (INI-078 F2 step 3, plan §3): his words to something of his that is OPEN reach it by the doors
that already decide it, before the model is called.

One door today, the switchboard (`nucleo.switchboard.route.take`): one decision over one board of the processes in
course and the rows waiting on his answer (`board.open_processes`) — «is this for process N, or for none?» — his stop
to one of them ending its row through the one cancel door. With nothing open it answers at once and costs nothing.
The send owner's draft (`nucleo.send.owner.take`) goes FIRST here when the send is wired (step 4).

The doors do not speak by themselves: the line they would say is collected and handed back for the manager's mouth.
They run on the engine's loop, where the processes live.
"""
from __future__ import annotations


class HostRoute:
    async def take(self, account: str, text: str) -> str | None:
        from nucleo.conversation_host.acts import _on_engine_loop
        from nucleo.switchboard import board, route
        if not board.open_processes():          # nothing open: nobody to take his words, no decision paid
            return None
        said: list[str] = []
        from voice.observer import emit
        took = await _on_engine_loop(route.take(text, brain=None, emit=emit, say=said.append))
        return (said[-1] if said else "") if took else None
