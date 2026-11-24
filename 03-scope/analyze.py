"""Measure rolling-shutter band spacing in a selected region of one frame."""

import argparse
import csv
import json
import math
from pathlib import Path


def read_video_frame(path, index):
    try:
        import cv2
    except ImportError as error:
        raise ValueError(
            "Video decoding requires OpenCV. Install it with "
            "'python -m pip install opencv-python'."
        ) from error

    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise ValueError(f"cannot open video {path}")
        # Read in presentation order so the index has the same meaning for
        # variable frame rate clips and videos with inter-frame compression.
        for _ in range(index + 1):
            success, frame = capture.read()
            if not success:
                raise ValueError(f"cannot read frame {index} from {path}")
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        height, width = gray.shape
        return gray.tobytes(), width, height
    finally:
        capture.release()


def brightness_profile(pixels, width, height, roi, axis):
    x, y, roi_width, roi_height = roi
    if x < 0 or y < 0 or roi_width < 1 or roi_height < 1:
        raise ValueError("ROI needs nonnegative coordinates and a positive size")
    if x + roi_width > width or y + roi_height > height:
        raise ValueError(f"ROI {roi} extends outside the {width}x{height} frame")

    image = memoryview(pixels)
    rows = [
        image[row * width + x : row * width + x + roi_width]
        for row in range(y, y + roi_height)
    ]
    if axis == "columns":
        return [sum(column) / roi_height for column in zip(*rows)]
    return [sum(row) / roi_width for row in rows]


