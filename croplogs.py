import mmap
import os
import struct
import sys
from typing import Optional

from datalog import DataLogReader
from writelog import write_record

RSL_STATE_ID = "/Robot/SystemStats/RSLState"


def _find_rsl_true_timestamp(buf: bytes) -> Optional[int]:
    reader = DataLogReader(buf)
    if not reader:
        return None
    entries = {}
    for rec in reader:
        if rec.isStart():
            try:
                start = rec.getStartData()
                entries[start.entry] = start
            except TypeError:
                continue
        elif rec.isFinish():
            try:
                entries.pop(rec.getFinishEntry(), None)
            except TypeError:
                continue
        elif rec.isSetMetadata():
            try:
                md = rec.getSetMetadataData()
                if md.entry in entries:
                    entries[md.entry].metadata = md.metadata
            except TypeError:
                continue
        else:
            entry = entries.get(rec.entry)
            if not entry:
                continue
            if entry.name == RSL_STATE_ID:
                try:
                    # Return the first time the boolean becomes False
                    if entry.type == "boolean" and not rec.getBoolean():
                        return rec.timestamp
                except TypeError:
                    continue
    return None


def crop_to_timestamp(buf: bytes, crop_ts: int) -> Optional[bytes]:
    """Return cropped log bytes or None if input invalid."""
    reader = DataLogReader(buf)
    if not reader:
        return None

    # First pass: collect start/setMetadata/finish info that occurred before crop_ts
    start_payloads: dict[int, bytes] = {}
    start_timestamps: dict[int, int] = {}
    latest_setmd: dict[int, bytes] = {}
    finished_before = set()

    for rec in reader:
        if rec.timestamp >= crop_ts:
            continue
        if rec.isStart():
            try:
                start_payloads[rec.getStartData().entry] = bytes(rec.data)
                start_timestamps[rec.getStartData().entry] = rec.timestamp
            except TypeError:
                continue
        elif rec.isFinish():
            try:
                finished_before.add(rec.getFinishEntry())
            except TypeError:
                continue
        elif rec.isSetMetadata():
            try:
                md = rec.getSetMetadataData()
                latest_setmd[md.entry] = bytes(rec.data)
            except TypeError:
                continue

    # active entries: started before crop and not finished before crop
    active_entries = [
        eid for eid in start_payloads.keys() if eid not in finished_before
    ]

    # Build output: copy header (version and extra header) from input
    out = bytearray()
    out += b"WPILOG"
    out += struct.pack("<H", reader.getVersion())
    extra = reader.getExtraHeader().encode("utf-8")
    out += struct.pack("<I", len(extra))
    out += extra

    # Emit start records for active entries (timestamp set to crop_ts)
    for eid in active_entries:
        payload = start_payloads[eid]
        write_record(out, 0, crop_ts, payload)
        # If there was a setMetadata before crop_ts for this entry, emit it (so metadata matches)
        if eid in latest_setmd:
            write_record(out, 0, crop_ts, latest_setmd[eid])

    # Second pass: write every record with timestamp >= crop_ts preserving original payloads
    reader2 = DataLogReader(buf)
    for rec in reader2:
        if rec.timestamp < crop_ts:
            continue
        write_record(out, rec.entry, rec.timestamp, bytes(rec.data))

    return bytes(out)


def process_path(path: str) -> None:
    with open(path, "rb") as f:
        buf = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)

    found = _find_rsl_true_timestamp(buf)
    if found is None:
        print(f"No RSL false found in {path}", file=sys.stderr)
        return

    # determine earliest timestamp in the file (used to clamp the crop)
    min_ts = 0
    rdr = DataLogReader(buf)
    if rdr:
        for rec in rdr:
            min_ts = rec.timestamp
            break

    # leave 5 seconds before the first false
    five_sec = 5000000
    crop_ts = found - five_sec
    if crop_ts < min_ts:
        crop_ts = min_ts
    out_bytes = crop_to_timestamp(buf, crop_ts)
    if out_bytes is None:
        print(f"Not a valid log: {path}", file=sys.stderr)
        return

    base, ext = os.path.splitext(path)
    out_path = f"{base}-cropped{ext}"
    with open(out_path, "wb") as f:
        f.write(out_bytes)


def _usage_and_exit():
    print("Usage: croplogs.py <file1> [file2 ...]", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        _usage_and_exit()

    for p in sys.argv[1:]:
        process_path(p)
