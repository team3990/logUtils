from argparse import ArgumentParser

from lib.croplib import crop
from lib.utils import glob

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
            crop(p, args.start_pad, args.end_pad)
