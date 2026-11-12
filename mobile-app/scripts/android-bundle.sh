#!/bin/sh
# Build the store bundle (.aab), signed with the UPLOAD key (V2-870). Nothing is sent to Google here.
#
#   ZAELAR_ORIGIN=https://engine.example.org [ZAELAR_ALLOW_NAVIGATION=signin.example.org] \
#   ANDROID_UPLOAD_KEYSTORE=/path/upload.jks ANDROID_UPLOAD_KEYSTORE_PASSWORD=… [ANDROID_UPLOAD_KEY_ALIAS=upload] \
#   [ANDROID_UPLOAD_KEY_PASSWORD=…] [ANDROID_VERSION_CODE=1331] [ANDROID_VERSION_NAME=1.0.0] \
#   ./scripts/android-bundle.sh [--dry-run]
#
# Play App Signing keeps the key that signs what users install; this build is signed with the upload key, which only
# proves to Play that the bundle comes from us (a lost upload key is reset in the console, the app keeps its identity).
# The keystore and its passwords come from the environment — never from a file in a repository.
# versionName = package.json "version" (or ANDROID_VERSION_NAME); versionCode = update/BUILD × 10 unless ANDROID_VERSION_CODE is set
# (app/build.gradle). Output: build/aab/Zaelar-<version>-<code>.aab. --dry-run checks the inputs and prints the commands.
set -eu
cd "$(dirname "$0")/.."
DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1
fail() { echo "android-bundle: $*" >&2; exit 1; }
[ -n "${ZAELAR_ORIGIN:-}" ] || fail "ZAELAR_ORIGIN is not set (the https engine origin the app opens)"
case "$ZAELAR_ORIGIN" in https://*) ;; *) fail "ZAELAR_ORIGIN must be https for a store build";; esac
[ -n "${ANDROID_UPLOAD_KEYSTORE:-}" ] || fail "ANDROID_UPLOAD_KEYSTORE is not set (path to the upload keystore)"
[ -f "$ANDROID_UPLOAD_KEYSTORE" ] || fail "no keystore at $ANDROID_UPLOAD_KEYSTORE"
[ -n "${ANDROID_UPLOAD_KEYSTORE_PASSWORD:-}" ] || fail "ANDROID_UPLOAD_KEYSTORE_PASSWORD is not set"
SDK="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-}}"
[ -n "$SDK" ] && [ -d "$SDK" ] || fail "ANDROID_HOME is not set (the Android SDK folder)"
run() { echo "+ $*"; [ "$DRY" = 1 ] || "$@"; }

VERSION="${ANDROID_VERSION_NAME:-$(node -p "require('./package.json').version")}"
CODE="${ANDROID_VERSION_CODE:-$(awk '{printf "%d", $1 * 10}' ../update/BUILD)}"
OUT="build/aab/Zaelar-$VERSION-$CODE.aab"
echo "+ sdk.dir=$SDK → android/local.properties"
[ "$DRY" = 1 ] || echo "sdk.dir=$SDK" > android/local.properties
run npx cap sync android
run sh -c "cd android && ./gradlew --quiet clean bundleRelease"
run mkdir -p build/aab
run cp android/app/build/outputs/bundle/release/app-release.aab "$OUT"
if [ "$DRY" = 0 ]; then
  JARSIGNER="$(/usr/libexec/java_home 2>/dev/null)/bin/jarsigner"
  [ -x "$JARSIGNER" ] || JARSIGNER=jarsigner
  "$JARSIGNER" -verify "$OUT" >/dev/null 2>&1 || fail "$OUT is not signed — check the upload key variables"
fi
echo "bundle $VERSION ($CODE) → $OUT"
