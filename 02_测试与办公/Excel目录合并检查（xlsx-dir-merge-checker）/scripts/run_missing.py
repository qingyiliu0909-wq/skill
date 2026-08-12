import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from check_missing_only import compare_directories, format_report

dir_a = Path(r"C:\Pan01\demo\EM_Build\ExportDatas\datas")
dir_b = Path(r"D:\OBT1.4Geili\EM\ExportDatas\datas")

diffs = compare_directories(dir_a, dir_b)
report = format_report(diffs, dir_a, dir_b)

output_path = Path(__file__).parent / "missing_only_result.txt"
with open(output_path, "w", encoding="utf-8") as f:
    f.write(report)

print(f"Result written to: {output_path}")
print(f"Total missing: {len(diffs)}")