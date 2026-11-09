"""`python -m genome <command>` — the genome from the command line (V2-859).

  identity   the generation, hash and languages of the genome on disk
  check      the schema check; exit 1 when the genesis on disk would be refused
  diff       this agent's heritable learned genes that differ from its generation (`--json` for one document)

Offline and read-only: nothing here writes a row or sends anything.
"""
from __future__ import annotations

import json
import sys


def main(argv: list[str]) -> int:
    import genome
    cmd = argv[0] if argv else "identity"
    if cmd == "identity":
        print(json.dumps(genome.identity(), sort_keys=True))
        return 0
    if cmd == "check":
        data = genome._read()
        why = [f"unreadable: {data!r}"] if isinstance(data, Exception) else genome.check(data)
        print("\n".join(why) if why else "ok")
        return 1 if why else 0
    if cmd == "diff":
        from . import diff
        d = diff.diff()
        print(json.dumps(d, sort_keys=True, ensure_ascii=False) if "--json" in argv else diff.render(d))
        return 0
    print(__doc__.strip())
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
