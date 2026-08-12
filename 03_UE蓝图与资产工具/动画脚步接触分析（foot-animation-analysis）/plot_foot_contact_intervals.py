from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from xml.sax.saxutils import escape


CONFIG_PATH = Path(__file__).with_name("Config.md")


def load_project_root(config_path: Path) -> Path:
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    content = config_path.read_text(encoding="utf-8")
    match = re.search(r"\{Project_Root\}\s*:\s*(.+)", content)
    if not match:
        raise ValueError(f"Project_Root not found in config: {config_path}")

    project_root = match.group(1).strip()
    if not project_root:
        raise ValueError(f"Project_Root is empty in config: {config_path}")

    return Path(project_root)


ROOT = load_project_root(CONFIG_PATH)
DATA_DIR = ROOT / "Saved"


def load_track(data_dir: Path, file_name: str):
    data = json.loads((data_dir / file_name).read_text(encoding="utf-8"))
    frames = []
    z_values = []
    for keyframe in data["TrackData"]["Keyframes"]:
        frames.append(int(keyframe["FrameIndex"]))
        z_values.append(float(keyframe["Translation"]["Z"]))
    return data["BoneName"], frames, z_values


def should_keep_contact_run(start_index: int, end_index_exclusive: int, total_frames: int, min_run_length: int) -> bool:
    run_length = end_index_exclusive - start_index
    return run_length >= min_run_length or start_index == 0 or end_index_exclusive == total_frames


def detect_contact_intervals(frames: list[int], z_values: list[float], threshold_margin: float = 1.0, min_run_length: int = 3):
    min_z = min(z_values)
    threshold = min_z + threshold_margin
    in_contact = [z <= threshold for z in z_values]

    intervals: list[tuple[int, int]] = []
    start_index: int | None = None

    for index, is_contact in enumerate(in_contact):
        if is_contact and start_index is None:
            start_index = index
        elif not is_contact and start_index is not None:
            if should_keep_contact_run(start_index, index, len(frames), min_run_length):
                intervals.append((frames[start_index], frames[index - 1]))
            start_index = None

    if start_index is not None and should_keep_contact_run(start_index, len(frames), len(frames), min_run_length):
        intervals.append((frames[start_index], frames[-1]))

    lift_off_frames: list[int] = []
    for start_frame, end_frame in intervals:
        end_index = frames.index(end_frame)
        if end_index + 1 < len(frames):
            lift_off_frames.append(frames[end_index + 1])

    return threshold, intervals, lift_off_frames


def expand_contact_windows(
    frames: list[int],
    z_values: list[float],
    stable_intervals: list[tuple[int, int]],
    window_margin: float = 2.0,
):
    window_threshold, window_pairs = build_contact_window_pairs(frames, z_values, stable_intervals, window_margin)

    windows = [window for window, _stable_interval in window_pairs]

    merged_windows: list[tuple[int, int]] = []
    for start_frame, end_frame in windows:
        if not merged_windows or start_frame > merged_windows[-1][1] + 1:
            merged_windows.append((start_frame, end_frame))
        else:
            merged_windows[-1] = (merged_windows[-1][0], max(merged_windows[-1][1], end_frame))

    return window_threshold, merged_windows


def build_contact_window_pairs(
    frames: list[int],
    z_values: list[float],
    stable_intervals: list[tuple[int, int]],
    window_margin: float = 2.0,
):
    min_z = min(z_values)
    window_threshold = min_z + window_margin

    window_pairs: list[tuple[tuple[int, int], tuple[int, int]]] = []
    for start_frame, end_frame in stable_intervals:
        start_index = frames.index(start_frame)
        end_index = frames.index(end_frame)

        while start_index > 0 and z_values[start_index - 1] <= window_threshold:
            start_index -= 1

        while end_index + 1 < len(frames) and z_values[end_index + 1] <= window_threshold:
            end_index += 1

        window_pairs.append(((frames[start_index], frames[end_index]), (start_frame, end_frame)))

    return window_threshold, window_pairs


