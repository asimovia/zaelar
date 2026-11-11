#!/bin/sh
# Archive a store build and export the .ipa (V2-870). Nothing is sent to Apple here — see ios-upload.sh.
#
#   APPLE_TEAM_ID=ABCDE12345 ZAELAR_ORIGIN=https://engine.example.org ZAELAR_ALLOW_NAVIGATION=signin.example.org \
#   [ZAELAR_APP_LINKS_HOST=engine.example.org] [ZAELAR_SIGN=manual] ./scripts/ios-archive.sh [--dry-run]
#
# Needs a PAID Apple Developer team (App Store distribution and Associated Domains are refused to a personal team).
# Two ways to sign:
#   · automatic (default): Xcode's account, or an App Store Connect API key (ASC_KEY_ID, ASC_ISSUER_ID, ASC_KEY_P8 =
#     path to the .p8 — names only) with a role that may use cloud-managed distribution certificates;
#   · ZAELAR_SIGN=manual: the certificate, its key and the «Zaelar App Store» profile made in the developer portal and
#     saved in ZAELAR_SIGN_DIR (scripts/manual-signing.sh) — archived with Apple Distribution from the start.
# ZAELAR_APP_LINKS_HOST is optional: with it the Associated Domains entitlement is signed in (the App ID must have the
# capability); without it the build carries no entitlements file.
# Output: build/Zaelar.xcarchive and build/ipa/App.ipa. --dry-run checks the inputs and prints the commands only.
set -eu
cd "$(dirname "$0")/.."
DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1
fail() { echo "ios-archive: $*" >&2; exit 1; }
[ -n "${APPLE_TEAM_ID:-}" ] || fail "APPLE_TEAM_ID is not set (the paid team's ID)"
[ -n "${ZAELAR_ORIGIN:-}" ] || fail "ZAELAR_ORIGIN is not set (the https engine origin the app opens)"
case "$ZAELAR_ORIGIN" in https://*) ;; *) fail "ZAELAR_ORIGIN must be https for a store build";; esac
MODE="${ZAELAR_SIGN:-automatic}"
case "$MODE" in automatic|manual) ;; *) fail "ZAELAR_SIGN must be automatic or manual";; esac
AUTH=""
if [ -n "${ASC_KEY_P8:-}" ]; then
  [ -n "${ASC_KEY_ID:-}" ] && [ -n "${ASC_ISSUER_ID:-}" ] || fail "ASC_KEY_P8 is set: ASC_KEY_ID and ASC_ISSUER_ID are needed too"
  AUTH="-authenticationKeyPath $ASC_KEY_P8 -authenticationKeyID $ASC_KEY_ID -authenticationKeyIssuerID $ASC_ISSUER_ID"
fi
ARCHIVE=build/Zaelar.xcarchive
OPTS=build/ExportOptions.plist
ENT_SETTING=""
run() { echo "+ $*"; [ "$DRY" = 1 ] || "$@"; }

run sh scripts/version.sh
run npx cap sync ios
mkdir -p build
if [ -n "${ZAELAR_APP_LINKS_HOST:-}" ]; then
  echo "+ render ios/App/App/App.entitlements (applinks/webcredentials: $ZAELAR_APP_LINKS_HOST)"
  [ "$DRY" = 1 ] || sed "s/__APP_LINKS_HOST__/$ZAELAR_APP_LINKS_HOST/g" ios/App/App/App.entitlements.template > ios/App/App/App.entitlements
  ENT_SETTING="CODE_SIGN_ENTITLEMENTS=App/App.entitlements"
fi

if [ "$MODE" = manual ]; then
  . scripts/manual-signing.sh
  manual_signing "${ZAELAR_SIGN_PROFILE:-Zaelar App Store}" || fail "manual signing could not be prepared"
  SIGN_ARGS="CODE_SIGN_STYLE=Manual"
  EXPORT_SIGNING="<key>signingStyle</key><string>manual</string>
  <key>signingCertificate</key><string>Apple Distribution</string>
  <key>provisioningProfiles</key><dict><key>com.zaelar.app</key><string>$SIGN_PROFILE</string></dict>"
else
  SIGN_ARGS="CODE_SIGN_STYLE=Automatic"
  EXPORT_SIGNING="<key>signingStyle</key><string>automatic</string>"
fi
echo "+ render $OPTS ($MODE signing)"
[ "$DRY" = 1 ] || cat > "$OPTS" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>method</key><string>app-store-connect</string>
  <key>destination</key><string>export</string>
  <key>teamID</key><string>$APPLE_TEAM_ID</string>
  $EXPORT_SIGNING
  <key>manageAppVersionAndBuildNumber</key><false/>
  <key>uploadSymbols</key><true/>
</dict></plist>
PLIST

if [ "$MODE" = manual ]; then
  # shellcheck disable=SC2086
  run xcodebuild -project ios/App/App.xcodeproj -scheme App -configuration Release -destination 'generic/platform=iOS' \
    -archivePath "$ARCHIVE" -derivedDataPath ios/DerivedData DEVELOPMENT_TEAM="$APPLE_TEAM_ID" $SIGN_ARGS \
    CODE_SIGN_IDENTITY="$SIGN_IDENTITY" PROVISIONING_PROFILE_SPECIFIER="$SIGN_PROFILE" \
    OTHER_CODE_SIGN_FLAGS="--keychain ${SIGN_KEYCHAIN:-}" $ENT_SETTING archive
  run xcodebuild -exportArchive -archivePath "$ARCHIVE" -exportOptionsPlist "$OPTS" -exportPath build/ipa
else
  # shellcheck disable=SC2086
  run xcodebuild -project ios/App/App.xcodeproj -scheme App -configuration Release -destination 'generic/platform=iOS' \
    -archivePath "$ARCHIVE" -derivedDataPath ios/DerivedData -allowProvisioningUpdates $AUTH \
    DEVELOPMENT_TEAM="$APPLE_TEAM_ID" $SIGN_ARGS $ENT_SETTING archive
  # shellcheck disable=SC2086
  run xcodebuild -exportArchive -archivePath "$ARCHIVE" -exportOptionsPlist "$OPTS" -exportPath build/ipa \
    -allowProvisioningUpdates $AUTH
fi
[ "$DRY" = 1 ] && echo "dry run: inputs OK, nothing built" || echo "archived: $ARCHIVE · ipa: build/ipa/App.ipa"
