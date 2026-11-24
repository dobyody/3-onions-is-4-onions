"""End-to-end check of the v2 integration kit (exit code 0 = all pass). Run from the project root.

  python3 04-demo/selftest2.py

Covers: reference packet, chunk CRC, out-of-order reassembly, synthetic rolling-shutter fixtures
(clean, hard + rotated + dropped frames), the constant-light and frame-mean controls, live.py on a
fixture and on an mp4, and the trial sheet. Fixtures are written to 04-demo/fixtures/ (ignored by Git
except packet-v2.json); results go to a temporary folder.
"""
import json
import os
import random
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import protocol2 as p2  # noqa: E402
import rs_ref  # noqa: E402

FX = os.path.join(HERE, "fixtures")
PY = sys.executable
failures = []


def check(name, cond, detail=""):
    print("%s  %s %s" % ("ok  " if cond else "FAIL", name, detail))
    if not cond:
        failures.append(name)


def run(args, env=None):
    r = subprocess.run([PY] + args, capture_output=True, text=True, env=env)
    return r.returncode, r.stdout + r.stderr


def decode_npz(path, frame_mean=False):
    d = np.load(path)
    dec = rs_ref.Decoder(frame_mean=frame_mean)
    n_chunks, msg = 0, None
    for img, fid, ts in zip(d["frames"], d["frame_id"], d["capture_ts_s"]):
        r = dec.push({"frame_id": int(fid), "image": img, "orientation": int(d["orientation"]), "capture_ts_s": float(ts)})
        n_chunks += len(r["chunks"])
        msg = msg or (r["messages"][0] if r["messages"] else None)
    return n_chunks, msg


