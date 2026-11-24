"""Reference rolling-shutter decoder for protocol v2 (integration check, not the receiver deliverable).

It exists so the demo owner can prove that the synthetic fixtures are decodable and so live.py runs
end to end before 02-receiver ships its own decoder. The receiver's decoder should replace it
(live.py --decoder path.py:ClassName) and must beat it.

Per frame: rotate to sensor rows, average the ROI across columns -> row profile, divide by a moving
average (Manchester keeps the mean constant, so this removes scene shading and exposure), search the
sync pattern over a range of rows-per-chip, then read Manchester bits and check each chunk's CRC.
"""
import numpy as np

import protocol2 as p2

SYNC_PM = np.array(p2.SYNC_CHIPS, dtype=float) * 2 - 1


def orient(img, orientation):
    """orientation = clockwise degrees to rotate the received image so sensor rows are horizontal."""
    k = {0: 0, 90: -1, 180: 2, 270: 1}[int(orientation) % 360]
    return np.rot90(img, k) if k else img


def to_gray(img):
    img = np.asarray(img)
    if img.ndim == 3:
        img = img[..., :3].astype(np.float32) @ np.array([0.114, 0.587, 0.299], dtype=np.float32)  # BGR
    return img.astype(np.float32)


def row_profile(img, roi=None):
    g = to_gray(img)
    if roi:
        x, y, w, h = roi
        g = g[y:y + h, x:x + w]
    return g.mean(axis=1)


def normalize(profile, rows_per_chip):
    win = max(3, int(round(rows_per_chip * 8)) | 1)
    k = np.ones(win) / win
    pad = np.pad(profile, win // 2, mode="reflect")
    base = np.convolve(pad, k, mode="valid")
    return profile / np.maximum(base, 1e-6) - 1.0


def _chip_means(cs, start, rpc, n):
    centers = start + (np.arange(n) + 0.5) * rpc
    lo = np.floor(centers - 0.25 * rpc).astype(int)
    hi = np.maximum(np.ceil(centers + 0.25 * rpc).astype(int), lo + 1)
    return (cs[hi] - cs[lo]) / (hi - lo)


def _read(cs, start, rpc):
    c = _chip_means(cs, start, rpc, p2.CHUNK_CHIPS)
    first, second = c[0::2], c[1::2]
    bits = (first > second).astype(int)
    margin = float(np.mean(np.abs(first - second)))
    return p2.bits_to_bytes(list(bits)), margin


def decode_profile(profile, rpc_min=2.0, rpc_max=16.0, rpc_hint=None, thresh=0.55):
    """Return CRC-valid chunks found in one row profile (list of dicts with row_start, rows_per_chip)."""
    profile = np.asarray(profile, dtype=float)
    n = len(profile)
    if rpc_hint:
        rpcs = rpc_hint * np.geomspace(0.9, 1.1, 21)
    else:
        rpcs = np.geomspace(rpc_min, rpc_max, int(np.log(rpc_max / rpc_min) / np.log(1.01)) + 1)
    s_cache = {}
    cands = []
    for rpc in rpcs:
        if p2.CHUNK_CHIPS * rpc + 2 > n:
            continue
        key = int(round(rpc))
        if key not in s_cache:
            s_cache[key] = normalize(profile, rpc)
        s = s_cache[key]
        idx = np.minimum((np.arange(int(len(SYNC_PM) * rpc)) / rpc).astype(int), len(SYNC_PM) - 1)
        t = SYNC_PM[idx]
        t = t - t.mean()
        corr = np.correlate(s, t, mode="valid")
        energy = np.sqrt(np.convolve(s * s, np.ones(len(t)), mode="valid") - np.convolve(s, np.ones(len(t)), mode="valid") ** 2 / len(t))
        score = corr / (np.linalg.norm(t) * np.maximum(energy, 1e-9))
        limit = n - int(p2.CHUNK_CHIPS * rpc) - 1
        for i in np.nonzero(score[:max(0, limit)] > thresh)[0]:
            cands.append((float(score[i]), int(i), float(rpc)))
    cands.sort(reverse=True)
    found, taken = [], []
    for sc, start, rpc in cands:
        if any(abs(start - a) < b for a, b in taken):
            continue
        s = s_cache[int(round(rpc))]
        cs = np.concatenate([[0.0], np.cumsum(s)])
        best = None
        for r in rpc * np.linspace(0.97, 1.03, 31):
            for st in start + np.arange(-0.5, 0.51, 0.25) * r:
                if st < 0 or st + p2.CHUNK_CHIPS * r + 1 >= n:
                    continue
                raw, margin = _read(cs, st, r)
                ch = p2.parse_chunk(raw)
                if ch and ch["crc_ok"] and (best is None or margin > best[0]):
                    best = (margin, st, r, ch)
        taken.append((start, p2.CHUNK_CHIPS * rpc * 0.5))
        if best:
            margin, st, r, ch = best
            ch.update(row_start=round(st, 2), rows_per_chip=round(r, 4), sync_score=round(sc, 3),
                      margin=round(margin, 4))
            found.append(ch)
            taken[-1] = (st, p2.CHUNK_CHIPS * r)
    return sorted(found, key=lambda c: c["row_start"])


class Decoder:
    """Stateful per-stream decoder. push(frame) -> dict with chunks, messages and the row profile.

    frame = {"frame_id", "image", "orientation" (deg), "capture_ts_s", "ts_kind": "capture"|"arrival"}
    """

    def __init__(self, roi=None, rows_per_chip=None, frame_mean=False):
        self.roi = roi
        self.rpc = rows_per_chip
        self.frame_mean = frame_mean
        self.asm = p2.Reassembler()

    def push(self, frame):
        img = orient(frame["image"], frame.get("orientation", 0))
        prof = row_profile(img, self.roi)
        if self.frame_mean:  # control: throw away the row information, keep one brightness per frame
            prof = np.full_like(prof, prof.mean())
        chunks = decode_profile(prof, rpc_hint=self.rpc)
        msgs = []
        for c in chunks:
            c["frame_id"] = frame["frame_id"]
            m = self.asm.add(c, frame["frame_id"], frame.get("capture_ts_s"))
            if m:
                msgs.append(m)
        return {"frame_id": frame["frame_id"], "chunks": chunks, "messages": msgs, "profile": prof}
