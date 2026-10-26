// THE CLIENT NEVER OPENS A CARD FROM WORDS (V2-807 T-05).
//
// The browser used to run a fast path over every transcript, interim ones included: a verb-stem table
// (`abr|muestr|ensen|pon|saca|sube…`) plus a catalogue lookup of the same text, then `desktop.show(target)`.
// «pon también la web de punto com» — a signature correction — opened a browser, because `pon` is a stem and
// «web» an alias of the browser card; «¿puedes poner los interlineados… este mensaje» opened messaging. V2-776 F
// had already removed the lane's close and move branches for the same reason and kept open as «idempotent,
// harmless». An open puts a card on screen nobody ordered, and the engine then reads that canvas as context.
//
// The class: a canvas mutation is decided by the engine (verdict, action map, tool) and reaches the browser
// as a `widget show|close` event. This MOUNTS the real `sse.js` handler and replays words in several languages
// and scripts — non-orders full of stems and catalogue nouns AND true orders — through every channel a
// transcript arrives by (interim, spoken final + directed verdict, typed). The catalogue lookup answers a card
// for ANY text, the worst case. Not one show/close may come out of words; the engine's own op still opens.
import assert from "node:assert/strict";

const mem = new Map([["hb_lang", "es"], ["hb_i18n_es", JSON.stringify({})]]);
globalThis.localStorage = { getItem: k => (mem.has(k) ? mem.get(k) : null),
                            setItem: (k, v) => mem.set(k, String(v)), removeItem: k => mem.delete(k) };
// Every lookup «finds» a card: if any path still turned words into an open, this makes it fire.
const asked = [];
globalThis.fetch = async (url) => { asked.push(String(url));
  return { ok: true, json: async () => ({ match: "navegador" }), text: async () => "" }; };
globalThis.document = { documentElement: { lang: "es", setAttribute(){}, style: { setProperty(){} } },
                        querySelectorAll: () => [], querySelector: () => null, addEventListener(){},
                        dispatchEvent(){},
                        createElement: () => ({ style: {}, classList: { add(){}, remove(){} },
                                                appendChild(){}, setAttribute(){} }),
                        head: { appendChild(){} }, body: { appendChild(){} } };
globalThis.window = { addEventListener(){}, location: { href: "http://localhost/" } };
let sink = null;
globalThis.EventSource = class { constructor() { sink = this; } };

await import("../../../../frontend/app/core/store.js?v=2");
const { openSSE } = await import("../../../../frontend/app/services/sse.js?v=2");
const calls = [];
const rec = (name) => (...a) => { calls.push([name, ...a]); };
const desktop = { show: rec("show"), close: rec("close"), closeAll: rec("closeAll"), move: rec("move"),
                  refreshData(){}, createWidget(){}, modifyWidget(){}, onDeleted(){}, showConfirm(){},
                  hideConfirm(){}, resize(){}, fullscreen(){}, refreshRegistry(){}, list: () => [] };
openSSE(desktop);
assert.ok(sink && typeof sink.onmessage === "function", "the SSE handler did not mount");
const push = (o) => sink.onmessage({ data: JSON.stringify(o) });
const flush = () => new Promise(r => setTimeout(r, 30));

const SENTENCES = [
  // non-orders carrying an open stem and a catalogue noun (the measured two first)
  "Nombre completo está bien, y pon también la web de punto com",
  "¿puedes poner los interlineados? No queda bien este mensaje",
  "saca la firma de la segunda línea y sube el teléfono arriba",
  "muéstrale más cariño en el saludo del correo",
  "put the website in the signature too",
  "show some respect in the greeting of that email",
  "mets aussi le site web dans la signature",
  "署名にもウェブサイトを入れて",
  // true orders: the client must not act on these either — the engine does
  "abre la agenda", "muéstrame el navegador", "open the calendar", "ouvre l'agenda", "カレンダーを開いて",
  // and the closes V2-776 F already took away must stay gone
  "cierra todo", "close everything",
];

for (const text of SENTENCES) {
  push({ kind: "interim", role: "user", text });                                        // partial, while he talks
  push({ kind: "transcript", role: "user", label: "transcript", text });                // spoken final…
  push({ kind: "ambient", label: "👂 dirigido a zaelar", directed: true, window_open: true, window_s: 5, text });
  push({ kind: "transcript", role: "user", label: "text-injected chat", text });         // typed
  await flush();
  assert.deepEqual(calls, [], `«${text}» changed the canvas from the client: ${JSON.stringify(calls)}`);
}
assert.ok(!asked.some(u => u.includes("/widgets/identify")),
  "words must not even be looked up against the catalogue to pick a card: " + asked.join(", "));

// The engine's op still opens — this is the only door.
push({ kind: "widget", label: "show", id: "agenda", src: "flash" });
await flush();
assert.equal(calls.length, 1, "the engine's show must reach the canvas");
assert.equal(calls[0][0], "show");
assert.equal(calls[0][1], "agenda");

// …and the canvas's own report is never obeyed back (neither his hand nor client code, V2-807 T-15).
calls.length = 0;
for (const src of ["user", "client", "client:engine", "client:restore"]) {
  push({ kind: "widget", label: "show", id: "navegador", src });
  push({ kind: "widget", label: "close", id: "navegador", src });
}
await flush();
assert.deepEqual(calls, [], "a canvas report was obeyed as an order: " + JSON.stringify(calls));

console.log("ok — the client never opens or closes a card from words");
