"""
Winget Command Runner Module
Handles execution and parsing of winget commands.
"""

import subprocess
import re
import threading
from dataclasses import dataclass
from typing import List, Callable, Optional


@dataclass
class Package:
    """Represents an upgradable package."""

    name: str
    id: str
    current_version: str
    available_version: str
    source: str


def get_upgradable_packages() -> tuple[List[Package], str]:
    """
    Run 'winget upgrade' and parse the output into Package objects.
    Returns a tuple of (packages list, raw output string).
    """
    try:
        # Run winget upgrade command
        result = subprocess.run(
            ["winget", "upgrade"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

        output = result.stdout
        packages = parse_winget_output(output)
        return packages, output

    except FileNotFoundError:
        return [], "Error: winget is not installed or not in PATH"
    except Exception as e:
        return [], f"Error running winget: {str(e)}"


def parse_winget_output(output: str) -> List[Package]:
    """Parse the winget upgrade output into Package objects."""
    packages = []
    lines = output.strip().split("\n")

    # Find the header line with dashes
    header_index = -1
    for i, line in enumerate(lines):
        if line.startswith("---") or (line.startswith("-") and len(line) > 20):
            header_index = i
            break

    if header_index == -1 or header_index == 0:
        return packages

    # Get the header line to determine column positions
    header_line = lines[header_index - 1]
    dash_line = lines[header_index]

    # Find column positions based on the header
    # Headers: Name, Id, Version, Available, Source
    name_pos = 0
    id_pos = header_line.lower().find("id")
    version_pos = header_line.lower().find("version")
    available_pos = header_line.lower().find("available")
    source_pos = header_line.lower().find("source")

    # Fallback: use dash segments to find columns
    if id_pos == -1:
        # Try to find columns by looking at dash separations
        segments = re.findall(r"-+", dash_line)
        if len(segments) >= 5:
            pos = 0
            positions = []
            for seg in segments:
                positions.append(pos)
                pos += len(seg) + 1
            if len(positions) >= 5:
                name_pos, id_pos, version_pos, available_pos, source_pos = positions[:5]

    # Parse each package line
    for line in lines[header_index + 1 :]:
        if not line.strip():
            continue
        if "upgrades available" in line.lower():
            continue
        if line.startswith(" ") and len(line.strip()) == 0:
            continue

        try:
            # Extract fields based on positions
            if source_pos > 0:
                name = line[name_pos:id_pos].strip()
                pkg_id = line[id_pos:version_pos].strip()
                current_ver = line[version_pos:available_pos].strip()
                available_ver = line[available_pos:source_pos].strip()
                source = line[source_pos:].strip()

                # Handle the < prefix in version (indicates older than)
                current_ver = current_ver.lstrip("< ")

                if pkg_id and available_ver:
                    packages.append(
                        Package(
                            name=name if name else pkg_id,
                            id=pkg_id,
                            current_version=current_ver,
                            available_version=available_ver,
                            source=source,
                        )
                    )
        except Exception:
            continue

    return packages


def upgrade_package(
    package_id: str,
    output_callback: Optional[Callable[[str], None]] = None,
    complete_callback: Optional[Callable[[bool, str], None]] = None,
) -> None:
    """
    Upgrade a specific package by ID.
    Runs in a separate thread to avoid blocking the UI.

    Args:
        package_id: The winget package ID to upgrade
        output_callback: Called with each line of output
        complete_callback: Called when complete with (success, message)
    """

    def run_upgrade():
        try:
            process = subprocess.Popen(
                [
                    "winget",
                    "upgrade",
                    package_id,
                    "--accept-package-agreements",
                    "--accept-source-agreements",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW,
            )

            full_output = []
            for line in process.stdout:
                line = line.rstrip()
                full_output.append(line)
                if output_callback:
                    output_callback(line)

            process.wait()

            output_text = "\n".join(full_output)
            success = process.returncode == 0 or "Successfully installed" in output_text

            if complete_callback:
                if success:
                    complete_callback(True, f"Successfully upgraded {package_id}")
                else:
                    complete_callback(False, f"Failed to upgrade {package_id}")

        except Exception as e:
            if complete_callback:
                complete_callback(False, f"Error: {str(e)}")

    thread = threading.Thread(target=run_upgrade, daemon=True)
    thread.start()


def upgrade_all_packages(
    packages: List[Package],
    output_callback: Optional[Callable[[str], None]] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    complete_callback: Optional[Callable[[int, int], None]] = None,
) -> None:
    """
    Upgrade all packages sequentially.

    Args:
        packages: List of packages to upgrade
        output_callback: Called with each line of output
        progress_callback: Called with (current_index, total, package_name)
        complete_callback: Called when all done with (success_count, fail_count)
    """

    def run_all():
        success_count = 0
        fail_count = 0

        for i, pkg in enumerate(packages):
            if progress_callback:
                progress_callback(i + 1, len(packages), pkg.name)

            if output_callback:
                output_callback(f"\n{'=' * 60}")
                output_callback(f"Upgrading {pkg.name} ({i + 1}/{len(packages)})")
                output_callback(f"{'=' * 60}\n")

            try:
                process = subprocess.Popen(
                    [
                        "winget",
                        "upgrade",
                        pkg.id,
                        "--accept-package-agreements",
                        "--accept-source-agreements",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )

                full_output = []
                for line in process.stdout:
                    line = line.rstrip()
                    full_output.append(line)
                    if output_callback:
                        output_callback(line)

                process.wait()

                output_text = "\n".join(full_output)
                if process.returncode == 0 or "Successfully installed" in output_text:
                    success_count += 1
                else:
                    fail_count += 1

            except Exception as e:
                fail_count += 1
                if output_callback:
                    output_callback(f"Error: {str(e)}")

        if complete_callback:
            complete_callback(success_count, fail_count)

    thread = threading.Thread(target=run_all, daemon=True)
    thread.start()
