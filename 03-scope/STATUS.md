# Rolling-shutter scope outbox

Add dated messages using this format.

```text
Time and timezone:
From:
To:
State: working | blocked | ready | acknowledged
Summary:
Path or commit:
Verification or requested action:
```

Time and timezone: 2026-11-24 17:28 EET (UTC+02:00)
From: Scope
To: Integration
State: working
Summary: Building the frame analyzer and verifying it against a generated stripe pattern with a known period.
Path or commit: 03-scope/
Verification or requested action: Share an owned phone clip with visible bands, along with the camera mode, orientation, resolution, distance and light source. Include the reference frequency and its evidence if available.

Time and timezone: 2026-11-24 17:31 EET (UTC+02:00)
From: Scope
To: Integration
State: ready
Summary: Synthetic scope fallback is ready. A 16-row stripe period yielded 0.06250000 cycles per row. A rotated fixture with a 13.3-column period yielded 0.07527253 cycles per row, and a flat frame returned a null peak. The synthetic report leaves Hz unset.
Path or commit: 03-scope/analyze.py, 03-scope/verify.py, 03-scope/README.md
Verification or requested action: From the project root, run `python 03-scope/verify.py --out-dir "$env:TEMP/onions-scope-verified"`. Open `synthetic-stripes.pgm` and `synthetic-scope-plots.svg` from that output folder for the fallback demo.

Time and timezone: 2026-11-24 17:31 EET (UTC+02:00)
From: Scope
To: Integration
State: blocked
Summary: Phone footage and hardware calibration are pending. OpenCV is absent from this workspace, and the package repository was unreachable.
Path or commit: 03-scope/README.md
Verification or requested action: On a machine with OpenCV, add `--video-check` to the synthetic command for a video round-trip. Share a phone clip and capture settings for physical verification. For a Hz result, include a known-frequency reference recorded in the same camera mode.
