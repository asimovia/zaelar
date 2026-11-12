// youtube widget — stylesheet, third part (V2-885): the bar at three widths, Inicio's catalogue, the mini-player,
// the queue's rows and the empty states. Joined LAST into the one sheet, so its rules win by order over the halves'.
export const CSS_CARDS = `
  /* The card measures ITSELF: a desk card dragged narrow and the phone read the same rules (container query). */
  .hb-yt{container:hbyt/inline-size}
  /* THE BAR — tabs · spacer · platform icons · plug · one --sp-6 · the search, pinned right. */
  .hb-yt-navright{position:relative}
  .hb-yt-find,.hb-yt-menubtn{width:var(--hb-ctl-h-sm,32px);height:var(--hb-ctl-h-sm,32px);flex:0 0 auto;padding:0;
    border:1px solid var(--hb-line,rgba(255,255,255,.14));background:transparent;color:var(--hb-ink,#F2F4F7);
    border-radius:var(--hb-r-s,8px);cursor:pointer;display:flex;align-items:center;justify-content:center}
  .hb-yt-find{margin-left:calc(var(--sp-6,32px) - var(--sp-2,8px))}
  .hb-yt-find svg,.hb-yt-menubtn svg{width:16px;height:16px;display:block}
  .hb-yt-find:hover,.hb-yt-menubtn:hover,.hb-yt-menubtn[aria-expanded=true]{border-color:var(--hb-accent,#AE90FF);color:var(--hb-accent,#AE90FF)}
  .hb-yt-find:focus-visible,.hb-yt-menubtn:focus-visible,.hb-yt-mitem:focus-visible{outline:none;box-shadow:var(--hb-focus-ring,0 0 0 2px #AE90FF)}
  .hb-yt-menubtn{display:none}
  .hb-yt-menu{position:absolute;right:0;top:calc(100% + 6px);z-index:5;display:flex;flex-direction:column;min-width:200px;
    padding:6px;background:var(--hb-bg-soft,#272D35);border:1px solid var(--hb-line,rgba(255,255,255,.14));
    border-radius:var(--hb-r-m,10px);box-shadow:0 10px 28px rgba(0,0,0,.45)}
  .hb-yt-menu[hidden]{display:none}
  .hb-yt-mitem{border:0;background:none;color:var(--hb-ink,#F2F4F7);font:inherit;font-size:var(--fs-ui,14px);font-weight:600;
    text-align:left;min-height:44px;padding:0 var(--sp-3,12px);border-radius:var(--hb-r-s,8px);cursor:pointer}
  .hb-yt-mitem:hover{background:var(--hb-hover,rgba(255,255,255,.06))}
  .hb-yt-mitem.on{color:var(--hb-accent,#AE90FF)}
  /* Narrower than one line: the tools take a SECOND row, aligned right — never a ragged wrap. */
  @container hbyt (max-width:620px){
    .hb-yt-nav{flex-wrap:wrap;row-gap:var(--sp-1,4px)}
    .hb-yt-tabs{flex:1 1 100%}
  }
  /* The phone width: Inicio (and the face on screen) stay, the other tabs go behind «⋯»; the search always shows.
     The platform icons and the plug are not phone controls (V2-876 P-24). */
  @container hbyt (max-width:460px){
    .hb-yt-nav{flex-wrap:nowrap}
    .hb-yt-tabs{flex:1 1 auto}
    .hb-yt-tab:not([data-tab=inicio]):not(.on){display:none}
    .hb-yt-dots,.hb-yt-plug{display:none}
    .hb-yt-menubtn{display:flex}
    .hb-yt-find{margin-left:0}
  }
  .zm-scroll .hb-yt-find,.zm-scroll .hb-yt-menubtn{width:44px;height:44px}
  /* INICIO — the search on top, then the results ALONE or the catalogue's rows. */
  .hb-yt-reshead{margin-bottom:calc(-1 * var(--sp-3,12px))}
  .hb-yt-rgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:var(--sp-3,12px)}
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
  /* THE MINI-PLAYER — inside the card, at its foot, only while a video is current and its face is not shown. */
  .hb-yt-mini{display:none;flex:0 0 auto;align-items:center;gap:var(--sp-3,12px);min-width:0;box-sizing:border-box;
    padding:var(--sp-2,8px) var(--sp-3,12px);border-top:1px solid var(--hb-line-subtle,rgba(255,255,255,.09));
    background:var(--hb-bg-soft,#272D35)}
  .hb-yt.hb-yt-hasvid:not(.hb-yt-t-player) .hb-yt-mini{display:flex}
  .zm-scroll .hb-yt-mini{position:sticky;bottom:0;z-index:2}
  .hb-yt-mthumb{width:96px;aspect-ratio:16/9;object-fit:cover;border-radius:6px;background:#000;cursor:pointer;flex:0 0 auto}
  .hb-yt-minfo{flex:1 1 auto;min-width:0;display:flex;flex-direction:column;gap:2px;border:0;background:none;padding:0;
    text-align:left;color:inherit;font:inherit;cursor:pointer}
  .hb-yt-mtitle{font-size:var(--fs-caption,13.8px);font-weight:600;color:var(--hb-ink,#F2F4F7);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-yt-mchan{font-size:var(--fs-micro,12.75px);color:var(--hb-muted,#A9B1BD);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-yt-mbtn{width:36px;height:36px;flex:0 0 auto;border:0;border-radius:50%;background:none;color:var(--hb-ink,#F2F4F7);
    padding:0;display:flex;align-items:center;justify-content:center;cursor:pointer}
  .hb-yt-mbtn svg{width:18px;height:18px;display:block}
  .hb-yt-mbtn:hover{background:var(--hb-hover,rgba(255,255,255,.06))}
  .hb-yt-mbtn.main{background:#f03;color:#fff}
  .hb-yt-mbtn.main:hover{background:#f03;opacity:.88}
  .zm-scroll .hb-yt-mbtn{width:44px;height:44px}
  @container hbyt (max-width:460px){ .hb-yt-mthumb{width:64px} }
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
  /* The phone: the face full width, the ordinal on it, the controls in a row under the words, 44 pt each. */
  @container hbyt (max-width:460px){
    .hb-yt-qrow,.hb-yt-mylists .hb-yt-qrow{grid-template-columns:minmax(0,1fr);gap:var(--sp-2,8px)}
    .hb-yt-qrow .hb-yt-rimg{width:100%}
    .hb-yt-qrow .hb-yt-rown{position:absolute;top:calc(var(--sp-2,8px) + 6px);left:calc(var(--sp-2,8px) + 6px);z-index:1;
      background:rgba(0,0,0,.62);color:#fff;border-radius:6px;padding:2px 6px;min-width:0}
    .hb-yt-qacts{justify-content:flex-end}
    .hb-yt-qbtn{width:44px;height:44px}
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
