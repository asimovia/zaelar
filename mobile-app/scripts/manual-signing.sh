#!/bin/sh
# Manual signing for the store and device builds (ZAELAR_SIGN=manual), sourced by ios-archive.sh and ios-device.sh.
#
# For when no Apple account is signed into Xcode: the certificates and profiles were made in the developer portal and
# saved in one folder (ZAELAR_SIGN_DIR, default ~/.zaelar-signing). `manual_signing <profile name>`:
#   · finds the `.mobileprovision` whose Name is <profile name> (e.g. «Zaelar App Store», «Zaelar Dev»);
#   · finds the certificate that profile carries among the folder's `<name>.cer` files and its `<name>.key` (PEM);
#   · builds a .p12 on the fly (random password, 0600, deleted) and imports it into a THROWAWAY keychain — unlocked,
#     with the key partition list set so codesign never waits on a prompt — added to the search list, which is
#     restored and the keychain deleted on exit, whatever happens (the pattern of
#     daemon/packaging/macos/sign_and_notarize.sh);
#   · installs the profile into ~/Library/MobileDevice/Provisioning Profiles/<UUID>.mobileprovision;
#   · sets SIGN_IDENTITY (the certificate's common name), SIGN_PROFILE (the profile's name), SIGN_KEYCHAIN.
# Nothing here prints a key, a password or a certificate body. With DRY=1 it only reports what it found.
SIGN_DIR="${ZAELAR_SIGN_DIR:-$HOME/.zaelar-signing}"

_ms_profile() {   # <name> → path of the profile with that Name, or empty
  for f in "$SIGN_DIR"/*.mobileprovision; do
    [ -f "$f" ] || continue
    n="$(security cms -D -i "$f" 2>/dev/null | plutil -extract Name raw -o - - 2>/dev/null)"
    [ "$n" = "$1" ] && { echo "$f"; return 0; }
  done
  return 1
}

manual_signing() {
  want="$1"
  PROFILE_FILE="$(_ms_profile "$want")" || { echo "manual signing: no profile named «$want» in $SIGN_DIR" >&2; return 1; }
  WORK="$(mktemp -d)"; chmod 700 "$WORK"
  security cms -D -i "$PROFILE_FILE" > "$WORK/profile.plist"
  SIGN_PROFILE="$want"
  PROFILE_UUID="$(plutil -extract UUID raw -o - "$WORK/profile.plist")"
  plutil -extract DeveloperCertificates.0 raw -o - "$WORK/profile.plist" | base64 -D > "$WORK/profile-cert.der"
  CERT=""
  for c in "$SIGN_DIR"/*.cer; do
    [ -f "$c" ] || continue
    openssl x509 -inform DER -in "$c" -outform DER -out "$WORK/cand.der" 2>/dev/null || \
      openssl x509 -in "$c" -outform DER -out "$WORK/cand.der" 2>/dev/null || continue
    cmp -s "$WORK/cand.der" "$WORK/profile-cert.der" && { CERT="$c"; break; }
  done
  [ -n "$CERT" ] || { echo "manual signing: the certificate in «$want» is not among $SIGN_DIR/*.cer" >&2; rm -rf "$WORK"; return 1; }
  KEY="${CERT%.cer}.key"
  [ -f "$KEY" ] || { echo "manual signing: $KEY is missing" >&2; rm -rf "$WORK"; return 1; }
  SIGN_IDENTITY="$(openssl x509 -inform DER -in "$WORK/profile-cert.der" -noout -subject -nameopt multiline \
    | sed -n 's/^ *commonName *= *//p')"
  echo "manual signing: profile «$SIGN_PROFILE» ($PROFILE_UUID), identity «$SIGN_IDENTITY», key $(basename "$KEY")"
  if [ "${DRY:-0}" = 1 ]; then rm -rf "$WORK"; return 0; fi

  P12_PASS="$(openssl rand -hex 16)"; KC_PASS="$(openssl rand -hex 16)"
  openssl x509 -inform DER -in "$WORK/profile-cert.der" -out "$WORK/cert.pem"
  ( umask 077; openssl pkcs12 -export -legacy -inkey "$KEY" -in "$WORK/cert.pem" -out "$WORK/id.p12" \
      -passout "pass:$P12_PASS" -name "$SIGN_IDENTITY" )
  SIGN_KEYCHAIN="$WORK/zaelar-ios.keychain-db"
  OLD_LIST="$(security list-keychains -d user | tr '\n' ' ')"     # quoted entries: a path with spaces survives
  trap 'eval security list-keychains -d user -s "$OLD_LIST" >/dev/null 2>&1; security delete-keychain "$SIGN_KEYCHAIN" >/dev/null 2>&1; rm -rf "$WORK"' EXIT INT TERM
  security create-keychain -p "$KC_PASS" "$SIGN_KEYCHAIN"
  security set-keychain-settings -lut 3600 "$SIGN_KEYCHAIN"
  security unlock-keychain -p "$KC_PASS" "$SIGN_KEYCHAIN"
  security import "$WORK/id.p12" -k "$SIGN_KEYCHAIN" -P "$P12_PASS" -f pkcs12 -T /usr/bin/codesign -T /usr/bin/security >/dev/null
  rm -f "$WORK/id.p12"
  # The intermediate authorities (Xcode's own, then the folder's — e.g. Apple WWDR G3 for Apple Distribution / Development): without the
  # chain the identity is not «valid» and codesign refuses it. A certificate that is already there is skipped.
  # Xcode ships the WWDR intermediates (G3 is `AppleWWDRCA-2030.cer`) — used first, no download needed.
  XCODE_CA="$(xcode-select -p)/../SharedFrameworks/DVTFoundation.framework/Versions/A/Resources"
  for c in "$XCODE_CA"/*.cer "$SIGN_DIR"/*.cer; do
    [ -f "$c" ] && [ "$c" != "$CERT" ] || continue
    security import "$c" -k "$SIGN_KEYCHAIN" >/dev/null 2>&1 || true
  done
  security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k "$KC_PASS" "$SIGN_KEYCHAIN" >/dev/null
  eval security list-keychains -d user -s '"$SIGN_KEYCHAIN"' "$OLD_LIST"
  mkdir -p "$HOME/Library/MobileDevice/Provisioning Profiles"
  cp "$PROFILE_FILE" "$HOME/Library/MobileDevice/Provisioning Profiles/$PROFILE_UUID.mobileprovision"
}
