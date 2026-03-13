import mmap
import struct
import sys

from datalog import DataLogReader
from writelog import patch_control_entry_id, write_record


def merge_logs(log1_path: str, log2_path: str, output_path: str) -> None:
    with open(log1_path, "rb") as f:
        buf1 = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    with open(log2_path, "rb") as f:
        buf2 = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)

    reader1 = DataLogReader(buf1)
    reader2 = DataLogReader(buf2)

    if not reader1:
        raise ValueError(f"Not a valid WPILOG file: {log1_path}")
    if not reader2:
        raise ValueError(f"Not a valid WPILOG file: {log2_path}")

    out = bytearray()

    out += b"WPILOG"
    out += struct.pack("<H", 0x0100)
    out += struct.pack("<I", 0)

    max_entry_id = 0
    last_timestamp = 0

    for record in reader1:
        write_record(out, record.entry, record.timestamp, bytes(record.data))
        if record.timestamp > last_timestamp:
            last_timestamp = record.timestamp
        if record.isStart():
            try:
                start = record.getStartData()
                if start.entry > max_entry_id:
                    max_entry_id = start.entry
            except TypeError:
                pass

    timestamp_offset = last_timestamp + 1000  # microseconds

    entry_id_map: dict[int, int] = {}
    next_entry_id = max_entry_id + 1

    for record in reader2:
        new_timestamp = record.timestamp + timestamp_offset

        if record.isStart():
            try:
                start = record.getStartData()
                entry_id_map[start.entry] = next_entry_id
                next_entry_id += 1
            except TypeError:
                pass

        if record.entry == 0:
            if len(record.data) >= 5:
                payload_entry_id = int.from_bytes(record.data[1:5], byteorder="little")
                remapped_id = entry_id_map.get(payload_entry_id, payload_entry_id)
                patched_data = patch_control_entry_id(bytes(record.data), remapped_id)
            else:
                patched_data = bytes(record.data)
            write_record(out, 0, new_timestamp, patched_data)
        else:
            new_entry_id = entry_id_map.get(record.entry, record.entry)
            write_record(out, new_entry_id, new_timestamp, bytes(record.data))

    with open(output_path, "wb") as f:
        f.write(out)

    print(f"Merged log written to {output_path}")
    print(f"  Log1: last timestamp {last_timestamp / 1_000_000:.3f}s")
    print(
        f"  Log2: offset by {timestamp_offset / 1_000_000:.3f}s, {len(entry_id_map)} entries remapped"
    )


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(
            "Usage: mergelogs.py <log1.wpilog> <log2.wpilog> <output.wpilog>",
            file=sys.stderr,
        )
        sys.exit(1)

    merge_logs(sys.argv[1], sys.argv[2], sys.argv[3])
