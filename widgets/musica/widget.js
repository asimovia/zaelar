// musica: face of the music connector (V2-041) — Spotify-style lists (V2-058), a PRO pass (V2-629/V2-678), the
// V2-717 redesign (the widget is ONE box: the canvas window IS the frame; the bar above the content is the ONE bar
// the house standard allows; the song that is sounding OCCUPIES the card) and V2-795: the card does what a player
// does — a queue you can see and edit, shuffle and repeat, a volume you can mute, list management (rename, delete,
// reorder, play from a song, shuffle a list), a heart on every row, a search over the catalogue with artist and
// album pages — and the content is SECTIONED: each shelf is a quiet panel one rung up the elevation ladder
// (V2-689), never a frame around the whole card. Contract: render(el, data, ctx).
// data = GET /widgets/musica/data -> {mode:"spotify"|"youtube"|"local"|"idle", connected, can_connect,
//   own_client_id_set, default_available, redirect_uri, now_playing (spotify, with progress_ms/duration_ms,
//   shuffle, repeat)|null, yt:{videoId,title,artist,paused,muted,volume,cmd_seq,art,seek:{n,to,by},queue,shuffle,
//   repeat}, local:{src,title,artist,art,paused,seq,seek:{n,to,by}},
//   playlists:[{id,name,art,tracks:[{title,artist,album,art,query,uri,videoId}]}], recent:[track],
//   top:[track+count], fav_current:bool, fav:{id,name}, modes:{shuffle,repeat,supported},
//   queue:{items,editable,source}, volume:{level,muted}, browse:{search,artist,album},
//   view:{kind:"home|now|library|queue|playlist|search|artist|album|connect",id}}.
//   ctx.action(name,payload) -> POST /widgets/musica/action (JSON).
//
// Faces (drawView): `home` is ADAPTIVE — the song when something sounds, the library when nothing does; `now` and
// `library` pin either; `queue`, `playlist`, `search`, `artist`, `album` and `connect` are screens of their own.
// PLAYBACK = the connector (ctx.action -> connectors.music); nothing here reinvents a backend, and nothing here
// touches the network: the catalogue answers arrive in the store (`browse`) and are painted from there.
//
// THE PLAYHEAD (V2-717) belongs to whoever is making the sound, and that is why there is no position in the
// store. A local file and the hidden YouTube iframe play in THIS page and hold their own clock, so the card reads
// them directly and a drag seeks them with no server in the loop; Spotify plays on a device somewhere else, so its
// `progress_ms` is a photograph the card advances locally and a drag is a round trip. A seek asked by VOICE
// travels the other way — a numbered command in the store (`seek:{n,to,by}`) that `applyPendingSeek` applies.
//
// The hidden YouTube-audio player is reused between re-renders (persistent `_ytHost`): rebuilding the view never
// reloads the iframe, which would restart the song.
//
// ICONS are inline SVG in the SAME visual language as the app shell (frontend/app/lib/icons.js), duplicated
// locally because widget.js cannot import from frontend/app.
//
// ⚠️ No backtick may appear inside the CSS template below, not even in a comment: it ends the literal and kills
// the whole module (met twice; `node --check` catches it, nothing at runtime does).

