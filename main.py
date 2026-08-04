"""
Winget Upgrade GUI
A modern desktop application for managing Windows package upgrades via winget.
"""

from __future__ import annotations

import ctypes
import logging
import re
import sys
import threading
import time
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

import config
import process_guard
from ui_components import (
    SUCCESS_COLORS,
    SUCCESS_HOVER,
    ConfirmDialog,
    OutputConsole,
    PackageListFrame,
    StatusBar,
)
from version import __version__
from winget_runner import (
    Package,
    ScanResult,
    UpgradeResult,
    get_upgradable_packages,
    upgrade_packages,
)

logger = logging.getLogger(__name__)

APPEARANCE_OPTIONS = ["System", "Light", "Dark"]

# How long an unanswered "close the running app?" prompt blocks a batch.
PROMPT_TIMEOUT_SECONDS = 300

# Accepts decimal commas — winget localizes numbers (e.g. "4,5 MB" on Swedish).
_PROGRESS_RE = re.compile(r"([\d.,]+)\s*(KB|MB|GB)\s*/\s*([\d.,]+)\s*(KB|MB|GB)")
_UNIT_KB = {"KB": 1, "MB": 1024, "GB": 1024 * 1024}


def _to_float(number: str) -> float:
    return float(number.replace(",", "."))


