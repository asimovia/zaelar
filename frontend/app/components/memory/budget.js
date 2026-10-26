// ============================================================================
// memory/budget.js — what THIS browser is allowed to draw (V2-808).
//
// One install is one person, but the device that opens the viewer can be a phone or a big desktop screen. The
// tier is picked from what the browser reports (`navigator.deviceMemory` in GB — Chromium only, and capped at 8 —,
// `navigator.hardwareConcurrency`, and the viewport width) and decides two numbers the server is asked for: the
// node budget of the graph and the rows of one list page. The server clamps both again; this is the polite half.
// A missing reading never promotes a device: unknown memory is treated as «not more than a laptop».
// ============================================================================

export const TIERS = {
  phone: { tier: "phone", nodes: 300, rows: 50 },
  laptop: { tier: "laptop", nodes: 1500, rows: 100 },
  big: { tier: "big", nodes: 3000, rows: 200 },
};

export function deviceTier(env = {}) {
  const mem = Number(env.deviceMemory) || 0;
  const cores = Number(env.hardwareConcurrency) || 0;
  const width = Number(env.width) || 0;
  if ((width && width < 700) || (mem && mem <= 2) || (cores && cores <= 2)) return TIERS.phone;
  if (width >= 1600 && mem >= 8 && cores >= 8) return TIERS.big;
  return TIERS.laptop;
}

export function currentEnv() {
  const nav = typeof navigator !== "undefined" ? navigator : {};
  return { deviceMemory: nav.deviceMemory, hardwareConcurrency: nav.hardwareConcurrency,
           width: typeof window !== "undefined" ? window.innerWidth : 0 };
}

export const currentTier = () => deviceTier(currentEnv());
