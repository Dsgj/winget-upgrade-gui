"""
Custom UI Components for Winget Upgrade GUI
Built on CustomTkinter for a modern, dark-themed appearance.
"""

import customtkinter as ctk
from typing import Callable, Optional
from winget_runner import Package


class PackageCard(ctk.CTkFrame):
    """A card displaying a single package with upgrade button and progress bar."""

    def __init__(
        self, parent, package: Package, on_upgrade: Callable[[Package], None], **kwargs
    ):
        super().__init__(parent, **kwargs)
        self.package = package
        self.on_upgrade = on_upgrade
        self.is_upgrading = False

        # Configure the frame
        self.configure(
            corner_radius=8,
            fg_color=("gray90", "gray17"),
            border_width=1,
            border_color=("gray70", "gray30"),
        )

        # Grid configuration
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)

        # Left side - Package info
        info_frame = ctk.CTkFrame(self, fg_color="transparent")
        info_frame.grid(row=0, column=0, sticky="nsew", padx=15, pady=12)
        info_frame.grid_columnconfigure(0, weight=1)

        # Package name (truncate if too long)
        display_name = (
            package.name[:50] + "..." if len(package.name) > 50 else package.name
        )
        self.name_label = ctk.CTkLabel(
            info_frame,
            text=display_name,
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        )
        self.name_label.grid(row=0, column=0, sticky="w")

        # Package ID
        self.id_label = ctk.CTkLabel(
            info_frame,
            text=package.id,
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray60"),
            anchor="w",
        )
        self.id_label.grid(row=1, column=0, sticky="w", pady=(2, 0))

        # Version info
        version_text = f"{package.current_version}  →  {package.available_version}"
        self.version_label = ctk.CTkLabel(
            info_frame,
            text=version_text,
            font=ctk.CTkFont(size=12),
            text_color=("gray30", "gray70"),
            anchor="w",
        )
        self.version_label.grid(row=2, column=0, sticky="w", pady=(4, 0))

        # Right side - Upgrade button
        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.grid(row=0, column=1, sticky="nse", padx=15, pady=12)

        self.upgrade_button = ctk.CTkButton(
            button_frame,
            text="Upgrade",
            width=100,
            height=36,
            font=ctk.CTkFont(size=13),
            command=self._on_upgrade_click,
        )
        self.upgrade_button.pack(anchor="center", expand=True)

        # Source label
        self.source_label = ctk.CTkLabel(
            button_frame,
            text=package.source,
            font=ctk.CTkFont(size=10),
            text_color=("gray50", "gray50"),
        )
        self.source_label.pack(anchor="center", pady=(4, 0))

        # Progress section (hidden by default)
        self.progress_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.progress_frame.grid(
            row=1, column=0, columnspan=2, sticky="ew", padx=15, pady=(0, 10)
        )
        self.progress_frame.grid_columnconfigure(0, weight=1)
        self.progress_frame.grid_remove()  # Hidden initially

        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(
            self.progress_frame,
            height=8,
            corner_radius=4,
            progress_color=("#3B8ED0", "#1F6AA5"),
        )
        self.progress_bar.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        self.progress_bar.set(0)

        # Progress status label
        self.progress_label = ctk.CTkLabel(
            self.progress_frame,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray60"),
            anchor="w",
        )
        self.progress_label.grid(row=1, column=0, sticky="w")

    def _on_upgrade_click(self):
        if not self.is_upgrading:
            self.on_upgrade(self.package)

    def set_upgrading(self, upgrading: bool):
        """Update the UI to show upgrading state."""
        self.is_upgrading = upgrading
        if upgrading:
            self.upgrade_button.configure(
                text="Upgrading...", state="disabled", fg_color=("gray60", "gray40")
            )
            self.progress_frame.grid()  # Show progress section
            self.progress_bar.set(0)
            self.progress_label.configure(text="Starting...")
        else:
            self.upgrade_button.configure(
                text="Upgrade",
                state="normal",
                fg_color=ctk.ThemeManager.theme["CTkButton"]["fg_color"],
            )
            self.progress_frame.grid_remove()  # Hide progress section

    def update_progress(self, progress: float, status: str):
        """Update the progress bar and status text."""
        self.progress_bar.set(progress)
        self.progress_label.configure(text=status)

        # Change color based on stage
        if "download" in status.lower():
            self.progress_bar.configure(progress_color=("#3B8ED0", "#1F6AA5"))
        elif "install" in status.lower():
            self.progress_bar.configure(progress_color=("#9B59B6", "#8E44AD"))
        elif "verify" in status.lower():
            self.progress_bar.configure(progress_color=("#F39C12", "#D68910"))

    def set_complete(self, success: bool):
        """Update the UI to show completion state."""
        self.is_upgrading = False
        self.progress_frame.grid_remove()  # Hide progress section

        if success:
            self.upgrade_button.configure(
                text="✓ Done", state="disabled", fg_color=("#2ECC71", "#27AE60")
            )
        else:
            self.upgrade_button.configure(
                text="✗ Failed", state="normal", fg_color=("#E74C3C", "#C0392B")
            )


