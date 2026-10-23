---
title: Zaelar Alignment Review
category: ops
updated: 2026-07-09
owner: ricart
status: current
---

# Alignment review workflow — "run the alignment review"

**Trigger:** run it **when closing any change that touches the architecture, a module, a flow or a
decision/invariant** (a planned task, a structural fix, a new piece of the brain/memory/bus), and on demand
when the operator says *"run the alignment review"* / *"check that everything is aligned"*.

**Goal:** make sure that, after the change, **code ↔ context ↔ canonical docs ↔ diagrams ↔ planning ↔ tests**
tell THE SAME story — the CURRENT state, with no dirty code and no legacy. It codifies the checklist so the
instructions do not have to be repeated each time. It is the **quality gate** at the end of a change.

> How it relates to the other workflows: [[zaelar-change-protocol]] closes **one** change
> (restart→version→commit); [[zaelar-docs-sync]] is the docs↔structure coherence step; [[zaelar-audit-workflow]]
> audits the **whole** system periodically. **This review is narrower and more frequent**: it runs after EVERY
> architecture/module change and checks full alignment, including the **diagrams** and the **planning state**.

---

## 0. Does it apply to my change?

It applies if the change does ANY of these:
- touches a **piece of the system** (voice, FlashBrain, SlowBrain, memory, bus, widgets, connectors, server, config);
- changes a **flow** drawn in the public `/technology` diagrams (turn path, escalation, memory retrieval, widget refresh);
- adds/removes/renames a **module, route, tag, env var, command or decision/invariant**;
- changes **how something works** that a canonical doc describes (even if the layout does not change).

A trivial change inside a single file with no effect on a flow or contract does NOT trigger it (a commit is enough).

---

## 1. Alignment checklist (tick EVERY box)

### A · Code and boot
- [ ] The change is **clean**: no dead code, no legacy branches, no `# TODO`/"before X now Y" comments, no
      orphaned imports/files. `grep` for the retired symbols = 0 hits outside history.
- [ ] Clean boot verified: `curl -s localhost:43917/api/brain` answers; no traceback in the log.
- [ ] If you touched `.py`, you **restarted** zaelar and checked it live (not only tests).

### B · Tests
- [ ] `./.venv/bin/pytest` on what you touched is green; no regression in the adjacent suite.
- [ ] If the change has an observable surface, it was **really exercised** (voice tester or manual test), not only unit.

### C · Context (`CLAUDE.md`, `.meshkore/docs/criteria.md`)
- [ ] The description of the affected module(s) reflects **how it works today** (not how it used to).
- [ ] The affected criteria are up to date; no retired rule is still worded as current.
- [ ] The **hard rules** are still correct. The canonical-docs table does not point at deleted files.

### D · Canonical docs (`.meshkore/docs/<category>/`)
- [ ] The doc of the touched category (architecture / modules / product / ops / security / conventions) is current.
- [ ] **No legacy**: no "where we came from"/history of earlier architectures in the LIVE docs.

### E · Planning (the state IS the queue; the daemon serves it to the Architect)
- [ ] The change's tasks are at **`status: done`** in their source `.md` (`.meshkore/modules/<m>/tasks/T*.md`,
      local), with `completed_at` + `commit_shas`. The daemon auto-archives the initiative when ALL its tasks
      are done.
- [ ] A dated line in the initiative's log. The generated `state.json` is **not** edited by hand.
- [ ] If the change was not planned, its initiative/task was opened FIRST (visible live in the Architect).

### F · Golden rule
- [ ] **Context + docs + architecture (diagram) say the same as the code.** If something appears in one, it
      appears in all three. Reading `/technology` (web) or `CLAUDE.md`, nothing would be stale.

---

## 2. Quick probes (copy-paste)

```bash
# Legacy/dirty in the live docs (only what is CURRENT should come out):
grep -rinE "pipecat|hermes|BRAIN=duo| duo |razonador" CLAUDE.md .meshkore/docs
# Symbols retired by this change (fill in) → 0 hits in live code:
grep -rn "<retired_symbol>" --include=*.py . | grep -v .venv
# Planning: the change's tasks done + initiative current (served by the daemon):
grep -h "^status:" .meshkore/modules/*/tasks/T*.md | sort | uniq -c
```

---

## 3. Report template (paste it into the log / the reply)

```
### Alignment review — <change> (<date>)
- Code/boot: <ok · what was cleaned · live check>
- Tests: <what was exercised>
- CLAUDE.md / criteria: <modules/rules touched>
- Canonical docs: <files updated · legacy purged>
- Diagrams: <tabs touched · stamp updated>
- Planning: <tasks done · initiative · log>
- Golden rule: <code↔context↔architecture aligned: yes/no>
- Open: <none | list>
```

If ANY box is left unticked, the change **is not closed** — fix the misalignment before calling the change done.
