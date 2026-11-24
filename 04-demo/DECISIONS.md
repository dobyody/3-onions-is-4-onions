# Integration decisions

Use the initial v1 contract as the baseline. For each agreed change record the revision, time, affected roles, their acknowledgments and the effective interface. Link to a fixture when relevant.

## v2: live rolling-shutter modem (TASK.md)

| Field | Value |
| --- | --- |
| Revision | v2, **proposed**, not yet effective |
| Time | 2026-11-24 18:45 Europe/Chisinau |
| Proposed by | integration (demo) |
| Affected roles | transmitter (emitter, chip format), receiver (row decoder, reassembly), scope (live transport, row time) |
| Interface | [PROTOCOL-v2.md](PROTOCOL-v2.md): Manchester chips (duration per setup from `rs_plan.py`, default 50 µs for our 60 fps phones), 11-byte chunks `DD AA, msg_id, index, count, data[4], CRC-16`, descriptor chunk with length and message CRC-16, carousel with an 8-chip gap; frame dict for transport; `push(frame)` decoder interface |
| Fixture | [fixtures/packet-v2.json](fixtures/packet-v2.json) (64-byte UTF-8 reference message, chunks, one carousel loop as chips); synthetic frames from `make_rs_fixture.py` |
| Acknowledgments | transmitter: pending · receiver: pending · scope: pending |

Update 2026-11-24 19:00: default chip changed from 100 µs to 50 µs because the team films at 60 fps. A 100 µs chunk (17.6 ms) does not fit in a 60 fps readout (~15 ms).

The v1 contract stays effective for the 200 ms screen modem, which is kept for comparison.
