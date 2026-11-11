// Map: the places data.py located, pinned and numbered over OpenStreetMap tiles, with the list beneath.
//
// No map library and no fetch: the tiles are plain <img> elements (the same way the image viewer shows remote
// pictures), positioned with Web-Mercator arithmetic. The view FITS every pin, and re-fits when the card changes
// shape — a drag, maximize, or the chat docking beside it — through one ResizeObserver per card. A pin or a row
// goes through ctx.action("select"), the same door as the voice. Place names come from outside: textContent only.

const TILE = 256;
// OpenStreetMap's own tiles, no key. CARTO's basemaps (used until 2026-09-28) started answering EVERY tile with an
// «API KEY REQUIRED» image — measured in the demo pass that day: the map card showed only that watermark.
const TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";

function injectStyles(){
  if(document.getElementById("hb-map-css"))return;
  const s=document.createElement("style"); s.id="hb-map-css"; s.textContent=`
  .hb-map{font-family:var(--sans,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif);
          color:var(--hb-ink,#F2F4F7);width:100%;box-sizing:border-box;height:100%;min-height:0;
          display:flex;flex-direction:column;gap:var(--sp-2,8px)}
  .hb-map .maptitle{font-size:var(--fs-title,1rem);font-weight:600;line-height:var(--hb-lh-tight,1.35)}
  .hb-map .mapview{position:relative;flex:1 1 auto;min-height:180px;overflow:hidden;
          border-radius:var(--hb-r-l,12px);border:1px solid var(--hb-line,rgba(255,255,255,.14));
          background:var(--hb-bg-soft,#272D35)}
  .hb-map .maptile{position:absolute;width:256px;height:256px;user-select:none;-webkit-user-drag:none;pointer-events:none}
  .hb-map .mappin{position:absolute;transform:translate(-50%,-100%);display:flex;flex-direction:column;
          align-items:center;cursor:pointer;z-index:2;background:none;border:none;padding:0;font:inherit}
  .hb-map .mappin b{display:flex;align-items:center;justify-content:center;min-width:26px;height:26px;
          border-radius:13px;background:var(--hb-accent,#AE90FF);color:var(--canvas,#16191E);font-size:.8rem;
          font-weight:700;box-shadow:0 1px 4px rgba(0,0,0,.45);border:2px solid #fff}
  .hb-map .mappin.is-on b{background:var(--hb-warn,#F2CE6B);transform:scale(1.2)}
  .hb-map .mappin i{width:2px;height:8px;background:#fff;box-shadow:0 1px 2px rgba(0,0,0,.4)}
  .hb-map .mappin:focus-visible b{box-shadow:var(--hb-focus-ring,0 0 0 2px #AE90FF)}
  .hb-map .mapattr{position:absolute;right:4px;bottom:2px;font-size:10px;color:#333;
          background:rgba(255,255,255,.75);padding:0 4px;border-radius:3px;z-index:3}
  .hb-map .maplist{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:var(--sp-1,4px)}
  .hb-map .maprow{display:flex;gap:var(--sp-2,8px);align-items:baseline;text-align:left;cursor:pointer;
          font:inherit;color:inherit;background:transparent;border:1px solid transparent;
          border-radius:var(--hb-r-s,8px);padding:4px 8px}
  .hb-map .maprow:hover{background:var(--hb-hover,#3C434F)}
  .hb-map .maprow:focus-visible{outline:none;box-shadow:var(--hb-focus-ring,0 0 0 2px #AE90FF)}
  .hb-map .maprow.is-on{background:color-mix(in srgb,var(--hb-accent,#AE90FF) 18%,transparent);
          border-color:color-mix(in srgb,var(--hb-accent,#AE90FF) 55%,transparent)}
  .hb-map .maprow b{flex:none;font-size:var(--fs-caption,.86rem)}
  .hb-map .maprow span{font-size:var(--fs-caption,.86rem);font-weight:600}
  .hb-map .maprow small{display:block;font-size:var(--fs-micro,.8rem);color:var(--hb-muted,#A7B0BE);font-weight:400}
  .hb-map .mapempty{font-size:var(--fs-caption,.86rem);color:var(--hb-muted,#A7B0BE);padding:var(--sp-4,16px) 0}
  /* The base map is ALWAYS drawn (V2-877 #8: a sentence over black read as broken): empty, it is the world or his
     area, with the one request that fills it in a note over the top. One finger PANS the map — the view carries
     [data-hpan], so the phone deck leaves that swipe to it and still pages from the screen's edge (V2-124). */
  .hb-map .mapview{touch-action:none;cursor:grab}
  .hb-map .mapview.is-drag{cursor:grabbing}
  .hb-map .mapnote{position:absolute;left:var(--sp-3,12px);right:var(--sp-3,12px);top:var(--sp-3,12px);z-index:4;
          padding:var(--sp-3,12px) var(--sp-4,16px);border-radius:var(--hb-r-l,12px);
          background:color-mix(in srgb,var(--hb-bg,#1F242B) 92%,transparent);border:1px solid var(--hb-line,rgba(255,255,255,.14));
          font-size:var(--fs-ui,.95rem);line-height:var(--hb-lh,1.55);color:var(--hb-ink,#F2F4F7);pointer-events:none}
  .hb-map .mapctl{position:absolute;right:var(--sp-2,8px);bottom:var(--sp-5,24px);z-index:4;display:flex;flex-direction:column;
          gap:var(--sp-1,4px)}
  .hb-map .mapctl button{width:44px;height:44px;border-radius:var(--hb-r-m,10px);border:1px solid var(--hb-line,rgba(255,255,255,.14));
          background:color-mix(in srgb,var(--hb-bg,#1F242B) 92%,transparent);color:var(--hb-ink,#F2F4F7);font:600 20px/1 var(--sans,system-ui);
          cursor:pointer;display:flex;align-items:center;justify-content:center;padding:0}
  .hb-map .mapctl button:focus-visible{outline:none;box-shadow:var(--hb-focus-ring,0 0 0 2px #AE90FF)}
  /* On the phone the map takes the page above its list; rows are 44pt. */
  .zm-scroll .hb-map{min-height:100%}
  .zm-scroll .hb-map .mapview{min-height:min(60vh,520px)}
  .zm-scroll .hb-map .maprow{min-height:44px;align-items:center}
  .zm-scroll .hb-map .mappin b{min-width:30px;height:30px;border-radius:15px}
  `; document.head.appendChild(s);
}