function injectStyles(){
  if(document.getElementById("hb-mus2-css")) return;
  const s = document.createElement("style"); s.id = "hb-mus2-css"; s.textContent = `
  /* THREE bands that never trade places: the one bar, a scrolling middle, the transport at the foot. The root
     fills the card and switches OFF the card's own scroll (the :has rule), so the middle owns the overflow. */
  .hb-scroll:has(> .hb-mus2-root){overflow:hidden}
  .hb-mus2-root{position:relative;height:100%;display:flex;flex-direction:column;overflow:hidden}
  /* el._viewHost sits between root and the visible card and needs its own place in the height chain: with no
     rule of its own it is height:auto, and a percentage height under it resolves against nothing (V2-678). */
  .hb-mus2-viewhost{flex:1 1 auto;min-height:0;display:flex;flex-direction:column}
  /* V2-717 — ONE box: no border, radius or background of our own; the window is the frame.
     V2-795 — the rungs this card uses, named once so every panel picks the same step of the ladder:
     the card sits on --hb-bg (surface 1), a PANEL is --hb-bg-soft (surface 2), a card inside a panel is
     --hb-bubble (surface 3), and hover is --hb-hover. Hairlines are alpha so they weigh the same on every rung. */
  .hb-mus2{--sp-green:#1DB954;--mus-panel:var(--hb-bg-soft,rgba(127,127,127,.07));
           --mus-card:var(--hb-bubble,rgba(127,127,127,.11));--mus-hover:var(--hb-hover,rgba(127,127,127,.16));
           --mus-line:var(--hb-line-subtle,rgba(127,127,127,.18));--mus-r:var(--hb-r-l,12px);
           --mus-shadow:var(--hb-shadow-1,0 1px 2px rgba(0,0,0,.18),0 4px 12px rgba(0,0,0,.10));
           font-family:var(--sans,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif);
           width:100%;height:100%;min-height:0;box-sizing:border-box;background:transparent;overflow:hidden;
           color:var(--hb-ink,#0d1622);display:flex;flex-direction:column;container-type:inline-size}
  .hb-mus2 svg{display:block}
  .hb-mus2 button{font-family:inherit}

  /* ── THE ONE BAR: where you are on the left, the search and the source chip in ONE right cluster ── */
  .hb-mus2-headfix{flex:0 0 auto;background:var(--hb-bg-soft,rgba(127,127,127,.05));
                   border-bottom:1px solid var(--mus-line);padding:5px 12px;min-height:32px;
                   display:flex;align-items:center;gap:8px}
  .hb-mus2-right{margin-left:auto;display:flex;align-items:center;gap:6px;flex:0 0 auto}
  .hb-mus2-prov{font-size:12px;color:var(--hb-muted,#5b6b82);border:1px solid var(--hb-line,#e3e8f0);
                border-radius:999px;padding:3px 10px;display:flex;align-items:center;gap:6px;flex:0 0 auto;
                background:var(--hb-bg,transparent);cursor:pointer;line-height:1.5}
  .hb-mus2-prov:hover{border-color:var(--hb-accent,#3D6FE0);color:var(--hb-ink,#0d1622)}
  .hb-mus2-dot{width:7px;height:7px;border-radius:50%;background:var(--hb-neutral,#c2ccda);flex:0 0 auto}
  .hb-mus2-dot.on{background:var(--sp-green)}
  .hb-mus2-seg{display:flex;gap:2px;border:1px solid var(--hb-line,#e3e8f0);border-radius:999px;padding:2px;
               background:var(--hb-bg,transparent);flex:0 1 auto;min-width:0;overflow:hidden}
  .hb-mus2-segb{border:0;background:none;color:var(--hb-muted,#5b6b82);font-size:12px;font-weight:700;
                padding:4px 10px;border-radius:999px;cursor:pointer;display:flex;align-items:center;gap:5px;
                line-height:1;white-space:nowrap}
  .hb-mus2-segb svg{width:13px;height:13px;flex:none}
  .hb-mus2-segb:hover{color:var(--hb-ink,#0d1622)}
  .hb-mus2-segb.on{background:color-mix(in srgb,var(--hb-accent,#3D6FE0) 18%,transparent);color:var(--hb-ink,#0d1622);
                   box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--hb-accent,#3D6FE0) 55%,transparent)}
  .hb-mus2-back{border:0;background:none;color:var(--hb-muted,#5b6b82);font-size:13px;font-weight:600;cursor:pointer;
                display:flex;align-items:center;gap:4px;padding:2px 4px 2px 0;flex:0 0 auto}
  .hb-mus2-back svg{width:15px;height:15px}
  .hb-mus2-back:hover{color:var(--hb-accent,#3D6FE0)}
  /* a quiet square icon button — the house kit's shape, drawn here so a card rendered outside the app keeps it */
  .hb-mus2-ibtn{border:1px solid transparent;background:none;color:var(--hb-muted,#5b6b82);cursor:pointer;
                width:28px;height:28px;border-radius:8px;display:flex;align-items:center;justify-content:center;
                padding:0;flex:0 0 auto;transition:background .12s,color .12s}
  .hb-mus2-ibtn svg{width:16px;height:16px}
  .hb-mus2-ibtn:hover{background:var(--mus-hover);color:var(--hb-ink,#0d1622)}
  .hb-mus2-ibtn.on{color:var(--sp-green)}
  .hb-mus2-ibtn.risk:hover{color:var(--hb-risk,#e5484d)}
  .hb-mus2-ibtn:disabled{opacity:.35;cursor:default;pointer-events:none}
  .hb-mus2-sbox{flex:1 1 auto;min-width:0;display:flex;align-items:center;gap:7px;height:28px;padding:0 10px;
                border:1px solid var(--hb-line,#e3e8f0);border-radius:999px;background:var(--hb-bg,transparent)}
  .hb-mus2-sbox:focus-within{border-color:var(--hb-accent,#3D6FE0)}
  .hb-mus2-sbox svg{width:14px;height:14px;color:var(--hb-muted-2,#9aa7b8);flex:none}
  .hb-mus2-sinp{flex:1 1 auto;min-width:0;border:0;outline:none;background:none;color:var(--hb-ink,#0d1622);
                font:inherit;font-size:13px}

  /* ── the middle ── */
  .hb-mus2-scroll{flex:1 1 auto;min-height:0;overflow:auto;padding:14px;display:flex;flex-direction:column;gap:12px}
  /* safe center, never plain center: a centred column CLIPS what overflows at both ends (V2-717, measured) */
  .hb-mus2-scroll.mid{justify-content:safe center;align-items:center;container-type:size}
  /* a SHORT card (the window is resizable) gives the cover the room first: the facts line goes, the title shrinks */
  @container (height < 250px){ .hb-mus2-nowm{display:none} .hb-mus2-nowt{font-size:17px;margin-top:8px}
                               .hb-mus2-nowa{margin-top:2px} .hb-mus2-nowart{height:min(76%,320px)}
                               .hb-mus2-seek{margin-top:8px} }

  /* V2-795 — A PANEL per shelf: one rung up, a hairline, the soft resting shadow. Quiet on purpose: the content
     is the music, the panel only says where one group ends and the next begins. */
  .hb-mus2-sec{display:flex;flex-direction:column;gap:10px;background:var(--mus-panel);border:1px solid var(--mus-line);
               border-radius:var(--mus-r);box-shadow:var(--mus-shadow);padding:12px;flex:0 0 auto}
  .hb-mus2-sechead{display:flex;align-items:center;gap:8px;min-height:24px}
  .hb-mus2-sech{font-size:13.5px;font-weight:700;letter-spacing:-.005em}
  .hb-mus2-secn{font-size:12px;color:var(--hb-muted-2,#9aa7b8);font-variant-numeric:tabular-nums}
  .hb-mus2-secact{margin-left:auto;display:flex;align-items:center;gap:6px}
  .hb-mus2-note{font-size:12px;color:var(--hb-muted,#5b6b82);line-height:1.45}
  .hb-mus2-pill{border:1px solid var(--hb-line,#e3e8f0);background:var(--mus-card);color:var(--hb-ink,#0d1622);
                border-radius:999px;padding:4px 11px;font-size:12px;font-weight:600;cursor:pointer;line-height:1.3;
                display:flex;align-items:center;gap:5px}
  .hb-mus2-pill svg{width:13px;height:13px}
  .hb-mus2-pill:hover{border-color:var(--hb-accent,#3D6FE0);background:var(--mus-hover)}
  .hb-mus2-pill.risk{color:var(--hb-risk,#e5484d)}

  /* lists as CARDS with a cover mosaic; the «new list» is a pill in the panel's head, not a giant tile */
  .hb-mus2-lists{display:grid;grid-template-columns:repeat(auto-fill,minmax(104px,1fr));gap:10px}
  .hb-mus2-pl{min-width:0;display:flex;flex-direction:column;gap:7px;padding:8px;border-radius:10px;cursor:pointer;
              background:var(--mus-card);border:1px solid transparent;position:relative;
              transition:background .14s,transform .14s,box-shadow .14s}
  .hb-mus2-pl:hover{background:var(--mus-hover);transform:translateY(-1px);box-shadow:var(--mus-shadow)}
  .hb-mus2-pl .hb-mus2-art{width:100%;height:auto;aspect-ratio:1/1}
  .hb-mus2-plname{font-size:13px;font-weight:600;line-height:1.25;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-mus2-plsub{font-size:12px;color:var(--hb-muted,#5b6b82)}
  .hb-mus2-plplay{position:absolute;right:13px;top:calc(100% - 78px);width:34px;height:34px;border-radius:50%;
                  border:0;background:var(--sp-green);color:#0b1a10;display:flex;align-items:center;justify-content:center;
                  cursor:pointer;box-shadow:0 6px 14px rgba(0,0,0,.35);opacity:0;transform:translateY(4px);
                  transition:opacity .14s,transform .14s}
  .hb-mus2-plplay svg{width:15px;height:15px}
  .hb-mus2-pl:hover .hb-mus2-plplay{opacity:1;transform:none}

  .hb-mus2-art{border-radius:8px;display:flex;align-items:center;justify-content:center;overflow:hidden;flex:0 0 auto;
               background:linear-gradient(135deg,var(--hb-accent,#3D6FE0),var(--hb-accent2,#16B8A6))}
  .hb-mus2-art img{width:100%;height:100%;object-fit:cover}
  .hb-mus2-art svg{width:38%;height:38%;color:rgba(255,255,255,.92)}
  .hb-mus2-art.fav{background:linear-gradient(135deg,#7b5cff,#e05ca8)}
  .hb-mus2-mosaic{display:grid;grid-template-columns:1fr 1fr;grid-template-rows:1fr 1fr}
  .hb-mus2-mosaic img{width:100%;height:100%;object-fit:cover;display:block}
  .hb-mus2-new .hb-mus2-art{background:var(--mus-card);border:1.5px dashed var(--hb-line,#e3e8f0);
                            color:var(--hb-muted,#5b6b82)}
  .hb-mus2-new .hb-mus2-art svg{color:var(--hb-muted,#5b6b82)}

  /* ── rows ── */
  .hb-mus2-grid{display:flex;flex-direction:column;gap:2px}
  .hb-mus2-tr{display:flex;align-items:center;gap:10px;padding:6px 8px;border-radius:8px;cursor:pointer;
              user-select:none;position:relative;transition:background .12s}
  .hb-mus2-tr:hover{background:var(--mus-hover)}
  .hb-mus2-tr.selected{background:var(--mus-card);box-shadow:inset 0 0 0 1px var(--hb-line,#e3e8f0)}
  /* V2-795 — three states that never look alike: HOVER is a neutral tone; CURRENT (the song the player holds)
     is a green title and a green edge, with no fill of its own, so it reads the same under the pointer and
     away from it; the animated meter is drawn ONLY while it is actually sounding. */
  .hb-mus2-tr.current{box-shadow:inset 3px 0 0 var(--sp-green)}
  .hb-mus2-tr.current .hb-mus2-trt{color:var(--sp-green)}
  .hb-mus2-tr.current .hb-mus2-trn svg{width:14px;height:14px;color:var(--sp-green)}
  .hb-mus2-tr.dragover{box-shadow:inset 0 2px 0 var(--hb-accent,#3D6FE0)}
  .hb-mus2-tr.current.selected{box-shadow:inset 3px 0 0 var(--sp-green),inset 0 0 0 1px var(--hb-line,#e3e8f0)}
  .hb-mus2-tr .hb-mus2-art{width:40px;height:40px;border-radius:6px;position:relative}
  .hb-mus2-trplay{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;border:0;padding:0;
                  background:rgba(0,0,0,.55);color:#fff;opacity:0;cursor:pointer;transition:opacity .12s;border-radius:6px}
  .hb-mus2-trplay svg{width:16px;height:16px;color:#fff}
  .hb-mus2-tr:hover .hb-mus2-trplay{opacity:1}
  .hb-mus2-trn{font-size:12px;color:var(--hb-muted-2,#9aa7b8);font-variant-numeric:tabular-nums;
               min-width:18px;text-align:center;display:flex;align-items:center;justify-content:center}
  .hb-mus2-trmeta{min-width:0;flex:1}
  .hb-mus2-trt{font-size:13px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-mus2-tra{font-size:12px;color:var(--hb-muted,#5b6b82);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-mus2-trx{display:flex;align-items:center;gap:2px;flex:0 0 auto}
  /* a row's own buttons are quiet until the row is under the pointer; a liked heart stays lit, it is a STATE */
  .hb-mus2-trx .hb-mus2-ibtn{opacity:0;width:26px;height:26px}
  .hb-mus2-trx .hb-mus2-ibtn svg{width:14px;height:14px}
  .hb-mus2-tr:hover .hb-mus2-trx .hb-mus2-ibtn,.hb-mus2-trx .hb-mus2-ibtn.on,.hb-mus2-trx .hb-mus2-ibtn:focus-visible{opacity:1}
  .hb-mus2-x{border:0;background:none;color:var(--hb-muted-2,#9aa7b8);cursor:pointer;
             padding:5px;border-radius:7px;line-height:1;flex:0 0 auto;display:flex}
  .hb-mus2-x svg{width:14px;height:14px}
  .hb-mus2-x:hover{color:var(--hb-risk,#e5484d)}
  .hb-mus2-grip{color:var(--hb-muted-2,#9aa7b8);cursor:grab;display:flex;opacity:0;flex:0 0 auto}
  .hb-mus2-grip svg{width:14px;height:14px}
  .hb-mus2-tr:hover .hb-mus2-grip{opacity:1}
  .hb-mus2-empty{font-size:12.5px;color:var(--hb-muted-2,#9aa7b8);padding:2px}

  /* a small menu that floats over the card (add to which list) */
  .hb-mus2-menu{position:absolute;z-index:20;min-width:180px;max-width:240px;max-height:240px;overflow:auto;padding:5px;
                background:var(--hb-bubble,#fff);border:1px solid var(--hb-line,#e3e8f0);border-radius:10px;
                box-shadow:var(--hb-shadow-2,0 16px 40px rgba(0,0,0,.25))}
  .hb-mus2-menu button{display:block;width:100%;text-align:left;border:0;background:none;color:var(--hb-ink,#0d1622);
                       padding:7px 9px;border-radius:7px;font-size:13px;cursor:pointer;white-space:nowrap;
                       overflow:hidden;text-overflow:ellipsis}
  .hb-mus2-menu button:hover{background:var(--mus-hover)}

  /* ── a page head (list, artist, album): cover, kicker, name, facts, actions ── */
  .hb-mus2-head{display:flex;gap:16px;align-items:flex-end;padding:2px 2px 4px}
  .hb-mus2-artwrap{position:relative;flex:0 0 auto}
  .hb-mus2-head .hb-mus2-art{width:112px;height:112px;border-radius:10px;
                             box-shadow:0 14px 30px -12px rgba(0,0,0,.6),0 2px 6px rgba(0,0,0,.2)}
  .hb-mus2-head .hb-mus2-art.round{border-radius:50%}
  .hb-mus2-headmeta{display:flex;flex-direction:column;gap:6px;min-width:0;flex:1}
  .hb-mus2-headk{font-size:12px;text-transform:uppercase;letter-spacing:.1em;color:var(--hb-muted-2,#9aa7b8);font-weight:600}
  .hb-mus2-headn{font-size:22px;font-weight:800;line-height:1.1;letter-spacing:-.02em;word-break:break-word}
  .hb-mus2-headn.link,.hb-mus2-plsub.link{cursor:pointer}
  .hb-mus2-plsub.link:hover{color:var(--hb-ink,#0d1622);text-decoration:underline}
  .hb-mus2-acts{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-top:2px}
  .hb-mus2-renin{font:inherit;font-size:20px;font-weight:800;border:1px solid var(--hb-accent,#3D6FE0);border-radius:8px;
                 padding:2px 8px;background:var(--hb-bg,transparent);color:var(--hb-ink,#0d1622);min-width:0;width:100%;box-sizing:border-box}
  .hb-mus2-playfab{position:absolute;right:8px;bottom:8px;width:44px;height:44px;border-radius:50%;
                   background:var(--sp-green);color:#0b1a10;border:0;cursor:pointer;
                   display:flex;align-items:center;justify-content:center;box-shadow:0 6px 14px rgba(0,0,0,.35);
                   transition:transform .15s}
  .hb-mus2-playfab svg{width:18px;height:18px}
  .hb-mus2-playfab:hover{transform:scale(1.06)}
  .hb-mus2-playfab:disabled{opacity:.4;cursor:default;box-shadow:none;transform:none}

  /* artists: round faces in a row that scrolls sideways */
  .hb-mus2-faces{display:flex;gap:12px;overflow-x:auto;padding-bottom:2px}
  .hb-mus2-face{flex:0 0 auto;width:84px;display:flex;flex-direction:column;align-items:center;gap:6px;cursor:pointer;
                text-align:center;border-radius:10px;padding:6px 2px}
  .hb-mus2-face:hover{background:var(--mus-hover)}
  .hb-mus2-face .hb-mus2-art{width:64px;height:64px;border-radius:50%}
  .hb-mus2-facen{font-size:12px;font-weight:600;max-width:80px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}

  /* ── THE TRANSPORT, lifted off the content: its own tone, a hairline, a soft upward shadow, and a thin
     progress line along its top edge (the mini-player's own shape) ── */
  .hb-mus2-bar{flex:0 0 auto;position:relative;border-top:1px solid var(--mus-line);background:var(--hb-bg-soft,rgba(127,127,127,.06));
               box-shadow:0 -10px 24px -18px rgba(0,0,0,.55);padding:9px 14px 8px;display:flex;flex-direction:column;gap:4px}
  .hb-mus2-barrow{display:flex;align-items:center;gap:10px;min-width:0}
  .hb-mus2-tapsound{display:block;width:100%;margin:0 0 8px;padding:9px 12px;border:0;border-radius:10px;cursor:pointer;
    background:var(--hb-accent,#7c5cff);color:#fff;font-size:13px;font-weight:600;text-align:center}
  /* V2-795 — the progress row: elapsed · the rail you click or drag · total, then the volume you can SEE */
  .hb-mus2-barprog{display:flex;align-items:center;gap:8px;min-width:0;height:20px}
  .hb-mus2-bartime{font-size:12px;color:var(--hb-muted-2,#9aa7b8);font-variant-numeric:tabular-nums;min-width:34px;flex:0 0 auto}
  .hb-mus2-bartime.r{text-align:right}
  .hb-mus2-barprog .hb-mus2-cbtn{padding:3px}
  .hb-mus2-barprog .hb-mus2-cbtn svg{width:16px;height:16px}
  .hb-mus2-barartwrap{position:relative;flex:0 0 auto}
  .hb-mus2-bar .hb-mus2-art{width:44px;height:44px;border-radius:8px;box-shadow:0 3px 10px rgba(0,0,0,.18)}
  .hb-mus2-bar.empty .hb-mus2-art{background:var(--hb-bg,transparent);border:1.5px dashed var(--hb-line,#e3e8f0);
                                  box-shadow:none;color:var(--hb-muted,#5b6b82)}
  .hb-mus2-bar.empty .hb-mus2-art svg{color:var(--hb-muted,#5b6b82)}
  .hb-mus2-areq{position:absolute;right:-3px;bottom:-3px;width:19px;height:19px;border-radius:50%;
                background:var(--hb-ink,#0d1622);display:flex;align-items:center;justify-content:center;
                box-shadow:0 0 0 2px var(--hb-bg-soft,#fbfdff)}
  .hb-mus2-areq .hb-mus2-eq{width:10px;height:9px}
  .hb-mus2-areq .hb-mus2-eq span{width:2px}
  .hb-mus2-barmeta{min-width:0;flex:1}
  .hb-mus2-bart{font-size:15px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-mus2-bara{font-size:12.5px;color:var(--hb-muted,#5b6b82);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .hb-mus2-baridle{font-size:13px;font-weight:600;color:var(--hb-muted,#5b6b82);font-style:italic}
  .hb-mus2-barc{display:flex;align-items:center;gap:2px;flex:0 0 auto}
  .hb-mus2-barside{display:flex;align-items:center;gap:2px;flex:0 0 auto}
  .hb-mus2-cbtn{border:0;background:none;color:var(--hb-ink,#0d1622);cursor:pointer;padding:6px;
                border-radius:8px;line-height:1;display:flex;position:relative}
  .hb-mus2-cbtn svg{width:18px;height:18px}
  .hb-mus2-cbtn:hover{color:var(--hb-accent,#3D6FE0)}
  .hb-mus2-cbtn.mode{color:var(--hb-muted,#5b6b82)}
  .hb-mus2-cbtn.mode svg{width:16px;height:16px}
  .hb-mus2-cbtn.mode.on{color:var(--sp-green)}
  .hb-mus2-cbtn.mode.on::after{content:"";position:absolute;left:50%;bottom:1px;width:4px;height:4px;margin-left:-2px;
                               border-radius:50%;background:var(--sp-green)}
  .hb-mus2-cbtn.fav{color:var(--sp-green)}
  .hb-mus2-cbtn.fav:hover{color:var(--sp-green);opacity:.8}
  .hb-mus2-cbtn.main{width:38px;height:38px;border-radius:50%;background:var(--hb-ink,#0d1622);margin:0 3px;
                     color:var(--hb-bg,#fff);align-items:center;justify-content:center;padding:0;
                     box-shadow:0 4px 12px rgba(0,0,0,.28)}
  .hb-mus2-cbtn.main svg{width:16px;height:16px}
  .hb-mus2-cbtn.main:hover{color:var(--hb-bg,#fff);opacity:.88}
  .hb-mus2-cbtn:disabled{opacity:.32;cursor:default;pointer-events:none}
  /* the volume, always visible: where it is, clickable, draggable — the same rail drawing as the progress */
  .hb-mus2-vol{width:72px;flex:0 0 auto;accent-color:var(--hb-ink,#0d1622);height:14px;margin:0;cursor:pointer}
  .hb-mus2-vol:hover{accent-color:var(--sp-green)}
  .hb-mus2-barrail{position:relative;flex:1 1 auto;height:14px;cursor:pointer;touch-action:none;min-width:40px}
  .hb-mus2-barrail i{position:absolute;left:0;right:0;top:5px;height:4px;border-radius:999px;background:var(--hb-line,#e3e8f0)}
  .hb-mus2-barrail b{position:absolute;left:0;top:5px;height:4px;border-radius:999px;background:var(--hb-ink,#0d1622);max-width:100%}
  .hb-mus2-barrail u{position:absolute;top:2px;width:10px;height:10px;margin-left:-5px;border-radius:50%;background:var(--sp-green);
                     box-shadow:0 1px 4px rgba(0,0,0,.45);opacity:0;transition:opacity .12s}
  .hb-mus2-barrail:hover b,.hb-mus2-barrail.hb-mus2-drag b{background:var(--sp-green)}
  .hb-mus2-barrail:hover u,.hb-mus2-barrail.hb-mus2-drag u{opacity:1}
  /* the card is resizable: the play modes are the first things to go when it is narrow */
  @container (width <= 400px){ .hb-mus2-barc .mode{display:none} .hb-mus2-vol{width:52px} }

  .hb-mus2-connect{display:flex;flex-direction:column;gap:8px}
  .hb-mus2-sub{font-size:12.5px;color:var(--hb-muted,#5b6b82);line-height:1.45}
  .hb-mus2-btn{border:0;background:var(--hb-accent,#3D6FE0);color:var(--canvas,#101216);border-radius:10px;padding:9px 13px;
               font-size:13px;font-weight:700;cursor:pointer;line-height:1;align-self:flex-start}
  .hb-mus2-btn:disabled{opacity:.5;cursor:default}
  .hb-mus2-btn.ghost{background:var(--mus-card);color:var(--hb-ink,#0d1622);border:1px solid var(--hb-line,#e3e8f0)}
  .hb-mus2-inp{width:100%;box-sizing:border-box;border:1px solid var(--hb-line,#e3e8f0);border-radius:8px;
               padding:6px 9px;font-size:13px;background:var(--hb-bg,transparent);color:var(--hb-ink,#0d1622)}
  .hb-mus2-newinp{width:150px}
  .hb-mus2-audio{position:absolute;width:1px;height:1px;opacity:0;pointer-events:none;left:-9999px;top:0}
  .hb-mus2-frame{width:1px;height:1px;border:0}
  .hb-mus2-eq{display:flex;align-items:flex-end;gap:2px;width:14px;height:14px}
  .hb-mus2-eq span{width:3px;background:var(--sp-green);border-radius:1px;animation:hbMusEq .9s ease-in-out infinite}
  .hb-mus2-eq span:nth-child(1){height:40%;animation-delay:-.6s}
  .hb-mus2-eq span:nth-child(2){height:100%;animation-delay:-.3s}
  .hb-mus2-eq span:nth-child(3){height:65%;animation-delay:0s}
  @keyframes hbMusEq{0%,100%{transform:scaleY(.4)}50%{transform:scaleY(1)}}

  /* ── AHORA SUENA — the song IS the screen (V2-717): sized against the HEIGHT that is there, so the whole ficha
     fits the card's first footprint with nothing to scroll ── */
  .hb-mus2-now{display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;
               width:100%;max-width:520px;height:100%;margin:0 auto;box-sizing:border-box}
  .hb-mus2-nowart{position:relative;height:min(68%,320px);width:auto;max-width:72%;aspect-ratio:1/1;
                  border-radius:16px;overflow:hidden;flex:0 1 auto;display:flex;align-items:center;justify-content:center;
                  background:linear-gradient(135deg,var(--hb-accent,#3D6FE0),var(--hb-accent2,#16B8A6));
                  box-shadow:0 26px 48px -20px rgba(0,0,0,.62),0 2px 8px rgba(0,0,0,.18)}
  .hb-mus2-nowart img{width:100%;height:100%;object-fit:cover}
  .hb-mus2-nowart svg{width:34%;height:34%;color:rgba(255,255,255,.92)}
  .hb-mus2-nowt{font-size:20px;font-weight:800;letter-spacing:-.02em;line-height:1.22;
                margin-top:clamp(10px,4%,20px);flex:0 0 auto;
                display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;word-break:break-word}
  .hb-mus2-nowa{font-size:14px;color:var(--hb-muted,#5b6b82);margin-top:6px;white-space:nowrap;overflow:hidden;
                text-overflow:ellipsis;max-width:100%}
  .hb-mus2-nowa.link{cursor:pointer}
  .hb-mus2-nowa.link:hover{color:var(--hb-ink,#0d1622);text-decoration:underline}
  .hb-mus2-nowm{display:flex;align-items:center;justify-content:center;gap:8px;margin-top:10px;font-size:12px;
                letter-spacing:.06em;text-transform:uppercase;color:var(--hb-muted-2,#9aa7b8)}
  .hb-mus2-nowm .hb-mus2-eq{width:11px;height:10px}
  .hb-mus2-nowm i{font-style:normal;opacity:.45}
  /* the scrubber's slot needs a width of its own: in a centred column a bare div shrinks to nothing (V2-717) */
  .hb-mus2-seekslot{width:100%;flex:0 0 auto}
  .hb-mus2-seek{width:100%;margin-top:clamp(12px,4%,22px);display:flex;align-items:center;gap:10px}
  .hb-mus2-time{font-size:12px;color:var(--hb-muted-2,#9aa7b8);min-width:40px;flex:0 0 auto;font-variant-numeric:tabular-nums}
  .hb-mus2-time.r{text-align:right}
  .hb-mus2-rail{position:relative;flex:1 1 auto;height:18px;display:flex;align-items:center;cursor:pointer;touch-action:none}
  .hb-mus2-railbg{position:absolute;left:0;right:0;height:4px;border-radius:999px;background:var(--hb-line,#e3e8f0)}
  .hb-mus2-fill{position:absolute;left:0;height:4px;border-radius:999px;background:var(--hb-ink,#0d1622);
                max-width:100%;transition:background .15s}
  .hb-mus2-knob{position:absolute;width:11px;height:11px;border-radius:50%;background:var(--hb-ink,#0d1622);
                box-shadow:0 1px 5px rgba(0,0,0,.45);transform:translateX(-50%);opacity:0;transition:opacity .12s}
  .hb-mus2-rail:hover .hb-mus2-fill,.hb-mus2-rail.hb-mus2-drag .hb-mus2-fill{background:var(--sp-green)}
  .hb-mus2-rail:hover .hb-mus2-knob,.hb-mus2-rail.hb-mus2-drag .hb-mus2-knob{opacity:1;background:var(--sp-green)}

  /* ── an empty library still has something to say (V2-717); its chips are REAL: each one plays ── */
  .hb-mus2-hero{display:flex;flex-direction:column;align-items:center;text-align:center;gap:12px;margin:auto;
                padding:10px 0;max-width:340px}
  .hb-mus2-herod{position:relative;width:76px;height:76px;border-radius:50%;flex:0 0 auto;
                 display:flex;align-items:center;justify-content:center;
                 background:linear-gradient(135deg,var(--hb-accent,#3D6FE0),var(--hb-accent2,#16B8A6));
                 box-shadow:0 14px 30px -12px rgba(0,0,0,.55)}
  .hb-mus2-herod svg{width:31px;height:31px;color:#fff}
  .hb-mus2-herod::after{content:"";position:absolute;inset:-9px;border-radius:50%;
                        border:1.5px solid var(--hb-accent,#3D6FE0);opacity:.3;animation:hbMusRing 3.2s ease-out infinite}
  @keyframes hbMusRing{0%{transform:scale(.92);opacity:.34}70%{transform:scale(1.12);opacity:0}100%{opacity:0}}
  .hb-mus2-herot{font-size:16.5px;font-weight:800;letter-spacing:-.015em}
  .hb-mus2-heros{font-size:12.5px;color:var(--hb-muted,#5b6b82);line-height:1.5}
  .hb-mus2-chips{display:flex;flex-wrap:wrap;gap:7px;justify-content:center}
  .hb-mus2-chip{border:1px solid var(--hb-line,#e3e8f0);background:var(--mus-panel);
                color:var(--hb-ink,#0d1622);border-radius:999px;padding:6px 12px;font-size:12.5px;font-weight:600;
                cursor:pointer;line-height:1.2}
  .hb-mus2-chip:hover{border-color:var(--hb-accent,#3D6FE0);color:var(--hb-accent,#3D6FE0)}
  .hb-mus2-hero .hb-mus2-pl{width:auto;align-items:center;gap:5px;background:none;padding:2px}
  .hb-mus2-hero .hb-mus2-pl:hover{transform:none;box-shadow:none}
  .hb-mus2-hero .hb-mus2-new .hb-mus2-art{width:44px;height:44px;border-radius:12px}
  .hb-mus2-hero .hb-mus2-plname{font-size:12px;color:var(--hb-muted,#5b6b82)}
  `; document.head.appendChild(s);
}

