#!/bin/sh
# Build the app for a real iPhone and install it on the connected one (V2-870 S3: voice on a real device).
#
# Needs: full Xcode with the developer's Apple ID added (Xcode › Settings › Accounts — a free personal team is enough;
# its builds expire after 7 days), the phone connected by cable, paired, and in Developer Mode.
#
#   ZAELAR_ORIGIN=https://engine.example.org \
#   ZAELAR_ALLOW_NAVIGATION=signin.example.org \
#   TEAM=ABCDE12345 ./scripts/ios-device.sh [device-id]
#
# · The build targets `generic/platform=iOS`, not the device itself, so it needs no device-support files for the
#   phone's iOS version (a phone newer than this Xcode still installs).
# · Installing goes through `devicectl`; the app is then opened by tapping its icon (no debugger attached).
# · TEAM is the team ID in Xcode › Settings › Accounts. The project keeps com.zaelar.app; a free personal team may
#   refuse it (an id belongs to one team), so BUNDLE_ID=com.zaelar.app.dev overrides it for this build only — build
#   settings on the command line, the project file is never edited.
# · ZAELAR_SIGN=manual signs with the portal's development certificate and «Zaelar Dev» profile instead of an Xcode
#   account (scripts/manual-signing.sh); LAUNCH=1 opens the app after installing (needs the phone's developer image).
# · device-id: the CoreDevice identifier or UDID from `xcrun devicectl list devices`; default: the first paired iPhone.
# · Voice needs an https origin: a plain-http LAN address is not a secure context, so the WebView gives it no mic.
set -eu
cd "$(dirname "$0")/.."
: "${ZAELAR_ORIGIN:?set ZAELAR_ORIGIN to the engine origin the phone should open (https for voice)}"
: "${TEAM:?set TEAM to your development team ID (Xcode › Settings › Accounts)}"
BUNDLE_ID="${BUNDLE_ID:-com.zaelar.app}"
DEVICE="${1:-}"
if [ -z "$DEVICE" ]; then
  JSON="$(mktemp)"
  xcrun devicectl list devices --json-output "$JSON" >/dev/null
  DEVICE="$(python3 -c 'import json,sys
for x in json.load(open(sys.argv[1])).get("result",{}).get("devices",[]):
    if x.get("hardwareProperties",{}).get("platform")=="iOS" and x.get("connectionProperties",{}).get("pairingState")=="paired":
        print(x.get("identifier","")); break' "$JSON")"
  rm -f "$JSON"
fi
[ -n "$DEVICE" ] || { echo "no paired iPhone found (xcrun devicectl list devices)"; exit 1; }

npx cap sync ios
if [ "${ZAELAR_SIGN:-automatic}" = manual ]; then
  # The development certificate and the «Zaelar Dev» profile from the portal (scripts/manual-signing.sh); the device
  # must be in that profile.
  . scripts/manual-signing.sh
  manual_signing "${ZAELAR_SIGN_PROFILE:-Zaelar Dev}" || exit 1
  xcodebuild -project ios/App/App.xcodeproj -scheme App -configuration Debug -destination 'generic/platform=iOS' \
    -derivedDataPath ios/DerivedData DEVELOPMENT_TEAM="$TEAM" CODE_SIGN_STYLE=Manual \
    CODE_SIGN_IDENTITY="$SIGN_IDENTITY" PROVISIONING_PROFILE_SPECIFIER="$SIGN_PROFILE" \
    OTHER_CODE_SIGN_FLAGS="--keychain $SIGN_KEYCHAIN" PRODUCT_BUNDLE_IDENTIFIER="$BUNDLE_ID" build
else
  xcodebuild -project ios/App/App.xcodeproj -scheme App -configuration Debug -destination 'generic/platform=iOS' \
    -derivedDataPath ios/DerivedData -allowProvisioningUpdates \
    DEVELOPMENT_TEAM="$TEAM" CODE_SIGN_STYLE=Automatic PRODUCT_BUNDLE_IDENTIFIER="$BUNDLE_ID" build
fi
xcrun devicectl device install app --device "$DEVICE" ios/DerivedData/Build/Products/Debug-iphoneos/App.app
[ "${LAUNCH:-0}" = 1 ] && xcrun devicectl device process launch --device "$DEVICE" "$BUNDLE_ID" || true
echo "Installed $BUNDLE_ID on $DEVICE — open it from the home screen. A free team's app must be trusted once:"
echo "Settings › General › VPN & Device Management › your Apple ID › Trust."
