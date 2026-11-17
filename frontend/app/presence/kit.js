// kit.js — the parametric face's vocabulary (part lists, the default spec), its drawing helpers and the LAYER
// registry: one base (rig + head) and everything on top is a layer in a slot (`addLayer`). V2-928.

export const SHAPES = ["ellipse", "round", "egg", "pear", "heart", "square", "alien", "blob", "ghost", "drop"];
export const TEXTURES = ["smooth", "bits", "pixels", "dots", "poly", "stripes", "spots", "scales", "fur", "wire",
  "lines", "hex", "noise", "glass", "stars", "panels", "gradient"];
export const EYES = ["porcelain", "dot", "round", "manga", "logo", "alien", "cat", "button", "happy", "sleepy", "visor",
  "cyclops", "led", "ring"];
export const BROWS = ["none", "line", "thick", "arch", "round", "unibrow", "angry"];
export const MOUTHS = ["filled", "line", "teeth", "cat", "beak", "lips", "fangs", "led", "wave", "o"];
export const NOSES = ["none", "dot", "button", "triangle", "heart", "line", "snout"];
export const EARS = ["none", "human", "cat", "fox", "bear", "mouse", "bunny", "dog", "elf", "fins"];
export const HAIRS = ["none", "tuft", "fringe", "bob", "long", "spiky", "mohawk", "curls", "buns", "afro", "beanie", "sprout"];
export const MUZZLES = ["none", "muzzle", "owl", "panda", "mask", "face"];
export const EXTRAS = ["none", "antenna", "antennae", "horns", "unicorn", "bow", "halo", "crown"];

// ---------------------------------------------------------------------------------------------------- ONE system
// One base — the rig (how it moves) + the head (silhouette, skin, texture) — and everything on top is a LAYER that
// sits in a SLOT. A face is just "which layer in each slot" (the spec). Adding a new animal, accessory or eye means
// registering a layer (`addLayer`), never touching the base or the pipeline below.
//   layer = { draw(ctx, G, spec, front), tall?: bool }   (ears/hair/extra are called twice: behind and in front)
export const SLOTS = ["extra", "hair", "ears", "muzzle", "cheeks", "eyes", "brows", "nose", "mouth"];
const LISTS = { eyes: EYES, brows: BROWS, mouth: MOUTHS, nose: NOSES, ears: EARS, hair: HAIRS, muzzle: MUZZLES, extra: EXTRAS };
const REG = {};
export function addLayer(slot, type, layer) {
  (REG[slot] ||= {})[type] = layer;
  const list = LISTS[slot]; if (list && !list.includes(type)) list.push(type);
}
export const layerFor = (slot, spec) => (REG[slot] || {})[(spec[slot] || {}).type];
const TALL = { ears: ["cat", "fox", "bunny", "mouse", "bear"], extra: ["antenna", "antennae", "horns", "unicorn", "halo", "crown"],
  hair: ["spiky", "mohawk", "afro", "buns", "sprout", "tuft", "beanie"] };
/** Does anything stick out above the head (so the stage leaves room for it)? */
export function isTall(spec) {
  return ["ears", "extra", "hair"].some((k) => { const t = spec[k].type, L = (REG[k] || {})[t]; return L ? !!L.tall : TALL[k].includes(t); });
}

export const DEFAULT_SPEC = {
  head: { shape: "ellipse", w: 1, h: 1, volume: 0.6, opacity: 1, skin: "#eef1f7", skin2: "#cfd6e4", texture: "smooth",
    tex: 0.5, texScale: 1, outline: 0, outlineColor: "#1e2433" },
  eyes: { type: "porcelain", size: 1, gap: 1, y: 0, iris: "#6b7cff", sclera: "#ffffff", lens: "#0a0e1e", lashes: false },
  brows: { type: "none", size: 1, color: "#2a3142" },
  mouth: { type: "filled", size: 1, color: "#2a3142", tongue: "#ff7eb6" },
  nose: { type: "none", size: 1, color: "#2a3142" },
  ears: { type: "none", color: "", inner: "#ffb3c7" },
  hair: { type: "none", color: "#3b2a1a" },
  muzzle: { type: "none", color: "#ffffff" },
  cheeks: { blush: 0, freckles: false, whiskers: false },
  extra: { type: "none", color: "#ffb14a" },
  bg: "#e9ecf2",
};

