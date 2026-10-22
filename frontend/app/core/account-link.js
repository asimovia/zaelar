// account-link.js — the link to the cloud account page, built from the ONE url the engine knows (V2-785).
//
// The engine owns the url (`nucleo/cloud_account.account_url`, env `ZAELAR_ACCOUNT_URL`) and hands it to the
// interface in `/api/config` and `/api/energy`. Nothing here carries its own literal: until 2026-10-22 the desktop
// had one and the phone had a RELATIVE "/account", which in a hosted deployment pointed at the agent's own origin —
// a page that does not exist. Pure, so it is tested without a browser.

/** `url` + optional `#fragment` (replacing any fragment it had). Empty url → "" (self-host: no account page). */
export function accountLink(url, fragment = "") {
  const base = String(url || "").trim().split("#")[0];
  if (!base) return "";
  return fragment ? `${base}#${fragment}` : base;
}

/** The reason the out-of-energy notice should be open for, or "" when it should not. Pure: the decision the
 *  rendered test (and anyone reading the notice) relies on. A notice the person closed stays closed for THAT
 *  reason; a new exhaustion (a different reason, or after a top-up and a second run-out) opens it again. */
export function noticeReason(energy, closedFor = "") {
  const e = energy || {};
  if (!e.cloud || !e.exhausted) return "";
  const reason = String(e.exhausted.reason || "exhausted");
  return reason === closedFor ? "" : reason;
}
