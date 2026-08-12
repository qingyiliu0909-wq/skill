#!/usr/bin/env python3
"""
analyze_actors.py — Query and summarize parsed .umap actor data.

Usage:
    python3 analyze_actors.py actors.json --summary
    python3 analyze_actors.py actors.json --find-actor BP_MyActor_5
    python3 analyze_actors.py actors.json --find-class StaticMeshActor
    python3 analyze_actors.py actors.json --find-prop MyCustomScore
    python3 analyze_actors.py actors.json --diff other_actors.json
"""

import json
import sys
import argparse
import os
from collections import Counter


def load(path: str) -> list:
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def cmd_summary(actors: list):
    print(f"\n{'='*50}")
    print(f"  Total exports:  {len(actors)}")
    class_counts = Counter(a['ClassName'] for a in actors)
    print(f"\n  Actor classes ({len(class_counts)} unique):")
    for cls, cnt in class_counts.most_common(20):
        print(f"    {cnt:5d}  {cls}")

    # Property coverage
    all_props = Counter()
    for a in actors:
        for k in a.get('Properties', {}).keys():
            all_props[k] += 1
    print(f"\n  Top properties found:")
    for prop, cnt in all_props.most_common(15):
        pct = cnt * 100 // len(actors)
        print(f"    {cnt:5d} ({pct:3d}%)  {prop}")
    print()


def cmd_find_actor(actors: list, name: str):
    matches = [a for a in actors if name.lower() in a['ExportName'].lower()]
    if not matches:
        print(f"No actor found matching '{name}'")
        return
    for m in matches:
        print(f"\n{'─'*60}")
        print(f"  Name:   {m['ExportName']}")
        print(f"  Class:  {m['ClassName']}")
        print(f"  Outer:  {m['OuterName']}")
        props = m.get('Properties', {})
        if props:
            print(f"  Properties ({len(props)}):")
            for k, v in props.items():
                print(f"    {k}: {v}")
        else:
            print("  (no properties parsed)")


def cmd_find_class(actors: list, cls: str):
    matches = [a for a in actors if cls.lower() in a['ClassName'].lower()]
    print(f"Found {len(matches)} actors of class '{cls}':")
    for m in matches[:50]:
        props = m.get('Properties', {})
        loc = props.get('RelativeLocation') or props.get('Location', {})
        loc_str = ""
        if isinstance(loc, dict):
            loc_str = f"  Loc=({loc.get('X',0):.1f}, {loc.get('Y',0):.1f}, {loc.get('Z',0):.1f})"
        print(f"  [{m['ExportIndex']:4d}] {m['ExportName']}{loc_str}")
    if len(matches) > 50:
        print(f"  ... and {len(matches)-50} more")


def cmd_find_prop(actors: list, prop: str):
    matches = [(a, a['Properties'][prop]) for a in actors
               if prop in a.get('Properties', {})]
    print(f"Found {len(matches)} actors with property '{prop}':")
    for actor, val in matches[:30]:
        print(f"  {actor['ExportName']}  ({actor['ClassName']})  → {val}")


def cmd_diff(actors_a: list, actors_b: list):
    names_a = {a['ExportName'] for a in actors_a}
    names_b = {a['ExportName'] for a in actors_b}

    only_a = names_a - names_b
    only_b = names_b - names_a
    common = names_a & names_b

    print(f"\nDiff summary:")
    print(f"  File A: {len(actors_a)} exports")
    print(f"  File B: {len(actors_b)} exports")
    print(f"  Only in A: {len(only_a)}")
    print(f"  Only in B: {len(only_b)}")
    print(f"  Common:    {len(common)}")

    if only_a:
        print("\nOnly in A (first 20):")
        for n in sorted(only_a)[:20]:
            print(f"  - {n}")

    if only_b:
        print("\nOnly in B (first 20):")
        for n in sorted(only_b)[:20]:
            print(f"  + {n}")

    # Check Transform changes for common actors
    map_a = {a['ExportName']: a for a in actors_a}
    map_b = {a['ExportName']: a for a in actors_b}
    changed = []
    for name in common:
        pa = map_a[name].get('Properties', {})
        pb = map_b[name].get('Properties', {})
        la = pa.get('RelativeLocation') or pa.get('Location')
        lb = pb.get('RelativeLocation') or pb.get('Location')
        if la != lb:
            changed.append((name, la, lb))

    if changed:
        print(f"\nActors with changed Location ({len(changed)}):")
        for name, la, lb in changed[:20]:
            print(f"  {name}")
            print(f"    A: {la}")
            print(f"    B: {lb}")


def main():
    parser = argparse.ArgumentParser(description="Analyze parsed .umap actor data")
    parser.add_argument("input", help="actors.json from umap_parser.py")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--find-actor", metavar="NAME")
    parser.add_argument("--find-class", metavar="CLASS")
    parser.add_argument("--find-prop", metavar="PROP")
    parser.add_argument("--diff", metavar="OTHER_JSON")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"ERROR: {args.input} not found"); sys.exit(1)

    actors = load(args.input)

    if args.summary:
        cmd_summary(actors)
    if args.find_actor:
        cmd_find_actor(actors, args.find_actor)
    if args.find_class:
        cmd_find_class(actors, args.find_class)
    if args.find_prop:
        cmd_find_prop(actors, args.find_prop)
    if args.diff:
        actors_b = load(args.diff)
        cmd_diff(actors, actors_b)

    if not any([args.summary, args.find_actor, args.find_class,
                args.find_prop, args.diff]):
        cmd_summary(actors)


if __name__ == "__main__":
    main()
