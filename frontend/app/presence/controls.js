// controls.js — the customiser's knobs, grouped (V2-928). Labels and option names are i18n keys:
// `presence.grp.<group>`, `presence.ctl.<path>`, `presence.opt.<value>` (an unknown option shows its own id).
import { SHAPES, TEXTURES, EYES, BROWS, MOUTHS, NOSES, EARS, HAIRS, MUZZLES, EXTRAS } from "./creator.js?v=1";

const S = (path, opts) => ({ path, kind: "select", opts });
const Rg = (path, min, max, step = 0.01) => ({ path, kind: "range", min, max, step });
const Cl = (path) => ({ path, kind: "color" });
const Ck = (path) => ({ path, kind: "check" });

export const CONTROLS = [
  ["head", [S("head.shape", SHAPES), Rg("head.w", 0.75, 1.35), Rg("head.h", 0.8, 1.25), Cl("head.skin"), Cl("head.skin2"),
    Rg("head.volume", 0, 1), Rg("head.opacity", 0.2, 1), Rg("head.outline", 0, 0.06, 0.005), Cl("head.outlineColor")]],
  ["texture", [S("head.texture", TEXTURES), Rg("head.tex", 0, 1), Rg("head.texScale", 0.5, 2, 0.05)]],
  ["eyes", [S("eyes.type", EYES), Rg("eyes.size", 0.6, 1.8), Rg("eyes.gap", 0.7, 1.3), Rg("eyes.y", -0.6, 0.6),
    Cl("eyes.iris"), Cl("eyes.sclera"), Cl("eyes.lens"), Ck("eyes.lashes")]],
  ["brows", [S("brows.type", BROWS), Rg("brows.size", 0.5, 2), Cl("brows.color")]],
  ["mouth", [S("mouth.type", MOUTHS), Rg("mouth.size", 0.5, 1.9), Cl("mouth.color"), Cl("mouth.tongue")]],
  ["nose", [S("nose.type", NOSES), Rg("nose.size", 0.5, 1.8), Cl("nose.color")]],
  ["ears", [S("ears.type", EARS), Cl("ears.color"), Cl("ears.inner")]],
  ["hair", [S("hair.type", HAIRS), Cl("hair.color")]],
  ["details", [S("muzzle.type", MUZZLES), Cl("muzzle.color"), Rg("cheeks.blush", 0, 1), Ck("cheeks.freckles"), Ck("cheeks.whiskers"),
    S("extra.type", EXTRAS), Cl("extra.color")]],
];

export const getP = (o, p) => p.split(".").reduce((x, k) => (x == null ? x : x[k]), o);
export const setP = (o, p, v) => { const ks = p.split("."); let x = o; for (let i = 0; i < ks.length - 1; i++) x = x[ks[i]] ||= {}; x[ks[ks.length - 1]] = v; };
