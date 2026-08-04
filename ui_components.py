"""
Custom UI Components for Winget Upgrade GUI
Built on CustomTkinter for a modern appearance in dark and light mode.
"""

from __future__ import annotations

from typing import Callable

import customtkinter as ctk

from winget_runner import Package, UpgradeResult

SUCCESS_COLORS = ("#2ECC71", "#27AE60")
SUCCESS_HOVER = ("#27AE60", "#1E8449")
DANGER_COLORS = ("#E74C3C", "#C0392B")
DANGER_HOVER = ("#C0392B", "#922B21")
WARNING_TEXT = ("#B9770E", "#F39C12")
DANGER_TEXT = ("#C0392B", "#E74C3C")
MUTED_TEXT = ("gray40", "gray60")


class ConfirmDialog(ctk.CTkToplevel):
    """Modal yes/no dialog that the caller can also dismiss programmatically.

    tkinter's messagebox maps to a native MessageBoxW that cannot be closed
    from code, so a timed-out prompt would linger and keep the main window
    disabled. This one exposes dismiss().
    """

    def __init__(self, parent, title: str, message: str, on_answer: Callable[[bool], None]):
        super().__init__(parent)
        self._on_answer = on_answer
        self._answered = False

        self.title(title)
        self.resizable(False, False)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", lambda: self._answer(False))

        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(padx=24, pady=20, fill="both", expand=True)

        ctk.CTkLabel(
            container,
            text=message,
            font=ctk.CTkFont(size=13),
            justify="left",
            anchor="w",
            wraplength=460,
        ).pack(anchor="w", pady=(0, 18))

        buttons = ctk.CTkFrame(container, fg_color="transparent")
        buttons.pack(anchor="e")

        no_button = ctk.CTkButton(
            buttons,
            text="No",
            width=110,
            height=34,
            fg_color="transparent",
            border_width=1,
            text_color=("gray20", "gray80"),
            hover_color=("gray85", "gray25"),
            command=lambda: self._answer(False),
        )
        no_button.pack(side="left", padx=(0, 10))

        yes_button = ctk.CTkButton(
            buttons,
            text="Yes, close it",
            width=140,
            height=34,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=SUCCESS_COLORS,
            hover_color=SUCCESS_HOVER,
            command=lambda: self._answer(True),
        )
        yes_button.pack(side="left")

        self.bind("<Escape>", lambda _event: self._answer(False))
        self.bind("<Return>", lambda _event: self._answer(True))

        self.update_idletasks()
        self._center_on(parent)
        self.grab_set()
        yes_button.focus_set()

    def _center_on(self, parent) -> None:
        x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 3
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def _answer(self, value: bool) -> None:
        if self._answered:
            return
        self._answered = True
        self._close()
        self._on_answer(value)

    def _close(self) -> None:
        try:
            self.grab_release()
        except Exception:
            pass
        if self.winfo_exists():
            self.destroy()

    def dismiss(self) -> None:
        """Close the dialog without answering (timeout/cancel paths)."""
        if not self._answered:
            self._answered = True
            self._close()


