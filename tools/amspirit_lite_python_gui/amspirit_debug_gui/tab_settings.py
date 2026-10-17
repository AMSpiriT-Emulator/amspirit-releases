"""Settings tab: read-only view of the current keyboard mapping.

Read-only here too (remapping goes through POST /api/keymap, which exists
server-side but this UI never calls it).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class SettingsTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=8)
        self.app = app
        self._build()
        # Regime A. The key mapping is fixed configuration: nothing the
        # emulator does while running can change it, so re-reading it on a
        # timer would be asking a question whose answer cannot have moved.
        self._panel = app.register_panel(self, "A", self._refresh)

    def _build(self):
        top = ttk.Frame(self)
        top.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(top, text="Host key -> CPC character (follows the ROM language)", style="Value.TLabel").pack(side=tk.LEFT)

        self._tree = ttk.Treeview(
            self, columns=("host", "types", "shift", "ctrl"), show="headings", height=24
        )
        self._tree.heading("host", text="Host key")
        self._tree.heading("types", text="Types")
        self._tree.heading("shift", text="Shift")
        self._tree.heading("ctrl", text="Ctrl")
        self._tree.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(8, 0))

        self._status_var = tk.StringVar()
        ttk.Label(self, textvariable=self._status_var, style="Muted.TLabel").pack(side=tk.TOP, anchor="w", pady=(6, 0))

    def _refresh(self):
        def done(result, error):
            if error is not None:
                self._status_var.set(f"read failed: {self.app.describe_error(error)}")
                return
            self._tree.delete(*self._tree.get_children())
            keys = result.get("keys", [])
            for entry in keys:
                types = "(custom)" if entry.get("custom") else entry.get("types", "")
                self._tree.insert(
                    "", tk.END,
                    values=(entry.get("host_key"), types, bool(entry.get("shift")), bool(entry.get("ctrl"))),
                )
            for entry in result.get("hotkeys", []):
                self._tree.insert("", tk.END, values=(entry.get("host_key"), "(emulator hotkey)", "", ""))
            self._status_var.set(f"{len(keys)} key(s)")

        self._panel.run(lambda: self.app.client.get("/api/keymap"), done)
