"""Build, persist, and query the dependency graph.

Nodes: procedures / functions / views / triggers / tables (defined or inferred).
Edges: calls, reads, writes, fires_on.

The money query is `impact()`: the transitive set of objects that depend on a
given object — "what breaks if I change X".
"""
from __future__ import annotations

import datetime
import json
from collections import defaultdict, deque
from pathlib import Path

EDGE_KINDS = ("calls", "reads", "writes", "fires_on")


def build(objects: list[dict], source: str = "") -> dict:
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    for o in objects:
        nodes[o["name"]] = {"type": o["type"], "defined": True,
                            "has_dynamic_sql": o["has_dynamic_sql"], "source": o["source"]}
    for o in objects:
        for kind in EDGE_KINDS:
            for dst in sorted(o.get(kind, ())):
                # filter probable aliases: short, never defined anywhere
                if len(dst) <= 2 and dst not in nodes:
                    continue
                if dst not in nodes:
                    nodes[dst] = {"type": "table", "defined": False,
                                  "has_dynamic_sql": False, "source": ""}
                edges.append({"src": o["name"], "dst": dst, "kind": kind})
    return {"generated": datetime.date.today().isoformat(), "source": source,
            "nodes": nodes, "edges": edges}


def save(graph: dict, path: str | Path) -> None:
    Path(path).write_text(json.dumps(graph, indent=1), encoding="utf-8")


def load(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ---- queries ----------------------------------------------------------------
def _index(graph: dict):
    fwd, rev = defaultdict(list), defaultdict(list)
    for e in graph["edges"]:
        fwd[e["src"]].append(e)
        rev[e["dst"]].append(e)
    return fwd, rev


def object_info(graph: dict, name: str) -> dict:
    name = name.lower()
    node = graph["nodes"].get(name)
    if not node:
        return {"error": f"unknown object: {name}"}
    fwd, rev = _index(graph)
    out = {"name": name, **node}
    out["uses"] = {k: sorted({e["dst"] for e in fwd[name] if e["kind"] == k})
                   for k in EDGE_KINDS}
    out["used_by"] = {k: sorted({e["src"] for e in rev[name] if e["kind"] == k})
                      for k in EDGE_KINDS}
    if node["has_dynamic_sql"]:
        out["warning"] = "contains dynamic SQL — static dependencies are incomplete"
    return out


def impact(graph: dict, name: str, max_depth: int = 0) -> dict:
    """Everything that transitively depends on `name` (reverse reachability).
    max_depth 0 = unlimited. Returns objects grouped by distance."""
    name = name.lower()
    if name not in graph["nodes"]:
        return {"error": f"unknown object: {name}"}
    _, rev = _index(graph)
    seen = {name: 0}
    q = deque([(name, 0)])
    hits: list[tuple[int, str, str]] = []
    while q:
        cur, d = q.popleft()
        if max_depth and d >= max_depth:
            continue
        for e in rev[cur]:
            if e["src"] not in seen:
                seen[e["src"]] = d + 1
                hits.append((d + 1, e["src"], e["kind"]))
                q.append((e["src"], d + 1))
    by_depth: dict[int, list] = defaultdict(list)
    for d, src, kind in sorted(hits):
        by_depth[d].append({"object": src, "via": kind,
                            "type": graph["nodes"][src]["type"]})
    dyn = [h[1] for h in hits if graph["nodes"][h[1]]["has_dynamic_sql"]]
    return {"target": name, "total_impacted": len(hits),
            "by_depth": {str(k): v for k, v in by_depth.items()},
            "dynamic_sql_caveat": sorted(set(dyn)) or None}


def table_usage(graph: dict, table: str) -> dict:
    table = table.lower()
    _, rev = _index(graph)
    readers = sorted({e["src"] for e in rev[table] if e["kind"] == "reads"})
    writers = sorted({e["src"] for e in rev[table] if e["kind"] == "writes"})
    return {"table": table, "writers": writers, "readers": readers,
            "writer_count": len(writers), "reader_count": len(readers)}


def hotspots(graph: dict, top: int = 10) -> dict:
    fwd, rev = _index(graph)
    fan_in = sorted(((len({e["src"] for e in rev[n]}), n) for n in graph["nodes"]),
                    reverse=True)[:top]
    fan_out = sorted(((len({e["dst"] for e in fwd[n]}), n) for n in graph["nodes"]
                      if graph["nodes"][n]["type"] != "table"), reverse=True)[:top]
    return {"most_depended_on": [{"object": n, "dependents": c} for c, n in fan_in if c],
            "widest_reach": [{"object": n, "touches": c} for c, n in fan_out if c]}


def stats(graph: dict) -> dict:
    types = defaultdict(int)
    for n in graph["nodes"].values():
        key = n["type"] + ("" if n["defined"] else " (inferred)")
        types[key] += 1
    dyn = sum(1 for n in graph["nodes"].values() if n["has_dynamic_sql"])
    return {"objects": dict(sorted(types.items())), "edges": len(graph["edges"]),
            "objects_with_dynamic_sql": dyn, "generated": graph["generated"],
            "source": graph["source"]}


def search(graph: dict, term: str) -> list[dict]:
    t = term.lower()
    return [{"name": n, **meta} for n, meta in sorted(graph["nodes"].items()) if t in n]
