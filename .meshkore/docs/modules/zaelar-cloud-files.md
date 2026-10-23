<!--
Canonical module doc for the cloud-file connectors + the `archivos` explorer.
PUBLIC repo: this describes the MECHANISM only.
-->

# Cloud files — connectors + explorer

Zaelar reaches into the operator's cloud drive (Google Drive, OneDrive) to **read**: browse folders, search by
name or content, and open a file's detail card. It is driven with the mouse and by voice.

## The two pieces and the boundary between them

```
connectors/files/          the outside world              widgets/archivos/        the surface
├─ providers.py   typed registry                         ├─ manifest.json   declared actions
├─ oauth.py       PKCE, one token per provider           ├─ data.py         cache + actions
├─ gdrive.py      Drive v3                               ├─ widget.js       explorer + wizard
├─ onedrive.py    Microsoft Graph                        └─ notes.md
├─ service.py     ◀── THE PROVIDER-AGNOSTIC FACADE ──▶
└─ server_api.py  /api/cloudfiles/*
```

**The widget does not know who it is talking to.** `service.py` returns ONE normalized shape and nothing else:

```
{id, name, kind: "folder"|"file", mime, size|None, modified, web_url, provider}
```

A third provider is a client module and a registry row: **zero lines in the widget**. A test requires both
clients to emit exactly the same keys — without it the facade would be an illusion.

`size` is `None`, not `0`, for anything that has no size (a folder, a native Google document): «0 B» next to a
real document is a claim, and a false one.

## The PERMISSION TIER is the design, not a constant

It is the one thing to understand before touching anything here, and the two providers are not in the same
situation. As MECHANISM — what the API does:

| provider | tier | what it sees | can it browse? |
|---|---|---|---|
| Google Drive | `drive.file` | only what the app created or the user picked by hand | **NO** |
| Google Drive | `drive.readonly` | everything, read-only — a Google **restricted** scope | yes |
| OneDrive | `Files.Read` + `offline_access` | everything, read-only | yes |

Google requires a security assessment (CASA) before a **published** app may request the restricted scope;
someone using **their own OAuth client** with their own account is not publishing anything. That is why the
tier is a **per-install** choice rather than a fixed value, travels attached to the token, and the wizard shows
it **before** consent rather than after the drive looks empty. Microsoft Graph asks for nothing equivalent for
personal OneDrive: a single tier.

### And its consequence, which is the most important decision in the module

A token with the narrow tier **answers 200 with an empty list**, which is indistinguishable from «this folder is
empty». So in that case `service.py` answers `ok: True`, zero entries **and a `reason`**, and the card prints the
reason. Collapsing those two states would tell someone with a full Drive that it is empty, and get a narrow
permission diagnosed as a broken connector.

## The skills — without any new tool

The manifest's **declared actions** ARE the skills; the FlashBrain runs them through the existing generic
`widget_data` tool. A connector catalogue must not make a turn that does not mention it more expensive: an
entry costs one prompt line, not a tool slot.

| action | for |
|---|---|
| `open_folder` · `go_up` · `go_home` | browsing |
| `search_files` | search **and ANSWER** — returns the matches in `result.matches` |
| `open_file` | one file's detail card, with its `web_url` |
| `refresh` · `clear_search` · `set_view` · `set_provider` | view state |
| `open_connectors` · `close_connectors` · `connect_provider` · `disconnect_provider` | the wizard |

Every browsing action carries `"view": true`, which is what makes «ábreme el Drive» LIST the contents instead of
merely raising the card. `disconnect_provider` is the only one with `confirm`.

`ref_index()` gives a different `field` per class — `folderId` for folders, `fileId` for files — otherwise «abre
el presupuesto» would enter the folder named like the file. `prompt_digest()` puts the listing in front of the
brain **while the card is open**, so «what's in here?» is a question about text we already have.

## Where the network happens

In `apply_action` and nowhere else. `view_data` runs on every render **and again on every SSE push**, so a call
there would be an HTTP round trip per repaint: it serves the cache and publishes `needs_refresh`, and the card
asks for a listing ONCE on mount if the cache is stale. **No `tick`**: polling someone's cloud spends quota to
answer a question nobody asked.

`data.py` imports the connector — normally forbidden — because this widget IS a connector and there is no stdlib
equivalent for a token refreshed from the credential store. It is on the curated list
`widgets/validator.py::_STDLIB_EXEMPT`, next to `musica`, and the import is **deferred** so the catalogue does not
pay for `httpx` on every turn.

## Credentials

The operator registers **their own** OAuth application once (Google Cloud / Microsoft Entra) and pastes the
`client_id` into ⚙ → Connectors. It is kept in the credential store; tokens live in
`.meshkore/credentials/files_oauth.json` (chmod 600, gitignored) and **never leave the process**.

**Voice carries intent, never a credential**: no action payload accepts a `client_secret` — a test forbids it,
because voice reaches exactly those payloads. That is why the card's wizard offers *connect* and *disconnect*,
and registering the app lives in settings.

`widget.js` does not touch the network: consent is started by a declared action that returns the URL, and the
card opens the window **synchronously on the click** (filling in its `location` afterwards) or the browser
blocks it.

## Scope

- **Read-only**, on both providers.
- **It does not talk to other widgets.** `open_file` returns metadata and `web_url`; whether that becomes a
  document on the canvas or a page in the browser **is the brain's decision**.
- **iCloud Drive is outside what any third party can reach**: CloudKit only gives access to the app's own
  container, never the user's iCloud Drive, and there is no public third-party API.
- **No download by default.** `service.download()` exists, capped, for when a turn has to hand a file to another
  surface; the explorer does not use it.

## Testing it

```bash
./.venv/bin/python -m pytest tests/connectors/unit/files tests/browser/unit/archivos \
    tests/browser/e2e/widgets/test_archivos_render.py -q          # deterministic
./.venv/bin/python -m pytest tests/connectors/unit/files/live_cloud_drive_roundtrip.py -v
```

The second is node **5.8**, marked `live`: excluded from CI, it **SKIPS with the steps to enable it** while no
account with browsing permission is connected. It never asserts or prints a file name — this repo is public.
