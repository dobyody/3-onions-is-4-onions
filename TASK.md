# Hackathon task: Live rolling-shutter optical modem

Build a modem that sends a test message from a team-owned display or dedicated light transmitter to a phone camera. The phone streams camera frames to a laptop, where the receiver extracts bits from brightness variations **within each frame** and displays the recovered message as soon as it has verified the checksum. The operator explicitly starts transmission, and the modulation should be imperceptible to observers under the documented demo conditions.

This brief defines the next version of the project. The existing 200 ms screen modem, video-file decoder and scope are useful for comparison and development.

## What counts as done

| Requirement | Acceptance test |
| --- | --- |
| Rolling-shutter decoding | Show a raw camera crop and its row-brightness trace. Recover multiple successive temporal symbols from different rows of a single captured frame. With symbols held constant in the fixture, there should be no packet to decode. As a control, collapse each frame to its mean brightness and rerun the same capture. A verified packet should require the row-level data. |
| Imperceptible modulation | With the scene, background brightness and observer position held fixed, use randomized modulating and steady-light trials. Start with 10 balanced, blinded trials per observer and publish the scores, number of observers and viewing conditions. Treat this as a demo-level check under those conditions. |
| Longer messages, higher speed | Send at least 64 UTF-8 bytes chosen at demo time, in at most 25 seconds from Send to checksum-verified delivery. Report payload goodput in bits/s including overhead and retries. Aim for at least 8 successful attempts out of 10 on the same hardware setup. |
| Live phone-to-laptop stream | Show a continuous camera preview on the laptop for at least 30 seconds and decode a live packet while the stream is running. Aim for capture-to-preview latency under 1 second at the 95th percentile, measured with a visible stopwatch over at least 20 observations. |
| Reproducible demo | Save the actual camera mode, effective stream FPS and resolution, emitter/display settings, throughput, packet success rate and video latency. Count unsuccessful trials. If the hardware misses a target, report the measured result and show the relevant failure mode. |

## Four parallel assignments

| Person and agent | Folder | Owns | First handoff |
| --- | --- | --- | --- |
| 1. Optical transmitter | `01-transmitter/` | Validate an optical emitter the team controls and send deliberately generated test payloads. Measure what the actual display or light source can produce. Implement payload framing after agreeing on the symbol format. | Camera sample showing known successive symbols within a frame, plus emission settings and the expected symbol sequence. |
| 2. Rolling-shutter receiver | `02-receiver/` | Convert the selected region into a row-time signal, find symbol boundaries and synchronization, and reassemble verified packets across frames. Handle orientation, frame gaps, duplicate data and lost lock. | Synthetic frame decoding test plus a reusable decoder that accepts individual frames. |
| 3. Live camera transport | `03-scope/` | Deliver live phone frames to the laptop and expose the camera crop and row profile. Measure preview latency and test whether the chosen stream settings preserve the bands. | Open the laptop preview, point the phone at the agreed source and show a live row trace with frame IDs. |
| 4. Integration and verification | `04-demo/` | Agree on interfaces, integrate the live path, prepare reference fixtures and benchmark the hardware. Own the latency, goodput and visibility trials and the final demo. | One integration command and a trial sheet, with an explicit record of the source and capture mode tested. |

## Shared interface and first checkpoint

- **Optical symbols.** Transmitter and receiver agree on the preamble, symbol representation, nominal timing, payload layout, sequence numbers and checksum before building around physical recordings. The demo owner publishes the reference packet and synthetic frame fixture.
- **Video input.** The live path hands the receiver a frame ID, image pixels, orientation and capture timestamp when available. If the only timestamp is arrival time, label it accordingly. Keep the queue bounded and expose dropped frames. Preserve enough resolution for the receiver to sample individual rows. When using browser camera capture, provide a trusted HTTPS origin for the phone.
- **Decoder output.** Include packet ID, recovered payload, checksum status, and relevant frame IDs. Provide enough diagnostic data to show how the receiver read symbols from rows of a real frame.
- **Hardware go/no-go.** In the first 15–20 minutes, try the intended display and phone mode and inspect a raw crop. Mark the hardware path verified only when controlled optical symbols are distinguishable within individual frames. A browser display update is ordinarily tied to the display refresh rate. If the team's display cannot produce a usable signal, a team-controlled fast light source is an alternative if available and allowed by the hackathon. Otherwise document the hardware limit and show the live transport and synthetic row decoder as separately verified components.
- **Handoffs.** Each agent keeps its role folder and writes progress, questions, fixtures and run commands to its own `STATUS.md`. The integration owner records agreed protocol changes in `04-demo/DECISIONS.md`.

## Demo sequence

1. Open the laptop preview and point the phone at the transmitter.
2. Send a fresh test message and show the camera crop and row-brightness trace during live reception.
3. Reveal the recovered message, checksum, delivery time and measured goodput.
4. Show the frame-mean control and summarize the reliability and observer trials.

References: [Rolling-shutter exposure and optical sampling](https://www.mdpi.com/2304-6732/12/7/720#sec2), [browser repaint timing](https://developer.mozilla.org/en-US/docs/Web/API/Window/requestAnimationFrame), [browser camera access](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia).