// ---------------------------------------------------------------------------------------------------- utils
export const TAU = Math.PI * 2;
export const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
export function rgb(hex) {
  const h = String(hex || "#000").replace("#", "");
  const f = h.length === 3 ? h.split("").map((c) => c + c).join("") : h.padEnd(6, "0");
  const n = parseInt(f.slice(0, 6), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
export function mix(a, b, t) {
  const A = rgb(a), B = rgb(b);
  return "#" + A.map((x, i) => Math.round(x + (B[i] - x) * t).toString(16).padStart(2, "0")).join("");
}
export const rgba = (hex, a) => { const [r, g, b] = rgb(hex); return `rgba(${r},${g},${b},${a})`; };
export const lum = (hex) => { const [r, g, b] = rgb(hex); return (0.299 * r + 0.587 * g + 0.114 * b) / 255; };
export const hash = (i, j, s = 0) => { const x = Math.sin(i * 127.1 + j * 311.7 + s * 74.7) * 43758.5453; return x - Math.floor(x); };
export function merge(base, over) {
  const out = JSON.parse(JSON.stringify(base));
  for (const k in over || {}) {
    if (over[k] && typeof over[k] === "object" && !Array.isArray(over[k])) out[k] = merge(out[k] || {}, over[k]);
    else out[k] = over[k];
  }
  return out;
}
export function poly(ctx, pts, close = true) {
  ctx.beginPath();
  pts.forEach((p, i) => (i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)));
  if (close) ctx.closePath();
}
export function circle(ctx, x, y, r) { ctx.beginPath(); ctx.arc(x, y, Math.max(0.1, r), 0, TAU); }
export function oval(ctx, x, y, rx, ry, rot = 0) { ctx.beginPath(); ctx.ellipse(x, y, Math.max(0.1, rx), Math.max(0.1, ry), rot, 0, TAU); }
const _glyph = new Map();
export function glyph(ch, color) {
  const key = ch + color;
  if (_glyph.has(key)) return _glyph.get(key);
  const c = document.createElement("canvas"); c.width = c.height = 32;
  const x = c.getContext("2d");
  x.fillStyle = color; x.font = "bold 26px ui-monospace, Menlo, monospace"; x.textAlign = "center"; x.textBaseline = "middle";
  x.fillText(ch, 16, 17);
  _glyph.set(key, c);
  return c;
}

// The rig's proportions for a spec (eye size/gap/height, mouth size, head size and depth).
export function shapeOf(spec) {
  const h = spec.head, e = spec.eyes, m = spec.mouth;
  const hx = h.w, hy = 1.15 * h.h, hz = 0.95 * (0.55 + 0.7 * h.volume);
  const k = e.size;
  return {
    head: { x: hx, y: hy, z: hz },
    eye: { x: 0.38 * e.gap * Math.min(1.25, hx), y: 0.1 + e.y * 0.25, w: 0.2 * k, h: 0.13 * k, k },
    mouth: { y: -0.42 * h.h + (e.y < -0.3 ? 0.04 : 0), k: m.size },
  };
}

// ---------------------------------------------------------------------------------------------------- silhouette
export function silhouetteUV(spec, n = 72) {
  const { w, h, shape } = spec.head, hx = w, hy = 1.15 * h, out = [];
  for (let i = 0; i < n; i++) {
    const a = (i / n) * TAU, c = Math.cos(a), s = Math.sin(a);
    let x = c, y = s;
    if (shape === "egg") { if (s < 0) x *= 1 - 0.14 * -s; }
    else if (shape === "pear") { x *= 1 + 0.14 * -s; if (s > 0) x *= 1 - 0.1 * s; }
    else if (shape === "heart") { if (s < 0) x *= 1 - 0.42 * (-s) ** 1.6; else y *= 0.95; }
    else if (shape === "alien") { if (s < 0) x *= 1 - 0.5 * (-s) ** 1.4; else { x *= 1.08; y *= 1.05; } }
    else if (shape === "drop") { if (s > 0) x *= 1 - 0.55 * s ** 2.5; y *= s > 0 ? 1.08 : 1; }
    else if (shape === "square") { const p = 4; x = Math.sign(c) * Math.abs(c) ** (2 / p); y = Math.sign(s) * Math.abs(s) ** (2 / p); x *= 0.97; y *= 0.95; }
    else if (shape === "blob") { const k = 1 + 0.045 * Math.sin(3 * a + 0.7) + 0.03 * Math.sin(5 * a); x *= k; y *= k; }
    else if (shape === "ghost") { if (s < 0) { y = -0.25 + s * 0.95 - 0.05 * Math.sin(c * 14); x *= 1.0; } }
    else if (shape === "round") { const m = Math.max(hx, hy) / hy; x = c * (hy / hx) * m * 0.92; y = s * 0.92 * m; }
    out.push([x * hx, y * hy]);
  }
  return out;
}

