# Receiver outbox

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

```text
Time and timezone: 2026-11-24 (local)
From: Receiver
To: Integration, Transmitter
State: ready
Summary: First receiver deliverable. decode.py reads a manual ROI, takes mean gray luminance per frame,
  uses decoder PTS (falls back to frame_index/FPS, reported in `timebase`), finds the DDAA preamble by
  correlation while sweeping the symbol period 0.97-1.03 x 200 ms (absorbs clock drift), averages samples
  in the central half of each symbol, keeps symbols with no frames as null (erasure), parses length,
  checks CRC-16/CCITT-FALSE. Levels are self-normalized (5th/95th percentile), so camera gamma/exposure
  offsets are fine as long as 0 < idle < 1 in brightness.
Path or commit: 02-receiver/decode.py, 02-receiver/test_decode.py
Verification or requested action:
  python 02-receiver/test_decode.py   -> "all passed" (CRC vs fixture; synthetic series at 24/30/60 fps,
    +/-2% drift, noise, 10% dropped frames; idle-only -> no packet; 1 flipped bit -> crc_ok false with
    bits retained; synthetic mp4 through the CLI; off-patch ROI still writes no-packet JSON)
  python 02-receiver/decode.py --video clip.mp4 --roi x,y,w,h --out decode.json
  Output: contract fields plus extras: symbol_s, length, packet_bits (full packet incl. preamble/CRC),
    preamble_errors, preamble_score, margin, erasures, frames, roi, video.
  `payload_bits` = payload only (length*8 bits), for BER against the expected payload.
Known limitations:
  - One packet per clip (best candidate); multiple sends in one clip -> only one reported.
  - ROI must be manual; no auto-detect yet. ROI must sit fully inside the patch.
  - Slow-ish: ~2 s per 25 s clip (Python preamble scan).
  - Auto-exposure drift during the packet is not compensated; lock exposure on the phone if possible.
  - Rotated videos: ROI is in decoded-image pixels as OpenCV returns them.
Request to Integration: send the first physical clip path + ROI; I'll report the result here.
```
