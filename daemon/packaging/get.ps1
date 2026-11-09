# One line, and the daemon is installed (V2-575 · P4).
#
#   irm https://raw.githubusercontent.com/asimovia/zaelar/main/daemon/packaging/get.ps1 | iex
#
# WHY A TERMINAL COMMAND IS THE MAIN PATH, and not a download button. The Mark of the Web is written by
# whatever SAVED the file — a browser stamps it, `Invoke-WebRequest` does not — so a file that arrives this
# way never triggers the SmartScreen "Windows protected your PC" panel, which is the single biggest reason an
# install of an unsigned tool gets abandoned. No Microsoft account, no code-signing certificate, no reputation
# to build up over months.
#
# ⚠️ IT DOES NOT TRUST THE DOWNLOAD BLINDLY. Piping a script into `iex` is exactly as safe as its origin and
# no safer, so: this script comes over https from the repository it belongs to, the binary comes from that
# repository's own release, and its SHA-256 is compared with the `SHA256SUMS-windows` the build published
# beside it — before anything is executed.
#
# WHAT IS PROVEN, EXACTLY. The hash alone is two files agreeing: it catches a corrupt download, NOT a release
# whose binary and sums were both replaced. That is what the signature is for. The build signs the sums with
# Sigstore keyless — the signer is the release workflow's GitHub identity, the signature is in the public Rekor
# log — so when `cosign` is on PATH this script verifies `SHA256SUMS-windows.sigstore.json` against that
# identity and REFUSES to install on a bad or missing signature. A passing install then means: these bytes are
# the ones the `daemon-artifacts.yml` workflow of asimovia/zaelar built and signed for a release tag. It does
# NOT mean anybody reviewed the code, nor that Microsoft vouches for it — the .exe carries no Authenticode
# signature (a later step). Without `cosign`, only the hash is checked and the script says so. A fork that
# publishes its own releases sets ZAELAR_DAEMON_SIGNER_RE to its own workflow's identity.
#
# NO ADMINISTRATOR. Anywhere.
$ErrorActionPreference = 'Stop'

$Repo    = if ($env:ZAELAR_DAEMON_REPO)     { $env:ZAELAR_DAEMON_REPO }     else { 'asimovia/zaelar' }
$RawBase = if ($env:ZAELAR_DAEMON_RAW_BASE) { $env:ZAELAR_DAEMON_RAW_BASE } else { "https://raw.githubusercontent.com/$Repo/main/daemon/packaging" }

function Say($m) { Write-Host "  $m" }
function Die($m) { Write-Host "X $m" -ForegroundColor Red; exit 1 }

if (-not $IsWindows -and $PSVersionTable.PSVersion.Major -ge 6) {
  Die 'this installer is for Windows. On macOS run the curl one-liner instead.'
}

# TLS 1.2 for Windows PowerShell 5.1, whose default still refuses github.com on some builds — the failure is
# an opaque "could not create SSL/TLS secure channel" that sends people hunting for a proxy problem.
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}

# ── the newest release that CARRIES THIS FILE ────────────────────────────────────────────────────────────
# Not `releases/latest` (an engine release whose daemon build is still running, or failed, has no daemon
# assets yet) and not a tag prefix either: the daemon is rebuilt on every engine tag, so a prefix-filtered
# `daemon-v*` tag sinks below the first page of the API within weeks and the one-liner dies on a healthy
# repository. The rule is the asset itself: the newest release that publishes exactly this file.
$Asset = 'zaelar-daemon-windows.exe'
$Tag = $env:ZAELAR_DAEMON_TAG
if (-not $Tag) {
  try {
    $releases = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases?per_page=100" `
                                  -Headers @{ 'User-Agent' = 'zaelar-daemon-get' }
    $Tag = ($releases | Where-Object { @($_.assets | ForEach-Object { $_.name }) -contains $Asset } | Select-Object -First 1).tag_name
  } catch { }
}
if (-not $Tag) { Die 'could not find a published daemon release. Set ZAELAR_DAEMON_TAG to install a specific one.' }

$Base  = "https://github.com/$Repo/releases/download/$Tag"
Write-Host ''
Write-Host "Zaelar Local Daemon · $Tag"
Write-Host ''

