"""
Command line interface module
"""

import argparse
from pathlib import Path
from typing import List, Optional

from .utils import get_python_version_warning, validate_python_version


def parse_arguments(args: Optional[List[str]] = None) -> argparse.Namespace:
    """
    Parse command line arguments

    Args:
        args: Arguments to parse. If None, uses sys.argv

    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        prog="auto-wheel",
        description="Automatically download Python wheel packages for offline installation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Download packages from requirements.txt for Python 3.9
    auto-wheel -p 3.9 -r requirements.txt

    # Download specific packages
    auto-wheel -p 3.9 -pkg requests flask pandas

    # Auto-detect dependency source from project directory
    auto-wheel -p 3.9 --from ./my-project

    # Specify a specific lock file or pyproject.toml
    auto-wheel -p 3.9 --from ./my-project/uv.lock
    auto-wheel -p 3.9 --from ./my-project/pyproject.toml

    # Specify output directory
    auto-wheel -p 3.9 -r requirements.txt -o ./my_wheels

    # Specify target platform
    auto-wheel -p 3.9 -r requirements.txt --platform manylinux2014_x86_64

    # Use custom config file
    auto-wheel -p 3.9 -r requirements.txt -c config.json

    # Preview dependencies without downloading
    auto-wheel -p 3.9 -pkg requests==2.31.0 --plan-only -o ./preview

    # Download with confirmed dependency tree
    auto-wheel -p 3.9 -pkg requests==2.31.0 --approve-tree ./preview/dependency-tree.json

    # Generate requirements with hash verification
    auto-wheel -p 3.9 -r requirements.txt --with-hashes

    # Verify offline installability after download
    auto-wheel -p 3.9 -r requirements.txt --verify-installability
        """,
    )

    # Python version
    parser.add_argument(
        "-p",
        "--python-version",
        type=str,
        help="Target Python version (e.g., 3.9, 3.10, 3.11)",
    )

    # Input source: either requirements file or package names
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "-r", "--requirements", type=str, help="Path to requirements.txt file"
    )
    input_group.add_argument(
        "-pkg",
        "--packages",
        nargs="+",
        help="Package names to download (space separated)",
    )
    input_group.add_argument(
        "--from",
        type=str,
        dest="from_path",
        help="Path to dependency source file or project directory "
        "(auto-detects requirements.txt / pyproject.toml / lock file)",
    )

    # Output directory
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        help="Output directory for downloaded wheels (default: ./downloads)",
    )

    # Platform specification
    parser.add_argument(
        "--platform",
        type=str,
        help="Target platform (e.g., win_amd64, manylinux2014_x86_64, macosx_10_9_x86_64, auto)",
    )

    # Implementation (CPython, PyPy, etc.)
    parser.add_argument(
        "--implementation",
        type=str,
        default="cp",
        help="Python implementation (default: cp for CPython)",
    )

    # ABI
    parser.add_argument(
        "--abi",
        type=str,
        help="Python ABI (e.g., cp39, none). If not specified, auto-detected from Python version",
    )

    # Config file
    parser.add_argument(
        "-c", "--config", type=str, help="Path to configuration file (JSON format)"
    )

    # Generate requirements with hashes
    parser.add_argument(
        "--with-hashes",
        action="store_true",
        help="Generate requirements.txt with package hashes for secure installation",
    )

    # Only binary (wheel-first with automatic source fallback)
    parser.add_argument(
        "--only-binary",
        type=str,
        default=":all:",
        help="Prefer binary wheels (default: :all:). Falls back to source distributions when no wheels are available",
    )

    # Verbose output
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose output"
    )

    # Dry run
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be downloaded without actually downloading",
    )

    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Only resolve dependencies and generate preview artifacts (dependency-tree.json, coverage-report.md) without downloading",
    )

    parser.add_argument(
        "--approve-tree",
        type=str,
        help="Path to approved dependency-tree.json for confirmation gate (use after --plan-only)",
    )

    parser.add_argument(
        "--verify-installability",
        action="store_true",
        help="Run offline installability verification after download and generate installability-report.md",
    )

    return parser.parse_args(args)


def validate_arguments(args: argparse.Namespace) -> None:
    """
    Validate parsed arguments

    Args:
        args: Parsed arguments

    Raises:
        ValueError: If arguments are invalid
    """
    # Validate requirements file exists
    if args.requirements:
        req_path = Path(args.requirements)
        if not req_path.exists():
            raise ValueError(f"Requirements file not found: {args.requirements}")
        if not req_path.is_file():
            raise ValueError(f"Not a file: {args.requirements}")

    # Validate --from path exists
    if getattr(args, "from_path", None):
        from_path = Path(args.from_path)
        if not from_path.exists():
            raise ValueError(f"Path not found: {args.from_path}")

    # Validate Python version format
    if args.python_version:
        validate_python_version(args.python_version)
        warning = get_python_version_warning(args.python_version)
        if warning:
            print(warning)

    # Validate config file if specified
    if args.config:
        config_path = Path(args.config)
        if not config_path.exists():
            raise ValueError(f"Config file not found: {args.config}")
        if not config_path.is_file():
            raise ValueError(f"Not a file: {args.config}")

    if args.plan_only and args.approve_tree:
        raise ValueError("--plan-only 与 --approve-tree 不能同时使用")

    if args.approve_tree:
        approve_path = Path(args.approve_tree)
        if not approve_path.exists():
            raise ValueError(f"Approved dependency tree file not found: {args.approve_tree}")
        if not approve_path.is_file():
            raise ValueError(f"Not a file: {args.approve_tree}")
