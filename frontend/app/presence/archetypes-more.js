// archetypes-more.js — the animal, robot and fantasy archetypes (split from catalog.js by size). V2-928.
import { SKIN_H, HAIR_C, IRIS, PASTEL, NEON, BG_DARK, BG_LIGHT, ZEYES, ZIRIS, ZSOFT, ZDARK } from "./palettes.js?v=1";

export const MORE = [
  // ------------------------------------------------------------------ animals
  { id: "gato", cat: "animal", name: "Cat", spec: {
    head: { shape: "heart", skin: "#f4a259", skin2: "#c46d1e", volume: 0.55 },
    eyes: { type: "cat", size: 1.05, iris: "#2bb673" }, ears: { type: "cat", inner: "#ffb3c7" },
    nose: { type: "triangle", color: "#ff7eb6", size: 0.8 }, mouth: { type: "cat", color: "#5a2d0c" },
    cheeks: { whiskers: true }, muzzle: { type: "muzzle", color: "#fff1e0" }, bg: "#fff4e6" },
    vary: { "head.skin": ["#f4a259", "#9aa0a6", "#2b2b2b", "#ffffff", "#e8c39e", "#c9a27e"], "head.texture": ["smooth", "stripes", "spots", "fur"], "eyes.type": ["cat", "round", "button", "manga"], "eyes.iris": ["#2bb673", "#ffcc33", "#4f8cff", "#ff8c42"] } },
  { id: "perro", cat: "animal", name: "Dog", spec: {
    head: { shape: "pear", skin: "#c68642", skin2: "#8d5524", volume: 0.55 },
    eyes: { type: "button", size: 1.05 }, ears: { type: "dog", color: "#8d5524" }, brows: { type: "round", color: "#8d5524" },
    nose: { type: "heart", color: "#2b1b12" }, mouth: { type: "filled", color: "#5a2d0c" }, muzzle: { type: "muzzle", color: "#f6e0c4" }, bg: "#eef6ff" },
    vary: { "head.skin": ["#c68642", "#f1c27d", "#ffffff", "#3b3b3b", "#a0522d", "#e6be8a"], "ears.color": ["#8d5524", "#3b3b3b", "#a0522d", "#ffffff"], "head.texture": ["smooth", "spots", "fur"], "eyes.type": ["button", "round", "happy"] } },
  { id: "oso", cat: "animal", name: "Bear", spec: {
    head: { shape: "pear", skin: "#8d5524", skin2: "#5c3a21", volume: 0.6 },
    eyes: { type: "button", size: 0.9 }, ears: { type: "bear", inner: "#d9a066" }, nose: { type: "triangle", color: "#2b1b12" },
    mouth: { type: "line", color: "#2b1b12" }, muzzle: { type: "muzzle", color: "#d9a066" }, bg: "#f3ede4" },
    vary: { "head.skin": ["#8d5524", "#f1e3c6", "#3b2a1a", "#c68642", "#ffffff"], "head.texture": ["smooth", "fur"], "extra.type": ["none", "bow", "crown"], "eyes.type": ["button", "round", "happy"] } },
  { id: "panda", cat: "animal", name: "Panda", spec: {
    head: { shape: "round", skin: "#ffffff", volume: 0.55 },
    eyes: { type: "button", size: 0.85 }, ears: { type: "bear", color: "#1b1b1b", inner: "#3b3b3b" }, muzzle: { type: "panda", color: "#1b1b1b" },
    nose: { type: "triangle", color: "#1b1b1b", size: 0.8 }, mouth: { type: "cat", color: "#1b1b1b" }, bg: "#e6f4ea" },
    vary: { "muzzle.color": ["#1b1b1b", "#7b61ff", "#a0522d", "#e0457b"], "ears.color": ["#1b1b1b", "#7b61ff", "#a0522d"], "cheeks.blush": [0, 0.6], "head.texture": ["smooth", "fur", "noise"] } },
  { id: "conejo", cat: "animal", name: "Bunny", spec: {
    head: { shape: "round", skin: "#f2f2f2", volume: 0.5 },
    eyes: { type: "round", size: 1.1, iris: "#e0457b" }, ears: { type: "bunny", inner: "#ffb3c7" },
    nose: { type: "button", color: "#ff7eb6", size: 0.6 }, mouth: { type: "teeth", color: "#7a3b3b", size: 0.7 }, cheeks: { blush: 0.6, whiskers: true }, bg: "#f6eefc" },
    vary: { "head.skin": ["#f2f2f2", "#e6be8a", "#9aa0a6", "#5c3a21", "#ffd1dc"], "eyes.iris": IRIS, "eyes.type": ["round", "button", "manga"] } },
  { id: "zorro", cat: "animal", name: "Fox", spec: {
    head: { shape: "heart", skin: "#ff8c42", skin2: "#c45a12", volume: 0.55 },
    eyes: { type: "cat", size: 0.95, iris: "#ffcc33" }, ears: { type: "fox", inner: "#2b1b12" },
    nose: { type: "triangle", color: "#1b1b1b", size: 0.7 }, mouth: { type: "cat", color: "#3b1b0a" }, muzzle: { type: "face", color: "#fff1e0" }, bg: "#fff3e0" },
    vary: { "head.skin": ["#ff8c42", "#f2f2f2", "#9aa0a6", "#c45a12"], "eyes.type": ["cat", "button", "manga"], "head.texture": ["smooth", "fur"] } },
  { id: "buho", cat: "animal", name: "Owl", spec: {
    head: { shape: "square", skin: "#8d6e63", skin2: "#5d4037", volume: 0.5, texture: "scales", tex: 0.5 },
    eyes: { type: "round", size: 1.35, iris: "#ffb14a" }, muzzle: { type: "owl", color: "#efe1cf" },
    mouth: { type: "beak", color: "#ffb14a" }, ears: { type: "cat", inner: "#5d4037" }, brows: { type: "angry", color: "#3e2723" }, bg: "#1b1e2b" },
    vary: { "head.skin": ["#8d6e63", "#bdbdbd", "#f5f5f5", "#6d4c41", "#455a64"], "eyes.iris": ["#ffb14a", "#ffd54f", "#38d9ff", "#ff7043"], "head.texture": ["scales", "fur", "smooth"] } },
  { id: "rana", cat: "animal", name: "Frog", spec: {
    head: { shape: "pear", skin: "#7ccf5f", skin2: "#4d9a35", volume: 0.6, w: 1.1, h: 0.85, texture: "spots", tex: 0.35 },
    eyes: { type: "round", size: 1.3, y: 0.55, gap: 1.1, iris: "#1b1b1b" }, mouth: { type: "line", color: "#2e5d22", size: 1.7 }, cheeks: { blush: 0.5 }, bg: "#e6f5e0" },
    vary: { "head.skin": ["#7ccf5f", "#38d9ff", "#ff5fd2", "#ffd93b", "#ff8c42"], "head.texture": ["spots", "smooth", "dots"], "extra.type": ["none", "crown"] } },
  { id: "cerdito", cat: "animal", name: "Piglet", spec: {
    head: { shape: "round", skin: "#ffc2d1", skin2: "#f08ca8", volume: 0.55 },
    eyes: { type: "button", size: 0.9 }, ears: { type: "cat", color: "#f8a5bd", inner: "#ff7eb6" },
    nose: { type: "snout", color: "#ff9cb8", size: 1.2 }, mouth: { type: "line", color: "#a8325a" }, cheeks: { blush: 0.6 }, bg: "#fff0f4" },
    vary: { "head.skin": ["#ffc2d1", "#ffd6e0", "#f6a6b2", "#e8b4a0"], "head.texture": ["smooth", "spots", "noise"], "eyes.type": ["button", "happy", "round"] } },
  { id: "raton", cat: "animal", name: "Mouse", spec: {
    head: { shape: "heart", skin: "#9aa0a6", volume: 0.5 },
    eyes: { type: "button", size: 1 }, ears: { type: "mouse", inner: "#ffb3c7" }, nose: { type: "button", color: "#ff7eb6", size: 0.6 },
    mouth: { type: "teeth", color: "#3b3b3b", size: 0.6 }, cheeks: { whiskers: true }, bg: "#f2f4f7" },
    vary: { "head.skin": ["#9aa0a6", "#f2f2f2", "#c8a27e", "#5c5c5c"], "eyes.type": ["button", "round"], "cheeks.blush": [0, 0.6] } },
  { id: "pinguino", cat: "animal", name: "Penguin", spec: {
    head: { shape: "egg", skin: "#1f2a44", volume: 0.55 },
    eyes: { type: "round", size: 1, iris: "#1b1b1b" }, muzzle: { type: "face", color: "#ffffff" },
    mouth: { type: "beak", color: "#ffb14a", size: 0.9 }, cheeks: { blush: 0.5 }, bg: "#e3f2fd" },
    vary: { "head.skin": ["#1f2a44", "#37474f", "#1b1b1b", "#4f5b93"], "hair.type": ["none", "beanie", "tuft"], "eyes.type": ["round", "button", "happy"] } },
  { id: "tigre", cat: "animal", name: "Tiger", spec: {
    head: { shape: "pear", skin: "#ff9f1c", skin2: "#1b1b1b", volume: 0.55, texture: "stripes", tex: 0.9 },
    eyes: { type: "cat", size: 0.95, iris: "#ffd54f" }, ears: { type: "bear", inner: "#fff1e0" }, muzzle: { type: "muzzle", color: "#fff6ea" },
    nose: { type: "triangle", color: "#e0457b", size: 0.8 }, mouth: { type: "cat", color: "#1b1b1b" }, cheeks: { whiskers: true }, bg: "#fff5e6" },
    vary: { "head.skin": ["#ff9f1c", "#f5f5f5", "#ffcc80"], "head.texture": ["stripes", "spots"], "eyes.iris": ["#ffd54f", "#4f8cff", "#2bb673"] } },
  { id: "mono", cat: "animal", name: "Minimal", spec: {
    head: { shape: "round", skin: "#6d4c41", volume: 0.55 },
    eyes: { type: "round", size: 1, iris: "#5d4037" }, ears: { type: "human", color: "#6d4c41", inner: "#d7a98c" },
    muzzle: { type: "face", color: "#d7a98c" }, nose: { type: "dot", color: "#3e2723" }, mouth: { type: "teeth", color: "#3e2723" }, bg: "#f1f8e9" },
    vary: { "head.skin": ["#6d4c41", "#8d6e63", "#3e2723", "#a1887f"], "hair.type": ["none", "tuft"], "hair.color": ["#3e2723", "#6d4c41"] } },
  { id: "pollito", cat: "animal", name: "Chick", spec: {
    head: { shape: "round", skin: "#ffe066", skin2: "#ffc300", volume: 0.5, texture: "fur", tex: 0.3 },
    eyes: { type: "button", size: 0.9 }, mouth: { type: "beak", color: "#ff8c42", size: 0.8 }, hair: { type: "tuft", color: "#ffc300" }, cheeks: { blush: 0.6 }, bg: "#fffbe6" },
    vary: { "head.skin": ["#ffe066", "#fff3b0", "#ffd166"], "extra.type": ["none", "bow", "crown"], "eyes.type": ["button", "happy"] } },
  // ------------------------------------------------------------------ animals (2): pack-animals layers
  { id: "pato", cat: "animal", name: "Duck", spec: {
    head: { shape: "round", skin: "#fbfbfb", skin2: "#d9dde6", volume: 0.55, texture: "fur", tex: 0.15 },
    eyes: { type: "button", size: 0.95 }, mouth: { type: "bill", color: "#ff9f1c", size: 1 }, hair: { type: "tuft", color: "#c3cad6" },
    cheeks: { blush: 0.45 }, bg: "#e6f4ff" },
    vary: { "head.skin": ["#fbfbfb", "#ffe066", "#2f7d4a", "#8d6e4a", "#c9ccd6", "#fff3b0"], "mouth.color": ["#ff9f1c", "#ffc93c", "#ff7b54"],
      "eyes.type": ["button", "round", "happy", "zaelar-kawaii"], "extra.type": ["none", "bow", "crown", "headphones"], "bg": ["#e6f4ff", "#e9f7ef", "#fff8e1"] } },
  { id: "fenec", cat: "animal", name: "Fennec", spec: {
    head: { shape: "heart", skin: "#f1d3a6", skin2: "#d9a86a", volume: 0.55, texture: "fur", tex: 0.2, w: 0.95 },
    ears: { type: "fennec", inner: "#ffcfc4" }, muzzle: { type: "face", color: "#fff6e8" },
    eyes: { type: "round", size: 1.2, iris: "#3b2a1a" }, nose: { type: "button", color: "#2b1b12", size: 0.8 },
    mouth: { type: "cat", color: "#5a3825" }, cheeks: { blush: 0.35, whiskers: true }, bg: "#fff3e0" },
    vary: { "head.skin": ["#f1d3a6", "#f6e2c2", "#e8c08a", "#fbe9d0", "#d9b48a"], "eyes.type": ["round", "zaelar-kawaii", "manga", "button"],
      "eyes.iris": ["#3b2a1a", "#8b5a2b", "#2bb673", "#b366ff"], "head.texture": ["fur", "smooth", "dots"], "ears.inner": ["#ffcfc4", "#ffd9a8", "#f5b8c4"] } },
  { id: "lemur", cat: "animal", name: "Lemur", spec: {
    head: { shape: "round", skin: "#9b9ba6", skin2: "#6b6b78", volume: 0.55, texture: "fur", tex: 0.3 },
    ears: { type: "cat", color: "#7a7a86", inner: "#3a3a44" }, muzzle: { type: "lemur", color: "#fbfbfd" },
    eyes: { type: "round", size: 1.35, iris: "#ff9f1c" }, nose: { type: "button", color: "#1b1b22", size: 0.75 },
    mouth: { type: "line", color: "#1b1b22", size: 0.6 }, bg: "#eef0f2" },
    vary: { "eyes.iris": ["#ff9f1c", "#ffc93c", "#ff7b54", "#ffd166"], "eyes.type": ["round", "zaelar-kawaii", "manga"], "head.skin": ["#9b9ba6", "#a9a9b4", "#8a8a96", "#b8a89a"], "mouth.type": ["line", "filled", "cat"] } },
  { id: "titi", cat: "animal", name: "Marmoset", spec: {
    head: { shape: "round", skin: "#8a6d55", skin2: "#5a4535", volume: 0.55, texture: "fur", tex: 0.35 },
    ears: { type: "monkey", inner: "#f0c9a8" }, muzzle: { type: "face", color: "#f3d2b3" }, extra: { type: "tufts", color: "#ffffff" },
    eyes: { type: "round", size: 1.25, iris: "#5a3825" }, nose: { type: "dot", color: "#3b2a1a" }, mouth: { type: "filled", color: "#5a2d1c", size: 0.7 },
    cheeks: { blush: 0.3 }, bg: "#f6efe6" },
    vary: { "head.skin": ["#8a6d55", "#6d5a4a", "#a08060", "#7a7068"], "eyes.type": ["round", "zaelar-kawaii", "button"], "extra.type": ["tufts", "tufts", "none", "bow"], "mouth.type": ["filled", "teeth", "o"] } },
  { id: "kiki", cat: "animal", name: "Kiki", spec: {
    head: { shape: "egg", skin: "#6d4c41", skin2: "#3e2723", volume: 0.6, texture: "fur", tex: 0.25 },
    ears: { type: "monkey", inner: "#f6d7b8" }, muzzle: { type: "face", color: "#f6d7b8" }, hair: { type: "tuft", color: "#6d4c41" },
    eyes: { type: "zaelar-kawaii", size: 1.05, iris: "#b07cff" }, nose: { type: "dot", color: "#3e2723" }, mouth: { type: "teeth", color: "#3e2723" },
    cheeks: { blush: 0.5 }, bg: "#fdf0e3" },
    vary: { "head.skin": ["#6d4c41", "#8d6e63", "#4e342e", "#a1887f", "#ff8c42"], "eyes.type": ["zaelar-kawaii", "round", "manga", "button"], "extra.type": ["none", "headphones", "crown", "bow"], "extra.color": ["#4f8cff", "#b366ff", "#ff6fae", "#ffd166"] } },
  { id: "cachorro", cat: "animal", name: "Puppy", spec: {
    head: { shape: "round", skin: "#f2d2a9", skin2: "#c79a6b", volume: 0.55, texture: "spots", tex: 0.25 },
    ears: { type: "floppy", color: "#8d5a3b", inner: "#5a3825" }, muzzle: { type: "muzzle", color: "#fff6ea" },
    eyes: { type: "button", size: 1.1 }, nose: { type: "button", color: "#2b1b12", size: 1.1 }, mouth: { type: "filled", color: "#3b2a1a", size: 0.75 },
    cheeks: { blush: 0.35 }, bg: "#fff3e0" },
    vary: { "head.skin": ["#f2d2a9", "#ffffff", "#c68642", "#3b2a1a", "#e6be8a", "#a0a0a8"], "ears.color": ["#8d5a3b", "#3b2a1a", "#e6be8a", "#5a3825", "#ffffff"],
      "head.texture": ["spots", "smooth", "fur"], "eyes.type": ["button", "round", "zaelar-kawaii", "happy"], "extra.type": ["none", "bow", "headphones"] } },
  { id: "husky", cat: "animal", name: "Husky", spec: {
    head: { shape: "heart", skin: "#6f7a8a", skin2: "#4a5260", volume: 0.55, texture: "fur", tex: 0.2 },
    ears: { type: "fox", color: "#5a6372", inner: "#f2f2f5" }, muzzle: { type: "face", color: "#f6f7fa" },
    eyes: { type: "round", size: 1.1, iris: "#38d9ff" }, nose: { type: "button", color: "#1b1b22" }, mouth: { type: "filled", color: "#1b1b22", size: 0.8 }, bg: "#e8f1fb" },
    vary: { "head.skin": ["#6f7a8a", "#3b3f4a", "#a0522d", "#c9ccd6"], "eyes.iris": ["#38d9ff", "#4f8cff", "#8b5a2b", "#2bb673"], "eyes.type": ["round", "zaelar-kawaii", "zaelar-glow"] } },
  { id: "gatito", cat: "animal", name: "Kitten", spec: {
    head: { shape: "round", skin: "#ffb26b", skin2: "#e07b2e", volume: 0.55, texture: "stripes", tex: 0.3 },
    ears: { type: "cat", inner: "#ffb3c7" }, muzzle: { type: "muzzle", color: "#fff3e6" },
    eyes: { type: "round", size: 1.25, iris: "#2bb673" }, nose: { type: "triangle", color: "#ff8fb8", size: 0.8 }, mouth: { type: "cat", color: "#5a2d0c" },
    cheeks: { whiskers: true, blush: 0.35 }, bg: "#fff4e6" },
    vary: { "head.skin": ["#ffb26b", "#c9c9d1", "#f5f0e6", "#8a8a96", "#e6be8a"], "eyes.iris": ["#2bb673", "#ffcc33", "#4f8cff", "#b366ff"], "eyes.type": ["round", "cat", "zaelar-kawaii", "manga"], "head.texture": ["stripes", "smooth", "spots"] } },
  { id: "siames", cat: "animal", name: "Siamese", spec: {
    head: { shape: "heart", skin: "#f3e6d6", skin2: "#cdb79e", volume: 0.5 },
    ears: { type: "cat", color: "#5a4535", inner: "#8a6d55" }, muzzle: { type: "muzzle", color: "#7a5c45" },
    eyes: { type: "cat", size: 1.1, iris: "#4f8cff" }, nose: { type: "triangle", color: "#3b2a1a", size: 0.7 }, mouth: { type: "cat", color: "#3b2a1a" },
    cheeks: { whiskers: true }, bg: "#eef2f8" },
    vary: { "eyes.iris": ["#4f8cff", "#38d9ff", "#7b61ff"], "eyes.type": ["cat", "round", "zaelar"], "extra.type": ["none", "bow", "crown"] } },
  { id: "gatonegro", cat: "animal", name: "Black cat", spec: {
    head: { shape: "round", skin: "#23242c", skin2: "#0f1016", volume: 0.6, texture: "fur", tex: 0.15 },
    ears: { type: "cat", inner: "#ff8fb8" }, eyes: { type: "cat", size: 1.2, iris: "#ffd166" },
    nose: { type: "triangle", color: "#ff8fb8", size: 0.7 }, mouth: { type: "cat", color: "#c9c9d6" }, cheeks: { whiskers: true }, bg: "#141522" },
    vary: { "eyes.iris": ["#ffd166", "#7cff6b", "#38d9ff", "#ff9f1c"], "eyes.type": ["cat", "round", "zaelar-glow"], "extra.type": ["none", "bow", "halo", "headphones"] } },
  // ------------------------------------------------------------------ robots
  { id: "robot", cat: "robot", name: "Robot", spec: {
    head: { shape: "square", skin: "#9fb3c8", skin2: "#5b6b7d", volume: 0.6, texture: "panels", tex: 0.8 },
    eyes: { type: "led", size: 1, iris: "#38d9ff" }, mouth: { type: "led", color: "#38d9ff" }, extra: { type: "antenna", color: "#ff5f5f" }, bg: "#0f1626" },
    vary: { "head.skin": ["#9fb3c8", "#ffd166", "#ef476f", "#06d6a0", "#ffffff", "#2b2d42"], "eyes.iris": NEON, "eyes.type": ["led", "ring", "visor", "logo"], "mouth.type": ["led", "wave", "line"] } },
  { id: "visorbot", cat: "robot", name: "Visor", spec: {
    head: { shape: "ellipse", skin: "#2a3352", skin2: "#4f8cff", volume: 0.7, texture: "lines", tex: 0.25 },
    eyes: { type: "visor", size: 1, iris: "#38d9ff" }, mouth: { type: "wave", color: "#38d9ff" }, bg: "#04060b" },
    vary: { "head.skin": ["#2a3352", "#f2f4f7", "#1b1b1b", "#3a1460"], "eyes.iris": NEON, "head.texture": ["lines", "hex", "smooth", "panels"] } },
  { id: "android", cat: "robot", name: "Android", spec: {
    head: { shape: "egg", skin: "#f2f4f7", skin2: "#9aa6b8", volume: 0.65, texture: "panels", tex: 0.5 },
    eyes: { type: "logo", size: 1.05, iris: "#b07cff" }, mouth: { type: "line", color: "#4f8cff" }, bg: "#e9ecf2" },
    vary: { "head.skin": ["#f2f4f7", "#1e2433", "#ffe9e0", "#e6f4ff"], "eyes.type": ["logo", "ring", "porcelain", "led"], "head.texture": ["panels", "smooth", "hex"] } },
  { id: "pixelbot", cat: "robot", name: "Pixelbot", spec: {
    head: { shape: "square", skin: "#7b61ff", skin2: "#ffffff", volume: 0.3, texture: "pixels", tex: 0.4 },
    eyes: { type: "led", size: 0.9, iris: "#ffffff" }, mouth: { type: "led", color: "#ffffff" }, bg: "#0d0b1e" },
    vary: { "head.skin": NEON.concat(["#7b61ff"]), "head.texture": ["pixels", "bits", "dots"], "head.skin2": ["#ffffff", "#000000", "#ffe2a3"] } },
  { id: "bitbot", cat: "robot", name: "Binary", spec: {
    head: { shape: "ellipse", skin: "#08111f", skin2: "#4f8cff", volume: 0.4, texture: "bits", tex: 0.8 },
    eyes: { type: "logo", size: 1.05, iris: "#b07cff" }, mouth: { type: "line", color: "#38d9ff" }, bg: "#020409" },
    vary: { "head.skin2": ["#4f8cff", "#7cff6b", "#b366ff", "#ffb14a"], "eyes.type": ["logo", "ring", "led"], "head.texture": ["bits", "dots", "pixels"] } },
  // ------------------------------------------------------------------ fantasy
  { id: "monstruo", cat: "fantasy", name: "Monster", spec: {
    head: { shape: "blob", skin: "#4f8cff", skin2: "#2a5bd7", volume: 0.65, texture: "fur", tex: 0.6 },
    eyes: { type: "cyclops", size: 1, iris: "#2bb673" }, mouth: { type: "fangs", color: "#1a2a5a", size: 1.4 }, extra: { type: "horns", color: "#fff1d6" }, bg: "#eaf2fb" },
    vary: { "head.skin": ["#4f8cff", "#ff5fd2", "#7cff6b", "#ff8c42", "#b366ff"], "eyes.type": ["cyclops", "round", "button"], "head.texture": ["fur", "spots", "smooth"] } },
  { id: "fantasma", cat: "fantasy", name: "Ghost", spec: {
    head: { shape: "ghost", skin: "#ffffff", skin2: "#c9d6ff", volume: 0.45, opacity: 0.8 },
    eyes: { type: "dot", size: 1.4 }, mouth: { type: "o", color: "#1e2433", size: 0.7 }, cheeks: { blush: 0.4 }, bg: "#1b1e2b" },
    vary: { "head.opacity": [0.8, 0.6, 0.95], "head.skin": ["#ffffff", "#e0f7ff", "#f3e5ff"], "extra.type": ["none", "halo", "bow"] } },
  { id: "dragon", cat: "fantasy", name: "Dragon", spec: {
    head: { shape: "heart", skin: "#e0457b", skin2: "#8a1c4a", volume: 0.6, texture: "scales", tex: 0.8 },
    eyes: { type: "cat", size: 1, iris: "#ffcc33" }, mouth: { type: "fangs", color: "#4a0f25" }, nose: { type: "dot", color: "#4a0f25" },
    extra: { type: "horns", color: "#ffe2a3" }, ears: { type: "fins", color: "#8a1c4a" }, bg: "#140a1e" },
    vary: { "head.skin": ["#e0457b", "#2bb673", "#4f8cff", "#ffb14a", "#1b1b1b"], "eyes.iris": ["#ffcc33", "#38d9ff", "#7cff6b"], "head.texture": ["scales", "hex", "poly"] } },
  { id: "dragoncito", cat: "fantasy", name: "Little dragon", spec: {
    head: { shape: "round", skin: "#7cd67c", skin2: "#3ea05a", volume: 0.6, texture: "scales", tex: 0.25 },
    eyes: { type: "zaelar-kawaii", size: 1, iris: "#b07cff" }, ears: { type: "fins", color: "#3ea05a" }, extra: { type: "horns", color: "#fff1d6" },
    nose: { type: "snout", color: "#9be29b", size: 0.8 }, mouth: { type: "filled", color: "#1f5c2a", size: 0.7 }, cheeks: { blush: 0.55 }, bg: "#eefbe9" },
    vary: { "head.skin": ["#7cd67c", "#7fc8ff", "#c9a0ff", "#ffb3d9", "#ffd166", "#ff8c6b"], "eyes.type": ["zaelar-kawaii", "round", "button", "manga"], "extra.type": ["horns", "spikes", "unicorn"], "head.texture": ["scales", "smooth", "dots"] } },
  { id: "dragonfuego", cat: "fantasy", name: "Fire dragon", spec: {
    head: { shape: "heart", skin: "#d93b2b", skin2: "#7a1410", volume: 0.65, texture: "scales", tex: 0.6 },
    eyes: { type: "cat", size: 1.05, iris: "#ffcc33" }, extra: { type: "spikes", color: "#ffb14a" }, ears: { type: "fins", color: "#7a1410" },
    nose: { type: "snout", color: "#b52a1c", size: 0.9 }, mouth: { type: "fangs", color: "#3a0805" }, bg: "#1a0806" },
    vary: { "head.skin": ["#d93b2b", "#ff6a1a", "#b8202a", "#2b2b35"], "extra.color": ["#ffb14a", "#ffd166", "#1b1b1b"], "eyes.type": ["cat", "zaelar-glow"], "head.texture": ["scales", "poly", "hex"] } },
  { id: "dragonhielo", cat: "fantasy", name: "Ice dragon", spec: {
    head: { shape: "egg", skin: "#bfe6ff", skin2: "#6fb5e8", volume: 0.7, texture: "glass", tex: 0.6 },
    eyes: { type: "zaelar-glow", size: 1.05, iris: "#38d9ff" }, extra: { type: "spikes", color: "#ffffff" }, ears: { type: "fins", color: "#8fd3ff" },
    nose: { type: "snout", color: "#a6dbff", size: 0.8 }, mouth: { type: "line", color: "#2b5d8a" }, bg: "#06101c" },
    vary: { "head.skin": ["#bfe6ff", "#e0f7ff", "#c9b6ff", "#a0ffd8"], "head.texture": ["glass", "hex", "poly", "stars"], "eyes.type": ["zaelar-glow", "zaelar", "ring"] } },
  { id: "dragonoriental", cat: "fantasy", name: "Eastern dragon", spec: {
    head: { shape: "egg", skin: "#e0453b", skin2: "#8a1c1c", volume: 0.6, texture: "scales", tex: 0.35, w: 1.05 },
    eyes: { type: "round", size: 1.1, iris: "#ffcc33" }, extra: { type: "horns", color: "#ffd166" }, ears: { type: "fins", color: "#ffd166" },
    brows: { type: "thick", color: "#ffd166" }, nose: { type: "snout", color: "#c43a30" }, mouth: { type: "teeth", color: "#3a0805" },
    cheeks: { whiskers: true }, bg: "#2a0a0a" },
    vary: { "head.skin": ["#e0453b", "#2bb673", "#4f8cff", "#ffd166"], "eyes.type": ["round", "cat", "zaelar"], "head.texture": ["scales", "hex"] } },
  { id: "slime", cat: "fantasy", name: "Slime", spec: {
    head: { shape: "drop", skin: "#7cff6b", skin2: "#ffffff", volume: 0.7, opacity: 0.65, texture: "glass", tex: 0.8 },
    eyes: { type: "dot", size: 1.2 }, mouth: { type: "filled", color: "#1f5c2a", size: 0.8 }, cheeks: { blush: 0.5 }, bg: "#0d1a12" },
    vary: { "head.skin": ["#7cff6b", "#38d9ff", "#ff5fd2", "#ffd93b", "#b366ff"], "eyes.type": ["dot", "happy", "button"] } },
  { id: "hada", cat: "fantasy", name: "Fairy", spec: {
    head: { shape: "heart", skin: "#ffe7f3", skin2: "#ffd1ec", volume: 0.5, texture: "stars", tex: 0.6 },
    eyes: { type: "manga", size: 1.15, iris: "#b366ff" }, ears: { type: "elf", inner: "#ffb3c7" }, mouth: { type: "line", color: "#e0457b", size: 0.7 },
    hair: { type: "long", color: "#c9b6ff" }, cheeks: { blush: 0.7 }, extra: { type: "crown", color: "#ffd166" }, bg: "#f6eefc" },
    vary: { "hair.color": ["#c9b6ff", "#ffd6a5", "#a0e7e5", "#ffaebc", "#f2f2f2"], "eyes.iris": IRIS, "extra.type": ["crown", "halo", "bow", "unicorn"] } },
  { id: "calabaza", cat: "fantasy", name: "Pumpkin", spec: {
    head: { shape: "pear", skin: "#ff8c1a", skin2: "#c45a00", volume: 0.65, w: 1.15, h: 0.9, texture: "lines", tex: 0.3 },
    eyes: { type: "happy", size: 1.2 }, mouth: { type: "teeth", color: "#3a1a00", size: 1.4 }, hair: { type: "sprout", color: "#4caf50" }, bg: "#1a1206" },
    vary: { "head.skin": ["#ff8c1a", "#ffb14a", "#7cff6b", "#b366ff"], "eyes.type": ["happy", "alien", "led"] } },
];
