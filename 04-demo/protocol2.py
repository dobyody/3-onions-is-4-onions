"""Modem interface v2 (PROPOSED, see 04-demo/PROTOCOL-v2.md): rolling-shutter chunks.

A message (UTF-8 bytes) is cut into short chunks. Every chunk is small enough to fit inside one
camera frame's readout, so a single frame can carry a complete, CRC-checked chunk. The emitter
repeats all chunks in a loop (carousel) until the operator stops it; the receiver collects chunks
from any frames until it has them all, then checks the whole-message CRC.

Chunk (11 bytes = 88 bits = 176 chips):
    sync DD AA | msg_id | index | count | data[4] | CRC-16/CCITT-FALSE over msg_id..data (high byte first)
    index 0 = descriptor: data = message length (2 bytes, big endian) + message CRC-16 (2 bytes)
    index 1..count-1 = message bytes, 4 per chunk, last one padded with 0x00
Line code: Manchester, bit 1 -> chips (1, 0), bit 0 -> chips (0, 1), MSB first.
Chip level 1 = brighter than the mean, 0 = darker, by the same amount, so the mean light stays
constant (no visible flicker). Between chunks the emitter holds the mean level for GAP_CHIPS chips.
"""
import json
import os

SYNC = bytes([0xDD, 0xAA])
CHIP_US = 50             # default chip for 60 fps phones (20 kHz chips); per setup, see rs_plan.py
GAP_CHIPS = 8            # mean-level gap between chunks
DATA_PER_CHUNK = 4
CHUNK_BYTES = 2 + 3 + DATA_PER_CHUNK + 2
CHUNK_BITS = CHUNK_BYTES * 8
CHUNK_CHIPS = CHUNK_BITS * 2
MAX_MESSAGE_BYTES = 254 * DATA_PER_CHUNK

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE_V2 = os.path.join(HERE, "fixtures", "packet-v2.json")
# 64 UTF-8 bytes, with non-ASCII letters on purpose (s-comma, a-breve take 2 bytes each).
REFERENCE_MESSAGE = "Salut din Chișinău! Rolling-shutter modem v2, test 0123456789A"


def crc16_ccitt_false(data):
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return crc


def bytes_to_bits(data):
    return [(b >> (7 - i)) & 1 for b in data for i in range(8)]


def bits_to_bytes(bits):
    return bytes(int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits) - len(bits) % 8, 8))


def manchester(bits):
    out = []
    for b in bits:
        out += (1, 0) if b else (0, 1)
    return out


SYNC_CHIPS = manchester(bytes_to_bits(SYNC))


def make_chunk(msg_id, index, count, data):
    if len(data) != DATA_PER_CHUNK:
        raise ValueError("chunk data must be %d bytes" % DATA_PER_CHUNK)
    body = bytes([msg_id & 0xFF, index, count]) + bytes(data)
    crc = crc16_ccitt_false(body)
    return SYNC + body + bytes([crc >> 8, crc & 0xFF])


def build_chunks(message, msg_id=1):
    """message: str (UTF-8) or bytes -> list of 11-byte chunks, descriptor first."""
    data = message.encode("utf-8") if isinstance(message, str) else bytes(message)
    if not 1 <= len(data) <= MAX_MESSAGE_BYTES:
        raise ValueError("message must be 1..%d bytes" % MAX_MESSAGE_BYTES)
    n_data = -(-len(data) // DATA_PER_CHUNK)
    count = n_data + 1
    mcrc = crc16_ccitt_false(data)
    chunks = [make_chunk(msg_id, 0, count, bytes([len(data) >> 8, len(data) & 0xFF, mcrc >> 8, mcrc & 0xFF]))]
    padded = data + bytes(n_data * DATA_PER_CHUNK - len(data))
    for i in range(n_data):
        chunks.append(make_chunk(msg_id, i + 1, count, padded[i * 4:i * 4 + 4]))
    return chunks


def gap_chips(i):
    """Mean-level gap after chunk i."""
    return GAP_CHIPS


def carousel_chips(chunks):
    """One loop of the emitter: chips per chunk followed by a mean-level gap (None = mean level)."""
    out = []
    for i, c in enumerate(chunks):
        out += manchester(bytes_to_bits(c))
        out += [None] * gap_chips(i)
    return out


def parse_chunk(raw):
    """11 bytes -> dict, or None when the sync is wrong. crc_ok tells whether it can be trusted."""
    raw = bytes(raw)
    if len(raw) != CHUNK_BYTES or raw[:2] != SYNC:
        return None
    body, crc = raw[2:9], raw[9] << 8 | raw[10]
    return {"msg_id": body[0], "index": body[1], "count": body[2], "data": body[3:7].hex(),
            "crc_ok": crc16_ccitt_false(body) == crc}


class Reassembler:
    """Collect CRC-valid chunks (from any frames) and emit each message once it verifies."""

    def __init__(self):
        self.msgs = {}

    def add(self, chunk, frame_id, ts=None):
        if not chunk.get("crc_ok"):
            return None
        if not 0 <= chunk["index"] < chunk["count"]:
            return None
        key = (chunk["msg_id"], chunk["count"])
        m = self.msgs.setdefault(key, {"chunks": {}, "frames": set(), "first_ts": ts, "dup": 0, "done": False})
        if chunk["index"] in m["chunks"]:
            m["dup"] += 1
        m["chunks"][chunk["index"]] = bytes.fromhex(chunk["data"])
        m["frames"].add(frame_id)
        if m["done"] or len(m["chunks"]) < chunk["count"]:
            return None
        desc = m["chunks"][0]
        length, mcrc = desc[0] << 8 | desc[1], desc[2] << 8 | desc[3]
        data = b"".join(m["chunks"][i] for i in range(1, chunk["count"]))[:length]
        ok = len(data) == length and crc16_ccitt_false(data) == mcrc
        m["done"] = ok
        return {"packet_id": chunk["msg_id"], "payload": data.decode("utf-8", errors="replace"),
                "payload_bytes": length, "crc_ok": ok, "chunks": chunk["count"], "duplicates": m["dup"],
                "frame_ids": sorted(m["frames"]), "first_chunk_ts": m["first_ts"], "verified_ts": ts}

    def progress(self):
        return {"%d/%d" % k: len(v["chunks"]) for k, v in self.msgs.items()}


def reference_json(message=REFERENCE_MESSAGE, msg_id=1):
    chunks = build_chunks(message, msg_id)
    loop = carousel_chips(chunks)
    return {
        "protocol": "v2-proposed", "message_utf8": message, "message_bytes": len(message.encode("utf-8")),
        "message_hex": message.encode("utf-8").hex(), "msg_id": msg_id, "chunk_count": len(chunks),
        "message_crc16": "%04x" % crc16_ccitt_false(message.encode("utf-8")),
        "chunks_hex": [c.hex() for c in chunks], "chip_us": CHIP_US, "gap_chips": GAP_CHIPS,
        "chips_per_chunk": CHUNK_CHIPS, "loop_chips": len(loop),
        "loop_ms": len(loop) * CHIP_US / 1000.0,
        "loop_chips_string": "".join("-" if c is None else str(c) for c in loop),
        "line_code": "Manchester: bit 1 -> chips 1,0; bit 0 -> chips 0,1; '-' = mean level",
    }


def write_reference(path=FIXTURE_V2):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(reference_json(), f, indent=2, ensure_ascii=False)
        f.write("\n")
    return path


if __name__ == "__main__":
    print("wrote", write_reference())