class PackageListFrame(ctk.CTkScrollableFrame):
    """Scrollable frame containing package cards."""

    def __init__(self, parent, on_upgrade: Callable[[Package], None], **kwargs):
        super().__init__(parent, **kwargs)
        self.on_upgrade = on_upgrade
        self.package_cards: dict[str, PackageCard] = {}

        self.configure(corner_radius=0, fg_color="transparent")

        self.grid_columnconfigure(0, weight=1)

    def set_packages(self, packages: list[Package]):
        """Clear and repopulate the package list."""
        # Clear existing cards
        for card in self.package_cards.values():
            card.destroy()
        self.package_cards.clear()

        # Create new cards
        for i, package in enumerate(packages):
            card = PackageCard(self, package=package, on_upgrade=self.on_upgrade)
            card.grid(row=i, column=0, sticky="ew", pady=(0, 8), padx=4)
            self.package_cards[package.id] = card

    def get_card(self, package_id: str) -> Optional[PackageCard]:
        """Get a package card by ID."""
        return self.package_cards.get(package_id)

    def show_empty_message(self, message: str = "No packages available for upgrade"):
        """Show a message when no packages are available."""
        for card in self.package_cards.values():
            card.destroy()
        self.package_cards.clear()

        label = ctk.CTkLabel(
            self,
            text=message,
            font=ctk.CTkFont(size=14),
            text_color=("gray40", "gray60"),
        )
        label.grid(row=0, column=0, pady=40)


class OutputConsole(ctk.CTkFrame):
    """A console-style output display for command logs."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)

        self.configure(corner_radius=8, fg_color=("gray95", "gray10"))

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Header with title and clear button
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 4))
        header.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            header,
            text="📋 Output Log",
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w",
        )
        title.grid(row=0, column=0, sticky="w")

        clear_btn = ctk.CTkButton(
            header,
            text="Clear",
            width=60,
            height=24,
            font=ctk.CTkFont(size=11),
            fg_color="transparent",
            border_width=1,
            command=self.clear,
        )
        clear_btn.grid(row=0, column=1, sticky="e")

        # Text display
        self.textbox = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color=("white", "gray8"),
            corner_radius=6,
            wrap="word",
        )
        self.textbox.grid(row=1, column=0, sticky="nsew", padx=10, pady=(4, 10))
        self.textbox.configure(state="disabled")

    def append(self, text: str):
        """Append text to the console."""
        self.textbox.configure(state="normal")
        self.textbox.insert("end", text + "\n")
        self.textbox.see("end")
        self.textbox.configure(state="disabled")

    def clear(self):
        """Clear the console."""
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        self.textbox.configure(state="disabled")


class StatusBar(ctk.CTkFrame):
    """Status bar showing current operation status."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)

        self.configure(height=30, corner_radius=0, fg_color=("gray85", "gray20"))

        self.grid_columnconfigure(0, weight=1)

        self.status_label = ctk.CTkLabel(
            self, text="Ready", font=ctk.CTkFont(size=11), anchor="w"
        )
        self.status_label.grid(row=0, column=0, sticky="w", padx=12, pady=4)

        self.progress_label = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=11), anchor="e"
        )
        self.progress_label.grid(row=0, column=1, sticky="e", padx=12, pady=4)

    def set_status(self, text: str):
        """Set the status text."""
        self.status_label.configure(text=text)

    def set_progress(self, text: str):
        """Set the progress text."""
        self.progress_label.configure(text=text)
