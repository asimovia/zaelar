#!/usr/bin/env bash
# Developer ID signing, notarization and the installer package for Zaelar.app (V2-869 §5).
#
#   sign_and_notarize.sh sign  <Zaelar.app> <dist dir> <suffix>   identity sign, notarize, staple, re-zip, .pkg
#   sign_and_notarize.sh check <Zaelar.app> <work dir> <suffix>   build the .pkg UNSIGNED and check its structure
#
# WHO RUNS THIS. The release workflow, on a macOS runner, and only when the identity secrets exist — otherwise the
# workflow skips it with a visible "unsigned: identity secrets absent" notice and publishes the ad hoc build exactly
# as before. `check` runs on every build, so the package's SHAPE is proven long before an identity exists to sign it.
#
# WHAT IT READS (environment; values are never printed — GitHub masks them, and nothing here uses `set -x`):
#   APPLE_DEVID_APP_P12 / _PASSWORD          the "Developer ID Application" certificate (.p12, base64)
#   APPLE_DEVID_INSTALLER_P12 / _PASSWORD    the "Developer ID Installer" certificate (.p12, base64)
#   NOTARY_KEY_P8, NOTARY_KEY_ID, NOTARY_ISSUER   an App Store Connect API key for `notarytool`
#   APPLE_TEAM_ID                            the team both certificates must belong to
#
# THE ORDER, and why:
#   1. a throwaway keychain (deleted on exit, whatever happens) holds the two identities;
#   2. every Mach-O inside the bundle is signed INSIDE-OUT with the hardened runtime and a secure timestamp, then
#      the bundle itself — not `codesign --deep` for signing: Apple documents `--deep` as a verification aid, and
#      it applies one set of options to nested code it never inspected;
#   3. `codesign --verify --deep --strict` and the team identifier must equal APPLE_TEAM_ID;
#   4. notarize the app (zip → `notarytool submit --wait`), refuse anything but "Accepted", staple the ticket into
#      the bundle, and re-zip it — so `Zaelar-<suffix>.zip`, the file the one-line installer and the auto-update use,
#      carries a notarized, stapled app;
#   5. build `Zaelar.pkg` (current-user install, no administrator), sign it with the Installer identity, notarize
#      and staple it too: the file a person double-clicks, which Gatekeeper accepts without a warning.
# The sums, the Sigstore signature and the update manifest are computed AFTER this, over these final bytes.
set -euo pipefail

MODE="${1:?usage: sign_and_notarize.sh sign|check <Zaelar.app> <dir> <suffix>}"
APP="${2:?}"
OUT="${3:?}"
SUFFIX="${4:?}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG_ID="com.zaelar.daemon.pkg"

say() { printf '  %s\n' "$*"; }
die() { printf '✗ %s\n' "$*" >&2; exit 1; }

[[ -x "$APP/Contents/MacOS/zaelar-daemon" ]] || die "$APP is not a Zaelar.app"
VERSION="$(/usr/bin/plutil -extract CFBundleShortVersionString raw "$APP/Contents/Info.plist")"
case "$SUFFIX" in
  macos) ARCH="arm64" ;;
  macos-x86_64) ARCH="x86_64" ;;
  *) die "unknown suffix $SUFFIX" ;;
esac

WORK="$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/zaelar-sign.XXXXXX")"
KEYCHAIN=""
cleanup() {
  if [[ -n "$KEYCHAIN" ]]; then security delete-keychain "$KEYCHAIN" >/dev/null 2>&1 || true; fi
  rm -rf "$WORK"
}
trap cleanup EXIT

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

if [[ "$MODE" == "check" ]]; then
  mkdir -p "$OUT"
  build_pkg "$APP" "$OUT/Zaelar-$SUFFIX.unsigned.pkg"
  check_pkg "$OUT/Zaelar-$SUFFIX.unsigned.pkg"
  exit 0
fi
[[ "$MODE" == "sign" ]] || die "unknown mode $MODE"

for name in APPLE_DEVID_APP_P12 APPLE_DEVID_APP_P12_PASSWORD APPLE_DEVID_INSTALLER_P12 \
            APPLE_DEVID_INSTALLER_P12_PASSWORD NOTARY_KEY_P8 NOTARY_KEY_ID NOTARY_ISSUER APPLE_TEAM_ID; do
  [[ -n "${!name:-}" ]] || die "$name is not set — every identity secret is needed to sign"
done

# ── 1. the throwaway keychain ────────────────────────────────────────────────────────────────────────────────
KEYCHAIN="$WORK/zaelar-signing.keychain-db"
KC_PASSWORD="$(uuidgen)"
security create-keychain -p "$KC_PASSWORD" "$KEYCHAIN"
security set-keychain-settings -lut 3600 "$KEYCHAIN"
security unlock-keychain -p "$KC_PASSWORD" "$KEYCHAIN"
umask 077
printf '%s' "$APPLE_DEVID_APP_P12" | base64 --decode > "$WORK/app.p12"
printf '%s' "$APPLE_DEVID_INSTALLER_P12" | base64 --decode > "$WORK/installer.p12"
security import "$WORK/app.p12" -k "$KEYCHAIN" -P "$APPLE_DEVID_APP_P12_PASSWORD" -f pkcs12 \
  -T /usr/bin/codesign >/dev/null
