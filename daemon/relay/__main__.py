"""`python -m daemon.relay <command>` — the relay link from a terminal.

    pair CODE [URL]   redeem a one-time pairing code (the URL only if no relay is configured yet)
    status            is this daemon paired, and with which relay (never prints the credential)
    unpair            forget the credential (the relay URL is kept)
"""
from __future__ import annotations

import json
import sys

from . import config, pair as pairing


def main(argv: list[str]) -> int:
    command = (argv[1] if len(argv) > 1 else "").strip().lower()
    if command == "pair":
        if len(argv) < 3:
            print("usage: python -m daemon.relay pair CODE [RELAY_URL]", file=sys.stderr)
            return 2
        try:
            out = pairing.pair(argv[2], argv[3] if len(argv) > 3 else "")
        except pairing.PairingError as e:
            print(e.message, file=sys.stderr)
            return 1
        print(f"paired{(' with ' + out['account_hint']) if out.get('account_hint') else ''}; "
              "restart the daemon (or use the tray) to connect.")
        return 0
    if command == "status":
        cfg = config.load()
        print(json.dumps({"paired": bool(cfg.get("url") and cfg.get("credential")), "url": cfg.get("url") or "",
                          "account_hint": cfg.get("account_hint") or "", "paired_at": cfg.get("paired_at") or 0},
                         indent=1))
        return 0
    if command == "unpair":
        pairing.unpair()
        print("unpaired")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
