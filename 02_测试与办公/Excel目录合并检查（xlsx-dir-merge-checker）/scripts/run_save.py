import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from compare_dirs import compare_directories, format_report

dir_a = Path(r"C:\Pan01\demo\EM_Build\ExportDatas\datas")
dir_b = Path(r"D:\OBT1.4Geili\EM\ExportDatas\datas")

diffs = compare_directories(dir_a=dir_a, dir_b=dir_b, glob_pattern="**/*.xlsx", svn_lookup=False, svn_log_limit=80)

report = format_report(diffs, dir_a, dir_b)

# 确保目录存在
script_dir = os.path.dirname(__file__)
output_path = os.path.join(script_dir, "result.txt")

with open(output_path, "w", encoding="utf-8") as f:
    f.write(report)

print(f"Result written to: {output_path}")
print(f"Total diffs: {len(diffs)}")