# Capture procedure, trial sheet and fallback

Owner: Integration (04-demo). Large clips are NOT committed; store them in the team Drive folder and
record the link below. Only results/*.json, results/RESULTS.md and small fixtures go into Git.

## Setup record (fill one block per setup)

| Field | Setup A (baseline) | Setup B (harder) |
| --- | --- | --- |
| Phone model |  |  |
| Camera app and mode (resolution, fps, HDR off?) |  |  |
| Exposure / focus locked (AE/AF lock) |  |  |
| Orientation (portrait/landscape) |  |  |
| Distance phone → screen (cm) |  |  |
| Angle (straight / degrees) |  |  |
| Screen and brightness % |  |  |
| Room light |  |  |
| Browser + sender commit |  |  |
| Receiver commit |  |  |
| ROI x,y,w,h |  |  |

## Procedure for one attempt

1. Phone on a fixed stand, same position for all attempts of a setup. Lock exposure and focus on the patch.
2. Start recording. Wait ~2 s. Click **Send** on the laptop. Wait until idle (gray 128) for ≥1 s after the packet.
3. Stop recording when the sender says **Sent**. Click **Save log** (see 01-transmitter/CAPTURE.md).
4. Copy the clip to the laptop as `clips/<setup>-<nn>.mov` and the log as `clips/<setup>-<nn>.tx.json`.
   (`clips/` is outside 04-demo and clips are ignored by Git.)
5. Find the ROI once per setup (the phone does not move between attempts):
   ```
   python3 04-demo/roi.py --video clips/A-01.mov        # automatic; check clips/A-01.mov.roi.png
   python3 04-demo/roi.py --video clips/A-01.mov --pick # draw it by hand if automatic is wrong
   ```
6. Score it:
   ```
   python3 04-demo/bench.py run --video clips/A-01.mov --roi X,Y,W,H --setup "A" --attempt 1 \
       --tx-log clips/A-01.tx.json --notes "..."
   ```
   Attempts whose sender log has `timing_ok=false` are logged but excluded from the totals: repeat them.
7. After the series: `python3 04-demo/bench.py report` → `04-demo/results/RESULTS.md`.

Target: at least 8 CRC-valid packets out of 10 attempts in setup A. Report every attempt, including failures.

## Fallback for the live demo

| Item | Value |
| --- | --- |
| Fallback modem clip (Drive link) |  |
| Setup it was recorded in | A |
| Recorded on (date/time) |  |
| ROI |  |
| Decoded result (payload, CRC, BER) |  |
| Scope clip / frame used |  |
| Scope source: hardware or SYNTHETIC |  |
| Row-time calibration evidence (or "not calibrated") |  |

Run the fallback exactly as on stage:
```
python3 04-demo/demo.py --video clips/fallback.mp4 --roi X,Y,W,H --label "FALLBACK setup A <date>" \
    --scope-video clips/stripes.mp4 --scope-roi X,Y,W,H --frame N
```
If no real stripes: `python3 04-demo/demo.py --video clips/fallback.mp4 --roi X,Y,W,H --label "FALLBACK" --scope-video 04-demo/fixtures/synth_stripes.mp4 --scope-roi 0,0,640,480`
and say out loud that the scope panel is SYNTHETIC.

## One-minute demo script

| Time | Action | Say |
| --- | --- | --- |
| 0:00–0:10 | Phone records, click Send | "The screen sends HELLO RS at 5 bit/s with brightness" |
| 0:10–0:35 | Run demo.py on the clip | "Recovered text, CRC OK, BER and goodput" |
| 0:35–0:50 | Point at the scope panel | "Stripes = rows exposed at different times. Peak in cycles per row; Hz only with calibration" |
| 0:50–1:00 | Show RESULTS.md | "N/10 valid packets in setup A" |
