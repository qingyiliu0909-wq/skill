import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "analyze_trace.py"
SPEC = importlib.util.spec_from_file_location("analyze_trace", SCRIPT)
ANALYZE_TRACE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ANALYZE_TRACE)


class AnalyzeFramesTests(unittest.TestCase):
    def test_game_and_rendering_are_summarized_independently(self):
        frames = [
            {"frameType": "Game", "frameIndex": 10, "start": 1.0, "end": 1.010, "duration": 0.010},
            {"frameType": "Game", "frameIndex": 11, "start": 1.010, "end": 1.030, "duration": 0.020},
            {"frameType": "Rendering", "frameIndex": 3, "start": 1.002, "end": 1.032, "duration": 0.030},
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            frame_path = Path(temp_dir) / "frames.json"
            frame_path.write_text(
                "\n".join(json.dumps(frame) for frame in frames),
                encoding="utf-8",
            )
            result = ANALYZE_TRACE.analyze_frames(frame_path, threshold_ms=16)

        self.assertEqual(result["Game"]["count"], 2)
        self.assertEqual(result["Rendering"]["count"], 1)
        self.assertAlmostEqual(result["Game"]["average_ms"], 15.0)
        self.assertEqual(result["Game"]["slow_frames"][0]["frameIndex"], 11)
        self.assertEqual(result["Rendering"]["slow_frames"][0]["frameIndex"], 3)
        self.assertEqual(result["Rendering"]["slow_frames"][0]["frameType"], "Rendering")

    def test_frame_summary_contains_required_percentiles(self):
        frames = [
            {"frameType": "Game", "frameIndex": index, "start": index, "end": index + duration, "duration": duration}
            for index, duration in enumerate([0.010, 0.020, 0.030, 0.100])
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            frame_path = Path(temp_dir) / "frames.json"
            frame_path.write_text("\n".join(json.dumps(frame) for frame in frames), encoding="utf-8")
            summary = ANALYZE_TRACE.analyze_frames(frame_path)["Game"]

        self.assertEqual(summary["median_ms"], 25.0)
        self.assertEqual(summary["p90_ms"], 100.0)
        self.assertEqual(summary["p95_ms"], 100.0)
        self.assertEqual(summary["p99_ms"], 100.0)
        self.assertEqual(summary["max_ms"], 100.0)


class EventSummaryTests(unittest.TestCase):
    def test_summary_includes_distribution_percentiles_and_max(self):
        summary = ANALYZE_TRACE.summarize_by_name(
            {
                "Event": [
                    {"duration": 0.001},
                    {"duration": 0.002},
                    {"duration": 0.003},
                    {"duration": 0.100},
                ]
            }
        )

        self.assertEqual(summary["Event"].get("median"), 0.0025)
        self.assertEqual(summary["Event"].get("p90"), 0.100)
        self.assertEqual(summary["Event"].get("p99"), 0.100)
        self.assertEqual(summary["Event"].get("max"), 0.100)


if __name__ == "__main__":
    unittest.main()
