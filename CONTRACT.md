# Modem interface v1

## Packet and optical signal

| Field | Definition |
| --- | --- |
| Preamble | Two bytes, hex DDAA |
| Length | One byte, payload length 1 through 16 |
| Payload | Printable ASCII, use `HELLO RS` for the first demo |
| CRC | CRC-16/CCITT-FALSE over length byte and payload only. Poly 0x1021, init 0xFFFF, no reflection, xorout 0x0000. Append high byte first. |
| Bit order | Bytes in field order. Most significant bit first in every byte. |
| Symbol duration | 200 ms nominal |
| Screen signal | One visible rectangular patch at gray 128 while idle, gray 64 for 0 and gray 192 for 1. Hold idle for at least 1 second before and after each packet. Send one packet per click. |

Use a monotonic browser clock and log the expected packet and actual timing of visual updates. Repeated bits can hold the same brightness. For timestamps at the receiver, prefer decoded video presentation timestamps when available. Log an estimated frame-index/FPS time base if used as fallback. The receiver should work from a manually selected rectangular region before attempting automatic detection. Use steady samples near symbol centers after synchronizing to the preamble, retaining missing symbols as erasures. The reference packet is in [fixtures/packet-v1.json](fixtures/packet-v1.json).

## Run commands from the project root

These are implementation targets for the role agents. The sender is a local `01-transmitter/index.html` page, with a button to save a JSON log with `payload_ascii`, `packet_hex`, `symbol_ms` and `symbols`. Each symbol record includes `index`, `bit` and `applied_ms` relative to transmit start. Here applied time is a browser callback measurement, not a physical display timestamp.

```text
python 02-receiver/decode.py --video path/to/clip.mp4 --roi x,y,w,h --out path/to/decode.json
python 03-scope/analyze.py --video path/to/clip.mp4 --frame 0 --roi x,y,w,h --out path/to/scope.json
```

ROI units are integer pixels in the decoded image, measured from the upper left. Scope results must record the axis used for analysis if the video is rotated. A no-packet result for an otherwise processable clip must still write JSON. Input/usage errors may exit with an error.

| Output | Required JSON fields |
| --- | --- |
| Receiver | `packet_found` boolean, `crc_ok` boolean or null, `payload_ascii` string or null, `payload_bits` array of 0, 1 or null in transmission order, `packet_start_s` number or null, `packet_end_s` number or null, `timebase` string. Use an empty bits array for no packet. Retain pre-CRC bits from a candidate even if its CRC fails. |
| Scope | `frame_index`, `analysis_axis`, `profile` array, `peak_cycles_per_row` number or null, `row_time_s` number or null, `peak_hz` number or null. Accept optional `--row-time-s` for documented calibration. Store the profile/spectrum plot or a CSV alongside the report. |

## Metrics

- Packet success rate = CRC-valid packets with the expected payload / total attempts.
- Pre-CRC payload BER = unequal known bits / compared known bits. Align to the expected payload, count erased payload bits separately, and report attempts that never synchronized. Report BER as unavailable when no bits are comparable.
- Payload goodput = confirmed payload bits / elapsed test time, including idle and failed attempts. For the single packet demo, report the chosen timing window.
- Scope frequency = cycles per row / seconds per row. Calibrate row timing with a known optical reference and record camera mode, orientation and calibration evidence. Report the tested frequency range only as far as supported by known source frequencies. A peak from an unknown source gives a stripe period, and its frequency can still be ambiguous due to aliasing.
