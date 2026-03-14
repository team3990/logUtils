import argparse
import mmap
import struct
from typing import Optional

from lib.datalog import DataLogReader
from lib.utils import patch_control_entry_id, write_new_record, write_record


def merge_logs(input_paths: list[str], output_path: str, gap_ms: int = 1) -> None:
    if len(input_paths) == 0:
        raise ValueError("no input files")

    # basic header (v1.0) and empty extra header
    out = bytearray()
    out += b"WPILOG"
    out += struct.pack("<H", 0x0100)
    out += struct.pack("<I", 0)

    max_entry_id = 0
    last_timestamp = 0
    next_entry_id = 0

    # Process files in order. For the first file we copy records verbatim while
    # discovering the maximum entry id and last timestamp. For each subsequent
    # file we remap entry IDs (assigning increasing IDs starting after the max
    # seen so far) and offset timestamps so the file sits after the previous one.
    for i, path in enumerate(input_paths):
        with open(path, "rb") as f:
            buf = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)

        reader = DataLogReader(buf)
        if not reader:
            raise ValueError(f"Not a valid WPILOG file: {path}")

        if i == 0:
            # first quick scan to discover first timestamp, last timestamp and max entry id
            first_ts: Optional[int] = None
            for record in reader:
                if first_ts is None:
                    first_ts = record.timestamp
                if record.timestamp > last_timestamp:
                    last_timestamp = record.timestamp
                if record.isStart():
                    try:
                        start = record.getStartData()
                        if start.entry > max_entry_id:
                            max_entry_id = start.entry
                    except TypeError:
                        pass

            # prepare next_entry_id and annotation
            next_entry_id = max_entry_id + 1

            # place annotation just before the first record (one microsecond before)
            if first_ts is None:
                # empty file — nothing to copy, continue
                continue
            annotation_entry = next_entry_id
            next_entry_id += 1
            annotation_ts = max(0, first_ts - 1)

            ann_name = "nextLog"
            ann_type = "string"
            write_new_record(out, annotation_ts, annotation_entry, ann_name, ann_type, path.encode("utf-8"))

            # second pass: write the file records verbatim
            reader2 = DataLogReader(buf)
            for record in reader2:
                write_record(out, record.entry, record.timestamp, bytes(record.data))
        else:
            # gap in microseconds. Ensure we leave at least a tiny slot so the
            # annotation can be placed immediately after the previous file and
            # before any records from the next file.
            gap_us = int(gap_ms * 1000)
            # Add a small safety delta so the next file's first record is strictly
            # after the annotation.
            SAFETY_US = 2
            timestamp_offset = last_timestamp + gap_us + SAFETY_US

            # add a string entry to indicate file name of next match (the annotation)
            annotation_entry = next_entry_id
            next_entry_id += 1
            # place the annotation immediately after the end of the previous file
            # (one microsecond after last_timestamp)
            annotation_ts = last_timestamp + 1

            # Write a Start control for the annotation entry and a single string data record
            ann_name = "nextLog"
            ann_type = "string"
            write_new_record(out, annotation_ts, annotation_entry, ann_name, ann_type, path.encode("utf-8"))

            # map of entry ids for this file -> new entry id in output
            entry_id_map: dict[int, int] = {}

            for record in reader:
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
                        payload_entry_id = int.from_bytes(
                            record.data[1:5], byteorder="little"
                        )
                        remapped_id = entry_id_map.get(
                            payload_entry_id, payload_entry_id
                        )
                        patched_data = patch_control_entry_id(
                            bytes(record.data), remapped_id
                        )
                    else:
                        patched_data = bytes(record.data)
                    write_record(out, 0, new_timestamp, patched_data)
                else:
                    new_entry_id = entry_id_map.get(record.entry, record.entry)
                    write_record(out, new_entry_id, new_timestamp, bytes(record.data))

                # update last_timestamp as we write new records
                if new_timestamp > last_timestamp:
                    last_timestamp = new_timestamp

    with open(output_path, "wb") as f:
        f.write(out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Concatenate multiple WPILOG files")
    parser.add_argument(
        "inputs", nargs="+", help="Input WPILOG files to concatenate (order matters)"
    )
    parser.add_argument("-o", "--output", required=True, help="Output WPILOG path")
    parser.add_argument(
        "--gap",
        type=float,
        default=1.0,
        help="Gap in milliseconds between files (default: 1 ms)",
    )
    args = parser.parse_args()

    merge_logs(args.inputs, args.output, args.gap)
