#!/usr/bin/env python3
"""Analyze FrameProvider JSONL or Timing Events JSONL exports."""

import argparse
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List


def percentile(ordered: List[float], fraction: float) -> float:
    if not ordered:
        return 0.0
    index = max(0, math.ceil(fraction * len(ordered)) - 1)
    return ordered[index]


def iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path} line {line_number}: {exc}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"JSONL record at {path} line {line_number} must be an object")
            yield record


def analyze_frames(jsonl_path: Path, threshold_ms: float = 16.0) -> Dict[str, Any]:
    grouped: Dict[str, List[Dict[str, Any]]] = {"Game": [], "Rendering": []}
    for frame in iter_jsonl(Path(jsonl_path)):
        frame_type = frame.get("frameType")
        if frame_type not in grouped:
            continue
        required = ("frameIndex", "start", "end", "duration")
        if any(field not in frame for field in required):
            raise ValueError(f"Frame record is missing required fields: {frame}")
        grouped[frame_type].append(frame)

    result: Dict[str, Any] = {}
    for frame_type, frames in grouped.items():
        durations_ms = sorted(float(frame["duration"]) * 1000.0 for frame in frames)
        slow_frames = [
            {
                "frameType": frame_type,
                "frameIndex": frame["frameIndex"],
                "start": frame["start"],
                "end": frame["end"],
                "duration_ms": float(frame["duration"]) * 1000.0,
            }
            for frame in frames
            if float(frame["duration"]) * 1000.0 > threshold_ms
        ]
        slow_frames.sort(key=lambda frame: frame["duration_ms"], reverse=True)
        result[frame_type] = {
            "count": len(frames),
            "average_ms": sum(durations_ms) / len(durations_ms) if durations_ms else 0.0,
            "median_ms": statistics.median(durations_ms) if durations_ms else 0.0,
            "p90_ms": percentile(durations_ms, 0.90),
            "p95_ms": percentile(durations_ms, 0.95),
            "p99_ms": percentile(durations_ms, 0.99),
            "max_ms": durations_ms[-1] if durations_ms else 0.0,
            "slow_frames": slow_frames,
        }
    return result


def traverse_and_collect(event, events_by_depth, events_by_name, depth=0):
    name = event.get("name", "")
    duration = event.get("duration", 0)
    children = event.get("children", []) or []
    events_by_depth[depth].append({"name": name, "duration": duration})
    events_by_name[name].append({"duration": duration, "depth": depth})
    for child in children:
        traverse_and_collect(child, events_by_depth, events_by_name, depth + 1)


def summarize_by_name(events_by_name):
    summary = {}
    for name, events in events_by_name.items():
        durations = sorted(float(event["duration"]) for event in events)
        total = sum(durations)
        summary[name] = {
            "total": total,
            "count": len(events),
            "avg": total / len(events) if events else 0,
            "median": statistics.median(durations),
            "p90": percentile(durations, 0.90),
            "p99": percentile(durations, 0.99),
            "max": durations[-1],
        }
    return dict(sorted(summary.items(), key=lambda item: item[1]["total"], reverse=True))


def find_role_events(events_by_name):
    keywords = [
        "Character", "Role", "Avatar", "EM_", "Lua", "Skill", "Buff", "Weapon",
        "InitAvatar", "OnCharacter", "TickGroup", "Battle", "AIModule", "Inventory",
        "Mission", "Chat", "Social",
    ]
    role_events = {}
    for name, events in events_by_name.items():
        if any(keyword in name for keyword in keywords):
            total = sum(float(event["duration"]) for event in events)
            role_events[name] = {"total": total, "count": len(events), "avg": total / len(events)}
    return dict(sorted(role_events.items(), key=lambda item: item[1]["total"], reverse=True))


def analyze_events(jsonl_path: Path) -> Dict[str, Any]:
    events_by_depth = defaultdict(list)
    events_by_name = defaultdict(list)
    for event_tree in iter_jsonl(Path(jsonl_path)):
        traverse_and_collect(event_tree, events_by_depth, events_by_name)
    summary = summarize_by_name(events_by_name)
    return {
        "total_events": sum(len(events) for events in events_by_depth.values()),
        "by_depth": {depth: len(events) for depth, events in sorted(events_by_depth.items())},
        "top_events": dict(list(summary.items())[:30]),
        "role_events": find_role_events(events_by_name),
    }


# The neutral name remains useful for event-only callers; it no longer implies frames.
analyze_jsonl = analyze_events


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze traceloader JSONL artifacts")
    parser.add_argument("jsonl_path")
    parser.add_argument("--type", choices=("frames", "events"), required=True)
    parser.add_argument("--threshold-ms", type=float, default=16.0)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    path = Path(args.jsonl_path)
    if not path.is_file():
        parser.error(f"File not found: {path}")
    result = analyze_frames(path, args.threshold_ms) if args.type == "frames" else analyze_events(path)
    output_path = Path(args.output) if args.output else path.with_name(path.stem + "_analysis.json")
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
