"""
Main entry point for auto-wheel
"""

import sys
from pathlib import Path

from .cli import parse_arguments, validate_arguments
from .config import Config
from .downloader import WheelDownloader
from .requirements_generator import RequirementsGenerator


def main():
    """Main entry point"""
    try:
        # Parse command line arguments
        args = parse_arguments()

        # Validate arguments
        validate_arguments(args)

        # Load configuration
        config = Config(config_path=args.config)

        # Get Python version (from args or config)
        python_version = args.python_version or config.get("default_python_version")
        if not python_version:
            print("Error: Python version not specified. Use -p/--python-version or set default_python_version in config.", file=sys.stderr)
            sys.exit(1)

        # Get output directory (from args or config)
        output_dir = args.output or config.download_dir

        # Get platform
        platform = args.platform or config.get("default_platform", "auto")

        # Print configuration
        print("=" * 60)
        print("Auto Wheel - Offline Package Downloader")
        print("=" * 60)
        print(f"Python version: {python_version}")
        print(f"Platform: {platform}")
        print(f"Output directory: {output_dir}")
        print(f"Implementation: {args.implementation}")
        print(f"ABI: {args.abi or 'auto'}")

        if args.requirements:
            print(f"Requirements file: {args.requirements}")
        elif args.packages:
            print(f"Packages: {', '.join(args.packages)}")

        if config.index_url:
            print(f"Index URL: {config.index_url}")
        else:
            print("Index URL: https://pypi.org/simple (default)")

        if args.dry_run:
            print("\n[DRY RUN MODE - No files will be downloaded]")

        print("=" * 60)
        print()

        # Initialize downloader
        downloader = WheelDownloader(
            python_version=python_version,
            output_dir=output_dir,
            platform=platform if platform != "auto" else None,
            implementation=args.implementation,
            abi=args.abi,
            only_binary=args.only_binary,
            verbose=args.verbose,
            config_pip_args=config.get_pip_args(),
            max_attempts=max(1, config.retries),
            retry_delay=3.0,
            command_timeout=max(config.timeout, 60)
        )

        # Download packages
        print("Downloading packages...")
        print()

        if args.requirements:
            result = downloader.download_from_requirements(
                args.requirements,
                dry_run=args.dry_run
            )
        else:
            result = downloader.download_packages(
                args.packages,
                dry_run=args.dry_run
            )

        # Check result
        if not result["success"]:
            print("\nDownload failed!", file=sys.stderr)
            print(result.get("error", "Unknown error"), file=sys.stderr)
            sys.exit(1)

        if args.dry_run:
            print("\nDry run completed successfully.")
            print(f"Command that would be executed:\n{result['command']}")
            return

        print("\nDownload completed successfully!")
        print(f"Packages saved to: {output_dir}")

        # Generate requirements file
        print("\nGenerating offline requirements file...")
        generator = RequirementsGenerator(
            output_dir=output_dir,
            with_hashes=args.with_hashes
        )

        try:
            req_file = generator.generate()
            print(f"Requirements file generated: {req_file}")

            # Generate installation scripts
            script_file = generator.generate_install_script()
            print(f"Installation script generated: {script_file}")
            print(f"  Also generated: {Path(output_dir) / 'install.bat'}")

            print("\n" + "=" * 60)
            print("Setup complete! To install offline:")
            print("=" * 60)
            print(f"1. Copy the '{Path(output_dir).name}' folder to your offline machine")
            print(f"2. Run: pip install --no-index --find-links={Path(output_dir).name} -r {Path(output_dir).name}/requirements-offline.txt")
            print("   Or execute the install script:")
            print(f"   - Linux/Mac: cd {Path(output_dir).name} && ./install.sh")
            print(f"   - Windows: cd {Path(output_dir).name} && install.bat")
            print("=" * 60)

        except Exception as e:
            print(f"\nWarning: Failed to generate requirements file: {e}", file=sys.stderr)
            print("You can still install packages using:")
            print(f"  pip install --no-index --find-links={output_dir} <package_name>")

    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user.", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        if args.verbose if 'args' in locals() else False:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
