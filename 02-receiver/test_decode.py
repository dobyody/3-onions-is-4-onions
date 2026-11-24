"""Synthetic checks: python 02-receiver/test_decode.py"""
import json
import os
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from decode import crc16_ccitt_false, decode_series  # noqa: E402

FIX = json.load(open(os.path.join(HERE, "..", "fixtures", "packet-v1.json")))
BITS = FIX["bits"]
PAYLOAD_BITS = BITS[24:24 + 8 * len(FIX["payload_ascii"])]


def synth(fps=30.0, drift=1.0, noise=3.0, lead=1.5, tail=1.5, drop=0.0, seed=0, gamma=2.2):
    """Camera-like luminance: idle/0/1 at gray 128/64/192 through a gamma curve + noise."""
    rng = np.random.default_rng(seed)
    T = 0.2 * drift
    dur = lead + len(BITS) * T + tail
    t = np.arange(0, dur, 1 / fps) + rng.uniform(0, 1 / fps)
    t = t[rng.random(len(t)) >= drop]
    level = np.full(len(t), 128.0)
    k = np.floor((t - lead) / T).astype(int)
    inside = (k >= 0) & (k < len(BITS))
    level[inside] = np.where(np.array(BITS)[k[inside]] == 1, 192.0, 64.0)
    y = 255 * (level / 255) ** (1 / gamma) + rng.normal(0, noise, len(t))
    return t, y, lead, lead + len(BITS) * T


def check(name, res, start=None, end=None):
    assert res["packet_found"], name
    assert res["crc_ok"] is True, (name, res)
    assert res["payload_ascii"] == FIX["payload_ascii"], (name, res["payload_ascii"])
    assert res["payload_bits"] == PAYLOAD_BITS, name
    if start is not None:
        assert abs(res["packet_start_s"] - start) < 0.05, (name, res["packet_start_s"], start)
        assert abs(res["packet_end_s"] - end) < 0.1, (name, res["packet_end_s"], end)
    print(f"ok  {name}")


def main():
    assert f"{crc16_ccitt_false(bytes.fromhex(FIX['packet_hex'][4:-4])):04X}" == FIX["crc_hex"]
    print("ok  crc matches fixture")

    for kw in [{}, {"fps": 24}, {"fps": 60}, {"drift": 1.02}, {"drift": 0.98},
               {"noise": 8}, {"drop": 0.1, "seed": 3}]:
        t, y, s, e = synth(**kw)
        check(f"series {kw or 'nominal'}", decode_series(t, y), s, e)

    # Pure idle -> no packet; single flipped payload bit -> CRC fails but bits retained.
    t = np.arange(0, 10, 1 / 30)
    assert decode_series(t, 128 + np.random.default_rng(1).normal(0, 2, len(t)))["packet_found"] is False
    print("ok  idle-only -> no packet")
    t, y, lead, _ = synth()
    flip = 30  # a payload bit
    m = (t >= lead + flip * 0.2) & (t < lead + (flip + 1) * 0.2)
    y[m] = 255 * ((192.0 if BITS[flip] == 0 else 64.0) / 255) ** (1 / 2.2)
    r = decode_series(t, y)
    assert r["packet_found"] and r["crc_ok"] is False and len(r["payload_bits"]) == 64, r
    assert sum(a != b for a, b in zip(r["payload_bits"], PAYLOAD_BITS)) == 1
    print("ok  corrupted bit -> crc_ok false, bits retained")

    # End to end through the CLI with an mp4.
    import cv2
    with tempfile.TemporaryDirectory() as d:
        vid, out = os.path.join(d, "synth.mp4"), os.path.join(d, "decode.json")
        fps = 30
        w = cv2.VideoWriter(vid, cv2.VideoWriter_fourcc(*"mp4v"), fps, (320, 240))
        lead = 1.2
        for i in range(int((lead + len(BITS) * 0.2 + 1.2) * fps)):
            k = int(np.floor((i / fps - lead) / 0.2))
            g = 128 if not 0 <= k < len(BITS) else (192 if BITS[k] else 64)
            frame = np.full((240, 320, 3), 30, np.uint8)
            frame[80:160, 100:220] = g
            w.write(frame)
        w.release()
        subprocess.run([sys.executable, os.path.join(HERE, "decode.py"), "--video", vid,
                        "--roi", "110,90,100,60", "--out", out], check=True)
        check("cli mp4", json.load(open(out)), lead, lead + len(BITS) * 0.2)
        # Off-patch ROI is processable but has no packet: JSON must still be written.
        subprocess.run([sys.executable, os.path.join(HERE, "decode.py"), "--video", vid,
                        "--roi", "0,0,50,50", "--out", out], check=True)
        r = json.load(open(out))
        assert r["packet_found"] is False and r["payload_bits"] == [] and "timebase" in r
        print("ok  cli no-packet json")
    print("all passed")


if __name__ == "__main__":
    main()
