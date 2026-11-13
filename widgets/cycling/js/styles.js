// Cycling — the card's stylesheet, injected once. Theme tokens only (every var() with its dark fallback), the
// component kit (hb-*) for buttons, panels, tabs and fields, and the `cy-` prefix for everything of its own.

export function injectStyles() {
  if (document.getElementById("hb-cycling-css")) return;
  const s = document.createElement("style"); s.id = "hb-cycling-css"; s.textContent = `
  .hb-cycling{font-family:var(--sans,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif);color:var(--hb-ink,#F2F4F7);
    width:100%;box-sizing:border-box;display:flex;flex-direction:column;gap:var(--sp-3,12px);position:relative;
    font-size:var(--fs-ui,.95rem);line-height:var(--hb-lh,1.55)}
  .hb-cycling .cy-panel{display:flex;flex-direction:column;gap:var(--sp-2,8px)}
  .hb-cycling .cy-title-row{display:flex;align-items:center;gap:var(--sp-2,8px);justify-content:space-between}
  .hb-cycling .cy-title{margin:0;font-size:var(--fs-title,1rem);font-weight:600;flex:1;min-width:0;overflow-wrap:anywhere}
  .hb-cycling .cy-title-input{flex:1;min-width:0}
  .hb-cycling .cy-note{font-size:var(--fs-caption,.86rem);color:var(--hb-muted,#A7B0BE);text-align:center}
  .hb-cycling .cy-left{text-align:left}
  .hb-cycling .cy-warn{color:var(--hb-warn,#FFC53D)}
  .hb-cycling .cy-muted{font-size:var(--fs-caption,.86rem);color:var(--hb-muted,#A7B0BE)}
  .hb-cycling .cy-start{font-size:1.05rem;font-weight:700;padding:var(--sp-3,12px);letter-spacing:.04em}
  .hb-cycling .cy-big{padding:var(--sp-3,12px);font-weight:700;letter-spacing:.04em;width:100%}
  .hb-cycling .cy-row2{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:var(--sp-2,8px)}
  .hb-cycling .cy-chips{display:flex;flex-wrap:wrap;gap:var(--sp-2,8px)}
  .hb-cycling .cy-cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:var(--sp-3,12px);align-items:start}
  .hb-cycling .cy-list{display:flex;flex-direction:column;gap:var(--sp-2,8px)}
  .hb-cycling .cy-zone-row{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:var(--sp-2,8px)}
  .hb-cycling .cy-zfield .hb-input{width:100%;box-sizing:border-box}
  .hb-cycling .cy-ride{display:flex;align-items:center;gap:var(--sp-2,8px);padding:var(--sp-2,8px) var(--sp-3,12px)}
  .hb-cycling .cy-rowbtn{flex:1;min-width:0;text-align:left;background:transparent;border:1px solid transparent;color:inherit;font:inherit;
    cursor:pointer;padding:var(--sp-1,4px) var(--sp-2,8px);border-radius:var(--hb-r-s,8px);display:flex;flex-direction:column;gap:2px}
  .hb-cycling .cy-rowbtn:hover{background:var(--hb-hover,#3C434F)}
  .hb-cycling .cy-rowbtn:focus-visible{outline:none;box-shadow:var(--hb-focus-ring,0 0 0 2px #AE90FF)}
  .hb-cycling .cy-row-top{display:flex;flex-wrap:wrap;align-items:baseline;gap:var(--sp-2,8px)}
  .hb-cycling .is-armed{color:var(--hb-risk,#FF7384)}
  .hb-cycling .cy-seggrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:var(--sp-2,8px)}
  .hb-cycling .cy-segcard{text-align:left;font:inherit;color:inherit;cursor:pointer;display:flex;flex-direction:column;gap:var(--sp-1,4px)}
  .hb-cycling .cy-segcard-t{font-size:var(--fs-caption,.86rem);overflow-wrap:anywhere}
  .hb-cycling .cy-segcard-v{display:flex;flex-wrap:wrap;gap:var(--sp-2,8px);font-size:var(--fs-micro,.8rem);color:var(--hb-muted,#A7B0BE)}
  .hb-cycling .cy-ready{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:var(--sp-2,8px)}
  .hb-cycling .cy-ready-cell{background:var(--hb-bubble,#313740);border:1px solid var(--hb-line-subtle,rgba(255,255,255,.09));
    border-radius:var(--hb-r-m,10px);padding:var(--sp-2,8px);display:flex;flex-direction:column;align-items:center;gap:2px;text-align:center}
  .hb-cycling .cy-ready-t{font-size:var(--fs-micro,.8rem);color:var(--hb-muted,#A7B0BE);text-transform:uppercase;letter-spacing:.05em}
  .hb-cycling .cy-ready-l{font-size:var(--fs-caption,.86rem);font-weight:600}
  .hb-cycling .cy-light{font-size:1.1rem;line-height:1}
  .hb-cycling .cy-light-green{color:var(--hb-ok,#3DDC97)} .hb-cycling .cy-light-yellow{color:var(--hb-warn,#FFC53D)}
  .hb-cycling .cy-light-red{color:var(--hb-risk,#FF7384)} .hb-cycling .cy-light-gray{color:var(--hb-muted,#A7B0BE)}
  .hb-cycling .cy-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(96px,1fr));gap:var(--sp-2,8px)}
  .hb-cycling .cy-stat{background:var(--hb-bubble,#313740);border:1px solid var(--hb-line-subtle,rgba(255,255,255,.09));border-radius:var(--hb-r-m,10px);
    padding:var(--sp-2,8px) var(--sp-3,12px)}
  .hb-cycling .cy-stat-lbl{font-size:var(--fs-micro,.8rem);color:var(--hb-muted,#A7B0BE);text-transform:uppercase;letter-spacing:.05em}
  .hb-cycling .cy-stat-val{font-size:1.35rem;font-weight:600;font-variant-numeric:tabular-nums}
  .hb-cycling .cy-stat.is-accent .cy-stat-val{color:var(--hb-accent,#AE90FF)}
  .hb-cycling .cy-speed{text-align:center}
  .hb-cycling .cy-speed-val{font-variant-numeric:tabular-nums;line-height:1}
  .hb-cycling .cy-sp-int{font-size:4.5rem;font-weight:700}
  .hb-cycling .cy-sp-dec{font-size:2rem;font-weight:600;color:var(--hb-muted,#A7B0BE)}
  .hb-cycling .cy-hr{background:var(--hb-bg-soft,#272D35);border:1px solid var(--hb-line,rgba(255,255,255,.14));border-radius:var(--hb-r-l,12px);
    padding:var(--sp-3,12px);display:flex;flex-direction:column;gap:var(--sp-2,8px)}
  .hb-cycling .cy-hr-top{display:flex;align-items:baseline;justify-content:center;gap:var(--sp-2,8px)}
  .hb-cycling .cy-hr-num{font-size:3rem;font-weight:700;font-variant-numeric:tabular-nums;color:var(--hb-c-red,#FF6259)}
  .hb-cycling .cy-hr-unit{color:var(--hb-muted,#A7B0BE)}
  .hb-cycling .cy-zbar{position:relative;height:12px;border-radius:6px;background:var(--hb-neutral,#8B98AC);opacity:.9}
  .hb-cycling .cy-zband{position:absolute;left:30%;width:40%;top:0;bottom:0;border-radius:6px;background:var(--hb-ok,#3DDC97)}
  .hb-cycling .cy-zmark{position:absolute;top:-4px;width:4px;height:20px;margin-left:-2px;border-radius:2px;background:var(--hb-ink,#F2F4F7)}
  .hb-cycling .cy-zone-above .cy-hr-unit,.hb-cycling .cy-zone-below .cy-hr-unit{color:var(--hb-warn,#FFC53D)}
  .hb-cycling .cy-tabs{display:flex}
  .hb-cycling .cy-blink{animation:cy-blink 1.2s steps(2,start) infinite}
  @keyframes cy-blink{to{color:var(--hb-warn,#FFC53D)}}
  .hb-cycling .cy-overlay{position:absolute;inset:0;z-index:5;background:color-mix(in srgb,var(--hb-bg,#1F242B) 96%,transparent);
    display:flex;flex-direction:column;align-items:center;justify-content:center;gap:var(--sp-3,12px);padding:var(--sp-4,16px);border-radius:var(--hb-r-l,12px)}
  .hb-cycling .cy-ov-lbl{font-size:var(--fs-title,1rem);color:var(--hb-muted,#A7B0BE);text-transform:uppercase;letter-spacing:.08em}
  .hb-cycling .cy-ov-num{font-size:6rem;font-weight:700;line-height:1;font-variant-numeric:tabular-nums}
  .hb-cycling .cy-ov-q{font-size:1.25rem;font-weight:700;text-align:center}
  .hb-cycling .cy-ov-hint{color:var(--hb-muted,#A7B0BE);text-align:center}
  .hb-cycling .cy-toast{background:color-mix(in srgb,var(--hb-accent,#AE90FF) 18%,transparent);border:1px solid color-mix(in srgb,var(--hb-accent,#AE90FF) 55%,transparent);
    border-radius:var(--hb-r-m,10px);padding:var(--sp-2,8px) var(--sp-3,12px);font-weight:600;text-align:center}
  .hb-cycling .cy-ghost-banner{display:flex;flex-wrap:wrap;gap:var(--sp-2,8px);align-items:baseline;justify-content:center;background:var(--hb-bg-soft,#272D35);
    border:1px solid var(--hb-line-strong,rgba(255,255,255,.24));border-radius:var(--hb-r-m,10px);padding:var(--sp-2,8px) var(--sp-3,12px)}
  .hb-cycling .cy-gb-name{font-weight:700} .hb-cycling .cy-gb-time{font-variant-numeric:tabular-nums;font-weight:600}
  .hb-cycling .cy-gb-pr{color:var(--hb-muted,#A7B0BE)}
  .hb-cycling .is-ahead{color:var(--hb-ok,#3DDC97)} .hb-cycling .is-behind{color:var(--hb-warn,#FFC53D)}
  .hb-cycling .cy-approach{display:flex;gap:var(--sp-2,8px);align-items:baseline;flex-wrap:wrap;border-left:4px solid var(--hb-warn,#FFC53D);
    background:var(--hb-bg-soft,#272D35);border-radius:var(--hb-r-s,8px);padding:var(--sp-2,8px) var(--sp-3,12px)}
  .hb-cycling .cy-approach-d{margin-left:auto;font-variant-numeric:tabular-nums;font-weight:600}
  .hb-cycling .cy-picker{display:flex;flex-wrap:wrap;gap:var(--sp-2,8px);align-items:flex-start}
  .hb-cycling .cy-picker-btn{flex:1;min-width:0;display:flex;gap:var(--sp-2,8px);justify-content:space-between}
  .hb-cycling .cy-picker-list{display:flex;flex-direction:column;gap:var(--sp-1,4px);width:100%}
  .hb-cycling .cy-ghost{display:flex;flex-direction:column;gap:var(--sp-2,8px)}
  .hb-cycling .cy-seglen{height:8px;border-radius:4px;background:var(--hb-neutral,#8B98AC);overflow:hidden}
  .hb-cycling .cy-seglen-fill{display:block;height:100%;background:var(--hb-accent,#AE90FF)}
  .hb-cycling .cy-seglen.is-near .cy-seglen-fill{background:var(--hb-ok,#3DDC97)}
  .hb-cycling .cy-staff{position:relative;height:220px;background:var(--hb-bg-soft,#272D35);border:1px solid var(--hb-line,rgba(255,255,255,.14));
    border-radius:var(--hb-r-l,12px);overflow:hidden;
    background-image:repeating-linear-gradient(to bottom,transparent 0,transparent 43px,var(--hb-line-subtle,rgba(255,255,255,.09)) 43px,var(--hb-line-subtle,rgba(255,255,255,.09)) 44px)}
  .hb-cycling .cy-rival{position:absolute;transform:translate(-50%,-50%);width:14px;height:14px;border-radius:50%;border:2px solid var(--hb-ink,#F2F4F7)}
  .hb-cycling .cy-rival.is-ahead{background:var(--hb-warn,#FFC53D)} .hb-cycling .cy-rival.is-behind{background:var(--hb-ok,#3DDC97)}
  .hb-cycling .cy-rival.is-pr{background:var(--hb-c-violet,#A47CFF)}
  .hb-cycling .cy-rival-lbl{position:absolute;left:18px;top:-3px;font-size:var(--fs-micro,.8rem);white-space:nowrap;color:var(--hb-ink,#F2F4F7)}
  .hb-cycling .cy-me-mark{position:absolute;left:0;right:0;transform:translateY(-50%);text-align:center;font-weight:700;font-size:var(--fs-caption,.86rem);
    border-top:2px solid var(--hb-accent,#AE90FF);color:var(--hb-accent,#AE90FF)}
  .hb-cycling .cy-of{position:absolute;left:50%;transform:translateX(-50%);font-size:var(--fs-micro,.8rem);color:var(--hb-muted,#A7B0BE)}
  .hb-cycling .cy-of-top{top:2px} .hb-cycling .cy-of-bot{bottom:2px}
  .hb-cycling .cy-ghost-pos{display:flex;justify-content:space-between;align-items:baseline;font-variant-numeric:tabular-nums}
  .hb-cycling .cy-gp-rank{font-size:1.4rem} .hb-cycling .cy-gp-behind{color:var(--hb-ok,#3DDC97)} .hb-cycling .cy-gp-ahead{color:var(--hb-warn,#FFC53D)}
  .hb-cycling .cy-split,.hb-cycling .cy-board,.hb-cycling .cy-rank{display:grid;grid-template-columns:3.5em 4.5em 1fr auto auto;gap:var(--sp-2,8px);align-items:baseline;
    font-variant-numeric:tabular-nums;padding:var(--sp-1,4px) 0;border-bottom:1px solid var(--hb-line-subtle,rgba(255,255,255,.09))}
  .hb-cycling .cy-board,.hb-cycling .cy-rank{grid-template-columns:2em 4.5em 1fr}
  .hb-cycling .cy-rank-n{color:var(--hb-muted,#A7B0BE)}
  .hb-cycling .cy-spark{width:100%;height:60px;background:var(--hb-bubble,#313740);border-radius:var(--hb-r-s,8px)}
  .hb-cycling .cy-spark polyline{fill:none;stroke-width:2;stroke-linejoin:round}
  .hb-cycling .cy-spark-hr polyline{stroke:var(--hb-c-red,#FF6259)} .hb-cycling .cy-spark-elev polyline{stroke:var(--hb-c-teal,#2DD4BF)}
  .hb-cycling .cy-mapbox{position:relative;width:100%;height:240px;min-height:180px;overflow:hidden;border-radius:var(--hb-r-l,12px);
    border:1px solid var(--hb-line,rgba(255,255,255,.14));background:var(--hb-bg-soft,#272D35);touch-action:none;cursor:grab}
  .hb-cycling .cy-mapbox-tall{height:320px} .hb-cycling .cy-mapbox-live{height:300px}
  .hb-cycling .cy-mapbox.is-marking{cursor:crosshair;border-color:var(--hb-accent,#AE90FF)}
  .hb-cycling .cy-tile{position:absolute;width:256px;height:256px;user-select:none;-webkit-user-drag:none;pointer-events:none}
  .hb-cycling .cy-ovl{position:absolute;left:0;top:0;pointer-events:none;z-index:1}
  .hb-cycling .cy-line{fill:none;stroke-linejoin:round;stroke-linecap:round}
  .hb-cycling .cy-route{stroke:var(--hb-c-orange,#FF8C42);stroke-width:4}
  .hb-cycling .cy-highlight{stroke:var(--hb-c-amber,#FFC53D);stroke-width:7}
  .hb-cycling .cy-seg{stroke:var(--hb-c-blue,#5B9BFF);stroke-width:5} .hb-cycling .cy-seg-in{stroke:var(--hb-c-orange,#FF8C42);stroke-width:5}
  .hb-cycling .cy-nearby{stroke:var(--hb-c-grey,#8B98AC);stroke-width:3;stroke-dasharray:4 3;opacity:.6}
  .hb-cycling .cy-dot{stroke:#fff;stroke-width:2.5}
  .hb-cycling .cy-me{fill:var(--hb-c-orange,#FF8C42)} .hb-cycling .cy-start{fill:var(--hb-c-green,#3DDC97)} .hb-cycling .cy-end{fill:var(--hb-c-red,#FF6259)}
  .hb-cycling .cy-rv-ahead{fill:var(--hb-c-amber,#FFC53D)} .hb-cycling .cy-rv-behind{fill:var(--hb-c-green,#3DDC97)}
  .hb-cycling .cy-attr{position:absolute;right:4px;bottom:2px;font-size:10px;color:#333;background:rgba(255,255,255,.75);padding:0 4px;border-radius:3px;z-index:2}
  .hb-cycling .cy-mapctl{position:absolute;right:var(--sp-2,8px);top:var(--sp-2,8px);z-index:3;display:flex;flex-direction:column;gap:var(--sp-1,4px)}
  .hb-cycling .cy-mapctl button{width:36px;height:36px;border-radius:var(--hb-r-m,10px);border:1px solid var(--hb-line,rgba(255,255,255,.14));
    background:color-mix(in srgb,var(--hb-bg,#1F242B) 92%,transparent);color:var(--hb-ink,#F2F4F7);font:600 18px/1 var(--sans,system-ui);cursor:pointer;padding:0}
  .hb-cycling .cy-mapctl button:focus-visible{outline:none;box-shadow:var(--hb-focus-ring,0 0 0 2px #AE90FF)}
  .hb-cycling .cy-crumbs{flex-wrap:wrap}
  `; document.head.appendChild(s);
}