def calculate_interval_alpha(frame: int, window_interval: tuple[int, int], stable_interval: tuple[int, int]) -> float:
    window_start, window_end = window_interval
    stable_start, stable_end = stable_interval

    if frame < window_start or frame > window_end:
        return 0.0

    if stable_start <= frame <= stable_end:
        return 1.0

    if frame < stable_start:
        transition_length = stable_start - window_start
        if transition_length <= 0:
            return 1.0
        return max(0.0, min(1.0, (frame - window_start) / transition_length))

    transition_length = window_end - stable_end
    if transition_length <= 0:
        return 1.0
    return max(0.0, min(1.0, (window_end - frame) / transition_length))


def build_frame_alpha_rows(
    frames: list[int],
    window_pairs: list[tuple[tuple[int, int], tuple[int, int]]],
):
    rows: list[tuple[int, float]] = []
    for frame in frames:
        alpha = 0.0
        for window_interval, stable_interval in window_pairs:
            alpha = max(alpha, calculate_interval_alpha(frame, window_interval, stable_interval))
        rows.append((frame, alpha))
    return rows


def write_alpha_txt(
    output_path: Path,
    asset_name: str,
    frames: list[int],
    left_name: str,
    left_window_pairs: list[tuple[tuple[int, int], tuple[int, int]]],
    right_name: str,
    right_window_pairs: list[tuple[tuple[int, int], tuple[int, int]]],
):
    all_frames = sorted(set(frames))
    left_alpha_rows = build_frame_alpha_rows(all_frames, left_window_pairs)
    right_alpha_rows = build_frame_alpha_rows(all_frames, right_window_pairs)
    left_rows = dict(left_alpha_rows)
    right_rows = dict(right_alpha_rows)
    left_airborne_frames, left_landing_frames = detect_alpha_events(left_alpha_rows)
    right_airborne_frames, right_landing_frames = detect_alpha_events(right_alpha_rows)

    lines: list[str] = []
    lines.append(f"# {asset_name} foot alpha data")
    lines.append("# Alpha = 0 means fully airborne, Alpha = 1 means fully grounded")
    lines.append("# Transition uses the analyzed contact window around each stable contact interval")
    lines.append(f"# Left foot: {left_name}")
    lines.append(f"# Right foot: {right_name}")
    lines.append(f"# {left_name} fully airborne starts: {format_frame_list(left_airborne_frames)}")
    lines.append(f"# {left_name} start landing frames: {format_frame_list(left_landing_frames)}")
    lines.append(f"# {right_name} fully airborne starts: {format_frame_list(right_airborne_frames)}")
    lines.append(f"# {right_name} start landing frames: {format_frame_list(right_landing_frames)}")
    lines.append(f"Frame\t{left_name}\t{right_name}")

    for frame in all_frames:
        left_alpha = left_rows.get(frame, 0.0)
        right_alpha = right_rows.get(frame, 0.0)
        lines.append(f"{frame}\t{left_alpha:.6f}\t{right_alpha:.6f}")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def detect_alpha_events(rows: list[tuple[int, float]], epsilon: float = 1e-6):
    fully_airborne_frames: list[int] = []
    start_landing_frames: list[int] = []
    previous_alpha: float | None = None

    for frame, alpha in rows:
        is_airborne = alpha <= epsilon
        was_airborne = previous_alpha is not None and previous_alpha <= epsilon

        if is_airborne and (previous_alpha is None or previous_alpha > epsilon):
            fully_airborne_frames.append(frame)

        if alpha > epsilon and was_airborne:
            start_landing_frames.append(frame)

        previous_alpha = alpha

    return fully_airborne_frames, start_landing_frames


def format_frame_list(frames: list[int]) -> str:
    return ", ".join(str(frame) for frame in frames) if frames else "none"


