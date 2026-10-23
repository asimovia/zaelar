# Configuration area — tabs, the single connector registry, and widget origin

The full-screen Configuration area (⚙, `frontend/app/components/ConfigPanel.js`, a system surface) is organised
in **tabs** (`TABS` in `ConfigPanel.js`):

1. **Settings** — API/model per piece, voice, language, balances: the side menu of sections.
2. **Appearance** — design profiles and custom knobs for the desktop's skin.
3. **Connectors** — EVERY connector in the system, with its connected/authenticated state, and **connect/revoke
   right there** (the same actions are also available from the widgets that own a connector, e.g. messaging).
4. **Widgets** — one alphabetical list with a badge per line: **built-in** (ships with the agent) vs **yours**
   (created by the user). Read-only.

**Hard invariant:** connectors are NATIVE and **all their configuration and credentials are DYNAMIC, visible,
revocable and authenticatable from the frontend — NOTHING in `.env`** (env vars are only a power-user fallback).
Connection code lives in `connectors/<x>/`; the data (cluster tokens, the Architect token, etc.) lives in the
agent's store and is managed from the tab.

## Pieces

### Backend

- **`connectors/registry.py`** — the ONE typed inventory: `descriptors()` returns, per connector,
  `{id, label, family, families, auth (qr|app-password|oauth|token|cluster), connected, status, detail,
  REDACTED config, [clusters]}`. It aggregates every connector family (messaging, music, files, photos, video
  accounts, calendar, contacts, Google, Architect, MeshKore). Read-only; each source is isolated, so a broken
  connector never takes the registry down. `serves(descriptor, family)` is the single reader that decides
  whether a connector belongs to a family, so a widget strip and the settings tab can never disagree.
- **Dynamic infra tokens (not `.env`):** `config/connectors.py::_DEFAULTS` carries `architect: {enabled, token,
  url}` (`token` is a secret → redacted). `connectors/architect/client.py::token()/base_url()` read the store
  FIRST and fall back to `.env` only if it is empty. MeshKore keeps its own dynamic store
  (`store.stage/resolve/save_cluster`).
- **Endpoints** (`server/config_api.py`): `GET /api/connectors` (the registry), `GET /api/connectors/catalog`, and
  `POST /api/connectors/architect/connect|disconnect` (set/revoke the token). Messaging, Spotify and MeshKore
  reuse their own endpoints (`/api/messaging/{p}/connect|disconnect`, `/api/spotify/*`,
  `/api/meshkore/stage|connect|disconnect`).
- **Widget origin:** `widgets/registry.py::origin_of` → `builtin` (the curated `_BUILTINS` set) | `user`. An
  explicit `origin` in the manifest wins; the **generator stamps `origin:"user"`** on everything it creates.
  Propagated to `registry()`/`project_state()` → `GET /widgets/registry` + `state.widget_registry`.

### Frontend

- **`ConfigPanel.js`**: a `.cf-tabs` bar over the `.cf-tabpane`. The Connectors tab paints cards per family with
  the connection boxes (WhatsApp/Telegram QR, email app-password, Spotify OAuth, Architect token, MeshKore
  cluster), calling the REST endpoints directly (with a short poll after connecting to pick up the QR). The
  Widgets tab is the alphabetical list with the built-in/yours badge. `api.js` holds the helpers; `styles.css`
  the styles (`.cf-tabs/.cf-tab/.cf-tabpane/.cf-btn/.cf-fam/.cf-wrow/.cf-wbadge`).

## Built-in vs user widgets

The built-in set is the curated `_BUILTINS` in `widgets/registry.py` (agenda, clock, timer, search, results,
browser, messaging, music, YouTube and the other core widgets). Everything else — anything the generator creates
— is the user's.

## Extension points

- **Connecting by voice** («connect my WhatsApp») fits as a tool that triggers the same connect action; the voice
  carries the intent, and any credential step stays in the UI.
- The WhatsApp/Telegram QR in the tab refreshes with a short poll after connecting; it can subscribe to the
  messaging SSE stream, as the messaging widget does, to update instantly.
