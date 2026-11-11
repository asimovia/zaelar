#!/bin/sh
# Upload the signed .ipa made by ios-archive.sh to App Store Connect (→ TestFlight / review), with an App Store
# Connect API key (any role that may upload builds).
#
#   ASC_KEY_ID=… ASC_ISSUER_ID=… ASC_KEY_P8=/path/AuthKey_….p8 ./scripts/ios-upload.sh [--dry-run]
#
# The .ipa is already signed (automatic or manual — see ios-archive.sh), so the upload only authenticates:
# `xcrun altool --upload-app` with the key's id, its issuer and the PATH to the .p8. Only these variable NAMES appear
# in this repo. --dry-run checks and prints.
set -eu
cd "$(dirname "$0")/.."
DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1
fail() { echo "ios-upload: $*" >&2; exit 1; }
for v in ASC_KEY_ID ASC_ISSUER_ID ASC_KEY_P8; do
  eval "val=\${$v:-}"; [ -n "$val" ] || fail "$v is not set"
done
IPA=build/ipa/App.ipa
if [ "$DRY" = 0 ]; then
  [ -f "$ASC_KEY_P8" ] || fail "ASC_KEY_P8 does not point to a .p8 file"
  [ -f "$IPA" ] || fail "no $IPA — run scripts/ios-archive.sh first"
fi
echo "+ xcrun altool --upload-app -f $IPA -t ios --api-key \$ASC_KEY_ID --api-issuer \$ASC_ISSUER_ID --p8-file-path \$ASC_KEY_P8"
[ "$DRY" = 1 ] && { echo "dry run: inputs OK, nothing uploaded"; exit 0; }
xcrun altool --upload-app -f "$IPA" -t ios --api-key "$ASC_KEY_ID" --api-issuer "$ASC_ISSUER_ID" --p8-file-path "$ASC_KEY_P8"
echo "uploaded — the build appears in App Store Connect › TestFlight after processing"
