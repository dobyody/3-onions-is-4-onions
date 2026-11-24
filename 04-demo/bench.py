"""Integration bench harness for the rolling-shutter modem (role 4).

Run everything from the project root.

  # 1. First independent check: synthetic fixture -> receiver -> score (exit code 0 = pass)
  python 04-demo/bench.py fixture

  # 2. One real attempt (appends a row to 04-demo/results/trials.jsonl)
  python 04-demo/bench.py run --video clips/try01.mp4 --roi 410,220,300,300 \
      --setup "A: iPhone 1080p30, 40 cm, room light" --attempt 1

  # 3. Summary table per setup -> 04-demo/results/RESULTS.md
  python 04-demo/bench.py report

  # 4. Check the scope output follows the contract
  python 04-demo/bench.py scope --video clips/stripes.mp4 --frame 0 --roi 0,0,1080,1920
"""
import argparse
import datetime
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from metrics import RECEIVER_FIELDS, SCOPE_FIELDS, aggregate, check_schema, score_attempt  # noqa: E402
from protocol import ROOT, build_packet, load_reference  # noqa: E402

DECODER = os.path.join(ROOT, "02-receiver", "decode.py")
SCOPE = os.path.join(ROOT, "03-scope", "analyze.py")
RESULTS_DIR = os.path.join(HERE, "results")
TRIALS = os.path.join(RESULTS_DIR, "trials.jsonl")
FIXTURE_DIR = os.path.join(HERE, "fixtures")


def video_duration_s(path):
    import cv2
    cap = cv2.VideoCapture(path)
    n = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    return (n / fps) if fps and n else None


def run_tool(script, args, out_path):
    if not os.path.exists(script):
        sys.exit("not found: %s\n(the owning role has not delivered it yet; pull their branch or wait)"
                 % os.path.relpath(script, ROOT))
    cmd = [sys.executable, script] + args + ["--out", out_path]
    print("$ " + " ".join(os.path.relpath(c, ROOT) if os.path.isabs(c) and c.startswith(ROOT) else c for c in cmd))
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if proc.stdout.strip():
        print(proc.stdout.rstrip())
    if proc.returncode != 0:
        print(proc.stderr.rstrip(), file=sys.stderr)
        sys.exit("tool exited with code %d" % proc.returncode)
    if not os.path.exists(out_path):
        sys.exit("tool finished but did not write %s (contract: JSON must always be written)" % out_path)
    with open(out_path) as f:
        return json.load(f)


def decode(video, roi, decoder, out_path):
    data = run_tool(decoder, ["--video", video, "--roi", roi], out_path)
    problems = check_schema(data, RECEIVER_FIELDS)
    if problems:
        print("CONTRACT PROBLEMS in receiver output:\n  - " + "\n  - ".join(problems))
    return data, problems


def print_score(s):
    ber = "n/a" if s["ber"] is None else "%.4f" % s["ber"]
    print("synchronized=%s crc_ok=%s success=%s payload=%r" % (s["synchronized"], s["crc_ok"], s["success"], s["payload_ascii"]))
    print("BER=%s (%d/%d compared bits), erased=%d, missing=%d, bits layout=%s"
          % (ber, s["unequal_bits"], s["compared_bits"], s["erased_bits"], s["missing_bits"], s["bits_layout"]))


# ---------------------------------------------------------------- commands