// ── icon set, "our line" (V2-629) ────────────────────────────────────────────────────────────────────────
// Two attribute sets, never combined on one <svg> — the HTML parser keeps the FIRST occurrence of a duplicate
// attribute, so an outline base plus a later fill override stays an outline forever.
const _SW = 'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" ' +
           'stroke-linejoin="round"';                                            // OUTLINE icons
const _SF = 'viewBox="0 0 24 24" fill="currentColor" stroke="none"';              // SOLID icons
const ICON_NOTE      = `<svg ${_SW}><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>`;
const ICON_PLUS       = `<svg ${_SW}><path d="M12 5v14"/><path d="M5 12h14"/></svg>`;
const ICON_BACK       = `<svg ${_SW}><path d="m15 18-6-6 6-6"/></svg>`;
const ICON_CLOSE      = `<svg ${_SW}><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>`;
const ICON_PREV       = `<svg ${_SW}><polygon points="19 20 9 12 19 4 19 20"/><line x1="5" y1="19" x2="5" y2="5"/></svg>`;
const ICON_NEXT       = `<svg ${_SW}><polygon points="5 4 15 12 5 20 5 4"/><line x1="19" y1="5" x2="19" y2="19"/></svg>`;
const ICON_PLAY       = `<svg ${_SF}><path d="M8 5v14l11-7z"/></svg>`;
const ICON_PAUSE      = `<svg ${_SF}><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>`;
const ICON_VOL_OFF    = `<svg ${_SW}><path d="M11 5 6 9H2v6h4l5 4V5z"/><path d="m22 9-6 6"/><path d="m16 9 6 6"/></svg>`;
const ICON_VOL_UP     = `<svg ${_SW}><path d="M11 5 6 9H2v6h4l5 4V5z"/><path d="M15.5 8.5a5 5 0 0 1 0 7"/><path d="M18.5 5.5a9 9 0 0 1 0 13"/></svg>`;
const ICON_LIST       = `<svg ${_SW}><path d="M8 6h13"/><path d="M8 12h13"/><path d="M8 18h13"/><path d="M3 6h.01"/><path d="M3 12h.01"/><path d="M3 18h.01"/></svg>`;
const ICON_QUEUE      = `<svg ${_SW}><path d="M3 6h13"/><path d="M3 12h9"/><path d="M3 18h9"/><path d="m16 13 5 3-5 3z"/></svg>`;
const ICON_SEARCH     = `<svg ${_SW}><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>`;
const ICON_SHUFFLE    = `<svg ${_SW}><path d="M16 3h5v5"/><path d="M4 20 21 3"/><path d="M21 16v5h-5"/><path d="m15 15 6 6"/><path d="M4 4l5 5"/></svg>`;
const ICON_REPEAT     = `<svg ${_SW}><path d="m17 2 4 4-4 4"/><path d="M3 11v-1a4 4 0 0 1 4-4h14"/><path d="m7 22-4-4 4-4"/><path d="M21 13v1a4 4 0 0 1-4 4H3"/></svg>`;
const ICON_REPEAT_ONE = `<svg ${_SW}><path d="m17 2 4 4-4 4"/><path d="M3 11v-1a4 4 0 0 1 4-4h14"/><path d="m7 22-4-4 4-4"/><path d="M21 13v1a4 4 0 0 1-4 4H3"/><path d="M11 10h1v4"/></svg>`;
const ICON_EDIT       = `<svg ${_SW}><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/></svg>`;
const ICON_TRASH      = `<svg ${_SW}><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/></svg>`;
const ICON_GRIP       = `<svg ${_SW}><circle cx="9" cy="6" r="1"/><circle cx="15" cy="6" r="1"/><circle cx="9" cy="12" r="1"/><circle cx="15" cy="12" r="1"/><circle cx="9" cy="18" r="1"/><circle cx="15" cy="18" r="1"/></svg>`;
const ICON_ADDLIST    = `<svg ${_SW}><path d="M3 6h12"/><path d="M3 12h12"/><path d="M3 18h8"/><path d="M18 14v8"/><path d="M14 18h8"/></svg>`;
const ICON_HEART      = `<svg ${_SW}><path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.6l-1-1a5.5 5.5 0 0 0-7.8 7.8l1 1L12 21l7.8-7.8 1-1a5.5 5.5 0 0 0 0-7.6z"/></svg>`;
const ICON_HEART_FILL = `<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="2" ` +
  `stroke-linecap="round" stroke-linejoin="round"><path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.6l-1-1a5.5 5.5 ` +
  `0 0 0-7.8 7.8l1 1L12 21l7.8-7.8 1-1a5.5 5.5 0 0 0 0-7.6z"/></svg>`;

// Raw SVG markup -> element (same trick as frontend/app/core/dom.js::raw — duplicated, widgets never import
// app-shell code).
function svgEl(markup){
  const t = document.createElement("template");
  t.innerHTML = markup.trim();
  return t.content.firstElementChild;
}

function h(tag, cls, text){
  const e = document.createElement(tag);
  if(cls) e.className = cls;
  if(text != null) e.textContent = String(text);
  return e;
}

// Animated "now playing" bars — the visible signal that THIS row/mini-player is the one making sound.
function eqIcon(){
  const wrap = h("div", "hb-mus2-eq");
  wrap.appendChild(h("span")); wrap.appendChild(h("span")); wrap.appendChild(h("span"));
  return wrap;
}

// Cover art: image (Spotify URL) or fallback emoji. URL goes into img.src, never innerHTML.
function artNode(art, fallback){
  const a = h("div", "hb-mus2-art");
  const paintFallback = () => { a.textContent = ""; a.appendChild(svgEl(fallback || ICON_NOTE)); };
  if(art){
    const img = document.createElement("img"); img.src = art; img.alt = "";
    // A dead or since-removed thumbnail (V2-629) degrades to the SAME placeholder a missing one gets,
    // instead of the browser's broken-image glyph — cheap, and it is what "a player nicer than the rest"
    // means for the one part of this that is a hotlink to somebody else's server (the V2-563 fact of life).
    img.onerror = paintFallback;
    a.appendChild(img);
  }
  // A crisp SVG placeholder instead of an emoji glyph (V2-629): an emoji font renders differently per OS —
  // the exact "looks like a different app" seam a redesign is supposed to close — an inline vector does not.
  else paintFallback();
  return a;
}

// Text compare for "is this the track that's playing" — accent/case-insensitive, same spirit as the server's
// own `_norm` (data.py), kept separately here because widget.js never imports server code (V2-557).
function _norm(s){
  return String(s || "").normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
}

function nowPlayingMatches(t, np){
  if(!np) return false;
  const a = _norm(t.title || t.query), b = _norm(np.title);
  if(!a || !b) return false;
  const aa = _norm(t.artist), ba = _norm(np.artist);
  if(a === b) return (aa && ba) ? aa === ba : true;   // missing artist on either side: the title match is enough
  // A legacy merged title ("madonna papa don't preach", no separate artist field) played through a CONNECTED
  // provider reports its own clean, real title ("papa don't preach") — a plain equality never matches, so this
  // row would never light up for the exact case the redesign exists to fix. If the stored title ENDS with the
  // now-playing title, treat the leftover prefix as the artist and require it to agree with `np.artist` when
  // that is known — a bare suffix match with no artist to cross-check would risk lighting up an unrelated song
  // that merely ends the same way.
  if(!aa && b.length > 3 && a.endsWith(b)){
    const prefix = a.slice(0, a.length - b.length).trim();
    return !ba || prefix === ba || prefix.endsWith(ba);
  }
  return false;
}

