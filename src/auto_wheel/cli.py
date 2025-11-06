"""
Command line interface module
"""

import argparse
import sys
from pathlib import Path
from typing import List, Optional


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

  # Specify output directory
  auto-wheel -p 3.9 -r requirements.txt -o ./my_wheels

  # Specify target platform
  auto-wheel -p 3.9 -r requirements.txt --platform manylinux2014_x86_64

  # Use custom config file
  auto-wheel -p 3.9 -r requirements.txt -c config.json
        """
    )

    # Python version
    parser.add_argument(
        "-p", "--python-version",
        type=str,
        help="Target Python version (e.g., 3.9, 3.10, 3.11)"
    )

    # Input source: either requirements file or package names
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "-r", "--requirements",
        type=str,
        help="Path to requirements.txt file"
    )
    input_group.add_argument(
        "-pkg", "--packages",
        nargs="+",
        help="Package names to download (space separated)"
    )

    # Output directory
    parser.add_argument(
        "-o", "--output",
        type=str,
        help="Output directory for downloaded wheels (default: ./downloads)"
    )

    # Platform specification
    parser.add_argument(
        "--platform",
        type=str,
        help="Target platform (e.g., win_amd64, manylinux2014_x86_64, macosx_10_9_x86_64, auto)"
    )

    # Implementation (CPython, PyPy, etc.)
    parser.add_argument(
        "--implementation",
        type=str,
        default="cp",
        help="Python implementation (default: cp for CPython)"
    )

    # ABI
    parser.add_argument(
        "--abi",
        type=str,
        help="Python ABI (e.g., cp39, none). If not specified, auto-detected from Python version"
    )

    # Config file
    parser.add_argument(
        "-c", "--config",
        type=str,
        help="Path to configuration file (JSON format)"
    )

    # Generate requirements with hashes
    parser.add_argument(
        "--with-hashes",
        action="store_true",
        help="Generate requirements.txt with package hashes for secure installation"
    )

    # Only binary (no source distributions)
    parser.add_argument(
        "--only-binary",
        type=str,
        default=":all:",
        help="Only download binary wheels, no source distributions (default: :all:)"
    )

    # Verbose output
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output"
    )

    # Dry run
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be downloaded without actually downloading"
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

    # Validate Python version format
    if args.python_version:
        parts = args.python_version.split(".")
        if len(parts) < 2:
            raise ValueError(
                f"Invalid Python version format: {args.python_version}. "
                "Expected format: X.Y or X.Y.Z (e.g., 3.9 or 3.9.7)"
            )
        try:
            major, minor = int(parts[0]), int(parts[1])
            if major < 3 or (major == 3 and minor < 7):
                print(f"Warning: Python {args.python_version} is quite old. "
                      "Some packages may not be available.")
        except ValueError:
            raise ValueError(
                f"Invalid Python version: {args.python_version}. "
                "Version numbers must be integers."
            )

    # Validate config file if specified
    if args.config:
        config_path = Path(args.config)
        if not config_path.exists():
            raise ValueError(f"Config file not found: {args.config}")
        if not config_path.is_file():
            raise ValueError(f"Not a file: {args.config}")
