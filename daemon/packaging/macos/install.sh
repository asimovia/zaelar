#!/usr/bin/env bash
# Install (or upgrade) the Zaelar Local Daemon on macOS, for the CURRENT USER ONLY.
#
# NO SUDO, ON PURPOSE. A daemon whose whole job is to read one person's documents has no business running as
# root, and asking for an administrator password is the single biggest reason an install gets abandoned. It
# goes in this user's own Application Support and runs as a per-user LaunchAgent, which means it can never
# reach another account's files even if every check inside it failed at once.
#
# RE-RUNNING IT IS THE UPGRADE PATH. Stop, replace, start — so "deploy a new version" is the same command as
# "install", and there is no second procedure to get wrong. The allowlist and the token live in the state
# directory, which is never touched, so an upgrade keeps the folders the user chose.
#
#   ./install.sh                     use the artifact next to this script, or the newest in dist/
#   ./install.sh /path/to/artifact   use a specific one: Zaelar-macos.pkg (signed + notarized, checked with
#                                    Gatekeeper) / Zaelar-macos.zip / Zaelar.app (the desktop app, with its
#                                    menu-bar icon and its browser driver), or a onefile binary / a .pyz
#
# THE APP is installed as `<prefix>/Zaelar.app` and started by the same LaunchAgent; `<prefix>/bin/zaelar-daemon`
# becomes a two-line launcher into it, so the terminal commands (`status`, `allow`, …) are unchanged.
set -euo pipefail

LABEL="com.zaelar.daemon"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Where everything lands. The default is the platform's own place for this and needs no explanation; the
# override exists because "somewhere else" is a legitimate answer — an encrypted volume, a synced folder
# deliberately avoided, a machine whose home directory is small.
#
#   ZAELAR_DAEMON_PREFIX="/Volumes/Work/Zaelar" ./install.sh
#
# THE STATE FOLLOWS THE PROGRAM, with nothing to configure: the daemon resolves its own root from where its
# binary sits (`<prefix>/bin/<program>` → `<prefix>`, see `daemon/paths.py::_install_root`). So a custom prefix
# moves the token and the folder allowlist with it, launchd needs no environment block, and the DEFAULT prefix
# resolves to exactly where the state has always been. Move the folder and you have moved everything.
PREFIX="${ZAELAR_DAEMON_PREFIX:-$HOME/Library/Application Support/Zaelar}"
BIN_DIR="$PREFIX/bin"
LOG_DIR="$PREFIX/logs"
AGENT="$HOME/Library/LaunchAgents/$LABEL.plist"
TARGET="$BIN_DIR/zaelar-daemon"
APP="$PREFIX/Zaelar.app"

say() { printf '  %s\n' "$*"; }
die() { printf '✗ %s\n' "$*" >&2; exit 1; }

[[ "$(uname -s)" == "Darwin" ]] || die "this installer is for macOS; use windows/install.ps1 on Windows."

# ── find something to install ─────────────────────────────────────────────────────────────────────────────
# The onefile binary is preferred because it carries its own interpreter: nothing else has to be present on the
# machine. The .pyz is the fallback and needs a python3, which is why the check below is a check and not an
# assumption — a launchd job that cannot find its interpreter fails at LOGIN, hours later, with the user
# nowhere near a terminal.
SOURCE="${1:-}"
if [[ -z "$SOURCE" ]]; then
  # The `-macos` names are what a RELEASE asset is called (the two runners would otherwise both claim
  # `zaelar-daemon.pyz` and one would overwrite the other), so a person who downloaded the file from the web and
  # ran this script next to it lands here. Without these four lines that person gets "no artifact found" while
  # the artifact sits in the same folder, which is the most demoralising install failure there is.
  ARCH_SUFFIX="macos"; [[ "$(uname -m)" == "x86_64" ]] && ARCH_SUFFIX="macos-x86_64"
  for candidate in "$HERE/Zaelar-$ARCH_SUFFIX.pkg" "$HOME/Downloads/Zaelar-$ARCH_SUFFIX.pkg" \
                   "$HERE/Zaelar-$ARCH_SUFFIX.zip" "$HOME/Downloads/Zaelar-$ARCH_SUFFIX.zip" \
                   "$HERE/../../../dist/daemon/Zaelar.zip" "$HERE/../../../dist/app/Zaelar.app" \
                   "$HERE/zaelar-daemon-macos" "$HERE/zaelar-daemon-macos.pyz" \
                   "$HERE/zaelar-daemon" "$HERE/zaelar-daemon.pyz" \
                   "$HOME/Downloads/zaelar-daemon-macos" "$HOME/Downloads/zaelar-daemon-macos.pyz" \
                   "$HERE/../../../dist/daemon/zaelar-daemon" "$HERE/../../../dist/daemon/zaelar-daemon.pyz"; do
    [[ -e "$candidate" ]] && { SOURCE="$candidate"; break; }
  done