// A playlist where every track shares the SAME artist should say that artist ONCE (the header), not on every
// row — the operator's complaint on a playlist that happened to be one Madonna album, titles like "Madonna
// Papa Don't Preach" repeated verbatim in each row. Two cases: (1) tracks already carry a proper `artist`
// field, uniformly — show it, strip nothing (`title`/`artist` were already separate). (2) legacy/free-text
// data where the artist got baked INTO `title` with no separator (a bare `query` used as the title, V2-384's
// "one call is all the model gets" combined with a search string that already had the artist inside it): if
// EVERY track's title starts with the same leading word(s) and something real is left over after them, treat
// that shared prefix as the artist for DISPLAY ONLY — the stored data is never touched, so this is always
// reversible and never invents a fact that is not already, verbatim, in every row.
function deriveArtistInfo(tracks){
  const list = tracks || [];
  const noStrip = {commonArtist: "", strip: (title) => title};
  if(list.length < 2) return noStrip;

  const artists = list.map(t => String(t.artist || "").trim());
  if(artists.every(a => a)){
    return (new Set(artists.map(_norm)).size === 1) ? {commonArtist: artists[0], strip: (t) => t} : noStrip;
  }
  if(artists.some(a => a)) return noStrip;   // mixed metadata quality (some tagged, some not) — don't guess

  const wordLists = list.map(t => String(t.title || "").trim().split(/\s+/).filter(Boolean));
  const minWords = Math.min(...wordLists.map(w => w.length));
  if(minWords < 2) return noStrip;
  let k = 0;
  for(let i = 0; i < minWords - 1; i++){       // leave at least one real word behind as the title
    const w0 = _norm(wordLists[0][i]);
    if(!w0 || !wordLists.every(w => _norm(w[i]) === w0)) break;
    k = i + 1;
  }
  if(k === 0) return noStrip;
  const commonArtist = wordLists[0].slice(0, k).join(" ");
  return {
    commonArtist,
    strip: (title) => {
      const words = String(title || "").trim().split(/\s+/);
      return words.length > k ? words.slice(k).join(" ") : title;
    },
  };
}

function ytPost(iframe, func, args){
  try{ if(iframe && iframe.contentWindow)
    iframe.contentWindow.postMessage(JSON.stringify({event:"command", func:func, args:args||[]}), "*"); }catch(_){}
}
// Ensure the player is audible (unmute + set volume): on mount and every command, so "no audio" actually wakes up.
function ytEnsureAudible(iframe, vol){
  ytPost(iframe, "unMute");
  ytPost(iframe, "setVolume", [Math.max(0, Math.min(100, vol||70))]);
}

// YouTube player events (V2-047 F4/F10): `listening` handshake -> onReady/onStateChange(ENDED).
//
// V2-717 — the SAME handshake already delivers the clock. Once `listening` is sent the embed posts
// `infoDelivery` frames carrying `currentTime` and `duration`; nothing extra is asked of it and no network
// call of ours is involved. Kept as a stamped sample (`at`) rather than a running counter so the bar can
// interpolate between frames instead of stepping, and thrown away whenever the video changes — a position
// belonging to the PREVIOUS song, painted for a quarter of a second on the new one, is a lie the eye catches.
let _ytReady = null, _ytEnded = null;
// V2-812 — what the page player REALLY does with the sound. A phone browser may keep a muted-autoplay start silent
// (refuse the unmute, or never start) until a tap on the page. The embed says so in its own `infoDelivery`
// (`muted`, `playerState`); the card reports it as `player_audio` and shows a tap row while it lasts.
let _ytSound = null;                   // per-render reporter: (info) → `player_audio` when it disagrees with the store
let _ytLoadedAt = 0;                   // when the current song's frame was mounted: a silence inside the grace is not a verdict
const _SOUND_GRACE_MS = 2500;
let _ytClock = {vid: "", t: 0, d: 0, at: 0};
function ytStartListening(iframe){
  try{ iframe.contentWindow.postMessage(JSON.stringify({event:"listening", id:"hb-musica", channel:"widget"}), "*"); }catch(_){}
}
if (typeof window !== "undefined" && !window.__hbMusicaYtBound){
  window.__hbMusicaYtBound = true;
  window.addEventListener("message", (ev) => {
    if (typeof ev.data !== "string" || ev.data.indexOf("\"event\"") < 0) return;
    let d; try{ d = JSON.parse(ev.data); }catch(_){ return; }
    // Only OUR hidden player (the handshake id): the youtube WIDGET's player also emits onStateChange on this
    // same window since V2-366, and without this filter a video ending would advance the MUSIC queue.
    if (d.id !== "hb-musica") return;
    if (d.event === "onReady" && _ytReady) _ytReady();
    else if (d.event === "onStateChange" && Number(d.info) === 0 && _ytEnded) _ytEnded();   // 0 = ENDED
    else if (d.event === "infoDelivery" && d.info && typeof d.info === "object"){
      const info = d.info;
      if (typeof info.currentTime === "number"){ _ytClock.t = info.currentTime; _ytClock.at = Date.now(); }
      if (typeof info.duration === "number" && info.duration > 0) _ytClock.d = info.duration;
      if (_ytSound && (typeof info.muted === "boolean" || typeof info.playerState === "number")) _ytSound(info);
    }
  });
}

// A seek asked by VOICE («adelanta un minuto», «ponla en el minuto dos») arrives as a COMMAND in the store —
// `{n, to, by}` — never as a position, because the position only exists HERE: the hidden iframe and the
// <audio> element live in this page and the server has never held a clock for them. `n` is a counter of its
// own and deliberately NOT `cmd_seq`: riding on cmd_seq would re-apply the last seek on every later pause or
// volume command, which is a song that jumps backwards every time you touch the volume.
function applyPendingSeek(el, blk, getPos, seekTo){
  const sk = blk && blk.seek;
  const n = sk ? Number(sk.n || 0) : 0;
  if(!n || el._hbSeekN === n) return;
  el._hbSeekN = n;
  const abs = (sk.to !== undefined && sk.to !== null && sk.to !== "");
  const to = abs ? Number(sk.to) : Number(getPos() || 0) + Number(sk.by || 0);
  if(isFinite(to)) seekTo(Math.max(0, to));
}

// Where the YouTube song IS, interpolated from the last sample the embed sent (see `_ytClock`). Returns null
// while the clock says nothing — a player that has not answered yet must draw NO scrubber rather than a bar
// pinned at zero that looks broken.
function ytPosition(vid, playing){
  if(!vid || _ytClock.vid !== vid || !_ytClock.at) return null;
  const drift = playing ? (Date.now() - _ytClock.at) / 1000 : 0;
  const dur = _ytClock.d || 0;
  const pos = Math.max(0, _ytClock.t + drift);
  return {pos: dur ? Math.min(pos, dur) : pos, dur};
}

// The hidden player lives in a persistent host (`el._ytHost`) that is NOT rebuilt when the view re-renders, so
// reorder/navigation never restarts the song. The iframe is recreated only if videoId changes.
// Is the agent STOPPED? (V2-092): when power is off, music should not play, and especially should not start by
// itself on page reload. The bug was that saved state said "playing" and the iframe was born with `autoplay=1`.
// `ctx.running` is a live canvas getter reflecting server truth (nucleo/runstate.py). Treat it as stopped only when
// explicit; a ctx without the field must not leave the player muted forever.
function halted(ctx){ return !!(ctx && ctx.running === false); }

// V2-638 — a track that is a FILE we hold plays HERE, in the page, through a plain <audio> against our own
// library route. It shares `_ytHost` with the hidden YouTube iframe because only one of the two can ever be
// mounted (the server clears the yt block when a local track starts), and the same memo guards (`_hbSeq`)
// keep a re-render from restarting the song — the reason the seq exists at all is that asking for the SAME
// file twice must still be two events.
function syncLocalPlayer(el, data, ctx){
  const loc = data.local || {};
  const host = el._ytHost;
  const stopped = halted(ctx);
  if(!loc.src){
    if(el._hbAudio){ host.textContent = ""; el._hbAudio = null; el._hbLocal = null; el._hbLocSeq = null; }
    return false;
  }
  if(el._hbLocal === loc.src && el._hbAudio){        // same file -> only apply the new command
    applyPendingSeek(el, loc, () => el._hbAudio.currentTime,
                     (secs) => { try{ el._hbAudio.currentTime = secs; }catch(_){} });
    if(el._hbLocSeq !== loc.seq){
      el._hbLocSeq = loc.seq;
      if(loc.paused || stopped) el._hbAudio.pause();
      else { try{ el._hbAudio.currentTime = 0; }catch(_){} const q = el._hbAudio.play(); if(q && q.catch) q.catch(function(){}); }
    }
    return true;
  }
  host.textContent = "";
  el._hbFrame = null; el._hbVid = null; el._hbSeq = null;   // the iframe, if any, is gone with the innerHTML
  el._hbSeekN = Number((loc.seek || {}).n || 0);            // a seek asked of the PREVIOUS file is not asked here
  const a = document.createElement("audio");
  a.className = "hb-mus2-audio-el";
  a.preload = "metadata";
  // Our own library route only — never an arbitrary origin (the V2-620 boundary).
  if(String(loc.src).startsWith("/api/library/")) a.src = loc.src;
  if(!(loc.paused || stopped)){ const q = a.play(); if(q && q.catch) q.catch(function(){}); }
  a.addEventListener("ended", function(){ try{ ctx.action("ended"); }catch(_){} });
  host.appendChild(a);
  el._hbAudio = a; el._hbLocal = loc.src; el._hbLocSeq = loc.seq;
  return true;
}

// V2-812 — the page player's real sound against what the store wants. Silent = the player reports itself muted, or
// not playing (state other than 1 playing / 3 buffering), past the grace, while sound is wanted. Heard clears it.
function bindSoundReport(el, data, ctx){
  const yt = data.yt || {};
  let sent = "";
  _ytSound = (info) => {
    if(!ctx || !ctx.action || halted(ctx) || !yt.videoId || yt.paused || yt.muted) return;
    const state = Number(info.playerState);
    const silent = info.muted === true || (typeof info.playerState === "number" && state !== 1 && state !== 3);
    if(silent && Date.now() - _ytLoadedAt < _SOUND_GRACE_MS) return;
    if(silent === !!yt.audio_blocked) return;
    const key = yt.videoId + "|" + silent + "|" + (yt.cmd_seq || 0);
    if(key === sent) return;
    sent = key;
    try{ const q = ctx.action("player_audio", {muted: silent, videoId: yt.videoId}); if(q && q.catch) q.catch(() => {}); }catch(_){}
  };
}

// A TAP is the only thing a phone browser accepts as permission to sound: the player is unmuted and started inside
// that same gesture. Any tap on the page does it while the block lasts; the row below names it.
function unlockSound(el, data){
  const yt = data.yt || {};
  if(!el._hbFrame) return;
  ytEnsureAudible(el._hbFrame, yt.volume);
  ytPost(el._hbFrame, "playVideo");
}
function armSoundUnlock(el, data){
  if(el._hbUnlockArmed || typeof document === "undefined") return;
  el._hbUnlockArmed = true;
  const go = () => {
    el._hbUnlockArmed = false;
    document.removeEventListener("pointerdown", go, true);
    unlockSound(el, el._hbData || data);
  };
  document.addEventListener("pointerdown", go, true);
}
function soundRow(el, data){
  const yt = data.yt || {};
  if(data.mode !== "youtube" || !yt.audio_blocked || yt.paused || yt.muted) return null;
  const b = h("button", "hb-mus2-tapsound", "🔈 " + tt("tap_sound", null, "Toca aquí para que suene en esta pantalla"));
  b.onclick = () => unlockSound(el, data);
  return b;
}

function syncYtPlayer(el, data, ctx){
  const yt = data.yt || {};
  const host = el._ytHost;
  const stopped = halted(ctx);
  el._hbData = data;
  bindSoundReport(el, data, ctx);
  if(yt.audio_blocked && !yt.paused && !stopped) armSoundUnlock(el, data);
  // A local file and a YouTube track can never sound at once: if one is mounted the other releases.
  if(syncLocalPlayer(el, data, ctx)) return;
  if(!yt.videoId){                                   // nothing playing through YouTube -> release the frame
    if(el._hbFrame){ host.textContent = ""; el._hbFrame = null; el._hbVid = null; el._hbSeq = null; }
    return;
  }
  if(el._hbVid === yt.videoId && el._hbFrame){       // same video -> only apply the new command
    applyPendingSeek(el, yt, () => { const p = ytPosition(yt.videoId, !yt.paused); return p ? p.pos : 0; },
                     (secs) => { ytPost(el._hbFrame, "seekTo", [secs, true]);
                                 _ytClock.t = secs; _ytClock.at = Date.now(); });
    if(el._hbSeq !== yt.cmd_seq){
      el._hbSeq = yt.cmd_seq;
      if(yt.paused || stopped){ ytPost(el._hbFrame, "pauseVideo"); }
      else { ytEnsureAudible(el._hbFrame, yt.volume); ytPost(el._hbFrame, "playVideo"); }
    }
    return;
  }
  // New video -> hidden iframe. Guaranteed start: mute=1 because muted autoplay is always allowed, then unmute
  // immediately through the API because the page already has operator interaction. With the agent stopped,
  // `autoplay` is disabled in the `src` itself; any later pause would arrive too late and the start would be heard.
  host.textContent = "";
  _ytClock = {vid: yt.videoId, t: 0, d: 0, at: 0};   // a new song, a new clock — never the old song's seconds
  // A seek asked of the PREVIOUS song never reaches this one: the provider drops it when it loads a new
  // video (`_bump(yt, "load")`). So a command still standing here arrived AFTER the load — «pon X y ponla en
  // el minuto dos» in one breath — and is applied once the player answers, not discarded.
  const frame = document.createElement("iframe");
  frame.className = "hb-mus2-frame";
  frame.allow = "autoplay";
  frame.src = "https://www.youtube-nocookie.com/embed/" + encodeURIComponent(yt.videoId)
            + "?enablejsapi=1&autoplay=" + ((yt.paused || stopped) ? 0 : 1)
            + "&mute=1&controls=0&playsinline=1&rel=0";
  frame.addEventListener("load", () => ytStartListening(frame));
  host.appendChild(frame);
  el._hbFrame = frame; el._hbVid = yt.videoId; el._hbSeq = yt.cmd_seq;
  el._hbSeekN = 0;
  const wake = () => {
    if(halted(ctx)){ ytPost(frame, "pauseVideo"); return; }   // re-read because `wake` runs in timeouts up to 2.6s
    ytEnsureAudible(frame, yt.volume); if(!yt.paused) ytPost(frame, "playVideo");
    applyPendingSeek(el, yt, () => { const p = ytPosition(yt.videoId, true); return p ? p.pos : 0; },
                     (secs) => { ytPost(frame, "seekTo", [secs, true]); _ytClock.t = secs; _ytClock.at = Date.now(); });
  };
  _ytLoadedAt = Date.now();
  _ytReady = wake;                                   // real onReady is the exact moment; timeouts back it up
  _ytEnded = () => { try{ ctx.action("ended"); }catch(_){} };   // F4: on end -> advance queue on the server
  setTimeout(wake, 1200); setTimeout(wake, 2600);
}

