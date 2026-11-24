"""v2 trial sheet: setups, delivery attempts, preview latency and blinded visibility trials (TASK.md).

Run from the project root. Everything lands in 04-demo/results/ and `report` writes RESULTS-v2.md.

  # 1. Record the hardware setup once (camera mode, effective fps, resolution, emitter settings)
  python3 04-demo/trials2.py setup --name A --phone "Pixel 7" --camera-mode "1080p30, exposure locked 1/8000" \
      --fps 30 --resolution 1920x1080 --orientation 90 --row-time-us 28 --emitter "LED + ESP32, 10 kHz chips, depth 25%" \
      --distance-cm 30 --transport "IP Webcam MJPEG over Wi-Fi"
  # 2. Log every delivery attempt (a live.py run log, or by hand). Failed attempts count too.
  python3 04-demo/trials2.py attempt --setup A --run 04-demo/results/live-20261124-190000.json
  python3 04-demo/trials2.py attempt --setup A --failed --elapsed-s 25 --notes "lost lock"
  # 3. Preview latency: one photo shows the real stopwatch and its image in the preview; enter real_ms:preview_ms
  python3 04-demo/trials2.py latency --setup A --pairs 12030:11610,15200:14840,...
  # 4. Visibility: make a blinded randomized plan per observer, run it, then score the answers
  python3 04-demo/trials2.py visibility-plan --observer O1 --trials 10
  python3 04-demo/trials2.py visibility-score --observer O1 --answers MSSMMSMSSM \
      --conditions "2 m, room lights on, white wall, observer seated"
  # 5. Summary
  python3 04-demo/trials2.py report
"""
import argparse
import datetime
import json
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.environ.get("V2_RESULTS_DIR") or os.path.join(HERE, "results")
ATTEMPTS = os.path.join(RESULTS, "attempts-v2.jsonl")
LATENCY = os.path.join(RESULTS, "latency-v2.jsonl")
VIS = os.path.join(RESULTS, "visibility-v2.jsonl")
TARGET_BYTES, TARGET_S, TARGET_OK, TARGET_N = 64, 25.0, 8, 10


def now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def append(path, row):
    os.makedirs(RESULTS, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(x) for x in f if x.strip()]


def cmd_setup(a):
    os.makedirs(RESULTS, exist_ok=True)
    d = {k: v for k, v in vars(a).items() if k != "func"}
    d["time"] = now()
    path = os.path.join(RESULTS, "setup-%s.json" % a.name)
    with open(path, "w") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)
    print("wrote", os.path.relpath(path))


def cmd_attempt(a):
    row = {"time": now(), "setup": a.setup, "notes": a.notes}
    if a.run:
        with open(a.run) as f:
            log = json.load(f)
        ok = [m for m in log["messages"] if m["crc_ok"] and m.get("matches_expected") is not False]
        m = ok[0] if ok else None
        row.update(run=a.run, source=log["source"], effective_fps=log.get("effective_fps"),
                   frames_dropped=log.get("frames_dropped_in_queue"), frame_mean_control=log.get("frame_mean_control"),
                   success=bool(m), payload_bytes=m["payload_bytes"] if m else 0,
                   delivery_s=m.get("delivery_s") if m else None,
                   elapsed_s=(m.get("delivery_s") if m and m.get("delivery_s") else a.elapsed_s or log.get("wall_s")),
                   frame_ids=(m["frame_ids"] if m else []), chunks=(m["chunks"] if m else None))
        if m and m.get("delivery_s") is None:
            print("WARNING: no Send mark in this run, so delivery time is unknown (press s in the preview at Send)")
    else:
        if a.elapsed_s is None:
            sys.exit("give --run, or --elapsed-s for a manual entry")
        row.update(success=not a.failed, payload_bytes=0 if a.failed else a.bytes,
                   delivery_s=None if a.failed else a.elapsed_s, elapsed_s=a.elapsed_s)
    if row.get("frame_mean_control"):
        row["notes"] = (row["notes"] + " [frame-mean control, not a delivery attempt]").strip()
    append(ATTEMPTS, row)
    print("logged: success=%s bytes=%s elapsed=%s s" % (row["success"], row["payload_bytes"], row["elapsed_s"]))


def cmd_latency(a):
    vals = []
    if a.pairs:
        for pr in a.pairs.split(","):
            shown, preview = (float(v) for v in pr.split(":"))
            vals.append(shown - preview)
    if a.diffs_ms:
        vals += [float(v) for v in a.diffs_ms.split(",")]
    for v in vals:
        if v < 0:
            sys.exit("negative latency %.0f ms: the order is real_stopwatch:preview_stopwatch" % v)
        append(LATENCY, {"time": now(), "setup": a.setup, "latency_ms": v, "notes": a.notes})
    print("logged %d observations" % len(vals))


