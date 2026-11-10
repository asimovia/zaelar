# Building, installing and releasing the Zaelar Local Daemon

**Trigger:** *"build the daemon installers"*, *"release a new daemon version"*, *"how does someone install
this?"*

The daemon runs on the user's own computer, so unlike the engine it is not deployed — it is **handed over**.
Everything below is about producing a file somebody else can run, and about the one property that matters more
than any of it: that re-running the installer is the whole upgrade procedure.

---

## 1. What gets built

| Artifact | Needs | For |
|---|---|---|
| `zaelar-daemon.pyz` | a Python ≥ 3.11 on the target | developers, self-hosters, and the guarantee that there is always a way to ship — **files only**: no Playwright inside, so `/health` says `browser.state = "unsupported"` |
| `Zaelar.app` → `Zaelar.zip` (macOS) | nothing on the target | an ordinary Mac user: onedir app bundle, menu-bar icon, bundled browser driver |
| `zaelar-daemon.exe` (Windows) / `zaelar-daemon` (Linux) | nothing on the target | onefile; the tray on Windows, headless on Linux |
| `manifest.json`, `SHA256SUMS` | — | telling whether the file you have is the file that was built |

The portable archive is built by the **standard library** (`zipapp`) with no build dependency at all, which is
why it exists alongside the onefile: a build that only works when a third-party tool is working is a build that
stops existing the first time that tool breaks on a new Python.

```bash
python daemon/packaging/build.py             # everything this machine can build
python daemon/packaging/build.py --zipapp    # portable only, needs nothing installed

# what the desktop program bundles + PyInstaller, all pinned
pip install -r daemon/requirements.txt -r daemon/packaging/requirements-build.txt
python daemon/packaging/build.py --standalone   # Zaelar.app on macOS, onefile elsewhere (`--onefile` = old name)
```

Output lands in `dist/daemon/` (gitignored — the artifacts are reproducible from source, so a binary in a git
repo would only ever be a stale one). The macOS bundle itself is assembled in `dist/app/Zaelar.app` and only its
zip goes to `dist/daemon/`: a release attaches every file in that folder, and a bundle is thousands of files.

⚠️ **Two manifests, two jobs.** `daemon/requirements.txt` is the RUNTIME manifest of the packaged program — what
the installer bundles, each line pinned and explained (node **7.36** holds it to the decided set). PyInstaller is a
BUILD dependency and lives in `daemon/packaging/requirements-build.txt`. Neither is needed by `python -m daemon`:
the headless service is still standard library only, every bundled package is imported lazily inside the function
that needs it, and node **7.101** fails if the headless import path loads the tray or a GUI library.

### The desktop resident (V2-869): what the installed program carries

**The browser driver, not a browser.** Playwright and its Node driver (~100 MB in the wheel) ship inside the
program (`--collect-data playwright`: the driver is data no import statement reveals). The browser itself is
measured on the computer, never assumed (`daemon/browser/channel.py`):

1. **Google Chrome**, when installed → Playwright's `channel="chrome"`. Found per OS: macOS
   `/Applications/Google Chrome.app` or `~/Applications/…`; Windows the `App Paths\chrome.exe` registry key, then
   `Program Files` / `Program Files (x86)` / `%LOCALAPPDATA%`; Linux `google-chrome` / `google-chrome-stable` on PATH.
   The daemon uses Chrome's PROGRAM on its own profile directory — never the person's Chrome profile.
2. Otherwise **Chromium, downloaded on first run** into Playwright's own cache (`~/Library/Caches/ms-playwright`,
   `%LOCALAPPDATA%\ms-playwright`, `~/.cache/ms-playwright`) by `playwright install --no-shell chromium` through
   the bundled driver (`daemon/browser/download.py`). A background job with progress (parsed from Playwright's own
   `NN% of SIZE MiB` lines) and a cancel; a cancel sets `browser.auto_download = false` so the next start does not
   begin it again. Only a revision folder carrying Playwright's `INSTALLATION_COMPLETE` marker counts — a cancelled
   download leaves the folder without it. ~170 MB measured for Chromium 149 (`--no-shell` skips the headless shell
   the daemon never uses). The resident starts the job by itself when `auto_download` is on; the menu shows it with
   Cancel; `zaelar-daemon browser install` runs it in a terminal.

**v1 supports Google Chrome only** as an installed browser. Edge, Firefox and Safari are not looked for, and
`/health` lists them as `unsupported_browsers` so the interface can say so.

`/health` gains (`routes.health()` merges `daemon.browser.health_fields()` — the one line in `routes.py`; the logic
stays in `daemon/browser/`):

```json
"browser": {"state": "ready|downloading|absent|unsupported", "channel": "chrome|chromium|",
            "progress": 0-100, "size_mb": 171.0, "error": "only after a failed download"},
"unsupported_browsers": ["edge", "firefox", "safari"]
```

`unsupported` = this program has no Playwright (the `.pyz`, a bare `python -m daemon`) or the person turned windows
off (`ZAELAR_DAEMON_BROWSER=0`). `browser.auth` is declared exactly when `state == "ready"`. The measured channel is
recorded in `daemon.json` → `browser.channel` (a record, re-measured on every launch, never read back as an order).
`zaelar-daemon browser` prints the same object from a terminal.

