// HomeToday.js — the deck's HOME says what today holds (V2-876 rule 7, P-10: «Home shows today under the greeting»):
// a greeting by the hour, his next three appointments (the agenda card's own data, `/widgets/agenda/data`, read at most
// once a minute and only while the home is on screen), and what is playing — read from the open card that PRODUCES
// (the deck's V2-092 reading), never guessed. Each line taps through to its app. A line with nothing to say is not drawn;
// the «Talk to zaelar» hint stays below. No weather line: nothing on the engine keeps today's weather without a search,
// and a home that fetched one on every look would spend for a glance.
import { t } from "../../../app/core/i18n.js?v=1";
import * as store from "../../../app/core/store.js?v=2";

const EVERY_MS = 60000;
const hhmm = (m) => String(m.startTime || m.start || m.time || "").slice(0, 5);

/** The next `n` appointments from the agenda's data, at or after `now` (a Date). PURE — exported for the test. */
export function nextUp(data, now, n = 3) {
  const pad = (x) => String(x).padStart(2, "0");
  const today = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
  const nowKey = today + " " + pad(now.getHours()) + ":" + pad(now.getMinutes());
  return ((data && data.meetings) || [])
    .filter((m) => m && m.date && m.title && !m.deleted)
    .map((m) => ({ ...m, key: m.date + " " + (hhmm(m) || "00:00") }))
    .filter((m) => m.key >= nowKey || (m.date === today && !hhmm(m)))
    .sort((a, b) => (a.key < b.key ? -1 : a.key > b.key ? 1 : 0))
    .slice(0, n)
    .map((m) => ({ title: m.title, time: hhmm(m), day: m.date === today ? "" : m.date }));
}

function dayLabel(iso) {
  try {
    return new Intl.DateTimeFormat(store.lang() || "en", { weekday: "short", day: "numeric", timeZone: "UTC" })
      .format(new Date(iso + "T00:00:00Z"));
  } catch (_) { return iso; }
}

export function HomeToday() {
  const el = document.createElement("section");
  el.className = "zm-today";
  let at = 0, ups = [];
  const row = (cls, main, side, open) => {
    const b = document.createElement("button");
    b.className = "zm-today-row " + cls;
    const m = document.createElement("span"); m.textContent = main;
    const s = document.createElement("small"); s.textContent = side;
    b.append(s, m);
    b.onclick = open;
    return b;
  };
  const draw = (deck) => {
    const hr = new Date().getHours();
    const h = document.createElement("h2");
    h.textContent = t(hr < 6 || hr >= 21 ? "mobile.greet_night" : hr < 13 ? "mobile.greet_morning" : "mobile.greet_afternoon");
    const out = [h];
    if (ups.length) {
      const k = document.createElement("div"); k.className = "zm-today-k"; k.textContent = t("mobile.today_next");
      out.push(k, ...ups.map((u) => row("appt", u.title, (u.day ? dayLabel(u.day) + " · " : "") + (u.time || ""),
        () => deck.show("agenda", { by: "hand" }))));
    }
    const playing = deck.order.map((id) => deck.cards.get(id)).find((w) => w && deck._producing(w));
    if (playing) {
      const d = playing._data || {}, np = d.here || d.now_playing || {};
      const what = [np.title, np.artist].filter(Boolean).join(" · ") || playing.titleEl.textContent;
      out.push(row("play", what, "♪ " + t("mobile.producing"), () => deck._goTo(deck.order.indexOf(playing.id || ""), 0)));
    }
    el.replaceChildren(...out);
  };
  const refresh = (deck) => {
    draw(deck);
    if (Date.now() - at < EVERY_MS) return;
    at = Date.now();
    fetch("/widgets/agenda/data", { cache: "no-store" }).then((r) => (r.ok ? r.json() : null))
      .then((d) => { ups = nextUp(d, new Date()); draw(deck); }).catch(() => {});
  };
  return { el, refresh };
}
