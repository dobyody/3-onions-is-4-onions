# Rolling-shutter scope and screen-to-camera modem

**Build a camera that reads light in two ways.** First, use a laptop screen to send a short test message with a visible brightness patch, film it on a phone, and recover the message on a laptop. Then visualize brightness across the rows of a frame to show how a rolling-shutter camera can reveal faster light changes within one frame. Use your own screens, recordings, and test messages.

Rolling-shutter sensors expose different rows at different times. A changing light source can therefore produce stripes. The stripe period is directly measurable in rows. Converting it to Hz requires the row timing for that device and recording mode. See [TickRS, section 2](https://www.mdpi.com/2304-6732/12/7/720#sec2).

## Four people, four deliverables

| Person and agent | Folder | Owns | First independent check |
| --- | --- | --- | --- |
| 1 · Transmitter | [01-transmitter](01-transmitter/AGENTS.md) | Browser sender, packet encoder, transmit log | Encoder matches the reference packet |
| 2 · Receiver | [02-receiver](02-receiver/AGENTS.md) | OpenCV video decoder, synchronization, CRC and metrics | Synthetic time series decodes to the reference message |
| 3 · Scope | [03-scope](03-scope/AGENTS.md) | Row-profile extraction, spectrum, calibration and capture experiments | Synthetic stripes yield the expected period |
| 4 · Integration | [04-demo](04-demo/AGENTS.md) | Bench harness, sample recordings, results and live demo | A deterministic receiver fixture runs end to end |

### Demo order

1. **Send and decode.** Start a phone recording, then click Send on the laptop. Decode the clip and display the recovered text, CRC result and payload goodput.
2. **Show the scope.** Put a frame with visible bands next to its row-brightness curve and spectrum. Report the peak in cycles per row. Use Hz when the timing is calibrated for that same camera mode.
3. **Show reliability.** Aim for at least 8 CRC-valid packets across 10 attempts in one documented setup. Record packet success, pre-CRC bit error rate with its denominator, missing bits, and goodput. Repeat in one harder setup if time allows. These are targets to measure.

Use a laptop browser, a phone that can record video and a laptop with Python, NumPy and OpenCV. Start with ordinary video at a fixed camera angle. Record the camera mode, resolution and distance. Use a known recording from the same setup as the live demo fallback. If your screens produce no reliable stripes, demonstrate the scope on a clearly labeled synthetic frame and report the hardware outcome separately. The browser modem has a 5 bit/s line rate. A kHz scope claim needs measured response to a calibrated source in that range.

## Start the four agents

- Read [TEAM.md](TEAM.md) for the four-terminal setup, file ownership and handoffs.
- Read [CONTRACT.md](CONTRACT.md) for packet bytes, CLI interfaces and scoring.
- Keep the included [reference packet](fixtures/packet-v1.json) fixed for the first integration pass.
