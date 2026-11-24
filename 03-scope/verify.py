"""Generate the sample frame and verify the Scope output on known signals."""

import argparse
import json
import math
from pathlib import Path
import subprocess
import sys

from analyze import analyze_frame, write_report


def stripe_frame(width, height, axis, period):
    return bytes(
        round(128 + 75 * math.cos(math.tau * sample / period))
        for row in range(height)
        for column in range(width)
        for sample in (row if axis == "rows" else column,)
    )


def check_peak(report, expected):
    actual = report["peak_cycles_per_row"]
    if actual is None or not math.isclose(actual, expected, rel_tol=0.005):
        raise AssertionError(f"expected {expected:.8f} cycles per row, got {actual}")


def check_video(out, pixels, width, height, roi, expected):
    import cv2
    import numpy as np

    video = out / "synthetic-stripes.avi"
    writer = cv2.VideoWriter(
        str(video), cv2.VideoWriter_fourcc(*"MJPG"), 30, (width, height)
    )
    try:
        if not writer.isOpened():
            raise RuntimeError("OpenCV could not create the synthetic AVI")
        flat = np.full((height, width, 3), 128, dtype=np.uint8)
        gray = np.frombuffer(pixels, dtype=np.uint8).reshape((height, width))
        writer.write(flat)
        writer.write(cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR))
    finally:
        writer.release()

    output = out / "video-scope.json"
    subprocess.run(
        [
            sys.executable, str(Path(__file__).with_name("analyze.py")),
            "--video", str(video), "--frame", "1",
            "--roi", ",".join(map(str, roi)), "--out", str(output),
        ],
        check=True,
    )
    report = json.loads(output.read_text(encoding="utf-8"))
    check_peak(report, expected)
    assert report["frame_index"] == 1 and report["peak_hz"] is None
    print(f"Video CLI recovered {report['peak_cycles_per_row']:.8f} cycles per row")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--video-check", action="store_true",
                        help="also round-trip a two-frame AVI through the OpenCV CLI")
    args = parser.parse_args()

    width, height = 192, 272
    roi = (8, 8, 176, 256)
    period = 16
    frame = stripe_frame(width, height, "rows", period)
    report, bins = analyze_frame(frame, width, height, roi, 0, "rows", None)
    check_peak(report, 1 / period)
    assert report["analysis_axis"] == "rows" and len(report["profile"]) == roi[3]
    assert report["row_time_s"] is None and report["peak_hz"] is None

    vertical = stripe_frame(width, height, "columns", 13.3)
    row_time_s = 20e-6  # Synthetic value to check the conversion arithmetic.
    rotated, _ = analyze_frame(vertical, width, height, roi, 0, "columns", row_time_s)
    check_peak(rotated, 1 / 13.3)
    assert rotated["analysis_axis"] == "columns" and len(rotated["profile"]) == roi[2]
    assert math.isclose(rotated["peak_hz"], 1 / (13.3 * row_time_s), rel_tol=0.005)

    flat = bytes([128]) * (width * height)
    blank, _ = analyze_frame(flat, width, height, roi, 0, "rows", row_time_s)
    assert blank["peak_cycles_per_row"] is None and blank["peak_hz"] is None

    write_report(args.out_dir / "synthetic-scope.json", report, bins)
    sample = args.out_dir / "synthetic-stripes.pgm"
    sample.write_bytes(f"P5\n{width} {height}\n255\n".encode("ascii") + frame)
    print(f"Synthetic fixture recovered {report['peak_cycles_per_row']:.8f} cycles per row")
    print(f"Column fixture recovered {rotated['peak_cycles_per_row']:.8f} cycles per row")
    print("Flat fixture returned a null peak")
    if args.video_check:
        check_video(args.out_dir, frame, width, height, roi, 1 / period)


if __name__ == "__main__":
    main()
