from __future__ import annotations

import argparse
from pathlib import Path

from .config import Config
from .pipeline import reframe


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clipperx",
        description="Convert horizontal video to a stable 9:16 cinematic reframe.",
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--analysis-width", type=int, default=480)
    parser.add_argument("--sample-fps", type=float, default=4.0)
    parser.add_argument("--lookahead", type=float, default=1.5)
    parser.add_argument("--width", type=int, default=1080)
    parser.add_argument("--height", type=int, default=1920)
    parser.add_argument("--crf", type=int, default=20)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    config = Config(
        analysis_width=args.analysis_width,
        sample_fps=args.sample_fps,
        lookahead_seconds=args.lookahead,
        output_width=args.width,
        output_height=args.height,
        crf=args.crf,
    )
    output = reframe(args.input, args.output, config)
    print(f"Created {output}")


if __name__ == "__main__":
    main()
