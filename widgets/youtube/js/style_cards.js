// youtube widget — stylesheet, third part (V2-885): the bar's own pieces, Inicio's catalogue, the mini-player,
// the queue's rows and the empty states. Joined LAST into the one sheet, so its rules win by order over the halves'.
export const CSS_CARDS = `
  /* The app measures ITSELF: a desk app dragged narrow and the phone read the same rules (container query). */
  .hb-yt{container:hbyt/inline-size}
  /* THE BAR is the house bar (V2-882): lib/toolbar.js measures its step; the search has an area of its own at every
     step — closing row 1 a --sp-6 right of the plug, closing the tools' row at step 2, before ⋯ at step 3. The
     secondary tabs live in the tray only as the ⋯ menu's rows; at that step Inicio and the face on screen stay. */
  .hb-yt .hb-yt-nav.hb-bar{grid-template-columns:minmax(0,1fr) auto auto auto auto;grid-template-areas:"lead views aux find more"}
  .hb-yt .hb-yt-nav.hb-bar[data-step="2"]{grid-template-columns:minmax(0,1fr) auto;grid-template-areas:"lead lead" "aux find"}
  .hb-yt .hb-yt-nav.hb-bar[data-step="3"]{grid-template-columns:minmax(0,1fr) auto auto;grid-template-areas:"lead find more"}
  .hb-yt-find{grid-area:find;width:var(--hb-ctl-h-sm,32px);height:var(--hb-ctl-h-sm,32px);padding:0;
    margin-left:var(--sp-6,32px);border:1px solid var(--hb-line,rgba(255,255,255,.14));background:transparent;
    color:var(--hb-ink,#F2F4F7);border-radius:var(--hb-r-s,8px);cursor:pointer;display:flex;align-items:center;justify-content:center}
  .hb-yt-find svg{width:16px;height:16px;display:block}
  .hb-yt-find:hover{border-color:var(--hb-accent,#AE90FF);color:var(--hb-accent,#AE90FF)}
  .hb-yt-find:focus-visible,.hb-yt-mitem:focus-visible{outline:none;box-shadow:var(--hb-focus-ring,0 0 0 2px #AE90FF)}
  .hb-yt-nav:not([data-step="3"]) .hb-yt-menu{display:none}
  @container hbyt (width >= 520px){                         /* a narrow card wears the chip row (style_phone.js) */
    .hb-yt-nav[data-step="3"] .hb-yt-tab:not([data-tab=inicio]):not(.on){display:none}
    .hb-yt-nav[data-step="3"] .hb-yt-find{margin-left:var(--sp-2,8px)}
  }
  .hb-yt-mitem{border:0;background:none;color:var(--hb-ink,#F2F4F7);font:inherit;font-size:var(--fs-ui,14px);font-weight:600;
    text-align:left;min-height:44px;padding:0 var(--sp-3,12px);border-radius:var(--hb-r-s,8px);cursor:pointer}
  .hb-yt-mitem:hover{background:var(--hb-hover,rgba(255,255,255,.06))}
  .hb-yt-mitem.on{color:var(--hb-accent,#AE90FF)}
  .zm-scroll .hb-yt-find{width:44px;height:44px} .zm-scroll .hb-yt-navright{display:none}   /* rule 5: not phone controls */
  /* INICIO — the results ALONE (a feed, style_phone.js) or the catalogue's rows. */
  .hb-yt-shelf{display:flex;flex-direction:column;gap:var(--sp-2,8px);min-width:0}
  .hb-yt-shelfh{display:flex;align-items:center;gap:var(--sp-2,8px);min-width:0}
  .hb-yt-shelft{margin:0 auto 0 0;font-size:var(--fs-ui,14px);font-weight:700;color:var(--hb-ink,#F2F4F7);min-width:0;
    white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-yt-sugsub{font-weight:400;margin-left:6px;color:var(--hb-muted,#A9B1BD)}
  .hb-yt-seeall{flex:0 0 auto;border:0;background:none;color:var(--hb-accent,#AE90FF);font:inherit;font-size:var(--fs-caption,13.8px);
    font-weight:600;cursor:pointer;padding:4px 8px;border-radius:var(--hb-r-s,8px)}
  .hb-yt-seeall:hover{background:var(--hb-hover,rgba(255,255,255,.06))}
  .hb-yt-shrow{display:grid;grid-auto-flow:column;grid-auto-columns:clamp(160px,30%,230px);gap:var(--sp-3,12px);
    overflow-x:auto;scroll-snap-type:x proximity;padding-bottom:6px;scrollbar-width:thin}
  .hb-yt-shrow > *{scroll-snap-align:start}
  .hb-yt-shrow:has(> .hb-yt-chtile){grid-auto-columns:112px}
  .hb-yt-chtile{display:flex;flex-direction:column;align-items:center;gap:6px;border:0;background:none;color:inherit;font:inherit;
    cursor:pointer;padding:var(--sp-2,8px) 4px;border-radius:var(--hb-r-m,10px);min-width:0}
  .hb-yt-chtile:hover{background:var(--hb-hover,rgba(255,255,255,.06))}
  .hb-yt-chtname{font-size:var(--fs-micro,12.75px);font-weight:600;color:var(--hb-ink,#F2F4F7);text-align:center;line-height:1.25;
    display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
  /* THE MINI-PLAYER — inside the card, at its foot, only while a video is current and its face is not shown: ONE slim
     row (≤ 64 px) with the progress on its top edge, the sound toggle only while it plays muted (2026-11-17). */
  .hb-yt-mini{display:none;position:relative;flex:0 0 auto;align-items:center;gap:var(--sp-3,12px);min-width:0;
    box-sizing:border-box;padding:6px var(--sp-2,8px) 6px 0;border-top:1px solid var(--hb-line-subtle,rgba(255,255,255,.09));
    background:var(--hb-bg-soft,#272D35);flex-wrap:nowrap}
  .hb-yt.hb-yt-hasvid:not(.hb-yt-t-player) .hb-yt-mini{display:flex}
  .hb-yt.hb-yt-hasvid.hb-yt-typing .hb-yt-mini,.hb-yt.hb-yt-hasvid:has(.hb-yt-search input:focus) .hb-yt-mini{display:none}
  .zm-scroll .hb-yt-mini{position:sticky;bottom:0;z-index:2}
  .hb-yt-mline{position:absolute;left:0;right:0;top:-1px;height:2px;background:var(--hb-line,rgba(255,255,255,.14))}
  .hb-yt-mprog{height:100%;width:0;background:#f03}
  .hb-yt-mthumb{height:48px;width:auto;aspect-ratio:16/9;object-fit:cover;background:#000;cursor:pointer;flex:0 0 auto}
  .hb-yt-minfo{flex:1 1 auto;min-width:0;display:flex;flex-direction:column;justify-content:center;gap:2px;border:0;
    background:none;padding:0;text-align:left;color:inherit;font:inherit;cursor:pointer}
  .hb-yt-mtitle{font-size:var(--fs-caption,13.8px);font-weight:600;color:var(--hb-ink,#F2F4F7);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-yt-mchan{font-size:var(--fs-micro,12.75px);color:var(--hb-muted,#A9B1BD);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-yt-mbtn{width:36px;height:36px;flex:0 0 auto;border:0;border-radius:50%;background:none;color:var(--hb-ink,#F2F4F7);
    padding:0;display:flex;align-items:center;justify-content:center;cursor:pointer}
  .hb-yt-mbtn svg{width:20px;height:20px;display:block}
  .hb-yt-mbtn:hover{background:var(--hb-hover,rgba(255,255,255,.06))}
  .hb-yt-mini .hb-yt-mbtn.snd{display:none;color:#f03}
  .hb-yt-mini.muted .hb-yt-mbtn.snd{display:flex}
  .zm-scroll .hb-yt-mbtn{width:44px;height:44px}
  /* THE QUEUE — one card per video, --sp-3 apart: ordinal, a 120 px face, title over channel · date, the controls. */
  .hb-yt-qrow{position:relative;display:grid;grid-template-columns:auto 120px minmax(0,1fr) auto;align-items:center;
    gap:var(--sp-3,12px);padding:var(--sp-2,8px);border-radius:var(--hb-r-m,10px);background:var(--hb-bg-soft,#272D35);
    border:1px solid var(--hb-line-subtle,rgba(255,255,255,.09))}
  .hb-yt-qrow:hover{background:var(--hb-bubble,#313740)}
  .hb-yt-qrow.playing{border-color:color-mix(in srgb,#f03 55%,transparent)}
  .hb-yt-mylists .hb-yt-qrow{grid-template-columns:120px minmax(0,1fr) auto}
  .hb-yt-qrow .hb-yt-rimg{width:120px;border-radius:8px}
  .hb-yt-qinfo{display:flex;flex-direction:column;gap:4px;min-width:0}
  .hb-yt-qrow .hb-yt-rowt{white-space:normal;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;
    font-size:var(--fs-ui,14px);font-weight:600;line-height:1.3}
  .hb-yt-qrow .hb-yt-rowc{max-width:none;font-size:var(--fs-micro,12.75px)}
  .hb-yt-qrow .hb-yt-rown{font-size:var(--fs-caption,13.8px);min-width:20px}
  .hb-yt-qacts{display:flex;align-items:center;gap:2px}
  .hb-yt-qbtn{width:32px;height:32px;flex:0 0 auto;border:0;background:none;border-radius:var(--hb-r-s,8px);padding:0;
    color:var(--hb-muted,#A9B1BD);display:flex;align-items:center;justify-content:center;cursor:pointer}
  .hb-yt-qbtn svg{width:16px;height:16px;display:block}
  .hb-yt-qbtn:hover{background:var(--hb-hover,rgba(255,255,255,.06));color:var(--hb-ink,#F2F4F7)}
  .hb-yt-qbtn.hb-yt-rowx:hover{color:var(--hb-risk,#FF8A92)}
  .hb-yt-qbtn:disabled{opacity:.3;cursor:default;pointer-events:none}
  .hb-yt-qbtn:focus-visible{outline:none;box-shadow:var(--hb-focus-ring,0 0 0 2px #AE90FF)}
  /* A saved list on the phone: the face full width, the controls in a row under the words, 44 pt each. */
  @container hbyt (max-width:460px){
    .hb-yt-mylists .hb-yt-qrow{grid-template-columns:minmax(0,1fr);gap:var(--sp-2,8px)}
    .hb-yt-mylists .hb-yt-qrow .hb-yt-rimg{width:100%}
    .hb-yt-mylists .hb-yt-qacts{justify-content:flex-end}
    .hb-yt-mylists .hb-yt-qbtn{width:44px;height:44px}
  }
  /* The queue on a narrow card is the YouTube playlist row: the picture ~40 % (≤ 168 px) left, title over channel,
     its controls behind one ⋮ (sheet.js); a wide card keeps the four named buttons. */
  .hb-yt-qrow .hb-yt-qmore{display:none}
  @container hbyt (max-width:519px){
    .hb-yt-list .hb-yt-qrow{grid-template-columns:auto minmax(0,min(40%,168px)) minmax(0,1fr) auto;gap:var(--sp-2,8px);
      padding:var(--sp-1,4px);background:none;border-color:transparent}
    .hb-yt-list .hb-yt-qrow.playing{background:color-mix(in srgb,#f03 10%,transparent)}
    .hb-yt-list .hb-yt-qrow .hb-yt-rimg{width:100%}
    .hb-yt-list .hb-yt-qrow .hb-yt-rown{min-width:14px;font-size:var(--fs-micro,12.75px)}
    .hb-yt-list .hb-yt-qacts{display:none}
    .hb-yt-list .hb-yt-qrow .hb-yt-qmore{display:flex;align-self:start}
  }
  /* EMPTY faces: one sentence and the options as buttons (the kit's hb-empty-state). */
  .hb-yt-emptytxt{max-width:46ch}
  .hb-yt-emptyopts{display:flex;gap:var(--sp-2,8px);flex-wrap:wrap;justify-content:center;margin-top:var(--sp-2,8px)}
  .zm-scroll .hb-yt-emptyopts .hb-btn{min-height:44px}
  .hb-yt-listh .hb-yt-newbtn{margin-left:auto}
  .hb-yt .hb-yt-newlist{display:none}
  .hb-yt.hb-yt-t-listas:not(.hb-yt-connmode) .hb-yt-newlist:not([hidden]){display:flex;flex-direction:column;gap:6px}
  .hb-yt-nlrow{display:flex;gap:6px;align-items:center}
  .hb-win.hb-cinema .hb-yt-mini,.hb-win:fullscreen .hb-yt-mini,
  .hb-win.hb-cinema .hb-yt-newlist,.hb-win:fullscreen .hb-yt-newlist{display:none}
`;