let _T = null;
function tt(key, params, fb){
  try{
    if(_T){ const s=_T("widgets.map."+key, params); if(s && s!=="widgets.map."+key) return s; }
  }catch(_){}
  let s = fb;
  if(params) for(const k in params) s = s.split("{"+k+"}").join(String(params[k]));
  return s;
}
function txt(tag, cls, s){ const e=document.createElement(tag); if(cls)e.className=cls; if(s!=null)e.textContent=s; return e; }

// Web Mercator: degrees → world pixels at zoom z.
function project(lat, lon, z){
  const n = TILE * Math.pow(2, z);
  const s = Math.sin(Math.max(-85, Math.min(85, lat)) * Math.PI / 180);
  return { x: (lon + 180) / 360 * n, y: (0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)) * n };
}

// The deepest zoom at which every pin fits the box with a margin; one pin sits at street level.
export function fit(places, w, h, pad = 48){
  if(!places.length) return { z: 2, cx: 0, cy: 0 };
  let z = places.length === 1 ? 15 : 17;
  for(; z > 1; z--){
    const pts = places.map(p => project(p.lat, p.lon, z));
    const xs = pts.map(p => p.x), ys = pts.map(p => p.y);
    if(Math.max(...xs) - Math.min(...xs) <= w - 2 * pad && Math.max(...ys) - Math.min(...ys) <= h - 2 * pad){
      return { z, cx: (Math.max(...xs) + Math.min(...xs)) / 2, cy: (Math.max(...ys) + Math.min(...ys)) / 2 };
    }
  }
  const p = project(places[0].lat, places[0].lon, 1);
  return { z: 1, cx: p.x, cy: p.y };
}

// Where the camera starts: every pin fitted; with no pin, his area at city level, else the whole world.
export function home(places, area, w, h){
  if(places.length) return fit(places, w, h);
  if(area && typeof area.lat === "number" && typeof area.lon === "number"){
    const p = project(area.lat, area.lon, 11); return { z: 11, cx: p.x, cy: p.y };
  }
  const z = w > 700 ? 3 : 2, n = TILE * Math.pow(2, z);
  return { z, cx: n / 2, cy: n / 2 };
}

function drawMap(view, places, selected, ctx, cam){
  view.querySelectorAll(".maptile,.mappin,.mapattr").forEach(n => n.remove());
  const w = view.clientWidth || 600, h = view.clientHeight || 360;
  const { z, cx, cy } = cam;
  const ox = cx - w / 2, oy = cy - h / 2;             // world pixel at the view's top-left
  const max = Math.pow(2, z);
  const tx0 = Math.floor(ox / TILE), ty0 = Math.floor(oy / TILE);
  const tx1 = Math.floor((ox + w) / TILE), ty1 = Math.floor((oy + h) / TILE);
  const subs = "abcd";
  for(let tx = tx0; tx <= tx1; tx++){
    for(let ty = ty0; ty <= ty1; ty++){
      if(ty < 0 || ty >= max) continue;
      const wx = ((tx % max) + max) % max;
      const img = document.createElement("img");
      img.className = "maptile"; img.alt = ""; img.loading = "lazy"; img.decoding = "async";
      img.src = TILES.replace("{s}", subs[(wx + ty) % 4]).replace("{z}", z).replace("{x}", wx).replace("{y}", ty);
      img.style.left = Math.round(tx * TILE - ox) + "px"; img.style.top = Math.round(ty * TILE - oy) + "px";
      view.insertBefore(img, view.firstChild);
    }
  }
  places.forEach((p, i) => {
    const pt = project(p.lat, p.lon, z);
    const pin = document.createElement("button");
    pin.type = "button";
    pin.className = "mappin" + (selected === i + 1 ? " is-on" : "");
    pin.style.left = Math.round(pt.x - ox) + "px"; pin.style.top = Math.round(pt.y - oy) + "px";
    pin.title = p.name;
    pin.setAttribute("aria-label", `${i + 1}. ${p.name}`);
    pin.appendChild(txt("b", null, String(i + 1)));
    pin.appendChild(document.createElement("i"));
    pin.onclick = () => { try{ ctx && ctx.action && ctx.action("select", { item: String(i + 1) }); }catch(_){} };
    view.appendChild(pin);
  });
  view.appendChild(txt("div", "mapattr", "© OpenStreetMap"));
}

