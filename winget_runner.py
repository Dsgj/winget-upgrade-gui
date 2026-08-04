"""
Winget Command Runner Module
Executes and parses winget commands, classifies results via winget's
documented return codes, and streams output to callbacks.

Parsing is locale-agnostic: winget localizes its column headers and all
messages to the Windows display language, so nothing here may key off
English words. Column positions are derived from the header row itself
and rows are validated structurally.
"""

from __future__ import annotations

import logging
import re
import subprocess
import threading
import unicodedata
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger(__name__)

SCAN_TIMEOUT_SECONDS = 180

# Documented winget return codes -> human-readable reason.
# https://github.com/microsoft/winget-cli/blob/master/doc/windows/package-manager/winget/returnCodes.md
FAILURE_RETURN_CODES = {
    0x8A150001: "winget internal error",
    0x8A150006: "The installer ran but failed",
    0x8A150008: "Downloading the installer failed — check your network",
    0x8A150011: "Installer hash mismatch — the download does not match the manifest",
    0x8A150014: "No package found matching the given ID",
    0x8A150016: "Multiple packages matched — the package ID is ambiguous",
    0x8A150019: "Administrator privileges are required for this upgrade",
    0x8A150041: "Package license agreements were not accepted",
    0x8A150046: "Source agreements were not accepted",
    0x8A150056: "This installer refuses to run from an administrator session",
    0x8A150068: "A winget pin blocks this upgrade (remove it with: winget pin remove <id>)",
    0x8A15007D: "User-scoped package cannot be upgraded from an elevated (admin) session",
    0x8A150101: "The application is currently running — close it and retry",
    0x8A150102: "Another installation is already in progress — wait and retry",
    0x8A150103: "Files are in use by another application — close it and retry",
    0x8A150104: "A required dependency is missing",
    0x8A150105: "Not enough disk space",
    0x8A150106: "Not enough memory",
    0x8A150107: "No network connection",
    0x8A150108: "Installer failed — contact the application vendor",
    0x8A15010A: "Installation failed — restart your PC, then try again",
    0x8A15010C: "Installation was cancelled",
    0x8A15010D: "This version is already installed",
    0x8A15010E: "A newer version is already installed",
    0x8A15010F: "Blocked by your organization's policy",
}

# Mapped failures whose text is generic — the installer's own output
# (its exit code, log path) is the actionable part, so keep appending it.
GENERIC_FAILURE_CODES = {0x8A150001, 0x8A150006}

# Codes that mean "nothing to do" rather than a real failure.
BENIGN_RETURN_CODES = {
    0x8A15002B: "No applicable update found — already up to date",
}

# The install succeeded but Windows needs a restart to finish.
REBOOT_RETURN_CODES = {
    0x8A150109: "Upgraded — restart your PC to finish the installation",
    0x8A15010B: "Upgraded — the installer initiated a restart",
}


@dataclass
class Package:
    """Represents an upgradable package."""

    name: str
    id: str
    current_version: str
    available_version: str
    source: str
    pinned: bool = False  # True if the upgrade requires --include-pinned


@dataclass
class ScanResult:
    """Outcome of a 'winget upgrade' scan."""

    packages: list[Package] = field(default_factory=list)
    raw_output: str = ""
    error: str | None = None


@dataclass
class UpgradeResult:
    """Outcome of upgrading a single package."""

    package_id: str
    success: bool
    reason: str
    reboot_required: bool = False
    return_code: int | None = None
    cancelled: bool = False


# ---------------------------------------------------------------------------
# Output cleanup
# ---------------------------------------------------------------------------

def clean_line(line: str) -> str:
    """Reduce a winget output line to its final visible text.

    winget animates spinners and progress bars with carriage returns and
    backspaces even when writing to a pipe; only the text after the last
    carriage return is what the user would have seen.
    """
    if "\r" in line:
        line = line.rsplit("\r", 1)[-1]
    return line.replace("\x08", "").rstrip()


def is_noise_line(line: str) -> bool:
    """True for spinner-animation leftovers and blank lines."""
    stripped = line.strip()
    if not stripped:
        return True
    return len(stripped) <= 2 and all(c in "-\\|/" for c in stripped)


# ---------------------------------------------------------------------------
# Table parsing
# ---------------------------------------------------------------------------

def _char_width(ch: str) -> int:
    return 2 if unicodedata.east_asian_width(ch) in ("F", "W") else 1


def _display_column(line: str, index: int) -> int:
    """Display column (as winget aligns it) of the char at string index."""
    return sum(_char_width(ch) for ch in line[:index])


