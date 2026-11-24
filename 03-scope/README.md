# Rolling-shutter scope

Run from the project root. Install OpenCV to read phone videos.

```powershell
python -m pip install opencv-python
python 03-scope/analyze.py --video path/to/clip.mp4 --frame 0 --roi 40,80,320,480 --out "$env:TEMP/onions-scope-capture/scope.json"
```

Select a crop containing visible bands and as little surrounding texture as possible. Use `--axis columns` for vertical bands when the decoded image is rotated relative to the sensor. The ROI uses coordinates in the decoded frame, and the frame index starts at zero.

The command writes the report to the requested JSON path and saves `scope-profile.csv`, `scope-spectrum.csv`, and `scope-plots.svg` beside it. The spectrum uses a linearly detrended, Hann-windowed brightness profile. The reported peak is the dominant spatial component in the ROI, which can come from scene texture, a harmonic, or aliasing. A constant or straight-line brightness profile yields a null peak.

## Calibration

Use a reference light with an independently known modulation frequency and a confidently identified, unaliased fundamental. Divide the measured cycles per row by the reference frequency in Hz to estimate seconds per row. Record the reference and how its frequency was established, the original video and ROI, camera and mode, decoded resolution, orientation, distance, and exposure settings if available. Apply `--row-time-s` to captures taken with the same camera mode and image sampling. The report keeps `peak_hz` null until a row-time value and a spectral peak are both available.

## Reproduce the synthetic handoff

```powershell
python 03-scope/verify.py --out-dir "$env:TEMP/onions-scope-verified"
```

This uses only the Python standard library. It writes the source frame `synthetic-stripes.pgm`, the spectrum and profile plot `synthetic-scope-plots.svg`, and the associated JSON and CSV files. The sample has a 16-row stripe period, with an expected peak of 0.0625 cycles per row. The verification also checks vertical bands with a noninteger period, the calibrated conversion arithmetic, and a flat frame.

After installing OpenCV, add `--video-check` to exercise the video CLI on a generated two-frame AVI. Use a physical clip with documented capture settings to assess the camera and calibration.