def cmd_fixture(a):
    payload, ref_hex = load_reference()
    mine = build_packet(payload).hex()
    if ref_hex and ref_hex != mine:
        sys.exit("packet mismatch: fixtures/packet-v1.json has %s, CONTRACT rules give %s" % (ref_hex, mine))
    print("reference packet %s (%r)%s" % (mine, payload, "" if ref_hex else "  [no packet_hex in fixture, computed]"))

    variants = {
        "synth_clean": [],
        "synth_noisy": ["--noise", "10", "--blur", "5", "--fps", "29.97", "--gain", "0.85", "--offset", "12", "--seed", "7"],
    }
    os.makedirs(FIXTURE_DIR, exist_ok=True)
    failures = 0
    for name, extra in variants.items():
        video = os.path.join(FIXTURE_DIR, name + ".mp4")
        truth_path = video + ".truth.json"
        if a.regenerate or not os.path.exists(truth_path) or not os.path.exists(video):
            subprocess.run([sys.executable, os.path.join(HERE, "make_fixture.py"), "--out", video,
                            "--payload", payload] + extra, check=True, cwd=ROOT)
        with open(truth_path) as f:
            truth = json.load(f)
        print("\n=== %s ===" % name)
        out = os.path.join(FIXTURE_DIR, name + ".decode.json")
        data, problems = decode(video, ",".join(map(str, truth["roi"])), a.decoder, out)
        s = score_attempt(data, payload)
        print_score(s)
        ok = s["success"] and s["unequal_bits"] == 0 and not problems
        start = data.get("packet_start_s")
        if start is not None:
            err = abs(start - truth["packet_start_s"])
            print("packet_start_s=%.3f (truth %.3f, error %.3f s)" % (start, truth["packet_start_s"], err))
            ok = ok and err <= 0.2
        print("RESULT:", "PASS" if ok else "FAIL")
        failures += not ok
    print("\n%d/%d fixtures passed" % (len(variants) - failures, len(variants)))
    sys.exit(1 if failures else 0)