**The transport is Playwright's pipe**, never `--remote-debugging-port`: a debug port would let any local process —
a web page's `fetch` included — drive a browser the person is signed in to. Node **7.100** fails on the flag anywhere
in `daemon/`.

**The tray** (`daemon/tray/`) — macOS a menu-bar extra on `rumps` (template image; the glyph changes SHAPE per
state: full dot connected, half dot waiting, cross error), Windows a notification-area icon on `pystray` + `Pillow`
(glyph and colour). It is a VIEW of `/health`, polled over HTTP every 5 s like any client, and never owns state. Menu:
**Open Zaelar · Allowed folders… · Sign-in window** (open/close; while there is no browser: download / cancel) ·
**Check for updates** (runs the signed update check now; once a verified update is waiting the item becomes
«Install Zaelar X (build N) and restart» — §3 «How the installed daemon updates itself») · **Quit**. On by default
for the packaged program, off for `python -m daemon`; `--tray` / `--no-tray` override. The HTTP server binds BEFORE
the GUI library loads, so an icon that cannot be drawn never costs the daemon (no tray → it serves headless and says
why). On Windows the `.exe` stays a console program (so `status` prints in a terminal) and the tray hides the console
when nobody started it from one. Icons: `daemon/tray/icons/`, regenerated by `daemon/packaging/tray_icons.py`.

**Open Zaelar** (`daemon/browser/app_window.py`) — starts the browser PROGRAM directly with `--app=<url>` on the
daemon's own app profile (`config/daemon/browser/app-profile`, separate from the sign-in window's because Chrome locks
a profile to one process). No Playwright and no pipe: nothing drives that window, so it carries no automation banner.
Where it points: the local engine when `/healthz` answers on `ZAELAR_ENGINE_URL` (loopback only) or
`http://localhost:43917`; else the link `daemon.relay.login_link` returns, imported lazily (the relay is its own
change); else the item is disabled with «pair with your cloud agent first». One window: a second click while it is
open does nothing.

