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
