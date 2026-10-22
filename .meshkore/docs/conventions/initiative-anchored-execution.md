# Initiative-anchored execution

The MeshKore preamble points here (standard §24). Every piece of work anchors to an `(initiative, task)` pair.

In this repo:

- Engine initiatives are `V2-xxx` under `.meshkore/roadmap/initiatives/` (gitignored: the plan is not published).
  Take the number from the highest existing one, never guess it.
- Work that is not about the engine is **not** anchored here.
- A fix found while working on something else is recorded in the current initiative's log, or gets its own
  initiative if it is a separate unit of work.
- `tests/infrastructure/unit/test_roadmap_closure.py` checks that the diary and the initiatives agree.
