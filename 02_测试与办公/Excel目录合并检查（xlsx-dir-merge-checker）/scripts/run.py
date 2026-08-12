import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from compare_dirs import compare_directories, format_report

dir_a = Path(r"C:\Pan01\demo\EM_Build\ExportDatas\datas")
dir_b = Path(r"D:\OBT1.4Geili\EM\ExportDatas\datas")

diffs = compare_directories(dir_a=dir_a, dir_b=dir_b, glob_pattern="**/*.xlsx", svn_lookup=False, svn_log_limit=80)

report = format_report(diffs, dir_a, dir_b)
sys.stderr.write(report)
sys.stderr.write("\n")
sys.stderr.flush()