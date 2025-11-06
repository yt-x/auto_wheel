"""
Requirements file generation module
"""

import hashlib
import subprocess
import sys
from pathlib import Path
from typing import List, Dict, Optional, Set
from packaging.requirements import Requirement
from packaging.version import parse as parse_version


class RequirementsGenerator:
    """Generate requirements.txt from downloaded packages"""

    def __init__(self, output_dir: str, with_hashes: bool = False):
        """
        Initialize requirements generator

        Args:
            output_dir: Directory containing downloaded packages
            with_hashes: Include package hashes in requirements.txt
        """
        self.output_dir = Path(output_dir)
        self.with_hashes = with_hashes

    def generate(self, output_file: str = "requirements-offline.txt") -> str:
        """
        Generate requirements.txt from downloaded packages

        Args:
            output_file: Name of output requirements file

        Returns:
            Path to generated requirements file
        """
        packages = self._get_packages_info()

        if not packages:
            raise ValueError(f"No packages found in {self.output_dir}")

        output_path = self.output_dir / output_file

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("# Generated offline requirements file\n")
            f.write(f"# Install with: pip install --no-index --find-links={self.output_dir.name} -r {output_file}\n")
            f.write("#\n")
            f.write("# Note: This file contains exact versions of all downloaded packages\n\n")

            for pkg_name, pkg_info in sorted(packages.items()):
                requirement = f"{pkg_name}=={pkg_info['version']}"

                if self.with_hashes and pkg_info.get('hash'):
                    f.write(f"{requirement} \\\n")
                    f.write(f"    --hash=sha256:{pkg_info['hash']}\n")
                else:
                    f.write(f"{requirement}\n")

        return str(output_path)

    def _get_packages_info(self) -> Dict[str, Dict[str, str]]:
        """
        Extract package information from downloaded files

        Returns:
            Dictionary mapping package names to their info
        """
        packages = {}

        # Find all wheel files
        for wheel_path in self.output_dir.glob("*.whl"):
            info = self._parse_wheel_filename(wheel_path)
            if info:
                pkg_name = info['name'].replace('_', '-')  # Normalize name

                # If package already exists, keep the one with higher version
                if pkg_name in packages:
                    existing_version = parse_version(packages[pkg_name]['version'])
                    new_version = parse_version(info['version'])
                    if new_version <= existing_version:
                        continue

                packages[pkg_name] = {
                    'version': info['version'],
                    'filename': wheel_path.name,
                    'hash': self._calculate_hash(wheel_path) if self.with_hashes else None
                }

        # Also handle source distributions if no wheel available
        for sdist_path in list(self.output_dir.glob("*.tar.gz")) + list(self.output_dir.glob("*.zip")):
            info = self._parse_sdist_filename(sdist_path)
            if info:
                pkg_name = info['name'].replace('_', '-')

                # Only add if no wheel exists for this package
                if pkg_name not in packages:
                    packages[pkg_name] = {
                        'version': info['version'],
                        'filename': sdist_path.name,
                        'hash': self._calculate_hash(sdist_path) if self.with_hashes else None
                    }

        return packages

    def _parse_wheel_filename(self, wheel_path: Path) -> Optional[Dict[str, str]]:
        """Parse wheel filename to extract package info"""
        filename = wheel_path.name

        if not filename.endswith(".whl"):
            return None

        # Wheel format: {distribution}-{version}(-{build})?-{python}-{abi}-{platform}.whl
        parts = filename[:-4].split("-")

        if len(parts) < 5:
            return None

        return {
            "name": parts[0],
            "version": parts[1],
        }

    def _parse_sdist_filename(self, sdist_path: Path) -> Optional[Dict[str, str]]:
        """Parse source distribution filename"""
        filename = sdist_path.name

        # Remove extensions
        if filename.endswith(".tar.gz"):
            name_version = filename[:-7]
        elif filename.endswith(".zip"):
            name_version = filename[:-4]
        else:
            return None

        # Try to split name and version
        # Format is usually: package-name-1.2.3
        parts = name_version.rsplit("-", 1)
        if len(parts) != 2:
            return None

        return {
            "name": parts[0],
            "version": parts[1],
        }

    def _calculate_hash(self, file_path: Path) -> str:
        """Calculate SHA256 hash of a file"""
        sha256_hash = hashlib.sha256()

        with open(file_path, "rb") as f:
            # Read in chunks to handle large files
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)

        return sha256_hash.hexdigest()

    def generate_install_script(self, requirements_file: str = "requirements-offline.txt") -> str:
        """
        Generate a shell script for offline installation

        Args:
            requirements_file: Name of requirements file

        Returns:
            Path to generated install script
        """
        script_path = self.output_dir / "install.sh"

        script_content = f"""#!/bin/bash
# Offline installation script
# Generated by auto-wheel

set -e

echo "Installing packages from {requirements_file}..."
pip install --no-index --find-links=. -r {requirements_file}

echo "Installation complete!"
"""

        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(script_content)

        # Make script executable on Unix-like systems
        try:
            script_path.chmod(0o755)
        except Exception:
            pass  # Windows doesn't support chmod

        # Also create a Windows batch file
        batch_path = self.output_dir / "install.bat"
        batch_content = f"""@echo off
REM Offline installation script
REM Generated by auto-wheel

echo Installing packages from {requirements_file}...
pip install --no-index --find-links=. -r {requirements_file}

echo Installation complete!
pause
"""

        with open(batch_path, 'w', encoding='utf-8') as f:
            f.write(batch_content)

        return str(script_path)
