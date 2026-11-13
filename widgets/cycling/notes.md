- 2026-11-13 V2-901: created by porting the cycling area of the person's previous product so it works the same inside the agent:
  heart-rate zone setup, ride recording (GPS + strap heart rate + altitude through the device bridge, 5-s countdown,
  pause/resume, save or discard), trackpoints per ride, stats and 1-km splits, ride history with names and the town,
  ride page (route, splits, heart-rate and elevation profiles, segments crossed, GPS gaps), segments (create from a
  ride, rename, redo the path, recalculate, delete, PR, attempts), and the live ghost rider.
- Decisions:
  - `screens: shared`, the same claim pattern as `activity`: ONE screen reads the sensors (the phone app, or the screen
    where he tapped Start); a desktop never starts reading because of a request made elsewhere. Samples arrive in
    batches every 5 s (the missed ones in one batch when the locked phone comes back), deduplicated by `seq`.
  - The source's per-fix GPS pipeline (accuracy 30 m / 20 m while calibrating, 80 km/h outlier, 6-s window blended
    60/40 with the GPS speed, low-pass 0.65, persist every >5 s) runs in `recorder.py`, sample by sample in time
    order, so a batch handed over late gives the same ride. A pause is an interval of TIME, not a flag.
  - Trackpoints live in `store.data_dir("cycling")/rides/<id>.jsonl`, never in `state.json` (rewritten every save).
  - The maths are ported 1:1 with JavaScript rounding (`engine.jround`, half up). The live trace for the map is
    thinned (a point every ≥ 8 m, ≤ 1,500) instead of every fix.
  - Maps are OSM tiles as plain `<img>` with an SVG overlay (approach copied from `widgets/map`, not imported). No
    network from widget.js: details come through internal read actions (`ride_detail`, `segment_detail`).
  - The ghost runs in data.py on every accepted fix (so every screen and the voice see the same race); the rivals'
    per-second positions are computed in the widget (`js/ghost.js`).
  - Network only in actions, bounded: Open-Meteo (ride temperature, readiness window), Nominatim (town, ≥ 1.1 s
    apart), OSRM (a blackout rebuilt along the road; one routed gap per batch, the rest counted straight).
- Deliberate differences from the source (each one a bug or a host constraint):
  - A blackout's distance is counted ONCE (the source added the routed/straight stretch AND the direct step).
  - A saved ride keeps its average and max heart rate and climb (the source left them empty on save).
  - Deleting a ride gives its segments' PR back to the best remaining attempt (the source kept a deleted ride's PR).
  - The ride's temperature reads Open-Meteo's local hours with their UTC offset (the source compared them as UTC).
  - A heart rate older than 15 s is not «now» (the source kept showing the strap's last value).
  - No screen wake lock, no IndexedDB queue, no haptics: the native bridge keeps recording with the screen locked
    and buffers what the widget missed. Toasts are events said once on the screen that sees them.
  - Discard is one action with `confirm` (the voice asks); on the widget it is the source's two-step overlay.
- Known limits / phase I (V2-902): legs and food lights need the core's model seam and the Nutrition widget's meals
  (they say «not available yet»); not in the catalogue (`_BUILTINS`) and «ride» still routes to Activity; the
  two catalogue ratchets that need a row for a new widget; no Apple Health export of a ride.
- 2026-11-13: naming (operator): in user-facing strings and docs this is a «widget», never «app», «card» or «tarjeta»; «phone app» is the native phone application and stays.
