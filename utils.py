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
