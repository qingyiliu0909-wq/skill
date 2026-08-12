import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
import importlib.util


BATCH_SCRIPT = Path(__file__).parents[1] / "scripts" / "batch_export_subsystems.py"
SPEC = importlib.util.spec_from_file_location("batch_export_subsystems", BATCH_SCRIPT)
BATCH_EXPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BATCH_EXPORT)


class CandidateSelectionTests(unittest.TestCase):
    def test_runtime_paths_are_normalized_to_absolute_paths(self):
        resolved = BATCH_EXPORT.resolve_runtime_path(Path("relative/output"))
        self.assertTrue(resolved.is_absolute())

    def test_nested_events_select_only_subsystems_with_matching_keywords(self):
        selector = getattr(BATCH_EXPORT, "select_matching_subsystems", None)
        if selector is None:
            self.fail("select_matching_subsystems is not implemented")

        with tempfile.TemporaryDirectory() as temp_dir:
            trace_path = Path(temp_dir) / "slow_frame.json"
            trace_path.write_text(
                json.dumps(
                    {
                        "name": "FEngineLoop",
                        "children": [
                            {"name": "STAT_NetworkManager_Tick"},
                            {"name": "Unrelated"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            subsystem_defs = {
                "network": {"export_config": {"WhiteKeywords": ["NetworkManager_Tick"]}},
                "fx": {"export_config": {"WhiteKeywords": ["PlayEffect"]}},
            }

            matches = selector(trace_path, subsystem_defs)

        self.assertEqual(matches, {"network": 1})


class BatchExportFailFastTests(unittest.TestCase):
    def test_first_failed_export_stops_remaining_subsystems_and_writes_manifest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            trace_path = root / "input.utrace"
            trace_path.write_text("trace", encoding="utf-8")
            insights_path = root / "UnrealInsights.exe"
            insights_path.write_text("exe", encoding="utf-8")
            output_root = root / "output"
            config_root = root / "configs"
            marker_path = root / "second_was_called.txt"
            result_path = output_root / "batch_export_results.json"

            subsystem_config = root / "subsystems.json"
            subsystem_config.write_text(
                json.dumps(
                    {
                        "defaults": {},
                        "subsystems": {
                            "first": {
                                "name": "First",
                                "output": "first.json",
                                "export_config": {},
                            },
                            "second": {
                                "name": "Second",
                                "output": "second.json",
                                "export_config": {},
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            fake_export = root / "fake_export.py"
            fake_export.write_text(
                "import json\n"
                "from pathlib import Path\n"
                f"MARKER = Path({str(marker_path)!r})\n"
                "def export_trace(config_path):\n"
                "    if Path(config_path).stem == 'second.traceloader':\n"
                "        MARKER.write_text('called', encoding='utf-8')\n"
                "    return {'success': True, 'returncode': 0, 'errors': []}\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(BATCH_SCRIPT),
                    "--trace-path",
                    str(trace_path),
                    "--unreal-insights-path",
                    str(insights_path),
                    "--subsystem-config",
                    str(subsystem_config),
                    "--export-trace-script",
                    str(fake_export),
                    "--output-root",
                    str(output_root),
                    "--config-root",
                    str(config_root),
                    "--start-time",
                    "1",
                    "--end-time",
                    "2",
                ],
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertFalse(marker_path.exists())
            payload = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["attempted_count"], 1)
            self.assertEqual(payload["not_run_subsystems"], ["second"])

    def test_candidate_source_exports_only_observed_subsystems(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            trace_path = root / "input.utrace"
            trace_path.write_text("trace", encoding="utf-8")
            insights_path = root / "UnrealInsights.exe"
            insights_path.write_text("exe", encoding="utf-8")
            candidate_source = root / "slow_frame.json"
            candidate_source.write_text(
                json.dumps({"name": "STAT_NetworkManager_Tick"}),
                encoding="utf-8",
            )
            called_path = root / "called.txt"
            subsystem_config = root / "subsystems.json"
            subsystem_config.write_text(
                json.dumps(
                    {
                        "defaults": {},
                        "subsystems": {
                            "fx": {
                                "name": "FX",
                                "output": "fx.json",
                                "export_config": {"WhiteKeywords": ["PlayEffect"]},
                            },
                            "network": {
                                "name": "Network",
                                "output": "network.json",
                                "export_config": {"WhiteKeywords": ["NetworkManager_Tick"]},
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            fake_export = root / "fake_export.py"
            fake_export.write_text(
                "import json\n"
                "from pathlib import Path\n"
                f"CALLED = Path({str(called_path)!r})\n"
                "def export_trace(config_path):\n"
                "    config = json.loads(Path(config_path).read_text(encoding='utf-8'))\n"
                "    assert config['unreal_insights_path'].endswith('UnrealInsights.exe')\n"
                "    assert ('output_' + 'json_path') not in config\n"
                "    output = Path(config['exports']['timing_events']['json_path'])\n"
                "    output.parent.mkdir(parents=True, exist_ok=True)\n"
                "    output.write_text('{\"name\":\"event\"}\\n', encoding='utf-8')\n"
                "    CALLED.write_text(Path(config_path).stem, encoding='utf-8')\n"
                "    return {'success': True, 'returncode': 0, 'errors': []}\n",
                encoding="utf-8",
            )
            output_root = root / "output"

            completed = subprocess.run(
                [
                    sys.executable,
                    str(BATCH_SCRIPT),
                    "--trace-path",
                    str(trace_path),
                    "--unreal-insights-path",
                    str(insights_path),
                    "--subsystem-config",
                    str(subsystem_config),
                    "--export-trace-script",
                    str(fake_export),
                    "--output-root",
                    str(output_root),
                    "--config-root",
                    str(root / "configs"),
                    "--start-time",
                    "1",
                    "--end-time",
                    "2",
                    "--candidate-source",
                    str(candidate_source),
                ],
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(called_path.read_text(encoding="utf-8"), "network.traceloader")
            payload = json.loads(
                (output_root / "batch_export_results.json").read_text(encoding="utf-8")
            )
            self.assertEqual(payload["candidate_matches"], {"network": 1})
            self.assertEqual(payload["not_observed_subsystems"], ["fx"])
            generated = json.loads(
                (root / "configs" / "network.traceloader.json").read_text(encoding="utf-8")
            )
            self.assertEqual(generated["unreal_insights_path"], str(insights_path.resolve()))
            self.assertEqual(
                generated["exports"]["timing_events"]["json_path"],
                str((output_root / "network.json").resolve()),
            )


if __name__ == "__main__":
    unittest.main()
