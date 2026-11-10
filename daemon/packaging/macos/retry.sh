# Retries for the calls that cross Apple's network (sourced by sign_and_notarize.sh).
#
# `stapler staple` / `stapler validate` fetch or check the ticket on Apple's CloudKit service, and a dropped
# connection there (NSURLErrorDomain -1005, exit 68) fails a release whose notarization was already ACCEPTED.
# `notarytool submit --wait` can lose its connection the same way. Neither is a verdict on the bytes, so they are
# tried again with a growing pause; a real verdict ("Invalid", "Rejected") is never retried.
#
# The pauses are RETRY_DELAYS (seconds): one retry per entry, after the first attempt. ZAELAR_RETRY_DELAYS
# overrides them (the tests set it to zeros).
# shellcheck shell=bash

read -r -a RETRY_DELAYS <<< "${ZAELAR_RETRY_DELAYS:-15 30 60 90 120}"

# retry <what> <command...> — run it; on failure wait the next pause and run it again; give up after the last.
# Under --dry-run (DRY=1) it prints the command as `run` does and the retry policy on the line after it.
retry() {
  local what="$1"; shift
  local max=$(( ${#RETRY_DELAYS[@]} + 1 )) attempt=1 rc
  if (( ${DRY:-0} )); then
    printf '+ %s\n' "$*"
    printf '  ↻ %s: up to %d attempts, pauses %s s\n' "$what" "$max" "${RETRY_DELAYS[*]}"
    return 0
  fi
  while :; do
    printf '  ↻ %s: attempt %d/%d\n' "$what" "$attempt" "$max"
    rc=0
    "$@" || rc=$?
    (( rc == 0 )) && return 0
    if (( attempt >= max )); then
      printf '  ✗ %s: failed %d times (last exit %d)\n' "$what" "$max" "$rc" >&2
      return "$rc"
    fi
    printf '  ↻ %s: exit %d, retrying in %ss\n' "$what" "$rc" "${RETRY_DELAYS[attempt-1]}" >&2
    sleep "${RETRY_DELAYS[attempt-1]}"
    attempt=$(( attempt + 1 ))
  done
}

# transient <stderr file> — true when what a failed Apple call printed is a network failure, not a verdict.
transient() {
  grep -Eiq 'NSURLErrorDomain|network connection (was lost|appears to be offline)|timed out|could not connect|connection (reset|refused)|HTTP status code:? *5[0-9][0-9]|service unavailable|-100[0-9]' "$1" 2>/dev/null
}