def cmd_vis_plan(a):
    n = a.trials
    seq = ["M"] * (n // 2) + ["S"] * (n - n // 2)
    rng = random.Random(a.seed if a.seed is not None else random.SystemRandom().randrange(1 << 30))
    rng.shuffle(seq)
    os.makedirs(RESULTS, exist_ok=True)
    plan = {"observer": a.observer, "time": now(), "trials": seq, "legend": "M = modulating (carousel), S = steady light"}
    path = os.path.join(RESULTS, "visibility-%s-plan.json" % a.observer)
    with open(path, "w") as f:
        json.dump(plan, f, indent=2)
    sheet = os.path.join(RESULTS, "visibility-%s-observer-sheet.md" % a.observer)
    with open(sheet, "w") as f:
        f.write("# Visibility trial, observer %s\n\nFor each trial write M if you think the light is sending data "
                "(modulating) or S if it is steady. Guess if unsure.\n\n| Trial | Your answer |\n| --- | --- |\n"
                % a.observer + "".join("| %d | |\n" % (i + 1) for i in range(n)))
    print("operator plan (do not show the observer):", os.path.relpath(path))
    print("observer sheet:", os.path.relpath(sheet))
    print("Keep scene, background brightness and observer position fixed. The operator who knows the plan should "
          "not be visible to the observer while switching modes.")


def binom_tail(k, n):
    return sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n


def cmd_vis_score(a):
    path = os.path.join(RESULTS, "visibility-%s-plan.json" % a.observer)
    with open(path) as f:
        plan = json.load(f)["trials"]
    ans = [c for c in a.answers.upper() if c in "MS"]
    if len(ans) != len(plan):
        sys.exit("%d answers for %d trials" % (len(ans), len(plan)))
    correct = sum(x == y for x, y in zip(ans, plan))
    hits = sum(x == y == "M" for x, y in zip(ans, plan))
    fa = sum(x == "M" and y == "S" for x, y in zip(ans, plan))
    row = {"time": now(), "observer": a.observer, "trials": len(plan), "correct": correct, "hits_M": hits,
           "false_alarms_on_S": fa, "p_value_one_sided": binom_tail(correct, len(plan)),
           "conditions": a.conditions, "plan": "".join(plan), "answers": "".join(ans)}
    append(VIS, row)
    print("observer %s: %d/%d correct, one-sided p=%.3f (chance = %d/%d)"
          % (a.observer, correct, len(plan), row["p_value_one_sided"], len(plan) // 2, len(plan)))


def pct(vals, q):
    s = sorted(vals)
    if not s:
        return None
    k = (len(s) - 1) * q / 100.0
    f = math.floor(k)
    return s[f] + (s[min(f + 1, len(s) - 1)] - s[f]) * (k - f)


def cmd_report(a):
    att = [r for r in read(ATTEMPTS) if not r.get("frame_mean_control")]
    controls = [r for r in read(ATTEMPTS) if r.get("frame_mean_control")]
    lat, vis = read(LATENCY), read(VIS)
    setups = {}
    for f in sorted(os.listdir(RESULTS)) if os.path.isdir(RESULTS) else []:
        if f.startswith("setup-") and f.endswith(".json"):
            with open(os.path.join(RESULTS, f)) as fh:
                s = json.load(fh)
            setups[s["name"]] = s
    L = ["# v2 results (live rolling-shutter modem)", "", "Generated %s by `04-demo/trials2.py report`. "
         "Targets from TASK.md: >= %d bytes in <= %.0f s, >= %d/%d successes, preview latency p95 < 1 s over >= 20 "
         "observations, 10 blinded visibility trials per observer." % (now(), TARGET_BYTES, TARGET_S, TARGET_OK, TARGET_N), ""]
    L += ["## Setups", "", "| Setup | Phone | Camera mode | FPS | Resolution | Orientation | Row time (us) | Emitter | Distance (cm) | Transport |",
          "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for s in setups.values():
        L.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % tuple(
            s.get(k) if s.get(k) is not None else "" for k in
            ("name", "phone", "camera_mode", "fps", "resolution", "orientation", "row_time_us", "emitter", "distance_cm", "transport")))
    if not setups:
        L.append("| (none recorded: run `trials2.py setup`) | | | | | | | | | |")
    L += ["", "## Delivery", "", "Goodput = payload bits of verified messages / total time of all attempts, failed ones included.", "",
          "| Setup | Attempts | Verified | Within %.0f s with >= %d B | Median delivery (s) | Max delivery (s) | Goodput incl. retries (bit/s) | Mean effective fps | Target %d/%d |"
          % (TARGET_S, TARGET_BYTES, TARGET_OK, TARGET_N),
          "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    by = {}
    for r in att:
        by.setdefault(r["setup"], []).append(r)
    for name, rows in by.items():
        ok = [r for r in rows if r["success"]]
        good = [r for r in ok if (r.get("delivery_s") or 1e9) <= TARGET_S and r["payload_bytes"] >= TARGET_BYTES]
        d = [r["delivery_s"] for r in ok if r.get("delivery_s") is not None]
        total_t = sum(r.get("elapsed_s") or 0 for r in rows)
        bits = sum(r["payload_bytes"] * 8 for r in ok)
        fps = [r["effective_fps"] for r in rows if r.get("effective_fps")]
        L.append("| %s | %d | %d | %d | %s | %s | %s | %s | %s |" % (
            name, len(rows), len(ok), len(good), "%.2f" % pct(d, 50) if d else "n/a", "%.2f" % max(d) if d else "n/a",
            "%.1f" % (bits / total_t) if total_t else "n/a", "%.1f" % (sum(fps) / len(fps)) if fps else "n/a",
            "met" if len(good) >= TARGET_OK and len(rows) >= TARGET_N else "not yet"))
    if not by:
        L.append("| (no attempts yet) | | | | | | | | |")
    if controls:
        L += ["", "Frame-mean controls: %d run(s), %d verified a message (should be 0)."
              % (len(controls), sum(1 for r in controls if r["success"]))]
    L += ["", "## Preview latency (stopwatch)", "", "| Setup | Observations | Median (ms) | p95 (ms) | Target |", "| --- | --- | --- | --- | --- |"]
    lb = {}
    for r in lat:
        lb.setdefault(r["setup"], []).append(r["latency_ms"])
    for name, v in lb.items():
        p95 = pct(v, 95)
        L.append("| %s | %d | %.0f | %.0f | %s |" % (name, len(v), pct(v, 50), p95,
                                                     "met" if len(v) >= 20 and p95 < 1000 else ("need >= 20 obs" if len(v) < 20 else "missed")))
    if not lb:
        L.append("| (no observations yet) | | | | |")
    L += ["", "## Visibility (blinded, randomized, balanced)", "",
          "Demo-level check under the stated conditions only. p = chance of at least this many correct by guessing.", "",
          "| Observer | Correct | Hits on M | False alarms on S | p (one-sided) | Conditions |", "| --- | --- | --- | --- | --- | --- |"]
    for r in vis:
        L.append("| %s | %d/%d | %d | %d | %.3f | %s |" % (r["observer"], r["correct"], r["trials"], r["hits_M"],
                                                         r["false_alarms_on_S"], r["p_value_one_sided"], r["conditions"] or ""))
    if vis:
        L += ["", "Observers: %d. Total %d/%d correct." % (len({r['observer'] for r in vis}), sum(r["correct"] for r in vis),
                                                         sum(r["trials"] for r in vis))]
    else:
        L.append("| (no observers yet) | | | | | |")
    L += ["", "## All attempts", "", "| Time | Setup | Verified | Bytes | Delivery (s) | Elapsed (s) | Run log | Notes |",
          "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in read(ATTEMPTS):
        L.append("| %s | %s | %s | %s | %s | %s | %s | %s |" % (
            r["time"], r["setup"], "yes" if r["success"] else "no", r["payload_bytes"],
            "%.2f" % r["delivery_s"] if r.get("delivery_s") is not None else "", "%.2f" % r["elapsed_s"] if r.get("elapsed_s") else "",
            os.path.basename(r.get("run") or ""), r.get("notes") or ""))
    path = os.path.join(RESULTS, "RESULTS-v2.md")
    os.makedirs(RESULTS, exist_ok=True)
    with open(path, "w") as f:
        f.write("\n".join(L) + "\n")
    print("\n".join(L))
    print("\nwrote", os.path.relpath(path))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(required=True)
    s = sub.add_parser("setup")
    s.add_argument("--name", required=True)
    for k in ("phone", "camera-mode", "resolution", "emitter", "emitter-settings", "transport", "notes"):
        s.add_argument("--" + k)
    s.add_argument("--fps", type=float, help="effective stream fps measured on the laptop")
    s.add_argument("--orientation", type=int)
    s.add_argument("--row-time-us", type=float, help="from the scope calibration")
    s.add_argument("--distance-cm", type=float)
    s.set_defaults(func=cmd_setup)
    s = sub.add_parser("attempt")
    s.add_argument("--setup", required=True)
    s.add_argument("--run", help="live.py run log")
    s.add_argument("--failed", action="store_true")
    s.add_argument("--bytes", type=int, default=TARGET_BYTES)
    s.add_argument("--elapsed-s", type=float, help="Send to verified, or to giving up")
    s.add_argument("--notes", default="")
    s.set_defaults(func=cmd_attempt)
    s = sub.add_parser("latency")
    s.add_argument("--setup", required=True)
    s.add_argument("--pairs", help="real_ms:preview_ms,... read from one photo each")
    s.add_argument("--diffs-ms", help="latencies already subtracted, comma separated")
    s.add_argument("--notes", default="")
    s.set_defaults(func=cmd_latency)
    s = sub.add_parser("visibility-plan")
    s.add_argument("--observer", required=True)
    s.add_argument("--trials", type=int, default=10)
    s.add_argument("--seed", type=int, help="omit for a fresh random order")
    s.set_defaults(func=cmd_vis_plan)
    s = sub.add_parser("visibility-score")
    s.add_argument("--observer", required=True)
    s.add_argument("--answers", required=True, help="M/S per trial, e.g. MSSMMSMSSM")
    s.add_argument("--conditions", default="")
    s.set_defaults(func=cmd_vis_score)
    s = sub.add_parser("report")
    s.set_defaults(func=cmd_report)
    a = p.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
