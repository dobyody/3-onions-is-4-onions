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


SYNC_BITS = np.array(p2.bytes_to_bits(p2.SYNC))
WEIGHTS = 1 << np.arange(7, -1, -1)


def _read_many(cs, starts, rpcs):
    """Read one chunk for every (start, rows_per_chip) pair at once. Returns (bytes matrix, margins)."""
    k = np.arange(p2.CHUNK_CHIPS) + 0.5
    centers = starts[:, None] + k[None, :] * rpcs[:, None]
    half = 0.25 * rpcs[:, None]
    lo = np.floor(centers - half).astype(int)
    hi = np.maximum(np.ceil(centers + half).astype(int), lo + 1)
    c = (cs[hi] - cs[lo]) / (hi - lo)
    first, second = c[:, 0::2], c[:, 1::2]
    bits = (first > second).astype(np.int64)
    by = (bits.reshape(len(starts), -1, 8) * WEIGHTS).sum(axis=2)
    return by, np.abs(first - second).mean(axis=1)


def _windowed(cs, cs2, m):
    s1 = cs[m:] - cs[:-m]
    s2 = cs2[m:] - cs2[:-m]
    return s1, s2


def decode_profile(profile, rpc_min=2.0, rpc_max=16.0, rpc_hint=None, thresh=0.55, hint_span=0.1):
    """Return CRC-valid chunks found in one row profile (list of dicts with row_start, rows_per_chip)."""
    profile = np.asarray(profile, dtype=float)
    n = len(profile)
    if rpc_hint:
        rpcs = rpc_hint * np.geomspace(1 - hint_span, 1 + hint_span, max(5, int(hint_span * 200) + 1))
    else:
        rpcs = np.geomspace(rpc_min, rpc_max, int(np.log(rpc_max / rpc_min) / np.log(1.01)) + 1)
    cache = {}
    cands = []
    for rpc in rpcs:
        if p2.CHUNK_CHIPS * rpc + 2 > n:
            continue
        key = int(round(rpc))
        if key not in cache:
            sn = normalize(profile, rpc)
            cache[key] = (sn, np.concatenate([[0.0], np.cumsum(sn)]), np.concatenate([[0.0], np.cumsum(sn * sn)]))
        sn, cs, cs2 = cache[key]
        idx = np.minimum((np.arange(int(len(SYNC_PM) * rpc)) / rpc).astype(int), len(SYNC_PM) - 1)
        t = SYNC_PM[idx]
        t = t - t.mean()
        m = len(t)
        corr = np.correlate(sn, t, mode="valid")
        s1, s2 = _windowed(cs, cs2, m)
        energy = np.sqrt(np.maximum(s2 - s1 * s1 / m, 0))
        score = corr / (np.linalg.norm(t) * np.maximum(energy, 1e-9))
        limit = n - int(p2.CHUNK_CHIPS * rpc) - 1
        for i in np.nonzero(score[:max(0, limit)] > thresh)[0]:
            cands.append((float(score[i]), int(i), float(rpc)))
    cands.sort(reverse=True)
    found, taken = [], []
    for sc, start, rpc in cands:
        if any(abs(start - a) < b for a, b in taken):
            continue
        cs = cache[int(round(rpc))][1]
        rr = rpc * np.linspace(0.97, 1.03, 31)
        ss = np.arange(-0.5, 0.51, 0.25)
        R, S = np.meshgrid(rr, ss, indexing="ij")
        R, S = R.ravel(), start + (S * R).ravel()
        keep = (S >= 0) & (S + p2.CHUNK_CHIPS * R + 1 < n)
        taken.append((start, p2.CHUNK_CHIPS * rpc * 0.5))
        if not keep.any():
            continue
        R, S = R[keep], S[keep]
        by, margin = _read_many(cs, S, R)
        best = None
        for j in np.nonzero((by[:, 0] == 0xDD) & (by[:, 1] == 0xAA))[0]:
            if best is not None and margin[j] <= best[0]:
                continue
            ch = p2.parse_chunk(bytes(by[j].astype(np.uint8)))
            if ch and ch["crc_ok"]:
                best = (float(margin[j]), float(S[j]), float(R[j]), ch)
        if best:
            mg, st, r, ch = best
            ch.update(row_start=round(st, 2), rows_per_chip=round(r, 4), sync_score=round(sc, 3), margin=round(mg, 4))
            found.append(ch)
            taken[-1] = (st, p2.CHUNK_CHIPS * r)
    return sorted(found, key=lambda c: c["row_start"])


class Decoder:
    """Stateful per-stream decoder. push(frame) -> dict with chunks, messages and the row profile.

    frame = {"frame_id", "image", "orientation" (deg), "capture_ts_s", "ts_kind": "capture"|"arrival"}
    """

    def __init__(self, roi=None, rows_per_chip=None, frame_mean=False, relock_after=30):
        self.roi = roi
        self.rpc = rows_per_chip      # calibration hint (fixed)
        self.lock = None              # rows per chip learned from decoded chunks
        self.miss = 0
        self.relock_after = relock_after
        self.frame_mean = frame_mean
        self.asm = p2.Reassembler()

    def push(self, frame):
        img = orient(frame["image"], frame.get("orientation", 0))
        prof = row_profile(img, self.roi)
        if self.frame_mean:  # control: throw away the row information, keep one brightness per frame
            prof = np.full_like(prof, prof.mean())
        # Search all chip sizes until the first chunk, then only around the learned one (fast enough for 60 fps).
        # After relock_after frames without a chunk, go back to the full search.
        hint = self.lock or self.rpc
        chunks = decode_profile(prof, rpc_hint=hint, hint_span=0.04 if self.lock else 0.1)
        if chunks:
            self.lock = float(np.median([c["rows_per_chip"] for c in chunks]))
            self.miss = 0
        else:
            self.miss += 1
            if self.lock and self.miss >= self.relock_after:
                self.lock, self.miss = None, 0
        msgs = []
        for c in chunks:
            c["frame_id"] = frame["frame_id"]
            m = self.asm.add(c, frame["frame_id"], frame.get("capture_ts_s"))
            if m:
                msgs.append(m)
        return {"frame_id": frame["frame_id"], "chunks": chunks, "messages": msgs, "profile": prof}
