#!/bin/sh
# Build the app for a connected iPhone, install it and launch it (V2-870 S3: voice on a real device).
#
# Needs: full Xcode with the developer's Apple ID added (Xcode › Settings › Accounts — a free personal team is enough;
# its builds expire after 7 days), the phone connected by cable, trusted, and in Developer Mode.
#
#   ZAELAR_ORIGIN=https://engine.example.org \
#   ZAELAR_ALLOW_NAVIGATION=signin.example.org \
#   TEAM=ABCDE12345 ./scripts/ios-device.sh [device-udid]
#
# TEAM is the team ID shown in Xcode › Settings › Accounts. The bundle id stays com.zaelar.app in the project; a free
# personal team may refuse it (an id is registered to one team), so BUNDLE_ID=com.zaelar.app.dev overrides it for this
# build only — through build settings on the command line, never by editing the project.
# Voice needs an https origin: a plain-http LAN address is not a secure context, so the WebView gives it no microphone.
set -eu
cd "$(dirname "$0")/.."
: "${ZAELAR_ORIGIN:?set ZAELAR_ORIGIN to the engine origin the phone should open (https for voice)}"
: "${TEAM:?set TEAM to your development team ID (Xcode › Settings › Accounts)}"
BUNDLE_ID="${BUNDLE_ID:-com.zaelar.app}"
UDID="${1:-}"
if [ -z "$UDID" ]; then
  JSON="$(mktemp)"
  xcrun devicectl list devices --json-output "$JSON" >/dev/null
  UDID="$(python3 -c 'import json,sys
d=json.load(open(sys.argv[1]))
for x in d.get("result",{}).get("devices",[]):
    h=x.get("hardwareProperties",{}); c=x.get("connectionProperties",{})
    if h.get("platform")=="iOS" and c.get("tunnelState")!="unavailable": print(h.get("udid","")); break' "$JSON")"
  rm -f "$JSON"
fi
[ -n "$UDID" ] || { echo "no connected iPhone found (xcrun devicectl list devices)"; exit 1; }

npx cap sync ios
xcodebuild -project ios/App/App.xcodeproj -scheme App -configuration Debug -destination "id=$UDID" \
  -derivedDataPath ios/DerivedData -allowProvisioningUpdates \
  DEVELOPMENT_TEAM="$TEAM" CODE_SIGN_STYLE=Automatic PRODUCT_BUNDLE_IDENTIFIER="$BUNDLE_ID" build
xcrun devicectl device install app --device "$UDID" ios/DerivedData/Build/Products/Debug-iphoneos/App.app
xcrun devicectl device process launch --device "$UDID" "$BUNDLE_ID"