// Playback bar (Spotify or YouTube).
function nowPlaying(data){
  if(data.now_playing && data.now_playing.title) return data.now_playing;
  const yt = data.yt || {};
  // yt.art/yt.artist (V2-629): the connector already resolves free cover art the instant it knows a videoId,
  // and the server splits an "Artist - Title" upload title for display — both arrive ready on `data.yt`.
  if(yt.videoId) return {title: yt.title || tt("music_fb", null, "Música"), artist: yt.artist || "", art: yt.art || "", playing: !yt.paused};
  // V2-795 — a file of the agent's own library is the third thing that can be sounding (V2-638), and the bar
  // showed nothing while it played.
  const loc = data.local || {};
  if(loc.src) return {title: loc.title || tt("music_fb", null, "Música"), artist: loc.artist || "", art: loc.art || "", playing: !loc.paused};
  return null;
}

// Lazy cover-art ENRICHMENT (V2-629): asked once per (title, artist) per page life, always AFTER the row/bar
// is already on screen with its fallback icon — never on anything that would delay playback starting.
const _enrichAsked = new Set();
function maybeEnrich(t, ctx){
  if(!t || t.art) return;
  const title = (t.title || t.query || "").trim();
  if(!title) return;
  const key = _norm(title) + "|" + _norm(t.artist || "");
  if(_enrichAsked.has(key)) return;
  _enrichAsked.add(key);
  // Defensive against ANY ctx implementation, not just the desktop host's own Promise-returning one — the
  // same caution `ended` already takes two lines below (`try{ ctx.action("ended"); }catch(_){}`), extended to
  // also tolerate a return value that is not thenable at all.
  try {
    const p = ctx.action("enrich_art", {title, artist: t.artist || ""});
    if (p && typeof p.catch === "function") p.catch(() => {});
  } catch (_) {}
}

// ── V2-717 · WHERE THE SONG IS, whoever is playing it ────────────────────────────────────────────────────
// Three players, one question. The two that play IN this page answer it themselves — a hidden <audio> and the
// hidden YouTube iframe, both with a real clock on this side of the wire. Spotify plays on a device somewhere
// else entirely, so its answer is the last `progress_ms` the server read, advanced by the local clock while
// it is playing. A source that cannot answer returns null, and then NO scrubber is drawn at all: a bar pinned
// at zero, or one that cannot be moved, is worse than no bar.
function playback(el, data, ctx){
  const loc = data.local || {};
  if(loc.src && el._hbAudio){
    const a = el._hbAudio;
    const dur = isFinite(a.duration) ? a.duration : 0;
    if(!dur) return null;                       // metadata not in yet: ask again on the next tick
    return {pos: a.currentTime || 0, dur, playing: !a.paused,
            seek: (s) => { try{ a.currentTime = s; }catch(_){} }};
  }
  const yt = data.yt || {};
  if(yt.videoId && el._hbFrame){
    const p = ytPosition(yt.videoId, !yt.paused);
    if(!p || !p.dur) return null;               // the embed has not sent a clock frame yet
    return {pos: p.pos, dur: p.dur, playing: !yt.paused,
            seek: (s) => { ytPost(el._hbFrame, "seekTo", [s, true]);
                           _ytClock.t = s; _ytClock.at = Date.now(); }};
  }
  const np = data.now_playing;
  if(np && np.duration_ms){
    const dur = Number(np.duration_ms) / 1000;
    const base = Number(np.progress_ms || 0) / 1000;
    const drift = (np.playing && el._hbNpAt) ? (Date.now() - el._hbNpAt) / 1000 : 0;
    // Spotify is the one source whose seek is a ROUND TRIP: the device is not here, so the card asks the
    // server, which asks Spotify. The bar still follows the finger locally; the truth lands on the next read.
    return {pos: Math.max(0, Math.min(dur, base + drift)), dur, playing: !!np.playing,
            seek: (s) => { try{ ctx.action("seek", {to: Math.round(s)}); }catch(_){} }};
  }
  return null;
}

function fmtTime(sec){
  if(!isFinite(sec) || sec < 0) sec = 0;
  const two = (n) => (n < 10 ? "0" : "") + n;
  const s = Math.floor(sec % 60), m = Math.floor(sec / 60) % 60, hrs = Math.floor(sec / 3600);
  return hrs ? `${hrs}:${two(m)}:${two(s)}` : `${m}:${two(s)}`;
}

// The scrubber he asked for: «una barra de progreso para que yo la pueda mover, a lo mejor si quiero
// escucharla un poco más para adelante». While the finger is down the paint follows it and the PLAYER IS NOT
// TOLD ANYTHING — one seek on release, never sixty on the way there, which is what turns a drag into a
// stuttering restart on the YouTube embed.
function seekRow(pb){
  const row = h("div", "hb-mus2-seek");
  const cur = h("div", "hb-mus2-time", "0:00");
  const rail = h("div", "hb-mus2-rail");
  rail.append(h("div", "hb-mus2-railbg"), h("div", "hb-mus2-fill"), h("div", "hb-mus2-knob"));
  const fill = rail.querySelector(".hb-mus2-fill"), knob = rail.querySelector(".hb-mus2-knob");
  const total = h("div", "hb-mus2-time r", "0:00");
  row.append(cur, rail, total);

  let dragging = false, frac = 0;
  const paint = (f, pos, dur) => {
    const pct = Math.max(0, Math.min(1, f)) * 100;
    fill.style.width = pct + "%"; knob.style.left = pct + "%";
    cur.textContent = fmtTime(pos); total.textContent = fmtTime(dur);
  };
  const fracAt = (ev) => {
    const r = rail.getBoundingClientRect();
    return r.width ? Math.max(0, Math.min(1, (ev.clientX - r.left) / r.width)) : 0;
  };
  const st = () => row._pb || {pos: 0, dur: 0, seek: null};
  rail.addEventListener("pointerdown", (ev) => {
    dragging = true; frac = fracAt(ev); rail.classList.add("hb-mus2-drag");
    try{ rail.setPointerCapture(ev.pointerId); }catch(_){}
    paint(frac, frac * st().dur, st().dur);
    ev.preventDefault();
  });
  rail.addEventListener("pointermove", (ev) => {
    if(!dragging) return;
    frac = fracAt(ev); paint(frac, frac * st().dur, st().dur);
  });
  const release = () => {
    if(!dragging) return;
    dragging = false; rail.classList.remove("hb-mus2-drag");
    const s = st();
    if(s.dur && s.seek) s.seek(frac * s.dur);
  };
  rail.addEventListener("pointerup", release);
  rail.addEventListener("pointercancel", release);
  // The tick calls this four times a second. A drag in progress OWNS the paint — the player's own position is
  // still where the song is, and letting it repaint under the finger is the bar fighting the operator.
  row.update = (next) => { row._pb = next; if(!dragging) paint(next.dur ? next.pos / next.dur : 0, next.pos, next.dur); };
  row.update(pb);
  return row;
}

// ── small shared pieces (V2-795) ─────────────────────────────────────────────────────────────────────────
function fire(ctx, name, payload){
  // Fire-and-forget like every control here; tolerant of a ctx whose action returns nothing thenable.
  try{ const p = ctx.action(name, payload); if(p && typeof p.catch === "function") p.catch(() => {}); return p; }
  catch(_){ return null; }
}

function iconBtn(svg, title, onclick, cls){
  const b = h("button", "hb-mus2-ibtn" + (cls ? " " + cls : ""));
  b.appendChild(svgEl(svg));
  if(title){ b.title = title; b.setAttribute("aria-label", title); }
  if(onclick) b.onclick = (e) => { e.stopPropagation(); onclick(e); };
  b.ondblclick = (e) => e.stopPropagation();
  return b;
}

function trackQuery(t){
  return t.query || [t.title, t.artist].filter(Boolean).join(" ") || t.title || "";
}

// What a play of ONE catalogue/library track asks: its words, plus its uri when it has one (the server keeps the
// uri only if the provider playing now is the one that minted it).
function playOne(t, ctx){
  const p = {query: trackQuery(t)};
  if(t.uri) p.uri = t.uri;
  if(t.provider) p.provider = t.provider;
  fire(ctx, "play", p);
}

// The favourites list is the SERVER's (`data.fav`): its id when it exists, the name the server would create.
function favList(data){
  const f = data.fav || {};
  return (data.playlists || []).find(p => p.id === f.id) || null;
}
function isLiked(t, data){
  const fl = favList(data);
  if(!fl) return false;
  const k = _norm(t.title || t.query) + "|" + _norm(t.artist);
  return (fl.tracks || []).some(x => (_norm(x.title || x.query) + "|" + _norm(x.artist)) === k);
}
function likeBtn(t, data, ctx){
  const liked = isLiked(t, data);
  return iconBtn(liked ? ICON_HEART_FILL : ICON_HEART,
    liked ? tt("unlike", null, "Quitar de Favoritos") : tt("like", null, "Guardar en Favoritos"),
    () => {
      const fl = favList(data);
      if(liked && fl) fire(ctx, "remove_from_playlist", {playlist: fl.id, item: t.title || t.query});
      else fire(ctx, "add_to_playlist", {playlist: fl ? fl.id : ((data.fav || {}).name || "Favoritos"),
                                        title: t.title || t.query, artist: t.artist || "", query: trackQuery(t)});
    }, liked ? "on" : "");
}

// A tiny menu over the card: «add this song to which list». Closed by any click outside it.
function openMenu(anchor, items){
  const root = anchor.closest(".hb-mus2-root");
  if(!root) return;
  root.querySelectorAll(".hb-mus2-menu").forEach(m => m.remove());
  const m = h("div", "hb-mus2-menu");
  items.forEach(it => {
    const b = h("button", null, it.label);
    b.onclick = (e) => { e.stopPropagation(); m.remove(); it.run(); };
    m.appendChild(b);
  });
  const r = anchor.getBoundingClientRect(), rr = root.getBoundingClientRect();
  m.style.top = Math.max(4, Math.min(rr.height - 250, r.bottom - rr.top + 4)) + "px";
  m.style.right = Math.max(4, rr.right - r.right) + "px";
  root.appendChild(m);
  const away = (e) => { if(!m.contains(e.target)){ m.remove(); document.removeEventListener("pointerdown", away, true); } };
  setTimeout(() => document.addEventListener("pointerdown", away, true), 0);
}
function addToListBtn(t, data, ctx){
  return iconBtn(ICON_ADDLIST, tt("add_to_list", null, "Añadir a una lista"), (e) => {
    const items = (data.playlists || []).map(pl => ({label: pl.name, run: () => fire(ctx, "add_to_playlist",
      {playlist: pl.id, title: t.title || t.query, artist: t.artist || "", query: trackQuery(t)})}));
    items.push({label: "＋ " + tt("new_playlist", null, "Nueva lista"), run: () => {
      fire(ctx, "add_to_playlist", {playlist: (t.artist || t.title || tt("new_playlist", null, "Nueva lista")),
                                    title: t.title || t.query, artist: t.artist || "", query: trackQuery(t)});
    }});
    openMenu(e.currentTarget, items);
  });
}

// A shelf: ONE quiet panel with its own head (title, a count, actions on the right).
function panel(title, count, actions){
  const sec = h("div", "hb-mus2-sec");
  const head = h("div", "hb-mus2-sechead");
  head.appendChild(h("div", "hb-mus2-sech", title));
  if(count != null && count !== "") head.appendChild(h("div", "hb-mus2-secn", String(count)));
  const right = h("div", "hb-mus2-secact");
  (actions || []).forEach(a => a && right.appendChild(a));
  head.appendChild(right);
  sec.appendChild(head);
  sec.head = head; sec.right = right;
  return sec;
}

function pill(svg, label, onclick, cls){
  const b = h("button", "hb-mus2-pill" + (cls ? " " + cls : ""));
  if(svg) b.appendChild(svgEl(svg));
  b.appendChild(h("span", null, label));
  b.onclick = (e) => { e.stopPropagation(); onclick(e); };
  return b;
}

// A list's cover: its own art; else a MOSAIC of the first four different covers it holds; else one cover; else
// the gradient with the note (a heart for the favourites list).
function coverOf(pl, isFav){
  if(pl.art) return artNode(pl.art, ICON_NOTE);
  const arts = [];
  (pl.tracks || []).forEach(t => { if(t.art && arts.indexOf(t.art) < 0) arts.push(t.art); });
  if(arts.length >= 4){
    const a = h("div", "hb-mus2-art hb-mus2-mosaic");
    arts.slice(0, 4).forEach(u => { const img = document.createElement("img"); img.src = u; img.alt = "";
                                    img.onerror = () => { img.style.visibility = "hidden"; }; a.appendChild(img); });
    return a;
  }
  if(arts.length) return artNode(arts[0], ICON_NOTE);
  const a = artNode(null, isFav ? ICON_HEART_FILL : ICON_NOTE);
  if(isFav) a.classList.add("fav");
  return a;
}