def cmd_run(a):
    payload = a.expected or load_reference()[0]
    os.makedirs(RESULTS_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = os.path.join(RESULTS_DIR, "decode-%s.json" % stamp)
    data, problems = decode(a.video, a.roi, a.decoder, out)
    s = score_attempt(data, payload)
    print_score(s)
    elapsed = a.elapsed_s if a.elapsed_s is not None else video_duration_s(a.video)
    tx = {}
    if a.tx_log:
        with open(a.tx_log) as f:
            log = json.load(f)
        tx = {"tx_log": a.tx_log, "timing_ok": log.get("timing_ok"),
              "tx_packet_hex": log.get("packet_hex"), "tx_payload": log.get("payload_ascii")}
        if log.get("timing_ok") is False:
            print("WARNING: transmit log has timing_ok=false -> repeat this attempt (marked invalid_tx)")
        if (log.get("payload_ascii") or payload) != payload:
            print("WARNING: transmit log payload %r differs from expected %r" % (log.get("payload_ascii"), payload))
    row = dict(s, time=stamp, setup=a.setup, attempt=a.attempt, video=a.video, roi=a.roi,
               expected=payload, elapsed_s=elapsed or 0.0, decode_json=os.path.relpath(out, ROOT),
               contract_problems=problems, notes=a.notes, **tx)
    with open(TRIALS, "a") as f:
        f.write(json.dumps(row) + "\n")
    print("logged to %s (elapsed %.1f s)" % (os.path.relpath(TRIALS, ROOT), row["elapsed_s"]))


def cmd_report(a):
    if not os.path.exists(TRIALS):
        sys.exit("no trials yet: run 'bench.py run ...' first")
    with open(TRIALS) as f:
        rows = [json.loads(line) for line in f if line.strip()]
    invalid = [r for r in rows if r.get("timing_ok") is False]
    rows_valid = [r for r in rows if r.get("timing_ok") is not False]
    setups = {}
    for r in rows_valid:
        setups.setdefault(r.get("setup") or "(no setup)", []).append(r)

    def fmt(v, pct=False, digits=3):
        if v is None:
            return "n/a"
        return ("%.0f%%" % (100 * v)) if pct else ("%.*f" % (digits, v))

    lines = ["# Bench results", "",
             "Generated %s from `results/trials.jsonl`. Metrics follow CONTRACT.md." % datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
             "",
             "| Setup | Attempts | CRC-valid | Success rate | Never synced | Pre-CRC BER (unequal/compared) | Erased | Missing | Goodput (bit/s) |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for name, rs in setups.items():
        g = aggregate(rs)
        lines.append("| %s | %d | %d | %s | %d | %s (%d/%d) | %d | %d | %s over %.0f s |" % (
            name, g["attempts"], g["successes"], fmt(g["packet_success_rate"], pct=True), g["never_synchronized"],
            fmt(g["ber"], digits=4), g["unequal_bits"], g["compared_bits"], g["erased_bits"], g["missing_bits"],
            fmt(g["goodput_bps"]), g["elapsed_s"]))
        target = "met" if g["successes"] >= 8 and g["attempts"] >= 10 else "not yet"
        lines.append("| ↳ target ≥8/10 | %s | | | | | | | |" % target)
    if invalid:
        lines += ["", "%d attempt(s) excluded because the sender log had timing_ok=false (listed below)." % len(invalid)]
    lines += ["", "## Attempts", "",
              "| Time | Setup | # | Success | CRC | Payload | BER | Erased | Missing | Notes |",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        lines.append("| %s | %s | %s | %s | %s | %s | %s | %d | %d | %s |" % (
            r["time"], r.get("setup") or "", r.get("attempt") or "", "yes" if r["success"] else "no", r["crc_ok"],
            r["payload_ascii"], fmt(r["ber"], digits=4), r["erased_bits"], r["missing_bits"], (r.get("notes") or "") + (" [tx timing_ok=false, excluded]" if r.get("timing_ok") is False else "")))
    path = os.path.join(RESULTS_DIR, "RESULTS.md")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print("\nwrote " + os.path.relpath(path, ROOT))


def cmd_scope(a):
    out = a.out or os.path.join(tempfile.gettempdir(), "scope-check.json")
    args = ["--video", a.video, "--frame", str(a.frame), "--roi", a.roi]
    if a.row_time_s is not None:
        args += ["--row-time-s", str(a.row_time_s)]
    data = run_tool(SCOPE, args, out)
    problems = check_schema(data, SCOPE_FIELDS)
    pk = data.get("peak_cycles_per_row")
    print("axis=%s peak=%s cycles/row%s, peak_hz=%s" % (
        data.get("analysis_axis"), pk, " (period %.1f rows)" % (1 / pk) if pk else "", data.get("peak_hz")))
    if data.get("peak_hz") is not None and data.get("row_time_s") is None:
        problems.append("peak_hz reported without row_time_s calibration")
    print("schema:", "OK" if not problems else "PROBLEMS\n  - " + "\n  - ".join(problems))
    sys.exit(1 if problems else 0)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fixture", help="synthetic end-to-end check of the receiver")
    f.add_argument("--decoder", default=DECODER)
    f.add_argument("--regenerate", action="store_true", help="rebuild the synthetic videos")
    f.set_defaults(func=cmd_fixture)

    r = sub.add_parser("run", help="decode and score one real attempt")
    r.add_argument("--video", required=True)
    r.add_argument("--roi", required=True, help="x,y,w,h in decoded pixels")
    r.add_argument("--setup", required=True, help='e.g. "A: iPhone 1080p30, 40 cm, room light"')
    r.add_argument("--attempt", type=int)
    r.add_argument("--expected", help="expected payload (default: reference fixture)")
    r.add_argument("--elapsed-s", type=float, help="test time for goodput (default: clip duration)")
    r.add_argument("--notes", default="")
    r.add_argument("--tx-log", help="tx-log-<time>.json saved by the sender page")
    r.add_argument("--decoder", default=DECODER)
    r.set_defaults(func=cmd_run)

    sub.add_parser("report", help="write results/RESULTS.md").set_defaults(func=cmd_report)

    s = sub.add_parser("scope", help="run 03-scope/analyze.py and check its JSON")
    s.add_argument("--video", required=True)
    s.add_argument("--frame", type=int, default=0)
    s.add_argument("--roi", required=True)
    s.add_argument("--row-time-s", type=float)
    s.add_argument("--out")
    s.set_defaults(func=cmd_scope)

    a = p.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
