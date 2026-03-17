import os
import sys
from argparse import ArgumentParser
from glob import glob

from lib.croplib import crop
from lib.mergelib import merge


def cmd_crop(args: ArgumentParser) -> int:
    # Expand globs and crop each file using provided paddings (milliseconds)
    files = []
    for pattern in args.paths:
        files.extend(glob(pattern))
    if not files:
        print("No files matched the given patterns", file=sys.stderr)
        return 2

    for p in files:
        print(f"Cropping {p} -> pad start={args.start_pad}ms end={args.end_pad}ms")
        crop(p, args.start_pad, args.end_pad)

    return 0


def cmd_merge(args: ArgumentParser) -> int:
    # Expand globs into ordered list
    inputs = []
    for pattern in args.inputs:
        inputs.extend(glob(pattern))
    if not inputs:
        print("No input files matched the given patterns", file=sys.stderr)
        return 2

    # Optionally crop inputs before merging. Cropped filenames are assumed to be
    # written as <base>-cropped<ext> by the crop function.
    if args.crop_pre:
        cropped = []
        for p in inputs:
            print(f"Pre-cropping {p}")
            crop(p, args.gap / 3.0, args.gap / 3.0)
            base, ext = os.path.splitext(p)
            cropped.append(f"{base}-cropped{ext}")
        inputs = cropped

    print(f"Merging {len(inputs)} files -> {args.output} (gap={args.gap}ms)")
    merge(inputs, args.output, gap_ms=args.gap)
    return 0


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    parser = ArgumentParser(description="Log utilities: crop and merge WPILOG files")
    sub = parser.add_subparsers(dest="cmd")

    p_crop = sub.add_parser("crop", help="Crop one or more log files")
    p_crop.add_argument("paths", nargs="+", help="Files or glob patterns to crop")
    p_crop.add_argument(
        "--start-pad",
        type=float,
        default=5000.0,
        dest="start_pad",
        help="Milliseconds to keep before the first RSL-false (default: 5000)",
    )
    p_crop.add_argument(
        "--end-pad",
        type=float,
        default=5000.0,
        dest="end_pad",
        help="Milliseconds to keep after the RSL true-start (default: 5000)",
    )

    p_merge = sub.add_parser("merge", help="Concatenate multiple WPILOG files")
    p_merge.add_argument(
        "inputs", nargs="+", help="Input file paths or glob patterns (order matters)"
    )
    p_merge.add_argument("-o", "--output", required=True, help="Output WPILOG path")
    p_merge.add_argument(
        "--gap",
        type=float,
        default=2000.0,
        help="Gap in milliseconds between files (default: 2000)",
    )
    p_merge.add_argument(
        "--crop-pre",
        action="store_true",
        help="Crop inputs before merging (uses gap/3 for pads)",
    )

    args = parser.parse_args(argv)
    if args.cmd == "crop":
        return cmd_crop(args)
    if args.cmd == "merge":
        return cmd_merge(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    main()
