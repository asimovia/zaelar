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
