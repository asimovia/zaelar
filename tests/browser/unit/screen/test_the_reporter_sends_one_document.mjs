// ============================================================================
// test_the_reporter_sends_one_document.mjs — the host side of a screen's ONE document (V2-907 T6).
//
// `frontend/app/widgets/screen-reporter.js` builds the document from a host ADAPTER and POSTs it to
// `/api/screen/report`. Measured here with a stub `fetch` and a stub document: the shape the engine's door takes
// (`widgets/screen_doc.write`), `n` going forward within a mount, changes coalesced, the same document not said
// twice, an order's answer flushed AT ONCE (no debounce: the engine is waiting on it), a lost answer said again,
// one POST in flight, a lost report tried again with backoff (V2-907 A2), a replaced mount taking the screen back,
// the beacon on `pagehide`, and `reportAll`.
// Run: node tests/browser/unit/screen/test_the_reporter_sends_one_document.mjs  (SCREEN_REPORTER=<path> for a disarm)
// ============================================================================
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const ENGINE = join(HERE, "..", "..", "..", "..");
let failures = 0;
const check = (name, ok, detail = "") => {
  if (ok) { console.log(`  ok   ${name}`); return; }
  failures++; console.log(`  FAIL ${name}${detail ? "\n       " + detail : ""}`);
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const handlers = {};
globalThis.document = { visibilityState: "visible", addEventListener: (k, f) => { handlers[k] = f; } };
globalThis.addEventListener = (k, f) => { handlers[k] = f; };
const SRC = process.env.SCREEN_REPORTER || join(ENGINE, "frontend/app/widgets/screen-reporter.js");
const { screenReporter, reportAll, DEBOUNCE_MS } = await import(pathToFileURL(SRC).href);

// a windows host: three cards, «agenda» minimised, «youtube» maximised in front
const host = { layout: "windows", ids: ["youtube", "results::c1", "agenda"],
  vis: { youtube: "front", "results::c1": "visible", agenda: "min" } };
const adapter = { layout: "windows", list: () => host.ids, vis: (id) => host.vis[id], layer: (id) => host.ids.indexOf(id),
  flags: (id) => (id === "youtube" ? { max: true } : {}), home: () => ({ shown: false, holds: [] }), panel: () => host.panel || "" };
const posts = [], beacons = [];
let status = 200, gate = null;
const fakeFetch = async (url, init) => { posts.push({ url, b: JSON.parse(init.body) });
  if (gate) await new Promise((r) => { gate.push(r); });
  return { status, json: async () => ({ ok: status === 200 }) }; };
const beacon = (url, body) => { beacons.push({ url, b: JSON.parse(body) }); return true; };

const r = screenReporter(adapter, { fetch: fakeFetch, beacon, device: "desktop:aaa" });
await sleep(30);
check("a mount says its document at once, to the screen's one door", posts.length === 1 && posts[0].url === "/api/screen/report",
  JSON.stringify(posts));
const first = posts[0].b;
check("the body is {dev, mount, n, doc, acks, by}, n=1",
  first.dev === "desktop:aaa" && first.mount === r.mount && first.n === 1 && Array.isArray(first.acks) && "by" in first,
  JSON.stringify(first));
check("the document: layout, front derived from vis, open in layer order with vis and flags, home, panel",
  JSON.stringify(first.doc) === JSON.stringify({ layout: "windows", front: "youtube",
    open: [{ id: "youtube", layer: 0, vis: "front", max: true }, { id: "results::c1", layer: 1, vis: "visible" },
           { id: "agenda", layer: 2, vis: "min" }],
    panel: "", home: { shown: false, holds: [] } }), JSON.stringify(first.doc));

r.changed("hand"); await sleep(DEBOUNCE_MS + 60);
check("the same document is not said twice", posts.length === 1, String(posts.length));

host.ids = ["youtube", "results::c1"]; r.changed("hand");
host.panel = "chat"; r.changed("hand");
await sleep(DEBOUNCE_MS / 2);
check("a change waits for the coalescing window", posts.length === 1);
await sleep(DEBOUNCE_MS);
check("changes within the window are one POST, n goes forward, the cause rides it",
  posts.length === 2 && posts[1].b.n === 2 && posts[1].b.by === "hand" && posts[1].b.doc.panel === "chat"
  && posts[1].b.doc.open.length === 2, JSON.stringify(posts[1] && posts[1].b));

delete host.vis["results::c1"]; host.ids = ["youtube"];
const t0 = Date.now();
r.ack(41, true, "done");
await sleep(20);
check("an order's answer is flushed at once, never debounced", posts.length === 3 && Date.now() - t0 < DEBOUNCE_MS,
  String(posts.length));
check("…carrying {seq, ok, why} and the document as it stands after the order",
  JSON.stringify(posts[2].b.acks) === '[{"seq":41,"ok":true,"why":"done"}]' && posts[2].b.n === 3
  && posts[2].b.doc.open.length === 1, JSON.stringify(posts[2].b));

r.ack(42, false, "not_open"); await sleep(20);
r.ack(43, false, "made_up"); await sleep(20);
r.ack(44, false, "done"); await sleep(20);
check("a noop answer says it did nothing; an unknown why is a refusal; «done» without doing it is a refusal",
  JSON.stringify(posts.slice(3).map((p) => p.b.acks[0])) === JSON.stringify([
    { seq: 42, ok: false, why: "not_open" }, { seq: 43, ok: false, why: "refused" }, { seq: 44, ok: false, why: "refused" }]),
  JSON.stringify(posts.slice(3).map((p) => p.b.acks)));

// a lost POST keeps its answer for the next one
status = 500; const k = posts.length;
r.ack(45, true, "done"); await sleep(20);
status = 200;
await sleep(DEBOUNCE_MS * 4 + 60);
const resent = posts.slice(k + 1).find((p) => p.b.acks.some((a) => a.seq === 45));
check("a lost answer is said again in the next POST", !!resent, JSON.stringify(posts.slice(k).map((p) => p.b.acks)));

// one POST in flight; what piled up goes in the next
gate = []; const m = posts.length;
r.ack(46, true, "done"); await sleep(10);
r.ack(47, true, "done"); await sleep(10);
check("one POST in flight at a time", posts.length === m + 1, String(posts.length - m));
const g = gate; gate = null; g.forEach((f) => f()); await sleep(20);
check("…and the answer that waited goes in the next one",
  posts.length === m + 2 && posts[m + 1].b.acks.some((a) => a.seq === 47) && posts[m + 1].b.n > posts[m].b.n,
  JSON.stringify(posts.slice(m).map((p) => p.b)));

// a replaced mount the operator looks at takes the screen back
const m0 = r.mount; status = 409; r.ack(48, true, "done"); await sleep(20); status = 200; await sleep(30);
const back = posts[posts.length - 1].b;
check("a replaced mount in view takes the screen back: new mount, n=1, its answer kept",
  r.mount !== m0 && back.mount === r.mount && back.n === 1 && back.acks.some((a) => a.seq === 48), JSON.stringify(back));

// the page goes away: a beacon with the whole document
handlers.pagehide && handlers.pagehide();
check("pagehide sends the document by beacon", beacons.length === 1 && beacons[0].url === "/api/screen/report"
  && beacons[0].b.doc.layout === "windows" && beacons[0].b.n > back.n, JSON.stringify(beacons));
const p0 = posts.length;
handlers.visibilitychange && handlers.visibilitychange(); await sleep(30);
check("coming back into view says it all again", posts.length === p0 + 1, String(posts.length - p0));
reportAll(); await sleep(30);
check("a reopened event stream says it all again", posts.length === p0 + 2, String(posts.length - p0));

r.dispose(); r.changed("hand"); r.ack(49, true, "done"); await sleep(DEBOUNCE_MS + 30);
check("a disposed host reports nothing more", posts.length === p0 + 2);

// a lost REPORT (no order answer in it) is tried again, each wait twice the last, RETRIES times, then left for the
// next change — the engine's copy of the screen does not stay stale because the one POST that said it was lost
{
  const tries = []; const real = globalThis.setTimeout;
  const f2 = async (url, init) => { tries.push({ t: Date.now(), b: JSON.parse(init.body) }); return { status: 503 }; };
  globalThis.setTimeout = (fn, ms, ...a) => real(fn, Math.max(0, (ms || 0) / 50), ...a);   // 1 s + 2 s + 4 s → 140 ms
  const lost = screenReporter(adapter, { fetch: f2, device: "desktop:ccc" });
  await new Promise((r) => real(r, 500));
  globalThis.setTimeout = real;
  const gaps = tries.slice(1).map((x, i) => x.t - tries[i].t);
  check("a lost report with no answer in it is tried again, 3 times, each wait longer than the last",
    tries.length === 4 && gaps[1] > gaps[0] && gaps[2] > gaps[1] && tries.every((x) => x.b.doc.layout === "windows")
    && tries.every((x, i) => !i || x.b.n > tries[i - 1].b.n), JSON.stringify({ n: tries.length, gaps }));
  lost.dispose();
}

// a deck: the home in view, nothing in front
const deck = screenReporter({ layout: "deck", list: () => ["musica"], vis: () => "behind",
  home: () => ({ shown: true, holds: ["greeting", "now_playing"] }), panel: () => "" }, { fetch: fakeFetch, device: async () => "mobile:bbb" });
await sleep(30);
const dk = posts[posts.length - 1].b;
check("a deck on its home: front \"\", home shown with what it holds, the device read once",
  dk.dev === "mobile:bbb" && dk.doc.front === "" && dk.doc.home.shown === true && dk.doc.home.holds.join() === "greeting,now_playing",
  JSON.stringify(dk));
deck.dispose();

if (process.env.SCREEN_BODIES) (await import("node:fs")).writeFileSync(process.env.SCREEN_BODIES, JSON.stringify(posts.map((p) => p.b)));
console.log(failures ? `\n${failures} failed` : "\nall ok");
process.exit(failures ? 1 : 0);