def _index_at_column(line: str, column: int) -> int:
    """String index of the char at a display column."""
    width = 0
    for i, ch in enumerate(line):
        if width >= column:
            return i
        width += _char_width(ch)
    return len(line)


def _slice_columns(line: str, start: int, end: int | None = None) -> str:
    i = _index_at_column(line, start)
    j = len(line) if end is None else _index_at_column(line, end)
    return line[i:j].strip()


def _is_separator(line: str) -> bool:
    stripped = line.strip()
    return len(stripped) > 20 and set(stripped) == {"-"}


def parse_winget_output(output: str) -> list[Package]:
    """Parse 'winget upgrade' table output into Package objects.

    Locale-independent: column offsets come from the header row (tokens
    separated by runs of 2+ spaces — winget pads columns, while multi-word
    localized headers use single spaces). Column order is always
    Name, Id, Version, Available, Source regardless of language.
    """
    lines = [clean_line(line) for line in output.splitlines()]
    packages: list[Package] = []

    separator_indices = [
        i for i, line in enumerate(lines) if i > 0 and _is_separator(line)
    ]

    # The sentence introducing the explicit-targeting (pinned) table is
    # localized; the English check is a best effort. Structurally, any
    # table after the first one is the pinned table.
    explicit_marker = next(
        (i for i, line in enumerate(lines) if "require explicit targeting" in line.lower()),
        -1,
    )

    for section, sep_index in enumerate(separator_indices):
        header_line = lines[sep_index - 1]
        # Tokens joined by single spaces are one multi-word localized header
        # ("Versión disponible"); columns are separated by 2+ padding spaces.
        tokens = list(re.finditer(r"\S+(?: \S+)*", header_line))
        if len(tokens) < 5:
            # Tightly-packed table: fall back to plain word boundaries.
            tokens = list(re.finditer(r"\S+", header_line))
        if len(tokens) < 5:
            continue
        col_starts = [_display_column(header_line, m.start()) for m in tokens[:5]]
        name_col, id_col, version_col, available_col, source_col = col_starts

        pinned = section >= 1 or (explicit_marker != -1 and sep_index > explicit_marker)

        end = (
            separator_indices[section + 1] - 1
            if section + 1 < len(separator_indices)
            else len(lines)
        )
        for line in lines[sep_index + 1 : end]:
            if not line.strip():
                continue
            name = _slice_columns(line, name_col, id_col)
            pkg_id = _slice_columns(line, id_col, version_col)
            current = _slice_columns(line, version_col, available_col).lstrip("< ").strip()
            available = _slice_columns(line, available_col, source_col)
            source = _slice_columns(line, source_col)

            # Structural validation: drops localized summary sentences
            # ("2 upgrades available.", "N packages have version numbers
            # that cannot be determined") without matching English text.
            if not pkg_id or " " in pkg_id or not available:
                continue

            packages.append(
                Package(
                    name=name or pkg_id,
                    id=pkg_id,
                    current_version=current,
                    available_version=available,
                    source=source,
                    pinned=pinned,
                )
            )

    return packages


# ---------------------------------------------------------------------------
# Return-code interpretation
# ---------------------------------------------------------------------------

def interpret_return_code(returncode: int) -> tuple[bool, str, bool]:
    """Map a winget exit code to (success, reason, reboot_required)."""
    code = returncode & 0xFFFFFFFF
    if code == 0:
        return True, "Upgraded successfully", False
    if code in BENIGN_RETURN_CODES:
        return True, BENIGN_RETURN_CODES[code], False
    if code in REBOOT_RETURN_CODES:
        return True, REBOOT_RETURN_CODES[code], True
    if code in FAILURE_RETURN_CODES:
        return False, FAILURE_RETURN_CODES[code], False
    return False, f"winget exited with code 0x{code:08X}", False


def failure_hint(lines: list[str]) -> str:
    """Last meaningful output lines — shown when the exit code is unknown."""
    meaningful = [
        line.strip()
        for line in lines
        if line.strip() and not is_noise_line(line) and not _is_separator(line)
    ]
    return " · ".join(meaningful[-2:])[:300]


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

_SUBPROCESS_KWARGS = {
    "text": True,
    "encoding": "utf-8",
    "errors": "replace",
    "stdin": subprocess.DEVNULL,
    "creationflags": subprocess.CREATE_NO_WINDOW,
}