fi
[[ -n "$SOURCE" && -e "$SOURCE" ]] || die "no artifact found. Build one: python daemon/packaging/build.py"

# ── a notarized installer package: Gatekeeper first, then the app inside it ─────────────────────────────────────
# A `.pkg` is published only Developer-ID-signed and notarized (`sign_and_notarize.sh`), so an unsigned one, or one
# Gatekeeper rejects, is refused rather than installed. The app is taken OUT of the package (`pkgutil --expand-full`,
# no administrator, no Installer.app) and installed exactly like the zip's — one install procedure, not two.
PKG_STAGE=""
if [[ "$SOURCE" == *.pkg ]]; then
  pkgutil --check-signature "$SOURCE" >/dev/null 2>&1 || die "$SOURCE is not signed. Nothing was installed."
  spctl --assess --type install "$SOURCE" >/dev/null 2>&1 \
    || die "Gatekeeper rejects $SOURCE (not notarized, or not by a known developer). Nothing was installed."
  PKG_STAGE="$(mktemp -d)"
  pkgutil --expand-full "$SOURCE" "$PKG_STAGE/x" >/dev/null || die "$SOURCE is not a readable package."
  SOURCE="$(find "$PKG_STAGE/x" -maxdepth 3 -type d -path '*/Payload/Zaelar.app'  | head -n 1)"
  [[ -n "$SOURCE" ]] || die "the package does not contain Zaelar.app."
  say "package ok — signed, and Gatekeeper accepts it"
fi

PYTHON=""
if [[ "$SOURCE" == *.pyz ]]; then
  PYTHON="$(command -v python3 || true)"
  [[ -n "$PYTHON" ]] || die "$SOURCE needs a python3 and there is none on PATH. Install the onefile build instead."
  "$PYTHON" - <<'PY' || die "the python3 on PATH is older than 3.11, which the daemon requires."
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
fi

mkdir -p "$BIN_DIR" "$LOG_DIR" "$(dirname "$AGENT")"

# ── stop whatever is running, so the file can be replaced ─────────────────────────────────────────────────
# `bootout` is the modern verb and `unload` the one that works on older macOS; the daemon may also be running
# from a terminal, which launchd knows nothing about. Every one of these is allowed to fail: "it was not
# running" is a fine outcome for a stop.
if launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1; then
  launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
else
  launchctl unload "$AGENT" >/dev/null 2>&1 || true
fi
sleep 0.5

