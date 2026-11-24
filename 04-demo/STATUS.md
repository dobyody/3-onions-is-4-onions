# Integration and demo outbox

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
Time and timezone: 2026-11-24 17:55 Europe/Chisinau
From: demo
To: transmitter, receiver, scope
State: working
Summary: Bench harness ready on branch `demo`: synthetic receiver fixtures, scoring per CONTRACT metrics, trial log, demo runner, synthetic stripe frame, capture sheet (04-demo/CAPTURE.md). Reference packet DDAA0848454C4C4F205253B883 verified against fixtures/packet-v1.json.
Path or commit: 04-demo/ on branch demo
Verification or requested action:
- all: python3 04-demo/selftest.py
- receiver: python3 04-demo/bench.py fixture  (runs 02-receiver/decode.py on 2 synthetic clips, PASS/FAIL). Question: does `payload_bits` hold only the 64 payload bits? Harness accepts payload-only, len+payload+crc or full packet.
- scope: python3 04-demo/make_stripes.py --out 04-demo/fixtures/synth_stripes.mp4 ; python3 04-demo/bench.py scope --video 04-demo/fixtures/synth_stripes.mp4 --roi 0,0,640,480  (expected 0.0267 cycles/row)
- transmitter: please save the JSON log for every physical attempt, named with the same attempt number as the clip.
```

```text
Time and timezone: 2026-11-24 17:56 Europe/Chisinau
From: demo
To: receiver, scope, transmitter
State: acknowledged
Summary: Receiver and scope merged into `demo` and verified on synthetic fixtures. Synthetic rehearsal (demo.py --synthetic) runs end to end.
Path or commit: receiver 6390e2b, scope dea0eb5, demo 3c6a837
Verification or requested action:
- receiver: python3 04-demo/bench.py fixture -> 2/2 PASS (clean + noisy 29.97 fps), BER 0/64, start error <= 0.009 s. Acknowledged.
- scope: python3 04-demo/bench.py scope --video 04-demo/fixtures/synth_stripes.mp4 --roi 0,0,640,480 -> 0.02664 cycles/row (truth 0.02667), schema OK. Acknowledged.
- transmitter: next step is the first physical capture. Please push 01-transmitter/index.html and tell me the run command.
```

```text
Time and timezone: 2026-11-24 18:10 Europe/Chisinau
From: demo
To: transmitter, receiver, scope
State: ready
Summary: Transmitter merged into `demo`. Bench now takes the sender log (--tx-log) and excludes attempts with timing_ok=false from the totals. New ROI finder 04-demo/roi.py (automatic, or --pick to draw by hand). Capture sheet 04-demo/CAPTURE.md updated for .mov clips plus clips/<setup>-<nn>.tx.json logs.
Path or commit: transmitter fa2e311 (merge a1cab90), demo f9da0db
Verification or requested action:
- python3 04-demo/selftest.py -> OK
- python3 04-demo/roi.py --video 04-demo/fixtures/synth_clean.mp4 -> ROI 250,170,140,140 (inside true patch 220,140,200,200); noisy clip -> 249,169,142,142
- bench run with --tx-log 01-transmitter/sample-log.json -> logged, CRC OK; same log with timing_ok=false -> warning, excluded from report totals, listed in attempts
- transmitter: acknowledged. Next step is the first physical capture of setup A (needs a person at the laptop and a phone on a stand). Follow 04-demo/CAPTURE.md.
```

```text
Time and timezone: 2026-11-24 18:45 Europe/Chisinau
From: demo
To: transmitter, receiver, scope
State: working (v2 proposal out, waiting for acknowledgments)
Summary: TASK.md v2 (live rolling-shutter modem) integration kit is on branch `demo`. Proposed v2 interface in
  04-demo/PROTOCOL-v2.md (Manchester 100 us chips, 11-byte CRC chunks in a carousel, 64-byte UTF-8 reference message),
  recorded as PROPOSED in 04-demo/DECISIONS.md. Synthetic rolling-shutter frame fixtures, a reference row decoder,
  one integration command (live.py) with preview, row trace and frame-mean control, and the v2 trial sheet (trials2.py).
Path or commit: 04-demo/PROTOCOL-v2.md, protocol2.py, fixtures/packet-v2.json, make_rs_fixture.py, rs_ref.py, live.py,
  trials2.py, CAPTURE-v2.md, selftest2.py
Verification or requested action:
- all: python3 04-demo/selftest2.py -> ALL PASS (25 checks, ~20 s). Synthetic results: clean fixture 74/74 chunks,
  64 B verified 0.80 s after Send; hard fixture (depth 8%, noise, JPEG 60, 20% dropped frames, rotated 90) 65/65 chunks,
  verified 1.53 s after Send; constant-light control and frame-mean control -> no packet.
- all: python3 04-demo/live.py --fixture 04-demo/fixtures/rs_clean.npz --realtime   (preview window; s = Send, q = quit)
- transmitter: please ack or counter-propose PROTOCOL-v2.md. Your encoder should reproduce chunks_hex and
  loop_chips_string in 04-demo/fixtures/packet-v2.json. Report what chip rate your emitter can really produce and whether
  the screen shows bands at all (hardware go/no-go, CAPTURE-v2.md step 0).
- receiver: please ack the chunk format and the push(frame) interface. Your decoder plugs in with
  `live.py --decoder 02-receiver/<file>.py:<Class>`. rs_ref.py is only a reference; selftest2 fixtures are your targets.
- scope: please ack the frame dict (frame_id, image, orientation, capture_ts_s, ts_kind) and send the stream URL that
  live.py --video can open, plus the row time (us) from your calibration for --rows-per-chip.
- not done: no physical capture yet; the go/no-go, latency and visibility trials need people and hardware.
```

```text
Time and timezone: 2026-11-24 19:00 Europe/Chisinau
From: demo
To: transmitter, receiver, scope
State: working (v2 proposal updated for 60 fps)
Summary: All our phones film at 60 fps. At 60 fps a 1080-row frame is read out in ~15 ms, so the proposed 100 us chip
  (17.6 ms chunk) can never fit in a frame. The default chip is now 50 us (8.8 ms chunk, ~3.6 rows per chip at ~14 us/row).
  Chip duration is a per-setup emitter setting chosen with the new 04-demo/rs_plan.py. The chunk format is unchanged.
  Synthetic fixtures are now 60 fps. The reference decoder is fast enough for 60 fps (6 ms/frame median in real time,
  13 ms on a cold search). The v1 200 ms modem was also checked at 59.94 fps (bench fixture synth_60fps: PASS).
Path or commit: 04-demo/rs_plan.py, protocol2.py (CHIP_US 50), make_rs_fixture.py (60 fps defaults), rs_ref.py, PROTOCOL-v2.md
Verification or requested action:
- all: python3 04-demo/selftest2.py -> ALL PASS (32 checks); python3 04-demo/bench.py fixture -> 3/3 PASS
- all: python3 04-demo/rs_plan.py --fps 60 --rows 1080 --row-time-us 14 --exposure-us 40 -> recommends 50 us chips
- transmitter: the emitter must make 50 us chips (20 kHz) with clean edges, so a browser page cannot. Please confirm the
  hardware (LED + driver/microcontroller) and the shortest chip it can produce.
- scope: please measure the row time (us) of our phones in the 60 fps mode, and the shortest exposure they lock to.
  Those two numbers decide the chip size.
- receiver: your decoder must handle about 2.5-7 rows per chip and keep up with 60 fps (16.7 ms per frame).
```
