---
title: The widget header standard — two bars, and the door to the connectors
category: conventions
updated: 2026-09-29
owner: ricart
status: current
---

# Two bars, and the door to the connectors

**This is a house rule, not a suggestion.** Every widget that has a connector behind it wears the same bars, in
the same order, with the same class shapes and the same behaviour. Zaelar's desktop is an operating system, so
those bars have a standard format, and they lead to the connector system.

A desktop where every window invents its own chrome is a pile of demos. The bars are how the product says
"this is one system", and the plug button is how a user learns, once, where every integration lives.

**Reference implementations:** `widgets/contactos/widget.js` (a card that lists many things),
`widgets/musica/widget.js` (a card whose content can be ONE thing) and `widgets/youtube/widget.js` (the flush
template, §«No inset either»).

---

## The WINDOW is bar one

**Two bars means TWO ON SCREEN, and the canvas already draws one.** `desktop.js` gives every card a header
carrying the widget's mark, its name and its ⚙ — so a brand disc and a content title under it would be the same
sentence said twice. **A widget adds ONE bar of its own.**

What that one bar holds is what could not live anywhere else: the widget's own control (a search box, a date
range), then `margin-left:auto`, then the provider icons, then the plug. Anything that would be a fixed TAB STRIP
moves into the content — for a widget with a rail, into the rail, where it is DERIVED from the data instead of
being a fixed set of words nobody can change (a contact is never a place, so the sections a contacts rail shows
come from what the contacts actually are).

And a count goes WITH its row: «All (2 688)» in the rail, never a sentence in the bar — a number in brackets next
to the label is understood the same way by everyone.

**A widget with no rail** (the agenda, messaging) still needs its view switcher somewhere; for those the view band
(below) is bar two, and no brand disc or repeated title is drawn above it. The invariant: **nothing the window
chrome already says gets said again.**

### The widget's bar

```
[ widget control ……… ]                         [icon][icon][icon]  [⏚]
──────────────────────────────────────────────────────────────────────  ← one hairline
```

| Part | Class | Rule |
|---|---|---|
| Widget control | — | Whatever this widget needs: the agenda's ‹ Today ›, a search box. |
| Content title (if any) | `.<pfx>title` / `.<pfx>range` | **14 px / 600.** It is the CONTENT's title — the date range, the folder — not the window's name. |
| Right cluster | `.<pfx>viewsright` | ONE cluster with `margin-left:auto`. Provider icons first, then the plug. |
| Provider icons | `.<pfx>connicon`, `.on`, `.off`, `.sel` | 28 px targets, a tooltip each, the provider's own brand colour. |
| Plug | `.<pfx>plug` | An ICON, no label; `aria-label` + `title` carry the word. Toggles the connectors screen. |

⚠️ **The content title sits one step UNDER the window title, never over it.** A 15/700 range beside a 14/600
window name inverts the hierarchy it is supposed to express.

⚠️ **Icons and plug share ONE right cluster.** With two `margin-left:auto` siblings they split the free space and
an icon floats mid-bar. The plug is the shared stroke drawing (as in `widgets/contactos/`), not a 🔌 emoji.

The plug carries no word because the source icons beside it already say "sources"; a label would be the third
thing in that row saying the same thing.

### The view band (widgets with no rail)

```
( Tab ) ( Tab ) ( Tab )              [icon][icon][icon]  [⏚]
────────────────────────────────────────────────────────────  ← one hairline
```

| Part | Class | Rule |
|---|---|---|
| The band | `.<pfx>views` | One hairline `border-bottom` in `--hb-line-subtle`. Horizontal scroll, scrollbar hidden. |
| View tabs | `.<pfx>tab`, `.on` | Pill. Selected = accent-tinted chip **with an accent ring** (`color-mix` 18 % + inset ring 55 %). Never a filled near-white pill — that is a second filled language on the screen. |
| Right cluster | `.<pfx>viewsright` | As above. |

**Disabled tabs stay at `opacity:.75`, not `.6`.** At .6 the effective ink contrast drops under the 4.5:1 floor;
the tabs are still the map of where you are, so "unavailable" must not read as "absent".

**The tabs go quiet while the connectors screen is open.** No view is the one on screen, so none is lit and none
is clickable (`disabled`). The chosen view survives underneath and comes back when the screen closes.

## The provider icons — three states, and they are different sentences

| State | Looks like | Clicks |
|---|---|---|
| `connected` | full colour, `.on` | **FILTERS** the content to that source; clicking again clears it, and while it is on the icon wears the accent ring (`.sel`) |
| `off` (built, not linked) | brand colour, dimmed | → the connectors screen (there is nothing to filter yet, and "connect it" is the only useful answer) |
| `unavailable` (**no connector exists**) | `.off`, `disabled` | nothing |

