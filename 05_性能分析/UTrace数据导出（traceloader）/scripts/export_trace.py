#!/usr/bin/env python3
"""Export Unreal trace artifacts from one self-contained JSON configuration."""

import csv
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


SKILL_NAME = "traceloader"
FRAME_DURATION_FIELDS = (
    "MinGameFrameDuration",
    "MaxGameFrameDuration",
    "MinRenderingFrameDuration",
    "MaxRenderingFrameDuration",
)
EXPORT_TARGETS = (
    ("frames_json", "frames", "json_path", "TimingInsights.ExportFramesToJSON"),
    ("frames_csv", "frames", "csv_path", "TimingInsights.ExportFramesToCSV"),
    ("metadata_csv", "metadata", "csv_path", "TimingInsights.ExportMetadataToCSV"),
    ("timing_events_json", "timing_events", "json_path", "TimingInsights.ExportTimingEventsToJSON"),
    ("timing_events_csv", "timing_events", "csv_path", "TimingInsights.ExportTimingEventsToCSV"),
)


def load_config(config_path: str) -> Dict[str, Any]:
    path = Path(config_path)
    if not path.is_file():
        raise ValueError(f"Config file not found: {path}")
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            config = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in config file: {exc}") from exc
    if not isinstance(config, dict):
        raise ValueError("Config root must be a JSON object")
    return config


def _configured_targets(config: Dict[str, Any]) -> List[Tuple[str, Path]]:
    exports = config.get("exports")
    if not isinstance(exports, dict):
        return []
    targets: List[Tuple[str, Path]] = []
    for artifact_key, group_name, field_name, _ in EXPORT_TARGETS:
        group = exports.get(group_name)
        if group is None:
            continue
        if not isinstance(group, dict):
            raise ValueError(f"exports.{group_name} must be an object")
        value = group.get(field_name)
        if value:
            if not isinstance(value, str):
                raise ValueError(f"exports.{group_name}.{field_name} must be a path string or null")
            targets.append((artifact_key, Path(value)))
    return targets


