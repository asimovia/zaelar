#!/usr/bin/env bash
# One line, and the daemon is installed (V2-575 · P4).
#
#   curl -fsSL https://raw.githubusercontent.com/asimovia/zaelar/main/daemon/packaging/get.sh | bash
#
# WHY A TERMINAL COMMAND IS THE MAIN PATH, and not a download button. Quarantine on macOS is set by whatever
# WROTE the file — a browser marks it, `curl` does not — so a file that arrives this way is never held by
# Gatekeeper and the user is never shown a dialog they have to know how to dismiss. That is the whole
# difference between "it installs" and "it looks like a virus", and it costs nothing: no Apple account, no
# notarization queue, no approval that takes weeks to arrive and has to be renewed.
#
# ⚠️ IT DOES NOT TRUST THE DOWNLOAD BLINDLY. Piping a script into a shell is exactly as safe as the origin it
# came from and no safer, so: this script is fetched over https from the repository it belongs to, the binary
# is fetched from that repository's own release, and its SHA-256 is checked against the `SHA256SUMS-*` the
# build published beside it — before anything is executed.
#
# WHAT IS PROVEN, EXACTLY. The hash alone is two files agreeing: it catches a corrupt download, NOT a release
# whose binary and sums were both replaced. That is what the signature is for. The build signs the sums with
# Sigstore keyless — the signer is the release workflow's GitHub identity, the signature is in the public Rekor
# log — so when `cosign` is on PATH this script verifies `SHA256SUMS-*.sigstore.json` against that identity and
# REFUSES to install on a bad or missing signature. Then a passing install means: these bytes are the ones the
# `daemon-artifacts.yml` workflow of asimovia/zaelar built and signed for a release tag. What it does NOT mean:
# that anybody reviewed the code. Apple vouches for it only when the release carries a notarized `.pkg` (preferred
# whenever the signed sums list one; `install.sh` asks Gatekeeper about it). Without `cosign`, only the hash is
# checked and the script says so. With `minisign`, the signed update manifest must list the same bytes too.
# A fork that publishes its own releases sets ZAELAR_DAEMON_SIGNER_RE to its own workflow's identity.
#
# NO SUDO. Anywhere. If this script ever needs an administrator password, something is wrong with it.
set -euo pipefail

REPO="${ZAELAR_DAEMON_REPO:-asimovia/zaelar}"
RAW_BASE="${ZAELAR_DAEMON_RAW_BASE:-https://raw.githubusercontent.com/$REPO/main/daemon/packaging}"

say()  { printf '  %s\n' "$*"; }
die()  { printf '✗ %s\n' "$*" >&2; exit 1; }

[[ "$(uname -s)" == "Darwin" ]] || die "this installer is for macOS. On Windows run the PowerShell one-liner instead."
command -v curl >/dev/null 2>&1 || die "curl is required and is not on PATH."

# ── which build is for this Mac ───────────────────────────────────────────────────────────────────────────
# ⚠️ APPLE SILICON AND INTEL ARE DIFFERENT BINARIES and there is no such thing as a build that runs on both:
# a PyInstaller bundle carries a real interpreter compiled for one architecture. Getting this wrong does not
# degrade, it fails with "bad CPU type in executable", which reads like a broken download.
# The macOS build is the `Zaelar.app` bundle (menu-bar icon, bundled browser driver), published zipped.
case "$(uname -m)" in
  arm64)  SUFFIX="macos" ;;
  x86_64) SUFFIX="macos-x86_64" ;;
  *)      die "unsupported architecture: $(uname -m)" ;;
esac
ASSET="Zaelar-$SUFFIX.zip"

