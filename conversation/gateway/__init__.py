"""The effect gateway: the only producer of effects — seal per revision, authority per effect, outbox, holds.

Import from the modules (`gateway.outbox`, `gateway.authority`, `gateway.dispatch`, `gateway.seal`): the package
loads nothing itself, so a leaf like `gateway.seal` can be imported by the inbox without loading the outbox."""
