#!/usr/bin/env bash
# Developer ID signing, notarization and the installer package for Zaelar.app (V2-869 §5).
#
#   sign_and_notarize.sh [--dry-run] sign <Zaelar.app> <dist dir> <suffix>   sign, notarize, staple, re-zip, [.pkg]
#   sign_and_notarize.sh check <Zaelar.app> <work dir> <suffix>              build the .pkg UNSIGNED, check its shape
#
# WHO RUNS THIS. The release workflow, on a macOS runner, and only when the identity secrets exist — otherwise the
# workflow skips it with a visible "unsigned: identity secrets absent" notice and publishes the ad hoc build exactly
# as before. `check` runs on every build, so the package's SHAPE is proven long before an identity exists to sign it.
#
# --dry-run PRINTS every command that touches a keychain, a signature, Apple's notary service or the output files
# (`+ codesign …`), runs none of them, and needs no secret. It still walks the REAL bundle to decide what to sign,
# so the printed plan is the plan a release would execute — the unit test reads it to pin the order without an
# Apple account. Read-only probes (`find`, `file`, `plutil`) run for real in both modes.
#
# WHAT IT READS (environment; values are never printed — GitHub masks them, and nothing here uses `set -x`):
#   APPLE_DEVID_APP_P12 / _PASSWORD               the "Developer ID Application" certificate (.p12, base64)  REQUIRED
#   NOTARY_KEY_P8, NOTARY_KEY_ID, NOTARY_ISSUER   an App Store Connect API key for `notarytool`              REQUIRED
#   APPLE_TEAM_ID                                 the team the certificates must belong to                   REQUIRED
#   APPLE_DEVID_INSTALLER_P12 / _PASSWORD         the "Developer ID Installer" certificate (.p12, base64)    OPTIONAL
#     Only the `.pkg` needs it. Without it the notarized, stapled zip is published and no `.pkg`; `get.sh` then
#     installs from the zip, exactly as it does for a release cut before any identity existed.
#
# THE ORDER, and why:
#   1. import: a throwaway keychain (deleted on exit, whatever happens) holds the identities, unlocked, with the key
#      partition list set so `codesign` never waits on an access prompt nobody can click; the keychain search list
#      is restored on exit, so a run on a developer's Mac leaves their keychains as they were;
#   2. sign INSIDE-OUT: every Mach-O file deepest path first, then every nested bundle (`Python.framework`) deepest
#      first, then the app — hardened runtime and a secure timestamp on all of them. Never `codesign --deep` to
#      SIGN: Apple documents `--deep` as a verification aid, and it applies one set of options to code it never
#      inspected;
#   3. verify: `codesign --verify --deep --strict`, and the team identifier must equal APPLE_TEAM_ID;
#   4. notarize the app, zipped, through `notarytool submit --wait`; anything but "Accepted" fails with Apple's log;
#   5. staple the ticket into the bundle and re-zip it (`ditto -c -k --keepParent`) — `Zaelar-<suffix>.zip`, the
#      file the one-line installer and the auto-update both use, carries a notarized, stapled app;
#   6. assess what a USER receives: the zip is extracted to a fresh folder and THAT copy must pass `codesign
#      --verify --deep --strict`, `stapler validate` and Gatekeeper (`spctl --assess --type execute` naming a
#      notarized Developer ID). Any of them failing fails the job: a release that would warn is not published;
#   7. the installer package, when the Installer identity exists: built, signed, notarized, stapled, assessed.
#
# ENTITLEMENTS ARE PER BINARY AND MEASURED (2026-11-10, Zaelar.app from build.py, arm64, hardened runtime):
#   the bundled Node (Playwright's driver)   `entitlements-node.plist` = allow-jit. Without it V8 dies on its first
#                                             JIT page (SIGTRAP); allow-jit alone runs it. Chromium is NOT bundled:
#                                             the daemon drives the installed Google Chrome, or downloads Chromium
#                                             on first run into the user's folder, outside this signature.
#   the app, the Python runtime, the tray     NO entitlements: `version`, `browser` and the resident with its
#                                             menu-bar icon ran with none. `allow-unsigned-executable-memory` was in
#                                             an earlier draft "for ctypes/libffi" — measured unnecessary, removed.
#   library validation                        kept ON: every dylib is re-signed here by the same team. (An AD HOC
#                                             hardened build cannot load its own Python — "different Team IDs" —
#                                             which is why measuring this locally needs disable-library-validation
#                                             as a stand-in for "same team", and why it is not shipped.)
# The workflow re-runs the smoke test on the SIGNED app (Chrome ready, Node's JIT, the resident with its tray): a
# missing entitlement fails the release on the runner, never on somebody's Mac.
set -euo pipefail

