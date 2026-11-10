#!/bin/sh
# Archive a store build and export the .ipa (V2-870). Nothing is sent to Apple here — see ios-upload.sh.
#
#   APPLE_TEAM_ID=ABCDE12345 ZAELAR_ORIGIN=https://engine.example.org ZAELAR_APP_LINKS_HOST=engine.example.org \
#   ZAELAR_ALLOW_NAVIGATION=signin.example.org ./scripts/ios-archive.sh [--dry-run]
#
# Needs a PAID Apple Developer team: App Store distribution and the Associated Domains entitlement are refused to a
# free personal team. Automatic signing with -allowProvisioningUpdates creates the distribution certificate and
# profile when the team's account is in Xcode › Settings › Accounts.
# Output: build/Zaelar.xcarchive and build/ipa/App.ipa. --dry-run checks the inputs and prints the commands only.
set -eu
cd "$(dirname "$0")/.."
DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1
fail() { echo "ios-archive: $*" >&2; exit 1; }
[ -n "${APPLE_TEAM_ID:-}" ] || fail "APPLE_TEAM_ID is not set (the paid team's ID, Xcode › Settings › Accounts)"
[ -n "${ZAELAR_ORIGIN:-}" ] || fail "ZAELAR_ORIGIN is not set (the https engine origin the app opens)"
case "$ZAELAR_ORIGIN" in https://*) ;; *) fail "ZAELAR_ORIGIN must be https for a store build";; esac
[ -n "${ZAELAR_APP_LINKS_HOST:-}" ] || fail "ZAELAR_APP_LINKS_HOST is not set (the host whose universal links open the app)"

# Optional: an App Store Connect API key lets -allowProvisioningUpdates create the certificate and the profile without
# an Xcode account signed in (ASC_KEY_ID, ASC_ISSUER_ID, ASC_KEY_P8 = path to the .p8 — names only, never values).
AUTH=""
if [ -n "${ASC_KEY_P8:-}" ]; then
  [ -n "${ASC_KEY_ID:-}" ] && [ -n "${ASC_ISSUER_ID:-}" ] || fail "ASC_KEY_P8 is set: ASC_KEY_ID and ASC_ISSUER_ID are needed too"
  AUTH="-authenticationKeyPath $ASC_KEY_P8 -authenticationKeyID $ASC_KEY_ID -authenticationKeyIssuerID $ASC_ISSUER_ID"
fi
ARCHIVE=build/Zaelar.xcarchive
ENT=ios/App/App/App.entitlements
OPTS=build/ExportOptions.plist
run() { echo "+ $*"; [ "$DRY" = 1 ] || "$@"; }

run sh scripts/version.sh
run npx cap sync ios
echo "+ render $ENT and $OPTS"
if [ "$DRY" = 0 ]; then
  mkdir -p build
  sed "s/__APP_LINKS_HOST__/$ZAELAR_APP_LINKS_HOST/g" ios/App/App/App.entitlements.template > "$ENT"
  cat > "$OPTS" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>method</key><string>app-store-connect</string>
  <key>destination</key><string>export</string>
  <key>teamID</key><string>$APPLE_TEAM_ID</string>
  <key>signingStyle</key><string>automatic</string>
  <key>manageAppVersionAndBuildNumber</key><false/>
  <key>uploadSymbols</key><true/>
</dict></plist>
PLIST
fi
run xcodebuild -project ios/App/App.xcodeproj -scheme App -configuration Release -destination 'generic/platform=iOS' \
  -archivePath "$ARCHIVE" -derivedDataPath ios/DerivedData -allowProvisioningUpdates \
  DEVELOPMENT_TEAM="$APPLE_TEAM_ID" CODE_SIGN_STYLE=Automatic CODE_SIGN_ENTITLEMENTS=App/App.entitlements archive
run xcodebuild -exportArchive -archivePath "$ARCHIVE" -exportOptionsPlist "$OPTS" -exportPath build/ipa \
  -allowProvisioningUpdates
[ "$DRY" = 1 ] && echo "dry run: inputs OK, nothing built" || echo "archived: $ARCHIVE · ipa: build/ipa/App.ipa"
