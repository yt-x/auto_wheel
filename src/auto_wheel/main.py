"""
Main entry point for auto-wheel
"""

import sys
from pathlib import Path
from typing import Any, Dict, List

from .cli import parse_arguments, validate_arguments
from .config import Config
from .downloader import WheelDownloader
from .requirements_generator import RequirementsGenerator
from .resolver import DependencyResolver
from .utils import get_python_version_warning, validate_python_version


def _summarize_stage_errors(errors: List[Dict[str, Any]]) -> Dict[str, str]:
    """Build compact per-stage error summary for CLI output."""
    stage_summary: Dict[str, str] = {}
    for err in errors or []:
        stage = err.get("stage") or "unknown"
        detail = (err.get("stderr") or err.get("stdout") or err.get("message") or "").strip()
        if detail and stage not in stage_summary:
            stage_summary[stage] = detail.splitlines()[0]
    return stage_summary


def _count_manifest_entries(manifest_path: Path) -> int:
    """Count non-comment entries in a manifest file."""
    if not manifest_path.exists():
        return 0

    count = 0
    with open(manifest_path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                count += 1
    return count


def main() -> None:
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
        validate_python_version(python_version)
        python_warning = get_python_version_warning(python_version)
        if python_warning:
            print(python_warning, file=sys.stderr)

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
            use_uv_resolver=config.use_uv_resolver,
            max_attempts=max(1, config.retries),
            retry_delay=3.0,
            # command_timeout: 整体 pip download 命令的超时（秒），最小 60
            # pip_timeout: pip 内部单个网络请求的超时（由配置控制）
            command_timeout=max(config.pip_timeout, 60)
        )

        # Resolve dependencies (optional uv)
        resolver = DependencyResolver(
            python_version=python_version,
            platform=platform if platform != "auto" else None,
            pip_args=config.get_pip_args(),
            use_uv=config.use_uv_resolver,
            timeout=config.timeout,
            verbose=args.verbose
        )
        print("Downloading packages...")
        print()

        if args.requirements:
            # 保留 -r 原生语义：优先尝试 uv 解析，失败或不可用则直接透传给 pip -r
            resolved_packages, used_uv, resolver_warning = resolver.resolve_from_requirements_file(args.requirements)
            if resolver_warning:
                print(f"Warning: {resolver_warning}", file=sys.stderr)

            if used_uv and resolved_packages:
                result = downloader.download_resolved_requirements(
                    resolved_packages,
                    dry_run=args.dry_run
                )
            else:
                result = downloader.download_from_requirements(
                    args.requirements,
                    dry_run=args.dry_run
                )
        else:
            packages_input = [pkg.strip() for pkg in (args.packages or []) if pkg.strip()]
            if not packages_input:
                raise ValueError("No packages to process. Check requirements file or --packages input.")

            resolved_packages, used_uv, resolver_warning = resolver.resolve(packages_input)
            if resolver_warning:
                print(f"Warning: {resolver_warning}", file=sys.stderr)

            if used_uv and resolved_packages:
                result = downloader.download_resolved_requirements(
                    resolved_packages,
                    dry_run=args.dry_run
                )
                if (
                    not args.dry_run
                    and not result.get("success")
                    and WheelDownloader._detect_no_wheel_reason(result.get("errors") or [])
                ):
                    print(
                        "Warning: uv 解析结果下载失败，回退到原始包列表重试。",
                        file=sys.stderr
                    )
                    result = downloader.download_packages(
                        packages_input,
                        dry_run=args.dry_run
                    )
            else:
                result = downloader.download_packages(
                    packages_input,
                    dry_run=args.dry_run
                )

        # Check result
        if not result["success"]:
            print("\nDownload failed!", file=sys.stderr)
            if result.get("fallback_reason"):
                print(f"Fallback reason: {result['fallback_reason']}", file=sys.stderr)
            stage_summary = _summarize_stage_errors(result.get("errors") or [])
            for stage, detail in stage_summary.items():
                print(f"[{stage}] {detail}", file=sys.stderr)
            print(result.get("error", "Unknown error"), file=sys.stderr)
            sys.exit(1)

        if args.dry_run:
            print("\nDry run completed successfully.")
            print(f"Command that would be executed:\n{result['command']}")
            return

        print("\nDownload completed successfully!")
        print(f"Packages saved to: {output_dir}")
        if result.get("used_source_fallback"):
            print("Notice: wheel-only download failed, source fallback succeeded.")
            if result.get("fallback_reason"):
                print(f"  Reason: {result['fallback_reason']}")
            fallback_report = result.get("source_fallback_report") or {}
            if fallback_report:
                print(
                    "  Source fallback summary:"
                    f" source_packages={fallback_report.get('source_package_count', 0)},"
                    f" wheel_dependencies={fallback_report.get('wheel_dependency_count', 0)},"
                    f" warnings={len(fallback_report.get('warnings') or [])}"
                )
            print("  Please process SOURCE_INSTALL_GUIDE.md before offline installation.")

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

            wheel_count = len(list(Path(output_dir).glob("*.whl")))
            sources_manifest = Path(output_dir) / "sources-offline.txt"
            source_guide = Path(output_dir) / "SOURCE_INSTALL_GUIDE.md"
            source_count = _count_manifest_entries(sources_manifest)

            print(f"\nArtifacts summary: wheels={wheel_count}, source packages={source_count}")
            if source_count > 0:
                print(f"  Source packages dir: {Path(output_dir) / 'sources'}")
                print(f"  Source manifest: {sources_manifest}")
                print(f"  Source guide: {source_guide}")

            print("\n" + "=" * 60)
            print("Setup complete! To install offline:")
            print("=" * 60)
            print(f"1. Copy the '{Path(output_dir).name}' folder to your offline machine")
            if source_count > 0:
                print(f"2. Source packages detected. Handle them first:")
                print(f"   - Review guide: {Path(output_dir).name}/SOURCE_INSTALL_GUIDE.md")
                print(f"   - Process sources listed in: {Path(output_dir).name}/sources-offline.txt")
                print(f"3. After source packages are handled, run:")
            else:
                print("2. Run:")
            print(f"   python -m pip install --no-index --find-links={Path(output_dir).name} -r {Path(output_dir).name}/requirements-offline.txt")
            print("   Or execute the install script:")
            print(f"   - Linux/Mac: cd {Path(output_dir).name} && ./install.sh")
            print(f"   - Windows: cd {Path(output_dir).name} && install.bat")
            print("=" * 60)

        except Exception as e:
            print(f"\nWarning: Failed to generate requirements file: {e}", file=sys.stderr)
            print("You can still install packages using:")
            print(f"  python -m pip install --no-index --find-links={output_dir} <package_name>")

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
