"""nucleo/switchboard — every chunk he says is plugged into where it belongs, before anything else reads it (V2-931).

Measured on his engine (2026-11-17): the question «whose is this sentence?» was answered in three places that did not
know each other — a flow router that only saw Brain Worker errands (44 of 44 decisions on a session with a task waiting
on him: «new», with an empty menu), a binder that read his explicit yes at 0.04, and the small model's own choice of
tool, which re-called the act five times and answered the task three times with words he never said. One sentence in
three pieces opened three tasks, each cancelling the last.

Now there is one board and one decision:

  · `board.open_processes()` — everything that is OPEN, in one list: the Brain Worker processes that run and every
    row that waits on his answer, whoever asked;
  · `route.take(chunk)` — one decision per chunk he says: it belongs to open process N (it adds to it, corrects it,
    answers its question, complains about it) → it is delivered there as he said it and Flash does not run; or it does
    not → Flash takes the turn (a screen order, a spoken answer, a new process through its own doors).

A process receives its chunks in one piece or in five, in order, and decides itself when it has enough to act. A pause
closes a chunk, never a request.
"""
