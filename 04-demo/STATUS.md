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
