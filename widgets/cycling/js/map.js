// Cycling — a route drawn over OpenStreetMap tiles, the same approach as the map app (copied, not imported):
// no map library and no fetch, the tiles are plain <img> elements placed with Web-Mercator arithmetic, and the
// lines and dots sit in one SVG on top. The view fits what it is given (or follows a point at a fixed zoom), re-fits
// when the card changes shape, pans with one finger and zooms with + / −; a tap can be read back as a position.

import { txt, tt } from "./util.js";

const TILE = 256;
const TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const NS = "http://www.w3.org/2000/svg";

export function project(lat, lon, z) {
  const n = TILE * Math.pow(2, z);
  const s = Math.sin(Math.max(-85, Math.min(85, lat)) * Math.PI / 180);
  return { x: (lon + 180) / 360 * n, y: (0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)) * n };
}
export function unproject(x, y, z) {
  const n = TILE * Math.pow(2, z);
  const lon = x / n * 360 - 180;
  const lat = Math.atan(Math.sinh(Math.PI * (1 - 2 * y / n))) * 180 / Math.PI;
  return [lat, lon];
}

export function fit(points, w, h, pad = 32, maxZ = 16) {
  if (!points.length) return { z: 12, cx: project(40.4168, -3.7038, 12).x, cy: project(40.4168, -3.7038, 12).y };
  for (let z = maxZ; z > 1; z--) {
    const pts = points.map((p) => project(p[0], p[1], z));
    const xs = pts.map((p) => p.x), ys = pts.map((p) => p.y);
    if (Math.max(...xs) - Math.min(...xs) <= w - 2 * pad && Math.max(...ys) - Math.min(...ys) <= h - 2 * pad) {
      return { z, cx: (Math.max(...xs) + Math.min(...xs)) / 2, cy: (Math.max(...ys) + Math.min(...ys)) / 2 };
    }
  }
  const p = project(points[0][0], points[0][1], 2);
  return { z: 2, cx: p.x, cy: p.y };
}

