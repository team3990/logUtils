from argparse import ArgumentParser

from lib.croplib import crop
from lib.mergelib import merge


if __name__ == "__main__":
    parser = ArgumentParser(description="Concatenate multiple WPILOG files")
    parser.add_argument(
        "inputs", nargs="+", help="Input WPILOG files to concatenate (order matters)"
    )
    parser.add_argument("-o", "--output", required=True, help="Output WPILOG path")
    parser.add_argument("-c", "--no-crop", required=False, help="Do not crop before merging", default=False)
    parser.add_argument(
        "-g",
        "--gap",
        type=float,
        default=2000,
        help="Gap in milliseconds between files (default: 2000 ms)",
    )
    args = parser.parse_args()

    if not args.crop:
        for file in args.inputs:
            crop(file, round(args.gap / 3), round(args.gap / 3))

    merge(args.inputs, args.output, round(args.gap / 3))