// ── TRACK ROWS ───────────────────────────────────────────────────────────────────────────────────────────
// Click SELECTS (visual, nothing sent); double-click — or the play button over the cover — PLAYS; the row's own
// buttons (heart, queue, add to a list, remove) are quiet until the row is under the pointer.
function trackRow(t, ctx, opts){
  opts = opts || {};
  maybeEnrich(t, ctx);
  // `current` = the song the player holds; `playing` = it is SOUNDING now. Only the second animates.
  const current = !!(opts.current || opts.playing);
  const row = h("div", "hb-mus2-tr" + (current ? " current" : "") + (opts.playing ? " playing" : ""));
  if(opts.drag){
    const grip = h("div", "hb-mus2-grip"); grip.appendChild(svgEl(ICON_GRIP)); grip.title = tt("drag", null, "Arrastra para mover");
    row.appendChild(grip);
  }
  if(opts.index != null || current){
    const cell = h("div", "hb-mus2-trn");
    if(opts.playing) cell.appendChild(eqIcon());
    else if(current) cell.appendChild(svgEl(ICON_NOTE));        // paused: a still marker, never a meter
    else cell.textContent = opts.index;
    row.appendChild(cell);
  }
  const art = artNode(t.art, ICON_NOTE);
  const play = opts.play || (() => playOne(t, ctx));
  const pb = h("button", "hb-mus2-trplay"); pb.appendChild(svgEl(ICON_PLAY));
  pb.title = tt("play", null, "Reproducir");
  pb.onclick = (e) => { e.stopPropagation(); play(); };
  pb.ondblclick = (e) => e.stopPropagation();
  art.appendChild(pb);
  row.appendChild(art);
  const meta = h("div", "hb-mus2-trmeta");
  meta.appendChild(h("div", "hb-mus2-trt", opts.title || t.title || t.query || "—"));
  const times = t.count ? tt("times", {n: t.count}, "{n} veces") : "";
  const sub = opts.hideArtist ? times : [t.artist, times].filter(Boolean).join(" · ");
  if(sub) meta.appendChild(h("div", "hb-mus2-tra", sub));
  row.appendChild(meta);
  const x = h("div", "hb-mus2-trx");
  if(opts.data){
    x.appendChild(likeBtn(t, opts.data, ctx));
    if(opts.queue !== false) x.appendChild(iconBtn(ICON_QUEUE, tt("add_queue", null, "Añadir a la cola"),
                                                   () => fire(ctx, "queue", {query: trackQuery(t)})));
    if(opts.addToList) x.appendChild(addToListBtn(t, opts.data, ctx));
  }
  row.appendChild(x);
  row.onclick = () => {
    const list = row.parentElement;
    if(list) list.querySelectorAll(".hb-mus2-tr.selected").forEach(r => r.classList.remove("selected"));
    row.classList.add("selected");
  };
  row.ondblclick = () => play();
  if(opts.remove){
    const rm = h("button", "hb-mus2-x"); rm.appendChild(svgEl(ICON_CLOSE));
    rm.title = opts.removeTitle || tt("remove_track", null, "Quitar de la lista");
    rm.onclick = (e) => { e.stopPropagation(); opts.remove(); };
    rm.ondblclick = (e) => e.stopPropagation();
    row.appendChild(rm);
  }
  if(opts.drag) makeReorderable(row, opts.dragIndex, opts.drag);
  return row;
}

// One state model for every row: CURRENT when it is the song the player holds, PLAYING only while that song is
// actually sounding (`np.playing`, the player's own report) — never inferred from «is the current track».
function rowState(t, np){
  const current = nowPlayingMatches(t, np);
  return {current, playing: current && !!(np && np.playing)};
}

// Reorder by dragging a row onto another (HTML5 drag and drop): ONE call on drop, never one per hover.
function makeReorderable(row, index, onMove){
  row.draggable = true;
  row.dataset.idx = String(index);
  row.addEventListener("dragstart", (e) => { try{ e.dataTransfer.setData("text/plain", String(index));
                                                   e.dataTransfer.effectAllowed = "move"; }catch(_){} });
  row.addEventListener("dragover", (e) => { e.preventDefault(); row.classList.add("dragover"); });
  row.addEventListener("dragleave", () => row.classList.remove("dragover"));
  row.addEventListener("drop", (e) => {
    e.preventDefault(); row.classList.remove("dragover");
    let from = NaN;
    try{ from = parseInt(e.dataTransfer.getData("text/plain"), 10); }catch(_){}
    if(isFinite(from) && from !== index) onMove(from, index);
  });
}

// A song the card SEES playing is reported once per page life (internal `played`): a song started by voice never
// crossed the card's own play path, so Recent and Most played would never hear of it otherwise.
const _reported = new Set();
function reportPlayed(np, ctx){
  if(!np || !np.title) return;
  const key = _norm(np.title) + "|" + _norm(np.artist);
  if(_reported.has(key)) return;
  _reported.add(key);
  fire(ctx, "played", {title: np.title, artist: np.artist || "", art: np.art || ""});
}

// ── THE TRANSPORT ────────────────────────────────────────────────────────────────────────────────────────
function playbackBar(el, data, ctx){
  const np = nowPlaying(data);
  const bar = h("div", "hb-mus2-bar" + (np ? "" : " empty"));
  const playing = !!(np && np.playing);
  if(np){ maybeEnrich(np, ctx); reportPlayed(np, ctx); }
  const tap = soundRow(el, data);                    // V2-812: the browser keeps it silent → the tap that fixes it
  if(tap) bar.appendChild(tap);
  const row = h("div", "hb-mus2-barrow");
  bar.appendChild(row);
  const artWrap = h("div", "hb-mus2-barartwrap");
  artWrap.appendChild(artNode(np && np.art, ICON_NOTE));
  if(playing){ const badge = h("div", "hb-mus2-areq"); badge.appendChild(eqIcon()); artWrap.appendChild(badge); }
  row.appendChild(artWrap);
  const meta = h("div", "hb-mus2-barmeta");
  // Two REAL states, never one row wearing a fake song title (V2-667): idle is a plain hint, no title/artist.
  if(np){
    meta.appendChild(h("div", "hb-mus2-bart", np.title || tt("music_fb", null, "Música")));
    meta.appendChild(h("div", "hb-mus2-bara", np.artist || (np.device ? np.device : "")));
  } else {
    meta.appendChild(h("div", "hb-mus2-baridle", tt("ask_what", null, "Dime qué quieres escuchar")));
  }
  row.appendChild(meta);
  const ctrls = h("div", "hb-mus2-barc");
  const mk = (svg, action, cls, payload, title) => {          // control = fire-and-forget; SSE re-renders
    const b = h("button", "hb-mus2-cbtn" + (cls ? " " + cls : ""));
    b.appendChild(svgEl(svg));
    if(title){ b.title = title; b.setAttribute("aria-label", title); }
    if(!np) b.disabled = true;
    b.onclick = () => fire(ctx, action, payload);
    return b;
  };
  const md = data.modes || {};
  const modesOk = !!md.supported;
  const shuf = mk(ICON_SHUFFLE, "shuffle", "mode" + (md.shuffle ? " on" : ""), {on: !md.shuffle},
                  tt("shuffle", null, "Aleatorio"));
  if(!modesOk) shuf.disabled = true;
  const rep = md.repeat || "off";
  const nextRep = rep === "off" ? "all" : (rep === "all" ? "one" : "off");
  const repB = mk(rep === "one" ? ICON_REPEAT_ONE : ICON_REPEAT, "repeat", "mode" + (rep !== "off" ? " on" : ""),
                  {mode: nextRep}, tt("repeat_" + rep, null, rep === "one" ? "Repetir la canción"
                                                           : (rep === "all" ? "Repetir la cola" : "Repetir: no")));
  if(!modesOk) repB.disabled = true;
  ctrls.appendChild(shuf);
  ctrls.appendChild(mk(ICON_PREV, "previous"));
  ctrls.appendChild(mk(playing ? ICON_PAUSE : ICON_PLAY, playing ? "pause" : "resume", "main"));
  ctrls.appendChild(mk(ICON_NEXT, "next"));
  ctrls.appendChild(repB);
  row.appendChild(ctrls);
  if(np){
    const side = h("div", "hb-mus2-barside");
    // The heart is a STATE indicator (V2-629): filled when the song is already saved.
    const fav = !!data.fav_current;
    const heart = mk(fav ? ICON_HEART_FILL : ICON_HEART, "favorite_current", fav ? "fav" : "", undefined,
                     fav ? tt("already_fav", null, "Ya está en Favoritos") : tt("save_fav", null, "Guardar en Favoritos"));
    side.appendChild(heart);
    row.appendChild(side);
    bar.appendChild(progressRow(el, data, ctx, mk));
  }
  return bar;
}

// THE PROGRESS ROW (V2-795): elapsed · a rail you click or drag · total, then the volume as a bar you can see.
// Same rules as the big scrubber: the rail and the times appear only once the player says where the song is,
// the shared tick paints them, a drag owns the paint and asks for ONE seek on release — so a voice `seek`, which
// moves the player, shows up here on the next tick. The volume slider is the provider's own level (`data.volume`,
// the same number voice volume_up/down/set_volume move), so a re-render after any of them puts it where it is.
function progressRow(el, data, ctx, mk){
  const row = h("div", "hb-mus2-barprog");
  const cur = h("div", "hb-mus2-bartime", ""), tot = h("div", "hb-mus2-bartime r", "");
  const rail = h("div", "hb-mus2-barrail");
  const fill = h("b"), knob = h("u");
  rail.append(h("i"), fill, knob);
  row.append(cur, rail, tot);
  let dragging = false, frac = 0, pb = null;
  const paint = (f) => { const pct = Math.max(0, Math.min(1, f)) * 100;
                         fill.style.width = pct + "%"; knob.style.left = pct + "%"; };
  const fracAt = (ev) => { const r = rail.getBoundingClientRect();
                           return r.width ? Math.max(0, Math.min(1, (ev.clientX - r.left) / r.width)) : 0; };
  rail.addEventListener("pointerdown", (ev) => { if(!pb) return; dragging = true; frac = fracAt(ev);
    rail.classList.add("hb-mus2-drag"); try{ rail.setPointerCapture(ev.pointerId); }catch(_){}
    paint(frac); cur.textContent = fmtTime(frac * pb.dur); ev.preventDefault(); });
  rail.addEventListener("pointermove", (ev) => { if(!dragging) return; frac = fracAt(ev); paint(frac);
                                                cur.textContent = fmtTime(frac * pb.dur); });
  const release = () => { if(!dragging) return; dragging = false; rail.classList.remove("hb-mus2-drag");
                          if(pb && pb.dur && pb.seek) pb.seek(frac * pb.dur); };
  rail.addEventListener("pointerup", release);
  rail.addEventListener("pointercancel", release);
  const show = (on) => { [cur, rail, tot].forEach(x => { x.style.visibility = on ? "" : "hidden"; }); };
  show(false);
  el._hbTickers.push(() => {
    pb = playback(el, data, ctx);
    if(!pb || !pb.dur){ show(false); return; }
    show(true);
    if(dragging) return;
    paint(pb.pos / pb.dur);
    cur.textContent = fmtTime(pb.pos); tot.textContent = fmtTime(pb.dur);
  });

  const vol = data.volume || {};
  const muted = !!vol.muted;
  row.appendChild(mk(muted ? ICON_VOL_OFF : ICON_VOL_UP, "set_volume", "", {mute: !muted},
                     muted ? tt("unmute", null, "Quitar silencio") : tt("mute", null, "Silenciar")));
  const localLevel = el._hbAudio ? Math.round((el._hbAudio.volume || 0) * 100) : null;
  const level = vol.level != null ? vol.level : localLevel;
  const sl = h("input", "hb-mus2-vol"); sl.type = "range"; sl.min = "0"; sl.max = "100";
  sl.value = String(muted ? 0 : (level != null ? level : 70));
  sl.title = tt("volume", null, "Volumen") + " · " + sl.value + "%";
  sl.setAttribute("aria-label", tt("volume", null, "Volumen"));
  sl.oninput = () => { sl.title = tt("volume", null, "Volumen") + " · " + sl.value + "%"; };
  sl.onchange = () => {
    fire(ctx, "set_volume", {level: Number(sl.value)});
    if(el._hbAudio){ try{ el._hbAudio.volume = Number(sl.value) / 100; }catch(_){} }
  };
  row.appendChild(sl);
  return row;
}

// The name of what is making sound — the same word the bar's chip shows, so the two never disagree.
function sourceLabel(data){
  if((data.local || {}).src) return tt("local_src", null, "Tu biblioteca");
  if(data.mode === "spotify") return "Spotify";      // V2-812: the player making the sound, not the account held
  if((data.yt || {}).videoId) return "YouTube";
  return tt("no_source", null, "Sin fuente");
}

// ── THE ONE BAR ──────────────────────────────────────────────────────────────────────────────────────────
// The window chrome above already carries the mark, the name and the system buttons. This bar holds what could
// not live anywhere else: where you are (a back crumb, or the derived switch), and ONE right cluster — the
// search and the source chip.
function provChip(data, ctx){
  const b = h("button", "hb-mus2-prov");
  const live = !!(data.mode === "spotify" || (data.yt || {}).videoId || (data.local || {}).src);
  b.appendChild(h("span", "hb-mus2-dot" + (live ? " on" : "")));
  b.appendChild(h("span", null, sourceLabel(data)));
  b.title = tt("sources", null, "Fuentes de música");
  b.onclick = () => fire(ctx, "open_view", {kind: "connect"});
  return b;
}

function headerBar(el, data, ctx, kind, opts){
  opts = opts || {};
  const bar = h("div", "hb-mus2-headfix");
  if(opts.back){
    const back = h("button", "hb-mus2-back");
    back.appendChild(svgEl(ICON_BACK)); back.appendChild(h("span", null, tt("back", null, "Volver")));
    back.onclick = () => fire(ctx, "open_view", {kind: opts.back});
    bar.appendChild(back);
  } else if(nowPlaying(data)){
    // DERIVED: a switch with one side is a label, so with nothing sounding there is no switch at all.
    const seg = h("div", "hb-mus2-seg");
    const tab = (id, icon, label) => {
      const b = h("button", "hb-mus2-segb" + (kind === id ? " on" : ""));
      b.appendChild(svgEl(icon)); b.appendChild(h("span", null, label));
      b.onclick = () => fire(ctx, "open_view", {kind: id});
      return b;
    };
    seg.appendChild(tab("now", ICON_NOTE, tt("tab_now", null, "Sonando")));
    seg.appendChild(tab("library", ICON_LIST, tt("tab_library", null, "Tu música")));
    if(((data.queue || {}).items || []).length || kind === "queue")
      seg.appendChild(tab("queue", ICON_QUEUE, tt("tab_queue", null, "Cola")));
    bar.appendChild(seg);
  }
  if(opts.search){
    bar.appendChild(searchBox(el, data, ctx));
  }
  const right = h("div", "hb-mus2-right");
  if(!opts.search) right.appendChild(iconBtn(ICON_SEARCH, tt("search", null, "Buscar"),
                                             () => fire(ctx, "open_view", {kind: "search"})));
  right.appendChild(provChip(data, ctx));
  bar.appendChild(right);
  return bar;
}

