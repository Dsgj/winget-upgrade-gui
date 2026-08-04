#!/usr/bin/env python3
"""
Build Script for Winget Upgrade Manager
Creates a standalone Windows executable using PyInstaller, with the app
icon and Windows version metadata embedded. CI calls this same script so
local and release builds cannot drift.
"""

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

from version import __version__

APP_NAME = "WingetUpgradeManager"

VERSION_FILE_TEMPLATE = """\
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={version_tuple},
    prodvers={version_tuple},
    mask=0x3F,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0),
  ),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'winget-upgrade-gui contributors'),
      StringStruct('FileDescription', 'Winget Upgrade Manager'),
      StringStruct('FileVersion', '{version}'),
      StringStruct('InternalName', '{app_name}'),
      StringStruct('LegalCopyright', 'MIT License'),
      StringStruct('OriginalFilename', '{app_name}.exe'),
      StringStruct('ProductName', 'Winget Upgrade Manager'),
      StringStruct('ProductVersion', '{version}'),
    ])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])]),
  ],
)
"""


def version_tuple() -> str:
    parts = [int(p) for p in __version__.split(".")]
    while len(parts) < 4:
        parts.append(0)
    return str(tuple(parts[:4]))


def main() -> int:
    # CI consoles (cp1252) choke on ✓/✗ otherwise; Actions renders UTF-8 fine.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    print("=" * 60)
    print(f"Building Winget Upgrade Manager v{__version__}")
    print("=" * 60)

    project_dir = Path(__file__).parent

    try:
        import PyInstaller

        print(f"✓ PyInstaller {PyInstaller.__version__} found")
    except ImportError:
        print("✗ PyInstaller not found. Installing...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "pyinstaller>=6.0"]
        )
        print("✓ PyInstaller installed")

    for folder in ["build", "dist"]:
        path = project_dir / folder
        if path.exists():
            print(f"Cleaning {folder}/...")
            try:
                shutil.rmtree(path)
            except PermissionError:
                print(
                    f"\n✗ Cannot remove {folder}/ — a file is locked. "
                    "Close any running WingetUpgradeManager.exe (check Task "
                    "Manager) and wait for OneDrive sync, then retry."
                )
                return 1

    version_file = project_dir / "file_version_info.txt"
    version_file.write_text(
        VERSION_FILE_TEMPLATE.format(
            version=__version__,
            version_tuple=version_tuple(),
            app_name=APP_NAME,
        ),
        encoding="utf-8",
    )

    icon = project_dir / "assets" / "icon.ico"

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--windowed",
        "--name",
        APP_NAME,
        "--clean",
        "--icon",
        str(icon),
        "--add-data",
        f"{icon};assets",
        "--version-file",
        str(version_file),
        "--hidden-import",
        "customtkinter",
        "--hidden-import",
        "darkdetect",
        "--hidden-import",
        "PIL",
        "--collect-all",
        "customtkinter",
        str(project_dir / "main.py"),
    ]

    print("\nRunning PyInstaller...")
    print("-" * 60)
    try:
        result = subprocess.run(cmd, cwd=project_dir, check=False)
    finally:
        # Clean up generated intermediates even on Ctrl+C
        for name in [f"{APP_NAME}.spec", "file_version_info.txt"]:
            artifact = project_dir / name
            if artifact.exists():
                artifact.unlink()
    print("-" * 60)

    if result.returncode != 0:
        print(f"\n✗ Build failed with code {result.returncode}")
        return 1

    exe_path = project_dir / "dist" / f"{APP_NAME}.exe"
    if not exe_path.exists():
        print("\n✗ Build completed but executable not found")
        return 1

    size_mb = exe_path.stat().st_size / (1024 * 1024)
    sha256_hash = hashlib.sha256()
    with open(exe_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256_hash.update(chunk)

    print("\n✓ Build successful!")
    print(f"  Output: {exe_path}")
    print(f"  Size:   {size_mb:.1f} MB")
    print(f"  SHA256: {sha256_hash.hexdigest().upper()}")
    print("\n" + "=" * 60)
    print(f"Done! You can now run dist/{APP_NAME}.exe")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
