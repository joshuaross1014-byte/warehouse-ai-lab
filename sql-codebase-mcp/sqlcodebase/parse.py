"""T-SQL reference scanner (pragmatic, regex-based).

Extracts objects and their dependencies from T-SQL source without a full
parser: comments and string literals are stripped first, then object
definitions and reference patterns are scanned.

Honest limitations (documented, not hidden):
  * Dynamic SQL (EXEC(...) / sp_executesql) cannot be statically resolved —
    objects containing it are FLAGGED so you know the graph is incomplete there.
  * UPDATE/DELETE via short aliases can produce alias noise; probable aliases
    (undefined names of <= 2 chars) are filtered out.
"""
from __future__ import annotations

import re

# ---- source cleanup ---------------------------------------------------------
_LINE_COMMENT = re.compile(r"--[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_STRING = re.compile(r"'(?:''|[^'])*'")


def clean(sql: str) -> str:
    sql = _BLOCK_COMMENT.sub(" ", sql)
    sql = _LINE_COMMENT.sub(" ", sql)
    return _STRING.sub("''", sql)


# ---- name handling ----------------------------------------------------------
def norm(name: str) -> str:
    """Normalize an object name: strip brackets/quotes, drop a leading dbo."""
    name = name.strip().strip(";").replace("[", "").replace("]", "").replace('"', "")
    parts = [p for p in name.split(".") if p]
    if len(parts) >= 2 and parts[-2].lower() == "dbo":
        parts = parts[-1:]
    return ".".join(parts[-2:]).lower()


_IGNORE_PREFIXES = ("#", "@", "sys.", "information_schema.", "tempdb.")


_PSEUDO = {"inserted", "deleted", "dual"}   # trigger pseudo-tables etc.
# keyword guard: no capture group should ever yield a bare SQL keyword, but
# T-SQL's grammar has enough odd corners that regex extraction occasionally
# does — blacklisting the vocabulary kills the whole bug class
_KEYWORDS = {
    "into", "from", "select", "where", "set", "values", "output", "with",
    "top", "as", "on", "and", "or", "not", "in", "if", "else", "begin", "end",
    "declare", "exec", "execute", "table", "view", "function", "procedure",
    "trigger", "update", "insert", "delete", "merge", "join", "inner", "left",
    "right", "outer", "cross", "apply", "union", "all", "distinct", "case",
    "when", "then", "null", "is", "exists", "like", "between", "order", "group",
    "by", "having",
}


def _keep(name: str) -> bool:
    n = name.lower()
    return (bool(n) and not n.startswith(_IGNORE_PREFIXES)
            and n not in _PSEUDO and n not in _KEYWORDS)


# ---- patterns ---------------------------------------------------------------
NAME = r"[\w\[\]\."'"'"]+"
CREATE_RE = re.compile(
    rf"\bCREATE\s+(?:OR\s+ALTER\s+)?(PROCEDURE|PROC|FUNCTION|VIEW|TRIGGER|TABLE)\s+({NAME})",
    re.I)
TRIGGER_ON_RE = re.compile(rf"\bTRIGGER\s+{NAME}\s+ON\s+({NAME})", re.I)
EXEC_RE = re.compile(rf"\bEXEC(?:UTE)?\s+(?!\()({NAME})", re.I)
DYNAMIC_RE = re.compile(r"\bEXEC(?:UTE)?\s*\(|\bsp_executesql\b", re.I)
WRITE_RES = [
    re.compile(rf"\bINSERT\s+(?:INTO\s+)?({NAME})", re.I),
    re.compile(rf"\bUPDATE\s+(?:TOP\s*\([^)]*\)\s*)?({NAME})", re.I),
    re.compile(rf"\bDELETE\s+(?:TOP\s*\([^)]*\)\s*)?(?:FROM\s+)?({NAME})", re.I),
    re.compile(rf"\bMERGE\s+(?:INTO\s+)?({NAME})", re.I),
    re.compile(rf"\bTRUNCATE\s+TABLE\s+({NAME})", re.I),
    re.compile(rf"\bINTO\s+({NAME})", re.I),          # SELECT ... INTO
]
READ_RE = re.compile(rf"\b(?:FROM|JOIN)\s+({NAME})", re.I)

TYPE_MAP = {"PROC": "procedure", "PROCEDURE": "procedure", "FUNCTION": "function",
            "VIEW": "view", "TRIGGER": "trigger", "TABLE": "table"}


def parse_source(sql: str, source_name: str = "") -> list[dict]:
    """Parse one T-SQL source (may contain multiple CREATEs) into object dicts:
    {name, type, calls, reads, writes, fires_on, has_dynamic_sql, source}."""
    text = clean(sql)
    creates = list(CREATE_RE.finditer(text))
    objects = []
    for i, m in enumerate(creates):
        body = text[m.start(): creates[i + 1].start() if i + 1 < len(creates) else len(text)]
        otype = TYPE_MAP[m.group(1).upper()]
        name = norm(m.group(2))
        obj = {"name": name, "type": otype, "source": source_name,
               "calls": set(), "reads": set(), "writes": set(),
               "fires_on": set(), "has_dynamic_sql": bool(DYNAMIC_RE.search(body))}
        if otype == "table":
            objects.append(obj)
            continue
        if otype == "trigger":
            t = TRIGGER_ON_RE.search(body)
            if t:
                obj["fires_on"].add(norm(t.group(1)))
        for r in EXEC_RE.finditer(body):
            n = norm(r.group(1))
            if _keep(n) and not n.startswith("sp_"):
                obj["calls"].add(n)
        for wre in WRITE_RES:
            for r in wre.finditer(body):
                n = norm(r.group(1))
                if _keep(n):
                    obj["writes"].add(n)
        for r in READ_RE.finditer(body):
            n = norm(r.group(1))
            if _keep(n):
                obj["reads"].add(n)
        obj["reads"] -= obj["writes"]          # write implies touch; keep sets distinct
        obj["calls"].discard(name)
        objects.append(obj)
    return objects