def validate_config(config: Dict[str, Any]) -> Dict[str, Any]:
    for field in ("unreal_insights_path", "trace_file_path"):
        if not isinstance(config.get(field), str) or not config[field].strip():
            raise ValueError(f"Missing required field: {field}")

    targets = _configured_targets(config)
    if not targets:
        raise ValueError("At least one export target is required in exports")

    export_config = config.get("export_config", {})
    if export_config is None:
        export_config = {}
    if not isinstance(export_config, dict):
        raise ValueError("export_config must be an object")

    for field in FRAME_DURATION_FIELDS:
        if field not in export_config:
            continue
        value = export_config[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise ValueError(f"{field} must be a non-negative number")

    for minimum, maximum in (
        ("MinGameFrameDuration", "MaxGameFrameDuration"),
        ("MinRenderingFrameDuration", "MaxRenderingFrameDuration"),
    ):
        if minimum in export_config and maximum in export_config:
            if export_config[minimum] > export_config[maximum]:
                raise ValueError(f"{minimum} must be less than or equal to {maximum}")
    return config


def has_timing_event_exports(config: Dict[str, Any]) -> bool:
    return any(key.startswith("timing_events_") for key, _ in _configured_targets(config))


def review_event_export_config(config: Dict[str, Any], review_mode: str = "warn") -> Dict[str, Any]:
    del review_mode
    reviewed = dict(config or {})
    fixes: List[str] = []
    warnings: List[str] = []
    blockers: List[str] = []

    if not reviewed.get("WhiteTracks"):
        reviewed["WhiteTracks"] = ["GameThread"]
        fixes.append('added WhiteTracks=["GameThread"]')

    start_time = reviewed.get("StartTime")
    end_time = reviewed.get("EndTime")
    if (start_time is None) ^ (end_time is None):
        blockers.append("StartTime and EndTime must appear together")
    if start_time is not None and end_time is not None and end_time <= start_time:
        blockers.append("EndTime must be greater than StartTime")

    limiting_fields = {
        "MinDepth", "MaxDepth", "MinDuration", "MaxDuration", *FRAME_DURATION_FIELDS,
        "WhiteEvents", "WhiteKeywords",
    }
    if start_time is None and end_time is None and not any(field in reviewed for field in limiting_fields):
        blockers.append("full-range event export must include a depth, duration, or whitelist limit")

    if blockers:
        decision = "invalid_and_stop"
    elif fixes and warnings:
        decision = "fixed_warn_and_run"
    elif fixes:
        decision = "fixed_and_run"
    elif warnings:
        decision = "warn_and_run"
    else:
        decision = "run"
    return {
        "config": reviewed,
        "config_review": {
            "decision": decision,
            "fixes": fixes,
            "warnings": warnings,
            "rejected_reasons": blockers,
        },
    }


# Kept as a source-level alias for callers already importing the function name;
# the removed configuration fields and runtime behavior are not supported.
review_export_config = review_event_export_config


def build_export_commands(config: Dict[str, Any]) -> List[str]:
    exports = config.get("exports", {})
    commands: List[str] = []
    for _, group_name, field_name, command_name in EXPORT_TARGETS:
        group = exports.get(group_name) or {}
        output_path = group.get(field_name)
        if output_path:
            commands.append(f"{command_name} {Path(output_path).as_posix()}")
    return commands


def build_exec_argument(commands: Iterable[str]) -> str:
    command_text = ";".join(commands)
    if not command_text:
        raise ValueError("At least one export command is required")
    return f"-ExecOnAnalysisCompleteCmd={command_text}"


def collect_output_parts(main_path: Path) -> List[Path]:
    main_path = Path(main_path)
    parts = [main_path] if main_path.is_file() else []
    pattern = re.compile(
        rf"^{re.escape(main_path.stem)}_part(?P<number>\d+){re.escape(main_path.suffix)}$",
        re.IGNORECASE,
    )
    numbered = []
    if main_path.parent.is_dir():
        for candidate in main_path.parent.iterdir():
            match = pattern.match(candidate.name)
            if match and candidate.is_file():
                numbered.append((int(match.group("number")), candidate))
    parts.extend(path for _, path in sorted(numbered, key=lambda item: item[0]))
    return parts


def _validate_jsonl(parts: List[Path], require_frame_type: bool) -> Optional[str]:
    records = 0
    found_frame_type = False
    for part in parts:
        with part.open("r", encoding="utf-8-sig") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    return f"Invalid JSONL record in {part} line {line_number}: {exc}"
                records += 1
                if isinstance(record, dict) and record.get("frameType") in {"Game", "Rendering"}:
                    found_frame_type = True
    if records == 0:
        return "JSONL artifact contains no records"
    if require_frame_type and not found_frame_type:
        return "Frame JSONL must contain at least one Game or Rendering record"
    return None


def _validate_csv(parts: List[Path], require_frame_type: bool) -> Optional[str]:
    rows = 0
    found_frame_type = False
    for part in parts:
        with part.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                return f"CSV artifact has no header: {part}"
            for row in reader:
                rows += 1
                if row.get("FrameType") in {"Game", "Rendering"}:
                    found_frame_type = True
    if rows == 0:
        return "CSV artifact must contain a header and at least one data row"
    if require_frame_type and not found_frame_type:
        return "Frame CSV must contain at least one Game or Rendering row"
    return None


def _validate_metadata_csv(parts: List[Path]) -> Optional[str]:
    rows = 0
    for part in parts:
        with part.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader, None)
            if not header:
                return f"Metadata CSV artifact has no header: {part}"
            for row in reader:
                if not row:
                    continue
                if len(row) < 7:
                    return f"Metadata CSV data row must contain at least 7 columns: {part}"
                try:
                    float(row[2])
                    float(row[3])
                    float(row[4])
                    int(row[5])
                except ValueError:
                    return f"Metadata CSV has invalid Start, End, Duration, or Depth values: {part}"
                if not ",".join(row[6:]).strip():
                    return f"Metadata CSV data row has empty Metadata: {part}"
                rows += 1
    if rows == 0:
        return "Metadata CSV must contain a header and at least one data row"
    return None


