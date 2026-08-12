import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "export_trace.py"
SPEC = importlib.util.spec_from_file_location("export_trace", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ConfigValidationTests(unittest.TestCase):
    def test_unreal_insights_path_is_required(self):
        config = {
            "trace_file_path": "trace.utrace",
            "exports": {"frames": {"json_path": "frames.json"}},
        }
        with self.assertRaisesRegex(ValueError, "unreal_insights_path"):
            MODULE.validate_config(config)

    def test_at_least_one_export_target_is_required(self):
        config = {
            "unreal_insights_path": "UnrealInsights.exe",
            "trace_file_path": "trace.utrace",
            "exports": {},
        }
        with self.assertRaisesRegex(ValueError, "export target"):
            MODULE.validate_config(config)

    def test_rejects_game_min_greater_than_max(self):
        config = {
            "unreal_insights_path": "UnrealInsights.exe",
            "trace_file_path": "trace.utrace",
            "exports": {"timing_events": {"json_path": "events.json"}},
            "export_config": {
                "MinGameFrameDuration": 0.100,
                "MaxGameFrameDuration": 0.033,
            },
        }
        with self.assertRaisesRegex(ValueError, "MinGameFrameDuration"):
            MODULE.validate_config(config)

    def test_rejects_negative_rendering_duration(self):
        config = {
            "unreal_insights_path": "UnrealInsights.exe",
            "trace_file_path": "trace.utrace",
            "exports": {"timing_events": {"json_path": "events.json"}},
            "export_config": {"MinRenderingFrameDuration": -0.001},
        }
        with self.assertRaisesRegex(ValueError, "MinRenderingFrameDuration"):
            MODULE.validate_config(config)


class CommandConstructionTests(unittest.TestCase):
    def test_metadata_only_builds_csv_command_without_event_config(self):
        config = {
            "unreal_insights_path": "D:/UE/UnrealInsights.exe",
            "trace_file_path": "D:/trace.utrace",
            "exports": {
                "metadata": {"csv_path": "D:/out/resource_load_metadata.csv"},
            },
        }
        self.assertEqual(
            MODULE.build_export_commands(config),
            ["TimingInsights.ExportMetadataToCSV D:/out/resource_load_metadata.csv"],
        )
        self.assertFalse(MODULE.has_timing_event_exports(config))

    def test_frames_only_builds_two_commands_without_export_config(self):
        config = {
            "unreal_insights_path": "D:/UE/UnrealInsights.exe",
            "trace_file_path": "D:/trace.utrace",
            "exports": {
                "frames": {
                    "json_path": "D:/out/frames.json",
                    "csv_path": "D:/out/frames.csv",
                }
            },
        }
        commands = MODULE.build_export_commands(config)
        self.assertEqual(
            commands,
            [
                "TimingInsights.ExportFramesToJSON D:/out/frames.json",
                "TimingInsights.ExportFramesToCSV D:/out/frames.csv",
            ],
        )
        self.assertFalse(MODULE.has_timing_event_exports(config))

    def test_frames_and_events_share_one_exec_argument(self):
        config = {
            "unreal_insights_path": "D:/UE/UnrealInsights.exe",
            "trace_file_path": "D:/trace.utrace",
            "exports": {
                "frames": {"json_path": "D:/out/frames.json"},
                "timing_events": {
                    "json_path": "D:/out/events.json",
                    "csv_path": "D:/out/events.csv",
                },
            },
        }
        commands = MODULE.build_export_commands(config)
        argument = MODULE.build_exec_argument(commands)
        self.assertEqual(argument.count("-ExecOnAnalysisCompleteCmd="), 1)
        self.assertIn("ExportFramesToJSON", argument)
        self.assertIn("ExportTimingEventsToJSON", argument)
        self.assertIn("ExportTimingEventsToCSV", argument)
        self.assertIn(";", argument)

    def test_new_frame_fields_survive_event_config_review(self):
        export_config = {
            "StartTime": 1.0,
            "EndTime": 2.0,
            "MinGameFrameDuration": 0.016,
            "MaxGameFrameDuration": 0.100,
            "MinRenderingFrameDuration": 0.020,
            "MaxRenderingFrameDuration": 0.120,
        }
        result = MODULE.review_event_export_config(export_config)
        for key, value in export_config.items():
            self.assertEqual(result["config"][key], value)


class ArtifactTests(unittest.TestCase):
    def test_metadata_csv_accepts_known_six_header_seven_data_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "metadata.csv"
            path.write_text(
                "ThreadId,Name,Start,End,Duration,DepthMetadata\n"
                '1,"LoadPackageInternal",1.0,1.2,0.2,4,"Package: /Game/UI/A"\n',
                encoding="utf-8",
            )
            result = MODULE.validate_artifact("metadata_csv", path)
            self.assertTrue(result["valid"], result["error"])

    def test_metadata_csv_rejects_rows_without_metadata_column(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "metadata.csv"
            path.write_text(
                "ThreadId,Name,Start,End,Duration,DepthMetadata\n"
                '1,"LoadPackageInternal",1.0,1.2,0.2,4\n',
                encoding="utf-8",
            )
            result = MODULE.validate_artifact("metadata_csv", path)
            self.assertFalse(result["valid"])
            self.assertIn("7 columns", result["error"])

    def test_collect_output_parts_uses_natural_part_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            main = root / "frames.json"
            for path in [main, root / "frames_part10.json", root / "frames_part2.json"]:
                path.write_text("{}\n", encoding="utf-8")
            self.assertEqual(
                [path.name for path in MODULE.collect_output_parts(main)],
                ["frames.json", "frames_part2.json", "frames_part10.json"],
            )

    def test_missing_requested_artifact_fails_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing.json"
            result = MODULE.validate_artifact("timing_events_json", path)
            self.assertFalse(result["valid"])
            self.assertIn("missing", result["error"].lower())

    def test_frame_json_requires_a_known_frame_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "frames.json"
            path.write_text(json.dumps({"frameType": "Unknown"}) + "\n", encoding="utf-8")
            result = MODULE.validate_artifact("frames_json", path)
            self.assertFalse(result["valid"])
            self.assertIn("Game or Rendering", result["error"])

    def test_csv_requires_header_and_data_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "frames.csv"
            path.write_text("FrameType,FrameIndex,Start,End,Duration\n", encoding="utf-8")
            result = MODULE.validate_artifact("frames_csv", path)
            self.assertFalse(result["valid"])
            self.assertIn("data row", result["error"])


if __name__ == "__main__":
    unittest.main()
