"""
Winget Upgrade GUI
A modern desktop application for managing Windows package upgrades via winget.
"""

import customtkinter as ctk
import threading
from typing import List

from winget_runner import (
    Package,
    get_upgradable_packages,
    upgrade_package,
    upgrade_all_packages,
)
from ui_components import PackageListFrame, OutputConsole, StatusBar


class WingetUpgradeApp(ctk.CTk):
    """Main application window."""

    def __init__(self):
        super().__init__()

        # Window configuration
        self.title("Winget Upgrade Manager")
        self.geometry("950x750")
        self.minsize(700, 500)

        # Set appearance
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # State
        self.packages: List[Package] = []
        self.is_refreshing = False
        self.is_upgrading_all = False

        # Build UI
        self._create_ui()

        # Initial refresh
        self.after(500, self.refresh_packages)

    def _create_ui(self):
        """Create the main UI layout."""
        # Configure grid
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self.grid_rowconfigure(3, weight=0)

        # ========== Header Section ==========
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))
        header_frame.grid_columnconfigure(1, weight=1)

        # Title
        title_label = ctk.CTkLabel(
            header_frame,
            text="📦 Winget Upgrade Manager",
            font=ctk.CTkFont(size=24, weight="bold"),
        )
        title_label.grid(row=0, column=0, sticky="w")

        # Package count
        self.count_label = ctk.CTkLabel(
            header_frame,
            text="",
            font=ctk.CTkFont(size=13),
            text_color=("gray40", "gray60"),
        )
        self.count_label.grid(row=0, column=1, sticky="w", padx=(15, 0))

        # Refresh button
        self.refresh_button = ctk.CTkButton(
            header_frame, text="🔄 Refresh", width=100, command=self.refresh_packages
        )
        self.refresh_button.grid(row=0, column=2, sticky="e")

        # ========== Action Bar ==========
        action_frame = ctk.CTkFrame(self, fg_color="transparent")
        action_frame.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 10))
        action_frame.grid_columnconfigure(0, weight=1)

        # Upgrade All button
        self.upgrade_all_button = ctk.CTkButton(
            action_frame,
            text="⬆️ Upgrade All",
            width=140,
            height=38,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=("#2ECC71", "#27AE60"),
            hover_color=("#27AE60", "#1E8449"),
            command=self.upgrade_all,
        )
        self.upgrade_all_button.grid(row=0, column=0, sticky="w")

        # Progress bar (hidden by default)
        self.progress_bar = ctk.CTkProgressBar(action_frame, width=200)
        self.progress_bar.grid(row=0, column=1, sticky="e", padx=(20, 0))
        self.progress_bar.set(0)
        self.progress_bar.grid_remove()

        # ========== Main Content Area ==========
        # Create a paned window for resizable split
        content_frame = ctk.CTkFrame(self, fg_color="transparent")
        content_frame.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 10))
        content_frame.grid_columnconfigure(0, weight=1)
        content_frame.grid_rowconfigure(0, weight=3)
        content_frame.grid_rowconfigure(1, weight=1)

        # Package list
        list_container = ctk.CTkFrame(content_frame, corner_radius=10)
        list_container.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        list_container.grid_columnconfigure(0, weight=1)
        list_container.grid_rowconfigure(0, weight=1)

        self.package_list = PackageListFrame(
            list_container, on_upgrade=self.upgrade_single, corner_radius=10
        )
        self.package_list.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)

        # Output console
        self.output_console = OutputConsole(content_frame, height=180)
        self.output_console.grid(row=1, column=0, sticky="nsew")

        # ========== Status Bar ==========
        self.status_bar = StatusBar(self)
        self.status_bar.grid(row=3, column=0, sticky="ew")

    def refresh_packages(self):
        """Refresh the list of upgradable packages."""
        if self.is_refreshing:
            return

        self.is_refreshing = True
        self.refresh_button.configure(state="disabled", text="Refreshing...")
        self.status_bar.set_status("Scanning for updates...")
        self.output_console.append("Running winget upgrade...")

        def do_refresh():
            packages, output = get_upgradable_packages()

            # Update UI on main thread
            self.after(0, lambda: self._on_refresh_complete(packages, output))

        thread = threading.Thread(target=do_refresh, daemon=True)
        thread.start()

    def _on_refresh_complete(self, packages: List[Package], output: str):
        """Handle refresh completion."""
        # Filter out pinned packages (they often can't be upgraded via winget)
        pinned_packages = [p for p in packages if p.pinned]
        regular_packages = [p for p in packages if not p.pinned]

        self.packages = regular_packages
        self.is_refreshing = False

        self.refresh_button.configure(state="normal", text="🔄 Refresh")

        if regular_packages:
            self.package_list.set_packages(regular_packages)
            self.count_label.configure(
                text=f"{len(regular_packages)} updates available"
            )
            self.status_bar.set_status(
                f"Found {len(regular_packages)} packages to upgrade"
            )
            self.upgrade_all_button.configure(state="normal")
        else:
            self.package_list.show_empty_message("✓ All packages are up to date!")
            self.count_label.configure(text="All up to date")
            self.status_bar.set_status("All packages are up to date")
            self.upgrade_all_button.configure(state="disabled")

        self.output_console.append(output)

        # Log info about excluded pinned packages
        if pinned_packages:
            pinned_names = ", ".join(p.name for p in pinned_packages)
            self.output_console.append(
                f"\n⚠️ Excluded {len(pinned_packages)} pinned package(s) that require manual upgrade: {pinned_names}"
            )

        self.output_console.append("\n" + "=" * 50 + "\n")

    def upgrade_single(self, package: Package):
        """Upgrade a single package."""
        card = self.package_list.get_card(package.id)
        if card:
            card.set_upgrading(True)

        self.status_bar.set_status(f"Upgrading {package.name}...")
        self.output_console.append(f"\n{'=' * 50}")
        self.output_console.append(f"Upgrading: {package.name}")
        self.output_console.append(f"{'=' * 50}\n")

        def on_output(line: str):
            self.after(
                0, lambda line_text=line: self._handle_output_line(line_text, card)
            )

        def on_complete(success: bool, message: str):
            def update_ui():
                if card:
                    card.set_complete(success)
                self.output_console.append(f"\n{message}")
                self.status_bar.set_status(message)

                # Remove from packages list if successful
                if success:
                    self.packages = [p for p in self.packages if p.id != package.id]
                    self.count_label.configure(
                        text=f"{len(self.packages)} updates available"
                        if self.packages
                        else "All up to date"
                    )

            self.after(0, update_ui)

        upgrade_package(package.id, on_output, on_complete, pinned=package.pinned)

    def _handle_output_line(self, line: str, card):
        """Parse output line and update progress if applicable."""
        self.output_console.append(line)

        if card and card.is_upgrading:
            # Parse progress from winget output
            # Example: "  ██████████████████████████████  4.54 MB / 4.54 MB"
            import re

            # Download progress pattern
            progress_match = re.search(
                r"([\d.]+)\s*(KB|MB|GB)\s*/\s*([\d.]+)\s*(KB|MB|GB)", line
            )
            if progress_match:
                current = float(progress_match.group(1))
                current_unit = progress_match.group(2)
                total = float(progress_match.group(3))
                total_unit = progress_match.group(4)

                # Convert to same unit for comparison
                unit_multipliers = {"KB": 1, "MB": 1024, "GB": 1024 * 1024}
                current_kb = current * unit_multipliers.get(current_unit, 1)
                total_kb = total * unit_multipliers.get(total_unit, 1)

                if total_kb > 0:
                    progress = min(current_kb / total_kb, 1.0)
                    status = f"Downloading: {progress_match.group(1)} {current_unit} / {progress_match.group(3)} {total_unit}"
                    self.after(
                        0, lambda p=progress, s=status: card.update_progress(p, s)
                    )

            # Check for install phase
            elif "Starting package install" in line or "Installing" in line:
                self.after(0, lambda: card.update_progress(0.5, "Installing..."))
            elif "verif" in line.lower():
                self.after(0, lambda: card.update_progress(0.3, "Verifying hash..."))
            elif "Successfully installed" in line:
                self.after(0, lambda: card.update_progress(1.0, "Complete!"))

    def upgrade_all(self):
        """Upgrade all packages."""
        if not self.packages or self.is_upgrading_all:
            return

        self.is_upgrading_all = True
        self.upgrade_all_button.configure(state="disabled", text="Upgrading...")
        self.refresh_button.configure(state="disabled")
        self.progress_bar.grid()
        self.progress_bar.set(0)

        packages_to_upgrade = self.packages.copy()
        self.current_upgrade_card = None

        def on_output(line: str):
            self.after(
                0,
                lambda line_text=line: self._handle_output_line(
                    line_text, self.current_upgrade_card
                ),
            )

        def on_progress(current: int, total: int, name: str):
            def update_ui():
                progress = current / total
                self.progress_bar.set(progress)
                self.status_bar.set_status(f"Upgrading {name}...")
                self.status_bar.set_progress(f"{current}/{total}")

                # Update the card
                for pkg in packages_to_upgrade:
                    if pkg.name == name:
                        card = self.package_list.get_card(pkg.id)
                        if card:
                            card.set_upgrading(True)
                            self.current_upgrade_card = card
                        break

            self.after(0, update_ui)

        def on_complete(success_count: int, fail_count: int):
            def update_ui():
                self.is_upgrading_all = False
                self.current_upgrade_card = None
                self.progress_bar.grid_remove()
                self.refresh_button.configure(state="normal")

                # Update all cards
                for pkg in packages_to_upgrade:
                    card = self.package_list.get_card(pkg.id)
                    if card and card.is_upgrading:
                        card.set_complete(True)

                message = f"Complete: {success_count} succeeded, {fail_count} failed"
                self.status_bar.set_status(message)
                self.status_bar.set_progress("")
                self.output_console.append(f"\n{'=' * 50}")
                self.output_console.append(message)
                self.output_console.append(f"{'=' * 50}\n")

                if fail_count == 0:
                    self.upgrade_all_button.configure(
                        text="✓ All Done", fg_color=("#2ECC71", "#27AE60")
                    )
                    self.packages = []
                    self.count_label.configure(text="All up to date")
                else:
                    self.upgrade_all_button.configure(
                        text="⬆️ Retry Failed",
                        state="normal",
                        fg_color=("#E74C3C", "#C0392B"),
                    )
                    # Refresh to get remaining packages
                    self.after(1000, self.refresh_packages)

            self.after(0, update_ui)

        upgrade_all_packages(packages_to_upgrade, on_output, on_progress, on_complete)


def main():
    app = WingetUpgradeApp()
    app.mainloop()


if __name__ == "__main__":
    main()
