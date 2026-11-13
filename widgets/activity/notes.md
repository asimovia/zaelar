- 2026-11-12 V2-890 F1: created so a ride can be started by voice and recorded with the phone in a pocket — heart
  rate from a Bluetooth strap and the GPS, going on with the screen locked. The visible feature behind the native device
  bridge (`docs/modules/zaelar-device-bridge.md`).
- Decisions: `screens: shared` — a reflection of data; ONE screen reads the sensors (the one that `claim`s: the phone
  app, or the screen where he tapped Start), every other screen shows the same figures. A desktop browser never
  starts reading because of a request made elsewhere. No `runtime` declaration: it records an input, it produces no
  sound or picture, and stopping the agent does not end his ride — he ends it. No `background` cycle: the screen
  that owns the activity pushes batches of samples (`samples`, every 5 s; the missed ones in one batch when the
  phone screen comes back). A sample batch sent twice counts once (`seq`).
- Known limits: a voice «stop» while the phone is locked loses the last ≤5 s not yet sent; figures asked by voice
  while the phone is locked are as of its last batch; the route is a drawn trace, not a base map.
- 2026-11-13 V2-898: made a stable base app, NO new scope (operator: «stable, don't evolve it»). What the voice can
  ask: `start` (kind running · walking · cycling · driving — read from `kind`, `type` or a short word; with none the
  app asks, never a default ride), `stop`, the running figures and, at rest, the last 3 activities (both through the
  digest, card open). Settings made visible: the strap in use (name + Change; «forget» needs the device door, V2-902)
  and numbers in the person's locale (km stays metric). Charts only from stored data: heart-rate sparkline (last
  10 min), 7-day distance bars, a history row opens its summary. A reading we lack is «—»/`None`: no GPS keeps no
  distance, no barometer no climb. Sensors start BEFORE the claim (a screen that cannot read never holds the
  activity); a failure is per activity; the owner token lives per tab (`sessionStorage`) so a reload resumes. Rejected:
  a redesign onto `hb-btn`/house bar (out of scope); `data.py` stays stdlib-only (stdlib `logging`, not loguru).
