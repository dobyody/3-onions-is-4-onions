# Capture procedure (one packet)

**Laptop (sender)**
1. Set screen brightness to maximum. Turn off auto-brightness, Night Shift / Night Light and True Tone, and don't let the laptop run on battery saver.
2. Open `01-transmitter/index.html` in Chrome or Edge (double-click it, or `open 01-transmitter/index.html` on macOS). The **Self-test** badge must say PASS.
3. Leave the payload as `HELLO RS` for the first pass. Pick a patch size, then click **Fullscreen**. In fullscreen, **Space** sends and **Esc** exits.
4. Keep this window in front for the whole send. Hiding the tab aborts the send. A stall shows **TIMING DEGRADED**, and the run should then be repeated.

**Phone (camera)**
5. Mount the phone so it can't move, filling most of the frame with the patch. Write down the distance and angle.
6. Use ordinary video at 30 or 60 fps (no slow-motion, HDR or cinematic mode). Tap and hold on the patch to lock exposure and focus (AE/AF lock). The idle gray should not clip.
7. Note the camera app, mode, resolution and fps.

**Send**
8. Start recording and wait about 2 s.
9. Press Space (or click Send). The patch stays gray (128) for 1 s, flickers for 20.8 s, then holds gray for 1 s. The total is about 22.8 s.
10. Wait until the status says **Sent**, then stop recording.
11. Click **Save log** (you may need to exit fullscreen first). This downloads `tx-log-<time>.json`.
12. Rename the clip to match the log, e.g. `2026-11-24T15-40-51Z_hello.mp4` beside `tx-log-2026-11-24T15-40-51-276Z.json`. Don't commit clips to Git (see `.gitignore`). Share them through the team location.

**Record per attempt:** clip name, log name, phone model, camera mode/res/fps, distance, angle, room lighting, and the `timing_ok` value from the log.

**Notes for Receiver**
- `applied_ms` is the browser `requestAnimationFrame` time relative to the Send click. It is not the time light left the screen. Expect the display to lag it by one to a few frames.
- The video and the log have no shared clock. Synchronize on the preamble (`DDAA`) in the video, not on the log timestamps.
- Gray levels are sRGB values 64, 128 and 192. The camera's response is nonlinear, so threshold relative to the measured idle level.
