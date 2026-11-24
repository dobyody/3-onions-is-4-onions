# Transmitter outbox

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
Time and timezone: 2026-11-24 15:45 UTC
From: Transmitter
To: Receiver, Integration
State: ready
Summary: The sender page and encoder are done. The encoder reproduces fixtures/packet-v1.json exactly (packet DDAA0848454C4C4F205253B883, CRC B883, 104 bits MSB-first). The page is a single self-contained file with no external dependencies.
Path or commit: 01-transmitter/index.html, 01-transmitter/test_encoder.mjs, 01-transmitter/CAPTURE.md, 01-transmitter/sample-log.json
Verification or requested action:
  - Verify:  node 01-transmitter/test_encoder.mjs   -> ALL PASS (tests the encoder block embedded in index.html)
  - Launch:  open 01-transmitter/index.html (Chrome/Edge). Self-test badge = PASS. Send / Space key -> 1 s idle 128, 104 x 200 ms symbols (64 = 0, 192 = 1), 1 s idle 128. Save log -> tx-log-<time>.json
  - Log: has the contract fields payload_ascii, packet_hex, symbol_ms and symbols[{index, bit, applied_ms}]. Extra fields are additive: scheduled_ms, bits, crc_hex, gray, pre/post_idle_ms, packet_start/end_ms, frame_interval_ms_median, late/skipped symbols, stall_frames, timing_ok, patch_px.
    applied_ms is ms from the Send click (so the first symbol is about 1000), measured by requestAnimationFrame, not photons.
  - Discard any attempt whose log has timing_ok=false. A hidden or throttled browser window drops symbols, and the page flags this.
  - Receiver: please synchronize on the preamble in the video. The log and video share no clock. sample-log.json is from a simulated 60 Hz frame clock, and real logs have the same layout.
  - Integration: CAPTURE.md lists the per-attempt fields to record for the trial sheet.
  - Not yet done: a real on-screen timing run and a phone capture (needs a human at the laptop).
```
