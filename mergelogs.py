from argparse import ArgumentParser

from lib.mergelib import merge


if __name__ == "__main__":
    parser = ArgumentParser(description="Concatenate multiple WPILOG files")
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

    merge(args.inputs, args.output, args.gap)
