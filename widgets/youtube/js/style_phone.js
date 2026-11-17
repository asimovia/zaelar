// youtube widget — stylesheet, fourth part (2026-11-17): the YouTube app's own shapes — the one search door in the bar,
// the feed item, the ⋮ sheet, the watch page (seek bar, title, chips, «A continuación») and, below 520px of card, the
// chip row. Joined LAST into the one sheet; tokens only, so the light and the dark theme both read it.
export const CSS_PHONE = `
  .hb-yt{position:relative}
  /* THE SEARCH DOOR — hidden until the 🔍 (or a band on Inicio) turns the bar into the field. */
  .hb-yt-search{grid-area:find;display:none;align-items:center;gap:2px;min-width:0;box-sizing:border-box;height:40px;
    width:clamp(220px,36cqw,400px);margin-left:var(--sp-4,16px);padding:0 4px;border-radius:999px;
    border:1px solid var(--hb-line,rgba(255,255,255,.14));background:var(--hb-bg-soft,#272D35)}
  .hb-yt-search:focus-within{border-color:var(--hb-accent,#AE90FF)}
  .hb-yt-search input{flex:1 1 auto;min-width:0;border:0;outline:none;background:none;padding:0 4px;
    color:var(--hb-ink,#F2F4F7);font-size:var(--fs-ui,14px)}
  .hb-yt-search input::placeholder{color:var(--hb-muted,#A9B1BD)}
  .hb-yt-search input::-webkit-search-cancel-button{display:none}
  .hb-yt-sbtn{width:30px;height:30px;flex:0 0 auto;border:0;border-radius:999px;background:none;padding:0;
    color:var(--hb-muted,#A9B1BD);cursor:pointer;display:flex;align-items:center;justify-content:center}
  .hb-yt-sbtn svg{width:16px;height:16px;display:block}
  .hb-yt-sbtn:hover{background:var(--hb-hover,rgba(255,255,255,.06));color:var(--hb-ink,#F2F4F7)}
  .hb-yt-sbtn:focus-visible,.hb-yt-down:focus-visible,.hb-yt-more3:focus-visible,.hb-yt-wchip:focus-visible,
  .hb-yt-item:focus-visible,.hb-yt-strack:focus-visible{outline:none;box-shadow:var(--hb-focus-ring,0 0 0 2px #AE90FF)}
  .hb-yt-sbtn.go,.hb-yt-sback{color:var(--hb-ink,#F2F4F7)}
  .hb-yt.hb-yt-smode .hb-yt-search{display:flex}
  .hb-yt.hb-yt-smode .hb-yt-find{display:none}
  .hb-yt-down{grid-area:down;display:none;width:var(--hb-ctl-h-sm,32px);height:var(--hb-ctl-h-sm,32px);padding:0;border:0;
    background:none;color:var(--hb-ink,#F2F4F7);border-radius:var(--hb-r-s,8px);cursor:pointer;align-items:center;justify-content:center}
  .hb-yt-down svg{width:22px;height:22px;display:block}
  /* His recent searches, under the field while he types into it. */
  .hb-yt-recent{display:none;flex-direction:column}
  .hb-yt.hb-yt-recents .hb-yt-recent{display:flex}
  .hb-yt.hb-yt-recents .hb-yt-home,.hb-yt.hb-yt-recents .hb-yt-blocked{display:none}
  .hb-yt-rq{display:flex;align-items:center;gap:var(--sp-4,16px);border:0;background:none;color:var(--hb-ink,#F2F4F7);font:inherit;
    font-size:var(--fs-ui,14px);text-align:left;padding:10px var(--sp-1,4px);cursor:pointer;border-radius:var(--hb-r-s,8px);min-width:0}
  .hb-yt-rq span{min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-yt-rq svg{width:18px;height:18px;flex:0 0 auto;color:var(--hb-muted,#A9B1BD)}
  .hb-yt-rq:hover{background:var(--hb-hover,rgba(255,255,255,.06))}
  /* THE FEED ITEM — one column: the picture full width, then ordinal · title, «channel · age», the ⋮. */
  .hb-yt-feed{display:flex;flex-direction:column;gap:var(--sp-5,24px);min-width:0}
  .hb-yt-item{display:grid;grid-template-columns:minmax(0,1fr) auto;grid-template-areas:"thumb thumb" "text more";
    column-gap:var(--sp-2,8px);row-gap:var(--sp-2,8px);min-width:0;cursor:pointer;border-radius:var(--hb-r-m,10px);text-align:left}
  .hb-yt-ithumb{grid-area:thumb;position:relative;aspect-ratio:16/9;border-radius:var(--hb-r-m,10px);overflow:hidden;
    background:var(--hb-bubble,#313740)}
  .hb-yt-ithumb img{display:block;width:100%;height:100%;object-fit:cover}
  .hb-yt-itext{grid-area:text;display:flex;flex-direction:column;gap:4px;min-width:0}
  .hb-yt-ititle{font-size:var(--fs-ui,14px);font-weight:600;line-height:1.3;color:var(--hb-ink,#F2F4F7);overflow:hidden;
    display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
  .hb-yt-rnum{margin-right:6px;font-size:var(--fs-micro,12.75px);font-weight:600;color:var(--hb-muted,#A9B1BD);
    font-variant-numeric:tabular-nums}
  .hb-yt-imeta{font-size:var(--fs-micro,12.75px);color:var(--hb-muted,#A9B1BD);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-yt-item > .hb-yt-more3{grid-area:more}
  .hb-yt-more3{align-self:start;width:32px;height:32px;flex:0 0 auto;border:0;border-radius:50%;background:none;
    padding:0;color:var(--hb-muted,#A9B1BD);cursor:pointer;display:flex;align-items:center;justify-content:center}
  .hb-yt-more3 svg{width:18px;height:18px;display:block;transform:rotate(90deg)}
  .hb-yt-more3:hover{background:var(--hb-hover,rgba(255,255,255,.06));color:var(--hb-ink,#F2F4F7)}
  .hb-yt-skel{cursor:default}
  .hb-yt-skel .hb-yt-ithumb,.hb-yt-iline{animation:hbytpulse 1.2s ease-in-out infinite alternate}
  .hb-yt-iline{height:12px;width:92%;border-radius:4px;background:var(--hb-bubble,#313740)}
  .hb-yt-iline.short{width:55%}
  @keyframes hbytpulse{from{opacity:1}to{opacity:.55}}
  @container hbyt (width >= 600px){            /* a wide card: the YouTube desktop row, the picture left */
    .hb-yt-item{grid-template-columns:clamp(240px,36%,320px) minmax(0,1fr) auto;grid-template-areas:"thumb text more";
      column-gap:var(--sp-4,16px)}
    .hb-yt-feed{gap:var(--sp-4,16px)}
    .hb-yt-ititle{font-size:var(--fs-body,15px)}
  }
  /* THE ⋮ SHEET — at the card's foot, over a scrim inside the card. */
  .hb-yt-scrim{position:absolute;inset:0;z-index:4;background:rgba(0,0,0,.45)}
  .hb-yt-sheet{position:absolute;left:0;right:0;bottom:0;z-index:5;max-width:480px;max-height:70%;margin-inline:auto;
    overflow:auto;display:flex;flex-direction:column;box-sizing:border-box;padding:var(--sp-2,8px) 0 var(--sp-3,12px);
    background:var(--hb-bubble,#313740);border-radius:var(--hb-r-l,12px) var(--hb-r-l,12px) 0 0;box-shadow:0 -8px 24px rgba(0,0,0,.28)}
  .hb-yt-sheett{padding:var(--sp-2,8px) var(--sp-4,16px);font-size:var(--fs-micro,12.75px);color:var(--hb-muted,#A9B1BD);
    white-space:nowrap;overflow:hidden;text-overflow:ellipsis;border-bottom:1px solid var(--hb-line-subtle,rgba(255,255,255,.09))}
  .hb-yt-sheeti{border:0;background:none;text-align:left;font:inherit;font-size:var(--fs-ui,14px);color:var(--hb-ink,#F2F4F7);
    padding:12px var(--sp-4,16px);cursor:pointer}
  .hb-yt-sheeti:hover,.hb-yt-sheeti:focus-visible{outline:none;background:var(--hb-hover,rgba(255,255,255,.06))}
  .hb-yt-sheeti:disabled{opacity:.4;cursor:default}
  /* THE WATCH PAGE — the seek bar under the video, the title and its channel, the chips, «A continuación». */
  .hb-yt .hb-yt-seek,.hb-yt .hb-yt-wchips,.hb-yt .hb-yt-upnext{display:none}
  .hb-yt.hb-yt-t-player.hb-yt-hasvid:not(.hb-yt-connmode) .hb-yt-seek{display:flex}
  .hb-yt.hb-yt-t-player.hb-yt-hasvid:not(.hb-yt-connmode) .hb-yt-wchips{display:flex}
  .hb-yt.hb-yt-t-player.hb-yt-hasvid:not(.hb-yt-connmode) .hb-yt-upnext:not([hidden]){display:flex}
  .hb-yt-seek{align-items:center;gap:var(--sp-3,12px);padding:var(--sp-1,4px) var(--sp-4,16px) 0}
  .hb-yt-strack{position:relative;flex:1 1 auto;height:20px;cursor:pointer;touch-action:none}
  .hb-yt-strack::before,.hb-yt-sfill{content:"";position:absolute;left:0;top:50%;height:3px;margin-top:-1.5px;border-radius:2px}
  .hb-yt-strack::before{right:0;background:var(--hb-line,rgba(255,255,255,.14))}
  .hb-yt-sfill{width:0;background:#f03}
  .hb-yt-sknob{position:absolute;left:0;top:50%;width:12px;height:12px;margin:-6px 0 0 -6px;border-radius:50%;background:#f03}
  .hb-yt-seek.off .hb-yt-sknob{display:none}
  .hb-yt-seek.off .hb-yt-strack{cursor:default}
  .hb-yt-stime{font-size:var(--fs-micro,12.75px);color:var(--hb-muted,#A9B1BD);font-variant-numeric:tabular-nums;white-space:nowrap}
  .hb-yt-follow{flex:0 0 auto}
  .hb-yt-follow[hidden]{display:none}
  .hb-yt-wchips,.hb-yt-upnext,.hb-yt-recent{flex:0 0 auto}       /* the body is a column: an overflowing row must not shrink */
  .hb-yt-wchips{gap:var(--sp-2,8px);overflow-x:auto;scrollbar-width:none;padding:var(--sp-1,4px) var(--sp-4,16px) var(--sp-3,12px)}
  .hb-yt-wchips::-webkit-scrollbar{display:none}
  .hb-yt-wchip{flex:0 0 auto;border:0;border-radius:999px;padding:6px 14px;font:inherit;font-size:var(--fs-caption,13.8px);
    font-weight:600;white-space:nowrap;cursor:pointer;color:var(--hb-ink,#F2F4F7);background:var(--hb-bg-soft,#272D35)}
  .hb-yt-wchip:hover{background:var(--hb-hover,rgba(255,255,255,.06))}
  .hb-yt-wchip.on{background:color-mix(in srgb,var(--hb-accent,#AE90FF) 18%,transparent);font-weight:700;
    box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--hb-accent,#AE90FF) 55%,transparent)}
  .hb-yt-upnext{flex-direction:column;gap:var(--sp-2,8px);padding:var(--sp-2,8px) var(--sp-4,16px) var(--sp-4,16px);
    border-top:1px solid var(--hb-line-subtle,rgba(255,255,255,.09))}
  .hb-yt-unhead{font-size:var(--fs-ui,14px);font-weight:700;color:var(--hb-ink,#F2F4F7);padding:var(--sp-1,4px) 0}
  .hb-yt-unrow{display:grid;grid-template-columns:minmax(0,min(40%,168px)) minmax(0,1fr);gap:var(--sp-3,12px);align-items:start;
    border:0;background:none;padding:4px;border-radius:var(--hb-r-m,10px);text-align:left;color:inherit;font:inherit;cursor:pointer}
  .hb-yt-unrow:hover{background:var(--hb-hover,rgba(255,255,255,.06))}
  .hb-yt-unrow img{width:100%;aspect-ratio:16/9;object-fit:cover;border-radius:8px;background:var(--hb-bubble,#313740)}
  .hb-yt-untext{display:flex;flex-direction:column;gap:4px;min-width:0}
  .hb-yt-untitle{font-size:var(--fs-caption,13.8px);font-weight:600;line-height:1.3;color:var(--hb-ink,#F2F4F7);overflow:hidden;
    display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
  .hb-yt-unchan{font-size:var(--fs-micro,12.75px);color:var(--hb-muted,#A9B1BD);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  /* A NARROW card (≤ 519 px: the phone, a desk card dragged small) — the YouTube app's bar and watch page. */
  @container hbyt (max-width:519px){
    .hb-yt .hb-yt-nav.hb-bar.hb-bar{grid-template-columns:auto minmax(0,1fr) auto;grid-template-areas:"down lead find";column-gap:var(--sp-1,4px)}
    .hb-yt .hb-yt-nav .hb-bar-tray,.hb-yt .hb-yt-nav.hb-bar .hb-bar-more{display:none}
    .hb-yt .hb-yt-nav .hb-yt-tabs{gap:var(--sp-2,8px);margin:0;overflow-x:auto;scrollbar-width:none;scroll-padding-inline:var(--sp-2,8px)}
    .hb-yt .hb-yt-nav .hb-yt-tab{display:inline-flex;align-items:center;border-radius:var(--hb-r-s,8px);padding:6px 12px;
      color:var(--hb-ink,#F2F4F7);background:var(--hb-bg-soft,#272D35)}
    .hb-yt .hb-yt-nav .hb-yt-tab.on{background:color-mix(in srgb,var(--hb-accent,#AE90FF) 18%,transparent)}
    .hb-yt .hb-yt-nav .hb-yt-tab[data-tab=player]{display:none}
    .zm-scroll .hb-yt .hb-yt-nav .hb-yt-tab{min-height:44px}
    .zm-scroll .hb-yt-down{width:44px;height:44px}
    .hb-yt.hb-yt-t-player:not(.hb-yt-connmode) .hb-yt-down{display:flex}
    .hb-yt .hb-yt-find{margin-left:var(--sp-1,4px)}
    .hb-yt.hb-yt-smode .hb-yt-nav.hb-bar.hb-bar{grid-template-columns:minmax(0,1fr);grid-template-areas:"find"}
    .hb-yt.hb-yt-smode .hb-yt-nav.hb-bar > :not(.hb-yt-search){display:none}
    .hb-yt .hb-yt-search{width:auto;margin:0}
    .hb-yt .hb-yt-search .go{display:none}
    .hb-yt .hb-yt-tline{flex-direction:column;align-items:stretch;gap:var(--sp-2,8px)}
    .hb-yt .hb-yt-title{white-space:normal;font-size:var(--fs-title,17px);line-height:1.3;
      display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
    .hb-yt .hb-yt-by{justify-content:space-between}
    .hb-yt .hb-yt-ctrls{justify-content:center;gap:var(--sp-5,24px)}
    .hb-yt .hb-yt-cbtn.wide,.hb-yt .hb-yt-ctrls .hb-yt-vol,
    .hb-yt.hb-yt-t-player:not(.hb-yt-hasvid) .hb-yt-hint{display:none}
  }
`;
