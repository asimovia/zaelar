#!/bin/sh
# Upload the archive made by ios-archive.sh to App Store Connect (→ TestFlight), with an App Store Connect API key.
#
#   ASC_KEY_ID=… ASC_ISSUER_ID=… ASC_KEY_P8=/path/AuthKey_….p8 APPLE_TEAM_ID=… ./scripts/ios-upload.sh [--dry-run]
#
# Uses `xcodebuild -exportArchive` with `destination: upload` — the upload path Xcode itself uses (altool's upload is
# deprecated). The key's values never appear in this repo: only these variable NAMES. --dry-run checks and prints.
set -eu
cd "$(dirname "$0")/.."
DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1
fail() { echo "ios-upload: $*" >&2; exit 1; }
for v in ASC_KEY_ID ASC_ISSUER_ID ASC_KEY_P8 APPLE_TEAM_ID; do
  eval "val=\${$v:-}"; [ -n "$val" ] || fail "$v is not set"
done
[ "$DRY" = 1 ] || [ -f "$ASC_KEY_P8" ] || fail "ASC_KEY_P8 does not point to a .p8 file"
ARCHIVE=build/Zaelar.xcarchive
[ "$DRY" = 1 ] || [ -d "$ARCHIVE" ] || fail "no $ARCHIVE — run scripts/ios-archive.sh first"
OPTS=build/ExportOptions-upload.plist
echo "+ render $OPTS"
if [ "$DRY" = 0 ]; then
  cat > "$OPTS" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>method</key><string>app-store-connect</string>
  <key>destination</key><string>upload</string>
  <key>teamID</key><string>$APPLE_TEAM_ID</string>
  <key>signingStyle</key><string>automatic</string>
  <key>manageAppVersionAndBuildNumber</key><false/>
</dict></plist>
PLIST
fi
echo "+ xcodebuild -exportArchive -archivePath $ARCHIVE -exportOptionsPlist $OPTS -exportPath build/upload -allowProvisioningUpdates -authenticationKeyPath \$ASC_KEY_P8 -authenticationKeyID \$ASC_KEY_ID -authenticationKeyIssuerID \$ASC_ISSUER_ID"
[ "$DRY" = 1 ] && { echo "dry run: inputs OK, nothing uploaded"; exit 0; }
xcodebuild -exportArchive -archivePath "$ARCHIVE" -exportOptionsPlist "$OPTS" -exportPath build/upload \
  -allowProvisioningUpdates -authenticationKeyPath "$ASC_KEY_P8" -authenticationKeyID "$ASC_KEY_ID" \
  -authenticationKeyIssuerID "$ASC_ISSUER_ID"
echo "uploaded — the build appears in App Store Connect › TestFlight after processing"