# ── which release: the daemon's OWN line first ─────────────────────────────────────────────────────────────
# The daemon is released on its own tags, `daemon-vX.Y.Z`; engine releases (`v*`) once carried daemon builds too, and
# "the newest release that carries the file" then installed an engine build over a newer, signed daemon release.
# The order (the same as `daemon/update/release_line.py`, node 7.129):
#   1. the `daemon-vX.Y.Z` tags — ALL of them, through `git/matching-refs`, so a daemon release never sinks below the
#      first page of the releases listing — newest VERSION first, the first whose release publishes "$ASSET";
#   2. only when none does, the newest release of any kind (the API lists newest first) that publishes it.
# Anchored on the closing quote, so the Apple Silicon name never matches the Intel one. Drafts are never listed to an
# anonymous caller, and a prerelease is skipped.
API="https://api.github.com/repos/$REPO"
carries() {   # <release json on stdin> — true when that release publishes exactly "$ASSET" and is not a prerelease
  local body; body="$(cat)"
  grep -Eq '"prerelease"[[:space:]]*:[[:space:]]*true' <<<"$body" && return 1
  grep -q "\"browser_download_url\"[[:space:]]*:[[:space:]]*\"[^\"]*/releases/download/[^/\"]*/$ASSET\"" <<<"$body"
}
daemon_tags() {   # every daemon-vX.Y.Z tag, newest version first
  curl -fsSL "$API/git/matching-refs/tags/daemon-v" 2>/dev/null \
    | grep -Eo '"refs/tags/daemon-v[0-9]+\.[0-9]+\.[0-9]+"' | tr -d '"' | sed 's#^refs/tags/##' \
    | sed 's/^daemon-v//' | sort -t. -k1,1nr -k2,2nr -k3,3nr | sed 's/^/daemon-v/' || true
}
resolve_tag() {
  local tag tried=0
  for tag in $(daemon_tags); do
    (( tried++ < 5 )) || break
    if curl -fsSL "$API/releases/tags/$tag" 2>/dev/null | carries; then printf '%s\n' "$tag"; return 0; fi
  done
  curl -fsSL "$API/releases?per_page=100" 2>/dev/null \
    | grep -o "\"browser_download_url\"[[:space:]]*:[[:space:]]*\"[^\"]*/releases/download/[^/\"]*/$ASSET\"" \
    | head -n 1 | sed 's#.*/releases/download/\([^/]*\)/.*#\1#' || true
}
TAG="${ZAELAR_DAEMON_TAG:-$(resolve_tag)}"
# Releases cut before the `.app` publish the single-file program instead. Until one carries the bundle, the newest
# that carries the old file is installed — the same daemon, without the menu-bar icon and the bundled browser.
if [[ -z "$TAG" ]]; then
  ASSET="zaelar-daemon-$SUFFIX"
  TAG="$(resolve_tag)"
fi
[[ -n "$TAG" ]] || die "could not find a published daemon release. Set ZAELAR_DAEMON_TAG to install a specific one."
case "$TAG" in
  daemon-v*) PICKED="the daemon's release line" ;;
  *)         PICKED="no daemon-v* release carries $ASSET — an older engine release that does" ;;
esac
[[ -n "${ZAELAR_DAEMON_TAG:-}" ]] && PICKED="ZAELAR_DAEMON_TAG"
BASE="https://github.com/$REPO/releases/download/$TAG"

printf '\nZaelar Local Daemon · %s · %s\n' "$TAG" "$(uname -m)"
say "release: $TAG ($PICKED)"
printf '\n'

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# Each architecture publishes its OWN checksum file: one `SHA256SUMS-macos` holding both would mean two
# jobs writing one name into a flattened release, and the second would win.
SUMS="SHA256SUMS-$SUFFIX"
curl -fsSL -o "$WORK/SHA256SUMS" "$BASE/$SUMS" || die "could not download $SUMS."

# ── the signature over the sums, when this Mac can check it ──────────────────────────────────────────────
# Checked BEFORE the hash, because the hash is only as good as the sums file it is compared with.
SIGNER_RE="${ZAELAR_DAEMON_SIGNER_RE:-^https://github.com/asimovia/zaelar/\.github/workflows/daemon-artifacts\.yml@refs/tags/}"
OIDC_ISSUER="https://token.actions.githubusercontent.com"
if command -v cosign >/dev/null 2>&1; then
  say "checking the signature…"
  # A missing bundle is a refusal, not a skip: whoever can replace the binary and the sums can also delete the
  # signature, so "no signature" must never quietly mean "fine".
  curl -fsSL -o "$WORK/SHA256SUMS.sigstore.json" "$BASE/$SUMS.sigstore.json" \
    || die "$TAG publishes no signature for $SUMS. Releases before signing have none — install a newer one, or uninstall cosign to install with the hash check only."
  if ! VERIFY_OUT="$(cosign verify-blob \
        --bundle "$WORK/SHA256SUMS.sigstore.json" \
        --certificate-identity-regexp "$SIGNER_RE" \
        --certificate-oidc-issuer "$OIDC_ISSUER" \
        "$WORK/SHA256SUMS" 2>&1)"; then
    die "the signature on $SUMS does not verify — it was not signed by the release workflow. Nothing was installed.
    $VERIFY_OUT"
  fi
  say "signature ok — signed by the release workflow"
else
  say "signature not checked (no cosign) — by hand: cosign verify-blob --bundle $SUMS.sigstore.json --certificate-identity-regexp '$SIGNER_RE' --certificate-oidc-issuer $OIDC_ISSUER $SUMS"