def spectrum(profile):
    """Return positive-frequency bins and the dominant cycles per sample."""
    count = len(profile)
    if count < 8:
        raise ValueError("ROI needs at least 8 pixels along the analysis axis")

    mean = sum(profile) / count
    center = (count - 1) / 2
    offsets = [index - center for index in range(count)]
    slope = sum(offset * (value - mean) for offset, value in zip(offsets, profile))
    slope /= sum(offset * offset for offset in offsets)
    residuals = [
        value - mean - slope * offset for value, offset in zip(profile, offsets)
    ]
    window = [0.5 - 0.5 * math.cos(math.tau * i / (count - 1)) for i in range(count)]
    weighted = [residual * weight for residual, weight in zip(residuals, window)]
    normalization = sum(window)

    # Goertzel computes each DFT bin with one recurrence over the profile.
    magnitudes = []
    for bin_index in range(1, count // 2 + 1):
        angle = math.tau * bin_index / count
        cosine, sine = math.cos(angle), math.sin(angle)
        coefficient = 2 * cosine
        previous = before_previous = 0.0
        for sample in weighted:
            current = sample + coefficient * previous - before_previous
            before_previous, previous = previous, current
        magnitude = math.hypot(
            previous - cosine * before_previous, sine * before_previous
        )
        magnitudes.append(magnitude / normalization)

    bins = [(index / count, value) for index, value in enumerate(magnitudes, 1)]
    if max(abs(residual) for residual in residuals) < 1e-9:
        return bins, None

    peak_index = max(range(len(magnitudes)), key=magnitudes.__getitem__)
    peak_bin = peak_index + 1.0
    # Interpolate between bins for a peak bracketed on both sides.
    if 0 < peak_index < len(magnitudes) - 1:
        left, middle, right = [
            math.log(max(value, 1e-12))
            for value in magnitudes[peak_index - 1 : peak_index + 2]
        ]
        curvature = left - 2 * middle + right
        if curvature < 0:
            peak_bin += 0.5 * (left - right) / curvature
    return bins, peak_bin / count


def analyze_frame(pixels, width, height, roi, frame_index, axis, row_time_s):
    profile = brightness_profile(pixels, width, height, roi, axis)
    bins, peak = spectrum(profile)
    peak_hz = None
    if peak is not None and row_time_s is not None:
        peak_hz = peak / row_time_s
        if not math.isfinite(peak_hz):
            raise ValueError("row timing gives a frequency outside numeric range")
    report = {
        "frame_index": frame_index,
        "analysis_axis": axis,
        "profile": profile,
        "peak_cycles_per_row": peak,
        "row_time_s": row_time_s,
        "peak_hz": peak_hz,
    }
    return report, bins


def write_report(path, report, bins):
    path.parent.mkdir(parents=True, exist_ok=True)
    profile_path = path.with_name(f"{path.stem}-profile.csv")
    spectrum_path = path.with_name(f"{path.stem}-spectrum.csv")
    with profile_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(("sample_index", "mean_luma"))
        writer.writerows(enumerate(report["profile"]))
    with spectrum_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(("cycles_per_row", "magnitude"))
        writer.writerows(bins)
    plot_path = path.with_name(f"{path.stem}-plots.svg")
    plot_path.write_text(render_plots(report, bins), encoding="utf-8")
    path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def render_plots(report, bins):
    axis_name = "Column" if report["analysis_axis"] == "columns" else "Row"
    profile = list(enumerate(report["profile"]))
    peak = report["peak_cycles_per_row"]
    caption = "No spectral peak" if peak is None else f"Peak at {peak:.5g} cycles per row"
    if report["peak_hz"] is not None:
        caption += f" ({report['peak_hz']:.5g} Hz)"
    panels = [
        (profile, 82, len(profile) - 1, 255, f"{axis_name} index within ROI", "Mean luma"),
        (bins, 348, 0.5, max(value for _, value in bins) or 1, "Cycles per row", "Magnitude"),
    ]
    svg = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 740 620" role="img">',
        '<title>Rolling-shutter brightness profile and spectrum</title>',
        '<rect width="740" height="620" fill="white"/>',
        '<g font-family="sans-serif" font-size="14" fill="#182230">',
        f'<text x="30" y="34" font-size="20">Frame {report["frame_index"]} · {caption}</text>',
    ]
    for samples, top, x_max, y_max, x_label, y_label in panels:
        left, plot_width, plot_height = 78, 622, 170
        bottom = top + plot_height
        svg.append(f'<text x="{left}" y="{top - 12}">{y_label}</text>')
        for step in range(5):
            fraction = step / 4
            y = bottom - fraction * plot_height
            x = left + fraction * plot_width
            svg.extend([
                f'<path d="M{left} {y}h{plot_width}" stroke="#d8dee6"/>',
                f'<text x="{left - 8}" y="{y + 5}" text-anchor="end">{fraction * y_max:.3g}</text>',
                f'<text x="{x}" y="{bottom + 20}" text-anchor="middle">{fraction * x_max:.4g}</text>',
            ])
        points = " ".join(
            f"{left + x / x_max * plot_width:.2f},{bottom - y / y_max * plot_height:.2f}"
            for x, y in samples
        )
        svg.append(f'<polyline points="{points}" fill="none" stroke="#215ea8" stroke-width="2"/>')
        if x_label == "Cycles per row" and peak is not None:
            peak_x = left + peak / x_max * plot_width
            svg.append(f'<path d="M{peak_x} {top}v{plot_height}" stroke="#a33c24" stroke-dasharray="5 4"/>')
        svg.append(f'<text x="{left + plot_width / 2}" y="{bottom + 45}" text-anchor="middle">{x_label}</text>')
    svg.append("</g></svg>\n")
    return "\n".join(svg)


def parse_roi(value):
    try:
        x, y, width, height = map(int, value.split(","))
    except ValueError as error:
        raise argparse.ArgumentTypeError("ROI must be four integers: x,y,w,h") from error
    return x, y, width, height


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--frame", type=int, default=0, help="zero-based decoded frame index")
    parser.add_argument("--roi", type=parse_roi, required=True, metavar="X,Y,W,H")
    parser.add_argument("--axis", choices=["rows", "columns"], default="rows",
                        help="use columns if sensor rows map to decoded image columns")
    parser.add_argument("--row-time-s", type=float,
                        help="calibrated seconds per sample along the analysis axis")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.frame < 0:
        parser.error("--frame must be nonnegative")
    if args.row_time_s is not None and (
        not math.isfinite(args.row_time_s) or args.row_time_s <= 0
    ):
        parser.error("--row-time-s must be finite and positive")
    if args.video.resolve() == args.out.resolve():
        parser.error("--out must differ from the input video path")

    try:
        pixels, width, height = read_video_frame(args.video, args.frame)
        report, bins = analyze_frame(
            pixels, width, height, args.roi, args.frame, args.axis, args.row_time_s
        )
        write_report(args.out, report, bins)
    except (ValueError, OSError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
