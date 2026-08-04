"""Tests for process_guard: name matching, path safety, ancestor exclusion.

Detection tests use this test run's own process as the "running
application". Nothing is spawned or killed except in the explicitly
marked close test, which uses a throwaway child process.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

import process_guard
from process_guard import (
    RunningProcess,
    ancestor_pids,
    close_processes,
    display_name_matches,
    find_install_dirs,
    find_running_processes,
    is_safe_install_dir,
)


def _own_image_dir() -> Path:
    # sys.executable can be a venv redirector; detection sees the real image.
    return Path(process_guard._process_exe(os.getpid())).parent


# --------------------------------------------------------------------------
# Name matching
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "package,display",
    [
        ("Git", "Git"),
        ("git", "GIT"),
        ("Git", "Git version 2.53.0.2"),
        ("7-Zip", "7-Zip 24.08 (x64)"),
        ("Mozilla Firefox", "Mozilla Firefox (x64 en-US)"),
        ("Microsoft Teams", "Microsoft Teams"),
    ],
)
def test_display_name_accepts_same_product(package, display):
    assert display_name_matches(package, display)


@pytest.mark.parametrize(
    "package,display",
    [
        ("Git", "GitHub Desktop"),
        ("Git", "Gitea"),
        # Sibling products sharing a name prefix must NOT match — closing
        # them would kill an unrelated application.
        ("Microsoft Edge", "Microsoft Edge WebView2 Runtime"),
        ("Microsoft Edge", "Microsoft Edge Update"),
        ("Microsoft Teams", "Microsoft Teams Meeting Add-in for Office"),
        ("Python", "Python Launcher"),
        ("", "Git"),
        ("Git", ""),
    ],
)
def test_display_name_rejects_other_products(package, display):
    assert not display_name_matches(package, display)


# --------------------------------------------------------------------------
# Install-directory safety
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "path",
    [
        r"C:\Windows",
        r"C:\Windows\System32",
        r"C:\Windows\System32\drivers",
        r"C:\Program Files",
        r"C:\Program Files (x86)",
        r"C:\Program Files\Common Files",
        r"C:\ProgramData",
        r"C:\\",
        r"C:\Users",
    ],
)
def test_shared_and_system_roots_rejected(path):
    assert not is_safe_install_dir(Path(path))


def test_user_profile_and_appdata_roots_rejected():
    for var in ("USERPROFILE", "LOCALAPPDATA", "APPDATA"):
        value = os.environ.get(var)
        if value:
            assert not is_safe_install_dir(Path(value))
    local = os.environ.get("LOCALAPPDATA")
    if local:
        assert not is_safe_install_dir(Path(local) / "Programs")


@pytest.mark.parametrize(
    "path",
    [r"C:\Program Files\Git", r"C:\Program Files (x86)\Vendor\App"],
)
def test_real_install_dirs_accepted(path):
    assert is_safe_install_dir(Path(path))


def test_find_install_dirs_for_installed_app():
    dirs = find_install_dirs("Git")
    assert dirs, "expected at least one install dir for Git"
    assert all(d.is_dir() and is_safe_install_dir(d) for d in dirs)
    assert any("git" in d.name.lower() for d in dirs)


def test_find_install_dirs_unknown_app():
    assert find_install_dirs("Definitely Not A Real App 424242") == []


# --------------------------------------------------------------------------
# Process detection
# --------------------------------------------------------------------------

def test_detects_own_python_process():
    found = find_running_processes([_own_image_dir()], exclude_pids=set())
    assert any(p.pid == os.getpid() for p in found)
    me = next(p for p in found if p.pid == os.getpid())
    assert me.name.lower().startswith("python")


def test_own_pid_and_ancestors_excluded_by_default():
    found = find_running_processes([_own_image_dir()])
    excluded = ancestor_pids()
    assert all(p.pid not in excluded for p in found)
    assert all(p.pid != os.getpid() for p in found)


def test_ancestor_pids_includes_self_and_real_parent():
    chain = ancestor_pids()
    assert os.getpid() in chain
    # pytest is launched by a shell/python parent, so the chain must grow.
    assert len(chain) >= 2


def test_no_dirs_no_processes():
    assert find_running_processes([]) == []


def test_prefix_matching_does_not_cross_directories():
    sibling = Path(str(_own_image_dir()) + "XYZ")
    found = find_running_processes([sibling], exclude_pids=set())
    assert all(p.pid != os.getpid() for p in found)


# --------------------------------------------------------------------------
# Closing
# --------------------------------------------------------------------------

def test_close_refuses_protected_and_stale_pids():
    # Our own process is protected: close_processes must not touch it.
    me = RunningProcess(
        pid=os.getpid(), name="python.exe", exe=process_guard._process_exe(os.getpid())
    )
    assert close_processes([me]) == []
    assert os.getpid() in ancestor_pids()  # still alive


def test_close_skips_pid_whose_executable_changed():
    # Same PID, different recorded exe => identity check fails => no kill.
    stale = RunningProcess(pid=os.getpid(), name="other.exe", exe=r"C:\nope\other.exe")
    assert close_processes([stale], protected_pids=set()) == []


def test_close_terminates_a_real_child_process():
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(120)"],
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    try:
        time.sleep(0.5)
        exe = process_guard._process_exe(child.pid)
        assert exe, "child process should be inspectable"
        target = RunningProcess(pid=child.pid, name=Path(exe).name, exe=exe)
        remaining = close_processes([target], grace_seconds=1.0, protected_pids=set())
        assert remaining == []
        assert child.poll() is not None or child.wait(timeout=5) is not None
    finally:
        if child.poll() is None:
            child.kill()