DRY=0
if [[ "${1:-}" == "--dry-run" ]]; then DRY=1; shift; fi
MODE="${1:?usage: sign_and_notarize.sh [--dry-run] sign|check <Zaelar.app> <dir> <suffix>}"
APP="${2:?}"
OUT="${3:?}"
SUFFIX="${4:?}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG_ID="com.zaelar.daemon.pkg"
ENTITLEMENTS_NODE="$HERE/entitlements-node.plist"

say() { printf '  %s\n' "$*"; }
die() { printf '✗ %s\n' "$*" >&2; exit 1; }
phase() { printf '== %s\n' "$*"; }
# Every command with a side effect goes through `run`: executed normally, printed (and skipped) under --dry-run.
run() {
  if (( DRY )); then printf '+ %s\n' "$*"; return 0; fi
  "$@"
}

[[ -x "$APP/Contents/MacOS/zaelar-daemon" ]] || die "$APP is not a Zaelar.app"
VERSION="$(/usr/bin/plutil -extract CFBundleShortVersionString raw "$APP/Contents/Info.plist")"
case "$SUFFIX" in
  macos) ARCH="arm64" ;;
  macos-x86_64) ARCH="x86_64" ;;
  *) die "unknown suffix $SUFFIX" ;;
esac

WORK="$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/zaelar-sign.XXXXXX")"
KEYCHAIN=""
SEARCH_LIST=()
cleanup() {
  if [[ -n "$KEYCHAIN" ]] && (( ! DRY )); then
    if (( ${#SEARCH_LIST[@]} )); then security list-keychains -d user -s "${SEARCH_LIST[@]}" >/dev/null 2>&1 || true; fi
    security delete-keychain "$KEYCHAIN" >/dev/null 2>&1 || true
  fi
  rm -rf "$WORK"
}
trap cleanup EXIT

# Deepest path first, then by spelling: `awk` prefixes the depth so the order is by NESTING (a reverse lexical sort
# puts `a/z` before `a/b/c`, sealing a folder's file after a deeper sibling bundle for no reason).
deepest_first() { awk -F/ '{ print NF "\t" $0 }' | sort -t "$(printf '\t')" -k1,1nr -k2 | cut -f2-; }

# ── the installer package (signed or not, the same shape) ────────────────────────────────────────────────────
# CURRENT-USER ONLY: the distribution enables the home domain and disables the system one, so Installer.app never
# asks for an administrator password; the payload lands in ~/Library/Application Support/Zaelar (where install.sh
# puts it), and `postinstall` runs that same install.sh to register the LaunchAgent. `BundleIsRelocatable=false`:
# otherwise Installer "upgrades" any other copy of com.zaelar.daemon it finds on the disk instead of this path.
build_pkg() {   # <app> <output .pkg> [installer identity]
  local app="$1" out="$2" identity="${3:-}"
  local root="$WORK/pkgroot" scripts="$WORK/pkgscripts" plist="$WORK/component.plist"
  rm -rf "$root" "$scripts"; mkdir -p "$root" "$scripts"
  ditto "$app" "$root/Zaelar.app"
  cp "$HERE/pkg/postinstall" "$scripts/postinstall"
  cp "$HERE/install.sh" "$scripts/install.sh"
  chmod 0755 "$scripts/postinstall" "$scripts/install.sh"
  pkgbuild --analyze --root "$root" "$plist" >/dev/null
  /usr/libexec/PlistBuddy -c "Set :0:BundleIsRelocatable false" "$plist"
  pkgbuild --root "$root" --component-plist "$plist" --identifier "$PKG_ID" --version "$VERSION" \
           --install-location "/Library/Application Support/Zaelar" --scripts "$scripts" \
           "$WORK/component.raw.pkg" >/dev/null
  # `pkgbuild` always writes `auth="root"`, which makes Installer ask for an administrator even for a home-folder
  # install. The component is expanded, marked `auth="none"`, and flattened again — the only way to say it.
  rm -rf "$WORK/component.x"
  pkgutil --expand "$WORK/component.raw.pkg" "$WORK/component.x"
  sed -i '' 's/auth="root"/auth="none"/' "$WORK/component.x/PackageInfo"
  rm -f "$WORK/component.pkg" "$WORK/component.raw.pkg"
  pkgutil --flatten "$WORK/component.x" "$WORK/component.pkg"
  cat > "$WORK/distribution.xml" <<EOF
<?xml version="1.0" encoding="utf-8"?>
<installer-gui-script minSpecVersion="2">
  <title>Zaelar</title>
  <domains enable_anywhere="false" enable_currentUserHome="true" enable_localSystem="false"/>
  <options customize="never" require-scripts="false" hostArchitectures="$ARCH"/>
  <choices-outline><line choice="default"><line choice="$PKG_ID"/></line></choices-outline>
  <choice id="default"/>
  <choice id="$PKG_ID" visible="false"><pkg-ref id="$PKG_ID"/></choice>
  <pkg-ref id="$PKG_ID" version="$VERSION" onConclusion="none">component.pkg</pkg-ref>
</installer-gui-script>
EOF
  if [[ -n "$identity" ]]; then
    productbuild --distribution "$WORK/distribution.xml" --package-path "$WORK" \
                 --sign "$identity" --keychain "$KEYCHAIN" --timestamp "$out" >/dev/null
  else
    productbuild --distribution "$WORK/distribution.xml" --package-path "$WORK" "$out" >/dev/null
  fi
}

check_pkg() {   # <pkg> — the shape every published package must have
  local pkg="$1" x="$WORK/expanded"
  rm -rf "$x"
  pkgutil --expand-full "$pkg" "$x"
  [[ -x "$x/component.pkg/Payload/Zaelar.app/Contents/MacOS/zaelar-daemon" ]] || die "the package carries no Zaelar.app"
  [[ -x "$x/component.pkg/Scripts/postinstall" ]] || die "the package carries no postinstall"
  [[ -f "$x/component.pkg/Scripts/install.sh" ]] || die "the package carries no install.sh"
  grep -q 'enable_currentUserHome="true"' "$x/Distribution" || die "the package is not a current-user install"
  grep -q 'enable_localSystem="false"' "$x/Distribution" || die "the package could ask for an administrator"
  grep -q 'relocatable="false"' "$x/component.pkg/PackageInfo" || die "the bundle is relocatable: Installer could update another copy"
  grep -q 'auth="none"' "$x/component.pkg/PackageInfo" || die "the package would ask for an administrator"
  say "package shape ok: current-user install, Zaelar.app + postinstall"
}

# Gatekeeper's verdict must NAME notarization: "accepted" alone is also what a machine with assessments switched
# off prints. On such a runner (`spctl --status` says disabled) the stapled ticket, validated just before, is the
# proof instead — said with a warning, never silently.
gatekeeper() {   # <execute|install> <path>
  if (( DRY )); then printf '+ spctl --assess --type %s --verbose=2 %s\n' "$1" "$2"; return 0; fi
  local verdict
  if spctl --status 2>/dev/null | grep -q 'assessments enabled'; then
    verdict="$(spctl --assess --type "$1" --verbose=2 "$2" 2>&1)" || die "Gatekeeper rejects $(basename "$2"): $verdict"
    grep -q 'source=Notarized Developer ID' <<<"$verdict" || die "Gatekeeper accepts $(basename "$2") but not as notarized: $verdict"
    say "Gatekeeper: $(basename "$2") accepted, notarized Developer ID"
  else
    printf '::warning::Gatekeeper assessments are disabled on this runner; %s is proven by its stapled ticket\n' "$(basename "$2")"
  fi
}

if [[ "$MODE" == "check" ]]; then
  mkdir -p "$OUT"
  build_pkg "$APP" "$OUT/Zaelar-$SUFFIX.unsigned.pkg"
  check_pkg "$OUT/Zaelar-$SUFFIX.unsigned.pkg"
  exit 0
fi
[[ "$MODE" == "sign" ]] || die "unknown mode $MODE"

WITH_PKG=0
if [[ -n "${APPLE_DEVID_INSTALLER_P12:-}" && -n "${APPLE_DEVID_INSTALLER_P12_PASSWORD:-}" ]]; then WITH_PKG=1; fi
if (( DRY )); then
  APPLE_TEAM_ID="${APPLE_TEAM_ID:-DRYRUNTEAM}"
else
  for name in APPLE_DEVID_APP_P12 APPLE_DEVID_APP_P12_PASSWORD NOTARY_KEY_P8 NOTARY_KEY_ID NOTARY_ISSUER APPLE_TEAM_ID; do
    [[ -n "${!name:-}" ]] || die "$name is not set — it is needed to sign and notarize"
  done
fi

# ── 1. import ────────────────────────────────────────────────────────────────────────────────────────────────
phase "import"
umask 077
KEYCHAIN="$WORK/zaelar-signing.keychain-db"
KC_PASSWORD="$(uuidgen)"
run security create-keychain -p "$KC_PASSWORD" "$KEYCHAIN"
run security set-keychain-settings -lut 3600 "$KEYCHAIN"
run security unlock-keychain -p "$KC_PASSWORD" "$KEYCHAIN"
import_p12() {   # <secret var> <password var> <tool…> — decoded to a 0600 temp file, imported, deleted
  local blob="$1" pass="$2"; shift 2
  local file="$WORK/identity.p12" tools=()
  for tool in "$@"; do tools+=(-T "$tool"); done
  if (( DRY )); then printf '+ security import <%s> -k %s -f pkcs12 %s\n' "$blob" "$KEYCHAIN" "${tools[*]}"; return 0; fi
  printf '%s' "${!blob}" | base64 --decode > "$file"
  security import "$file" -k "$KEYCHAIN" -P "${!pass}" -f pkcs12 "${tools[@]}" >/dev/null
  rm -f "$file"
}
import_p12 APPLE_DEVID_APP_P12 APPLE_DEVID_APP_P12_PASSWORD /usr/bin/codesign
if (( WITH_PKG )); then
  import_p12 APPLE_DEVID_INSTALLER_P12 APPLE_DEVID_INSTALLER_P12_PASSWORD /usr/bin/productbuild /usr/bin/pkgbuild
fi
run security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k "$KC_PASSWORD" "$KEYCHAIN"
if (( ! DRY )); then
  while IFS= read -r line; do
    line="${line#"${line%%[![:space:]]*}"}"; line="${line%\"}"; line="${line#\"}"
    [[ -n "$line" ]] && SEARCH_LIST+=("$line")
  done < <(security list-keychains -d user)
fi
run security list-keychains -d user -s "$KEYCHAIN" ${SEARCH_LIST[@]+"${SEARCH_LIST[@]}"}
if (( DRY )); then
  APP_ID="Developer ID Application: DRY RUN ($APPLE_TEAM_ID)"
  INSTALLER_ID="Developer ID Installer: DRY RUN ($APPLE_TEAM_ID)"
else
  APP_ID="$(security find-identity -v -p codesigning "$KEYCHAIN" | sed -n 's/.*"\(Developer ID Application: .*\)".*/\1/p' | head -n 1)"
  INSTALLER_ID="$(security find-identity -v "$KEYCHAIN" | sed -n 's/.*"\(Developer ID Installer: .*\)".*/\1/p' | head -n 1)"
fi
[[ -n "$APP_ID" ]] || die "no Developer ID Application identity in APPLE_DEVID_APP_P12"
[[ "$APP_ID" == *"($APPLE_TEAM_ID)" ]] || die "the application certificate is not from team APPLE_TEAM_ID"
if (( WITH_PKG )); then
  [[ -n "$INSTALLER_ID" ]] || die "no Developer ID Installer identity in APPLE_DEVID_INSTALLER_P12"
  [[ "$INSTALLER_ID" == *"($APPLE_TEAM_ID)" ]] || die "the installer certificate is not from team APPLE_TEAM_ID"
  say "identities loaded for team *** (application + installer)"
else
  say "identities loaded for team *** (application only: this release carries no .pkg)"
fi

# ── 2. sign inside-out ───────────────────────────────────────────────────────────────────────────────────────
phase "sign"
sign() {   # <path> [entitlements]
  local args=(--force --options runtime --timestamp --sign "$APP_ID")
  (( DRY )) || args+=(--keychain "$KEYCHAIN")
  [[ -n "${2:-}" ]] && args+=(--entitlements "$2")
  run codesign "${args[@]}" "$1"
}
count=0
while IFS= read -r file; do
  if file -b "$file" | grep -q 'Mach-O'; then
    if [[ "$(basename "$file")" == "node" ]]; then sign "$file" "$ENTITLEMENTS_NODE"; else sign "$file"; fi
    count=$((count + 1))
  fi
done < <(find "$APP/Contents" -type f ! -path '*/_CodeSignature/*' | deepest_first)
# Nested bundles are sealed as bundles too, deepest first, then the app itself. `find -type d` skips the
# `Resources/Python.framework` SYMLINK, so the framework is signed once, where it really is.
while IFS= read -r bundle; do sign "$bundle"; done \
  < <(find "$APP/Contents" -type d \( -name '*.framework' -o -name '*.app' \) | deepest_first)
sign "$APP"
say "signed $count Mach-O files and the bundle (hardened runtime, secure timestamp)"

# ── 3. verify what was signed ────────────────────────────────────────────────────────────────────────────────
phase "verify"
run codesign --verify --deep --strict --verbose=2 "$APP"
if (( ! DRY )); then
  TEAM="$(codesign -dv --verbose=2 "$APP" 2>&1 | sed -n 's/^TeamIdentifier=//p')"
  [[ "$TEAM" == "$APPLE_TEAM_ID" ]] || die "the signed bundle's team does not match APPLE_TEAM_ID"
  if [[ "$NOTARY_KEY_P8" == *"BEGIN PRIVATE KEY"* ]]; then
    printf '%s\n' "$NOTARY_KEY_P8" > "$WORK/notary.p8"
  else
    printf '%s' "$NOTARY_KEY_P8" | base64 --decode > "$WORK/notary.p8"
  fi
fi

# ── 4. notarize ──────────────────────────────────────────────────────────────────────────────────────────────
notarize() {   # <file> — refuses anything but Accepted, and prints Apple's log when it is not
  local file="$1" result id status
  phase "notarize $(basename "$file")"
  if (( DRY )); then
    printf '+ xcrun notarytool submit %s --key <NOTARY_KEY_P8> --key-id <NOTARY_KEY_ID> --issuer <NOTARY_ISSUER> --wait --timeout 45m\n' "$file"
    return 0
  fi
  # `|| true`: notarytool exits non-zero on Invalid or a timeout, and under `set -e` that ended the script BEFORE
  # Apple's log was fetched — the one thing that says which binary was refused and why.
  result="$(xcrun notarytool submit "$file" --key "$WORK/notary.p8" --key-id "$NOTARY_KEY_ID" \
            --issuer "$NOTARY_ISSUER" --wait --timeout 45m --output-format json 2>"$WORK/notary.err" || true)"
  id="$(/usr/bin/python3 -c 'import json,sys
try: print(json.loads(sys.argv[1]).get("id", ""))
except Exception: print("")' "$result")"
  status="$(/usr/bin/python3 -c 'import json,sys
try: print(json.loads(sys.argv[1]).get("status", ""))
except Exception: print("")' "$result")"
  if [[ "$status" != "Accepted" ]]; then
    cat "$WORK/notary.err" >&2 || true
    if [[ -n "$id" ]]; then
      xcrun notarytool log "$id" --key "$WORK/notary.p8" --key-id "$NOTARY_KEY_ID" --issuer "$NOTARY_ISSUER" || true
    fi
    die "notarization of $(basename "$file") ended ${status:-without a status}"
  fi
  say "notarized $(basename "$file")"
}
run ditto -c -k --sequesterRsrc --keepParent "$APP" "$WORK/notarize.zip"
notarize "$WORK/notarize.zip"

# ── 5. staple, re-zip ────────────────────────────────────────────────────────────────────────────────────────
phase "staple"
run xcrun stapler staple "$APP"
run rm -f "$OUT/Zaelar.zip"
run ditto -c -k --sequesterRsrc --keepParent "$APP" "$OUT/Zaelar.zip"

# ── 6. assess what a user receives: the published zip, extracted ─────────────────────────────────────────────
phase "assess"
RECEIVED="$WORK/received"
run mkdir -p "$RECEIVED"
run ditto -x -k "$OUT/Zaelar.zip" "$RECEIVED"
run codesign --verify --deep --strict --verbose=2 "$RECEIVED/Zaelar.app"
run xcrun stapler validate "$RECEIVED/Zaelar.app"
gatekeeper execute "$RECEIVED/Zaelar.app"

# ── 7. the installer package ─────────────────────────────────────────────────────────────────────────────────
if (( ! WITH_PKG )); then
  say "Zaelar.zip: Developer ID signed, notarized, stapled (no Installer identity: no .pkg)"
  exit 0
fi
phase "package"
if (( DRY )); then
  printf '+ productbuild --distribution distribution.xml --sign <%s> --timestamp %s\n' "Developer ID Installer" "$OUT/Zaelar.pkg"
else
  build_pkg "$APP" "$OUT/Zaelar.pkg" "$INSTALLER_ID"
fi
run pkgutil --check-signature "$OUT/Zaelar.pkg"
notarize "$OUT/Zaelar.pkg"
phase "staple package"
run xcrun stapler staple "$OUT/Zaelar.pkg"
phase "assess package"
run xcrun stapler validate "$OUT/Zaelar.pkg"
gatekeeper install "$OUT/Zaelar.pkg"
(( DRY )) || check_pkg "$OUT/Zaelar.pkg"
say "Zaelar.zip and Zaelar.pkg: Developer ID signed, notarized, stapled"
