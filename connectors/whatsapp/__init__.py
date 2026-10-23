#
# WhatsApp triage connector (unified store in connectors/messaging) — zaelar reads the operator's personal WhatsApp and
# only interrupts with what DESERVES attention, marking already-summarized content as read. Read-only + mark-read.
#
# The Baileys bridge in connectors/whatsapp/bridge/ is OURS: derived from an MIT bridge (provenance and licence in
# its VENDORED_FROM.md and LICENSE), patched throughout (// ZAELAR-PATCH), and it presents itself as Zaelar. The
# classifier is SHARED (connectors/messaging) and LOCAL by default — nothing personal leaves the machine.
#
# Modules: bridge/ (Node, vendored) · bridge_proc (lifecycle+QR) · client (HTTP) · service (engine). Triage, the
# unified store, proactive notice, brief, and tag dispatch live in connectors/messaging/ (common to all platforms).
# Bridge config is in config.py.
#
