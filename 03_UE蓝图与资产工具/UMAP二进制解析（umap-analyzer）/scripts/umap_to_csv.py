#!/usr/bin/env python3
"""
umap_to_csv.py — Convert umap_parser.py JSON output to a flat CSV table.

Flattens Transform properties and custom user-specified properties into columns.

Usage:
    python3 umap_to_csv.py actors.json --output actors.csv
    python3 umap_to_csv.py actors.json --output actors.csv --props MyScore,IsActive,TeamID
"""

import json
import csv
import sys
import argparse
import os
from typing import Optional


# ---------------------------------------------------------------------------
# Transform extraction helpers
# ---------------------------------------------------------------------------

def extract_transform_from_props(props: dict) -> dict:
    """
    Try multiple known paths where Transform data might live:
    1. Direct 'RelativeLocation' / 'RelativeRotation' / 'RelativeScale3D'  (SceneComponent style)
    2. Direct 'ActorTransform'  (rare, packed FTransform)
    3. Nested inside 'RootComponent' struct
    Returns flat dict with Loc_X/Y/Z, Rot_Pitch/Yaw/Roll, Scale_X/Y/Z.
    """
    result = {
        "Loc_X": "", "Loc_Y": "", "Loc_Z": "",
        "Rot_Pitch": "", "Rot_Yaw": "", "Rot_Roll": "",
        "Scale_X": "", "Scale_Y": "", "Scale_Z": "",
    }

    loc = props.get("RelativeLocation") or props.get("Location")
    rot = props.get("RelativeRotation") or props.get("Rotation")
    scale = props.get("RelativeScale3D") or props.get("Scale3D")

    transform = props.get("ActorTransform")

    if transform and isinstance(transform, dict):
        loc = transform.get("Translation", loc)
        rot_quat = transform.get("Rotation")
        scale = transform.get("Scale3D", scale)
        # Quat → approximate Euler (for display; use UE editor for precise conversion)
        if rot_quat and isinstance(rot_quat, dict):
            import math
            x, y, z, w = (rot_quat.get("X", 0), rot_quat.get("Y", 0),
                          rot_quat.get("Z", 0), rot_quat.get("W", 1))
            # Yaw (Z axis)
            yaw = math.degrees(math.atan2(2*(w*z + x*y), 1 - 2*(y*y + z*z)))
            # Pitch (Y axis)
            sinp = 2*(w*y - z*x)
            pitch = math.degrees(math.asin(max(-1, min(1, sinp))))
            # Roll (X axis)
            roll = math.degrees(math.atan2(2*(w*x + y*z), 1 - 2*(x*x + y*y)))
            result["Rot_Pitch"] = round(pitch, 4)
            result["Rot_Yaw"] = round(yaw, 4)
            result["Rot_Roll"] = round(roll, 4)

    if loc and isinstance(loc, dict):
        result["Loc_X"] = round(loc.get("X", ""), 4)
        result["Loc_Y"] = round(loc.get("Y", ""), 4)
        result["Loc_Z"] = round(loc.get("Z", ""), 4)

    if rot and isinstance(rot, dict) and not result["Rot_Yaw"]:
        result["Rot_Pitch"] = round(rot.get("Pitch", ""), 4)
        result["Rot_Yaw"] = round(rot.get("Yaw", ""), 4)
        result["Rot_Roll"] = round(rot.get("Roll", ""), 4)

    if scale and isinstance(scale, dict):
        result["Scale_X"] = round(scale.get("X", ""), 4)
        result["Scale_Y"] = round(scale.get("Y", ""), 4)
        result["Scale_Z"] = round(scale.get("Z", ""), 4)

    return result


def flatten_value(val) -> str:
    """Convert any value to a CSV-friendly string."""
    if val is None:
        return ""
    if isinstance(val, dict):
        return json.dumps(val, ensure_ascii=False)
    if isinstance(val, bool):
        return str(val)
    if isinstance(val, float):
        return f"{val:.6g}"
    return str(val)


# ---------------------------------------------------------------------------
# Main conversion
# ---------------------------------------------------------------------------

def json_to_csv(input_path: str, output_path: str,
                extra_props: Optional[list] = None,
                include_all_props: bool = False):
    with open(input_path, 'r', encoding='utf-8') as f:
        actors = json.load(f)

    if not actors:
        print("No exports found in JSON file.")
        return

    extra_props = extra_props or []

    # Build CSV rows
    rows = []
    all_extra_keys = set(extra_props)

    if include_all_props:
        for actor in actors:
            for k in actor.get("Properties", {}).keys():
                all_extra_keys.add(k)

    for actor in actors:
        props = actor.get("Properties", {})
        transform = extract_transform_from_props(props)

        row = {
            "ExportIndex": actor.get("ExportIndex", ""),
            "ExportName": actor.get("ExportName", ""),
            "ClassName": actor.get("ClassName", ""),
            "OuterName": actor.get("OuterName", ""),
            **transform,
        }

        # Extra / custom properties
        for key in sorted(all_extra_keys):
            val = props.get(key, "")
            row[key] = flatten_value(val)

        if actor.get("ParseError"):
            row["_ParseError"] = actor["ParseError"]

        rows.append(row)

    # Determine columns
    base_cols = [
        "ExportIndex", "ExportName", "ClassName", "OuterName",
        "Loc_X", "Loc_Y", "Loc_Z",
        "Rot_Pitch", "Rot_Yaw", "Rot_Roll",
        "Scale_X", "Scale_Y", "Scale_Z",
    ]
    extra_cols = sorted(all_extra_keys)
    all_cols = base_cols + extra_cols

    if any(r.get("_ParseError") for r in rows):
        all_cols.append("_ParseError")

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=all_cols, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)

    print(f"[OK] Wrote {len(rows)} rows → {output_path}")
    print(f"     Columns: {', '.join(all_cols)}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Convert umap JSON to CSV")
    parser.add_argument("input", help="actors.json from umap_parser.py")
    parser.add_argument("--output", "-o", default="actors.csv")
    parser.add_argument("--props", help="Comma-separated extra property names to include")
    parser.add_argument("--all-props", action="store_true",
                        help="Include ALL parsed properties as columns")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"ERROR: {args.input} not found")
        sys.exit(1)

    extra = [p.strip() for p in args.props.split(",")] if args.props else []
    json_to_csv(args.input, args.output, extra_props=extra,
                include_all_props=args.all_props)


if __name__ == "__main__":
    main()