Syncing, the connection wizard and everything else that manages a source live behind the plug; the icons are for
choosing what you see.

⚠️ **"You have not linked it" and "this is not available" are different sentences, and showing the first when the
second is true promises something the product cannot do.** A source with no connector is VISIBLE and INERT — no
button, no handler. Showing the full landscape of sources is the point.

⚠️ **The list is a READ of the real inventory, never a hardcoded "off".** Each widget derives it from
`connectors/registry.py::descriptors()` filtered by its family, so the day a second provider is registered it
lights up with nothing else to change. See `widgets/agenda/gcal.py::calendars()` and
`widgets/contactos/gcontacts.py::providers()` — identical functions, deliberately.

**Whatever the icon filters, the VOICE must be able to ask for too** — the filter is a payload key on the
widget's view action (`show_view {source}`), and the pushed view has to APPLY it, or the spoken answer and the
screen show different sets. And the plug itself needs an action (`show_connectors`), because a button with no
name is a button the voice cannot press.

## The widget IS the window — no box of its own

The window is bar one, and the window is also the FRAME. A widget root that draws its own `border` +
`border-radius` + `background` paints a card on top of the card the canvas already drew — two frames, two radii, a
gutter of dead space between them. **A widget adds no box of its own**; the three bands (bar / content / footer)
are separated by TONE and a hairline, never by a frame.

**A card whose content is a single object.** When a music card has a song playing, the song is the content —
cover, title, artist, facts, scrubber, centred and filling the band — and the strip at the foot keeps the
transport. The rule that generalises:

- the DEFAULT face is adaptive (`home` = the object when there is one, the library when there is not), and
  the two explicit faces exist so a click or a sentence can pin either;
- the switch between them is DERIVED — drawn only while there is somewhere to switch to, the same rule the
  contacts rail follows for a section with nothing in it;
- an EMPTY face still says something and offers something real to press — never just a heading and a dashed
  square.

⚠️ **Sizing a hero by WIDTH alone puts a scrollbar on the one screen meant to be calm**, and a flex column
that centres its content does not scroll when it overflows — it CLIPS, at both ends, with `scrollHeight`
none the wiser. Size the object against the height that is actually there and let it shrink; test
CONTAINMENT (is the top of the cover and the bottom of the scrubber inside the band?), never `scrollHeight`.

### No inset either — the FLUSH template

Dropping the widget's own box still leaves the HOST's 16 px inset around it, so the bar would float inside a
gutter under the window header. `widgets/youtube/widget.js` uses the flush template:

- `.hb-scroll:has(> .<root>){overflow:hidden;padding:0}` — the widget takes the host's inset and scroll
  away for its own card only (the same `:has` seam the player tab uses);
- the root is a `height:100%` flex column: the BAR (flush under the window header, one hairline) and ONE
  body region that owns the scroll and carries the gutter, so the bar never scrolls away;
- a media face (the player) goes EDGE TO EDGE inside that body: no inset, no radius; only its title
  line and controls carry padding.

Ratchets: `tests/browser/unit/youtube/test_the_player_dresses_like_the_product.py`.

## The connectors screen

**It replaces the content area. It is never a floating overlay.**

```
Conectores                                              ‹ Contactos
┌────────────────────────────────────────────────────────────────┐
│ [G]  Google Contacts        ● conectado      [ Desconectar ]   │
├────────────────────────────────────────────────────────────────┤
│  ⟳  SINCRONIZACIÓN                                             │
│     [●━]  Mantener sincronizado    comprueba cada minuto       │
│     ⇄  Google y zaelar se mantienen iguales.                   │
│     Sincronizar ahora               Última vez: … · 12 nuevos  │
└────────────────────────────────────────────────────────────────┘
│ []  iCloud (Apple)          ○ aún no disponible                │   ← dimmed, no button
```

- a back crumb that always says where "back" goes — to the widget, never out of it;
- one row per source: mark, label, a status dot, and **at most one button**;
- the connected source's own panel (sync box, default calendar, whatever it owns) **INSIDE that source's
  own card**, as its lower half — one border, one radius, a hairline between the two halves and a softer
  ground under the panel.

⚠️ **The CARD is the source, not the row.** A panel in a box of its own under the account row reads as a
second, unrelated feature, and a connectors screen's one job is to make obvious WHICH account a control acts
on. The shape is `.<pfx>srcbox` (the border) → `.<pfx>src` (the account row) + the panel; the panel carries no
border or radius of its own, and its heading is a small uppercase label, not a second title competing with the
account's name. `test_the_sync_panel_lives_INSIDE_the_account_it_belongs_to` is the ratchet.

