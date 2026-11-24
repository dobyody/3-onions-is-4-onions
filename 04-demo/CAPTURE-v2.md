# v2 trial sheet (live rolling-shutter modem)

Commands run from the project root. Results go to `04-demo/results/`, and `trials2.py report` writes `RESULTS-v2.md`.
Count every attempt, failures included.

## 0. Hardware go/no-go (first 15–20 minutes)

All our phones film at **60 fps**. At 60 fps a frame lasts 16.7 ms and the rows are read out in only ~15 ms, so the
chunks must be short.

0. Pick the chip duration for the camera mode. Use the row time from the scope calibration; until then the tool guesses.
   ```
   python3 04-demo/rs_plan.py --fps 60 --rows 1080 --row-time-us 14 --exposure-us <shortest exposure the phone reaches>
   ```
   Set the emitter to the recommended `--chip-us`, and pass the printed `--rows-per-chip` to `live.py`.
1. Point the phone at the emitter running the carousel, in the **60 fps** video mode. Lock exposure as short as the camera
   allows (bands blur when the exposure is longer than a chip) and lock focus. Write down the exposure you get.
2. Look at a raw crop: `python3 04-demo/live.py --video <stream URL or clip> --roi x,y,w,h --orientation <deg>`.
   The row trace must show regular bands, and the zoomed strip must show `DD AA` bits.
3. Write the result in `04-demo/STATUS.md`: **verified** only if controlled symbols are distinguishable inside single frames.
   If not, write down the hardware limit and demo the live transport and the synthetic row decoder separately.

## 1. Record the setup once

```
python3 04-demo/trials2.py setup --name A --phone "..." --camera-mode "1080p60, exposure locked, focus locked" \
    --fps <effective stream fps, aim for 60> --resolution 1920x1080 --orientation 90 --row-time-us <from scope calibration> \
    --emitter "..." --emitter-settings "chip 50 us, depth 25%, exposure 1/20000" --distance-cm 30 --transport "..."
```

## 2. Delivery attempts (aim for 8/10 with ≥64 bytes in ≤25 s)

1. Choose a fresh 64-byte UTF-8 message at demo time. Set a new `msg_id` on the emitter.
2. Start `live.py` with the setup file. When the operator presses Send on the emitter, press **s** in the preview window
   (that starts the delivery timer).
   ```
   python3 04-demo/live.py --video <stream> --roi x,y,w,h --orientation 90 --rows-per-chip <chip_us/row_time_us> \
       --expected "<message>" --setup-file 04-demo/results/setup-A.json
   ```
3. Log it, whether it verified or not: `python3 04-demo/trials2.py attempt --setup A --run 04-demo/results/live-<time>.json`.
   If the run never verified, add `--elapsed-s 25`.
4. Run the control once per setup with the same stream plus `--frame-mean`, then log it the same way. It must verify nothing.

## 3. Preview latency (≥20 observations, p95 < 1 s)

The phone films at 60 fps, but check the `effective_fps` that `live.py` reports. Wi-Fi streams often deliver fewer
frames, which only slows delivery down (every frame is a chance to catch chunks).

Show a millisecond stopwatch on a second screen. Point the phone at it and photograph the real stopwatch next to its
image in the preview. Each photo gives one pair of readings, `real_ms:preview_ms`.
```
python3 04-demo/trials2.py latency --setup A --pairs 12030:11610,15200:14840,...
```

## 4. Visibility (10 blinded, balanced, randomized trials per observer)

Keep the scene, background brightness and observer position fixed. The operator follows the plan. The observer sees only
their own sheet.
```
python3 04-demo/trials2.py visibility-plan --observer O1
python3 04-demo/trials2.py visibility-score --observer O1 --answers MSSMMSMSSM --conditions "2 m, lights on, seated"
```
Publish the scores, the number of observers and the conditions. This is a demo-level check only.

## 5. Report

`python3 04-demo/trials2.py report` writes `04-demo/results/RESULTS-v2.md`. Commit `results/`.
