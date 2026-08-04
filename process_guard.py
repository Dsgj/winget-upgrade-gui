"""Detect and close running applications before upgrading them.

Maps a winget package to its install folder(s) via the Windows uninstall
registry, finds running processes whose executables live under those
folders, and can close them — gracefully first, forcefully only for
whatever survives. Pure stdlib (winreg + ctypes + taskkill).

Safety rules, in order of importance:
  * Never touch our own process or any of its ancestors — upgrading the
    terminal that launched this app must not kill the app.
  * Never accept a "shared root" install directory (Windows, Program
    Files itself, the user profile, AppData, …); prefix-matching such a
    directory would sweep in unrelated or system processes.
  * Never kill a PID whose executable no longer matches what was
    detected — Windows reuses PIDs, and the prompt may sit for minutes.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import logging
import os
import re
import subprocess
import time
import winreg
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_UNINSTALL_KEYS = [
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    (
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
    ),
    (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
]

_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_TH32CS_SNAPPROCESS = 0x00000002

# A DisplayName may carry a version and/or a parenthesised qualifier after
# the package name ("Git version 2.53.0.2", "Mozilla Firefox (x64 en-US)")
# but nothing else — otherwise "Microsoft Edge" would match "Microsoft Edge
# WebView2 Runtime" and close an unrelated product.
_NAME_SUFFIX_RE = re.compile(
    r"^(?:version\s+)?(?:v?\d[\w.\-+]*)?\s*(?:\([^)]*\)\s*)*$", re.IGNORECASE
)

_kernel32 = ctypes.windll.kernel32
_psapi = ctypes.windll.psapi


class _PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_wchar * 260),
    ]


@dataclass(frozen=True)
class RunningProcess:
    pid: int
    name: str
    exe: str


# ---------------------------------------------------------------------------
# Name matching
# ---------------------------------------------------------------------------

def display_name_matches(package_name: str, display_name: str) -> bool:
    """True if a registry DisplayName denotes the given package.

    'Git' matches 'Git' and 'Git version 2.53' but not 'GitHub Desktop';
    'Microsoft Edge' does not match 'Microsoft Edge WebView2 Runtime'.
    """
    package_name = package_name.strip().lower()
    display_name = display_name.strip().lower()
    if not package_name or not display_name:
        return False
    if display_name == package_name:
        return True
    if not display_name.startswith(package_name + " "):
        return False
    return bool(_NAME_SUFFIX_RE.match(display_name[len(package_name) :].strip()))


# ---------------------------------------------------------------------------
# Install directories
# ---------------------------------------------------------------------------

def _shared_roots() -> set[str]:
    """Directories too broad to prefix-match against running processes."""
    candidates = [
        os.environ.get("SystemRoot", r"C:\Windows"),
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        os.environ.get("ProgramW6432", r"C:\Program Files"),
        os.environ.get("ProgramData", r"C:\ProgramData"),
        os.environ.get("PUBLIC", r"C:\Users\Public"),
        os.environ.get("USERPROFILE", ""),
        os.environ.get("LOCALAPPDATA", ""),
        os.environ.get("APPDATA", ""),
    ]
    roots = {os.path.normcase(c.rstrip("\\/")) for c in candidates if c}
    for base in (os.environ.get("LOCALAPPDATA"), os.environ.get("APPDATA")):
        if base:
            roots.add(os.path.normcase(str(Path(base) / "Programs")))
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
        if base:
            roots.add(os.path.normcase(str(Path(base) / "Common Files")))
    return roots


def is_safe_install_dir(directory: Path) -> bool:
    """Reject drive roots, the Windows tree, and shared application roots."""
    try:
        normalized = os.path.normcase(str(directory.resolve()).rstrip("\\/"))
    except OSError:
        return False
    if len(Path(normalized).parts) < 3:
        return False
    if normalized in _shared_roots():
        return False
    windows_dir = os.path.normcase(os.environ.get("SystemRoot", r"C:\Windows"))
    return not (normalized + os.sep).startswith(windows_dir + os.sep)


def _dir_from_registry_value(value: str) -> Path | None:
    """Extract a plausible install directory from an exe-path-like value."""
    value = value.strip().strip('"').split(",")[0].strip().strip('"')
    if not value.lower().endswith(".exe"):
        return None
    return Path(value).parent


def find_install_dirs(package_name: str) -> list[Path]:
    """Install folders for a package, from the uninstall registry keys."""
    dirs: list[Path] = []
    for hive, key_path in _UNINSTALL_KEYS:
        try:
            key = winreg.OpenKey(hive, key_path)
        except OSError:
            continue
        with key:
            for i in range(winreg.QueryInfoKey(key)[0]):
                try:
                    with winreg.OpenKey(key, winreg.EnumKey(key, i)) as subkey:

                        def value(name: str) -> str:
                            try:
                                data = winreg.QueryValueEx(subkey, name)[0]
                                return data if isinstance(data, str) else ""
                            except OSError:
                                return ""

                        if not display_name_matches(package_name, value("DisplayName")):
                            continue

                        candidates: list[Path | None] = []
                        location = value("InstallLocation").strip().strip('"')
                        if location:
                            candidates.append(Path(location))
                        candidates.append(_dir_from_registry_value(value("DisplayIcon")))
                        uninstall = value("UninstallString")
                        if "msiexec" not in uninstall.lower():
                            candidates.append(_dir_from_registry_value(uninstall))

                        for directory in candidates:
                            if (
                                directory
                                and directory not in dirs
                                and is_safe_install_dir(directory)
                                and directory.is_dir()
                            ):
                                dirs.append(directory)
                except OSError:
                    continue
    logger.info("Install dirs for %r: %s", package_name, [str(d) for d in dirs])
    return dirs


# ---------------------------------------------------------------------------
# Process inspection
# ---------------------------------------------------------------------------

def _process_exe(pid: int) -> str | None:
    handle = _kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(buffer))
        if _kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return buffer.value
        return None
    finally:
        _kernel32.CloseHandle(handle)


def _parent_map() -> dict[int, int]:
    """pid -> parent pid, from a process snapshot."""
    snapshot = _kernel32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
    if snapshot == -1:
        return {}
    parents: dict[int, int] = {}
    try:
        entry = _PROCESSENTRY32()
        entry.dwSize = ctypes.sizeof(_PROCESSENTRY32)
        if _kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            while True:
                parents[entry.th32ProcessID] = entry.th32ParentProcessID
                if not _kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                    break
    finally:
        _kernel32.CloseHandle(snapshot)
    return parents


def _creation_time(pid: int) -> int | None:
    handle = _kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        creation = wintypes.FILETIME()
        exit_time = wintypes.FILETIME()
        kernel = wintypes.FILETIME()
        user = wintypes.FILETIME()
        if _kernel32.GetProcessTimes(
            handle,
            ctypes.byref(creation),
            ctypes.byref(exit_time),
            ctypes.byref(kernel),
            ctypes.byref(user),
        ):
            return (creation.dwHighDateTime << 32) | creation.dwLowDateTime
        return None
    finally:
        _kernel32.CloseHandle(handle)


def ancestor_pids(pid: int | None = None) -> set[int]:
    """Our own PID plus every ancestor, so we never close our own host.

    A parent PID only counts if it started before its child — Windows
    reuses PIDs, and a recycled PID is not a real ancestor.
    """
    if pid is None:
        pid = os.getpid()
    parents = _parent_map()
    chain = {pid}
    current = pid
    for _ in range(64):  # depth guard against cycles from PID reuse
        parent = parents.get(current)
        if not parent or parent in chain:
            break
        child_start = _creation_time(current)
        parent_start = _creation_time(parent)
        if child_start is None or parent_start is None or parent_start > child_start:
            break
        chain.add(parent)
        current = parent
    return chain


def find_running_processes(
    directories: list[Path], exclude_pids: set[int] | None = None
) -> list[RunningProcess]:
    """Processes whose executable lives under any of the given directories.

    Our own process and its ancestors are excluded by default.
    """
    if not directories:
        return []
    if exclude_pids is None:
        exclude_pids = ancestor_pids()
    prefixes = [os.path.normcase(str(d)) + os.sep for d in directories]

    found: list[RunningProcess] = []
    for pid in _parent_map():
        if pid in exclude_pids or pid == 0:
            continue
        exe = _process_exe(pid)
        if not exe:
            continue
        normalized = os.path.normcase(exe)
        if any(normalized.startswith(prefix) for prefix in prefixes):
            found.append(RunningProcess(pid=pid, name=Path(exe).name, exe=exe))
    return found


# ---------------------------------------------------------------------------
# Closing
# ---------------------------------------------------------------------------

def _taskkill(args: list[str]) -> None:
    subprocess.run(
        ["taskkill", *args],
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
        check=False,
    )


def _identity_holds(process: RunningProcess) -> bool:
    """True while the PID still runs the executable we detected."""
    exe = _process_exe(process.pid)
    return exe is not None and os.path.normcase(exe) == os.path.normcase(process.exe)


def _still_running(processes: list[RunningProcess]) -> list[RunningProcess]:
    return [p for p in processes if _identity_holds(p)]


def close_processes(
    processes: list[RunningProcess],
    grace_seconds: float = 5.0,
    protected_pids: set[int] | None = None,
) -> list[RunningProcess]:
    """Close processes gracefully, then force-kill survivors.

    Only PIDs still running their originally detected executable are
    touched, so a recycled PID is never killed. Returns the processes
    still running afterwards (empty means everything closed).
    """
    if protected_pids is None:
        protected_pids = ancestor_pids()
    targets = [
        p for p in processes if p.pid not in protected_pids and _identity_holds(p)
    ]
    if not targets:
        return []
    logger.info("Closing processes: %s", [(p.pid, p.name) for p in targets])

    # Graceful: taskkill without /F posts WM_CLOSE to the app's windows.
    for process in targets:
        _taskkill(["/PID", str(process.pid)])

    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline:
        if not _still_running(targets):
            return []
        time.sleep(0.4)

    # Force survivors. No /T: descendants may belong to other applications.
    for process in _still_running(targets):
        _taskkill(["/F", "/PID", str(process.pid)])
    time.sleep(0.6)

    remaining = _still_running(targets)
    if remaining:
        logger.warning("Could not close: %s", [(p.pid, p.name) for p in remaining])
    return remaining
