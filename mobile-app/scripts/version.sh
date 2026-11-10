#!/bin/sh
# Stamp the app's version into the Xcode project (run by `npm run sync`):
#   CFBundleShortVersionString = MARKETING_VERSION      ← package.json "version"
#   CFBundleVersion            = CURRENT_PROJECT_VERSION ← the engine's update/BUILD (the number every release moves)
# App Store Connect refuses a second upload with the same CFBundleVersion: to ship a second build on the same engine
# build, set IOS_BUILD (e.g. IOS_BUILD=127.1). The project file only changes when one of the numbers does.
set -eu
cd "$(dirname "$0")/.."
VERSION="$(node -p "require('./package.json').version")"
BUILD="${IOS_BUILD:-$(tr -d '[:space:]' < ../update/BUILD)}"
case "$BUILD" in ''|*[!0-9.]*) echo "version.sh: build number '$BUILD' is not numeric"; exit 1;; esac
PBX=ios/App/App.xcodeproj/project.pbxproj
sed -i.bak -e "s/MARKETING_VERSION = [^;]*;/MARKETING_VERSION = $VERSION;/" \
           -e "s/CURRENT_PROJECT_VERSION = [^;]*;/CURRENT_PROJECT_VERSION = $BUILD;/" "$PBX"
rm -f "$PBX.bak"
echo "version $VERSION ($BUILD)"
