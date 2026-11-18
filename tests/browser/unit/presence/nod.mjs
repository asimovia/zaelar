// nod.mjs — the head's up-and-down (V2-928, 2026-11-18): how much it travels while the agent speaks and while he talks,
// and which replies open with a yes or a no (yes-no.js, with the bundles' own words). argv[2] = the presence folder,
// argv[3] = a JSON {es:{yes,no}, en:{yes,no}} of the bundle lines.
const base = new URL("file://" + process.argv[2].replace(/\/?$/, "/"));
const imp = (f) => import(new URL(f, base).href);
const { createRig } = await imp("rig.js?v=1");
const { polarity } = await imp("yes-no.js?v=1");
const W = JSON.parse(process.argv[3]);
let seed = 7; const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
const rig = createRig(rnd), sp = [], he = [];
for (let i = 0; i < 30 * 60; i++) sp.push(rig.update(1000 / 60, { visemes: { aa: Math.floor(i / 45) % 2 ? 0.9 : 0.15 }, mode: "speaking" }).pitch);
for (let i = 0; i < 30 * 60; i++) he.push(rig.update(1000 / 60, { visemes: {}, mode: "listening", hearing: true }).pitch);
const travel = (a) => a.slice(1).reduce((s, v, i) => s + Math.abs(v - a[i]), 0) / 30;      // rad per second
const said = {};
for (const [lang, lines] of Object.entries({
  es: ["Sí, claro que puedo.", "Sí.", "¡Claro! Ahora mismo.", "Por supuesto, dime.", "No, todavía no ha llegado.", "Qué va, no hay nada.",
       "No te preocupes, ya está.", "Si quieres lo miro.", "Noviembre empieza el lunes.", "Claramente es tarde."],
  en: ["Yes, I can.", "Sure! Right away.", "Of course, tell me.", "No, it has not arrived.", "Nope.",
       "Not now, later today.", "Yesterday it rained.", "Nobody called.", "Surely it will."] }))
  said[lang] = Object.fromEntries(lines.map((s) => [s, polarity(s, W[lang].yes, W[lang].no)]));
console.log(JSON.stringify({ speakTravel: travel(sp), hearTravel: travel(he), said }));
