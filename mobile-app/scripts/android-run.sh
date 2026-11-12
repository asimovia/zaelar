#!/bin/sh
# Build a debug app, install it on the running emulator (or the one connected phone) and open it (V2-870).
#
#   [ZAELAR_ORIGIN=http://localhost:43917] [ANDROID_SERIAL=emulator-5554] ./scripts/android-run.sh
#
# Needs a JDK 21 and the Android SDK (ANDROID_HOME, or ANDROID_SDK_ROOT; android/local.properties is written from it).
# A `localhost` origin is the engine on this Mac: `adb reverse` maps the emulator's (or phone's) localhost port to the
# Mac's, so the same origin works for the simulator, the emulator and the desktop — and a plain-http localhost is still
# a secure context, so the WebView gets the microphone.
set -eu
cd "$(dirname "$0")/.."
fail() { echo "android-run: $*" >&2; exit 1; }
SDK="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-}}"
[ -n "$SDK" ] && [ -d "$SDK" ] || fail "ANDROID_HOME is not set (the Android SDK folder)"
ADB="$SDK/platform-tools/adb"
[ -x "$ADB" ] || fail "no adb in $SDK/platform-tools (sdkmanager \"platform-tools\")"
[ "$("$ADB" get-state 2>/dev/null || true)" = device ] || fail "no emulator or phone connected (adb devices)"
echo "sdk.dir=$SDK" > android/local.properties

ORIGIN="${ZAELAR_ORIGIN:-http://localhost:43917}"
export ZAELAR_ORIGIN="$ORIGIN"
npx cap sync android
case "$ORIGIN" in
  http://localhost:*|http://127.0.0.1:*)
    PORT="${ORIGIN##*:}"; PORT="${PORT%%/*}"
    "$ADB" reverse "tcp:$PORT" "tcp:$PORT" >/dev/null && echo "adb reverse tcp:$PORT → this Mac";;
esac
(cd android && ./gradlew --quiet installDebug)
"$ADB" shell am start -n com.zaelar.app/.MainActivity >/dev/null
echo "opened com.zaelar.app on $("$ADB" get-serialno) → $ORIGIN/m"
