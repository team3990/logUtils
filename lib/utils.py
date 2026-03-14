import re
from enum import Enum
from os import path


def _encode_varint(value: int, length: int) -> bytes:
    return value.to_bytes(length, byteorder="little")


def _varint_len(value: int) -> int:
    if value <= 0xFF:
        return 1
    elif value <= 0xFFFF:
        return 2
    elif value <= 0xFFFFFF:
        return 3
    else:
        return 4


def write_record(out: bytearray, entry: int, timestamp: int, data: bytes) -> None:
    entry_len = _varint_len(entry)
    size_len = _varint_len(len(data))
    ts_len = _varint_len(timestamp)

    header_byte = (
        ((entry_len - 1) & 0x3)
        | (((size_len - 1) & 0x3) << 2)
        | (((ts_len - 1) & 0x7) << 4)
    )

    out.append(header_byte)
    out += _encode_varint(entry, entry_len)
    out += _encode_varint(len(data), size_len)
    out += _encode_varint(timestamp, ts_len)
    out += data


def patch_control_entry_id(data: bytes, new_entry_id: int) -> bytes:
    if len(data) < 5:
        return data
    return bytes([data[0]]) + new_entry_id.to_bytes(4, byteorder="little") + data[5:]


def make_start_payload(entry_id: int, name: str, type_str: str, metadata: str = "") -> bytes:
    nb = name.encode("utf-8")
    tb = type_str.encode("utf-8")
    mb = metadata.encode("utf-8")
    payload = bytes([0]) + int(entry_id).to_bytes(4, byteorder="little")
    payload += len(nb).to_bytes(4, byteorder="little") + nb
    payload += len(tb).to_bytes(4, byteorder="little") + tb
    payload += len(mb).to_bytes(4, byteorder="little") + mb
    return payload


def write_new_record(out: bytearray, ts: int, entry_id: int, name: str, type_str: str, data_bytes: bytes) -> None:
    start_payload = make_start_payload(entry_id, name, type_str)
    write_record(out, 0, ts, start_payload)
    write_record(out, entry_id, ts, data_bytes)


def find_match_type(log_name: str) -> tuple[MatchType, int, bool] | None:
    # Examples
    # Not a match : FRC_20260308_003853.wpilog = None
    # Practice match number 14, not cropped : FRC_20260305_235541_BCVI_P14.wpilog = (PRACTICE, 14, false)
    # Qualif match number 67, cropped : FRC_20260307_184832_BCVI_Q67-cropped.wpilog = (QUALIFICATION, 67, true)
    # Playoff match number 13, not cropped : FRC_20260308_001853_BCVI_E13.wpilog = (PLAYOFF, 13, false)
    # Work with the base filename only
    base = path.basename(log_name)

    # Look for a match-type letter (P/Q/E) followed by a match number and
    # optional "-cropped" suffix before the extension. Examples we should
    # match: "..._P14.wpilog", "..._Q67-cropped.wpilog", "..._E13.wpilog".
    m = re.search(
        r"(?P<type>[PQE])(?P<number>\d+)(?P<cropped>-cropped)?(?:\.wpilog)$", base
    )

    if not m:
        return None

    t = m.group("type")
    num = int(m.group("number"))
    cropped = bool(m.group("cropped"))

    if t == MatchType.PRACTICE.value:
        mt = MatchType.PRACTICE
    elif t == MatchType.QUALIFICATION.value:
        mt = MatchType.QUALIFICATION
    elif t == MatchType.PLAYOFF.value:
        mt = MatchType.PLAYOFF
    else:
        return None

    return (mt, num, cropped)  # match type, match number, is cropped


class MatchType(Enum):
    PRACTICE = "P"
    QUALIFICATION = "Q"
    PLAYOFF = "E"