def resource_path(name: str) -> Path:
    """Path to a bundled resource, both from source and PyInstaller-frozen."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    return base / name


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


class WingetUpgradeApp(ctk.CTk):
    """Main application window."""

    def __init__(self):
        super().__init__()

        self.config_data = config.load_config()

        self.title(f"Winget Upgrade Manager  v{__version__}")
        self.geometry("980x760")
        self.minsize(720, 520)
        try:
            self.iconbitmap(str(resource_path("assets/icon.ico")))
        except Exception:
            pass  # icon is cosmetic; never block startup on it

        appearance = str(self.config_data.get("appearance", "dark")).capitalize()
        if appearance not in APPEARANCE_OPTIONS:
            appearance = "Dark"
        ctk.set_appearance_mode(appearance.lower())
        ctk.set_default_color_theme("blue")

        # State. busy is None or one of "refresh" / "upgrade".
        self.packages: list[Package] = []
        self.busy: str | None = None
        self.cancel_event = threading.Event()
        self.current_upgrade_card = None
        self._download_active = False

        self._create_ui(appearance)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.after(300, self.refresh_packages)

    # ------------------------------------------------------------------ UI

    def _create_ui(self, appearance: str):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # ========== Header ==========
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))
        header_frame.grid_columnconfigure(1, weight=1)

        title_label = ctk.CTkLabel(
            header_frame,
            text="📦 Winget Upgrade Manager",
            font=ctk.CTkFont(size=24, weight="bold"),
        )
        title_label.grid(row=0, column=0, sticky="w")

        self.count_label = ctk.CTkLabel(
            header_frame,
            text="",
            font=ctk.CTkFont(size=13),
            text_color=("gray40", "gray60"),
        )
        self.count_label.grid(row=0, column=1, sticky="w", padx=(15, 0))

        self.appearance_control = ctk.CTkSegmentedButton(
            header_frame,
            values=APPEARANCE_OPTIONS,
            width=180,
            height=28,
            font=ctk.CTkFont(size=11),
            command=self._on_appearance_change,
        )
        self.appearance_control.set(appearance)
        self.appearance_control.grid(row=0, column=2, sticky="e", padx=(0, 12))

        self.refresh_button = ctk.CTkButton(
            header_frame, text="🔄 Refresh", width=100, command=self.refresh_packages
        )
        self.refresh_button.grid(row=0, column=3, sticky="e")

        # ========== Action Bar ==========
        action_frame = ctk.CTkFrame(self, fg_color="transparent")
        action_frame.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 10))
        action_frame.grid_columnconfigure(2, weight=1)

        self.select_all_var = ctk.BooleanVar(value=True)
        self.select_all_checkbox = ctk.CTkCheckBox(
            action_frame,
            text="Select all",
            font=ctk.CTkFont(size=12),
            variable=self.select_all_var,
            command=self._on_select_all,
        )
        self.select_all_checkbox.grid(row=0, column=0, sticky="w", padx=(4, 16))

        self.upgrade_button = ctk.CTkButton(
            action_frame,
            text="⬆️ Upgrade Selected",
            width=180,
            height=38,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=SUCCESS_COLORS,
            hover_color=SUCCESS_HOVER,
            command=self.upgrade_selected,
        )
        self.upgrade_button.grid(row=0, column=1, sticky="w")

        self.cancel_button = ctk.CTkButton(
            action_frame,
            text="✕ Cancel",
            width=90,
            height=38,
            fg_color="transparent",
            border_width=1,
            border_color=("#C0392B", "#E74C3C"),
            text_color=("#C0392B", "#E74C3C"),
            hover_color=("gray85", "gray25"),
            command=self._on_cancel,
        )
        self.cancel_button.grid(row=0, column=2, sticky="w", padx=(12, 0))
        self.cancel_button.grid_remove()

        self.progress_bar = ctk.CTkProgressBar(action_frame, width=200)
        self.progress_bar.grid(row=0, column=3, sticky="e", padx=(20, 0))
        self.progress_bar.set(0)
        self.progress_bar.grid_remove()

        # ========== Main Content ==========
        content_frame = ctk.CTkFrame(self, fg_color="transparent")
        content_frame.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 10))
        content_frame.grid_columnconfigure(0, weight=1)
        content_frame.grid_rowconfigure(0, weight=3)
        content_frame.grid_rowconfigure(1, weight=1)

        list_container = ctk.CTkFrame(content_frame, corner_radius=10)
        list_container.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        list_container.grid_columnconfigure(0, weight=1)
        list_container.grid_rowconfigure(0, weight=1)

        self.package_list = PackageListFrame(
            list_container,
            on_upgrade=self.upgrade_single,
            on_toggle=self._on_package_toggle,
            corner_radius=10,
        )
        self.package_list.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)

        self.output_console = OutputConsole(content_frame, height=180)
        self.output_console.grid(row=1, column=0, sticky="nsew")

        # ========== Status Bar ==========
        self.status_bar = StatusBar(self)
        self.status_bar.grid(row=3, column=0, sticky="ew")
        if is_admin():
            self.status_bar.set_meta("🛡️ Administrator")

    # ------------------------------------------------------- busy handling

    def _set_busy(self, mode: str):
        self.busy = mode
        self.refresh_button.configure(state="disabled")
        self.upgrade_button.configure(state="disabled")
        self.select_all_checkbox.configure(state="disabled")
        self.package_list.set_all_enabled(False)

    def _clear_busy(self):
        self.busy = None
        self.refresh_button.configure(state="normal", text="🔄 Refresh")
        self.select_all_checkbox.configure(state="normal")
        self.package_list.set_all_enabled(True)
        self._update_selection_ui()

    def _update_selection_ui(self):
        """Sync the Upgrade Selected button and count label with reality."""
        selected = len(self.package_list.selected_packages())
        total = len(self.packages)
        if total == 0:
            self.upgrade_button.configure(
                text="⬆️ Upgrade Selected", state="disabled", fg_color=SUCCESS_COLORS
            )
            self.count_label.configure(text="All up to date")
        else:
            self.upgrade_button.configure(
                text=f"⬆️ Upgrade Selected ({selected})",
                state="normal" if selected and self.busy is None else "disabled",
                fg_color=SUCCESS_COLORS,
            )
            self.count_label.configure(
                text=f"{total} update{'s' if total != 1 else ''} available"
            )

    # ------------------------------------------------------------- refresh

    def refresh_packages(self):
        if self.busy is not None:
            return

        self._set_busy("refresh")
        self.refresh_button.configure(text="Refreshing…")
        self.status_bar.set_status("Scanning for updates…")
        self.package_list.show_message("🔍 Scanning for updates…\nThis can take a minute.")
        self.output_console.append("Running: winget upgrade")

        def do_refresh():
            result = get_upgradable_packages()
            self.after(0, lambda: self._on_refresh_complete(result))

        threading.Thread(target=do_refresh, daemon=True, name="winget-scan").start()

    def _on_refresh_complete(self, result: ScanResult):
        self._clear_busy()
        self.output_console.append(result.raw_output)
        self.status_bar.set_progress(f"🕒 Checked {time.strftime('%H:%M')}")

        if result.error:
            self.packages = []
            self.package_list.show_message(f"⚠️ {result.error}", kind="error")
            self.count_label.configure(text="")
            self.status_bar.set_status("Scan failed")
            self.upgrade_button.configure(state="disabled")
            self.output_console.append(f"\n⚠️ {result.error}\n")
            return

        # Pinned packages are shown but deselected by default: winget can
        # upgrade them with --include-pinned, but the pin usually exists
        # for a reason (self-updating apps, held versions).
        self.packages = sorted(result.packages, key=lambda p: p.name.lower())
        skipped = set(self.config_data.get("skipped_ids", []))
        selected_ids = {
            p.id for p in self.packages if p.id not in skipped and not p.pinned
        }

        if self.packages:
            self.package_list.set_packages(self.packages, selected_ids=selected_ids)
            self.status_bar.set_status(
                f"Found {len(self.packages)} package(s) with updates"
            )
            pinned_count = sum(p.pinned for p in self.packages)
            if pinned_count:
                self.output_console.append(
                    f"\n📌 {pinned_count} pinned package(s) require explicit targeting — "
                    "deselected by default."
                )
        else:
            self.package_list.show_message(
                "✓ All packages are up to date!", kind="success"
            )
            self.status_bar.set_status("All packages are up to date")

        self.select_all_var.set(len(selected_ids) == len(self.packages))
        self._update_selection_ui()
        self.output_console.append("=" * 50 + "\n")

    # ------------------------------------------------------------ upgrades

    def upgrade_single(self, package: Package):
        self._start_upgrades([package])

    def upgrade_selected(self):
        selection = self.package_list.selected_packages()
        if selection:
            self._start_upgrades(selection)

    def _start_upgrades(self, targets: list[Package]):
        if self.busy is not None:
            return

        self._set_busy("upgrade")
        self.cancel_event.clear()
        self.upgrade_button.configure(text="Upgrading…")
        self.current_upgrade_card = None
        batch = len(targets) > 1
        if batch:
            self.cancel_button.grid()
            self.progress_bar.grid()
            self.progress_bar.set(0)

        def on_output(line: str):
            self.after(0, lambda text=line: self._handle_output_line(text))

        def on_progress(current: int, total: int, pkg: Package):
            def update_ui():
                self.status_bar.set_status(f"Upgrading {pkg.name}…")
                if batch:
                    self.status_bar.set_progress(f"{current}/{total}")
                card = self.package_list.get_card(pkg.id)
                if card:
                    card.set_upgrading(True)
                    self.current_upgrade_card = card
                    self._download_active = False

            self.after(0, update_ui)

        def on_package_complete(pkg: Package, result: UpgradeResult):
            def update_ui():
                card = self.package_list.get_card(pkg.id)
                if card:
                    card.set_result(result)
                if self.current_upgrade_card is card:
                    self.current_upgrade_card = None
                if batch:
                    done = self.progress_bar.get() + 1 / len(targets)
                    self.progress_bar.set(min(done, 1.0))
                if result.success:
                    self.packages = [p for p in self.packages if p.id != pkg.id]
                    icon = "🔁" if result.reboot_required else "✓"
                else:
                    icon = "✗"
                self.output_console.append(f"\n{icon} {pkg.name}: {result.reason}\n")

            self.after(0, update_ui)

        def on_complete(success_count: int, fail_count: int, cancelled: bool):
            def update_ui():
                # A package cancelled during its preflight never reports a
                # result, so clear its half-started card state here.
                card = self.current_upgrade_card
                if card is not None and card.is_upgrading:
                    card.set_upgrading(False)
                self.current_upgrade_card = None
                self.cancel_button.grid_remove()
                self.cancel_button.configure(state="normal", text="✕ Cancel")
                self.progress_bar.grid_remove()
                self.status_bar.set_progress("")
                self._download_active = False
                self._clear_busy()

                parts = [f"{success_count} succeeded"]
                if fail_count:
                    parts.append(f"{fail_count} failed")
                if cancelled:
                    parts.append("cancelled before finishing")
                message = "Done: " + ", ".join(parts)
                self.status_bar.set_status(message)
                self.output_console.append("=" * 50)
                self.output_console.append(message)
                self.output_console.append("=" * 50 + "\n")
                if fail_count:
                    self.status_bar.set_status(
                        message + " — failure reasons are shown on each package"
                    )

            self.after(0, update_ui)

        upgrade_packages(
            targets,
            output_callback=on_output,
            progress_callback=on_progress,
            package_complete_callback=on_package_complete,
            complete_callback=on_complete,
            cancel_event=self.cancel_event,
            preflight_callback=self._preflight_close_running,
        )

    def _log_async(self, message: str):
        """Append to the console from a worker thread."""
        self.after(0, lambda: self.output_console.append(message))

    def _preflight_close_running(self, package: Package):
        """Runs on the worker thread before each upgrade: if the app has
        running processes, ask the user (on the UI thread) whether to close
        them so the installer can replace its files.

        Never raises — a failed check just means we upgrade as before.
        """
        if self.cancel_event.is_set():
            return
        try:
            install_dirs = process_guard.find_install_dirs(package.name)
            processes = process_guard.find_running_processes(install_dirs)
        except Exception:
            logger.exception("Process check failed for %s", package.id)
            return
        if not processes or self.cancel_event.is_set():
            return

        names = sorted({p.name for p in processes})
        self._log_async(f"⚠️ {package.name} is running: {', '.join(names)}")

        answered = threading.Event()
        answer = {"close": False}
        dialog_ref: dict[str, object] = {}

        def ask():
            def on_answer(value: bool):
                answer["close"] = value
                answered.set()

            try:
                dialog_ref["dialog"] = ConfirmDialog(
                    self,
                    "Application is running",
                    f"{package.name} appears to be running:\n\n"
                    + "\n".join(f"    •  {name}" for name in names)
                    + "\n\nClose it so the upgrade can proceed?\n"
                    "Choosing No upgrades anyway, which may fail on locked files.",
                    on_answer,
                )
            except Exception:
                logger.exception("Could not show the close-app prompt")
                answered.set()

        self.after(0, ask)

        # Wait in slices so a Cancel click doesn't leave the batch parked on
        # an unanswered prompt; never wedge the worker indefinitely either.
        deadline = time.monotonic() + PROMPT_TIMEOUT_SECONDS
        while not answered.wait(timeout=0.25):
            if self.cancel_event.is_set() or time.monotonic() > deadline:
                break

        if not answered.is_set():
            def dismiss():
                dialog = dialog_ref.get("dialog")
                if dialog is not None:
                    dialog.dismiss()

            self.after(0, dismiss)
            self._log_async(
                "Prompt dismissed — "
                + ("upgrade cancelled." if self.cancel_event.is_set() else "upgrading anyway.")
            )
            return

        if not answer["close"] or self.cancel_event.is_set():
            return

        self._log_async(f"Closing {', '.join(names)}…")
        try:
            remaining = process_guard.close_processes(processes)
        except Exception:
            logger.exception("Closing processes failed for %s", package.id)
            return

        if remaining:
            still = ", ".join(sorted({p.name for p in remaining}))
            self._log_async(f"⚠️ Could not close: {still} — the upgrade may fail.")
        else:
            self._log_async(f"Closed {', '.join(names)}.")

    def _on_cancel(self):
        self.cancel_event.set()
        self.cancel_button.configure(state="disabled", text="Finishing current…")
        self.status_bar.set_status(
            "Cancelling — the package currently upgrading will finish first"
        )

    def _handle_output_line(self, line: str):
        """Append output and update the active card's progress display."""
        self.output_console.append(line)

        card = self.current_upgrade_card
        if not card or not card.is_upgrading:
            return
        try:
            # Only the download phase reports sizes; everything else is shown
            # as an animated bar. No English keywords — winget output is
            # localized to the Windows display language.
            match = _PROGRESS_RE.search(line)
            if match:
                current_kb = _to_float(match.group(1)) * _UNIT_KB.get(match.group(2), 1)
                total_kb = _to_float(match.group(3)) * _UNIT_KB.get(match.group(4), 1)
                if total_kb > 0:
                    progress = min(current_kb / total_kb, 1.0)
                    status = (
                        f"Downloading: {match.group(1)} {match.group(2)}"
                        f" / {match.group(3)} {match.group(4)}"
                    )
                    card.update_progress(progress, status)
                    self._download_active = True
            elif self._download_active:
                self._download_active = False
                card.set_indeterminate("Installing…")
        except Exception:
            # A destroyed widget or malformed line must never kill the UI loop.
            logger.exception("Progress update failed")

    # ------------------------------------------------------------- events

    def _on_package_toggle(self, package: Package, selected: bool):
        skipped = set(self.config_data.get("skipped_ids", []))
        if selected:
            skipped.discard(package.id)
        else:
            skipped.add(package.id)
        self.config_data["skipped_ids"] = sorted(skipped)
        config.save_config(self.config_data)
        # Sync the header checkbox; programmatic set() does not re-fire handlers.
        pending = [
            c
            for c in self.package_list.package_cards.values()
            if c.result_state != "success"
        ]
        self.select_all_var.set(bool(pending) and all(c.selected for c in pending))
        self._update_selection_ui()

    def _on_select_all(self):
        self.package_list.set_all_selected(self.select_all_var.get())
        # set_all_selected() bypasses per-card handlers, so persist the skip
        # list here — only for packages currently shown, preserving the rest.
        skipped = set(self.config_data.get("skipped_ids", []))
        for pkg_id, card in self.package_list.package_cards.items():
            if card.result_state == "success":
                continue
            if card.selected:
                skipped.discard(pkg_id)
            else:
                skipped.add(pkg_id)
        self.config_data["skipped_ids"] = sorted(skipped)
        config.save_config(self.config_data)
        self._update_selection_ui()

    def _on_appearance_change(self, value: str):
        ctk.set_appearance_mode(value.lower())
        self.config_data["appearance"] = value.lower()
        config.save_config(self.config_data)

    def _on_close(self):
        if self.busy == "upgrade":
            if not messagebox.askyesno(
                "Upgrade in progress",
                "An upgrade is still running. Quitting now may leave it "
                "half-finished.\n\nQuit anyway?",
            ):
                return
            self.cancel_event.set()
        self.destroy()


def main():
    config.setup_logging()
    logger.info("Starting Winget Upgrade Manager v%s", __version__)
    app = WingetUpgradeApp()
    app.mainloop()


if __name__ == "__main__":
    main()
