# Modem interface v2 (PROPOSED by integration, awaiting transmitter and receiver acknowledgment)

This is the starting proposal for [TASK.md](../TASK.md). The v1 contract ([CONTRACT.md](../CONTRACT.md)) stays as-is for the
200 ms screen modem. Nothing here is final until the transmitter and receiver acknowledge it in their STATUS.md and it is
recorded in [DECISIONS.md](DECISIONS.md). Every number below can change; tell integration in your outbox.

Reference implementation: [protocol2.py](protocol2.py). Reference vector: [fixtures/packet-v2.json](fixtures/packet-v2.json).

## Optical symbols

| Item | Proposal | Why |
| --- | --- | --- |
| Line code | Manchester. Bit 1 = chips `1,0`, bit 0 = chips `0,1`. MSB first. | Mean light is the same for every bit, so there is no low-frequency flicker. The receiver needs no absolute level. |
| Chip levels | `1` = mean × (1 + depth), `0` = mean × (1 − depth). The gap between chunks holds the mean level. | Equal swing around the mean keeps the brightness constant before, during and after Send. |
| Chip duration | **Per setup**, chosen with `rs_plan.py`. Default **50 µs** for our **60 fps** phones (20 kHz chips). | At 60 fps the readout of a 1080-row frame is only ~15 ms (~14 µs per row). A 50 µs chip is ~3.6 rows and the 176-chip chunk is 8.8 ms, so about 0.7 complete chunks land in every frame. A 100 µs chip (17.6 ms chunk) **never fits** in a 60 fps frame. The decoder finds the chip size by itself, so only the emitter setting changes. |
| Exposure | Lock the shortest exposure the phone allows. It should be ≤ the chip duration (up to 1.5× still decodes). | A longer exposure averages neighbouring chips together. 50 µs is 1/20000 s: check during the go/no-go what the phone really reaches with the LED in view. |
| Depth | Start at 25 %, lower it until the visibility trials pass and the decoder still locks. | Trades visibility against bit errors. |
| Emitter | A fast light the team controls (LED and driver, or a microcontroller). | A browser page is tied to the 60 Hz refresh, so it cannot make 10 kHz chips. Use the screen only if the go/no-go shows usable bands. |

## Chunk and message

A message is any UTF-8 text, 1–1016 bytes (64 bytes for the demo). It is cut into 11-byte chunks. The emitter loops all chunks
(a carousel) with an 8-chip mean-level gap after each, from Send until the operator stops it. The receiver collects
CRC-valid chunks from any frames in any order. Duplicates are fine and lost frames only delay delivery.

| Bytes | Field |
| --- | --- |
| 2 | Sync `DD AA` |
| 1 | `msg_id` (packet ID; change it for every new message) |
| 1 | `index` (0 = descriptor, 1..count−1 = data) |
| 1 | `count` (number of chunks including the descriptor) |
| 4 | Data. Descriptor: message length (2 bytes, big-endian) + message CRC-16 (2 bytes). Data chunks: next 4 message bytes, the last one padded with `00`. |
| 2 | CRC-16/CCITT-FALSE (as in v1) over `msg_id` through data, high byte first |

The message is verified when every index has a CRC-valid chunk and the CRC-16 of the reassembled bytes matches the
descriptor. A 64-byte message is 17 chunks, and one carousel loop is 0.16 s at 50 µs chips.

## Video input (transport → receiver)

Each frame is passed as `{frame_id, image, orientation, capture_ts_s, ts_kind}`:
- `image` is BGR or gray pixels at the resolution that reaches the laptop.
- `orientation` is the clockwise rotation, in degrees, that makes sensor rows horizontal.
- `ts_kind` is `capture` when the phone gives a capture timestamp, `arrival` when the time is taken on the laptop.

Keep the queue bounded (drop the oldest frame) and report dropped frames. Keep full row resolution: do not downscale vertically.

## Decoder output

Use a stateful object with `push(frame)` that returns `{frame_id, chunks: [...], messages: [...], profile}`:
- Each chunk has `msg_id, index, count, data, crc_ok, row_start, rows_per_chip, frame_id`.
- Each message has `packet_id, payload, payload_bytes, crc_ok, chunks, duplicates, frame_ids, first_chunk_ts, verified_ts`.
- `profile` is the row-brightness trace of the frame, used in the preview.

[rs_ref.py](rs_ref.py) is a reference decoder with this interface, so integration can run end to end now. The receiver's
decoder plugs in with `live.py --decoder 02-receiver/<file>.py:<Class>` (constructor keywords `roi, rows_per_chip, frame_mean`).

## Acceptance controls built into the kit

- `make_rs_fixture.py --mode constant`: the light is held at one level, so there must be no packet.
- `live.py --frame-mean`: each frame is collapsed to its mean brightness, so there must be no packet. A verified packet
  therefore needs the row data.
