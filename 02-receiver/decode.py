"""Screen-to-camera modem receiver (contract v1).

python 02-receiver/decode.py --video clip.mp4 --roi x,y,w,h --out decode.json
"""
import argparse
import json
import sys

import numpy as np

PREAMBLE = [int(b) for b in f"{0xDDAA:016b}"]
SYMBOL_S = 0.200
MAX_LEN = 16


def crc16_ccitt_false(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return crc


def bits_to_bytes(bits):
    """Bytes MSB-first; None if any bit in that byte is erased."""
    out = []
    for i in range(0, len(bits) - len(bits) % 8, 8):
        chunk = bits[i:i + 8]
        out.append(None if None in chunk else int("".join(map(str, chunk)), 2))
    return out


def read_roi_series(video, roi):
    import cv2

    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        raise SystemExit(f"cannot open video: {video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    x, y, w, h = roi
    pts, lum = [], []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        fh, fw = frame.shape[:2]
        if not lum and (w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > fw or y + h > fh):
            raise SystemExit(f"ROI {roi} outside frame {fw}x{fh}")
        patch = cv2.cvtColor(frame[y:y + h, x:x + w], cv2.COLOR_BGR2GRAY)
        lum.append(float(patch.mean()))
        pts.append(cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0)
    cap.release()
    n = len(lum)
    t = np.asarray(pts, dtype=float)
    # Prefer decoder PTS; fall back to index/FPS when PTS is missing or non-monotonic.
    if n > 1 and np.all(np.diff(t) > 0):
        timebase = "pts"
    else:
        if fps <= 0:
            raise SystemExit("no usable PTS and no FPS in container")
        t = np.arange(n) / fps
        timebase = f"frame_index/fps={fps:.3f}"
    return t, np.asarray(lum, dtype=float), timebase


def sample_symbols(t, s, t0, T, count):
    """Mean of normalized samples in the central half of each symbol; None = erasure."""
    vals = []
    for i in range(count):
        c = t0 + (i + 0.5) * T
        m = (t >= c - 0.25 * T) & (t <= c + 0.25 * T)
        vals.append(float(s[m].mean()) if m.any() else None)
    return vals


def hard(vals):
    return [None if v is None else int(v > 0) for v in vals]


def decode_candidate(t, s, t0, T):
    pre = hard(sample_symbols(t, s, t0, T, 16))
    head = hard(sample_symbols(t, s, t0, T, 24))
    length = bits_to_bytes(head[16:24])[0]
    res = {"t0": t0, "T": T, "preamble_errors": sum(a != b for a, b in zip(pre, PREAMBLE)),
           "length": length, "payload_bits": [], "crc_ok": None, "payload_ascii": None}
    if length is None or not 1 <= length <= MAX_LEN:
        res["packet_bits"] = head
        res["margin"] = 0.0
        return res
    total = 16 + 8 + 8 * length + 16
    vals = sample_symbols(t, s, t0, T, total)
    bits = hard(vals)
    payload_bits = bits[24:24 + 8 * length]
    payload = bits_to_bytes(payload_bits)
    crc_rx = bits_to_bytes(bits[24 + 8 * length:])
    if None not in payload and None not in crc_rx:
        crc_calc = crc16_ccitt_false(bytes([length] + payload))
        res["crc_ok"] = crc_calc == (crc_rx[0] << 8 | crc_rx[1])
    res["payload_ascii"] = "".join(
        "?" if b is None else (chr(b) if 32 <= b < 127 else "?") for b in payload)
    res.update(packet_bits=bits, payload_bits=payload_bits,
               margin=float(np.mean([abs(v) for v in vals if v is not None] or [0.0])),
               packet_end_s=t0 + total * T)
    return res


def decode_series(t, y, symbol_s=SYMBOL_S):
    t = np.asarray(t, dtype=float)
    y = np.asarray(y, dtype=float)
    lo, hi = np.percentile(y, [5, 95])
    no_packet = {"packet_found": False, "crc_ok": None, "payload_ascii": None, "payload_bits": [],
                 "packet_start_s": None, "packet_end_s": None}
    if len(y) < 2 or hi - lo < 1e-6:
        return no_packet
    s = (y - (lo + hi) / 2) / ((hi - lo) / 2)  # ~ -1 for 0, 0 for idle, +1 for 1
    ref = np.array(PREAMBLE) * 2 - 1
    dt = float(np.median(np.diff(t)))
    best = None
    # Sweep symbol period ±3% to absorb browser/camera clock drift.
    for T in symbol_s * np.arange(0.97, 1.0301, 0.0025):
        starts = np.arange(t[0], t[-1] - 16 * T, min(dt / 2, T / 10))
        if not len(starts):
            continue
        scores = []
        for t0 in starts:
            v = sample_symbols(t, s, t0, T, 16)
            scores.append(sum(r * (x or 0.0) for r, x in zip(ref, v)))
        t0 = float(starts[int(np.argmax(scores))])
        # Center t0 inside the plateau of near-max scores.
        good = starts[np.asarray(scores) >= max(scores) - 0.5]
        good = good[np.abs(good - t0) < T / 2]
        cand = decode_candidate(t, s, float(good.mean()), T)
        cand["score"] = max(scores) / 16
        key = (cand["crc_ok"] is True, -cand["preamble_errors"], cand["margin"], cand["score"])
        if best is None or key > best[0]:
            best = (key, cand)
    if best is None:
        return no_packet
    c = best[1]
    if c["preamble_errors"] > 1 or c["score"] < 0.4:
        return no_packet
    return {"packet_found": True, "crc_ok": c["crc_ok"], "payload_ascii": c["payload_ascii"],
            "payload_bits": c["payload_bits"], "packet_start_s": c["t0"],
            "packet_end_s": c.get("packet_end_s"),
            "symbol_s": c["T"], "length": c["length"], "packet_bits": c["packet_bits"],
            "preamble_errors": c["preamble_errors"], "preamble_score": c["score"],
            "margin": c["margin"], "erasures": c["packet_bits"].count(None)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--video", required=True)
    ap.add_argument("--roi", required=True, help="x,y,w,h in decoded-image pixels")
    ap.add_argument("--out", required=True)
    ap.add_argument("--symbol-ms", type=float, default=SYMBOL_S * 1000)
    a = ap.parse_args(argv)
    try:
        roi = [int(v) for v in a.roi.split(",")]
        assert len(roi) == 4
    except (ValueError, AssertionError):
        ap.error("--roi must be four integers x,y,w,h")
    t, y, timebase = read_roi_series(a.video, roi)
    result = decode_series(t, y, a.symbol_ms / 1000)
    result.update(timebase=timebase, video=a.video, roi=roi, frames=len(y))
    with open(a.out, "w") as f:
        json.dump(result, f, indent=2)
    print(json.dumps({k: result[k] for k in ("packet_found", "crc_ok", "payload_ascii")}))


if __name__ == "__main__":
    sys.exit(main())