def get_upgradable_packages() -> ScanResult:
    """Run 'winget upgrade' and parse the output. Never raises."""
    cmd = ["winget", "upgrade", "--accept-source-agreements", "--disable-interactivity"]
    logger.info("Scanning: %s", " ".join(cmd))
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=SCAN_TIMEOUT_SECONDS,
            check=False,
            **_SUBPROCESS_KWARGS,
        )
    except FileNotFoundError:
        msg = (
            "winget is not installed or not on PATH. "
            "Install 'App Installer' from the Microsoft Store."
        )
        logger.error(msg)
        return ScanResult(error=msg)
    except subprocess.TimeoutExpired:
        msg = (
            f"winget did not respond within {SCAN_TIMEOUT_SECONDS} seconds. "
            "Check your network connection and winget sources."
        )
        logger.error(msg)
        return ScanResult(error=msg)
    except OSError as exc:
        msg = f"Could not run winget: {exc}"
        logger.error(msg)
        return ScanResult(error=msg)

    output = result.stdout or ""
    packages = parse_winget_output(output)
    code = result.returncode & 0xFFFFFFFF
    logger.info("Scan finished: code=0x%08X, %d packages", code, len(packages))

    error = None
    if not packages and code != 0 and code not in BENIGN_RETURN_CODES:
        error = interpret_return_code(code)[1]
    elif not packages and any(_is_separator(clean_line(line)) for line in output.splitlines()):
        error = (
            "winget listed updates but the output could not be parsed. "
            "Please open an issue with the contents of the output log."
        )
    return ScanResult(packages=packages, raw_output=output, error=error)


def _build_upgrade_command(package_id: str, pinned: bool) -> list[str]:
    cmd = [
        "winget",
        "upgrade",
        "--id",
        package_id,
        "--accept-package-agreements",
        "--accept-source-agreements",
        "--disable-interactivity",
    ]
    if pinned:
        cmd.append("--include-pinned")
    return cmd


def execute_upgrade(
    package: Package,
    output_callback: Callable[[str], None] | None = None,
) -> UpgradeResult:
    """Upgrade one package, blocking until done. Never raises."""
    cmd = _build_upgrade_command(package.id, package.pinned)
    logger.info("Upgrading %s: %s", package.id, " ".join(cmd))
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            **_SUBPROCESS_KWARGS,
        )
    except FileNotFoundError:
        return UpgradeResult(package.id, False, "winget is not installed or not on PATH")
    except OSError as exc:
        return UpgradeResult(package.id, False, f"Could not run winget: {exc}")

    lines: list[str] = []
    assert process.stdout is not None
    for raw_line in process.stdout:
        line = clean_line(raw_line)
        if is_noise_line(line):
            continue
        lines.append(line)
        if output_callback:
            output_callback(line)
    process.wait()

    success, reason, reboot = interpret_return_code(process.returncode)
    code = process.returncode & 0xFFFFFFFF
    if not success and (code not in FAILURE_RETURN_CODES or code in GENERIC_FAILURE_CODES):
        hint = failure_hint(lines)
        if hint:
            reason = f"{reason} — {hint}"
    logger.info("Upgrade %s: success=%s reason=%s", package.id, success, reason)
    return UpgradeResult(
        package_id=package.id,
        success=success,
        reason=reason,
        reboot_required=reboot,
        return_code=process.returncode,
    )


def upgrade_packages(
    packages: list[Package],
    output_callback: Callable[[str], None] | None = None,
    progress_callback: Callable[[int, int, Package], None] | None = None,
    package_complete_callback: Callable[[Package, UpgradeResult], None] | None = None,
    complete_callback: Callable[[int, int, bool], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> threading.Thread:
    """Upgrade packages sequentially on a worker thread.

    Cancellation is cooperative and safe: setting cancel_event lets the
    current package finish, then skips the rest (killing an installer
    mid-flight risks a corrupt install).

    Args:
        packages: Packages to upgrade, in order.
        output_callback: Called with each cleaned line of winget output.
        progress_callback: Called with (index_1based, total, package) as each starts.
        package_complete_callback: Called with (package, UpgradeResult) as each finishes.
        complete_callback: Called at the end with (success_count, fail_count, cancelled).
    """

    def run_all() -> None:
        success_count = 0
        fail_count = 0
        cancelled = False

        for i, pkg in enumerate(packages):
            if cancel_event is not None and cancel_event.is_set():
                cancelled = True
                break

            if progress_callback:
                progress_callback(i + 1, len(packages), pkg)
            if output_callback:
                output_callback("=" * 60)
                output_callback(f"Upgrading {pkg.name} ({i + 1}/{len(packages)})")
                output_callback("=" * 60)

            result = execute_upgrade(pkg, output_callback)
            if result.success:
                success_count += 1
            else:
                fail_count += 1
            if package_complete_callback:
                package_complete_callback(pkg, result)

        if complete_callback:
            complete_callback(success_count, fail_count, cancelled)

    thread = threading.Thread(target=run_all, daemon=True, name="winget-upgrade")
    thread.start()
    return thread
