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
# that anybody reviewed the code, or that Apple or Microsoft vouch for it — the binary carries no Developer ID
# or Authenticode signature (a later step). Without `cosign`, only the hash is checked and the script says so.
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

# ── the newest release that CARRIES THIS FILE ──────────────────────────────────────────────────────────────
# Not `releases/latest` (an engine release whose daemon build is still running, or failed, has no daemon
# assets yet) and not a tag prefix either: the daemon is rebuilt on every engine tag, so a prefix-filtered
# `daemon-v*` tag sinks below the first page of the API within weeks, the filter finds nothing, and the
# one-liner dies on a perfectly healthy repository. The rule is the asset itself: the newest release (the API
# lists newest first) that publishes exactly "$ASSET" — anchored on the closing quote, so the Apple Silicon
# name never matches the Intel one.
resolve_tag() {
  curl -fsSL "https://api.github.com/repos/$REPO/releases?per_page=100" 2>/dev/null \
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
BASE="https://github.com/$REPO/releases/download/$TAG"

printf '\nZaelar Local Daemon · %s · %s\n\n' "$TAG" "$(uname -m)"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

say "downloading ${ASSET}…"
curl -fsSL -o "$WORK/$ASSET" "$BASE/$ASSET" || die "could not download $ASSET from $TAG."
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

# ── install with the same script the repository ships ─────────────────────────────────────────────────────
# Fetched from `main` rather than from the release, deliberately: it then shares this script's origin exactly,
# so the trust decision the user already made by running this line is the only one being made.
say "installing…"
curl -fsSL -o "$WORK/install.sh" "$RAW_BASE/macos/install.sh" || die "could not download the installer."
[[ "$ASSET" == *.zip ]] || chmod +x "$WORK/$ASSET"
bash "$WORK/install.sh" "$WORK/$ASSET"

# ⚠️ `| bash --purge` DOES NOT WORK and looks like it should: the option is read by bash, not by the script,
# and bash answers with its own usage text. Anybody who wants the destructive variant will type the obvious
# thing first, so the obvious thing has to be the one printed.
printf '\n  To remove it later:\n'
printf '    curl -fsSL %s/macos/uninstall.sh | bash\n' "$RAW_BASE"
printf '    curl -fsSL %s/macos/uninstall.sh | bash -s -- --purge   # and forget the folders you chose\n\n' "$RAW_BASE"
