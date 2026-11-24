"""One integration command for the v2 live path: frames -> row decoder -> verified message.

Run from the project root.

  # synthetic rehearsal (frames from the fixture, paced at its fps)
  python3 04-demo/live.py --fixture 04-demo/fixtures/rs_clean.npz --realtime
  # live phone stream (any URL OpenCV can open: MJPEG/RTSP/HTTP from the transport role) or a clip
  python3 04-demo/live.py --video http://PHONE:8080/video --roi 0,0,320,1080 --orientation 90 --rows-per-chip 3.57 \
      --setup-file 04-demo/results/setup-A.json      # 60 fps phone, 50 us chips (rows/chip from rs_plan.py)
  # local camera index
  python3 04-demo/live.py --camera 0
  # control: same input, each frame collapsed to its mean brightness (must NOT verify a message)
  python3 04-demo/live.py --fixture 04-demo/fixtures/rs_clean.npz --frame-mean

Preview window keys: s = mark Send (starts the delivery timer), q / Esc = quit. --headless runs without
a window. Each run writes 04-demo/results/live-<time>.json (and a preview PNG at verification).
The decoder is pluggable: --decoder 02-receiver/<file>.py:<Class>, with the interface of rs_ref.Decoder.
"""
import argparse
import datetime
import importlib.util
import json
import os
import queue
import sys
import threading
import time

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import protocol2 as p2  # noqa: E402
import rs_ref  # noqa: E402

RESULTS_DIR = os.path.join(HERE, "results")


def load_decoder(spec):
    if not spec:
        return rs_ref.Decoder
    path, _, cls = spec.partition(":")
    s = importlib.util.spec_from_file_location("ext_decoder", path)
    mod = importlib.util.module_from_spec(s)
    sys.path.insert(0, os.path.dirname(os.path.abspath(path)))
    s.loader.exec_module(mod)
    return getattr(mod, cls or "Decoder")


