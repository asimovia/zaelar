// catalog.js — the archetypes (one hand-made prototype per character) and the generator that turns each into many
// variations: same character, other palettes, textures, eyes, hair… Deterministic (seeded), so variation #7 of the
// fox is always the same fox.
import { DEFAULT_SPEC, merge } from "./creator.js?v=1";
import "./layers/pack-animals.js?v=1";   // layer pack: fennec/monkey/floppy ears, duck bill, lemur mask, spikes, glasses, headphones, tufts

export const CATEGORIES = [
  { id: "classic", name: "Classics" },
  { id: "zaelar", name: "Zaelar ✦" },
  { id: "human", name: "Humanoids" },
  { id: "alien", name: "Aliens" },
  { id: "animal", name: "Animals" },
  { id: "robot", name: "Robots" },
  { id: "fantasy", name: "Fantasy" },
  { id: "mine", name: "My faces" },
];
import { SKIN_H, HAIR_C, IRIS, PASTEL, NEON, BG_DARK, BG_LIGHT, ZEYES, ZIRIS, ZSOFT, ZDARK } from "./palettes.js?v=1";
import { MORE } from "./archetypes-more.js?v=1";

// vary: path → list of options (variation 0 is always the prototype itself)
const A = [
  // ------------------------------------------------------------------ Zaelar ✦ — the logo eye, friendly + futuristic
  { id: "zae-nube", cat: "zaelar", name: "Cloud", spec: {
    head: { shape: "round", skin: "#f4f6fb", skin2: "#d9e1f2", volume: 0.55, texture: "glass", tex: 0.25 },
    eyes: { type: "zaelar-kawaii", size: 1.05, iris: "#b07cff" }, mouth: { type: "filled", color: "#2a3142", size: 0.75 },
    cheeks: { blush: 0.45 }, bg: "#eef1fb" },
    vary: { "head.skin": ZSOFT, "eyes.iris": ZIRIS, "eyes.type": ZEYES, "head.texture": ["glass", "smooth", "dots", "hex"], "bg": BG_LIGHT } },
  { id: "zae-noche", cat: "zaelar", name: "Night", spec: {
    head: { shape: "ellipse", skin: "#141a33", skin2: "#4f8cff", volume: 0.7, texture: "stars", tex: 0.35 },
    eyes: { type: "zaelar-glow", size: 1.05, iris: "#b07cff", lens: "#060a18" }, mouth: { type: "wave", color: "#b07cff" }, bg: "#05070e" },
    vary: { "head.skin": ZDARK, "eyes.iris": ZIRIS, "head.texture": ["stars", "lines", "hex", "smooth"], "mouth.type": ["wave", "line", "led"], "eyes.type": ["zaelar-glow", "zaelar", "zaelar-kawaii"] } },
  { id: "zae-chip", cat: "zaelar", name: "Chip", spec: {
    head: { shape: "square", skin: "#e8ecf6", skin2: "#9aa6c8", volume: 0.55, texture: "panels", tex: 0.45 },
    eyes: { type: "zaelar", size: 1.05, iris: "#b07cff" }, mouth: { type: "led", color: "#4f8cff" }, extra: { type: "antenna", color: "#ffb14a" },
    cheeks: { blush: 0.3 }, bg: "#e9ecf5" },
    vary: { "head.skin": ZSOFT, "mouth.type": ["led", "line", "filled", "wave"], "extra.type": ["antenna", "antennae", "none"], "eyes.type": ZEYES, "eyes.iris": ZIRIS } },
  { id: "zae-burbuja", cat: "zaelar", name: "Bubble", spec: {
    head: { shape: "round", skin: "#b9d4ff", skin2: "#ffffff", volume: 0.8, opacity: 0.55, texture: "glass", tex: 0.9 },
    eyes: { type: "zaelar-glow", size: 1.1, iris: "#b07cff" }, mouth: { type: "o", color: "#4f8cff", size: 0.7 }, bg: "#0a0f22" },
    vary: { "head.skin": ["#b9d4ff", "#d8c6ff", "#a8f0ff", "#ffd6f5", "#c6ffe8"], "head.opacity": [0.45, 0.55, 0.7], "eyes.type": ["zaelar-glow", "zaelar-kawaii"], "mouth.type": ["o", "filled", "wave"] } },
  { id: "zae-bit", cat: "zaelar", name: "Bits", spec: {
    head: { shape: "ellipse", skin: "#0a1122", skin2: "#4f8cff", volume: 0.5, texture: "bits", tex: 0.6 },
    eyes: { type: "zaelar-glow", size: 1.1, iris: "#b07cff" }, mouth: { type: "line", color: "#7aa8ff" }, bg: "#03050b" },
    vary: { "head.skin2": ["#4f8cff", "#b366ff", "#38d9ff", "#ffb14a"], "head.texture": ["bits", "pixels", "dots", "wire"], "eyes.type": ["zaelar-glow", "zaelar"], "mouth.type": ["line", "wave", "led"] } },
  { id: "zae-pixel", cat: "zaelar", name: "Pixel", spec: {
    head: { shape: "square", skin: "#7b61ff", skin2: "#4f8cff", volume: 0.35, texture: "pixels", tex: 0.35 },
    eyes: { type: "zaelar-light", size: 1.1, iris: "#7b61ff", sclera: "#ffffff" }, mouth: { type: "led", color: "#ffffff" }, bg: "#0d0b1e" },
    vary: { "head.skin": ["#7b61ff", "#4f8cff", "#b366ff", "#38d9ff", "#ff6fae"], "head.texture": ["pixels", "bits", "hex"], "eyes.type": ["zaelar-light", "zaelar", "zaelar-kawaii"] } },
  { id: "zae-gato", cat: "zaelar", name: "Catbot", spec: {
    head: { shape: "round", skin: "#eef1f7", skin2: "#c9d2e6", volume: 0.55, texture: "hex", tex: 0.2 },
    eyes: { type: "zaelar-kawaii", size: 1, iris: "#b07cff" }, ears: { type: "cat", inner: "#b366ff" },
    mouth: { type: "cat", color: "#2a3142" }, nose: { type: "triangle", color: "#ff8fb8", size: 0.7 }, cheeks: { blush: 0.5, whiskers: true }, bg: "#eceffa" },
    vary: { "head.skin": ZSOFT.concat(ZDARK.slice(0, 2)), "ears.inner": ["#b366ff", "#4f8cff", "#ffb14a", "#ff8fb8"], "eyes.type": ZEYES, "head.texture": ["hex", "smooth", "fur", "panels"] } },
  { id: "zae-osito", cat: "zaelar", name: "Bearbot", spec: {
    head: { shape: "round", skin: "#c9b6ff", skin2: "#8f7be0", volume: 0.6, texture: "smooth" },
    eyes: { type: "zaelar-kawaii", size: 0.95, iris: "#4f8cff" }, ears: { type: "bear", inner: "#ffe2a3" },
    muzzle: { type: "muzzle", color: "#efe9ff" }, nose: { type: "button", color: "#3a2f6a" }, mouth: { type: "filled", color: "#3a2f6a", size: 0.7 }, cheeks: { blush: 0.4 }, bg: "#f1ecff" },
    vary: { "head.skin": ["#c9b6ff", "#a8c6ff", "#ffd6a5", "#b4f8c8", "#f2f4f7", "#2a3352"], "head.texture": ["smooth", "fur", "panels", "dots"], "eyes.type": ZEYES, "ears.type": ["bear", "mouse", "bunny"] } },
  { id: "zae-alien", cat: "zaelar", name: "Zeta", spec: {
    head: { shape: "alien", skin: "#a0ffd8", skin2: "#38b8a0", volume: 0.6, h: 1.05 },
    eyes: { type: "zaelar", size: 1.3, iris: "#b07cff", y: -0.08 }, mouth: { type: "line", color: "#1f5c50", size: 0.6 }, extra: { type: "antennae", color: "#ffb14a" }, bg: "#07131a" },
    vary: { "head.skin": ["#a0ffd8", "#c9b6ff", "#a8f0ff", "#ffd6f5", "#b4f8c8", "#ffe2a3"], "eyes.type": ZEYES, "head.texture": ["smooth", "spots", "glass", "noise"], "extra.type": ["antennae", "antenna", "none"] } },
  { id: "zae-prisma", cat: "zaelar", name: "Prism", spec: {
    head: { shape: "egg", skin: "#8fa8ff", skin2: "#c08cff", volume: 0.55, texture: "poly", tex: 0.6 },
    eyes: { type: "zaelar-light", size: 1.05, iris: "#7b61ff", sclera: "#f6f4ff" }, mouth: { type: "filled", color: "#2a2363", size: 0.75 }, bg: "#100c26" },
    vary: { "head.skin": ["#8fa8ff", "#c08cff", "#7fd6ff", "#ffb3d9", "#ffd08a"], "head.texture": ["poly", "hex", "gradient", "glass"], "eyes.type": ZEYES } },
  { id: "zae-aura", cat: "zaelar", name: "Aura", spec: {
    head: { shape: "drop", skin: "#ffffff", skin2: "#b9c6ff", volume: 0.5, opacity: 0.85, texture: "gradient", tex: 0.5 },
    eyes: { type: "zaelar-kawaii", size: 1, iris: "#b07cff" }, mouth: { type: "filled", color: "#2a3142", size: 0.6 }, extra: { type: "halo", color: "#ffd66b" }, cheeks: { blush: 0.5 }, bg: "#1a1630" },
    vary: { "head.skin": ["#ffffff", "#f3eaff", "#e6f4ff", "#fff3e0"], "head.opacity": [0.7, 0.85, 1], "extra.type": ["halo", "crown", "none"], "eyes.type": ZEYES } },
  { id: "zae-peque", cat: "zaelar", name: "Tiny", spec: {
    head: { shape: "round", skin: "#f8d9c4", skin2: "#e7b89a", volume: 0.5 },
    eyes: { type: "zaelar-light", size: 1.1, iris: "#7b61ff", sclera: "#ffffff" }, brows: { type: "line", color: "#5a3825" },
    nose: { type: "dot", color: "#d99a7e" }, mouth: { type: "filled", color: "#9c3d3d" }, hair: { type: "tuft", color: "#5a3825" },
    ears: { type: "human", inner: "#f0a98d" }, cheeks: { blush: 0.6, freckles: true }, bg: "#fdf3e7" },
    vary: { "head.skin": SKIN_H, "hair.type": ["tuft", "curls", "fringe", "buns", "bob", "spiky"], "hair.color": HAIR_C, "eyes.type": ["zaelar-light", "zaelar-kawaii"], "eyes.iris": ZIRIS } },
  { id: "zae-sol", cat: "zaelar", name: "Sun", spec: {
    head: { shape: "round", skin: "#ffe2a3", skin2: "#ffb14a", volume: 0.6, texture: "dots", tex: 0.15 },
    eyes: { type: "zaelar-kawaii", size: 1.05, iris: "#b366ff" }, mouth: { type: "filled", color: "#7a3b10", size: 0.85 }, cheeks: { blush: 0.7 }, bg: "#fff6e6" },
    vary: { "head.skin": ["#ffe2a3", "#ffd6a5", "#ffc6b8", "#fff0b3"], "eyes.type": ZEYES, "extra.type": ["none", "crown", "antenna"], "head.texture": ["dots", "smooth", "stars"] } },
  { id: "zae-astro", cat: "zaelar", name: "Astro", spec: {
    head: { shape: "ellipse", skin: "#f2f4f7", skin2: "#9aa6b8", volume: 0.65, texture: "lines", tex: 0.25, outline: 0.02, outlineColor: "#4f8cff" },
    eyes: { type: "zaelar-glow", size: 1.05, iris: "#b07cff" }, mouth: { type: "wave", color: "#4f8cff" }, extra: { type: "antenna", color: "#ffb14a" }, bg: "#0b1020" },
    vary: { "head.skin": ["#f2f4f7", "#e6f4ff", "#2a3352", "#1b1f33"], "head.outlineColor": ["#4f8cff", "#b366ff", "#38d9ff"], "eyes.type": ["zaelar-glow", "zaelar", "zaelar-light"], "head.texture": ["lines", "panels", "smooth"] } },
  // ------------------------------------------------------------------ humans (stylized, never realistic)
  { id: "porcelana", cat: "human", name: "Porcelain face", spec: {}, vary: {
    "head.skin": ["#eef1f7", "#fdf6ec", "#f2e6ff", "#e6f4ff", "#ffeef2", "#e9f7ef"], "eyes.iris": IRIS,
    "eyes.size": [1, 0.85, 1.2, 1.35], "head.texture": ["smooth", "smooth", "glass", "noise", "dots"], "bg": BG_LIGHT } },
  { id: "kid", cat: "human", name: "Kid", spec: {
    head: { shape: "round", skin: "#f8d9c4", skin2: "#e7b89a", volume: 0.5 },
    eyes: { type: "round", size: 1.15, iris: "#4f8cff" }, brows: { type: "line", color: "#5a3825" },
    nose: { type: "dot", color: "#d99a7e" }, mouth: { type: "filled", color: "#9c3d3d" }, hair: { type: "tuft", color: "#5a3825" },
    cheeks: { blush: 0.7, freckles: true }, ears: { type: "human", inner: "#f0a98d" }, bg: "#fdf3e7" },
    vary: { "head.skin": SKIN_H, "hair.type": ["tuft", "curls", "fringe", "buns", "spiky", "bob"], "hair.color": HAIR_C, "eyes.iris": IRIS, "cheeks.freckles": [true, false] } },
  { id: "manga", cat: "human", name: "Manga", spec: {
    head: { shape: "heart", skin: "#ffe7d6", volume: 0.45, h: 0.98 },
    eyes: { type: "manga", size: 1.25, iris: "#7b61ff", y: -0.1 }, brows: { type: "line", color: "#3b2a4a", size: 0.8 },
    mouth: { type: "line", color: "#c0566b", size: 0.7 }, nose: { type: "line", color: "#e3a48c", size: 0.7 },
    hair: { type: "bob", color: "#3b2a4a" }, cheeks: { blush: 0.6 }, bg: "#f1e9f5" },
    vary: { "hair.color": HAIR_C, "eyes.iris": IRIS, "hair.type": ["bob", "long", "fringe", "spiky", "buns"], "head.skin": ["#ffe7d6", "#f8d9c4", "#f1c27d", "#c68642", "#fff4ec"] } },
  { id: "emoji", cat: "human", name: "Emoji", spec: {
    head: { shape: "round", skin: "#ffd93b", skin2: "#f4a300", volume: 0.65 },
    eyes: { type: "dot", size: 1.3 }, brows: { type: "none" }, mouth: { type: "teeth", color: "#5a2d0c", size: 1.3 }, bg: "#fff8e1" },
    vary: { "eyes.type": ["dot", "happy", "round", "button", "sleepy"], "mouth.type": ["teeth", "filled", "line", "o"], "head.skin": ["#ffd93b", "#ffcc4d", "#ffe066", "#ffb84d"], "cheeks.blush": [0, 0.6] } },
  { id: "comic", cat: "human", name: "Comic", spec: {
    head: { shape: "egg", skin: "#f1c27d", volume: 0.3, outline: 0.03, outlineColor: "#1b1b1b" },
    eyes: { type: "round", size: 1.05, iris: "#2bb673" }, brows: { type: "thick", color: "#1b1b1b" },
    nose: { type: "line", color: "#1b1b1b" }, mouth: { type: "line", color: "#1b1b1b" }, hair: { type: "spiky", color: "#1b1b1b" },
    ears: { type: "human", inner: "#d9915a" }, bg: "#ffe9a8" },
    vary: { "head.skin": SKIN_H, "hair.type": ["spiky", "mohawk", "fringe", "curls", "afro", "none"], "hair.color": HAIR_C, "brows.type": ["thick", "angry", "arch"], "bg": ["#ffe9a8", "#a8e6ff", "#ffc2d1", "#c8f7c5"] } },
  { id: "doll", cat: "human", name: "Doll", spec: {
    head: { shape: "round", skin: "#ffe9e0", volume: 0.55 },
    eyes: { type: "button", size: 1.2, lashes: true }, mouth: { type: "lips", color: "#e0457b", size: 0.6 },
    hair: { type: "long", color: "#e6be8a" }, cheeks: { blush: 0.9 }, extra: { type: "bow", color: "#ff6fae" }, bg: "#fde8ef" },
    vary: { "hair.color": HAIR_C, "extra.color": ["#ff6fae", "#7b61ff", "#38d9ff", "#ffb14a"], "head.skin": SKIN_H, "hair.type": ["long", "buns", "curls", "bob"] } },
  { id: "persona", cat: "human", name: "Person", spec: {
    head: { shape: "egg", skin: "#e0ac69", volume: 0.55, w: 0.95 },
    eyes: { type: "porcelain", size: 1, iris: "#8b5a2b" }, brows: { type: "line", color: "#3b2a1a" },
    nose: { type: "line", color: "#a0703f" }, mouth: { type: "filled", color: "#7a3b3b", size: 0.9 },
    hair: { type: "fringe", color: "#2b1b12" }, ears: { type: "human", inner: "#c98b55" }, bg: "#eef0f4" },
    vary: { "head.skin": SKIN_H, "hair.type": ["fringe", "bob", "long", "curls", "afro", "none", "beanie"], "hair.color": HAIR_C, "eyes.type": ["porcelain", "round", "dot"] } },
  // ------------------------------------------------------------------ avatars (stylized people, Memoji-like, never realistic)
  { id: "avatar", cat: "human", name: "Avatar", spec: {
    head: { shape: "egg", skin: "#e0ac69", skin2: "#b9824a", volume: 0.6 },
    eyes: { type: "round", size: 1.05, iris: "#5a3825" }, brows: { type: "line", color: "#2b1b12", size: 1.2 },
    nose: { type: "button", color: "#c98b55", size: 0.8 }, mouth: { type: "filled", color: "#7a3b3b", size: 0.9 },
    hair: { type: "curls", color: "#2b1b12" }, ears: { type: "human", inner: "#c98b55" }, bg: "#e9eef7" },
    vary: { "head.skin": SKIN_H, "hair.type": ["curls", "fringe", "bob", "long", "afro", "spiky", "buns", "none", "beanie", "mohawk"], "hair.color": HAIR_C,
      "eyes.iris": IRIS, "extra.type": ["none", "none", "glasses", "headphones"], "extra.color": ["#1e2433", "#4f8cff", "#b366ff", "#ff6fae"],
      "eyes.type": ["round", "porcelain", "zaelar-light"], "brows.type": ["line", "thick", "arch"], "cheeks.freckles": [false, true] } },
  { id: "gamer", cat: "human", name: "Gamer", spec: {
    head: { shape: "round", skin: "#f1c27d", skin2: "#c68642", volume: 0.6 },
    eyes: { type: "round", size: 1.1, iris: "#4f8cff" }, brows: { type: "thick", color: "#1f1f2e" }, nose: { type: "dot", color: "#c68642" },
    mouth: { type: "teeth", color: "#5a2d0c" }, hair: { type: "spiky", color: "#7b61ff" }, extra: { type: "headphones", color: "#38d9ff" }, bg: "#0f1226" },
    vary: { "head.skin": SKIN_H, "hair.color": HAIR_C, "hair.type": ["spiky", "mohawk", "fringe", "curls", "none"], "extra.color": NEON, "eyes.type": ["round", "zaelar-glow", "manga"] } },
  { id: "profe", cat: "human", name: "Teacher", spec: {
    head: { shape: "egg", skin: "#f8d9c4", skin2: "#e0b090", volume: 0.55 },
    eyes: { type: "dot", size: 1.2 }, brows: { type: "arch", color: "#8a8a8a" }, nose: { type: "button", color: "#e3a48c" },
    mouth: { type: "filled", color: "#9c3d3d", size: 0.8 }, hair: { type: "bob", color: "#d9d9d9" }, ears: { type: "human", inner: "#f0a98d" },
    extra: { type: "glasses", color: "#5a3825" }, cheeks: { blush: 0.4 }, bg: "#f4efe6" },
    vary: { "head.skin": SKIN_H, "hair.type": ["bob", "curls", "none", "fringe", "buns"], "hair.color": ["#d9d9d9", "#f2f2f2", "#5a3825", "#2b1b12"], "extra.color": ["#5a3825", "#1e2433", "#b366ff", "#e0457b"] } },
  // ------------------------------------------------------------------ aliens
  { id: "grey", cat: "alien", name: "Grey", spec: {
    head: { shape: "alien", skin: "#a9b3bf", skin2: "#7d8794", volume: 0.6, h: 1.08 },
    eyes: { type: "alien", size: 1.15, iris: "#38d9ff", y: -0.15 }, mouth: { type: "line", color: "#5d6670", size: 0.55 }, bg: "#0b1320" },
    vary: { "head.skin": ["#a9b3bf", "#9fc5a8", "#c8b6e2", "#d8d0c0", "#8fb8de"], "head.texture": ["smooth", "noise", "lines", "glass"], "eyes.iris": NEON } },
  { id: "verdito", cat: "alien", name: "Little green", spec: {
    head: { shape: "drop", skin: "#7cff6b", skin2: "#2bb673", volume: 0.7 },
    eyes: { type: "round", size: 1.2, iris: "#141826" }, mouth: { type: "teeth", color: "#1f5c2a" },
    extra: { type: "antennae", color: "#ffb14a" }, cheeks: { blush: 0.3 }, bg: "#0d0b1e" },
    vary: { "head.skin": ["#7cff6b", "#38d9ff", "#ff5fd2", "#ffb14a", "#b366ff", "#a0e7e5"], "eyes.type": ["round", "cyclops", "button", "manga"], "head.texture": ["smooth", "spots", "dots", "scales"], "extra.type": ["antennae", "antenna", "none"] } },
  { id: "cyclops", cat: "alien", name: "Cyclops", spec: {
    head: { shape: "blob", skin: "#b366ff", skin2: "#7b2fe0", volume: 0.65 },
    eyes: { type: "cyclops", size: 1, iris: "#ffb14a" }, mouth: { type: "fangs", color: "#3a1460" },
    extra: { type: "antenna", color: "#38d9ff" }, bg: "#120a24" },
    vary: { "head.skin": NEON.concat(PASTEL), "head.texture": ["smooth", "spots", "fur", "scales", "dots"], "mouth.type": ["fangs", "teeth", "filled", "wave"], "eyes.iris": IRIS } },
  { id: "crystal", cat: "alien", name: "Crystal", spec: {
    head: { shape: "ellipse", skin: "#8fd3ff", skin2: "#ffffff", volume: 0.8, opacity: 0.45, texture: "glass", tex: 0.9 },
    eyes: { type: "ring", size: 1.1, iris: "#b366ff" }, mouth: { type: "wave", color: "#ffb14a" }, bg: "#05070c" },
    vary: { "head.skin": ["#8fd3ff", "#c9b6ff", "#a0ffd8", "#ffd6f5", "#fff0a8"], "head.texture": ["glass", "hex", "poly", "lines"], "eyes.type": ["ring", "logo", "led"], "head.opacity": [0.35, 0.45, 0.6] } },
  { id: "reptil", cat: "alien", name: "Reptilian", spec: {
    head: { shape: "heart", skin: "#4caf50", skin2: "#2e7d32", volume: 0.6, texture: "scales", tex: 0.7 },
    eyes: { type: "cat", size: 1.1, iris: "#ffcc33" }, mouth: { type: "line", color: "#1b4d1e", size: 1.3 }, ears: { type: "fins", color: "#2e7d32" }, bg: "#0b1a10" },
    vary: { "head.skin": ["#4caf50", "#00897b", "#8bc34a", "#795548", "#5c6bc0"], "eyes.iris": ["#ffcc33", "#ff5722", "#38d9ff", "#b366ff"], "head.texture": ["scales", "spots", "hex"] } },
  { id: "estelar", cat: "alien", name: "Stellar", spec: {
    head: { shape: "ellipse", skin: "#1a1446", skin2: "#ffffff", volume: 0.5, texture: "stars", tex: 1 },
    eyes: { type: "logo", size: 1.1, iris: "#b07cff" }, mouth: { type: "line", color: "#b366ff" }, extra: { type: "halo", color: "#ffe2a3" }, bg: "#03030a" },
    vary: { "head.skin": ["#1a1446", "#0b2545", "#2a0f3a", "#06141f"], "eyes.type": ["logo", "ring", "alien", "happy"], "extra.type": ["halo", "none", "crown"] } },
  ...MORE,
];
export const ARCHETYPES = A;

