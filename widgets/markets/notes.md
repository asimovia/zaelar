# markets — notes

- 2026-09-26 · Built for the operator's demo script («Show me a chart of Apple stock today» → «the last month
  instead» → «Close the chart»); before it the agent said «I can't actually display a chart here». One chart,
  prices only — no orders, portfolio or advice.
- Source: Yahoo Finance public chart + search endpoints, no key. Send a BARE `Mozilla/5.0` user-agent: a full
  browser UA without cookies gets 429 (measured). A 429 retries once on the twin host (query1 ↔ query2).
- Network only in `apply_action`; `view_data` serves the cache. Period tabs go through `ctx.action("range")`.
- The move is said by arrow + number, never colour alone.
- 2026-11-11 V2-877 #8 / V2-876 P-42: a PRICE question is the card's own (whenToUse + `show` desc say «what's Apple's stock price») — before, a quote went to the chat and the card stayed empty. Empty = a centred page with the request and a field that runs `show` by hand; on the phone (`.zm-scroll`) the chart takes the page and the period tabs are 44pt.
