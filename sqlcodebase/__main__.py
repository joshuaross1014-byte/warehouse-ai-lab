"""sql-codebase-mcp CLI.

    python -m sqlcodebase index <dir-or-file.sql> [-o graph.json]
    python -m sqlcodebase stats            [-g graph.json]
    python -m sqlcodebase info <object>    [-g graph.json]
    python -m sqlcodebase impact <object>  [--depth N] [-g graph.json]
    python -m sqlcodebase table <table>    [-g graph.json]
    python -m sqlcodebase hotspots         [-g graph.json]
    python -m sqlcodebase search <term>    [-g graph.json]
"""
import argparse
import json
import sys
from pathlib import Path

from . import graph as G
from .parse import parse_source

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def cmd_index(args):
    root = Path(args.path)
    files = [root] if root.is_file() else sorted(root.rglob("*.sql"))
    if not files:
        sys.exit(f"no .sql files under {root}")
    objects = []
    for f in files:
        objects.extend(parse_source(f.read_text(encoding="utf-8", errors="replace"), f.name))
    g = G.build(objects, source=str(root))
    G.save(g, args.out)
    print(json.dumps(G.stats(g), indent=2))
    print(f"\ngraph written: {args.out}")


def main():
    ap = argparse.ArgumentParser(prog="sqlcodebase")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("index"); p.add_argument("path"); p.add_argument("-o", "--out", default="graph.json")
    for name, need_arg in [("stats", None), ("info", "object"), ("impact", "object"),
                           ("table", "table"), ("hotspots", None), ("search", "term")]:
        p = sub.add_parser(name)
        if need_arg:
            p.add_argument(need_arg)
        if name == "impact":
            p.add_argument("--depth", type=int, default=0)
        p.add_argument("-g", "--graph", default="graph.json")
    args = ap.parse_args()

    if args.cmd == "index":
        return cmd_index(args)
    g = G.load(args.graph)
    out = {"stats": lambda: G.stats(g),
           "info": lambda: G.object_info(g, args.object),
           "impact": lambda: G.impact(g, args.object, args.depth),
           "table": lambda: G.table_usage(g, args.table),
           "hotspots": lambda: G.hotspots(g),
           "search": lambda: G.search(g, args.term)}[args.cmd]()
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
