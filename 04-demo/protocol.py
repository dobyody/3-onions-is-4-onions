"""Modem interface v1 helpers (see CONTRACT.md).

Packet = preamble DD AA | length (1..16) | payload ASCII | CRC-16/CCITT-FALSE (high byte first).
CRC covers the length byte and payload only. Bits are MSB first in every byte.
"""
import json
import os

PREAMBLE = bytes([0xDD, 0xAA])
SYMBOL_MS = 200
GRAY_IDLE, GRAY_ZERO, GRAY_ONE = 128, 64, 192
REFERENCE_PAYLOAD = "HELLO RS"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE_PATH = os.path.join(ROOT, "fixtures", "packet-v1.json")


def crc16_ccitt_false(data):
    """Poly 0x1021, init 0xFFFF, no reflection, xorout 0x0000."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return crc


def build_packet(payload_ascii):
    payload = payload_ascii.encode("ascii")
    if not 1 <= len(payload) <= 16:
        raise ValueError("payload length must be 1..16 bytes")
    if any(b < 0x20 or b > 0x7E for b in payload):
        raise ValueError("payload must be printable ASCII")
    body = bytes([len(payload)]) + payload
    crc = crc16_ccitt_false(body)
    return PREAMBLE + body + bytes([crc >> 8, crc & 0xFF])


def bytes_to_bits(data):
    return [(b >> (7 - i)) & 1 for b in data for i in range(8)]


def payload_bits(payload_ascii):
    return bytes_to_bits(payload_ascii.encode("ascii"))


def load_reference():
    """Read fixtures/packet-v1.json and return (payload_ascii, packet_hex or None).

    The fixture schema is not specified in CONTRACT.md, so a few likely key names are tried.
    """
    if not os.path.exists(FIXTURE_PATH):
        return REFERENCE_PAYLOAD, None
    with open(FIXTURE_PATH) as f:
        data = json.load(f)
    payload = data.get("payload_ascii") or data.get("payload") or REFERENCE_PAYLOAD
    packet_hex = data.get("packet_hex") or data.get("hex")
    if packet_hex:
        packet_hex = packet_hex.replace(" ", "").lower()
    return payload, packet_hex
