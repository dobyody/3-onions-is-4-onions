"""Generate a SYNTHETIC rolling-shutter stripe clip with a known period (in rows).

Use it to check 03-scope/analyze.py and as the clearly labeled fallback for the scope
part of the demo if real screens give no reliable stripes.

    python 04-demo/make_stripes.py --out 04-demo/fixtures/synth_stripes.mp4 --period-rows 37.5
"""
import argparse
import json
import os
import sys

import cv2
import numpy as np


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", required=True)
    p.add_argument("--period-rows", type=float, default=37.5)
    p.add_argument("--width", type=int, default=640)
    p.add_argument("--height", type=int, default=480)
    p.add_argument("--frames", type=int, default=30)
    p.add_argument("--fps", type=float, default=30.0)
    p.add_argument("--depth", type=float, default=40.0, help="stripe amplitude in gray levels")
    p.add_argument("--noise", type=float, default=4.0)
    p.add_argument("--row-time-s", type=float, default=None,
                   help="optional pretend row time; only recorded in truth to test Hz conversion")
    p.add_argument("--seed", type=int, default=3)
    a = p.parse_args()

    rng = np.random.default_rng(a.seed)
    rows = np.arange(a.height)[:, None]
    cols = np.arange(a.width)[None, :]
    vignette = 1.0 - 0.25 * ((cols - a.width / 2) / (a.width / 2)) ** 2  # uneven lighting across columns
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*("MJPG" if a.out.lower().endswith(".avi") else "mp4v"))
    w = cv2.VideoWriter(a.out, fourcc, a.fps, (a.width, a.height))
    if not w.isOpened():
        sys.exit("could not open VideoWriter for " + a.out)
    for i in range(a.frames):
        phase = 2 * np.pi * 0.37 * i  # stripes drift between frames, as with a real free-running source
        img = (120 + a.depth * np.sin(2 * np.pi * rows / a.period_rows + phase)) * vignette
        img = img + rng.normal(0, a.noise, (a.height, a.width))
        g = np.clip(img, 0, 255).astype(np.uint8)
        w.write(cv2.cvtColor(g, cv2.COLOR_GRAY2BGR))
    w.release()
    truth = {"video": os.path.basename(a.out), "synthetic": True, "period_rows": a.period_rows,
             "cycles_per_row": 1.0 / a.period_rows, "roi": [0, 0, a.width, a.height], "analysis_axis": "rows (image y)",
             "row_time_s": a.row_time_s,
             "hz_if_row_time": (1.0 / a.period_rows / a.row_time_s) if a.row_time_s else None}
    with open(a.out + ".truth.json", "w") as f:
        json.dump(truth, f, indent=2)
    print("wrote %s: period %.2f rows = %.5f cycles/row (SYNTHETIC)" % (a.out, a.period_rows, 1 / a.period_rows))


if __name__ == "__main__":
    main()