fi

# ── the notarized installer package, when this release has one ───────────────────────────────────────────
# A release cut after the publisher's Apple identity existed also carries `Zaelar-<suffix>.pkg`: the same app,
# Developer ID signed, notarized and stapled, which `install.sh` hands to Gatekeeper before using it. The SIGNED sums
# say whether it exists — a release without an identity lists only the zip, and the zip is installed exactly as before.
if [[ "$ASSET" == *.zip ]] && grep -Eq "^[0-9a-f]{64}[[:space:]]+Zaelar-$SUFFIX\.pkg$" "$WORK/SHA256SUMS"; then
  ASSET="Zaelar-$SUFFIX.pkg"
fi
say "downloading ${ASSET}…"
curl -fsSL -o "$WORK/$ASSET" "$BASE/$ASSET" || die "could not download $ASSET from $TAG."

# ── verify before anything is executed ────────────────────────────────────────────────────────────────────
# The order matters: the hash is checked while the file is still an inert blob in a temp directory, before it
# is made executable, moved anywhere, or handed to launchd.
say "checking the download…"
EXPECTED="$(sed -n "s/^\([0-9a-f]\{64\}\)[[:space:]]\{1,\}$ASSET$/\1/p" "$WORK/SHA256SUMS" | head -n 1)"
[[ -n "$EXPECTED" ]] || die "$ASSET is not listed in the published checksums for $TAG."
ACTUAL="$(shasum -a 256 "$WORK/$ASSET" | awk '{print $1}')"
[[ "$ACTUAL" == "$EXPECTED" ]] || die "checksum mismatch — the file that arrived is not the file that was built.
    expected $EXPECTED
    got      $ACTUAL"
say "checksum ok"

# ── the signed update manifest, when this Mac can check it ───────────────────────────────────────────────────
# The release also publishes `update-manifest.json` + `.minisig` — what an INSTALLED daemon updates from, signed with
# a key that is never in the release. With `minisign` on PATH, the manifest is verified against the PUBLIC key from
# this script's own origin (the repository's `main`, never the release) and must list the exact bytes that arrived.
# A release without a manifest (older) or without its signature (cut before the key existed) is skipped and said so;
# a manifest that does not verify, or does not list this file, is a refusal.
KEY_URL="${ZAELAR_DAEMON_UPDATE_KEY_URL:-${RAW_BASE%/packaging}/update/PUBLIC_KEY}"
if command -v minisign >/dev/null 2>&1; then
  if curl -fsSL -o "$WORK/update-manifest.json" "$BASE/update-manifest.json" 2>/dev/null; then
    if curl -fsSL -o "$WORK/update-manifest.json.minisig" "$BASE/update-manifest.json.minisig" 2>/dev/null; then
      curl -fsSL -o "$WORK/update-key.pub" "$KEY_URL" || die "could not download the update public key."
      minisign -V -q -p "$WORK/update-key.pub" -m "$WORK/update-manifest.json" >/dev/null 2>&1 \
        || die "the update manifest of $TAG does not verify against the published key. Nothing was installed."
      grep -q "\"$ACTUAL\"" "$WORK/update-manifest.json" \
        || die "the signed update manifest of $TAG does not list the file that arrived. Nothing was installed."
      say "update manifest ok — signed, and it lists this file"
    else
      say "update manifest not checked — $TAG publishes it unsigned"
    fi
  else
    say "update manifest not checked — $TAG publishes none"
  fi
fi

# ── install with the same script the repository ships ─────────────────────────────────────────────────────
# Fetched from `main` rather than from the release, deliberately: it then shares this script's origin exactly,
# so the trust decision the user already made by running this line is the only one being made.
say "installing…"
curl -fsSL -o "$WORK/install.sh" "$RAW_BASE/macos/install.sh" || die "could not download the installer."
[[ "$ASSET" == *.zip || "$ASSET" == *.pkg ]] || chmod +x "$WORK/$ASSET"
bash "$WORK/install.sh" "$WORK/$ASSET"

# ⚠️ `| bash --purge` DOES NOT WORK and looks like it should: the option is read by bash, not by the script,
# and bash answers with its own usage text. Anybody who wants the destructive variant will type the obvious
# thing first, so the obvious thing has to be the one printed.
printf '\n  To remove it later:\n'
printf '    curl -fsSL %s/macos/uninstall.sh | bash\n' "$RAW_BASE"
printf '    curl -fsSL %s/macos/uninstall.sh | bash -s -- --purge   # and forget the folders you chose\n\n' "$RAW_BASE"
