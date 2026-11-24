"""Scoring as defined in CONTRACT.md 'Metrics'."""
from protocol import payload_bits

RECEIVER_FIELDS = {
    "packet_found": (bool,),
    "crc_ok": (bool, type(None)),
    "payload_ascii": (str, type(None)),
    "payload_bits": (list,),
    "packet_start_s": (int, float, type(None)),
    "packet_end_s": (int, float, type(None)),
    "timebase": (str,),
}
SCOPE_FIELDS = {
    "frame_index": (int,),
    "analysis_axis": (str,),
    "profile": (list,),
    "peak_cycles_per_row": (int, float, type(None)),
    "row_time_s": (int, float, type(None)),
    "peak_hz": (int, float, type(None)),
}


def check_schema(data, fields):
    """Return a list of problems (empty list = OK)."""
    problems = []
    for name, types in fields.items():
        if name not in data:
            problems.append("missing field '%s'" % name)
        elif isinstance(data[name], bool) and bool not in types:
            problems.append("field '%s' is bool, expected %s" % (name, [t.__name__ for t in types]))
        elif not isinstance(data[name], types):
            problems.append("field '%s' has type %s, expected %s"
                            % (name, type(data[name]).__name__, [t.__name__ for t in types]))
    if not problems and fields is RECEIVER_FIELDS:
        if any(b not in (0, 1, None) or isinstance(b, float) for b in data["payload_bits"]):
            problems.append("payload_bits must contain only 0, 1 or null")
        if not data["packet_found"] and data["payload_bits"]:
            problems.append("packet_found is false but payload_bits is not empty")
    return problems


def extract_payload_bits(bits, n_payload_bits):
    """CONTRACT.md does not say whether payload_bits includes header/CRC.

    Accept payload-only, length+payload+CRC, or the full packet, and return the payload part.
    """
    n = len(bits)
    if n == n_payload_bits + 8 + 16:          # length + payload + crc
        return bits[8:8 + n_payload_bits], "length+payload+crc"
    if n == n_payload_bits + 16 + 8 + 16:     # full packet
        return bits[24:24 + n_payload_bits], "full packet"
    return bits, "payload only"


def score_attempt(decode, expected_payload):
    """Score one decode.json against the expected payload."""
    exp = payload_bits(expected_payload)
    got, layout = extract_payload_bits(decode.get("payload_bits") or [], len(exp))
    compared = unequal = erased = 0
    for i, e in enumerate(exp):
        if i >= len(got):
            break
        if got[i] is None:
            erased += 1
        else:
            compared += 1
            unequal += int(got[i] != e)
    missing = max(0, len(exp) - len(got))
    success = bool(decode.get("crc_ok")) and decode.get("payload_ascii") == expected_payload
    return {
        "synchronized": bool(decode.get("packet_found")),
        "success": success,
        "crc_ok": decode.get("crc_ok"),
        "payload_ascii": decode.get("payload_ascii"),
        "bits_layout": layout,
        "compared_bits": compared,
        "unequal_bits": unequal,
        "erased_bits": erased,
        "missing_bits": missing,
        "ber": (unequal / compared) if compared else None,
        "confirmed_payload_bits": len(exp) if success else 0,
    }


def aggregate(rows):
    """rows: list of dicts with score fields plus 'elapsed_s'."""
    n = len(rows)
    compared = sum(r["compared_bits"] for r in rows)
    unequal = sum(r["unequal_bits"] for r in rows)
    elapsed = sum(r["elapsed_s"] for r in rows)
    confirmed = sum(r["confirmed_payload_bits"] for r in rows)
    return {
        "attempts": n,
        "successes": sum(r["success"] for r in rows),
        "packet_success_rate": (sum(r["success"] for r in rows) / n) if n else None,
        "never_synchronized": sum(not r["synchronized"] for r in rows),
        "compared_bits": compared,
        "unequal_bits": unequal,
        "erased_bits": sum(r["erased_bits"] for r in rows),
        "missing_bits": sum(r["missing_bits"] for r in rows),
        "ber": (unequal / compared) if compared else None,
        "elapsed_s": elapsed,
        "confirmed_payload_bits": confirmed,
        "goodput_bps": (confirmed / elapsed) if elapsed else None,
    }