def validate_artifact(artifact_key: str, main_path: Path) -> Dict[str, Any]:
    main_path = Path(main_path)
    parts = collect_output_parts(main_path)
    if not main_path.is_file():
        return {"valid": False, "path": str(main_path), "parts": [], "error": "Requested artifact is missing"}
    empty = [str(path) for path in parts if path.stat().st_size == 0]
    if empty:
        return {"valid": False, "path": str(main_path), "parts": [str(p) for p in parts], "error": f"Artifact is empty: {empty[0]}"}

    require_frame_type = artifact_key.startswith("frames_")
    if artifact_key == "metadata_csv":
        error = _validate_metadata_csv(parts)
    elif artifact_key.endswith("_json"):
        error = _validate_jsonl(parts, require_frame_type)
    elif artifact_key.endswith("_csv"):
        error = _validate_csv(parts, require_frame_type)
    else:
        error = f"Unknown artifact type: {artifact_key}"
    return {
        "valid": error is None,
        "path": str(main_path),
        "parts": [str(path) for path in parts],
        "error": error,
    }


def validate_artifacts(config: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    artifacts: Dict[str, Any] = {key: None for key, *_ in EXPORT_TARGETS}
    errors: List[str] = []
    for artifact_key, path in _configured_targets(config):
        result = validate_artifact(artifact_key, path)
        artifacts[artifact_key] = {"path": result["path"], "parts": result["parts"]}
        if not result["valid"]:
            errors.append(f"{artifact_key}: {result['error']}")
    return artifacts, errors


def _default_log_path(config: Dict[str, Any]) -> Path:
    explicit = config.get("log_path")
    if explicit:
        return Path(explicit)
    targets = _configured_targets(config)
    return targets[0][1].with_suffix(".log")


def _event_export_config_path(config: Dict[str, Any]) -> Path:
    timing = config["exports"].get("timing_events") or {}
    source = timing.get("json_path") or timing.get("csv_path")
    return Path(source).with_suffix(".export_config.json")


def run_unreal_insights(
    config: Dict[str, Any], commands: List[str], export_config_path: Optional[Path], log_path: Path
) -> subprocess.CompletedProcess:
    command_line = [
        config["unreal_insights_path"],
        "-OpenTraceFile=" + Path(config["trace_file_path"]).as_posix(),
    ]
    if export_config_path is not None:
        command_line.append("-ExportConfig=" + export_config_path.as_posix())
    command_line.extend(
        [
            "-ABSLOG=" + str(log_path),
            build_exec_argument(commands),
            "-AutoQuit",
            "-NoUI",
        ]
    )
    return subprocess.run(command_line, capture_output=True, text=True)


def export_trace(config_path: str) -> Dict[str, Any]:
    errors: List[str] = []
    config_review: Dict[str, Any] = {}
    artifacts: Dict[str, Any] = {}
    try:
        config = validate_config(load_config(config_path))
        unreal_insights_path = Path(config["unreal_insights_path"])
        trace_path = Path(config["trace_file_path"])
        if not unreal_insights_path.is_file():
            raise ValueError(f"UnrealInsights executable not found: {unreal_insights_path}")
        if not trace_path.is_file():
            raise ValueError(f"Trace file not found: {trace_path}")

        for _, output_path in _configured_targets(config):
            output_path.parent.mkdir(parents=True, exist_ok=True)
        log_path = _default_log_path(config)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        export_config_path = None
        if has_timing_event_exports(config):
            review = review_event_export_config(config.get("export_config", {}))
            config_review = review["config_review"]
            if config_review["decision"] == "invalid_and_stop":
                return {
                    "success": False,
                    "returncode": None,
                    "artifacts": {},
                    "config_review": config_review,
                    "errors": list(config_review["rejected_reasons"]),
                }
            export_config_path = _event_export_config_path(config)
            export_config_path.parent.mkdir(parents=True, exist_ok=True)
            with export_config_path.open("w", encoding="utf-8") as handle:
                json.dump(review["config"], handle, indent=2, ensure_ascii=False)

        result = run_unreal_insights(config, build_export_commands(config), export_config_path, log_path)
        artifacts, validation_errors = validate_artifacts(config)
        artifacts["export_config"] = str(export_config_path) if export_config_path else None
        artifacts["log"] = str(log_path)
        errors.extend(validation_errors)
        if result.returncode != 0:
            errors.append(f"UnrealInsights exited with return code {result.returncode}")
        return {
            "success": result.returncode == 0 and not errors,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "artifacts": artifacts,
            "config_review": config_review,
            "errors": errors,
        }
    except (OSError, ValueError) as exc:
        return {
            "success": False,
            "returncode": None,
            "artifacts": artifacts,
            "config_review": config_review,
            "errors": [str(exc)],
        }


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python export_trace.py <config_path>")
        return 2
    result = export_trace(sys.argv[1])
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
