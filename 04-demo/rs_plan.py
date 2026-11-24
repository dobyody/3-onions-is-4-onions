"""Pick the v2 chip duration for a camera mode, and predict delivery time (timing only, no images).

The constraints that decide it:
  * rows per chip = chip_us / row_time_us should be >= ~3 so each chip spans several rows;
  * exposure should be <= chip_us (up to 1.5x still decodes), because a longer exposure averages
    neighbouring chips away. Lock the shortest exposure the phone allows and write it down;
  * a whole chunk (176 chips) must fit inside one frame's readout (rows x row_time), with room to spare,
    because the gap between frames is lost.

  python3 04-demo/rs_plan.py --fps 60 --rows 1080 --row-time-us 14 --exposure-us 50
  python3 04-demo/rs_plan.py --fps 60 --rows 1080 --row-time-us 14 --exposure-us 50 --chip-us 50   # one setting in detail

Without --row-time-us it assumes the readout fills --readout-frac of the frame period (a guess; calibrate with 03-scope).
"""
import argparse
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import protocol2 as p2  # noqa: E402


def chunk_slots(message_bytes):
    chunks = p2.build_chunks(b"x" * message_bytes)
    starts, off = [], 0
    for i, _ in enumerate(chunks):
        starts.append(off)
        off += p2.CHUNK_CHIPS + p2.gap_chips(i)
    return starts, off


def simulate(fps, readout_s, chip_s, exposure_s, message_bytes=64, phases=400, horizon_s=25.0, drop=0.0, seed=0):
    """Time from Send until every chunk has been fully inside some frame's readout, over random Send phases."""
    starts, loop = chunk_slots(message_bytes)
    n = len(starts)
    rng = np.random.default_rng(seed)
    T = 1.0 / fps
    usable = readout_s - exposure_s
    L = p2.CHUNK_CHIPS * chip_s
    times, per_frame = [], []
    for ph in rng.uniform(0, T, phases):
        seen = set()
        got = None
        f = 0
        while f * T < horizon_s + T:
            t0 = ph + f * T  # frame start relative to Send
            f += 1
            if drop and rng.random() < drop:
                continue
            k = 0
            j0 = int(t0 / (loop * chip_s))
            for j in range(j0, j0 + 2):
                for i, s in enumerate(starts):
                    cs = (j * loop + s) * chip_s
                    if cs >= t0 and cs + L <= t0 + usable:
                        seen.add(i)
                        k += 1
            per_frame.append(k)
            if len(seen) == n:
                got = t0 + readout_s
                break
        times.append(got)
    ok = [t for t in times if t is not None]
    return {
        "chunks": n, "chunk_ms": L * 1e3, "loop_ms": loop * chip_s * 1e3, "usable_readout_ms": usable * 1e3,
        "chunks_per_frame": float(np.mean(per_frame)) if per_frame else 0.0,
        "never": len(times) - len(ok), "median_s": float(np.median(ok)) if ok else None,
        "p95_s": float(np.percentile(ok, 95)) if ok else None, "max_s": max(ok) if ok else None,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--fps", type=float, default=60)
    p.add_argument("--rows", type=int, default=1080, help="sensor rows in the streamed image")
    p.add_argument("--row-time-us", type=float)
    p.add_argument("--readout-frac", type=float, default=0.9)
    p.add_argument("--exposure-us", type=float, default=50)
    p.add_argument("--chip-us", type=float, help="show one setting instead of a sweep")
    p.add_argument("--bytes", type=int, default=64)
    p.add_argument("--drop", type=float, default=0.0, help="fraction of frames lost in transport")
    a = p.parse_args()
    row_us = a.row_time_us or (a.readout_frac / a.fps) / a.rows * 1e6
    readout = a.rows * row_us * 1e-6
    if readout > 1 / a.fps:
        sys.exit("readout %.1f ms is longer than the %.1f ms frame period: check --rows/--row-time-us"
                 % (readout * 1e3, 1e3 / a.fps))
    print("camera: %.0f fps (frame %.2f ms), %d rows x %.1f us = readout %.2f ms, exposure %.0f us%s"
          % (a.fps, 1e3 / a.fps, a.rows, row_us, readout * 1e3, a.exposure_us,
             "" if a.row_time_us else "  [row time GUESSED, calibrate it]"))
    chips = [a.chip_us] if a.chip_us else [20, 25, 30, 40, 50, 60, 70, 80, 100, 125, 150]
    print("\n| chip us | rows/chip | chunk ms | chunks/frame | 64 B delivered: median / p95 / max s | never (of 400) | verdict |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    best = None
    for c in chips:
        rpc = c / row_us
        r = simulate(a.fps, readout, c * 1e-6, a.exposure_us * 1e-6, a.bytes, drop=a.drop)
        problems = []
        if rpc < 2.5:
            problems.append("too few rows/chip")
        if a.exposure_us > 1.5 * c:
            problems.append("exposure > 1.5 x chip (chips blur together)")
        if r["chunks_per_frame"] == 0:
            problems.append("chunk never fits in a frame")
        if r["never"]:
            problems.append("some Send times never complete")
        if r["p95_s"] and r["p95_s"] > 25:
            problems.append("slower than 25 s")
        tight = [] if problems else [w for w, bad in (("rows/chip < 3", rpc < 3), ("exposure > chip", a.exposure_us > c),
                                                         ("< 0.3 chunks/frame", r["chunks_per_frame"] < 0.3)) if bad]
        verdict = "; ".join(problems) if problems else ("tight: " + ", ".join(tight) if tight else "OK")
        if not problems:
            key = (len(tight), r["p95_s"])
            if best is None or key < best[2]:
                best = (c, r["p95_s"], key)
        fmt = lambda v: "%.2f" % v if v is not None else "-"  # noqa: E731
        print("| %g | %.1f | %.1f | %.2f | %s / %s / %s | %d | %s |" % (
            c, rpc, r["chunk_ms"], r["chunks_per_frame"], fmt(r["median_s"]), fmt(r["p95_s"]), fmt(r["max_s"]),
            r["never"], verdict))
    if not a.chip_us:
        if best:
            print("\nrecommended: --chip-us %g  (rows/chip %.1f; set the emitter to %g us chips and pass "
                  "--rows-per-chip %.2f to live.py)" % (best[0], best[0] / row_us, best[0], best[0] / row_us))
        else:
            print("\nno chip duration works for this camera mode: shorten the exposure, use more rows, or change mode")


if __name__ == "__main__":
    main()
