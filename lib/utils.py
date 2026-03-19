import glob as stdglob
from enum import Enum
from os import path
from re import search


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


def _make_start_payload(
    entry_id: int, name: str, type_str: str, metadata: str = ""
) -> bytes:
    nb = name.encode("utf-8")
    tb = type_str.encode("utf-8")
    mb = metadata.encode("utf-8")
    payload = bytes([0]) + int(entry_id).to_bytes(4, byteorder="little")
    payload += len(nb).to_bytes(4, byteorder="little") + nb
    payload += len(tb).to_bytes(4, byteorder="little") + tb
    payload += len(mb).to_bytes(4, byteorder="little") + mb
    return payload


def write_new_record(
    out: bytearray, ts: int, entry_id: int, name: str, type_str: str, data_bytes: bytes
) -> None:
    start_payload = _make_start_payload(entry_id, name, type_str)
    write_record(out, 0, ts, start_payload)
    write_record(out, entry_id, ts, data_bytes)


def glob(globPattern: str) -> list[str]:
    # Support simple keywords for match types and optional negation prefixes
    # Examples:
    #  - "practice" or "p" -> return all files that look like practice matches
    #  - "-practice" or "!p" -> return all files that are not practice (quals and elims)
    low = globPattern.strip().lower().removesuffix("s")
    neg = False
    if low and low[0] in ("-", "!"):
        neg = True
        low = low[1:]

    practice = {"p", "practice", "practise", "pratique"}
    qual = {"q", "qual", "qualif", "qualification"}
    elim = {"e", "elim", "elimination", "playoff"}

    # If the user asked for a specific match-type (or its negation), expand
    # to simple filename globs that look for _P / _Q / _E in the filename.
    if low in practice or low in qual or low in elim:
        wanted = []
        if low in practice:
            wanted.append("P")
        if low in qual:
            wanted.append("Q")
        if low in elim:
            wanted.append("E")

        if neg:
            include = [t for t in ("P", "Q", "E") if t not in wanted]
        else:
            include = wanted

        results = []
        for t in include:
            results.extend(stdglob.glob(f"*_{t}*.wpilog"))

        return sorted(set(results))

    return stdglob.glob(globPattern)