class Source(threading.Thread):
    """Reads frames into a bounded queue. Live sources drop the oldest frame when the queue is full."""

    def __init__(self, a, q):
        super().__init__(daemon=True)
        self.a, self.q = a, q
        self.dropped = self.read = 0
        self.done = threading.Event()
        self.info = {}

    def put(self, frame, live):
        if live:
            while True:
                try:
                    self.q.put_nowait(frame)
                    return
                except queue.Full:
                    try:
                        self.q.get_nowait()
                        self.dropped += 1
                    except queue.Empty:
                        pass
        else:
            self.q.put(frame)

    def run(self):
        a = self.a
        try:
            if a.fixture:
                d = np.load(a.fixture)
                orient = int(d["orientation"])
                frames, ids, ts = d["frames"], d["frame_id"], d["capture_ts_s"]
                fps = 1.0 / np.median(np.diff(ts)) if len(ts) > 1 else 30.0
                self.info = {"source": a.fixture, "kind": "fixture", "ts_kind": "capture", "nominal_fps": fps,
                             "resolution": "%dx%d" % (frames.shape[2], frames.shape[1])}
                t_start = time.monotonic()
                for img, fid, t in zip(frames, ids, ts):
                    if a.realtime:
                        delay = t_start + (t - ts[0]) - time.monotonic()
                        if delay > 0:
                            time.sleep(delay)
                    self.read += 1
                    self.put({"frame_id": int(fid), "image": img, "orientation": orient,
                              "capture_ts_s": float(t), "ts_kind": "capture"}, live=a.realtime)
            else:
                src = a.camera if a.camera is not None else a.video
                cap = cv2.VideoCapture(src)
                if not cap.isOpened():
                    raise SystemExit("cannot open %s" % src)
                is_file = a.video is not None and os.path.exists(a.video)
                self.info = {"source": str(src), "kind": "file" if is_file else "live",
                             "ts_kind": "capture" if is_file else "arrival",
                             "nominal_fps": cap.get(cv2.CAP_PROP_FPS) or None,
                             "resolution": "%dx%d" % (cap.get(cv2.CAP_PROP_FRAME_WIDTH), cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}
                fid = 0
                t0 = time.monotonic()
                while not self.done.is_set():
                    ok, img = cap.read()
                    if not ok:
                        break
                    ts = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0 if is_file else time.monotonic() - t0
                    self.read += 1
                    self.put({"frame_id": fid, "image": img, "orientation": a.orientation,
                              "capture_ts_s": ts, "ts_kind": self.info["ts_kind"]}, live=not is_file)
                    fid += 1
                cap.release()
        finally:
            self.q.put(None)


def draw_preview(frame, res, roi, status, height=540):
    img = rs_ref.orient(frame["image"], frame.get("orientation", 0))
    if img.ndim == 2:
        img = cv2.cvtColor(np.ascontiguousarray(img), cv2.COLOR_GRAY2BGR)
    img = np.ascontiguousarray(img)
    h, w = img.shape[:2]
    if roi:
        x, y, rw, rh = roi
        cv2.rectangle(img, (x, y), (x + rw, y + rh), (0, 0, 255), max(1, w // 200))
    scale = height / h
    view = cv2.resize(img, (max(1, int(w * scale)), height))
    prof = np.asarray(res["profile"], dtype=float)
    rpc = res["chunks"][0]["rows_per_chip"] if res["chunks"] else 4.0
    sig = rs_ref.normalize(prof, rpc) if len(prof) > 8 else prof
    panel = np.full((height, 300, 3), 255, np.uint8)
    y0 = roi[1] if roi else 0
    if len(sig) > 1:
        lim = max(float(np.percentile(np.abs(sig), 99)), 1e-6)
        xs = 150 + np.clip(sig / lim, -1, 1) * 140
        ys = (y0 + np.arange(len(sig))) * scale
        for c in res["chunks"]:
            a = int((y0 + c["row_start"]) * scale)
            b = int((y0 + c["row_start"] + p2.CHUNK_CHIPS * c["rows_per_chip"]) * scale)
            cv2.rectangle(panel, (0, a), (299, b), (200, 255, 200), -1)
            cv2.putText(panel, "chunk #%d" % c["index"], (215, a + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 120, 0), 1)
        cv2.polylines(panel, [np.stack([xs, ys], 1).astype(np.int32)], False, (60, 60, 60), 1)
    cv2.putText(panel, "row brightness (normalized)", (6, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)
    out = np.hstack([view, panel])
    W = max(out.shape[1], 760)
    if out.shape[1] < W:
        out = np.hstack([out, np.full((height, W - out.shape[1], 3), 255, np.uint8)])
    # zoom strip: the start of the first decoded chunk, rows left to right, with the bits read
    zoom = np.full((130, W, 3), 255, np.uint8)
    if res["chunks"] and len(sig) > 1:
        c = res["chunks"][0]
        r0, rpc = c["row_start"], c["rows_per_chip"]
        nchips = 48
        seg = sig[int(r0):int(r0 + nchips * rpc) + 1]
        lim = max(float(np.percentile(np.abs(sig), 99)), 1e-6)
        xs = 10 + np.arange(len(seg)) * (W - 20) / max(len(seg) - 1, 1)
        ys = 65 - np.clip(seg / lim, -1, 1) * 40
        for k in range(0, nchips, 2):
            xa = 10 + (k * rpc) * (W - 20) / max(len(seg) - 1, 1)
            cv2.line(zoom, (int(xa), 22), (int(xa), 108), (220, 220, 220), 1)
        bits = "".join("%d" % ((b >> (7 - i)) & 1) for b in bytes.fromhex("ddaa%02x%02x%02x" % (c["msg_id"], c["index"], c["count"])) for i in range(8))
        for k in range(nchips // 2):
            xa = 10 + ((2 * k + 1) * rpc) * (W - 20) / max(len(seg) - 1, 1)
            cv2.putText(zoom, bits[k], (int(xa) - 4, 124), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 90, 0), 1)
        cv2.polylines(zoom, [np.stack([xs, ys], 1).astype(np.int32)], False, (30, 30, 30), 1)
        cv2.putText(zoom, "frame %d, rows %d-%d: start of chunk #%d (sync DD AA, header), %.2f rows/chip; bits below"
                    % (res["frame_id"], int(r0), int(r0 + nchips * rpc), c["index"], rpc),
                    (8, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)
    else:
        cv2.putText(zoom, "no chunk in this frame", (8, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)
    out = np.vstack([out, zoom])
    bar = np.full((24 * len(status) + 8, W, 3), 32, np.uint8)
    for i, line in enumerate(status):
        cv2.putText(bar, line, (8, 22 + 24 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
    return np.vstack([out, bar])


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--fixture", help="npz from make_rs_fixture.py")
    src.add_argument("--video", help="clip path or stream URL")
    src.add_argument("--camera", type=int, help="local camera index")
    p.add_argument("--roi", help="x,y,w,h in the oriented image (default: whole frame)")
    p.add_argument("--orientation", type=int, default=0, choices=[0, 90, 180, 270],
                   help="clockwise rotation that makes sensor rows horizontal (fixtures carry their own)")
    p.add_argument("--rows-per-chip", type=float, help="hint from calibration (chip_us / row_time_us)")
    p.add_argument("--decoder", help="file.py:Class implementing push(frame) (default: 04-demo/rs_ref.py)")
    p.add_argument("--frame-mean", action="store_true", help="control: collapse each frame to its mean")
    p.add_argument("--expected", help="expected message (default: reference message for fixtures)")
    p.add_argument("--send-ts", type=float, help="Send time on the stream clock (fixtures: from truth)")
    p.add_argument("--realtime", action="store_true", help="pace fixture frames at their fps, drop when behind")
    p.add_argument("--queue", type=int, default=4)
    p.add_argument("--max-seconds", type=float, default=120)
    p.add_argument("--keep-going", action="store_true", help="do not stop after the first verified message")
    p.add_argument("--headless", action="store_true")
    p.add_argument("--setup-file", help="setup JSON from trials2.py setup (camera mode, emitter settings)")
    p.add_argument("--out", help="run log path (default results/live-<time>.json)")
    a = p.parse_args()

    roi = tuple(int(v) for v in a.roi.split(",")) if a.roi else None
    truth = None
    if a.fixture and os.path.exists(a.fixture + ".truth.json"):
        with open(a.fixture + ".truth.json") as f:
            truth = json.load(f)
    send_ts = a.send_ts if a.send_ts is not None else (truth or {}).get("send_s")
    expected = a.expected or ((truth or {}).get("message_utf8") if truth else None)
    Dec = load_decoder(a.decoder)
    dec = Dec(roi=roi, rows_per_chip=a.rows_per_chip, frame_mean=a.frame_mean)

    q = queue.Queue(maxsize=a.queue)
    reader = Source(a, q)
    reader.start()
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    os.makedirs(RESULTS_DIR, exist_ok=True)
    out = a.out or os.path.join(RESULTS_DIR, "live-%s.json" % stamp)
    win = None if a.headless else "v2 live (s = Send, q = quit)"
    t_wall0 = time.monotonic()
    send_wall = None
    processed = chunks_total = 0
    proc_ms = []
    first_frame_ts = last_frame_ts = None
    verified = []
    last = None
    while True:
        try:
            fr = q.get(timeout=1.0)
        except queue.Empty:
            if time.monotonic() - t_wall0 > a.max_seconds:
                break
            continue
        if fr is None or time.monotonic() - t_wall0 > a.max_seconds:
            break
        t1 = time.monotonic()
        res = dec.push(fr)
        proc_ms.append((time.monotonic() - t1) * 1e3)
        processed += 1
        chunks_total += len(res["chunks"])
        first_frame_ts = fr["capture_ts_s"] if first_frame_ts is None else first_frame_ts
        last_frame_ts = fr["capture_ts_s"]
        now = time.monotonic()
        for m in res["messages"]:
            m["wall_s"] = now - t_wall0
            if send_ts is not None and m.get("verified_ts") is not None:
                m["delivery_s"] = m["verified_ts"] - send_ts
                m["delivery_clock"] = fr["ts_kind"]
            elif send_wall is not None:
                m["delivery_s"] = now - send_wall
                m["delivery_clock"] = "wall (s key)"
            if m.get("delivery_s"):
                m["goodput_bps"] = m["payload_bytes"] * 8 / m["delivery_s"] if m["crc_ok"] else 0.0
            m["matches_expected"] = (m["payload"] == expected) if expected else None
            verified.append(m)
            print("\n=== MESSAGE #%d  crc_ok=%s  %d bytes  delivery %s  goodput %s\n%s\n"
                  % (m["packet_id"], m["crc_ok"], m["payload_bytes"],
                     "%.2f s" % m["delivery_s"] if m.get("delivery_s") else "n/a (no Send mark)",
                     "%.1f bit/s" % m["goodput_bps"] if m.get("goodput_bps") else "n/a", m["payload"]))
        prog = dec.asm.progress() if hasattr(dec, "asm") else {}
        status = ["frame %d  %.1f fps  dropped %d  chunks %d  %s%s" % (
            fr["frame_id"], processed / max(now - t_wall0, 1e-6), reader.dropped, chunks_total,
            " ".join("msg %s: %d" % kv for kv in prog.items()), "  [FRAME-MEAN CONTROL]" if a.frame_mean else "")]
        if verified:
            v = verified[-1]
            status.append(("VERIFIED: " if v["crc_ok"] else "CRC FAIL: ") + v["payload"][:70])
        if win or res["messages"]:
            img = draw_preview(fr, res, roi, status)
            if res["messages"]:
                cv2.imwrite(out.replace(".json", "-verified.png"), img)
            if win:
                cv2.imshow(win, img)
                k = cv2.waitKey(1) & 0xFF
                if k in (ord("q"), 27):
                    break
                if k == ord("s"):
                    send_wall = time.monotonic()
                    print("Send marked")
        last = res
        if verified and verified[-1]["crc_ok"] and not a.keep_going:
            break
    reader.done.set()
    elapsed = time.monotonic() - t_wall0
    if win:
        cv2.destroyAllWindows()
    setup = None
    if a.setup_file:
        with open(a.setup_file) as f:
            setup = json.load(f)
    stream_span = (last_frame_ts - first_frame_ts) if processed > 1 else None
    log = {
        "time": stamp, "protocol": "v2-proposed", "source": reader.info, "setup": setup, "roi": roi,
        "orientation": a.orientation, "decoder": a.decoder or "04-demo/rs_ref.py:Decoder",
        "frame_mean_control": a.frame_mean, "frames_read": reader.read, "frames_processed": processed,
        "frames_dropped_in_queue": reader.dropped, "wall_s": elapsed,
        "effective_fps": processed / stream_span if stream_span else None,
        "decode_ms_median": float(np.median(proc_ms)) if proc_ms else None,
        "decode_ms_p95": float(np.percentile(proc_ms, 95)) if proc_ms else None,
        "chunks_crc_ok": chunks_total, "send_ts": send_ts, "expected": expected,
        "messages": verified, "success": any(m["crc_ok"] and m.get("matches_expected") is not False for m in verified),
        "last_profile_frame": last["frame_id"] if last else None,
    }
    with open(out, "w") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)
    print("frames %d (dropped %d), effective %.1f fps, decode %.1f ms/frame median, chunks %d, success=%s"
          % (processed, reader.dropped, log["effective_fps"] or 0, log["decode_ms_median"] or 0, chunks_total,
             log["success"]))
    print("run log:", os.path.relpath(out))
    if a.frame_mean:  # the control passes when nothing verifies
        print("frame-mean control:", "PASS (no packet)" if not verified else "FAIL (verified without row data)")
        return 1 if verified else 0
    return 0 if log["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
