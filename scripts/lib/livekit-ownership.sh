# LiveKit ownership helpers for scripts/run-livekit.sh (sourced; also unit-tested by sourcing it).
#
# The class of bug: a restart that does not WAIT for the previous livekit-server to be fully gone. LiveKit
# drains gracefully on SIGTERM ("waiting for participants to exit") and keeps its UDP/TCP ports (7881/7882)
# while it does. The new server then dies on "bind: address already in use", the readiness probe on 7880
# answers from the DYING old one, and when it finishes draining voice is dead and nothing relaunches it.
# Rule: whoever starts LiveKit owns it — reap the old one until it is really gone (SIGKILL past a deadline),
# and keep checking that the one we started is the one alive.

# lk_reap_old <pgrep-pattern> [term_wait_s=8] [kill_wait_s=4]
# SIGTERM every match, wait for them to vanish, SIGKILL the stragglers. Returns 0 when none is left, 1 otherwise.
lk_reap_old() {
  local pat="$1" term_wait="${2:-8}" kill_wait="${3:-4}" pids i
  pids="$(pgrep -f "$pat" 2>/dev/null || true)"
  [[ -z "$pids" ]] && return 0
  for p in $pids; do kill "$p" 2>/dev/null || true; done
  for ((i = 0; i < term_wait * 4; i++)); do
    pgrep -f "$pat" >/dev/null 2>&1 || return 0
    sleep 0.25
  done
  for p in $(pgrep -f "$pat" 2>/dev/null || true); do kill -9 "$p" 2>/dev/null || true; done
  for ((i = 0; i < kill_wait * 4; i++)); do
    pgrep -f "$pat" >/dev/null 2>&1 || return 0
    sleep 0.25
  done
  return 1
}

# lk_alive <pid> — the livekit-server WE started is still running.
lk_alive() { [[ -n "${1:-}" ]] && kill -0 "$1" 2>/dev/null; }