class PackageCard(ctk.CTkFrame):
    """A card for one package: checkbox, info, upgrade button, progress/result row."""

    def __init__(
        self,
        parent,
        package: Package,
        on_upgrade: Callable[[Package], None],
        on_toggle: Callable[[Package, bool], None] | None = None,
        selected: bool = True,
        **kwargs,
    ):
        super().__init__(parent, **kwargs)
        self.package = package
        self.on_upgrade = on_upgrade
        self.on_toggle = on_toggle
        self.is_upgrading = False
        # None while pending, then "success" or "failed". Succeeded cards are
        # permanently deselected and disabled so they can't be re-upgraded.
        self.result_state: str | None = None
        self._determinate = True  # the bar is created in determinate mode

        self.configure(
            corner_radius=8,
            fg_color=("gray90", "gray17"),
            border_width=1,
            border_color=("gray70", "gray30"),
        )

        self.grid_columnconfigure(1, weight=1)

        # Selection checkbox
        self.selected_var = ctk.BooleanVar(value=selected)
        self.checkbox = ctk.CTkCheckBox(
            self,
            text="",
            width=24,
            variable=self.selected_var,
            command=self._on_toggle,
        )
        self.checkbox.grid(row=0, column=0, sticky="n", padx=(14, 0), pady=(16, 0))

        # Package info
        info_frame = ctk.CTkFrame(self, fg_color="transparent")
        info_frame.grid(row=0, column=1, sticky="nsew", padx=(4, 15), pady=12)
        info_frame.grid_columnconfigure(0, weight=1)

        display_name = (
            package.name[:60] + "…" if len(package.name) > 60 else package.name
        )
        if package.pinned:
            display_name = f"📌 {display_name}"
        self.name_label = ctk.CTkLabel(
            info_frame,
            text=display_name,
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        )
        self.name_label.grid(row=0, column=0, sticky="w")

        self.id_label = ctk.CTkLabel(
            info_frame,
            text=package.id,
            font=ctk.CTkFont(size=11),
            text_color=MUTED_TEXT,
            anchor="w",
        )
        self.id_label.grid(row=1, column=0, sticky="w", pady=(2, 0))

        version_text = f"{package.current_version or '?'}  →  {package.available_version}"
        self.version_label = ctk.CTkLabel(
            info_frame,
            text=version_text,
            font=ctk.CTkFont(size=12),
            text_color=("gray30", "gray70"),
            anchor="w",
        )
        self.version_label.grid(row=2, column=0, sticky="w", pady=(4, 0))

        # Upgrade button + source
        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.grid(row=0, column=2, sticky="nse", padx=15, pady=12)

        self.upgrade_button = ctk.CTkButton(
            button_frame,
            text="Upgrade",
            width=100,
            height=36,
            font=ctk.CTkFont(size=13),
            command=self._on_upgrade_click,
        )
        self.upgrade_button.pack(anchor="center", expand=True)

        self.source_label = ctk.CTkLabel(
            button_frame,
            text=package.source,
            font=ctk.CTkFont(size=10),
            text_color=("gray50", "gray50"),
        )
        self.source_label.pack(anchor="center", pady=(4, 0))

        # Progress / result row (hidden until needed)
        self.progress_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.progress_frame.grid(
            row=1, column=0, columnspan=3, sticky="ew", padx=15, pady=(0, 10)
        )
        self.progress_frame.grid_columnconfigure(0, weight=1)
        self.progress_frame.grid_remove()

        self.progress_bar = ctk.CTkProgressBar(
            self.progress_frame,
            height=8,
            corner_radius=4,
            progress_color=("#3B8ED0", "#1F6AA5"),
        )
        self.progress_bar.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        self.progress_bar.set(0)

        self.progress_label = ctk.CTkLabel(
            self.progress_frame,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=MUTED_TEXT,
            anchor="w",
            justify="left",
        )
        self.progress_label.grid(row=1, column=0, sticky="w")

    # -- selection ---------------------------------------------------------

    @property
    def selected(self) -> bool:
        return bool(self.selected_var.get())

    def set_selected(self, selected: bool) -> None:
        self.selected_var.set(selected)

    def _on_toggle(self) -> None:
        if self.on_toggle:
            self.on_toggle(self.package, self.selected)

    # -- actions -----------------------------------------------------------

    def _on_upgrade_click(self) -> None:
        if not self.is_upgrading:
            self.on_upgrade(self.package)

    def set_enabled(self, enabled: bool) -> None:
        """Enable/disable interaction while a global operation runs."""
        if self.result_state == "success":
            return  # a finished card must never become re-upgradable
        state = "normal" if enabled else "disabled"
        self.checkbox.configure(state=state)
        if not self.is_upgrading:
            self.upgrade_button.configure(state=state)

    def set_upgrading(self, upgrading: bool) -> None:
        self.is_upgrading = upgrading
        if upgrading:
            self.result_state = None
            self.upgrade_button.configure(
                text="Upgrading…", state="disabled", fg_color=("gray60", "gray40")
            )
            self.checkbox.configure(state="disabled")
            self.progress_frame.grid()
            self.progress_bar.grid()
            self.set_indeterminate("Working…")
        else:
            self.upgrade_button.configure(
                text="Upgrade",
                state="normal",
                fg_color=ctk.ThemeManager.theme["CTkButton"]["fg_color"],
            )
            self.checkbox.configure(state="normal")
            self._stop_bar()
            self.progress_frame.grid_remove()

    def _stop_bar(self) -> None:
        if not self._determinate:
            self.progress_bar.stop()
            self.progress_bar.configure(mode="determinate")
            self._determinate = True

    def set_indeterminate(self, status: str) -> None:
        """Animate the bar when winget gives no percentage to show."""
        if self._determinate:
            self.progress_bar.configure(mode="indeterminate")
            self.progress_bar.start()
            self._determinate = False
        self.progress_label.configure(text=status, text_color=MUTED_TEXT)

    def update_progress(self, progress: float, status: str) -> None:
        if not self._determinate:
            self._stop_bar()
        else:
            progress = max(progress, self.progress_bar.get())  # never move backwards
        self.progress_bar.set(min(progress, 1.0))
        self.progress_label.configure(text=status, text_color=MUTED_TEXT)

    def set_result(self, result: UpgradeResult) -> None:
        """Show the outcome of an upgrade, including the failure reason."""
        self.is_upgrading = False
        self._stop_bar()
        self.progress_bar.grid_remove()

        if result.success:
            self.result_state = "success"
            # Programmatic set() does not fire the checkbox command, so this
            # does not touch the persisted skip list.
            self.selected_var.set(False)
            self.checkbox.configure(state="disabled")
            self.upgrade_button.configure(
                text="✓ Done", state="disabled", fg_color=SUCCESS_COLORS
            )
            if result.reboot_required:
                self.progress_frame.grid()
                self.progress_label.configure(
                    text=f"🔁 {result.reason}", text_color=WARNING_TEXT
                )
            else:
                self.progress_frame.grid_remove()
        else:
            self.result_state = "failed"
            # Stays disabled until the batch ends; set_enabled re-enables it.
            self.checkbox.configure(state="disabled")
            self.upgrade_button.configure(
                text="↻ Retry",
                state="disabled",
                fg_color=DANGER_COLORS,
                hover_color=DANGER_HOVER,
            )
            self.progress_frame.grid()
            self.progress_label.configure(
                text=f"✗ {result.reason}",
                text_color=DANGER_TEXT,
                wraplength=600,
            )