// seeded RNG (mulberry32)
function rng(seed) {
  return () => { seed |= 0; seed = (seed + 0x6d2b79f5) | 0; let t = Math.imul(seed ^ (seed >>> 15), 1 | seed); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}
function setPath(o, path, v) { const ks = path.split("."); let x = o; for (let i = 0; i < ks.length - 1; i++) x = x[ks[i]]; x[ks[ks.length - 1]] = v; }

/** Build `n` variations per archetype. Variation 0 is the prototype exactly as designed. */
export function buildCatalog(n = 14) {
  const out = [];
  A.forEach((a, ai) => {
    const base = merge(DEFAULT_SPEC, a.spec);
    for (let i = 0; i < n; i++) {
      const spec = JSON.parse(JSON.stringify(base));
      if (i > 0) {
        const R = rng(ai * 1000 + i * 7919);
        for (const [path, opts] of Object.entries(a.vary || {})) if (R() < 0.7) setPath(spec, path, opts[Math.floor(R() * opts.length)]);
        spec.eyes.size = +(spec.eyes.size * (0.88 + R() * 0.28)).toFixed(2);
        spec.mouth.size = +(spec.mouth.size * (0.85 + R() * 0.3)).toFixed(2);
        spec.head.w = +(spec.head.w * (0.94 + R() * 0.12)).toFixed(2);
        spec.head.h = +(spec.head.h * (0.94 + R() * 0.12)).toFixed(2);
        if (spec.head.texture !== base.head.texture && spec.head.tex < 0.3) spec.head.tex = 0.5;
      }
      out.push({ id: `${a.id}-${i}`, cat: a.cat, name: i ? `${a.name} ${i + 1}` : a.name, spec });
    }
  });
  return out;
}