# ── install the artifact ──────────────────────────────────────────────────────────────────────────────────
# What launchd starts, and the environment it needs. The app's program lives inside the bundle, not in `bin/`, so
# it cannot find its state by where it sits (`daemon/paths.py::_install_root`): the prefix is handed to it instead.
PROGRAM="$TARGET"
ENV_BLOCK=""
PROCESS_TYPE="Background"
if [[ "$SOURCE" == *.zip || "$SOURCE" == *.app ]]; then
  STAGE="$(mktemp -d)"
  trap 'rm -rf "$STAGE" ${PKG_STAGE:+"$PKG_STAGE"}' EXIT
  if [[ "$SOURCE" == *.zip ]]; then
    # `ditto`, which keeps the bundle's symlinks and signature intact; `unzip` does not always.
    ditto -x -k "$SOURCE" "$STAGE" || die "$SOURCE is not a readable archive."
  else
    ditto "$SOURCE" "$STAGE/Zaelar.app"
  fi
  [[ -x "$STAGE/Zaelar.app/Contents/MacOS/zaelar-daemon" ]] || die "$SOURCE does not contain Zaelar.app."
  rm -rf "$APP"
  ditto "$STAGE/Zaelar.app" "$APP"
  # Same consent as below for the single file: the person chose to install THIS bundle.
  xattr -dr com.apple.quarantine "$APP" 2>/dev/null || true
  PROGRAM="$APP/Contents/MacOS/zaelar-daemon"
  printf '#!/bin/sh\nZAELAR_WORKSPACE="${ZAELAR_WORKSPACE:-%s}" exec "%s" "$@"\n' "$PREFIX" "$PROGRAM" > "$TARGET"
  chmod 0755 "$TARGET"
  rm -f "$BIN_DIR/zaelar-daemon.pyz"
  ENV_BLOCK="<key>EnvironmentVariables</key><dict><key>ZAELAR_WORKSPACE</key><string>$PREFIX</string></dict>"
  # A menu-bar app is interactive: `Background` lets the scheduler starve the icon's clicks.
  PROCESS_TYPE="Interactive"
  say "installed Zaelar.app (menu-bar icon, carries its own Python and browser driver)"
elif [[ "$SOURCE" == *.pyz ]]; then
  install -m 0644 "$SOURCE" "$BIN_DIR/zaelar-daemon.pyz"
  # A two-line launcher rather than a shebang: the plist names ONE program, and this keeps the plist identical
  # whichever artifact is installed — so an upgrade from .pyz to onefile does not need a different plist.
  cat > "$TARGET" <<EOF
#!/bin/sh
exec "$PYTHON" "$BIN_DIR/zaelar-daemon.pyz" "\$@"
EOF
  chmod 0755 "$TARGET"
  say "installed the portable build (needs $PYTHON)"
else
  install -m 0755 "$SOURCE" "$TARGET"
  # Gatekeeper quarantines anything that arrived from a browser, and the failure is a dialog the user cannot
  # dismiss into a working state. Clearing the attribute on a file THEY just chose to install is the same
  # consent they already gave; it is not a substitute for signing, which is a release step.
  xattr -d com.apple.quarantine "$TARGET" 2>/dev/null || true
  say "installed the standalone build (carries its own Python)"
fi

# ── register it to start at login ─────────────────────────────────────────────────────────────────────────
# KeepAlive with SuccessfulExit=false: restart it if it dies, but let a deliberate Quit (from the menu bar, an exit
# 0) stay stopped instead of fighting the user. ProcessType asks the scheduler to treat it as what it is.
cat > "$AGENT" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>$PROGRAM</string></array>
  $ENV_BLOCK
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key>
  <dict><key>SuccessfulExit</key><false/></dict>
  <key>ProcessType</key><string>$PROCESS_TYPE</string>
  <key>StandardOutPath</key><string>$LOG_DIR/daemon.log</string>
  <key>StandardErrorPath</key><string>$LOG_DIR/daemon.log</string>
</dict>
</plist>
EOF
chmod 0644 "$AGENT"

if ! launchctl bootstrap "gui/$(id -u)" "$AGENT" 2>/dev/null; then
  launchctl load "$AGENT" 2>/dev/null || die "launchd refused the agent; see $AGENT"
fi

# ── say what happened, and check it rather than assume ────────────────────────────────────────────────────
sleep 1
VERSION="$("$TARGET" version 2>/dev/null || echo "?")"
printf '\n✓ zaelar-daemon %s installed for %s\n' "$VERSION" "$USER"
say "program:  $TARGET"
say "state:    $PREFIX/config/daemon  (the token and the folders you allow)"
say "log:      $LOG_DIR/daemon.log"
say "starts:   at login, and now"
printf '\n'
say "It can read NOTHING until you choose folders — that is the point of the wizard in Zaelar."
say "From a terminal: $TARGET status | allow ~/Documents | deny ~/Documents"
printf '\n'
say "⚠️ The first time it reads ~/Documents, ~/Desktop or ~/Downloads, macOS will ask you to allow it."
say "   That prompt is the operating system's own permission layer, on top of ours. If you miss it,"
say "   grant it under System Settings → Privacy & Security → Files and Folders."
