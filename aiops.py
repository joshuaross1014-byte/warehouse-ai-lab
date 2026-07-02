"""warehouse-aiops CLI — the human side of the loop.

    python aiops.py seed              # (re)create the mock WMS with faults
    python aiops.py scan              # detect -> diagnose -> propose
    python aiops.py list [STATE]      # incidents
    python aiops.py show INC-0001     # full detail: evidence, diagnosis, proposal
    python aiops.py approve INC-0001  # execute the proposed fix (verified, transactional)
    python aiops.py reject INC-0001 [reason...]
    python aiops.py runbook           # print the runbook
"""
import json
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from core import engine, store
from mock import seed as mock_seed


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "help"

    if cmd == "seed":
        mock_seed.seed()
        print(f"mock WMS seeded with faults: {mock_seed.MOCK_DB}")

    elif cmd == "scan":
        created = engine.scan()
        if not created:
            print("scan clean — no new incidents")
        for inc in created:
            print(f"[{inc.severity.upper():8}] {inc.iid}  {inc.summary}")
            print(f"           root cause: {inc.diagnosis.get('root_cause')}")
            print(f"           proposal ({inc.proposal['kind']}): {inc.proposal['summary']}")
            print(f"           -> review with: python aiops.py show {inc.iid}")

    elif cmd == "list":
        state = argv[1].upper() if len(argv) > 1 else None
        for inc in store.all_incidents(state):
            b = inc.brief()
            print(f"{b['id']}  {b['state']:9} {b['severity']:8} {b['type']:14} {b['summary']}")

    elif cmd == "show" and len(argv) > 1:
        inc = store.get(argv[1])
        print(json.dumps(inc.full(), indent=2) if inc else f"no such incident: {argv[1]}")

    elif cmd == "approve" and len(argv) > 1:
        inc = engine.approve(argv[1])
        print(f"{inc.iid} -> {inc.state}: {inc.resolution}")

    elif cmd == "reject" and len(argv) > 1:
        inc = engine.reject(argv[1], " ".join(argv[2:]))
        print(f"{inc.iid} -> {inc.state}: {inc.resolution}")

    elif cmd == "runbook":
        try:
            print(open(store.RUNBOOK, encoding="utf-8").read())
        except FileNotFoundError:
            print("runbook is empty — no incidents closed yet")

    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