⚠️ **Two sentences saying one thing is not emphasis, it is noise.** The direction line already says what the
sync does; a warning beside it carries only what the line cannot — what unblocks it.

### A permanent state wears a SWITCH, not a button

**A button is a one-off by its grammar, whatever its label says.** "Sync contacts" as a primary button teaches
that syncing is an errand you run, when it is a state the connector keeps. The control for anything a connector
keeps doing — syncing, watching, importing on a cycle — is a switch that shows the STATE, and it says how often it
runs beside it (read from the engine, never a number typed into a label).

Doing it by hand stays available as a QUIET secondary (`.<pfx>quiet`), never a primary button beside the
switch. The shape lives in `widgets/contactos/widget.js` (`.ctswrow` / `.ctsw`); the day a second connector
panel needs one it gets promoted to `components.css` under the `hb-` prefix.

⚠️ **Check the class name is not already taken in your own sheet.** If a class already means something else
further down the stylesheet, the second definition loses silently. Two meanings on one surface, and the new one
loses.

## Connecting: `ctx.connect(...)`, never a window of your own

```js
const r = await ctx.connect("connect", {origin: location.origin},
                            {family: "contactos", onDone: () => { busy = false; }});
if (!(r && r.ok)) showError(r && r.error);
```

That is the whole of it. The canvas opens the window **inside the click** (a `window.open()` after an
`await` is outside the user gesture and every mainstream browser blocks it in SILENCE), with a features string
so it is a **popup on the desktop** and a **tab on a narrow screen**, and then it watches for the connection
landing.

⚠️ **Do NOT hand-roll this.** Hand-rolled consent windows drift into different behaviours for one idea — a popup
in one widget, a whole tab in another. `test_no_widget_hand_rolls_its_own_consent_window` is the ratchet: a
`window.open("")` inside a `widget.js` fails the suite.

### How the card NOTICES — three signals, and none of them is believed

When the user comes back from the consent window, the connect option must disappear and the source must show as
connected, in real time — otherwise the user is left wondering and may start the connection again indefinitely.

1. **The callback page posts to its opener** (`connectors/oauth_callback.py`) — instant, and the only one
   that fires while the user is still looking at the window.
2. **The server emits `widget/data`** for the family's widget (`oauth_callback.announce`) — the same path every
   other state change uses. A widget's own store goes through `widgets/store.py::save`, which emits it and makes
   the open card re-fetch itself; that is why the messaging card notices a Telegram QR being scanned **with no
   polling at all**. OAuth tokens live in a `SecureJsonStore`, which emits nothing, hence the explicit announce.
3. **A bounded poll** in `_watchConnect` — covers a window that was never ours to watch (a mobile tab with
   no opener) and a message a reused window ate.

⚠️ **Every one of them ends in `refreshData`, which re-reads state from the ENGINE.** The postMessage is a
HINT to go and look, never the answer — which is what makes it safe to accept it loosely, and why a forged
message buys a refresh and nothing more. A surface that believed the flag would paint "connected" over an
account that is not.

**A new connector gets all of this for free** by returning `oauth_callback.page(..., family=...)` from its
callback route and calling `oauth_callback.announce(family)` on success AND on disconnect — unlinking is a
state change too, and a card that goes on saying "connected" is the same mistake in reverse.

**By voice this cannot be completed**: the consent is a click. The action leaves the card ON the connectors
screen and the manifest tells the model to ask the user to press Connect.

## The checklist for the next widget

1. ONE bar of the widget's own under the window header: its control, then the right cluster. No brand disc, no
   repeated window title; a content title, if any, at 14/600.
2. If the widget has no rail: a `.<pfx>views` band, one hairline, tabs as accent-tinted chips, `disabled` while
   the connectors screen is open. If it has a rail: sections derived from the data, counts on their rows.
3. `.<pfx>viewsright` with the provider icons (connected = filter) and the icon-only plug.
4. A `providers()` reading `registry.descriptors()` by family — never a hardcoded list of states.
5. A connectors SCREEN, not an overlay, with a back crumb, and each source's panel inside its own card.
6. Connect goes through `ctx.connect(...)`, which opens the window synchronously.
7. No box of its own; the flush template when the content should reach the edges.
8. **No second door to the same thing.** An "Import from X" button somewhere else in the widget is a
   second place to keep in sync and a second vocabulary for one idea.
9. Rendered tests for all of it: see
   `tests/browser/unit/contactos/test_a_contact_card_looks_like_a_contact_card.py` (testmap **4.176**).
