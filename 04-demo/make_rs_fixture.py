"""Synthetic rolling-shutter frame fixture for protocol v2 (independent of transmitter and receiver code).

Simulates a light that runs the v2 carousel (protocol2.py) and a rolling-shutter camera: row r of
frame f is exposed from t_f + r*row_time for exposure_us, so successive rows see successive chips.

  python3 04-demo/make_rs_fixture.py --out 04-demo/fixtures/rs_clean.npz
  python3 04-demo/make_rs_fixture.py --out 04-demo/fixtures/rs_hard.npz --depth 0.08 --noise 8 --jpeg 60 --drop 0.2 --orientation 90
  python3 04-demo/make_rs_fixture.py --out 04-demo/fixtures/rs_constant.npz --mode constant   # control: no packet

Writes <out> (frames, frame_id, capture_ts_s, orientation) and <out>.truth.json. --png also writes
one sample frame next to it, and --mp4 a video copy for live.py --video (lossy, for transport tests).
"""
import argparse
import json
import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import protocol2 as p2  # noqa: E402


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", required=True)
    p.add_argument("--message", default=p2.REFERENCE_MESSAGE)
    p.add_argument("--msg-id", type=int, default=1)
    p.add_argument("--mode", choices=["carousel", "constant", "steady"], default="carousel",
                   help="constant = light held at the bright symbol level; steady = mean level, no data")
    p.add_argument("--height", type=int, default=1080, help="sensor rows")
    p.add_argument("--width", type=int, default=160)
    p.add_argument("--fps", type=float, default=30.0)
    p.add_argument("--frames", type=int, default=120)
    p.add_argument("--row-time-us", type=float, default=28.0)
    p.add_argument("--exposure-us", type=float, default=30.0)
    p.add_argument("--chip-us", type=float, default=p2.CHIP_US)
    p.add_argument("--depth", type=float, default=0.25, help="chip level = mean * (1 +/- depth)")
    p.add_argument("--send-s", type=float, default=0.5, help="time of the Send click")
    p.add_argument("--noise", type=float, default=3.0)
    p.add_argument("--jpeg", type=int, default=85, help="JPEG quality per frame (0 = none)")
    p.add_argument("--drop", type=float, default=0.0, help="fraction of frames lost in transport")
    p.add_argument("--orientation", type=int, choices=[0, 90, 180, 270], default=0)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--png", action="store_true")
    p.add_argument("--mp4", action="store_true")
    a = p.parse_args()
    rng = np.random.default_rng(a.seed)

    chip_s, row_s, exp_s = a.chip_us * 1e-6, a.row_time_us * 1e-6, a.exposure_us * 1e-6
    readout_s = a.height * row_s
    if readout_s > 1.0 / a.fps:
        sys.exit("readout %.1f ms is longer than the frame period" % (readout_s * 1e3))
    duration = a.frames / a.fps + readout_s + exp_s + chip_s
    n_chips = int(duration / chip_s) + 2
    level = np.ones(n_chips)
    chunks = p2.build_chunks(a.message, a.msg_id)
    loop = p2.carousel_chips(chunks)
    s0 = int(round(a.send_s / chip_s))
    if a.mode == "carousel":
        lv = np.array([1.0 if c is None else 1 + a.depth * (2 * c - 1) for c in loop])
        reps = -(-(n_chips - s0) // len(lv))
        level[s0:] = np.tile(lv, reps)[:n_chips - s0]
    elif a.mode == "constant":
        level[s0:] = 1 + a.depth
    edges = np.arange(n_chips + 1) * chip_s
    F = np.concatenate([[0.0], np.cumsum(level) * chip_s])

    rows = np.arange(a.height)
    shade = 0.85 + 0.15 * (1 - ((rows - a.height / 2) / (a.height / 2)) ** 2)
    texture = rng.normal(0, 8, size=(a.height, a.width)) + 150
    scene = texture * shade[:, None]

    frames, ids, ts, expected = [], [], [], []
    chunk_starts = []  # chip offsets of each chunk inside one loop
    off = 0
    for c in chunks:
        chunk_starts.append(off)
        off += p2.CHUNK_CHIPS + p2.GAP_CHIPS
    for f in range(a.frames):
        t0 = f / a.fps
        if a.drop and rng.random() < a.drop:
            continue
        t_row = t0 + rows * row_s
        light = (np.interp(t_row + exp_s, edges, F) - np.interp(t_row, edges, F)) / exp_s
        img = scene * light[:, None] + rng.normal(0, a.noise, size=scene.shape)
        img = np.clip(img, 0, 255).astype(np.uint8)
        if a.jpeg:
            ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, a.jpeg])
            img = cv2.imdecode(buf, cv2.IMREAD_GRAYSCALE)
        if a.orientation:
            img = np.rot90(img, {90: 1, 180: 2, 270: -1}[a.orientation])
        frames.append(img)
        ids.append(f)
        ts.append(t0)
        inside = []
        if a.mode == "carousel":
            first_loop = int((t0 - a.send_s) / (len(loop) * chip_s)) - 1
            for j in range(max(0, first_loop), first_loop + 3):
                for k, off in enumerate(chunk_starts):
                    cs = a.send_s + (j * len(loop) + off) * chip_s
                    ce = cs + p2.CHUNK_CHIPS * chip_s
                    if cs >= t0 and ce <= t0 + readout_s - exp_s:
                        inside.append(k)
        expected.append(inside)

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    np.savez_compressed(a.out, frames=np.stack(frames), frame_id=np.array(ids), capture_ts_s=np.array(ts),
                        orientation=a.orientation)
    collected, t_all = set(), None
    for i, e in zip(ids, expected):
        collected.update(e)
        if t_all is None and len(collected) == len(chunks):
            t_all = (i + 1) / a.fps
    truth = {
        "fixture": os.path.basename(a.out), "synthetic": True, "protocol": "v2-proposed", "mode": a.mode,
        "message_utf8": a.message if a.mode == "carousel" else None,
        "message_bytes": len(a.message.encode("utf-8")) if a.mode == "carousel" else 0,
        "msg_id": a.msg_id, "chunk_count": len(chunks), "send_s": a.send_s,
        "rows_per_chip": a.chip_us / a.row_time_us, "readout_ms": readout_s * 1e3,
        "frames_written": len(ids), "frames_dropped": a.frames - len(ids),
        "ideal_all_chunks_seen_s": t_all,
        "expected_chunks_per_frame": {str(i): e for i, e in zip(ids, expected)},
        "params": vars(a),
    }
    with open(a.out + ".truth.json", "w") as f:
        json.dump(truth, f, indent=2, ensure_ascii=False)
    if a.png:
        k = next((n for n, e in enumerate(expected) if e), 0)
        cv2.imwrite(os.path.splitext(a.out)[0] + ".sample.png", frames[k])
    if a.mp4:
        h, w = frames[0].shape
        vw = cv2.VideoWriter(os.path.splitext(a.out)[0] + ".mp4", cv2.VideoWriter_fourcc(*"mp4v"), a.fps, (w, h))
        for fr in frames:
            vw.write(cv2.cvtColor(fr, cv2.COLOR_GRAY2BGR))
        vw.release()
    print("wrote %s: %d frames (%d dropped), %d chunks, %.2f rows/chip, readout %.1f ms, all chunks visible by %s s"
          % (a.out, len(ids), a.frames - len(ids), len(chunks), truth["rows_per_chip"], truth["readout_ms"],
             "%.2f" % t_all if t_all else "never"))


if __name__ == "__main__":
    main()
