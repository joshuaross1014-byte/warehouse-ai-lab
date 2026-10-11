"""
guard.py - the read-only gate every SQL statement passes through before it reaches
SQL Server. Sibling of wms-dev-workbench/guard.py, stricter: this agent never writes,
on any server, under any flag.

Rules
    * The statement must start with SELECT or WITH.
    * One statement only: no GO batches, no stacked statements.
    * No write / DDL / EXEC / system-procedure words anywhere in the statement, scanned
      on comment-stripped, string-stripped text so a literal 'update' inside quotes
      does not trip it but a real UPDATE does.
    * No SELECT ... INTO (that creates a table).
The SQL login may well be db_owner; this gate is the control, so keep it strict.
"""
from __future__ import annotations

import re

READ_START = ("SELECT", "WITH")
BLOCKED_WORDS = {
    "INSERT", "UPDATE", "DELETE", "MERGE", "TRUNCATE",
    "DROP", "ALTER", "CREATE", "GRANT", "REVOKE", "DENY",
    "EXEC", "EXECUTE", "BACKUP", "RESTORE", "SHUTDOWN", "KILL", "DBCC",
    "OPENROWSET", "OPENQUERY", "OPENDATASOURCE", "BULK", "RECONFIGURE", "WAITFOR",
    "SP_EXECUTESQL", "XP_CMDSHELL",
}
_comment_block = re.compile(r"/\*.*?\*/", re.S)
_comment_line = re.compile(r"--[^\n]*")
_string_lit = re.compile(r"N?'(?:[^']|'')*'")


class GuardError(Exception):
    """Raised for anything that is not a single read-only SELECT."""


def normalise(sql: str) -> str:
    sql = _comment_block.sub(" ", sql)
    sql = _comment_line.sub(" ", sql)
    sql = _string_lit.sub("''", sql)
    return sql.strip()


def check(sql: str) -> str:
    """Return the normalised statement if it is read-only, else raise GuardError."""
    body = normalise(sql)
    if not body:
        raise GuardError("Empty statement.")
    if re.search(r"^\s*GO\s*$", body, re.M | re.I):
        raise GuardError("GO batches are not allowed; send one statement.")
    inner = body.rstrip().rstrip(";")
    if ";" in inner:
        raise GuardError("Only one statement per call.")
    first = re.match(r"\s*([A-Za-z_]+)", inner)
    first_word = first.group(1).upper() if first else ""
    if first_word not in READ_START:
        raise GuardError(f"Statement must start with SELECT or WITH (got '{first_word}'). This agent is read-only.")
    words = {w.upper() for w in re.findall(r"[A-Za-z_]+", inner)}
    hit = words & BLOCKED_WORDS
    if hit:
        raise GuardError(f"Blocked keyword(s) {sorted(hit)}: this agent is read-only on every server.")
    if "INTO" in words:
        raise GuardError("SELECT ... INTO creates a table; not allowed.")
    if re.search(r"\bxp_\w+", inner, re.I) or re.search(r"\bsp_\w+", inner, re.I):
        raise GuardError("System procedures are not allowed.")
    return inner