// The search box keeps what is being typed across a re-render (an SSE update rebuilds the view under the finger).
function searchBox(el, data, ctx){
  const box = h("div", "hb-mus2-sbox");
  box.appendChild(svgEl(ICON_SEARCH));
  const inp = h("input", "hb-mus2-sinp");
  inp.type = "search";
  inp.placeholder = tt("search_ph", null, "Canciones, artistas o álbumes");
  const last = ((data.browse || {}).search || {}).query || "";
  inp.value = el._hbDraft != null ? el._hbDraft : last;
  inp.addEventListener("input", () => { el._hbDraft = inp.value; });
  inp.addEventListener("keydown", (e) => {
    if(e.key === "Enter"){ const q = inp.value.trim(); if(q){ el._hbDraft = q; fire(ctx, "search", {query: q}); } }
  });
  box.appendChild(inp);
  // Focus only when the face was just opened or the box already had it: an SSE repaint must never pull the
  // keyboard away from whatever else he is typing in.
  if(el._hbFocusSearch) setTimeout(() => { try{ inp.focus(); }catch(_){} }, 0);
  return box;
}

function shell(el, data, ctx, kind, opts){
  const wrap = h("div", "hb-mus2");
  wrap.appendChild(headerBar(el, data, ctx, kind, opts));
  const scroll = h("div", "hb-mus2-scroll");
  wrap.appendChild(scroll);
  return {wrap, scroll, done: () => { wrap.appendChild(playbackBar(el, data, ctx)); el._viewHost.appendChild(wrap); }};
}

// ── AHORA SUENA: the song IS the screen (V2-717) ─────────────────────────────────────────────────────────
function nowView(el, data, ctx){
  const np = nowPlaying(data);
  const s = shell(el, data, ctx, "now");
  s.scroll.classList.add("mid");
  maybeEnrich(np, ctx);
  const box = h("div", "hb-mus2-now");
  const art = h("div", "hb-mus2-nowart");
  const fallback = () => { art.textContent = ""; art.appendChild(svgEl(ICON_NOTE)); };
  if(np.art){ const img = document.createElement("img"); img.src = np.art; img.alt = ""; img.onerror = fallback; art.appendChild(img); }
  else fallback();
  box.appendChild(art);
  box.appendChild(h("div", "hb-mus2-nowt", np.title || tt("music_fb", null, "Música")));
  const who = h("div", "hb-mus2-nowa" + (np.artist ? " link" : ""), np.artist || tt("unknown_artist", null, "Artista desconocido"));
  if(np.artist) who.onclick = () => fire(ctx, "open_view", {kind: "artist", name: np.artist});
  box.appendChild(who);
  const meta = h("div", "hb-mus2-nowm");
  if(np.playing) meta.appendChild(eqIcon());
  const facts = [];
  if(np.album) facts.push(np.album);
  facts.push(sourceLabel(data));
  if(np.device) facts.push(np.device);
  facts.forEach((f, i) => { if(i) meta.appendChild(h("i", null, "·")); meta.appendChild(h("span", null, f)); });
  box.appendChild(meta);
  // The scrubber has a SLOT of its own, usually empty until the player sends its first clock frame.
  const slot = h("div", "hb-mus2-seekslot");
  box.appendChild(slot);
  s.scroll.appendChild(box);
  s.done();
  el._hbTickers.push(() => {
    const pb = playback(el, data, ctx);
    if(!pb || !pb.dur){ if(slot.firstChild) slot.textContent = ""; return; }
    if(!slot.firstChild) slot.appendChild(seekRow(pb));
    else slot.firstChild.update(pb);
  });
}

// ── TU MÚSICA: lists + most played + recent, each a panel ────────────────────────────────────────────────
function libraryView(el, data, ctx){
  const s = shell(el, data, ctx, "library");
  const np = nowPlaying(data);
  const bare = !(data.playlists || []).length && !(data.top || []).length && !(data.recent || []).length;
  if(bare){
    s.scroll.classList.add("mid");
    s.scroll.appendChild(emptyHero(data, ctx));
    s.done();
    return;
  }
  const fav = favList(data);
  const pls = (data.playlists || []).slice().sort((a, b) => (b === fav) - (a === fav));   // favourites first
  const secL = panel(tt("your_playlists", null, "Tus listas"), pls.length || "", []);
  const lists = h("div", "hb-mus2-lists");
  pls.forEach(pl => {
    const c = h("div", "hb-mus2-pl");
    c.appendChild(coverOf(pl, pl === fav));
    c.appendChild(h("div", "hb-mus2-plname", pl.name || tt("playlist", null, "Lista")));
    const n = (pl.tracks || []).length;
    c.appendChild(h("div", "hb-mus2-plsub", `${n} ${n === 1 ? tt("song_one", null, "canción") : tt("song_many", null, "canciones")}`));
    if(n){
      const pp = h("button", "hb-mus2-plplay"); pp.appendChild(svgEl(ICON_PLAY));
      pp.title = tt("play_playlist", null, "Reproducir esta lista");
      pp.onclick = (e) => { e.stopPropagation(); fire(ctx, "play_playlist", {playlist: pl.id}); };
      c.appendChild(pp);
    }
    c.onclick = () => fire(ctx, "open_view", {kind: "playlist", id: pl.id});
    lists.appendChild(c);
  });
  secL.right.appendChild(newListPill(secL, ctx));
  if(pls.length) secL.appendChild(lists);
  else secL.appendChild(h("div", "hb-mus2-note", tt("no_lists", null, "Aún no tienes listas. Crea una o dime «guárdame esta en una lista».")));
  s.scroll.appendChild(secL);
  const rows = (title, list, numbered) => {
    if(!list.length) return;
    const sec = panel(title, null, []);
    const g = h("div", "hb-mus2-grid");
    list.forEach((t, i) => g.appendChild(trackRow(t, ctx, {index: numbered ? String(i + 1) : null,
      ...rowState(t, np), data, addToList: true})));
    sec.appendChild(g); s.scroll.appendChild(sec);
  };
  rows(tt("most_played", null, "Más escuchadas"), (data.top || []).slice(0, 5), true);
  rows(tt("recent", null, "Recientes"), (data.recent || []).slice(0, 8), false);
  s.done();
}

// An empty library is the FIRST thing a new operator sees (V2-717): something to say and something real to press.
function emptyHero(data, ctx){
  const hero = h("div", "hb-mus2-hero");
  const disc = h("div", "hb-mus2-herod");
  disc.appendChild(svgEl(ICON_NOTE));
  hero.appendChild(disc);
  hero.appendChild(h("div", "hb-mus2-herot", tt("empty_title", null, "Aquí vivirá tu música")));
  hero.appendChild(h("div", "hb-mus2-heros",
    tt("empty_sub", null, "Pídeme una canción y suena al momento. Lo que escuches irá apareciendo aquí, en Recientes y en Más escuchadas.")));
  const chips = h("div", "hb-mus2-chips");
  [tt("ex_1", null, "Pon música"), tt("ex_2", null, "Ponme a Frank Sinatra"), tt("ex_3", null, "Pon jazz tranquilo")]
    .forEach(q => {
      const c = h("button", "hb-mus2-chip", q);
      c.onclick = () => fire(ctx, "play", {query: q});
      chips.appendChild(c);
    });
  hero.appendChild(chips);
  const lists = h("div", "hb-mus2-lists");
  const card = h("div", "hb-mus2-pl hb-mus2-new");
  card.appendChild(artNode(null, ICON_PLUS));
  card.appendChild(h("div", "hb-mus2-plname", tt("new_playlist", null, "Nueva lista")));
  card.onclick = () => askName(card, (v) => fire(ctx, "create_playlist", {name: v}));
  lists.appendChild(card);
  hero.appendChild(lists);
  return hero;
}

// Inline: an input takes the place of the gesture; Enter or leaving it creates, Escape gives up.
function askName(anchor, done, initial){
  const inp = h("input", "hb-mus2-inp hb-mus2-newinp");
  inp.placeholder = tt("name_ph", null, "Nombre");
  if(initial) inp.value = initial;
  anchor.replaceWith(inp);
  inp.focus(); if(initial) inp.select();
  let over = false;
  const submit = () => { if(over) return; over = true; const v = (inp.value || "").trim();
                         if(v && v !== initial) done(v); else inp.replaceWith(anchor); };
  inp.addEventListener("keydown", e => { if(e.key === "Enter") submit();
                                         if(e.key === "Escape"){ over = true; inp.replaceWith(anchor); } });
  inp.addEventListener("blur", submit);
  return inp;
}

function newListPill(sec, ctx){
  const b = pill(ICON_PLUS, tt("new_short", null, "Nueva"), () => askName(b, (v) => fire(ctx, "create_playlist", {name: v})));
  b.classList.add("hb-mus2-new");
  return b;
}

// ── FUENTES: where the music comes from (V2-717) ─────────────────────────────────────────────────────────
function connectView(el, data, ctx){
  const s = shell(el, data, ctx, "connect", {back: "library"});
  const sec = panel(tt("sources", null, "Fuentes de música"), null, []);
  sec.appendChild(h("div", "hb-mus2-sub", tt("free_source", null,
    "YouTube suena gratis y sin cuenta: ya está listo, no hay nada que conectar.")));
  if(data.connected){
    sec.appendChild(h("div", "hb-mus2-sub", tt("spotify_on", null,
      "Spotify está conectado: tu biblioteca y tus dispositivos ya están disponibles.")));
    const d = h("button", "hb-mus2-btn ghost", tt("manage_spotify", null, "Gestionar Spotify"));
    d.onclick = () => ctx.openConnector("spotify");
    sec.appendChild(d);
  } else {
    sec.appendChild(h("div", "hb-mus2-sub", tt("connect_hint", null,
      "Dime «pon música» o «ponme a Frank Sinatra» y suena gratis. Conecta tu Spotify (Premium) para tu biblioteca.")));
    // The connection itself lives in ⚙ Conectores (2026-10-04) — the one door the voice also opens.
    const b = h("button", "hb-mus2-btn", tt("connect_spotify", null, "Conectar Spotify"));
    b.onclick = () => ctx.openConnector("spotify");
    sec.appendChild(b);
  }
  s.scroll.appendChild(sec);
  s.done();
}

// ── A LIST: cover (play button INSIDE it), name you can rename, actions, the tracklist you can reorder ──
function playlistView(el, data, ctx, pl){
  const s = shell(el, data, ctx, "playlist", {back: "library"});
  const tracks = pl.tracks || [];
  const n = tracks.length;
  const derived = deriveArtistInfo(tracks);
  const head = h("div", "hb-mus2-head");
  const artwrap = h("div", "hb-mus2-artwrap");
  artwrap.appendChild(coverOf(pl, favList(data) === pl));
  const play = h("button", "hb-mus2-playfab"); play.appendChild(svgEl(ICON_PLAY));
  play.title = tt("play_playlist", null, "Reproducir esta lista");
  if(!n) play.disabled = true;
  play.onclick = () => fire(ctx, "play_playlist", {playlist: pl.id});
  artwrap.appendChild(play);
  head.appendChild(artwrap);
  const hm = h("div", "hb-mus2-headmeta");
  hm.appendChild(h("div", "hb-mus2-headk", tt("playlist", null, "Lista")));
  const name = h("div", "hb-mus2-headn", pl.name || tt("playlist", null, "Lista"));
  hm.appendChild(name);
  const subParts = [];
  if(derived.commonArtist) subParts.push(derived.commonArtist);
  subParts.push(`${n} ${n === 1 ? tt("song_one", null, "canción") : tt("song_many", null, "canciones")}`);
  hm.appendChild(h("div", "hb-mus2-plsub", subParts.join(" · ")));
  const acts = h("div", "hb-mus2-acts");
  if(n) acts.appendChild(pill(ICON_SHUFFLE, tt("shuffle", null, "Aleatorio"),
                              () => fire(ctx, "play_playlist", {playlist: pl.id, shuffle: true})));
  acts.appendChild(iconBtn(ICON_EDIT, tt("rename", null, "Renombrar"), () => {
    const inp = askName(name, (v) => fire(ctx, "rename_playlist", {playlist: pl.id, name: v}), pl.name);
    inp.className = "hb-mus2-renin";
  }));
  const del = iconBtn(ICON_TRASH, tt("delete", null, "Borrar lista"), () => {
    // A whole list is a sweep: asked here, on the card, before it is gone.
    acts.textContent = "";
    acts.appendChild(h("span", "hb-mus2-plsub", tt("delete_q", {name: pl.name}, "¿Borrar «{name}»?")));
    acts.appendChild(pill(ICON_TRASH, tt("delete_yes", null, "Borrar"), () => fire(ctx, "delete_playlist", {playlist: pl.id}), "risk"));
    acts.appendChild(pill(null, tt("cancel", null, "Cancelar"), () => fire(ctx, "open_view", {kind: "playlist", id: pl.id})));
  }, "risk");
  acts.appendChild(del);
  hm.appendChild(acts);
  head.appendChild(hm);
  s.scroll.appendChild(head);

  const sec = panel(tt("songs", null, "Canciones"), n || "", []);
  const g = h("div", "hb-mus2-grid");
  const np = nowPlaying(data);
  if(n){
    tracks.forEach((t, i) => g.appendChild(trackRow(t, ctx, {
      index: String(i + 1),
      remove: () => fire(ctx, "remove_from_playlist", {playlist: pl.id, item: String(i + 1)}),
      title: derived.commonArtist ? derived.strip(t.title) : null,
      hideArtist: !!derived.commonArtist,
      ...rowState(t, np),
      // a song in a list plays IN the list: from this one on, the rest queued behind it
      play: () => fire(ctx, "play_playlist", {playlist: pl.id, from: String(i + 1)}),
      data, queue: true,
      drag: (from, to) => fire(ctx, "move_track", {playlist: pl.id, item: String(from + 1), to: String(to + 1)}),
      dragIndex: i,
    })));
  } else {
    g.appendChild(h("div", "hb-mus2-empty", tt("playlist_empty", null, "Lista vacía. Dime «añade una canción a esta lista».")));
  }
  sec.appendChild(g);
  s.scroll.appendChild(sec);
  s.done();
}