// spec: {lines:[{pts, cls}], dots:[{at:[lat,lng], cls, label}], fitTo:[[lat,lng]…] | follow:{at, z}, onTap(latlng)}
// The camera is kept on `box._cyCam` once he pans or zooms, until `key` (what is drawn) changes.
export function tileMap(box, spec, key) {
  box.classList.add("cy-map");
  box.setAttribute("data-hpan", "");
  if (box._cyKey !== key) { box._cyKey = key; box._cyCam = null; }
  const w0 = () => box.clientWidth || 360, h0 = () => box.clientHeight || 220;
  const auto = () => spec.follow && spec.follow.at
    ? (() => { const p = project(spec.follow.at[0], spec.follow.at[1], spec.follow.z); return { z: spec.follow.z, cx: p.x, cy: p.y }; })()
    : fit(spec.fitTo || [], w0(), h0());
  const cam = () => box._cyCam || auto();

  const draw = () => {
    box.querySelectorAll(".cy-tile,.cy-ovl,.cy-attr").forEach((n) => n.remove());
    const w = w0(), h = h0(), { z, cx, cy } = cam();
    const ox = cx - w / 2, oy = cy - h / 2, max = Math.pow(2, z);
    for (let tx = Math.floor(ox / TILE); tx <= Math.floor((ox + w) / TILE); tx++) {
      for (let ty = Math.floor(oy / TILE); ty <= Math.floor((oy + h) / TILE); ty++) {
        if (ty < 0 || ty >= max) continue;
        const wx = ((tx % max) + max) % max;
        const img = document.createElement("img");
        img.className = "cy-tile"; img.alt = ""; img.loading = "lazy"; img.decoding = "async";
        img.src = TILES.replace("{z}", z).replace("{x}", wx).replace("{y}", ty);
        img.style.left = Math.round(tx * TILE - ox) + "px"; img.style.top = Math.round(ty * TILE - oy) + "px";
        box.insertBefore(img, box.firstChild);
      }
    }
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("class", "cy-ovl");
    svg.setAttribute("width", w); svg.setAttribute("height", h);
    const px = (ll) => { const p = project(ll[0], ll[1], z); return [p.x - ox, p.y - oy]; };
    for (const ln of spec.lines || []) {
      if (!ln.pts || ln.pts.length < 2) continue;
      const pl = document.createElementNS(NS, "polyline");
      pl.setAttribute("class", "cy-line " + (ln.cls || ""));
      pl.setAttribute("points", ln.pts.map((p) => px(p).map((v) => v.toFixed(1)).join(",")).join(" "));
      svg.appendChild(pl);
    }
    for (const d of spec.dots || []) {
      if (!d.at) continue;
      const [x, y] = px(d.at);
      const c = document.createElementNS(NS, "circle");
      c.setAttribute("class", "cy-dot " + (d.cls || ""));
      c.setAttribute("cx", x.toFixed(1)); c.setAttribute("cy", y.toFixed(1)); c.setAttribute("r", d.r || 7);
      if (d.label) { const t = document.createElementNS(NS, "title"); t.textContent = d.label; c.appendChild(t); }
      svg.appendChild(c);
    }
    box.appendChild(svg);
    box.appendChild(txt("div", "cy-attr", "© OpenStreetMap"));
    box._cyZ = z;
  };

  box.textContent = "";
  const ctl = txt("div", "cy-mapctl");
  [["+", 1, tt("zoom_in", null, "Zoom in")], [String.fromCharCode(0x2212), -1, tt("zoom_out", null, "Zoom out")]].forEach(([g, dz, label]) => {
    const b = txt("button", null, g); b.type = "button"; b.title = label; b.setAttribute("aria-label", label);
    b.onpointerdown = (e) => e.stopPropagation();
    b.onclick = (e) => {
      e.stopPropagation();
      const c = cam(), z = Math.max(2, Math.min(18, c.z + dz)), f = Math.pow(2, z - c.z);
      box._cyCam = { z, cx: c.cx * f, cy: c.cy * f }; draw();
    };
    ctl.appendChild(b);
  });
  box.appendChild(ctl);

  let drag = null;
  box.onpointerdown = (e) => { drag = { x: e.clientX, y: e.clientY, c: cam(), moved: false }; try { box.setPointerCapture(e.pointerId); } catch (_) {} };
  box.onpointermove = (e) => {
    if (!drag) return;
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (!drag.moved && Math.hypot(dx, dy) < 6) return;
    drag.moved = true;
    box._cyCam = { z: drag.c.z, cx: drag.c.cx - dx, cy: drag.c.cy - dy }; draw();
  };
  box.onpointerup = (e) => {
    const d = drag; drag = null;
    if (d && !d.moved && spec.onTap) {
      const r = box.getBoundingClientRect ? box.getBoundingClientRect() : { left: 0, top: 0 };
      const c = cam();
      spec.onTap(unproject(c.cx - w0() / 2 + (e.clientX - r.left), c.cy - h0() / 2 + (e.clientY - r.top), c.z));
    }
  };
  box.onpointercancel = () => { drag = null; };

  try { if (box._cyRO) box._cyRO.disconnect(); } catch (_) {}
  if (typeof ResizeObserver === "function") {
    let last = "";
    box._cyRO = new ResizeObserver(() => { const k = w0() + "x" + h0(); if (k !== last) { last = k; draw(); } });
    box._cyRO.observe(box);
  }
  draw();
  return { redraw: draw };
}

// The point of a polyline at a fraction 0..1 of its length (where a rival stands on the segment).
export function along(pts, frac) {
  if (!pts || pts.length < 2) return null;
  const R = 6371, rad = Math.PI / 180;
  const hav = (a, b) => { const dl = (b[0] - a[0]) * rad, dn = (b[1] - a[1]) * rad;
    const h = Math.sin(dl / 2) ** 2 + Math.cos(a[0] * rad) * Math.cos(b[0] * rad) * Math.sin(dn / 2) ** 2; return 2 * R * Math.asin(Math.sqrt(h)); };
  const lens = []; let total = 0;
  for (let i = 1; i < pts.length; i++) { const d = hav(pts[i - 1], pts[i]); lens.push(d); total += d; }
  if (total === 0) return pts[0];
  let target = total * frac;
  for (let i = 0; i < lens.length; i++) {
    if (target <= lens[i]) { const a = pts[i], b = pts[i + 1], t = lens[i] ? target / lens[i] : 0; return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]; }
    target -= lens[i];
  }
  return pts[pts.length - 1];
}