$Work = Join-Path ([IO.Path]::GetTempPath()) ("zaelar-daemon-" + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $Work -Force | Out-Null
try {
  Say "downloading $Asset…"
  Invoke-WebRequest -Uri "$Base/$Asset" -OutFile (Join-Path $Work $Asset) -UseBasicParsing
  Invoke-WebRequest -Uri "$Base/SHA256SUMS-windows" -OutFile (Join-Path $Work 'SHA256SUMS') -UseBasicParsing

  # ── the signature over the sums, when this PC can check it ──────────────────────────────────────────────
  # Checked BEFORE the hash, because the hash is only as good as the sums file it is compared with.
  $SignerRe = if ($env:ZAELAR_DAEMON_SIGNER_RE) { $env:ZAELAR_DAEMON_SIGNER_RE } else { '^https://github.com/asimovia/zaelar/\.github/workflows/daemon-artifacts\.yml@refs/tags/' }
  $OidcIssuer = 'https://token.actions.githubusercontent.com'
  if (Get-Command cosign -ErrorAction SilentlyContinue) {
    Say 'checking the signature…'
    # A missing bundle is a refusal, not a skip: whoever can replace the binary and the sums can also delete
    # the signature, so "no signature" must never quietly mean "fine".
    try {
      Invoke-WebRequest -Uri "$Base/SHA256SUMS-windows.sigstore.json" -OutFile (Join-Path $Work 'SHA256SUMS.sigstore.json') -UseBasicParsing
    } catch {
      Die "$Tag publishes no signature for SHA256SUMS-windows. Releases before signing have none - install a newer one, or remove cosign from PATH to install with the hash check only."
    }
    # ⚠️ cosign reports success on stderr, and Windows PowerShell 5.1 under 'Stop' turns a redirected stderr line
    # into a terminating error — a GOOD signature would abort the install. The exit code is the verdict.
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
      $verifyOut = & cosign verify-blob `
        --bundle (Join-Path $Work 'SHA256SUMS.sigstore.json') `
        --certificate-identity-regexp $SignerRe `
        --certificate-oidc-issuer $OidcIssuer `
        (Join-Path $Work 'SHA256SUMS') 2>&1 | Out-String
      $verifyCode = $LASTEXITCODE
    } finally { $ErrorActionPreference = $previousPreference }
    if ($verifyCode -ne 0) {
      Die "the signature on SHA256SUMS-windows does not verify - it was not signed by the release workflow. Nothing was installed.`n    $verifyOut"
    }
    Say 'signature ok - signed by the release workflow'
  } else {
    Say "signature not checked (no cosign) - by hand: cosign verify-blob --bundle SHA256SUMS-windows.sigstore.json --certificate-identity-regexp '$SignerRe' --certificate-oidc-issuer $OidcIssuer SHA256SUMS-windows"
  }

  # ── verify before anything is executed ──────────────────────────────────────────────────────────────────
  # While the file is still an inert blob in a temp directory: before it is moved, registered with the task
  # scheduler, or started.
  Say 'checking the download…'
  $line = Get-Content (Join-Path $Work 'SHA256SUMS') | Where-Object { $_ -match "\s$([regex]::Escape($Asset))$" } | Select-Object -First 1
  if (-not $line) { Die "$Asset is not listed in the published checksums for $Tag." }
  $expected = ($line -split '\s+')[0].ToLower()
  $actual = (Get-FileHash -Path (Join-Path $Work $Asset) -Algorithm SHA256).Hash.ToLower()
  if ($actual -ne $expected) {
    Die "checksum mismatch - the file that arrived is not the file that was built.`n    expected $expected`n    got      $actual"
  }
  Say 'checksum ok'

  # ── install with the same script the repository ships ───────────────────────────────────────────────────
  # Fetched from `main` rather than from the release, deliberately: it then shares this script's origin
  # exactly, so the trust decision the user already made by running this line is the only one being made.
  Say 'installing…'
  $installer = Join-Path $Work 'install.ps1'
  Invoke-WebRequest -Uri "$RawBase/windows/install.ps1" -OutFile $installer -UseBasicParsing
  & $installer (Join-Path $Work $Asset)

  # `iex` cannot pass an argument to the script it runs, so the destructive variant needs the scriptblock
  # form. Printing only the simple line would leave somebody guessing at a syntax that does not exist.
  Write-Host ''
  Write-Host '  To remove it later:'
  Write-Host "    irm $RawBase/windows/uninstall.ps1 | iex"
  Write-Host "    & ([scriptblock]::Create((irm $RawBase/windows/uninstall.ps1))) -Purge   # and forget the folders you chose"
  Write-Host ''
} finally {
  Remove-Item -Recurse -Force $Work -ErrorAction SilentlyContinue
}
