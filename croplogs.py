import mmap
import os
import struct
import sys
from argparse import ArgumentParser
from glob import glob
from typing import Optional

from lib.datalog import DataLogReader
from lib.utils import write_record

RSL_STATE_ID = "/Robot/SystemStats/RSLState"

# require continuous true for at least TRUE_CONFIRM_US (module constant)
TRUE_CONFIRM_US = 20000000


def _find_rsl_false_then_true_timestamps(
    buf: bytes,
) -> tuple[Optional[int], Optional[int]]:
    """Return (first_false_ts, first_true_after_false_ts).

    first_false_ts: timestamp of the first record where RSLState is False.
    first_true_after_false_ts: timestamp of the first record after that where RSLState becomes True.
    Either value may be None if not found or the buffer isn't a valid log.
    """
    reader = DataLogReader(buf)
    if not reader:
        return (None, None)

    entries = {}
    found_false_ts: Optional[int] = None
    candidate_true_start: Optional[int] = None

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
                # still advance time — candidate_true_start may be confirmed by any later timestamp
                if (
                    candidate_true_start is not None
                    and rec.timestamp >= candidate_true_start + TRUE_CONFIRM_US
                ):
                    return (found_false_ts, candidate_true_start + TRUE_CONFIRM_US)
                continue

            if entry.name == RSL_STATE_ID:
                try:
                    if entry.type != "boolean":
                        continue
                    val = rec.getBoolean()

                    if found_false_ts is None:
                        # Look for first False
                        if not val:
                            found_false_ts = rec.timestamp
                        # reset candidate until we've seen a False
                        candidate_true_start = None
                    else:
                        # After we've seen False, look for sustained True
                        if val:
                            if candidate_true_start is None:
                                candidate_true_start = rec.timestamp
                            # If this record's timestamp is already past the confirmation threshold,
                            # we can return the confirmation time (start + threshold)
                            if rec.timestamp >= candidate_true_start + TRUE_CONFIRM_US:
                                return (
                                    found_false_ts,
                                    candidate_true_start + TRUE_CONFIRM_US,
                                )
                        else:
                            # False observed again, reset true candidate
                            candidate_true_start = None
                except TypeError:
                    continue

            # For non-RSL records, the passage of time can still confirm a candidate true
            if (
                candidate_true_start is not None
                and rec.timestamp >= candidate_true_start + TRUE_CONFIRM_US
            ):
                return (found_false_ts, candidate_true_start + TRUE_CONFIRM_US)

    return (found_false_ts, None)


def crop_to_timestamp(
    buf: bytes, start_ts: int, end_ts: Optional[int] = None
) -> Optional[bytes]:
    """Return cropped log bytes or None if input invalid.

    If end_ts is provided, the output will contain records with start_ts <= timestamp <= end_ts
    (inclusive). Any entries still active at end_ts will be closed with a Finish control record
    at end_ts so the cropped log remains consistent.
    """
    reader = DataLogReader(buf)
    if not reader:
        return None

    # First pass: collect start/setMetadata/finish info that occurred before start_ts
    start_payloads: dict[int, bytes] = {}
    start_timestamps: dict[int, int] = {}
    # last data payload seen for an entry before start_ts (used to emit an initial snapshot)
    last_data_before: dict[int, bytes] = {}
    latest_setmd: dict[int, bytes] = {}
    finished_before = set()

    for rec in reader:
        if rec.timestamp >= start_ts:
            continue
        if rec.isStart():
            try:
                sd = rec.getStartData()
                start_payloads[sd.entry] = bytes(rec.data)
                start_timestamps[sd.entry] = rec.timestamp
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
        else:
            # capture last data payload for entries before the crop start; this lets us
            # emit an initial snapshot at timestamp 0 so values like RSLState are present
            # during the padding even if no data point appears exactly at the crop start.
            try:
                # non-control data record
                last_data_before[rec.entry] = bytes(rec.data)
            except Exception:
                # ignore anything that doesn't behave like data
                pass

    # active entries: started before crop and not finished before crop
    active_entries = [
        eid for eid in start_payloads.keys() if eid not in finished_before
    ]
    active_set = set(active_entries)

    # Build output: copy header (version and extra header) from input
    out = bytearray()
    out += b"WPILOG"
    out += struct.pack("<H", reader.getVersion())
    extra = reader.getExtraHeader().encode("utf-8")
    out += struct.pack("<I", len(extra))
    out += extra

    # Emit start records for active entries (timestamp set to start_ts)
    for eid in active_entries:
        payload = start_payloads[eid]
        # shift start to 0 in the cropped file
        write_record(out, 0, 0, payload)
        # If there was a setMetadata before start_ts for this entry, emit it (so metadata matches)
        if eid in latest_setmd:
            write_record(out, 0, 0, latest_setmd[eid])
        # If we have a last-known data value for the entry from before the crop, emit
        # it at timestamp 0 so the initial state is present in the cropped log.
        if eid in last_data_before:
            write_record(out, eid, 0, last_data_before[eid])

    # Second pass: write every record with timestamp >= start_ts and <= end_ts (if provided)
    reader2 = DataLogReader(buf)
    for rec in reader2:
        if rec.timestamp < start_ts:
            continue
        if end_ts is not None and rec.timestamp > end_ts:
            # records are ordered by timestamp; we can stop
            break

        # record lies within window; write it with timestamps shifted so crop starts at 0
        shifted_ts = rec.timestamp - start_ts
        if shifted_ts < 0:
            shifted_ts = 0
        write_record(out, rec.entry, shifted_ts, bytes(rec.data))

        # Update active set for control records inside the window
        if rec.isStart():
            try:
                sd = rec.getStartData()
                active_set.add(sd.entry)
            except TypeError:
                pass
        elif rec.isFinish():
            try:
                fid = rec.getFinishEntry()
                active_set.discard(fid)
            except TypeError:
                pass

    # If we cropped the end and there are still active entries, emit Finish records at end_ts
    if end_ts is not None and len(active_set) > 0:
        for eid in sorted(active_set):
            # Finish control payload: [kControlFinish(1)] + entry_id (4 bytes little-endian)
            payload = bytes([1]) + int(eid).to_bytes(
                4, byteorder="little", signed=False
            )
            # shift end finish timestamp as well
            shifted_end = end_ts - start_ts
            if shifted_end < 0:
                shifted_end = 0
            write_record(out, 0, shifted_end, payload)

    return bytes(out)


