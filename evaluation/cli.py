"""Public command-line interface for SecureVibeBench."""

from __future__ import annotations

import argparse
from importlib.metadata import PackageNotFoundError, version
import sys

from . import run


def package_version() -> str:
    try:
        return version("securevibebench")
    except PackageNotFoundError:
        return "unknown"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="securevibebench", description="Run secure coding agent benchmarks.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {package_version()}")
    commands = parser.add_subparsers(dest="command", required=True)
    evaluation = commands.add_parser(
        "eval", help="Generate and evaluate code on SecureVibeBench tasks",
        description=run.__doc__, parents=[run.build_parser()], add_help=False,
    )
    evaluation.set_defaults(usage_error=evaluation.error)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    arguments = sys.argv[1:] if argv is None else argv
    if not arguments:
        parser.print_help()
        return 0
    return run.evaluate(run.check_arguments(parser.parse_args(arguments)))