export function render(el, data, ctx){
  _T = (ctx && typeof ctx.t === "function") ? ctx.t : null;
  injectStyles();
  el.className = "hb-map";
  el.textContent = "";
  const d = data || {};
  const places = (Array.isArray(d.places) ? d.places : []).filter(p => typeof p.lat === "number" && typeof p.lon === "number");
  if(d.title && places.length) el.appendChild(txt("div", "maptitle", String(d.title)));
  const view = txt("div", "mapview");
  view.setAttribute("data-hpan", "");
  el.appendChild(view);
  if(!places.length){
    view.appendChild(txt("div", "mapnote", tt("empty", null, "Ask to see places on a map — «show them on a map» — and they are pinned here.")));
  }
  const selected = Number(d.selected) || 0;

  // The CAMERA: where the map looks and how close. It starts at `home` and is HIS once he pans or zooms — kept on
  // the element across the re-renders a data push causes, dropped when the set of places changes.
  const key = places.map(p => `${p.lat},${p.lon}`).join("|");
  if(el._hbMapKey !== key){ el._hbMapKey = key; el._hbMapCam = null; }
  const cam = () => el._hbMapCam || home(places, d.area, view.clientWidth || 600, view.clientHeight || 360);
  const relayout = () => drawMap(view, places, selected, ctx, cam());

  const ctl = txt("div", "mapctl");
  const zoomBy = (dz) => {
    const c = cam(), z = Math.max(1, Math.min(18, c.z + dz)), f = Math.pow(2, z - c.z);
    el._hbMapCam = { z, cx: c.cx * f, cy: c.cy * f };
    relayout();
  };
  [["+", 1, tt("zoom_in", null, "Zoom in")], [String.fromCharCode(0x2212), -1, tt("zoom_out", null, "Zoom out")]].forEach(([g, dz, label]) => {
    const b = txt("button", null, g); b.type = "button"; b.title = label; b.setAttribute("aria-label", label);
    b.onclick = (e) => { e.stopPropagation(); zoomBy(dz); };
    b.onpointerdown = (e) => e.stopPropagation();
    ctl.appendChild(b);
  });
  view.appendChild(ctl);

  // One-finger PAN (pointer events: mouse and touch alike). A tap still reaches a pin: under 6px it is no drag.
  let drag = null;
  view.onpointerdown = (e) => { if(e.target.closest(".mappin")) return; drag = { x: e.clientX, y: e.clientY, c: cam(), moved: false };
    try{ view.setPointerCapture(e.pointerId); }catch(_){} };
  view.onpointermove = (e) => {
    if(!drag) return;
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if(!drag.moved && Math.hypot(dx, dy) < 6) return;
    drag.moved = true; view.classList.add("is-drag");
    el._hbMapCam = { z: drag.c.z, cx: drag.c.cx - dx, cy: drag.c.cy - dy };
    relayout();
  };
  view.onpointerup = view.onpointercancel = () => { drag = null; view.classList.remove("is-drag"); };

  if(places.length){
    const list = txt("div", "maplist");
    places.forEach((p, i) => {
      const row = txt("button", "maprow" + (selected === i + 1 ? " is-on" : ""));
      row.type = "button";
      row.appendChild(txt("b", null, `${i + 1}.`));
      const body = document.createElement("div");
      body.appendChild(txt("span", null, p.name));
      const sub = [p.address, p.note].filter(Boolean).join(" · ");
      if(sub) body.appendChild(txt("small", null, sub));
      row.appendChild(body);
      row.onclick = () => { try{ ctx && ctx.action && ctx.action("select", { item: String(i + 1) }); }catch(_){} };
      list.appendChild(row);
    });
    el.appendChild(list);
  }

  // Lay out once the card has a size, and again whenever it changes shape.
  try{ if(el._hbMapRO) el._hbMapRO.disconnect(); }catch(_){}
  if(typeof ResizeObserver === "function"){
    let last = "";
    el._hbMapRO = new ResizeObserver(() => {
      const k = `${view.clientWidth}x${view.clientHeight}`;
      if(k !== last){ last = k; relayout(); }
    });
    el._hbMapRO.observe(view);
  }
  relayout();
}
