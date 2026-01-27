#!/usr/bin/env python3
"""
Build Script for Winget Upgrade Manager
Creates a standalone Windows executable using PyInstaller.
"""

import subprocess
import sys
import shutil
from pathlib import Path


def main():
    """Build the executable."""
    print("=" * 60)
    print("Building Winget Upgrade Manager")
    print("=" * 60)

    # Ensure we're in the project directory
    project_dir = Path(__file__).parent

    # Check for PyInstaller
    try:
        import PyInstaller

        print(f"✓ PyInstaller {PyInstaller.__version__} found")
    except ImportError:
        print("✗ PyInstaller not found. Installing...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "pyinstaller>=6.0"]
        )
        print("✓ PyInstaller installed")

    # Clean previous builds
    for folder in ["build", "dist"]:
        path = project_dir / folder
        if path.exists():
            print(f"Cleaning {folder}/...")
            shutil.rmtree(path)

    # Build command
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",  # Single executable
        "--windowed",  # No console window
        "--name",
        "WingetUpgradeManager",
        "--clean",  # Clean PyInstaller cache
        # Hidden imports for CustomTkinter
        "--hidden-import",
        "customtkinter",
        "--hidden-import",
        "darkdetect",
        "--hidden-import",
        "PIL",
        # Collect all CustomTkinter data files
        "--collect-all",
        "customtkinter",
        # Main script
        str(project_dir / "main.py"),
    ]

    print("\nRunning PyInstaller...")
    print("-" * 60)

    result = subprocess.run(cmd, cwd=project_dir)

    print("-" * 60)

    if result.returncode == 0:
        exe_path = project_dir / "dist" / "WingetUpgradeManager.exe"
        if exe_path.exists():
            size_mb = exe_path.stat().st_size / (1024 * 1024)
            print("\n✓ Build successful!")
            print(f"  Output: {exe_path}")
            print(f"  Size: {size_mb:.1f} MB")
        else:
            print("\n✗ Build completed but executable not found")
            return 1
    else:
        print(f"\n✗ Build failed with code {result.returncode}")
        return 1

    # Clean up spec file (we don't need it in the repo)
    spec_file = project_dir / "WingetUpgradeManager.spec"
    if spec_file.exists():
        spec_file.unlink()
        print("  Cleaned up spec file")

    # Generate and display checksum (for verification)
    import hashlib

    sha256_hash = hashlib.sha256()
    with open(exe_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256_hash.update(chunk)
    checksum = sha256_hash.hexdigest().upper()
    print(f"  SHA256: {checksum}")

    print("\n" + "=" * 60)
    print("Done! You can now run dist/WingetUpgradeManager.exe")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
