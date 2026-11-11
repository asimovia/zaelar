# map — notes

- 2026-09-26 · Built for the operator's demo script («Find me three things I might enjoy doing this weekend» →
  «Show them on a map»); before it the agent said «I don't have a map widget».
- Places arrive by name + address/city; data.py geocodes them (Photon, Nominatim as stand-in — OpenStreetMap,
  no key) inside the 8 s action budget and never accepts invented coordinates from the model as a requirement.
- Tiles are plain <img> (CARTO Voyager, attribution drawn on the map); no map library, no fetch from widget.js.
- The view fits every pin and re-fits on resize (one ResizeObserver per card). Pins and rows select through
  ctx.action("select").
- 2026-11-11 V2-877 #8 / V2-876 P-41: the base map is ALWAYS drawn — empty, it opens on `area` (his `here`, rounded, from `view_data`) or the world, with the request in a note over it. Zoom +/− at the bottom-right corner (44pt); one-finger pan with pointer events, the view marked `[data-hpan]` so the phone deck leaves the swipe to it and still pages from the screen edge (V2-124). The camera survives data pushes and resets when the places change. Attribution is OpenStreetMap's (the CARTO line was stale since the tiles moved).