def process_path(
    path: str, start_pad_ms: float = 5000, end_pad_ms: float = 5000
) -> None:
    with open(path, "rb") as f:
        buf = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)

    found_false, found_true_after = _find_rsl_false_then_true_timestamps(buf)
    if found_false is None:
        print(f"No RSL false found in {path}", file=sys.stderr)
        return

    # determine earliest timestamp in the file (used to clamp the crop)
    min_ts = 0
    rdr = DataLogReader(buf)
    if rdr:
        for rec in rdr:
            min_ts = rec.timestamp
            break

    # leave start_pad_sec seconds before the first false for the start crop
    start_pad_us = int(start_pad_ms * 1000)
    crop_start_ts = found_false - start_pad_us
    if crop_start_ts < min_ts:
        crop_start_ts = min_ts
    # For end crop: if we found a confirmed true timestamp after the false,
    # compute the crop end so we leave `end_pad_sec` seconds after the true
    # START. The detector returns confirmed_true == true_start + TRUE_CONFIRM_US,
    # so true_start = confirmed_true - TRUE_CONFIRM_US. We therefore set:
    #   crop_end = true_start + end_pad = confirmed_true - TRUE_CONFIRM_US + end_pad
    crop_end_ts: Optional[int] = None
    if found_true_after is not None:
        end_pad_us = int(end_pad_ms * 1000)
        crop_end_ts = found_true_after - TRUE_CONFIRM_US + end_pad_us

    # If the computed end would be before the start crop, ignore end cropping.
    if crop_end_ts is not None and crop_end_ts <= crop_start_ts:
        crop_end_ts = None

    out_bytes = crop_to_timestamp(buf, crop_start_ts, crop_end_ts)
    if out_bytes is None:
        print(f"Not a valid log: {path}", file=sys.stderr)
        return

    base, ext = os.path.splitext(path)
    out_path = f"{base}-cropped{ext}"
    with open(out_path, "wb") as f:
        f.write(out_bytes)


if __name__ == "__main__":
    parser = ArgumentParser(description="Crop log files based on rsl state")
    parser.add_argument("paths", nargs="+", help="Input log file(s) to crop")
    parser.add_argument(
        "--start-pad",
        type=float,
        default=5000,
        dest="start_pad",
        help="Miliseconds to keep before the first RSL-false (default: 5)",
    )
    parser.add_argument(
        "--end-pad",
        type=float,
        default=5000,
        dest="end_pad",
        help="Miliseconds to keep after the RSL true-start (default: 5)",
    )
    args = parser.parse_args()

    for g in args.paths:
        for p in glob(g):
            print(f"Processing {p}")
            process_path(p, args.start_pad, args.end_pad)