def main():
    # protocol
    ref = p2.reference_json()
    with open(p2.FIXTURE_V2) as f:
        pub = json.load(f)
    check("packet-v2.json matches protocol2.py", pub == json.loads(json.dumps(ref, ensure_ascii=False)))
    check("reference message is 64 UTF-8 bytes", ref["message_bytes"] == 64)
    chunks = p2.build_chunks(p2.REFERENCE_MESSAGE)
    bad = bytearray(chunks[5])
    bad[6] ^= 0x10
    check("chunk CRC catches a flipped bit", not p2.parse_chunk(bytes(bad))["crc_ok"])
    asm, out = p2.Reassembler(), None
    order = list(range(len(chunks))) * 2
    random.Random(3).shuffle(order)
    for i in order:
        out = out or asm.add(p2.parse_chunk(chunks[i]), i)
    check("reassembly from shuffled duplicates", out and out["crc_ok"] and out["payload"] == p2.REFERENCE_MESSAGE)

    # fixtures
    specs = {
        "rs_clean": [],
        "rs_hard": ["--depth", "0.08", "--noise", "8", "--jpeg", "60", "--drop", "0.2", "--orientation", "90", "--seed", "2"],
        "rs_constant": ["--mode", "constant"],
        # same decoder, a 30 fps phone with its own chip size (rs_plan.py picks it per camera mode)
        "rs_30fps": ["--fps", "30", "--row-time-us", "28", "--chip-us", "100", "--frames", "90", "--seed", "5"],
    }
    for name, extra in specs.items():
        path = os.path.join(FX, name + ".npz")
        stale = True
        if os.path.exists(path + ".truth.json") and os.path.exists(path):
            with open(path + ".truth.json") as f:
                old = json.load(f)["params"]
            ref = json.loads(subprocess.run([PY, "-c", "import sys; sys.argv=['x','--out','x']+%r; sys.path.insert(0, %r); "
                                             "import make_rs_fixture as m, json; print(json.dumps(vars(m.parse_args())))" % (extra, HERE)],
                                            capture_output=True, text=True).stdout)
            stale = any(old.get(k) != v for k, v in ref.items() if k not in ("out", "png", "mp4"))
        if stale:
            rc, txt = run([os.path.join(HERE, "make_rs_fixture.py"), "--out", path, "--png"] + extra)
            check("generate " + name, rc == 0, txt.strip().splitlines()[-1] if txt.strip() else "")
    for name in ("rs_clean", "rs_hard", "rs_30fps"):
        path = os.path.join(FX, name + ".npz")
        with open(path + ".truth.json") as f:
            truth = json.load(f)
        expected = sum(len(v) for v in truth["expected_chunks_per_frame"].values())
        n, msg = decode_npz(path)
        check("%s: every complete chunk decoded" % name, n >= expected, "(%d/%d)" % (n, expected))
        ok = msg and msg["crc_ok"] and msg["payload"] == truth["message_utf8"]
        check("%s: message verified" % name, ok, "(%.2f s after Send)" % (msg["verified_ts"] - truth["send_s"]) if ok else "")
        check("%s: within 25 s" % name, ok and msg["verified_ts"] - truth["send_s"] <= 25)
    n, msg = decode_npz(os.path.join(FX, "rs_constant.npz"))
    check("control: constant light -> no packet", n == 0 and msg is None)
    n, msg = decode_npz(os.path.join(FX, "rs_clean.npz"), frame_mean=True)
    check("control: frame-mean -> no packet", n == 0 and msg is None)

    # integration command and trial sheet
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ, V2_RESULTS_DIR=tmp)
        log = os.path.join(tmp, "live-a.json")
        rc, txt = run([os.path.join(HERE, "live.py"), "--fixture", os.path.join(FX, "rs_hard.npz"), "--headless", "--out", log])
        with open(log) as f:
            lg = json.load(f)
        check("live.py on fixture verifies", rc == 0 and lg["success"], "(delivery %.2f s)" % lg["messages"][0]["delivery_s"] if lg["messages"] else txt[-300:])
        check("live.py writes preview PNG", os.path.exists(log.replace(".json", "-verified.png")))
        rt = os.path.join(tmp, "live-rt.json")
        run([os.path.join(HERE, "live.py"), "--fixture", os.path.join(FX, "rs_clean.npz"), "--headless", "--realtime",
             "--keep-going", "--max-seconds", "3", "--out", rt])
        with open(rt) as f:
            lg = json.load(f)
        check("decoder keeps up with 60 fps in real time", lg["decode_ms_median"] < 1000 / 60 and lg["success"],
              "(median %.1f ms/frame, %d of %d frames dropped)" % (lg["decode_ms_median"], lg["frames_dropped_in_queue"], lg["frames_read"]))
        rc, txt = run([os.path.join(HERE, "rs_plan.py"), "--fps", "60", "--rows", "1080", "--row-time-us", "14", "--exposure-us", "40"])
        check("rs_plan: 100 us chips cannot work at 60 fps, 50 us recommended",
              "| 100 | 7.1 | 17.6 | 0.00" in txt and "recommended: --chip-us 50 " in txt)
        rc, txt = run([os.path.join(HERE, "live.py"), "--fixture", os.path.join(FX, "rs_clean.npz"), "--headless",
                       "--frame-mean", "--out", os.path.join(tmp, "live-ctl.json")])
        check("live.py frame-mean control passes", rc == 0 and "PASS (no packet)" in txt)
        mp4 = os.path.join(tmp, "rs.npz")
        run([os.path.join(HERE, "make_rs_fixture.py"), "--out", mp4, "--frames", "60", "--mp4"])
        rc, txt = run([os.path.join(HERE, "live.py"), "--video", os.path.join(tmp, "rs.mp4"), "--headless",
                       "--send-ts", "0.5", "--out", os.path.join(tmp, "live-mp4.json")])
        check("live.py on mp4 video verifies", rc == 0, txt.strip().splitlines()[-2] if rc == 0 else txt[-300:])
        t2 = os.path.join(HERE, "trials2.py")
        steps = [
            ["setup", "--name", "SYN", "--phone", "synthetic", "--camera-mode", "1080 rows, 28 us/row", "--fps", "30",
             "--resolution", "160x1080", "--orientation", "90", "--row-time-us", "28", "--emitter", "simulated carousel"],
            ["attempt", "--setup", "SYN", "--run", log],
            ["attempt", "--setup", "SYN", "--failed", "--elapsed-s", "25", "--notes", "test failure row"],
            ["attempt", "--setup", "SYN", "--run", os.path.join(tmp, "live-ctl.json")],
            ["latency", "--setup", "SYN", "--diffs-ms", ",".join(str(300 + 10 * i) for i in range(20))],
            ["visibility-plan", "--observer", "T1", "--seed", "4"],
        ]
        for s in steps:
            rc, txt = run([t2] + s, env=env)
            check("trials2 " + s[0], rc == 0, "" if rc == 0 else txt[-300:])
        with open(os.path.join(tmp, "visibility-T1-plan.json")) as f:
            plan = "".join(json.load(f)["trials"])
        check("visibility plan is balanced", plan.count("M") == plan.count("S") == 5, plan)
        rc, txt = run([t2, "visibility-score", "--observer", "T1", "--answers", "M" * 10, "--conditions", "test"], env=env)
        check("trials2 visibility-score", rc == 0 and "5/10" in txt, txt.strip().splitlines()[-1] if txt.strip() else "")
        rc, txt = run([t2, "report"], env=env)
        check("trials2 report", rc == 0 and "| SYN | 2 | 1 |" in txt and "| SYN | 20 | 395 | 480 | met |" in txt
              and "1 run(s), 0 verified" in txt, "" if rc == 0 else txt[-300:])
    print("\nselftest2: %s" % ("ALL PASS" if not failures else "FAILED: " + ", ".join(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
