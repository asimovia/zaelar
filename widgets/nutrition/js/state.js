// Nutrition — the card's own state on THIS screen (it outlives the re-render every data push causes).
// A screen change is ONE transition: every entry point (a tab, a voice `show`, opening a meal) goes through `go()`,
// which resets what could hide the main face (an open editor, an open meal), so no path forgets to.

export const S = {
  screen: "today",
  day: null,            // null = the logical today
  meal: null,           // the meal whose detail is open
  mode: null,           // "refine" | "edit" on the open meal
  draft: "",            // the capture text being typed (survives a re-render)
  manual: false,        // the capture's «enter numbers» face
  manualVals: {},
  photo: null,          // { file, url } picked for the capture
  busy: false,
  error: "",
  coachShots: [],       // [{ file, url }] up to five photos of a menu
  coachText: "",
  weightOpen: null,     // the body entry being edited
  moreBody: false,
  seenOrder: "",        // the last `view` order adopted, so a voice `show` moves the card once
  repaint: null,
};

export function go(screen, day, meal) {
  if (screen) S.screen = screen;
  if (day !== undefined) S.day = day || null;
  S.meal = meal || null;
  S.mode = null;
  S.weightOpen = null;
  S.error = "";
}

// The order the brain wrote (`show`): adopted when it changes, never re-applied over his own taps.
export function adoptOrder(view) {
  const v = view || {};
  const key = JSON.stringify([v.screen || "today", v.day || null, v.meal || null, v.n || 0]);
  if (key === S.seenOrder) return;
  const first = !S.seenOrder;
  S.seenOrder = key;
  if (first && !v.n) return;          // a fresh card opens on today, not on whatever a past order said
  go(v.screen || "today", v.day || null, v.meal || null);
}

export function repaint() { if (S.repaint) S.repaint(); }