// ── THE QUEUE: what sounds now, and what comes next (editable where the player allows it) ───────────────
function queueView(el, data, ctx){
  const s = shell(el, data, ctx, "queue");
  const np = nowPlaying(data);
  const q = data.queue || {};
  const items = q.items || [];
  if(np){
    const cur = panel(tt("now_title", null, "Sonando ahora"), null, []);
    const g = h("div", "hb-mus2-grid");
    g.appendChild(trackRow(np, ctx, {current: true, playing: !!np.playing, data, queue: false, play: () => fire(ctx, np.playing ? "pause" : "resume")}));
    cur.appendChild(g); s.scroll.appendChild(cur);
  }
  const acts = [];
  if(q.editable && items.length) acts.push(pill(ICON_TRASH, tt("queue_clear", null, "Vaciar"), () => fire(ctx, "queue_clear", {})));
  const sec = panel(tt("queue_title", null, "A continuación"), items.length || "", acts);
  if(!q.editable && items.length) sec.appendChild(h("div", "hb-mus2-note",
    tt("queue_readonly", null, "Esta cola se ve aquí; para cambiarla, usa la app de Spotify.")));
  const g = h("div", "hb-mus2-grid");
  items.forEach((t, i) => g.appendChild(trackRow(t, ctx, {
    index: String(i + 1), data, queue: false,
    remove: q.editable ? () => fire(ctx, "queue_remove", {item: String(i + 1)}) : null,
    removeTitle: tt("remove_queue", null, "Quitar de la cola"),
    drag: q.editable ? (from, to) => fire(ctx, "queue_move", {item: String(from + 1), to: String(to + 1)}) : null,
    dragIndex: i,
  })));
  if(!items.length) g.appendChild(h("div", "hb-mus2-empty", tt("queue_empty", null, "No hay nada en cola. Añade canciones con ＋ desde cualquier lista.")));
  sec.appendChild(g);
  s.scroll.appendChild(sec);
  s.done();
}

// ── SEARCH: songs, artists, albums (and lists, where the catalogue has them) ─────────────────────────────
function searchView(el, data, ctx){
  const s = shell(el, data, ctx, "search", {back: "library", search: true});
  const res = (data.browse || {}).search || {};
  const has = k => (res[k] || []).length;
  if(!res.query){
    s.scroll.classList.add("mid");
    s.scroll.appendChild(h("div", "hb-mus2-note", tt("search_hint", null, "Busca una canción, un artista o un álbum.")));
    s.done(); return;
  }
  if(!has("tracks") && !has("artists") && !has("albums") && !has("playlists")){
    s.scroll.appendChild(h("div", "hb-mus2-note", tt("no_results", {q: res.query}, "Nada para «{q}».")));
    s.done(); return;
  }
  if(has("tracks")){
    const sec = panel(tt("songs", null, "Canciones"), null, []);
    const g = h("div", "hb-mus2-grid");
    res.tracks.forEach(t => g.appendChild(trackRow(t, ctx, {data, addToList: true})));
    sec.appendChild(g); s.scroll.appendChild(sec);
  }
  if(has("artists")){
    const sec = panel(tt("artists", null, "Artistas"), null, []);
    const row = h("div", "hb-mus2-faces");
    res.artists.forEach(a => {
      const f = h("div", "hb-mus2-face");
      f.appendChild(artNode(a.art, ICON_NOTE));
      f.appendChild(h("div", "hb-mus2-facen", a.name));
      f.onclick = () => fire(ctx, "open_view", {kind: "artist", id: a.id, source: a.source, name: a.name});
      row.appendChild(f);
    });
    sec.appendChild(row); s.scroll.appendChild(sec);
  }
  if(has("albums")) s.scroll.appendChild(albumShelf(tt("albums", null, "Álbumes"), res.albums, ctx));
  if(has("playlists")){
    const sec = panel(tt("playlists_found", null, "Listas"), null, []);
    const grid = h("div", "hb-mus2-lists");
    res.playlists.forEach(p => {
      const c = h("div", "hb-mus2-pl");
      c.appendChild(artNode(p.art, ICON_LIST));
      c.appendChild(h("div", "hb-mus2-plname", p.name));
      if(p.owner) c.appendChild(h("div", "hb-mus2-plsub", p.owner));
      c.onclick = () => fire(ctx, "play_album", {uri: p.uri, album: p.name});
      grid.appendChild(c);
    });
    sec.appendChild(grid); s.scroll.appendChild(sec);
  }
  s.done();
}

function albumShelf(title, albums, ctx){
  const sec = panel(title, null, []);
  const grid = h("div", "hb-mus2-lists");
  albums.forEach(al => {
    const c = h("div", "hb-mus2-pl");
    c.appendChild(artNode(al.art, ICON_NOTE));
    c.appendChild(h("div", "hb-mus2-plname", al.name));
    c.appendChild(h("div", "hb-mus2-plsub", [al.year, al.artist].filter(Boolean).join(" · ")));
    const pp = h("button", "hb-mus2-plplay"); pp.appendChild(svgEl(ICON_PLAY));
    pp.title = tt("play", null, "Reproducir");
    pp.onclick = (e) => { e.stopPropagation(); fire(ctx, "play_album", {id: al.id, source: al.source, uri: al.uri,
                                                                         album: al.name, artist: al.artist}); };
    c.appendChild(pp);
    c.onclick = () => fire(ctx, "open_view", {kind: "album", id: al.id, source: al.source, name: al.name, artist: al.artist});
    grid.appendChild(c);
  });
  sec.appendChild(grid);
  return sec;
}

// ── AN ARTIST: face, name, the popular songs, the albums ─────────────────────────────────────────────────
function artistView(el, data, ctx){
  const s = shell(el, data, ctx, "artist", {back: "search"});
  const page = (data.browse || {}).artist || {};
  const a = page.artist || {};
  const head = h("div", "hb-mus2-head");
  const wrap = h("div", "hb-mus2-artwrap");
  const face = artNode(a.art, ICON_NOTE); face.classList.add("round");
  wrap.appendChild(face);
  head.appendChild(wrap);
  const hm = h("div", "hb-mus2-headmeta");
  hm.appendChild(h("div", "hb-mus2-headk", tt("artist", null, "Artista")));
  hm.appendChild(h("div", "hb-mus2-headn", a.name || "—"));
  const acts = h("div", "hb-mus2-acts");
  if((page.top || []).length) acts.appendChild(pill(ICON_PLAY, tt("play", null, "Reproducir"),
    () => fire(ctx, "play_album", {kind: "artist", id: a.id, source: a.source, name: a.name})));
  hm.appendChild(acts);
  head.appendChild(hm);
  s.scroll.appendChild(head);
  if((page.top || []).length){
    const sec = panel(tt("popular", null, "Populares"), null, []);
    const g = h("div", "hb-mus2-grid");
    page.top.forEach((t, i) => g.appendChild(trackRow(t, ctx, {index: String(i + 1), data, addToList: true,
                                                                hideArtist: true})));
    sec.appendChild(g); s.scroll.appendChild(sec);
  }
  if((page.albums || []).length) s.scroll.appendChild(albumShelf(tt("albums", null, "Álbumes"), page.albums, ctx));
  s.done();
}

// ── AN ALBUM: cover, name, the artist (a door to the artist), year, its songs; play it, keep it as a list ──
function albumView(el, data, ctx){
  const s = shell(el, data, ctx, "album", {back: "search"});
  const page = (data.browse || {}).album || {};
  const al = page.album || {};
  const tracks = page.tracks || [];
  const head = h("div", "hb-mus2-head");
  const wrap = h("div", "hb-mus2-artwrap");
  wrap.appendChild(artNode(al.art, ICON_NOTE));
  const play = h("button", "hb-mus2-playfab"); play.appendChild(svgEl(ICON_PLAY));
  play.title = tt("play", null, "Reproducir");
  if(!tracks.length) play.disabled = true;
  play.onclick = () => fire(ctx, "play_album", {id: al.id, source: al.source, uri: al.uri, album: al.name, artist: al.artist});
  wrap.appendChild(play);
  head.appendChild(wrap);
  const hm = h("div", "hb-mus2-headmeta");
  hm.appendChild(h("div", "hb-mus2-headk", tt("album", null, "Álbum")));
  hm.appendChild(h("div", "hb-mus2-headn", al.name || "—"));
  const who = h("div", "hb-mus2-plsub" + (al.artist ? " link" : ""),
                [al.artist, al.year, `${tracks.length} ${tracks.length === 1 ? tt("song_one", null, "canción") : tt("song_many", null, "canciones")}`]
                  .filter(Boolean).join(" · "));
  if(al.artist) who.onclick = () => fire(ctx, "open_view", {kind: "artist", name: al.artist});
  hm.appendChild(who);
  const acts = h("div", "hb-mus2-acts");
  if(tracks.length) acts.appendChild(pill(ICON_ADDLIST, tt("save_as_list", null, "Guardar como lista"),
    () => fire(ctx, "add_tracks", {playlist: al.name, tracks: tracks.slice(0, 25).map(t => ({title: t.title, artist: t.artist}))})));
  hm.appendChild(acts);
  head.appendChild(hm);
  s.scroll.appendChild(head);
  const sec = panel(tt("songs", null, "Canciones"), tracks.length || "", []);
  const g = h("div", "hb-mus2-grid");
  tracks.forEach((t, i) => g.appendChild(trackRow(t, ctx, {index: String(i + 1), data, addToList: true, hideArtist: true})));
  sec.appendChild(g); s.scroll.appendChild(sec);
  s.done();
}

// Which face of the card is showing. `home` is ADAPTIVE and the default: the song when something sounds, the
// library when nothing does. The tick that paints the two progress lines is ONE interval for the whole face.
function drawView(el, data, ctx){
  if(el._hbTick){ clearInterval(el._hbTick); el._hbTick = null; }
  const ae = document.activeElement;
  const hadFocus = !!(ae && ae.classList && ae.classList.contains("hb-mus2-sinp") && el.contains(ae));
  el._hbTickers = [];
  el._viewHost.textContent = "";
  el.querySelectorAll(".hb-mus2-menu").forEach(m => m.remove());
  const view = data.view || {kind: "home"};
  let kind = (view.kind || "home").toLowerCase();
  if(kind === "nowplaying") kind = "now";                       // the pre-V2-717 spelling, never implemented
  if(kind !== "search") el._hbDraft = null;
  el._hbFocusSearch = kind === "search" && (hadFocus || el._hbLastKind !== "search");
  el._hbLastKind = kind;
  if(kind === "playlist"){
    const pl = (data.playlists || []).find(p => p.id === view.id);
    if(pl) playlistView(el, data, ctx, pl);
    else libraryView(el, data, ctx);
  }
  else if(kind === "connect") connectView(el, data, ctx);
  else if(kind === "queue") queueView(el, data, ctx);
  else if(kind === "search") searchView(el, data, ctx);
  else if(kind === "artist" && ((data.browse || {}).artist || {}).artist) artistView(el, data, ctx);
  else if(kind === "album" && ((data.browse || {}).album || {}).album) albumView(el, data, ctx);
  // A hero with nothing in it would be the emptiest screen of all: when the song ends while the card sits on
  // «Sonando», it falls back to the library instead of showing a frame around silence.
  else if((kind === "now" || kind === "home") && nowPlaying(data)) nowView(el, data, ctx);
  else libraryView(el, data, ctx);
  const tick = () => el._hbTickers.forEach(f => { try{ f(); }catch(_){} });
  tick();
  if(el._hbTickers.length) el._hbTick = setInterval(tick, 250);   // a local clock, no network
}

// ── i18n seam (V2-613 / V2-694): `ctx.t` for our own chrome, the literal as the FALLBACK ────────────────
// The fallback is, byte for byte, the string that used to be hardcoded here — so a widget rendered outside the
// engine (a render test, a headless DOM stub) shows exactly what it showed before, and only an engine with a
// bundle loaded shows the operator's own language.
let _T = null;
function tt(key, params, fb){
  try{
    if(_T){ const s=_T("widgets.musica."+key, params); if(s && s!=="widgets.musica."+key) return s; }
  }catch(_){}
  let s = fb;
  if(params) for(const k in params) s = s.split("{"+k+"}").join(String(params[k]));
  return s;
}

export function render(el, data, ctx){
  _T = (ctx && typeof ctx.t === "function") ? ctx.t : null;
  injectStyles();
  data = data || {};
  // V2-717 — WHEN this Spotify reading was taken. Spotify plays on a device that is not here, so `progress_ms`
  // is a photograph, not a clock: the scrubber advances it locally from the instant the photograph arrived,
  // and a NEW photograph (a different song, or a position that moved) restarts the count. Without the stamp
  // the bar would either freeze between reads or drift further from the truth the longer the card stayed open.
  const _np = data.now_playing || null;
  const _npKey = _np ? [_np.title, _np.artist, _np.progress_ms, _np.playing].join("|") : "";
  if(el._hbNpKey !== _npKey){ el._hbNpKey = _npKey; el._hbNpAt = Date.now(); }
  if(!el._hbInit){                    // hosts persistentes: la vista se reconstruye, el player oculto NO
    el.textContent = "";
    el.className = "hb-mus2-root";
    el._viewHost = document.createElement("div"); el._viewHost.className = "hb-mus2-viewhost";
    el._ytHost = document.createElement("div"); el._ytHost.className = "hb-mus2-audio";
    el.append(el._viewHost, el._ytHost);
    el._hbInit = true;
  }
  syncYtPlayer(el, data, ctx);
  drawView(el, data, ctx);
}
