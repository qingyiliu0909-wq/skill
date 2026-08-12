import sys
import os
from pathlib import Path

print("Step 1: Importing module")
sys.path.insert(0, str(Path(__file__).parent))

print("Step 2: Importing compare_directories")
from check_missing_only import compare_directories, format_report

print("Step 3: Setting up paths")
dir_a = Path(r"C:\Pan01\demo\EM_Build\ExportDatas\datas")
dir_b = Path(r"D:\OBT1.4Geili\EM\ExportDatas\datas")

print(f"Comparing: {dir_a} vs {dir_b}")

print("Step 4: Running compare_directories...")
diffs = compare_directories(dir_a, dir_b)

print(f"Step 5: Found {len(diffs)} missing items")

# Write result to file
output_path = os.path.join(os.path.dirname(__file__), "missing_result.txt")
report = format_report(diffs, dir_a, dir_b)

with open(output_path, "w", encoding="utf-8") as f:
    f.write(report)

print(f"Step 6: Result saved to: {output_path}")