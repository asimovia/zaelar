// Clock widget: large centered digital clock. Browser-local time, refreshed every second.
// Data comes from the server but is used only as an initial fallback; the client renders the real clock.

function injectStyles(){
  if(document.getElementById("hb-clock-css"))return;
  const s=document.createElement("style"); s.id="hb-clock-css"; s.textContent=`
  /* No frame of our own (the chrome is the host's) and the clock fills its page, centred (V2-876 P-33). Figures in
     the house sans with tabular digits — a monospace face slashes the zero. */
  .hb-clock{font-family:var(--sans,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif);color:var(--hb-ink,#0d1622);
            width:100%;min-height:100%;box-sizing:border-box;padding:var(--sp-5,24px) var(--sp-4,16px);text-align:center;
            display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px}
  .hb-clock .time{font-family:inherit;font-size:72px;font-weight:600;
                  color:var(--hb-ink,#0d1622);letter-spacing:-.01em;line-height:1;font-variant-numeric:tabular-nums}
  .hb-clock .time .sec{color:var(--hb-accent2,#16B8A6);font-size:54px;margin-left:4px}
  .hb-clock .dow{font-size:15px;color:var(--hb-muted,#5b6b82);letter-spacing:.02em}
  .hb-clock .date{font-size:15px;color:var(--hb-muted,#3a4757);text-transform:capitalize;letter-spacing:.01em}
  .hb-clock .tz{font-size:13px;color:var(--hb-muted,#9aa7b8);margin-top:2px}
  @media(max-width:480px){.hb-clock .time{font-size:64px}.hb-clock .time .sec{font-size:44px}}
  `; document.head.appendChild(s);
}

function pad(n){ return String(n).padStart(2,"0"); }

// The zone the clock shows: a valid IANA id the engine sent for him, else the device's. Unreadable → none.
function zoneOf(want){
  try{ if(want){ new Intl.DateTimeFormat("en", {timeZone: want}); return want; } }catch(_){}
  try{ return Intl.DateTimeFormat().resolvedOptions().timeZone || ""; }catch(_){ return ""; }
}
function zoneName(lang, want){
  const zone = zoneOf(want);
  try{
    const part = new Intl.DateTimeFormat(lang || "en", {timeZone: zone || undefined, timeZoneName: "long"})
      .formatToParts(new Date()).find(p => p.type === "timeZoneName");
    return part ? part.value : zone;
  }catch(_){ return zone; }
}

// V2-613: this is a SYSTEM widget, so day/month names follow the operator's language — but a hand-built
// template of translated WORDS cannot also reorder "January 5, 2026" into "5 de enero de 2026" (English and
// Spanish put the day and month in different places, and other languages differ further still). `Intl` already
// solves the whole shape — order, connectors, capitalization — for any locale, from `ctx.lang` alone; no bundle
// keys needed for this widget at all.
function fmtDow(d, lang){
  const s = new Intl.DateTimeFormat(lang || "en", {weekday:"long"}).format(d);
  return s.charAt(0).toUpperCase() + s.slice(1);
}
function fmtDate(d, lang){
  return new Intl.DateTimeFormat(lang || "en", {day:"numeric", month:"long", year:"numeric"}).format(d);
}

export function render(el, data, ctx){
  injectStyles();
  if(el._clockTimer){ clearInterval(el._clockTimer); el._clockTimer=null; }

  el.className="hb-clock";
  el.textContent="";
  const time = document.createElement("div"); time.className="time";
  const hm = document.createElement("span"); hm.className="hm";
  const sec = document.createElement("span"); sec.className="sec";
  time.appendChild(hm); time.appendChild(sec);
  const dow = document.createElement("div"); dow.className="dow";
  const date = document.createElement("div"); date.className="date";
  const tz = document.createElement("div"); tz.className="tz";
  el.appendChild(time); el.appendChild(dow); el.appendChild(date); el.appendChild(tz);

  const zone = zoneOf(data && data.tz);
  function tick(){
    const d = zone ? new Date(new Date().toLocaleString("en-US", {timeZone: zone})) : new Date();
    const lang = ctx && ctx.lang;
    hm.textContent = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
    sec.textContent = `:${pad(d.getSeconds())}`;
    dow.textContent = fmtDow(d, lang);
    date.textContent = fmtDate(d, lang);
  }
  // The zone is the SCREEN's own (the device he holds), said by its name in his language («Pacific Standard Time»)
  // rather than the IANA id. A `data.tz` the engine knows for him wins over the device (V2-877 #12).
  tz.textContent = zoneName(ctx && ctx.lang, data && data.tz);

  tick();
  el._clockTimer = setInterval(tick, 1000);
}
