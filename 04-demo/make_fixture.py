"""Generate a deterministic synthetic screen recording of one packet.

Writes a video plus a sidecar JSON (<out>.truth.json) with the ROI, expected payload
and exact symbol timing, so the receiver can be tested end to end without a phone.

Example (from the project root):
    python 04-demo/make_fixture.py --out 04-demo/fixtures/synth_clean.mp4
    python 04-demo/make_fixture.py --out 04-demo/fixtures/synth_noisy.mp4 --noise 12 --fps 29.97 --blur 5
"""
import argparse
import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from protocol import (GRAY_IDLE, GRAY_ONE, GRAY_ZERO, SYMBOL_MS, build_packet,  # noqa: E402
                      bytes_to_bits, load_reference)


def main():
    ref_payload, _ = load_reference()
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", required=True, help="output video path (.mp4 or .avi)")
    p.add_argument("--payload", default=ref_payload)
    p.add_argument("--fps", type=float, default=30.0)
    p.add_argument("--width", type=int, default=640)
    p.add_argument("--height", type=int, default=480)
    p.add_argument("--roi", default="220,140,200,200", help="patch rectangle x,y,w,h")
    p.add_argument("--idle-before-s", type=float, default=1.517, help="idle before first symbol (not frame-aligned on purpose)")
    p.add_argument("--idle-after-s", type=float, default=1.5)
    p.add_argument("--noise", type=float, default=0.0, help="Gaussian noise sigma in gray levels")
    p.add_argument("--blur", type=int, default=0, help="odd kernel size for blur, 0 = off")
    p.add_argument("--gain", type=float, default=1.0, help="brightness gain, simulates camera exposure")
    p.add_argument("--offset", type=float, default=0.0, help="brightness offset")
    p.add_argument("--seed", type=int, default=1)
    a = p.parse_args()

    x, y, w, h = [int(v) for v in a.roi.split(",")]
    packet = build_packet(a.payload)
    bits = bytes_to_bits(packet)
    sym_s = SYMBOL_MS / 1000.0
    start_s = a.idle_before_s
    end_s = start_s + len(bits) * sym_s
    total_s = end_s + a.idle_after_s
    n_frames = int(round(total_s * a.fps))

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*("MJPG" if a.out.lower().endswith(".avi") else "mp4v"))
    writer = cv2.VideoWriter(a.out, fourcc, a.fps, (a.width, a.height))
    if not writer.isOpened():
        sys.exit("could not open VideoWriter for " + a.out)

    rng = np.random.default_rng(a.seed)
    for i in range(n_frames):
        t = i / a.fps
        if start_s <= t < end_s:
            level = GRAY_ONE if bits[int((t - start_s) / sym_s)] else GRAY_ZERO
        else:
            level = GRAY_IDLE
        frame = np.full((a.height, a.width), 24.0, np.float32)  # dark surroundings
        frame[y:y + h, x:x + w] = level
        frame = frame * a.gain + a.offset
        if a.blur:
            frame = cv2.GaussianBlur(frame, (a.blur, a.blur), 0)
        if a.noise:
            frame += rng.normal(0, a.noise, frame.shape).astype(np.float32)
        frame = np.clip(frame, 0, 255).astype(np.uint8)
        writer.write(cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR))
    writer.release()

    truth = {
        "video": os.path.basename(a.out),
        "synthetic": True,
        "payload_ascii": a.payload,
        "packet_hex": packet.hex(),
        "roi": [x, y, w, h],
        "fps": a.fps,
        "symbol_ms": SYMBOL_MS,
        "packet_start_s": round(start_s, 6),
        "packet_end_s": round(end_s, 6),
        "duration_s": round(n_frames / a.fps, 6),
        "params": {k: v for k, v in vars(a).items() if k != "out"},
    }
    with open(a.out + ".truth.json", "w") as f:
        json.dump(truth, f, indent=2)
    print("wrote %s (%d frames, %.2f s) and %s.truth.json" % (a.out, n_frames, n_frames / a.fps, a.out))
    print("roi: %d,%d,%d,%d" % (x, y, w, h))


if __name__ == "__main__":
    main()