class PackageListFrame(ctk.CTkScrollableFrame):
    """Scrollable frame containing package cards, plus loading/empty/error states."""

    def __init__(
        self,
        parent,
        on_upgrade: Callable[[Package], None],
        on_toggle: Callable[[Package, bool], None] | None = None,
        **kwargs,
    ):
        super().__init__(parent, **kwargs)
        self.on_upgrade = on_upgrade
        self.on_toggle = on_toggle
        self.package_cards: dict[str, PackageCard] = {}
        self._message_label: ctk.CTkLabel | None = None

        self.configure(corner_radius=0, fg_color="transparent")
        self.grid_columnconfigure(0, weight=1)

    def _clear(self) -> None:
        for card in self.package_cards.values():
            card.destroy()
        self.package_cards.clear()
        if self._message_label is not None:
            self._message_label.destroy()
            self._message_label = None

    def set_packages(
        self, packages: list[Package], selected_ids: set[str] | None = None
    ) -> None:
        """Clear and repopulate the package list."""
        self._clear()
        for i, package in enumerate(packages):
            selected = True if selected_ids is None else package.id in selected_ids
            card = PackageCard(
                self,
                package=package,
                on_upgrade=self.on_upgrade,
                on_toggle=self.on_toggle,
                selected=selected,
            )
            card.grid(row=i, column=0, sticky="ew", pady=(0, 8), padx=4)
            self.package_cards[package.id] = card

    def get_card(self, package_id: str) -> PackageCard | None:
        return self.package_cards.get(package_id)

    def show_message(self, message: str, kind: str = "info") -> None:
        """Replace the list with a status message (loading/empty/error)."""
        self._clear()
        colors = {
            "info": MUTED_TEXT,
            "success": ("#1E8449", "#2ECC71"),
            "error": DANGER_TEXT,
        }
        self._message_label = ctk.CTkLabel(
            self,
            text=message,
            font=ctk.CTkFont(size=15),
            text_color=colors.get(kind, MUTED_TEXT),
            wraplength=640,
            justify="center",
        )
        self._message_label.grid(row=0, column=0, pady=48)

    def set_all_enabled(self, enabled: bool) -> None:
        for card in self.package_cards.values():
            card.set_enabled(enabled)

    def set_all_selected(self, selected: bool) -> None:
        for card in self.package_cards.values():
            if card.result_state != "success":
                card.set_selected(selected)

    def selected_packages(self) -> list[Package]:
        return [
            card.package
            for card in self.package_cards.values()
            if card.selected and card.result_state != "success"
        ]


class OutputConsole(ctk.CTkFrame):
    """A console-style output display for command logs."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)

        self.configure(corner_radius=8, fg_color=("gray95", "gray10"))

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

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
            text_color=("gray20", "gray80"),
            command=self.clear,
        )
        clear_btn.grid(row=0, column=1, sticky="e")

        self.textbox = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color=("white", "gray8"),
            corner_radius=6,
            wrap="word",
        )
        self.textbox.grid(row=1, column=0, sticky="nsew", padx=10, pady=(4, 10))
        self.textbox.configure(state="disabled")

    def append(self, text: str) -> None:
        self.textbox.configure(state="normal")
        self.textbox.insert("end", text + "\n")
        self.textbox.see("end")
        self.textbox.configure(state="disabled")

    def clear(self) -> None:
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        self.textbox.configure(state="disabled")


class StatusBar(ctk.CTkFrame):
    """Status bar: operation status left, progress + session info right."""

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
        self.progress_label.grid(row=0, column=1, sticky="e", padx=(0, 8), pady=4)

        self.meta_label = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(size=11),
            anchor="e",
            text_color=MUTED_TEXT,
        )
        self.meta_label.grid(row=0, column=2, sticky="e", padx=(0, 12), pady=4)

    def set_status(self, text: str) -> None:
        self.status_label.configure(text=text)

    def set_progress(self, text: str) -> None:
        self.progress_label.configure(text=text)

    def set_meta(self, text: str) -> None:
        self.meta_label.configure(text=text)
