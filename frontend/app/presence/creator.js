// creator.js — the PARAMETRIC avatar: one renderer, a spec of parts, endless combinations.
// A spec says what the head, skin, texture, eyes, brows, nose, mouth, ears, hair, cheeks, muzzle and extras look
// like; the rig (rig.js) still decides how they MOVE, so every combination talks, blinks and gestures the same way.
// Everything is drawn in face coordinates (u right, v up) and projected through the rig's 3D head, so ears, hair and
// textures turn with the head (with a little parallax between the surface and the silhouette).
import { SLOTS, addLayer, layerFor, isTall, DEFAULT_SPEC, merge, shapeOf, silhouetteUV, SHAPES, TEXTURES, EYES, BROWS, MOUTHS, NOSES, EARS, HAIRS, MUZZLES, EXTRAS, TAU, clamp, mix, rgba, lum, hash, poly, circle, oval } from "./kit.js?v=1";
import { texture } from "./textures.js?v=1";
import { ears, hair, extras } from "./parts-head.js?v=1";
import { muzzle, eyesAll, zaelarEye, brows, nose, mouthPart, cheeks } from "./parts-face.js?v=1";
export { SLOTS, addLayer, isTall, DEFAULT_SPEC, merge, mix, shapeOf, SHAPES, TEXTURES, EYES, BROWS, MOUTHS, NOSES, EARS, HAIRS, MUZZLES, EXTRAS };

// ---------------------------------------------------------------------------------------------------- the avatar
export function drawAvatar(ctx, G, spec) {
  const h = spec.head, r = G.r;
  // each slot: the registered layer if there is one, else the built-in drawing
  const L = (slot, builtin, front) => { const l = layerFor(slot, spec); l ? l.draw(ctx, G, spec, front) : builtin(ctx, G, spec, front); };
  const sil = silhouetteUV(spec).map(([u, v]) => G.proj(u, v, 0));
  L("extra", extras, false);
  L("hair", hair, false);
  L("ears", ears, false);
  // ---- the base: skin with a soft volume gradient lit from the upper-left (the light stays put while the head turns)
  const c = G.proj(0, 0, 0), R = c.s * Math.max(h.w, 1.15 * h.h);
  const lx = c.x - R * (0.35 + r.yaw * 0.6), ly = c.y - R * (0.4 - r.pitch * 0.6), v = h.volume;
  ctx.save();
  ctx.globalAlpha = h.opacity;
  if (h.opacity > 0.95 && v > 0.2) { ctx.shadowColor = "rgba(0,0,0,.28)"; ctx.shadowBlur = R * 0.18 * v; ctx.shadowOffsetY = R * 0.05 * v; }
  poly(ctx, sil);
  const g = ctx.createRadialGradient(lx, ly, R * 0.05, c.x, c.y, R * 1.15);
  g.addColorStop(0, mix(h.skin, "#ffffff", 0.45 * v)); g.addColorStop(0.45, h.skin); g.addColorStop(1, mix(h.skin, "#000000", 0.5 * v));
  ctx.fillStyle = g; ctx.fill();
  ctx.restore();
  ctx.save(); ctx.globalAlpha = Math.min(1, h.opacity + 0.2); texture(ctx, G, spec, sil); ctx.restore();
  if (h.outline > 0) { poly(ctx, sil); ctx.lineWidth = h.outline * G.R; ctx.strokeStyle = h.outlineColor; ctx.lineJoin = "round"; ctx.stroke(); }
  // ---- the layers on top
  L("ears", ears, true);
  L("muzzle", muzzle, true);
  cheeks(ctx, G, spec);
  L("eyes", eyesAll, true);
  L("brows", brows, true);
  L("nose", nose, true);
  L("mouth", mouthPart, true);
  L("hair", hair, true);
  L("extra", extras, true);
}

// the Zaelar logo eyes are layers too
for (const t of ["zaelar", "zaelar-kawaii", "zaelar-glow", "zaelar-light"])
  addLayer("eyes", t, { draw: (ctx, G, spec) => { for (const side of [-1, 1]) zaelarEye(ctx, G, spec, G.eye(side), side, t); } });

// drawing kit for layer packs (layers/*.js)
export const kit = { TAU, clamp, mix, rgba, lum, hash, poly, circle, oval, builtin: { ears, hair, extras, muzzle, eyes: eyesAll, brows, nose, mouth: mouthPart } };