def build_output_paths(data_dir: Path, asset_name: str):
    return (
        data_dir / f"{asset_name}_foot_contact_intervals.svg",
        data_dir / f"{asset_name}_foot_alpha_temp.txt",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze ik_foot_l and ik_foot_r contact data and generate alpha output.")
    parser.add_argument("--asset-name", default="Heitao_Walk_Loop", help="Animation asset short name used to resolve Saved json files.")
    parser.add_argument("--saved-dir", default=str(DATA_DIR), help="Directory containing exported foot json files.")
    return parser.parse_args()


def svg_text(x: float, y: float, text: str, size: int = 12, color: str = "#111111", anchor: str = "start", rotate: float | None = None) -> str:
    transform = f' transform="rotate({rotate} {x} {y})"' if rotate is not None else ""
    return (
        f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" fill="{color}" '
        f'text-anchor="{anchor}" font-family="Arial, Helvetica, sans-serif"{transform}>'
        f"{escape(text)}"
        "</text>"
    )


def make_panel(*, title: str, bone_name: str, frames: list[int], z_values: list[float], line_color: str, window_fill_color: str, stable_fill_color: str, windows: list[tuple[int, int]], stable_intervals: list[tuple[int, int]], lift_off_frames: list[int], note: str, panel_top: int, panel_left: int, panel_width: int, panel_height: int) -> str:
    margin_left = 64
    margin_right = 20
    margin_top = 34
    margin_bottom = 48
    plot_left = panel_left + margin_left
    plot_top = panel_top + margin_top
    plot_width = panel_width - margin_left - margin_right
    plot_height = panel_height - margin_top - margin_bottom

    min_frame = min(frames)
    max_frame = max(frames)
    min_z = min(z_values)
    max_z = max(z_values)
    threshold = min_z + 1.0
    y_min = min(min_z - 0.8, threshold - 0.8)
    y_max = max(max_z + 0.8, threshold + 0.8)

    def map_x(frame: float) -> float:
        return plot_left + (frame - min_frame) / (max_frame - min_frame) * plot_width

    def map_y(z: float) -> float:
        return plot_top + (y_max - z) / (y_max - y_min) * plot_height

    parts: list[str] = []
    parts.append(f'<rect x="{panel_left}" y="{panel_top}" width="{panel_width}" height="{panel_height}" rx="16" fill="#ffffff" stroke="#d6dbe5"/>')
    parts.append(svg_text(panel_left + 18, panel_top + 24, title, size=18, color="#111827"))
    parts.append(svg_text(panel_left + 18, panel_top + 44, f"判定阈值: Z <= {threshold:.2f}", size=11, color="#4b5563"))

    for tick in range(min_frame, max_frame + 1, 5):
        x = map_x(tick)
        parts.append(f'<line x1="{x:.2f}" y1="{plot_top}" x2="{x:.2f}" y2="{plot_top + plot_height}" stroke="#edf0f5" stroke-width="1"/>')
        parts.append(svg_text(x, plot_top + plot_height + 18, str(tick), size=10, color="#6b7280", anchor="middle"))

    y_tick_step = 2.0
    y_tick = y_min - (y_min % y_tick_step)
    if y_tick < y_min:
        y_tick += y_tick_step
    while y_tick <= y_max + 1e-6:
        y = map_y(y_tick)
        parts.append(f'<line x1="{plot_left}" y1="{y:.2f}" x2="{plot_left + plot_width}" y2="{y:.2f}" stroke="#edf0f5" stroke-width="1"/>')
        parts.append(svg_text(plot_left - 10, y + 4, f"{y_tick:.1f}", size=10, color="#6b7280", anchor="end"))
        y_tick += y_tick_step

    parts.append(f'<line x1="{plot_left}" y1="{plot_top + plot_height}" x2="{plot_left + plot_width}" y2="{plot_top + plot_height}" stroke="#364152" stroke-width="1.4"/>')
    parts.append(f'<line x1="{plot_left}" y1="{plot_top}" x2="{plot_left}" y2="{plot_top + plot_height}" stroke="#364152" stroke-width="1.4"/>')

    y_threshold = map_y(threshold)
    parts.append(f'<line x1="{plot_left}" y1="{y_threshold:.2f}" x2="{plot_left + plot_width}" y2="{y_threshold:.2f}" stroke="#6b7280" stroke-width="1.5" stroke-dasharray="6,5"/>')

    for start_frame, end_frame in windows:
        x1 = map_x(start_frame)
        x2 = map_x(end_frame)
        parts.append(f'<rect x="{x1:.2f}" y="{plot_top}" width="{(x2 - x1):.2f}" height="{plot_height}" fill="{window_fill_color}" opacity="0.45"/>')
        parts.append(svg_text((x1 + x2) / 2, plot_top + 16, f"接触窗口 {start_frame}-{end_frame}", size=10, color="#1f2937", anchor="middle"))

    for start_frame, end_frame in stable_intervals:
        x1 = map_x(start_frame)
        x2 = map_x(end_frame)
        parts.append(f'<rect x="{x1:.2f}" y="{plot_top}" width="{(x2 - x1):.2f}" height="{plot_height}" fill="{stable_fill_color}" opacity="0.85"/>')
        parts.append(svg_text((x1 + x2) / 2, plot_top + 32, f"稳定接地 {start_frame}-{end_frame}", size=11, color="#1f2937", anchor="middle"))

    for lift_frame in lift_off_frames:
        x = map_x(lift_frame)
        parts.append(f'<line x1="{x:.2f}" y1="{plot_top}" x2="{x:.2f}" y2="{plot_top + plot_height}" stroke="#111827" stroke-width="1.2" stroke-dasharray="2,4"/>')
        parts.append(svg_text(x + 4, plot_top + plot_height - 8, f"开始离地 {lift_frame}", size=10, color="#111827", rotate=-90))

    points = " ".join(f"{map_x(frame):.2f},{map_y(z):.2f}" for frame, z in zip(frames, z_values))
    parts.append(f'<polyline points="{points}" fill="none" stroke="{line_color}" stroke-width="2.8" stroke-linejoin="round" stroke-linecap="round"/>')

    for frame, z in zip(frames, z_values):
        x = map_x(frame)
        y = map_y(z)
        parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.4" fill="{line_color}"/>')

    parts.append(svg_text(plot_left - 46, plot_top + plot_height / 2, "Z 高度", size=11, color="#4b5563", anchor="middle", rotate=-90))
    parts.append(svg_text(plot_left + plot_width / 2, panel_top + panel_height - 14, "Frame", size=11, color="#4b5563", anchor="middle"))
    parts.append(
        f'<rect x="{panel_left + 16}" y="{panel_top + panel_height - 40}" width="{panel_width - 32}" height="24" rx="8" fill="#f7f7f7" stroke="#e5e7eb"/>'
    )
    parts.append(svg_text(panel_left + 28, panel_top + panel_height - 23, note, size=10, color="#4b5563"))

    return "\n".join(parts)


def main() -> None:
    args = parse_args()
    data_dir = Path(args.saved_dir)
    asset_name = args.asset_name
    output_path, alpha_output_path = build_output_paths(data_dir, asset_name)

    left_name, left_frames, left_z = load_track(data_dir, f"{asset_name}_ik_foot_l.Json")
    right_name, right_frames, right_z = load_track(data_dir, f"{asset_name}_ik_foot_r.Json")

    left_threshold, left_intervals, left_lift_off_frames = detect_contact_intervals(left_frames, left_z)
    right_threshold, right_intervals, right_lift_off_frames = detect_contact_intervals(right_frames, right_z)

    left_window_threshold, left_window_pairs = build_contact_window_pairs(left_frames, left_z, left_intervals)
    right_window_threshold, right_window_pairs = build_contact_window_pairs(right_frames, right_z, right_intervals)

    left_window_threshold, left_windows = expand_contact_windows(left_frames, left_z, left_intervals)
    right_window_threshold, right_windows = expand_contact_windows(right_frames, right_z, right_intervals)

    all_frames = sorted(set(left_frames) | set(right_frames))
    write_alpha_txt(
        alpha_output_path,
        asset_name,
        all_frames,
        left_name,
        left_window_pairs,
        right_name,
        right_window_pairs,
    )

    intervals = {
        left_name: left_intervals,
        right_name: right_intervals,
    }
    lift_off_frames = {
        left_name: left_lift_off_frames,
        right_name: right_lift_off_frames,
    }

    left_panel = make_panel(
        title=f"{left_name} - 接地/离地区间图",
        bone_name=left_name,
        frames=left_frames,
        z_values=left_z,
        line_color="#2b6cb0",
        window_fill_color="#dbeafe",
        stable_fill_color="#93c5fd",
        windows=left_windows,
        stable_intervals=intervals[left_name],
        lift_off_frames=lift_off_frames[left_name],
        note=f"浅色=Z <= {left_window_threshold:.2f} 的接触窗口，深色=Z <= {left_threshold:.2f} 的稳定接地。",
        panel_top=74,
        panel_left=24,
        panel_width=1352,
        panel_height=300,
    )
    right_panel = make_panel(
        title=f"{right_name} - 接地/离地区间图",
        bone_name=right_name,
        frames=right_frames,
        z_values=right_z,
        line_color="#c05621",
        window_fill_color="#fed7aa",
        stable_fill_color="#fdba74",
        windows=right_windows,
        stable_intervals=intervals[right_name],
        lift_off_frames=lift_off_frames[right_name],
        note=f"浅色=Z <= {right_window_threshold:.2f} 的接触窗口，深色=Z <= {right_threshold:.2f} 的稳定接地。",
        panel_top=394,
        panel_left=24,
        panel_width=1352,
        panel_height=300,
    )

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="720" viewBox="0 0 1400 720">
<rect x="0" y="0" width="1400" height="720" fill="#f3f4f6"/>
<text x="700" y="38" font-size="22" font-family="Arial, Helvetica, sans-serif" text-anchor="middle" fill="#111827">{asset_name} 左右脚 Z 轴轨迹与接地判定</text>
<text x="700" y="60" font-size="11" font-family="Arial, Helvetica, sans-serif" text-anchor="middle" fill="#4b5563">判定口径：浅色接触窗口 + 深色稳定接地平台 + 首次连续上升视为开始离地</text>
{left_panel}
{right_panel}
<rect x="24" y="686" width="1352" height="24" rx="8" fill="#ffffff" stroke="#d6dbe5"/>
<text x="40" y="703" font-size="10" font-family="Arial, Helvetica, sans-serif" fill="#4b5563">说明：浅色表示接触窗口，深色表示稳定接地平台，虚线表示 Z 高度阈值，竖虚线表示开始离地帧。</text>
</svg>'''

    output_path.write_text(svg, encoding="utf-8")
    left_alpha_rows = build_frame_alpha_rows(all_frames, left_window_pairs)
    right_alpha_rows = build_frame_alpha_rows(all_frames, right_window_pairs)
    left_airborne_frames, left_landing_frames = detect_alpha_events(left_alpha_rows)
    right_airborne_frames, right_landing_frames = detect_alpha_events(right_alpha_rows)

    print(f"Saved to: {output_path}")
    print(f"Saved alpha to: {alpha_output_path}")
    print(f"Left foot contact: {left_intervals}, lift-off at {left_lift_off_frames}")
    print(f"Right foot contact: {right_intervals}, lift-off at {right_lift_off_frames}")
    print(f"Left foot fully airborne starts at frames: {format_frame_list(left_airborne_frames)}")
    print(f"Left foot starts landing at frames: {format_frame_list(left_landing_frames)}")
    print(f"Right foot fully airborne starts at frames: {format_frame_list(right_airborne_frames)}")
    print(f"Right foot starts landing at frames: {format_frame_list(right_landing_frames)}")


if __name__ == "__main__":
    main()