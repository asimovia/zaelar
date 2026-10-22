---
title: Overview
updated: 2026-10-22
status: stable
---

# Zaelar — overview

Zaelar is a **personal operating system you talk to**: one voice agent that runs your agenda, your messages and
your errands, opens what you ask for as **widgets** on a canvas, and **remembers** who you are. Public tagline
(zaelar.com): «A personal agent you talk to — for your agenda, your messages and your errands. The Personal
Operating System.» It runs on its **own brain** — `nucleo/` («Colmena»: FlashBrain for the sub-second voice turn,
Brain Workers for errands that do not fit in a turn) — with its **own memory** (`memory/`, one SQLite file). No
external agent in the loop.

**Two ways to run the same engine** — one codebase, no fork:
- **Self-hosted, free**: clone `github.com/meshkore/zaelar` (Sustainable Use License 1.0, fair-code — `LICENSE.md`;
  never call it «open source» or «MIT»), `make run`, open `http://localhost:43917`. Your memory is one file on your
  machine; only the questions sent to your AI provider leave it.
- **Hosted (Zaelar Cloud)**: live in early access at zaelar.com — sign-up is open, each account gets its own
  isolated machine and storage, reached from the browser (`my.zaelar.com`) or installed on the phone as a PWA.
  Plans and pricing are on zaelar.com, not in this repo.

**What it does today** (built and in use): voice in English and Spanish with barge-in and corrections; agenda with
spoken reminders that fire; WhatsApp / Telegram / email / Google connectors; a canvas of built-in widgets (agenda,
lists, video, music, maps, markets, timers…) driven by voice; **generated widgets** — describe one and it is written
and kept in your Apps (beta); its own **browser** for errands (beta); and **live answers from other agents on the
MeshKore network** (hotels, flights, events — free agents found through the Oracle, no browser needed).

**Not built yet — never write these as shipped**: sharing apps/widgets between users; friend clusters (private
groups of people's agents) and posts; publishing your own agent to the mesh; two Zaelar agents negotiating with each
other in production; agents of shops beyond the free ones on the mesh today. State table:
`docs/architecture/zaelar-meshkore-network.md` §3.

**Source of truth**: `docs/product/zaelar-product.md` (onboarding) + `docs/architecture/zaelar-architecture.md`
(mental model). The public, curated story (and the claims we stand behind) is zaelar.com; `docs/` is the detail.
