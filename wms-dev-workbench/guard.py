"""
guard.py - the read-only gate every SQL statement passes through.

Same philosophy as a Claude Code PreToolUse write-guard hook, but enforced in-process:
    * PROD is never writable, regardless of flags.
    * TEST is writable only when WORKBENCH_ALLOW_WRITES=1 AND the caller passes
      allow_write=True (the SQL tab has an explicit checkbox for that).
    * One statement per request. No batches, no GO, no stacked statements.
    * Keyword scan is done on the comment-stripped, string-stripped text so a
      literal like 'update' inside quotes does not trip it, but a real UPDATE does.
"""
from __future__ import annotations

import re

from config import Profile

READ_START = ("SELECT", "WITH")
WRITE_WORDS = {
    "INSERT", "UPDATE", "DELETE", "MERGE", "TRUNCATE",
    "DROP", "ALTER", "CREATE", "GRANT", "REVOKE", "DENY",
    "EXEC", "EXECUTE", "BACKUP", "RESTORE", "SHUTDOWN", "KILL", "DBCC",
    "OPENROWSET", "OPENQUERY", "BULK", "RECONFIGURE", "WAITFOR",
}
_comment_block = re.compile(r"/\*.*?\*/", re.S)
_comment_line = re.compile(r"--[^\n]*")
_string_lit = re.compile(r"N?'(?:[^']|'')*'")


class GuardError(Exception):
    pass


def normalise(sql: str) -> str:
    sql = _comment_block.sub(" ", sql)
    sql = _comment_line.sub(" ", sql)
    sql = _string_lit.sub("''", sql)
    return sql.strip()


def check(sql: str, profile: Profile, allow_write: bool = False) -> str:
    """Return the classification ('read' | 'write') or raise GuardError."""
    body = normalise(sql)
    if not body:
        raise GuardError("Empty statement.")
    if re.search(r"^\s*GO\s*$", body, re.M | re.I):
        raise GuardError("GO batches are not allowed; send one statement.")
    inner = body.rstrip(";")
    if ";" in inner:
        raise GuardError("Only one statement per request.")

    words = {w.upper() for w in re.findall(r"[A-Za-z_]+", inner)}
    first = re.match(r"\s*([A-Za-z]+)", inner)
    first_word = first.group(1).upper() if first else ""
    is_read = first_word in READ_START and not (words & WRITE_WORDS) and "INTO" not in words
    if re.search(r"\bxp_\w+", inner, re.I) or re.search(r"\bsp_(configure|addlogin|password)", inner, re.I):
        is_read = False

    if is_read:
        return "read"
    if not profile.writable:
        raise GuardError(
            f"Blocked: {profile.name} is read-only in this workbench. "
            "Writes go through your normal staged-SQL + review path."
        )
    if not allow_write:
        raise GuardError("This looks like a write. Tick 'allow write' on TEST to run it.")
    return "write"
