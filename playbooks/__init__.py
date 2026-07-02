"""Playbook registry. A playbook = one incident type, one file, four functions:
detect(conn), diagnose(conn, evidence), propose(conn, diagnosis, evidence),
plus TYPE and SEVERITY constants. Add a file, register it here."""
from . import stuck_import, import_error

PLAYBOOKS = [stuck_import, import_error]
