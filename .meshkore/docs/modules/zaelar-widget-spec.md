# Widgets — the specification, and how one is created or changed

The one-page map of what a widget IS and where each rule lives. It does not repeat the rules: the long contract is
`widgets/AGENTS.md` (the house style and the hard rules, read by every agent that writes a widget) and the code
agent's own copy is `widgets/generator.py::_CONTRACT`. When a rule changes, those two change together
(`.meshkore/docs/ops/zaelar-widgets-workflow.md` §1), and this page only if a PIECE is added or moved.

## 1. The folder

```
widgets/<id>/                     built-in (in the repo)        widgets/_user/<id>/  his own or a fork (gitignored)
├─ manifest.json   identity · screens · state · actions · voice vocabulary · size · runtime
├─ data.py         view_data(q) (hot path, no network) · apply_action table · ref_index · prompt_digest · facts
├─ actions.py      the handlers, when data.py grows (imported back into data.py's ACTIONS table)
├─ widget.js       render(el, data, ctx) — ES module, no build step, no network from JS
├─ notes.md        the decision log of THIS widget: read before touching it, append after
├─ golden.json     the recorded shape of view_data() (the harness writes it)
└─ __init__.py
```

A folder in `widgets/_user/` SHADOWS the built-in with the same id. Before diagnosing a widget, check which file runs.

## 2. The manifest

| Field | What it decides | Rule lives in |
|---|---|---|
| `id`, `version`, `title`, `name`, `description`, `entry` | identity; `name` is also translated as `widgets.<id>.name` | `widgets/AGENTS.md` §Translation |
| `screens` | `shared` (data, any number of screens) or `single` (takes sound/picture, moves between screens) — REQUIRED | `widgets/screen_policy.py` |
| `state` | what the FACE shows (`order` · `report` · `facts`), or `{"static": why}` — REQUIRED | `widgets/state.py`, `state_decl.py` |
| `actions` | the data API the voice drives: `desc` (≤ 200 chars) + `how` + `payload`, and the flags `ref`, `confirm`, `repeatable`, `view`, `instant`, `internal`, `done_when`, `activation` | `widgets/actions.py`, `widgets/AGENTS.md` |
| `usage`, `whenToUse`, `keywords`, `aliases` | the voice's vocabulary: which card an order goes to | `widgets/brief.py`, `widgets/aliases.py` |
| `fill` | a card only a search fills | `nucleo/acts/fill.py` |
| `runtime` | a widget that PRODUCES (audio/video/recording): `output`, `produce`, `suspend`, `resume`, `active_when` | `widgets/producers.py` |
| `background` | a cycle `tick()` off the hot path | `widgets/AGENTS.md` §Background |
| `size`, `min`, `fullscreen`, `live_title` | the desk card's footprint; `live_title` lets `data.title` become the card header on desk AND phone | `frontend/app/widgets/desktop.js`, `frontend/mobile/app/shell/Deck.js` |
| `collections`, `connector_families`, `security` | rows the brain can address; the connector shelf; the sandbox level | `widgets/AGENTS.md` |

## 3. Voice, storage, language

- **Voice** reaches a widget only through its declared actions; the model never invents ids (`ref_index()`); a screen
  change is ONE transition inside the widget (`selectTab`-style), reached the same way by a click and by a pushed view.
- **Storage** is per widget: `store.load/save("<id>")` → `widgets/_data/<id>/state.json`, versioned with
  `DB_VERSION` + a lazy `_migrate`. Keys may be added; renaming or dropping one needs the migration.
- **Language**: every visible string is `tt(key, params, literal)` with the row in both `i18n/genesis/en/` and `es/`;
  no label table at module level; `ctx.lang` for dates and numbers. The word for these things in any visible text is
  «widget».

## 4. Layout — three sizes, one widget

The same `widget.js` serves the phone (~366px of content, `frontend/mobile/`), the desk card (`size` → `min`) and the
maximized card (~1400px). Laid out by container (`@container`), never by a width measured once. The chrome, padding
and scrolling are the host's; a widget never escapes its card (`position:fixed`, `100vw/vh`, `z-index > 5`).
The phone copies the platform's own app for the genre — chips that scroll sideways (`data-hpan`), one search door,
one-column lists with a ⋮ sheet, a slim now-playing bar, skeletons while loading, the header naming the widget.
Full text: `widgets/AGENTS.md` §Layout and «The phone». Measured by
`tests/browser/e2e/mobile/render_widgets_on_a_phone.py` and
`tests/browser/e2e/widgets/test_widget_roots_fill_a_wide_desktop_card.py`. The worked example is
`widgets/youtube/` (its `notes.md` records why each phone pattern was chosen).

## 5. Creating and changing a widget

| Who | How | What they read |
|---|---|---|
| A developer in this repo | edit the folder; `python -m tests.widget_harness <id>`; the targeted tests | `widgets/AGENTS.md`, `widgets/<id>/notes.md`, `.meshkore/docs/ops/zaelar-new-widget-or-connector-workflow.md` |
| The USER, by voice («hazme un widget de…», «cámbiale…») | the code agent through `widgets/generator.py` (`create` / `modify` / `repair`), writing only into `widgets/_user/<id>/`; a change to a built-in becomes a fork there; `restore_widget` returns to the shipped one | `_CONTRACT` inside `_CREATE_PROMPT` / `_MODIFY_PROMPT`, which points to `widgets/AGENTS.md` |

Either way the validation gate (`widgets/validator.py`, `validator_actions.py`, `validator_js.py`) decides whether it
enters the catalogue. A change to the widget SYSTEM (a new manifest field, the store, the hosts) follows
`.meshkore/docs/ops/zaelar-widgets-workflow.md`.
