import argparse
import importlib.util
import json
from pathlib import Path


def resolve_runtime_path(path: Path):
    return Path(path).expanduser().resolve()


def load_traceloader(export_trace_path: Path):
    spec = importlib.util.spec_from_file_location("traceloader_export_trace", export_trace_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def merged_export_config(defaults, subsystem_config, start_time, end_time):
    config = {}
    config.update(defaults)
    config.update(subsystem_config)
    config["StartTime"] = start_time
    config["EndTime"] = end_time
    return config


def validate_export_file(output_path: Path):
    if not output_path.exists():
        return False, "output missing"
    if output_path.stat().st_size <= 0:
        return False, "output empty"
    with open(output_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                return True, None
    return False, "output has no event lines"


def select_matching_subsystems(jsonl_path: Path, subsystem_defs):
    keyword_map = {
        subsystem_id: subsystem.get("export_config", {}).get("WhiteKeywords", [])
        for subsystem_id, subsystem in subsystem_defs.items()
    }
    matches = {subsystem_id: 0 for subsystem_id in subsystem_defs}

    def visit(event):
        name = event.get("name", "")
        for subsystem_id, keywords in keyword_map.items():
            if any(keyword in name for keyword in keywords):
                matches[subsystem_id] += 1
        for child in event.get("children") or []:
            visit(child)

    with open(jsonl_path, "r", encoding="utf-8") as source:
        for line in source:
            if line.strip():
                visit(json.loads(line))

    return {subsystem_id: count for subsystem_id, count in matches.items() if count > 0}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Read unified subsystem config, generate per-subsystem traceloader configs, and export sequentially."
    )
    parser.add_argument("--trace-path", required=True, help="Absolute path to the .utrace file")
    parser.add_argument(
        "--unreal-insights-path",
        required=True,
        help="Absolute path to UnrealInsights.exe written into every traceloader config",
    )
    parser.add_argument("--subsystem-config", required=True, help="Absolute path to 子系统分析配置.json")
    parser.add_argument("--export-trace-script", required=True, help="Absolute path to traceloader/scripts/export_trace.py")
    parser.add_argument("--output-root", required=True, help="Directory for subsystem json/log/export_config outputs")
    parser.add_argument("--config-root", required=True, help="Directory for generated per-subsystem .traceloader.json files")
    parser.add_argument("--start-time", required=True, type=float, help="Window start time in seconds")
    parser.add_argument("--end-time", required=True, type=float, help="Window end time in seconds")
    parser.add_argument(
        "--include",
        nargs="*",
        default=None,
        help="Optional subsystem ids to export. Default is all subsystems except skip=true.",
    )
    parser.add_argument(
        "--candidate-source",
        default=None,
        help="Optional slow-frame JSONL used to select subsystems whose WhiteKeywords were observed.",
    )
    parser.add_argument("--result-path", default=None, help="Optional custom path for batch_export_results.json")
    return parser.parse_args()


def main():
    args = parse_args()

    trace_path = resolve_runtime_path(args.trace_path)
    unreal_insights_path = resolve_runtime_path(args.unreal_insights_path)
    subsystem_config_path = resolve_runtime_path(args.subsystem_config)
    export_trace_path = resolve_runtime_path(args.export_trace_script)
    output_root = resolve_runtime_path(args.output_root)
    config_root = resolve_runtime_path(args.config_root)
    result_path = resolve_runtime_path(args.result_path) if args.result_path else output_root / "batch_export_results.json"

    output_root.mkdir(parents=True, exist_ok=True)
    config_root.mkdir(parents=True, exist_ok=True)

    config_data = json.loads(subsystem_config_path.read_text(encoding="utf-8-sig"))
    defaults = config_data.get("defaults", {})
    subsystem_defs = config_data["subsystems"]
    requested = set(args.include) if args.include else None
    candidate_matches = (
        select_matching_subsystems(resolve_runtime_path(args.candidate_source), subsystem_defs)
        if args.candidate_source
        else None
    )
    traceloader = load_traceloader(export_trace_path)

    selected = []
    skipped = []
    not_observed_subsystems = []
    for subsystem_id, subsystem in subsystem_defs.items():
        if requested and subsystem_id not in requested:
            continue
        if subsystem.get("skip") is True:
            skipped.append(
                {
                    "subsystem_id": subsystem_id,
                    "name": subsystem.get("name", subsystem_id),
                    "reason": "config skip=true",
                }
            )
            continue
        if candidate_matches is not None and subsystem_id not in candidate_matches:
            not_observed_subsystems.append(subsystem_id)
            continue
        selected.append((subsystem_id, subsystem))

    results = []
    for subsystem_id, subsystem in selected:
        output_path = output_root / subsystem["output"]
        skill_config_path = config_root / f"{subsystem_id}.traceloader.json"
        export_config = merged_export_config(
            defaults,
            subsystem["export_config"],
            args.start_time,
            args.end_time,
        )
        skill_config = {
            "unreal_insights_path": str(unreal_insights_path),
            "trace_file_path": str(trace_path),
            "log_path": str(output_path.with_suffix(".log")),
            "exports": {
                "timing_events": {
                    "json_path": str(output_path),
                    "csv_path": None,
                }
            },
            "export_config": export_config,
        }
        skill_config_path.write_text(json.dumps(skill_config, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"EXPORT {subsystem_id} -> {output_path}")
        result = traceloader.export_trace(str(skill_config_path))
        valid_output, invalid_reason = validate_export_file(output_path)
        success = bool(result.get("success")) and valid_output
        errors = list(result.get("errors", []))
        if invalid_reason:
            errors.append(invalid_reason)

        result_record = {
            "subsystem_id": subsystem_id,
            "name": subsystem["name"],
            "output": str(output_path),
            "config": str(skill_config_path),
            "log": str(output_path.with_suffix(".log")),
            "success": success,
            "returncode": result.get("returncode"),
            "errors": errors,
            "config_review": result.get("config_review", {}),
        }
        if output_path.exists():
            result_record["bytes"] = output_path.stat().st_size
        results.append(result_record)
        if not success:
            print(f"STOP_AFTER_FAILURE={subsystem_id}")
            break

    expected_count = len(selected)
    success_count = sum(1 for item in results if item["success"])
    failed = [item for item in results if not item["success"]]
    attempted_ids = {item["subsystem_id"] for item in results}
    not_run_subsystems = [
        subsystem_id
        for subsystem_id, _ in selected
        if subsystem_id not in attempted_ids
    ]

    payload = {
        "unreal_insights_path": str(unreal_insights_path),
        "trace_path": str(trace_path),
        "source_config": str(subsystem_config_path),
        "window": {
            "StartTime": args.start_time,
            "EndTime": args.end_time,
        },
        "expected_subsystem_count": expected_count,
        "attempted_count": len(results),
        "not_run_subsystems": not_run_subsystems,
        "candidate_source": args.candidate_source,
        "candidate_matches": candidate_matches,
        "not_observed_subsystems": not_observed_subsystems,
        "skipped_subsystems": skipped,
        "success_count": success_count,
        "failed_count": len(failed),
        "results": results,
    }
    result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"RESULT_PATH={result_path}")
    print(f"EXPECTED={expected_count} SUCCESS={success_count} FAILED={len(failed)}")
    if skipped:
        print(f"SKIPPED={len(skipped)}")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
