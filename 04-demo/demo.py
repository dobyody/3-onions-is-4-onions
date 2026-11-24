"""One-minute demo runner: recovered message + labeled rolling-shutter trace.

Run from the project root. It calls the real role tools (02-receiver/decode.py and
03-scope/analyze.py), then draws one figure and prints a short summary.

  # live clip (or the documented fallback clip) + a real stripe frame
  python 04-demo/demo.py --video clips/demo.mp4 --roi 410,220,300,300 \
      --scope-video clips/stripes.mp4 --scope-roi 0,0,1080,1920 --frame 12

  # rehearsal with synthetic inputs only (everything labeled SYNTHETIC)
  python 04-demo/demo.py --synthetic

Outputs go to 04-demo/demo_out/: demo.png, summary.json, decode.json, scope.json.
"""
import argparse
import json
import os
import subprocess
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bench  # noqa: E402
from metrics import SCOPE_FIELDS, check_schema, score_attempt  # noqa: E402
from protocol import ROOT, load_reference, payload_bits  # noqa: E402

OUT = os.path.join(HERE, "demo_out")


def read_frame(video, index):
    cap = cv2.VideoCapture(video)
    cap.set(cv2.CAP_PROP_POS_FRAMES, index)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        sys.exit("cannot read frame %d of %s" % (index, video))
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)


