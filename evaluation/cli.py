"""Public command-line interface for SecureVibeBench."""

from __future__ import annotations

import argparse
import sys

from . import run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="securevibebench", description="Run secure coding agent benchmarks.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "eval", help="Generate and evaluate code on SecureVibeBench tasks",
        description=run.__doc__, parents=[run.build_parser()], add_help=False,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    arguments = sys.argv[1:] if argv is None else argv
    if not arguments:
        parser.print_help()
        return 0
    return run.evaluate(parser.parse_args(arguments))