**The global hotkey is deferred.** Every cross-platform option adds more than one dependency (`pynput` brings `six`
and PyObjC's Quartz frameworks on macOS), and on macOS a global key listener needs one more system permission
prompt (Input Monitoring). Not built; no config key for it.

**macOS: why `Zaelar.app`, onedir.** A onefile program unpacks itself into a temporary folder on every start, which
the hardened runtime and notarization handle badly; and only an app bundle carries an `Info.plist`
(`daemon/packaging/macos/info_plist.py`, patched after PyInstaller and then re-sealed AD HOC — identity signing is a
later step):

| Key | Value | Why |
|---|---|---|
| `CFBundleIdentifier` | `com.zaelar.daemon` | the identity macOS files permission grants under (same string as the LaunchAgent label) |
| `LSUIElement` | `true` | no Dock icon: it lives in the menu bar |
| `NSDocumentsFolderUsageDescription` | "Zaelar reads the documents in the folders you allow, to find or read them when you ask." | the sentence macOS shows in its own prompt |
| `NSDesktopFolderUsageDescription` | "Zaelar only looks at your Desktop if you allow it, to find what you ask for." | 〃 |
| `NSDownloadsFolderUsageDescription` | "Zaelar reads your Downloads only if you allow it, to open or find what you downloaded." | 〃 |

⚠️ **`http.server`'s reverse lookup stalled the packaged program.** The stock `HTTPServer.server_bind` calls
`socket.getfqdn("127.0.0.1")`; inside the packaged daemon on macOS that lookup fell through to mDNS and the process
sat **36 s** before `/health` answered, on every start (measured 2026-11-09; a from-source Python did not). The
daemon's server overrides `server_bind` without it (`daemon/http/lifecycle.py`).

---

## 2. Installing (and upgrading — the same command)

### How an ordinary person installs it: one line

```bash
curl -fsSL https://raw.githubusercontent.com/asimovia/zaelar/main/daemon/packaging/get.sh | bash    # macOS
```
```powershell
irm https://raw.githubusercontent.com/asimovia/zaelar/main/daemon/packaging/get.ps1 | iex           # Windows
```

⚠️ **This is the main path, and not because terminals are nice.** macOS quarantine and the Windows Mark of the
Web are written by whatever **saved** the file — a browser stamps them, `curl` and `Invoke-WebRequest` do not.
So an **unsigned** build that arrives this way is never held by Gatekeeper and never raises "Windows protected
your PC". That buys, for free and immediately, most of what a code-signing certificate would buy: no Apple
Developer account, no Microsoft account, no notarization queue, nothing that expires, and no approval between
a fix and the person who needs it.

What the bootstrap does, in order: pick the build for `uname -m`, resolve **the newest release that publishes
that exact file** (never `releases/latest` — an engine release whose daemon build is still running has none; and
never a `daemon-v*` prefix — the daemon is rebuilt on every engine tag, so a prefix tag sinks below the API's
first page and the filter finds nothing), download it, **verify its SHA-256 against the published
sums while it is still an inert file in a temp directory**, and only then run the installer, fetched from
`main` so it shares the origin the user already trusted by running the line.

Be exact about what the hash is: **two files from one release agreeing.** It catches a corrupt download, not a
release whose binary and sums were both replaced — that is what the signature adds. When `cosign` is on PATH the
bootstrap first verifies the Sigstore bundle over the sums against the release workflow's identity and refuses
to install on a bad or missing signature; without it, it checks the hash only and prints the command to verify
by hand (see «Signing» below).

The direct download still works and the interface still offers it, in a `<details>` that says what it costs: a
browser saved the file, so macOS asks the user to allow it in System Settings and Windows shows SmartScreen.

### Where it lands, and how to put it somewhere else

| | Default |
|---|---|
| macOS | `~/Library/Application Support/Zaelar` |
| Windows | `%LOCALAPPDATA%\Zaelar` |

`ZAELAR_DAEMON_PREFIX` (or `-Prefix` on Windows) moves it, and the **uninstallers take the same override** —
one that only knew the default would remove the launch agent, report success, and leave the program and the
folder allowlist exactly where the user put them.

⚠️ **The state follows the program, and it is derived rather than configured.** The daemon takes its root from
where its own binary sits: `<prefix>/bin/<program>` → `<prefix>`, so the token, the allowlist and the audit log
land in `<prefix>/config/daemon`. That is why a custom prefix needs no environment variable in the launch
agent and no wrapper around the Windows task — which matters on Windows, where a scheduled task cannot carry an
environment variable and setting a user-level `ZAELAR_WORKSPACE` would repoint the **engine's** workspace as a
side effect. (The macOS `Zaelar.app` is the exception: its program sits inside the bundle, not in `bin/`, so the
LaunchAgent and the `bin/` launcher hand it `ZAELAR_WORKSPACE=<prefix>` — see «Installing from a checkout».)

The `bin` directory is the guard, not decoration. Without it a file somebody ran straight out of `~/Downloads`
would claim `~` as its root, and an in-repo `python -m daemon` would resolve `sys.executable` to
`.venv/bin/python` and take the **virtualenv** for its prefix.

⚠️ **"Installed" is not the same as "frozen".** A zipapp is not frozen, so the root resolution must recognise
an installed `.pyz` too; testing `_frozen()` alone would resolve its state to a directory *inside the archive
file* — impossible to create. Since this module never raises, every write would fail quietly: a fresh random
token on every start and a folder allowlist that does not survive a restart, behind a `/health` that answers
perfectly.

### Installing from a checkout

**macOS**

```bash
daemon/packaging/macos/install.sh              # Zaelar-macos.zip / dist/daemon/Zaelar.zip / dist/app/Zaelar.app,
                                               # else a onefile or .pyz next to it
daemon/packaging/macos/uninstall.sh [--purge]
```

Per-user LaunchAgent, `~/Library/Application Support/Zaelar`, **no sudo**. The app lands in
`<prefix>/Zaelar.app` (unpacked with `ditto`, quarantine cleared) and the LaunchAgent starts its program with
`ProcessType Interactive` (a menu-bar app) and `EnvironmentVariables → ZAELAR_WORKSPACE=<prefix>`: the program lives
inside the bundle, not in `<prefix>/bin/`, so «the state follows the program» cannot derive the prefix and it is
handed over instead. `<prefix>/bin/zaelar-daemon` becomes a two-line launcher into the bundle with the same
variable, so `status`, `allow`, `token` work as before. Verified by hand 2026-11-09 with a scratch `HOME` and a
prefix containing a space: launchd ran the app, `/health` declared `browser.auth`, state landed in the prefix,
uninstall left nothing.

**Windows**

```powershell
powershell -ExecutionPolicy Bypass -File daemon\packaging\windows\install.ps1
powershell -ExecutionPolicy Bypass -File daemon\packaging\windows\uninstall.ps1 [-Purge]
```

Per-user scheduled task at logon, `%LOCALAPPDATA%\Zaelar`, **no administrator**. If local policy refuses the
task, it falls back to a minimized Startup shortcut and says so rather than telling somebody to find an admin.

**No elevation on either platform, and that is a security property before it is a convenience one:** a per-user
daemon that needed elevation could then reach every account on the machine, which is exactly the blast radius
the permission circuit exists to keep small.

**Re-running the installer is the upgrade path** — stop, replace, start. The state directory (the token and the
folders the user chose) is never touched, so an upgrade keeps their choices. Uninstalling keeps them too unless
asked to `--purge`, because uninstalling is usually a step in troubleshooting and throwing away the allowlist
turns "let me reinstall this" into "let me set it all up again".

### The two install-time surprises, both real

- **macOS TCC.** The first time the daemon reads `~/Documents`, `~/Desktop` or `~/Downloads`, macOS asks the
  user to allow it — its own permission layer, on top of ours. If the prompt is missed: System Settings →
  Privacy & Security → Files and Folders. The installer prints this.
- **Quarantine / Mark of the Web.** A file that arrived through a browser is blocked, and the failure is a
  dialog the user cannot dismiss into a working state. Both installers clear it on the file the user just chose
  to install. That is **not** a substitute for signing.

---

## 3. Releasing

`.github/workflows/daemon-artifacts.yml` builds on **macos-latest** and **windows-latest** — the platforms
people install on, not the one the tests run on — and on a tag attaches the artifacts to the release.

It does more than build. On each runner it:

1. imports the daemon on a **bare Python with nothing installed** (stronger than proving it in a checkout where
   the engine's venv is next door and an accidental import would resolve);
2. **parse-checks the installer scripts** — a syntax error in a PowerShell file is a thing you find at install
   time, on somebody else's computer;
3. starts the **real binary** and checks `/health` answers **and that a request naming `Host: evil.example` is
   still refused with a 401** — the one regression that would ship a daemon which starts and defends nothing;
4. checks the installed-style build finds the runner's Google Chrome (`zaelar-daemon browser` → `ready`/`chrome`)
   and `/health` declares `browser.auth` — through the BUNDLED Playwright;
5. on macOS, checks the `.app`'s `Info.plist` (bundle id, `LSUIElement`, the three usage strings) and its ad-hoc
   seal (`codesign --verify --deep --strict`), and that the bundled Node driver is executable;
6. starts the resident WITH its tray (the packaged default) and checks it still answers — built and started, not
   clicked: clicking the menu is a manual check;
7. on macOS, builds the installer package UNSIGNED (never published) and checks its shape: a current-user install
   with no administrator, the bundle not relocatable, `postinstall` + `install.sh` inside.

### The pipeline, in the order the BYTES go through it

```
build → smoke test → identity signing (conditional) → rename → sums → cosign → provenance → manifest → minisign → release
```

Identity signing changes the bytes, so it runs BEFORE the sums: every later record — sums, Sigstore bundle,
provenance, update manifest — is then about the files that are actually published. The rename recomputes the sums
(below), so cosign signs after it; the manifest is written by its own job once every build job has renamed,
summed and cosigned, over the PUBLISHED names, and minisign signs it last.

| Step | Where | Runs when | Without it |
|---|---|---|---|
| Smoke test (the binary runs, finds Chrome, its guards hold) | each build job | always | — (the job fails) |
| Developer ID sign + notarize + staple + `Zaelar.pkg` | macOS jobs, `macos/sign_and_notarize.sh sign` | ALL eight Apple secrets exist | notice «unsigned: identity secrets absent»; the ad hoc zip ships as before |
| Authenticode (Azure Artifact Signing) | Windows job, `azure/artifact-signing-action` pinned by commit | ALL six Azure secrets exist | the same notice; the unsigned `.exe` ships as before |
| Rename + sums | `release_names.py` | always | — |
| Sigstore keyless over the sums + provenance | each build job | always | — |
| `update-manifest.json` | `manifest` job, `update_manifest.py` | always | — |
| minisign over the manifest | `manifest` job | `MINISIGN_SECRET_KEY` exists | notice: published UNSIGNED — every installed daemon refuses it |

**The secret names the workflow reads, and nothing else** (node 7.111 fails on any other `secrets.*`):

| Identity | Secrets |
|---|---|
| Apple | `APPLE_DEVID_APP_P12`, `APPLE_DEVID_APP_P12_PASSWORD` (the Developer ID Application `.p12`, base64), `APPLE_DEVID_INSTALLER_P12`, `APPLE_DEVID_INSTALLER_P12_PASSWORD` (Developer ID Installer), `NOTARY_KEY_P8` (an App Store Connect API key, PEM or base64), `NOTARY_KEY_ID`, `NOTARY_ISSUER`, `APPLE_TEAM_ID` |
| Windows | `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `ARTIFACT_SIGNING_ENDPOINT`, `ARTIFACT_SIGNING_ACCOUNT`, `ARTIFACT_SIGNING_PROFILE` |
| Update manifest | `MINISIGN_SECRET_KEY` (the whole minisign secret key file), `MINISIGN_PASSWORD` |

A PARTIAL set (some secrets of an identity, not all) is a warning, not a failure, and signs nothing: the workflow
stays green while secrets are being added one by one.

```bash
git tag daemon-v0.2.0 && git push origin daemon-v0.2.0
```

### ⚠️ Release assets are named per platform, and the interface depends on it

Both runners produce `zaelar-daemon.pyz`, `manifest.json` and `SHA256SUMS` under those exact names, and the
release job flattens every downloaded artifact into a single upload — so without a rename one platform's files
would overwrite the other's. Each runner renames its own before uploading:

| Published asset | Platform |
|---|---|
| `Zaelar-macos.zip`, `zaelar-daemon-macos.pyz` | macOS, Apple Silicon (the zipped `Zaelar.app`) |
| `Zaelar-macos-x86_64.zip`, `zaelar-daemon-macos-x86_64.pyz` | macOS, Intel |
| `zaelar-daemon-windows.exe`, `zaelar-daemon-windows.pyz` | Windows |
| `SHA256SUMS-<suffix>`, `manifest-<suffix>.json` | one per build job |
| `get.sh`, `get.ps1`, `zaelar-daemon-(un)install-*` | published once, architecture-independent |

⚠️ **Two Mac builds, not one.** A PyInstaller bundle carries a real interpreter compiled for one architecture
and `macos-latest` has been arm64 since macos-14, so a single build would hand an Intel Mac a binary that fails
with "bad CPU type in executable" — which every user reads as a corrupt download. `get.sh` picks by `uname -m`,
which is precisely what a download button cannot do: a user-agent does not say which Mac this is.

⚠️ **`release_names.py` owns the rename, and it RECOMPUTES the digests.** `build.py` writes `SHA256SUMS` under
the build names while the release publishes the architecture names, so the published sums must be computed
over the published names — otherwise the one-line installer would refuse a binary it fetched perfectly.
Patching the names inside the build's file is not enough: the digests are recomputed from the renamed files.

⚠️ **Releases cut before the `.app` publish `zaelar-daemon-macos[-x86_64]`** (onefile). `get.sh` asks for the newest
release carrying `Zaelar-<suffix>.zip` and, when none does yet, falls back to the newest carrying the old file — the
same daemon without the icon and the bundled browser. The download screen's direct link
(`server/daemon_downloads.py`) names the zip, so it 404s until the first release that carries it.

**These names are a contract.** `server/daemon_api.py` builds the download links from them, and both installers
look for them (including in `~/Downloads`, which is where a browser actually puts them). Renaming an asset
without the other two is how the download screen starts offering a 404, so node **7.44** joins all three.

### Where a user gets the file

`GET /api/daemon/status` carries a `downloads` block whose direct links follow **`releases/latest/download/`**:
every engine tag attaches a fresh daemon build, and the old pin to `daemon-v<version>` went stale silently (the
version number stood still while the code moved). The one-line command stays the main path and never depends
on `latest` carrying the files. The 🖥 icon in the interface renders it; when the engine runs on a remote host that is the icon's whole job,
since a remote engine cannot reach a daemon on somebody's desk.

`ZAELAR_DAEMON_DOWNLOAD_BASE` overrides the base URL for a mirror or a private build.

### Signing

**What is signed, and by whom.** Each build job signs its own `SHA256SUMS-<suffix>` with a **Sigstore keyless**
signature. There is no signing key: the job asks GitHub for an OIDC token (`id-token: write`), Sigstore's
Fulcio turns it into a short-lived certificate whose subject is the workflow's identity —
`https://github.com/asimovia/zaelar/.github/workflows/daemon-artifacts.yml@refs/tags/<tag>` on a release, issuer
`https://token.actions.githubusercontent.com` — and the signature is recorded in the public **Rekor**
transparency log. The job then attaches **GitHub build-provenance attestations** (`attestations: write`) to
exactly the files the sums list: `zaelar-daemon-<suffix>` (`.exe` on Windows) and `zaelar-daemon-<suffix>.pyz`.

| Published beside each build | What it is |
|---|---|
| `SHA256SUMS-<suffix>` | SHA-256 of the binary and the archive, under their published names |
| `SHA256SUMS-<suffix>.sigstore.json` | One Sigstore bundle: signature + certificate + Rekor inclusion proof |
| (GitHub attestation store) | SLSA build provenance for each file in the sums |

⚠️ **The order is the guard.** `release_names.py` rewrites the sums for the published names, so signing comes
AFTER it — a signature taken before would be valid over a file that is never published. The script also deletes
any signature already in `dist/daemon/` (a `.sigstore.json`, `.sig` or `.pem` from an earlier name or run), so
the only bundle beside the sums is the one made over them. The job then verifies its own bundle against its own
identity before uploading: a signature that only verifies on someone's laptop is an untested claim.

**One bundle, not `.sig` + `.pem`.** The bundle carries the transparency-log proof as well as the signature and
certificate, so verifying needs one extra file and no Rekor lookup to be trusted at install time; it is cosign's
default output and what `verify-blob --bundle` reads.

**Verifying a download by hand** (the checksum file first, then the binary against it):

```bash
cosign verify-blob \
  --bundle SHA256SUMS-macos.sigstore.json \
  --certificate-identity-regexp '^https://github.com/asimovia/zaelar/\.github/workflows/daemon-artifacts\.yml@refs/tags/' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  SHA256SUMS-macos
shasum -a 256 -c SHA256SUMS-macos --ignore-missing
gh attestation verify zaelar-daemon-macos --repo asimovia/zaelar
```

On Windows: the same `cosign` line with `-windows`, then `Get-FileHash zaelar-daemon-windows.exe` against the
sums. A `workflow_dispatch` build is signed by `…/daemon-artifacts.yml@refs/heads/<branch>`, so the regexp
above (tags only) correctly refuses it — a branch build is not a release.

**The installers verify it when they can.** `get.sh` and `get.ps1` check the bundle when `cosign` is on PATH and
refuse to install on a bad OR missing signature (whoever can replace the binary and the sums can also delete
the bundle, so "no signature" never means "fine"). Without `cosign` they keep the hash check and print one line
with the command above. `ZAELAR_DAEMON_SIGNER_RE` points the check at a fork's own workflow.

**What this proves, and what it does not.** A passing check means the bytes are the ones this repository's
release workflow built and signed for a tag. It does not mean the code was reviewed. Releases cut before signing
existed carry no bundle.

### Identity signing — Developer ID, notarization, Authenticode (conditional)

**macOS** (`daemon/packaging/macos/sign_and_notarize.sh sign`): the identities go into a throwaway keychain (unlocked,
key partition list set so `codesign` never waits on a prompt; deleted and the search list restored on exit, whatever
happens). Every Mach-O in the bundle is signed INSIDE-OUT — files deepest path first, then nested bundles
(`Python.framework`) deepest first, then the app — with the hardened runtime and a secure timestamp; never
`codesign --deep` to SIGN (it applies one set of options to nested code it never inspected — `--deep` is used to
VERIFY). The team identifier must equal `APPLE_TEAM_ID`. The app is notarized (`notarytool submit --wait`; anything
but `Accepted` fails the job and prints Apple's log), stapled and RE-ZIPPED, so `Zaelar-<suffix>.zip` — what `get.sh`
and the auto-update install — carries a notarized app. Then what a user RECEIVES is assessed: the published zip is
extracted and that copy must pass `codesign --verify --deep --strict`, `stapler validate` and Gatekeeper
(`spctl --assess --type execute` naming `Notarized Developer ID`); any failure fails the release.

**Entitlements are per binary and were measured** (2026-11-10, arm64 build, hardened runtime): only the bundled
Node that drives Playwright gets one — `allow-jit` (`macos/entitlements-node.plist`); without it V8 dies on its first
JIT page. The app, the Python runtime and the tray need none (`allow-unsigned-executable-memory`, once listed "for
ctypes", was measured unnecessary). Library validation stays on: every dylib is re-signed by the same team.
Chromium is not bundled — the daemon drives the installed Chrome or downloads Chromium on first run into the user's
folder. After signing, the workflow re-runs the smoke test on the SIGNED bytes (Chrome ready, Node's JIT, the resident
with its tray), so a missing entitlement fails on the runner.

**The `.pkg` is optional.** With the Developer ID Installer identity, `Zaelar.pkg` is built (`pkgbuild` +
`productbuild`, a distribution that enables only the current user's home: no administrator; the component is
`auth="none"` and not relocatable; payload `~/Library/Application Support/Zaelar/Zaelar.app`; a `postinstall` that runs
the same `install.sh`), signed, notarized, stapled, assessed as an install and published as `Zaelar-<suffix>.pkg` —
`get.sh` prefers it when the signed sums list it. Without that identity the notarized zip ships alone and `get.sh`
installs from it.

**Testable without Apple.** `sign_and_notarize.sh --dry-run sign <Zaelar.app> <dir> <suffix>` walks the real bundle
and prints every command it would run (`+ codesign …`), needs no secret and prints none. Every macOS build prints that
plan; node 7.126 pins its order on a fixture bundle.

**Whether a release is signed is measured from its bytes.** `update_manifest.py` writes `"signed": true|false` for
`macos`, `macos-x86_64` and `windows`: a Mac zip is signed when it carries the stapled ticket
(`Zaelar.app/Contents/CodeResources`) or its `.pkg` is published; a Windows `.exe` when its certificate-table directory
is not empty. The engine reads it from `releases/latest/download/update-manifest.json` in the background (cached six
hours, `null` until known) into `/api/daemon/status.downloads.platforms.<os>.signed`, and the 🖥 screen drops the
"your system will ask you to allow it" line only for a platform marked signed (nodes 7.127, 4.444). The updater never
trusts this flag; it trusts the minisign signature and the digest.

**Windows**: `azure/artifact-signing-action` (formerly Trusted Signing; the certificate never leaves Azure) signs
`zaelar-daemon.exe` with SHA-256 and an RFC 3161 timestamp; the job then requires `Get-AuthenticodeSignature` to
say `Valid` and runs the signed program. No separate installer: the onefile `.exe` plus `install.ps1` stays the
install path.

⚠️ **Not verified yet:** none of the signed branches has run against Apple or Azure — no secret is set yet. The
structure is pinned (nodes 7.111, 7.126), the unsigned package's shape and the signing plan are checked on every macOS
build, and the entitlements were measured on an ad hoc hardened build; the first run with the secrets is the real
test, on a CLEAN machine, before a release is announced.

### The first signed release — procedure

1. **Secrets** (repository → Settings → Secrets and variables → Actions; names only, values never in the repo):

   ```bash
   gh secret set APPLE_DEVID_APP_P12 --repo asimovia/zaelar < <(base64 -i developer-id-application.p12)
   gh secret set APPLE_DEVID_APP_P12_PASSWORD --repo asimovia/zaelar
   gh secret set NOTARY_KEY_P8 --repo asimovia/zaelar < AuthKey_XXXXXXXXXX.p8
   gh secret set NOTARY_KEY_ID --repo asimovia/zaelar
   gh secret set NOTARY_ISSUER --repo asimovia/zaelar
   gh secret set APPLE_TEAM_ID --repo asimovia/zaelar
   # optional — only for the .pkg:
   gh secret set APPLE_DEVID_INSTALLER_P12 --repo asimovia/zaelar < <(base64 -i developer-id-installer.p12)
   gh secret set APPLE_DEVID_INSTALLER_P12_PASSWORD --repo asimovia/zaelar
   ```

   The `.p12` must contain the certificate AND its private key (export both from Keychain Access). `NOTARY_KEY_P8`
   accepts the PEM text or its base64. The notary key needs the "Developer" role in App Store Connect → Users and
   Access → Integrations → Keys. Secrets reach tag pushes from this repository, never a fork's pull request.
2. **Dry rehearsal**: run the workflow by hand (`gh workflow run daemon-artifacts.yml --ref main`). It builds, signs
   and notarizes but publishes nothing (no tag, no `release` job). Read the `identity` step (no "unsigned" notice for
   macOS), the sign step (`notarized …`, `Gatekeeper: Zaelar.app accepted, notarized Developer ID`) and the signed
   smoke test.
3. **Tag**: bump `update/BUILD`, commit, then push the tag (`git tag daemon-vX.Y.Z && git push origin daemon-vX.Y.Z`).
4. **On a CLEAN Mac** (not the build machine; a fresh user account is enough), download the zip with a BROWSER so it
   is quarantined, unzip, and:

   ```bash
   spctl --assess --type execute --verbose=4 Zaelar.app        # accepted · source=Notarized Developer ID
   codesign -dv --verbose=4 Zaelar.app                         # Authority=Developer ID Application: … · TeamIdentifier · Runtime Version
   codesign --verify --deep --strict --verbose=2 Zaelar.app    # valid on disk · satisfies its Designated Requirement
   xcrun stapler validate Zaelar.app                           # The validate action worked!
   pkgutil --check-signature Zaelar-macos.pkg                  # Developer ID Installer · trusted by the Apple root (if published)
   spctl --assess --type install --verbose=4 Zaelar-macos.pkg  # accepted · source=Notarized Developer ID (if published)
   ```

   Then open it by double-click: no "cannot be opened" dialog. Check `update-manifest.json` says `"signed": true` for
   both Mac platforms, and the 🖥 screen's fold shows the signed sentence.

**Windows** is gated on `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `ARTIFACT_SIGNING_ENDPOINT`,
`ARTIFACT_SIGNING_ACCOUNT`, `ARTIFACT_SIGNING_PROFILE` (Azure Artifact Signing: no certificate file to hold; the
account and its identity validation come first). Until all six exist the `.exe` ships unsigned with a notice, the
manifest says `"signed": false` for it, and the screen keeps the SmartScreen line. Even signed, SmartScreen can warn
on a new release until the signature builds reputation — the signed Windows sentence says so.

### The signed update manifest

One `update-manifest.json` per release (`daemon/packaging/update_manifest.py`, shape in `daemon/update/manifest.py`
— writer and reader import the same table):

```json
{"product": "zaelar-daemon", "version": "0.2.2", "build": 123, "tag": "v3.140",
 "published_at": "2026-11-09T12:00:00Z", "min_engine_build": 0,
 "platforms": {"macos":        {"asset": "Zaelar-macos.zip",          "sha256": "…", "size": 1},
               "macos-x86_64": {"asset": "Zaelar-macos-x86_64.zip",   "sha256": "…", "size": 1},
               "windows":      {"asset": "zaelar-daemon-windows.exe", "sha256": "…", "size": 1},
               "pyz":          {"asset": "zaelar-daemon-macos.pyz",   "sha256": "…", "size": 1}},
 "installers": {"macos": {"asset": "Zaelar-macos.pkg", "sha256": "…", "size": 1}},
 "next_key": null}
```

- **`build` is the engine's `update/BUILD` (V2-553)** at the tag; `build.py` stamps the same integer into the
  packaged daemon (`daemon/update/BUILD`), so `/health.update.current.build`, the manifest and the engine's own
  number are ONE number, and the engine's connection icon can say "your daemon is older" with one comparison.
- The writer **refuses** a build name that survived the rename and any digest that disagrees with the job's
  `SHA256SUMS-<suffix>`; a platform whose build did not run is left out (and said so), not fatal.
- `installers` appears only when the notarized `.pkg` was built; the updater installs the zip.
- `next_key` rotates the key without a flag day: a manifest signed by a trusted key may announce the next public
  key, which the client remembers. A key is only ever learned from a manifest that verified.

**Signed with minisign** (`minisign -S`, prehashed Ed25519) using `MINISIGN_SECRET_KEY`, which is never in the
repository or the release. The **public key is committed at `daemon/update/PUBLIC_KEY`** — so trusting this
repository's `main` is the only trust decision, and the client never fetches the key it verifies with from the same
place as the thing it verifies. The job verifies its own signature with the CLIENT's code and the COMMITTED key,
so a secret that does not match the committed key fails the release here, not on users' machines. ⚠️ The committed
key is a DEVELOPMENT key: it is rotated (new pair, new `PUBLIC_KEY`, new secret) before the first real release.

### How the installed daemon updates itself (`daemon/update/`)

- **When:** an installed daemon checks once a day (first check two minutes after start; `ZAELAR_DAEMON_AUTO_UPDATE=0`
  turns it off), and whenever the person picks «Check for updates» in the tray. A source tree never updates itself.
- **Where:** the newest release (newest-first, as the API lists them) that CARRIES `update-manifest.json` — the
  same "asset exists" rule as `get.sh`.
- **What must verify** (any failure → `state = failed`, the reason in `/health.update.error`, nothing downloaded or
  changed): a `.minisig` exists (an unsigned manifest is refused — correct, not a gap), it verifies against the
  committed key (or a `next_key` learned from a verified manifest), the manifest parses, and its `tag` is the
  release it was found on (no replay of a valid manifest from another release).
- **Decision:** newer when the manifest's `build` is greater than this daemon's; the daemon's `version` only breaks
  a tie for a build that does not know its number. Never backwards.
- **Download:** to the updater's own staging folder; size and sha256 against the signed manifest; when `cosign` is
  on PATH, also the Sigstore bundle over `SHA256SUMS-<suffix>` and the asset's line in it (the same check as
  `get.sh`; optional — the manifest already pins the bytes). Any mismatch deletes the download → `failed`.
- **Swap** (from `ready` only, after re-hashing the staged file): macOS extracts the zip beside `Zaelar.app`,
  requires the new bundle's code signature to verify and — on a Developer-ID install — the SAME team, exchanges
  the two directories in one atomic `renamex_np(RENAME_SWAP)` and restarts with `launchctl kickstart -k
  gui/<uid>/com.zaelar.daemon`. Windows renames the running `.exe` aside (`zaelar-daemon.old.exe`), renames the new
  one into place (and back on failure), and a detached `cmd` restarts it two seconds after this process exits; the
  `.old.exe` is deleted by the next check. Chosen over "swap at next start via the scheduled task" because
  `install.ps1`'s Startup-folder fallback has no launcher to run a swap. A `.pyz` is `os.replace`d (atomic).
- **Automatic install** happens only when no sign-in window is open; otherwise the tray shows «Install Zaelar X
  (build N) and restart».
- **State:** `<state dir>/update/state.json` — `state` (`idle | downloading | ready | failed`), `error`,
  `last_check`, `last_result`, `available`, `pending`, `next_key`. `ready` is reachable only through `downloading`.
- **`/health.update`** = `{current: {version, build}, available: {version, build, tag, published_at} | null,
  state, error, last_check}` — read from that file, nothing fetched while answering.

⚠️ **Not verified live:** no release carries a signed manifest yet (no tag cut, no `MINISIGN_SECRET_KEY` stored),
the macOS swap + `kickstart` was exercised on fake bundles only, and the Windows rename dance only as file
operations on macOS — never on Windows.

### How a user verifies a release

The `cosign` + `shasum` + `gh attestation` lines above, plus, for the manifest:

```bash
curl -fsSLO https://raw.githubusercontent.com/asimovia/zaelar/main/daemon/update/PUBLIC_KEY
minisign -V -p PUBLIC_KEY -m update-manifest.json      # then compare the sha256 it lists with the file
spctl --assess --type install --verbose=2 Zaelar-macos.pkg        # notarized package (when published)
```

`get.sh` / `get.ps1` do all of it when the tools are present: cosign over the sums (bad or missing → refused);
minisign over the manifest when the release has one AND its signature (bad, or not listing the bytes that arrived
→ refused; no manifest or unsigned → skipped and said); and on a Mac they prefer `Zaelar-<suffix>.pkg` whenever the
SIGNED sums list one — `install.sh` then requires `pkgutil --check-signature` and Gatekeeper
(`spctl --assess --type install`) to accept it before taking the app out of it.

---

## 4. Tests

| Claim | Where it is checked |
|---|---|
| The archive assembles, carries every module, excludes the build tooling, and **runs** | Node **7.41**, on every CI run |
| The installed process does its whole job over real HTTP | Node **7.37** (boots a real `python -m daemon`) |
| The guards hold against a hostile local process | Node **7.40**, with disarms |
| The release asset names, the download links and the installers agree | Node **7.44** |
| The Windows and macOS builds, the installer syntax, and the guards surviving the build | `.github/workflows/daemon-artifacts.yml` on `windows-latest` / `macos-latest` |
| The sums are signed after the rename, provenance is attested, and the installers verify the bundle | Node **7.99** (workflow + installers + `release_names.py`, with disarms) and the workflow's own verify step |
| The browser: Chrome per OS, the Chromium download job (start → progress → ready / cancelled / failed), `browser.auth` only when launchable, the channel recorded, never a debug port | Node **7.100**, with disarms |
| The tray is a view of `/health` and off the headless path; «Open Zaelar» local → relay → disabled; the `.app`'s `Info.plist`; the zipped app in the release; installers parse | Node **7.101**, with disarms |
| The auto-update: minisign-signed manifest verified with the committed key (pure-Python Ed25519); unsigned / other key / tampered / replayed / size or sha256 mismatch / staged file changed → `failed` with the installed bytes unchanged; the state machine; `/health.update`; the swap's rollback; «Install» only when verified | Node **7.110**, with disarms |
| The manifest written after the rename and agreeing with the signed sums; conditional minisign / Developer ID / Authenticode with a visible skip and only the agreed secret names; the installers verify the manifest and prefer a notarized `.pkg`; the `.pkg` is a current-user install | Node **7.111**, with disarms |

The macOS install path (launchd accepts the job, starts it, defers to an already-running instance, and uninstall
leaves nothing) can be exercised by hand by installing into a temporary `HOME` and checking `launchctl print`.