def ensure_synthetic():
    fx = os.path.join(HERE, "fixtures")
    modem = os.path.join(fx, "synth_noisy.mp4")
    stripes = os.path.join(fx, "synth_stripes.mp4")
    if not os.path.exists(modem + ".truth.json"):
        subprocess.run([sys.executable, os.path.join(HERE, "make_fixture.py"), "--out", modem, "--noise", "10",
                        "--blur", "5", "--fps", "29.97", "--gain", "0.85", "--offset", "12", "--seed", "7"], check=True)
    if not os.path.exists(stripes + ".truth.json"):
        subprocess.run([sys.executable, os.path.join(HERE, "make_stripes.py"), "--out", stripes], check=True)
    with open(modem + ".truth.json") as f:
        roi = ",".join(map(str, json.load(f)["roi"]))
    with open(stripes + ".truth.json") as f:
        st = json.load(f)
    return modem, roi, stripes, ",".join(map(str, st["roi"])), st


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--video", help="modem clip (live or fallback)")
    p.add_argument("--roi", help="x,y,w,h of the brightness patch")
    p.add_argument("--expected", help="expected payload (default: reference fixture)")
    p.add_argument("--scope-video", help="clip with stripes; omit to show only the modem part")
    p.add_argument("--scope-roi")
    p.add_argument("--frame", type=int, default=0)
    p.add_argument("--row-time-s", type=float, help="calibrated row time for THIS camera mode")
    p.add_argument("--synthetic", action="store_true", help="use synthetic fixtures for both parts")
    p.add_argument("--label", default="", help='setup label shown on the figure, e.g. "LIVE" or "FALLBACK 2026-11-25 setup A"')
    p.add_argument("--no-open", action="store_true")
    a = p.parse_args()

    synth_modem = synth_scope = False
    stripes_truth = None
    if a.synthetic:
        a.video, a.roi, a.scope_video, a.scope_roi, stripes_truth = ensure_synthetic()
        synth_modem = synth_scope = True
    if not a.video or not a.roi:
        p.error("--video and --roi are required (or use --synthetic)")
    os.makedirs(OUT, exist_ok=True)
    expected = a.expected or load_reference()[0]

    # ---- part 1: send and decode
    dec, problems = bench.decode(a.video, a.roi, bench.DECODER, os.path.join(OUT, "decode.json"))
    s = score_attempt(dec, expected)
    window = None
    if dec.get("packet_start_s") is not None and dec.get("packet_end_s") is not None:
        window = dec["packet_end_s"] - dec["packet_start_s"]
    n_payload = len(payload_bits(expected))
    goodput = (n_payload / window) if (s["success"] and window) else 0.0

    # ---- part 2: scope
    scope = None
    if a.scope_video:
        args = ["--video", a.scope_video, "--frame", str(a.frame), "--roi", a.scope_roi]
        if a.row_time_s is not None:
            args += ["--row-time-s", str(a.row_time_s)]
        scope = bench.run_tool(bench.SCOPE, args, os.path.join(OUT, "scope.json"))
        sp = check_schema(scope, SCOPE_FIELDS)
        if sp:
            print("CONTRACT PROBLEMS in scope output:\n  - " + "\n  - ".join(sp))

    # ---- figure
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    tag_m = "SYNTHETIC" if synth_modem else (a.label or "RECORDED")
    fig = plt.figure(figsize=(14, 8 if scope else 4.5))
    gs = fig.add_gridspec(2 if scope else 1, 3)

    ax = fig.add_subplot(gs[0, 0])
    img = read_frame(a.video, 0)
    x, y, w, h = map(int, a.roi.split(","))
    ax.imshow(img)
    ax.add_patch(plt.Rectangle((x, y), w, h, fill=False, ec="red", lw=2))
    ax.set_title("Modem clip [%s]\nred = ROI" % tag_m, fontsize=10)
    ax.axis("off")

    ax = fig.add_subplot(gs[0, 1:])
    ax.axis("off")
    ok = s["success"]
    ax.text(0.0, 0.85, "Recovered: %r" % dec.get("payload_ascii"), fontsize=22, family="monospace",
            color="green" if ok else "firebrick", transform=ax.transAxes)
    ber = "n/a" if s["ber"] is None else "%.4f (%d/%d bits)" % (s["ber"], s["unequal_bits"], s["compared_bits"])
    lines = ["Expected: %r" % expected,
             "CRC: %s   packet found: %s" % ({True: "OK", False: "FAIL", None: "n/a"}[dec.get("crc_ok")], dec.get("packet_found")),
             "Pre-CRC BER: %s   erased: %d   missing: %d" % (ber, s["erased_bits"], s["missing_bits"]),
             "Goodput: %.2f bit/s over packet window %s (line rate 5 bit/s)" % (goodput, "%.1f s" % window if window else "n/a"),
             "Timebase: %s" % dec.get("timebase")]
    ax.text(0.0, 0.05, "\n".join(lines), fontsize=12, family="monospace", transform=ax.transAxes, va="bottom")

    if scope:
        tag_s = "SYNTHETIC - not a hardware result" if synth_scope else (a.label or "RECORDED")
        prof = np.asarray(scope["profile"], float)
        ax = fig.add_subplot(gs[1, 0])
        fr = read_frame(a.scope_video, a.frame)
        ax.imshow(fr)
        sx, sy, sw, sh = map(int, a.scope_roi.split(","))
        ax.add_patch(plt.Rectangle((sx, sy), sw, sh, fill=False, ec="red", lw=1.5))
        ax.set_title("Frame %d [%s]" % (a.frame, tag_s), fontsize=10)
        ax.axis("off")

        ax = fig.add_subplot(gs[1, 1])
        ax.plot(prof, lw=1)
        ax.set_xlabel("row index (%s)" % scope.get("analysis_axis"))
        ax.set_ylabel("mean brightness")
        ax.set_title("Row-brightness profile", fontsize=10)

        ax = fig.add_subplot(gs[1, 2])
        d = prof - np.convolve(prof, np.ones(31) / 31, mode="same") if len(prof) > 62 else prof - prof.mean()
        spec = np.abs(np.fft.rfft(d * np.hanning(len(d))))
        f = np.fft.rfftfreq(len(d), d=1.0)
        ax.plot(f[1:], spec[1:], lw=1)
        pk = scope.get("peak_cycles_per_row")
        if pk:
            ax.axvline(pk, color="red", ls="--")
            txt = "peak %.4f cycles/row\nperiod %.1f rows" % (pk, 1 / pk)
            if scope.get("peak_hz") is not None and scope.get("row_time_s") is not None:
                txt += "\n= %.0f Hz (row time %.2e s)" % (scope["peak_hz"], scope["row_time_s"])
            else:
                txt += "\nHz: not calibrated"
            ax.text(0.98, 0.95, txt, transform=ax.transAxes, ha="right", va="top", fontsize=10,
                    bbox=dict(fc="white", ec="gray"))
        ax.set_xlabel("cycles per row")
        ax.set_title("Spectrum (display only; peak from scope.json)", fontsize=10)

    fig.tight_layout()
    png = os.path.join(OUT, "demo.png")
    fig.savefig(png, dpi=110)

    summary = {"modem_source": tag_m, "video": a.video, "roi": a.roi, "expected": expected, "score": s,
               "goodput_window_s": window, "goodput_bps": goodput, "receiver_contract_problems": problems}
    if scope:
        summary["scope"] = {k: scope.get(k) for k in SCOPE_FIELDS if k != "profile"}
        summary["scope"]["source"] = "SYNTHETIC" if synth_scope else (a.label or "RECORDED")
        if stripes_truth:
            summary["scope"]["truth_cycles_per_row"] = stripes_truth["cycles_per_row"]
    with open(os.path.join(OUT, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    print("\n================ DEMO ================")
    print("Recovered: %r   CRC: %s   goodput %.2f bit/s" % (dec.get("payload_ascii"), dec.get("crc_ok"), goodput))
    if scope:
        print("Scope peak: %s cycles/row  peak_hz: %s" % (scope.get("peak_cycles_per_row"), scope.get("peak_hz")))
        if stripes_truth:
            print("  (synthetic truth: %.5f cycles/row)" % stripes_truth["cycles_per_row"])
    print("Figure: %s" % os.path.relpath(png, ROOT))
    if not a.no_open and sys.platform == "darwin":
        subprocess.run(["open", png])


if __name__ == "__main__":
    main()