security import "$WORK/installer.p12" -k "$KEYCHAIN" -P "$APPLE_DEVID_INSTALLER_P12_PASSWORD" -f pkcs12 \
  -T /usr/bin/productbuild -T /usr/bin/pkgbuild >/dev/null
rm -f "$WORK/app.p12" "$WORK/installer.p12"
security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k "$KC_PASSWORD" "$KEYCHAIN" >/dev/null
# shellcheck disable=SC2046
security list-keychains -d user -s "$KEYCHAIN" $(security list-keychains -d user | tr -d '"')
APP_ID="$(security find-identity -v -p codesigning "$KEYCHAIN" | sed -n 's/.*"\(Developer ID Application: .*\)".*/\1/p' | head -n 1)"
INSTALLER_ID="$(security find-identity -v "$KEYCHAIN" | sed -n 's/.*"\(Developer ID Installer: .*\)".*/\1/p' | head -n 1)"
[[ -n "$APP_ID" ]] || die "no Developer ID Application identity in APPLE_DEVID_APP_P12"
[[ -n "$INSTALLER_ID" ]] || die "no Developer ID Installer identity in APPLE_DEVID_INSTALLER_P12"
[[ "$APP_ID" == *"($APPLE_TEAM_ID)" ]] || die "the application certificate is not from team APPLE_TEAM_ID"
[[ "$INSTALLER_ID" == *"($APPLE_TEAM_ID)" ]] || die "the installer certificate is not from team APPLE_TEAM_ID"
say "identities loaded for team ***"

# ── 2. sign inside-out ───────────────────────────────────────────────────────────────────────────────────────
ENTITLEMENTS="$HERE/entitlements.plist"
sign() { codesign --force --options runtime --timestamp --entitlements "$ENTITLEMENTS" \
                  --keychain "$KEYCHAIN" --sign "$APP_ID" "$1"; }
count=0
while IFS= read -r -d '' file; do
  if file -b "$file" | grep -q 'Mach-O'; then sign "$file"; count=$((count + 1)); fi
done < <(find "$APP/Contents" -type f \( -perm -u+x -o -name '*.dylib' -o -name '*.so' \) -print0 | sort -rz)
# Nested bundles (frameworks) are sealed as bundles too, deepest first, then the app itself.
while IFS= read -r -d '' bundle; do sign "$bundle"; done \
  < <(find "$APP/Contents" -depth -type d \( -name '*.framework' -o -name '*.app' \) -print0)
sign "$APP"
say "signed $count Mach-O files and the bundle (hardened runtime, secure timestamp)"

# ── 3. verify what was signed ────────────────────────────────────────────────────────────────────────────────
codesign --verify --deep --strict --verbose=2 "$APP"
TEAM="$(codesign -dv --verbose=2 "$APP" 2>&1 | sed -n 's/^TeamIdentifier=//p')"
[[ "$TEAM" == "$APPLE_TEAM_ID" ]] || die "the signed bundle's team does not match APPLE_TEAM_ID"

# ── 4. notarize, staple, re-zip ──────────────────────────────────────────────────────────────────────────────
if [[ "$NOTARY_KEY_P8" == *"BEGIN PRIVATE KEY"* ]]; then
  printf '%s\n' "$NOTARY_KEY_P8" > "$WORK/notary.p8"
else
  printf '%s' "$NOTARY_KEY_P8" | base64 --decode > "$WORK/notary.p8"
fi
notarize() {   # <file> — refuses anything but Accepted, and prints Apple's log when it is not
  local file="$1" result id status
  result="$(xcrun notarytool submit "$file" --key "$WORK/notary.p8" --key-id "$NOTARY_KEY_ID" \
            --issuer "$NOTARY_ISSUER" --wait --timeout 45m --output-format json)"
  id="$(printf '%s' "$result" | /usr/bin/python3 -c 'import json,sys; print(json.load(sys.stdin).get("id",""))')"
  status="$(printf '%s' "$result" | /usr/bin/python3 -c 'import json,sys; print(json.load(sys.stdin).get("status",""))')"
  if [[ "$status" != "Accepted" ]]; then
    xcrun notarytool log "$id" --key "$WORK/notary.p8" --key-id "$NOTARY_KEY_ID" --issuer "$NOTARY_ISSUER" || true
    die "notarization of $(basename "$file") ended $status"
  fi
  say "notarized $(basename "$file")"
}
ditto -c -k --sequesterRsrc --keepParent "$APP" "$WORK/notarize.zip"
notarize "$WORK/notarize.zip"
xcrun stapler staple "$APP"
xcrun stapler validate "$APP"
spctl --assess --type execute --verbose=2 "$APP"
rm -f "$OUT/Zaelar.zip"
ditto -c -k --sequesterRsrc --keepParent "$APP" "$OUT/Zaelar.zip"

# ── 5. the installer package ─────────────────────────────────────────────────────────────────────────────────
build_pkg "$APP" "$OUT/Zaelar.pkg" "$INSTALLER_ID"
pkgutil --check-signature "$OUT/Zaelar.pkg"
notarize "$OUT/Zaelar.pkg"
xcrun stapler staple "$OUT/Zaelar.pkg"
spctl --assess --type install --verbose=2 "$OUT/Zaelar.pkg"
check_pkg "$OUT/Zaelar.pkg"
say "Zaelar.zip and Zaelar.pkg: Developer ID signed, notarized, stapled"
