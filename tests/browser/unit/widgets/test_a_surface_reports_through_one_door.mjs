// ============================================================================
// test_a_surface_reports_through_one_door.mjs — the card-side half of an app's reported state (V2-884 1a).
//
// `frontend/app/widgets/state-reporter.js` is THE reporter the three hosts give a card as `ctx.state`. Measured here
// with a stub `fetch`: a mount is a surface (its own id, its own `n` going forward, a FULL first snapshot); patches
// coalesce within 100 ms into one POST; a report carries the last revision the card APPLIED, never one it only
// received (`seen` alone acks nothing; `{applied: true}` sends the full snapshot that acks it); the answer's facts
// come back to the card. And the hosts: every `ctx` the desktop card, the activity rail and the phone's Deck build
// carries `state` from this one module (a host that forgets it is a card that can never report).
// Run: node tests/browser/unit/widgets/test_a_surface_reports_through_one_door.mjs
// ============================================================================
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const ENGINE = join(HERE, "..", "..", "..", "..");
let failures = 0;
const check = (name, ok, detail = "") => {
  if (ok) { console.log(`  ok   ${name}`); return; }
  failures++; console.log(`  FAIL ${name}${detail ? "\n       " + detail : ""}`);
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const { stateReporter } = await import(join(ENGINE, "frontend/app/widgets/state-reporter.js"));
const posts = [];
const fakeFetch = async (url, init) => { const b = JSON.parse(init.body); posts.push({ url, b });
  return { json: async () => ({ ok: true, facts: b.patch.muted ? ["audio_blocked"] : [] }) }; };

const a = stateReporter("youtube", "youtube", { fetch: fakeFetch, device: "desktop:aaa" });
const b = stateReporter("youtube", "youtube", { fetch: fakeFetch, device: "desktop:aaa" });
check("two mounts of one device are two surfaces", a.mount !== b.mount);
b.dispose();

a.seen({ epoch: "e1", rev: 3 });
const p1 = a.report({ playing: true });
a.report({ muted: true });
const facts = await p1;
check("patches within 100 ms are one POST", posts.length === 1, JSON.stringify(posts));
const first = posts[0].b;
check("the first report of a mount is FULL, n=1, to the app's door",
  first.full === true && first.n === 1 && posts[0].url === "/widgets/youtube/state" && first.dev === "desktop:aaa");
check("a revision only received is never acked", first.ack === null, JSON.stringify(first.ack));
check("the answer's facts come back to the card", JSON.stringify(facts) === '["audio_blocked"]');

await a.report({ volume: 40 });
const second = posts[1].b;
check("a later patch carries only what changed, n goes forward",
  second.full === false && second.n === 2 && JSON.stringify(second.patch) === '{"volume":40}', JSON.stringify(second));

await a.report({ muted: false }, { applied: true });
const third = posts[2].b;
check("applied: a FULL snapshot that acks the revision seen",
  third.full === true && third.ack && third.ack.rev === 3 &&
  third.patch.playing === true && third.patch.volume === 40 && third.patch.muted === false, JSON.stringify(third));

await a.report({ muted: false });
await sleep(150);
check("a value already said is not said again (the mount remembers it)", posts.length === 3);

await a.report({}, { forget: ["volume"] });
check("a field it can no longer vouch for is said apart from the patch",
  JSON.stringify(posts[3].b.forget) === '["volume"]' && !("volume" in posts[3].b.patch), JSON.stringify(posts[3].b));

a.dispose();
const late = await a.report({ playing: false });
await sleep(150);
check("a closed card reports nothing more (report after dispose)", posts.length === 4 && late === null);

// one POST in flight; a failed one makes the next a full snapshot; a replaced tab he looks at takes it back
let gate, calls = [];
const slow = (status, out) => async (url, init) => { calls.push(JSON.parse(init.body));
  await new Promise((r) => { gate = r; }); return { status, json: async () => out }; };
let mode = slow(200, { ok: true, facts: [] });
const c = stateReporter("youtube", "youtube", { fetch: (u, i) => mode(u, i), device: "desktop:aaa" });
c.report({ playing: true });
await sleep(150);
c.report({ volume: 10 });
await sleep(150);
check("one POST in flight at a time", calls.length === 1, String(calls.length));
mode = slow(500, null);
gate(); await sleep(20); gate(); await sleep(150);
mode = slow(200, { ok: true, facts: [] });
c.report({ volume: 11 });
await sleep(150); gate(); await sleep(20);
const afterFail = calls[calls.length - 1];
check("after a failed POST the next one is a full snapshot",
  afterFail.full === true && afterFail.patch.playing === true && afterFail.patch.volume === 11, JSON.stringify(afterFail));
const m0 = c.mount;
mode = slow(409, { ok: false, error: "a newer mount of this screen replaced this one" });
c.report({ volume: 12 });
await sleep(150); gate(); await sleep(20);
mode = slow(200, { ok: true, facts: [] });
await sleep(150); gate(); await sleep(20);
const back = calls[calls.length - 1];
check("a replaced mount he looks at takes the screen back with a new mount",
  c.mount !== m0 && back.mount === c.mount && back.full === true && back.n === 1, JSON.stringify(back));
c.dispose();

const { snapshotAll } = await import(join(ENGINE, "frontend/app/widgets/state-reporter.js"));
const d = stateReporter("youtube", "youtube", { fetch: fakeFetch, device: "desktop:aaa" });
await d.report({ playing: true });
const before = posts.length;
snapshotAll();
await sleep(150);
check("a reopened event stream makes every live mount say everything again",
  posts.length === before + 1 && posts[posts.length - 1].b.full === true);
d.dispose();

// ── the three hosts ──────────────────────────────────────────────────────────────────────────────────────────
const DESKTOP = readFileSync(join(ENGINE, "frontend/app/widgets/desktop.js"), "utf8");
const DECK = readFileSync(join(ENGINE, "frontend/mobile/app/shell/Deck.js"), "utf8");
const ctxBlocks = (src) => src.split(/const ctx\s*=\s*\{/).slice(1).map((s) => s.slice(0, 600));
const desk = ctxBlocks(DESKTOP), deck = ctxBlocks(DECK);
check("the desktop builds two card ctx (card, activity rail)", desk.length === 2, String(desk.length));
check("the phone builds one card ctx", deck.length === 1, String(deck.length));
check("every ctx carries `state` from the one reporter",
  [...desk, ...deck].every((b) => /state\s*:\s*\(patch, o\)\s*=>\s*rep\.report\(patch, o\)/.test(b)));
check("both host files import the one reporter",
  /import \{ mountState \} from "\.\/state-reporter\.js/.test(DESKTOP)
  && /import \{ mountState \} from "\.\.\/\.\.\/\.\.\/app\/widgets\/state-reporter\.js/.test(DECK));
check("the event stream's reopening calls snapshotAll",
  /sweepOnReopen\(_opens, snapshotAll\)/.test(readFileSync(join(ENGINE, "frontend/app/services/sse.js"), "utf8")));
check("a refresh tells the reporter the revision it brings and the host's own facts (C7)",
  /_rep\.seen\(data\._rev, data\._host\)/.test(DESKTOP.slice(DESKTOP.indexOf("async refreshData")))
  && /_rep\.seen\(data\._rev, data\._host\)/.test(DECK.slice(DECK.indexOf("async refreshData"))));

if (failures) { console.log(`\n${failures} failure(s)`); process.exit(1); }
console.log("\nall ok");
