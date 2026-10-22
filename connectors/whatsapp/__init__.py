#
# WhatsApp triage connector (unified store in connectors/messaging) — zaelar reads the operator's personal WhatsApp and
# only interrupts with what DESERVES attention, marking already-summarized content as read. Read-only + mark-read.
#
# Boundary with Hermes: the Baileys bridge is a
# vendored COPY from Hermes in connectors/whatsapp/bridge/ (patches marked // ZAELAR-PATCH), immune to
# `hermes update`. The classifier is SHARED (connectors/messaging), LOCAL by default (Ollama), and does NOT go
# through the Hermes agent -> nothing personal leaves the machine and the voice ACP invariant is preserved.
#
# Modules: bridge/ (Node, vendored) · bridge_proc (lifecycle+QR) · client (HTTP) · service (engine). Triage, the
# unified store, proactive notice, brief, and tag dispatch live in connectors/messaging/ (common to all platforms).
# Bridge config is in config.py.
#
