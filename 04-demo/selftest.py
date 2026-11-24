"""Self-test for the harness itself (no receiver needed): python 04-demo/selftest.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from metrics import RECEIVER_FIELDS, aggregate, check_schema, score_attempt  # noqa: E402
from protocol import build_packet, bytes_to_bits, crc16_ccitt_false, load_reference, payload_bits  # noqa: E402

assert crc16_ccitt_false(b"123456789") == 0x29B1, "CRC-16/CCITT-FALSE check value"
payload, ref_hex = load_reference()
pkt = build_packet(payload)
assert pkt[:2] == b"\xdd\xaa" and pkt[2] == len(payload)
if ref_hex:
    assert pkt.hex() == ref_hex, "packet differs from fixtures/packet-v1.json: %s vs %s" % (pkt.hex(), ref_hex)

exp = payload_bits(payload)
perfect = {"packet_found": True, "crc_ok": True, "payload_ascii": payload, "payload_bits": exp,
           "packet_start_s": 1.5, "packet_end_s": 22.3, "timebase": "pts"}
assert check_schema(perfect, RECEIVER_FIELDS) == []
s = score_attempt(perfect, payload)
assert s["success"] and s["ber"] == 0 and s["compared_bits"] == len(exp)

# full-packet bits layout is recognised
s = score_attempt(dict(perfect, payload_bits=bytes_to_bits(pkt)), payload)
assert s["bits_layout"] == "full packet" and s["ber"] == 0

# one flipped bit, two erasures, failed CRC
bad = list(exp); bad[3] ^= 1; bad[10] = None; bad[11] = None
s = score_attempt(dict(perfect, payload_bits=bad, crc_ok=False, payload_ascii=None), payload)
assert not s["success"] and s["unequal_bits"] == 1 and s["erased_bits"] == 2 and s["compared_bits"] == len(exp) - 2

# no packet: bits empty, BER unavailable
none = {"packet_found": False, "crc_ok": None, "payload_ascii": None, "payload_bits": [],
        "packet_start_s": None, "packet_end_s": None, "timebase": "frame_index/fps"}
assert check_schema(none, RECEIVER_FIELDS) == []
s0 = score_attempt(none, payload)
assert s0["ber"] is None and s0["missing_bits"] == len(exp) and not s0["synchronized"]

assert check_schema({"packet_found": "yes"}, RECEIVER_FIELDS)  # problems reported

g = aggregate([dict(score_attempt(perfect, payload), elapsed_s=25.0), dict(s0, elapsed_s=25.0)])
assert g["packet_success_rate"] == 0.5 and g["never_synchronized"] == 1
assert abs(g["goodput_bps"] - len(exp) / 50.0) < 1e-9
print("selftest OK  packet=%s  goodput example=%.2f bit/s" % (pkt.hex(), g["goodput_bps"]))
