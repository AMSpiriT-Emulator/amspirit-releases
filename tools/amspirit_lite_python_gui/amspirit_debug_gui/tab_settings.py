"""Settings tab: read-only view of the current keyboard mapping.

The original page is read-only here too (remapping goes through
POST /api/keymap, which exists server-side but this UI never calls it).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from amspirit_debug_gui import theme


class SettingsTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=8)
        self.app = app
        self._build()

    def _build(self):
        top = ttk.Frame(self)
        top.pack(side=tk.TOP, fill=tk.X)
        self._layout_var = tk.StringVar(value="Layout: --")
        ttk.Label(top, textvariable=self._layout_var, font=theme.mono(10, bold=True)).pack(side=tk.LEFT)
        ttk.Button(top, text="Refresh", command=self._refresh).pack(side=tk.LEFT, padx=(10, 0))

        self._tree = ttk.Treeview(
            self, columns=("kc", "vk", "vk_shift", "nomod"), show="headings", height=24
        )
        self._tree.heading("kc", text="SDL keycode")
        self._tree.heading("vk", text="VK (no shift)")
        self._tree.heading("vk_shift", text="VK (shift)")
        self._tree.heading("nomod", text="no-mod")
        self._tree.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(8, 0))

        self._status_var = tk.StringVar()
        ttk.Label(self, textvariable=self._status_var, style="Muted.TLabel").pack(side=tk.TOP, anchor="w", pady=(6, 0))

    def _refresh(self):
        def done(result, error):
            if error is not None:
                self._status_var.set(f"read failed: {self.app.describe_error(error)}")
                return
            self._layout_var.set(f"Layout: {result.get('layout', '?')}")
            self._tree.delete(*self._tree.get_children())
            for entry in result.get("mapping", []):
                kc = entry.get("sdl_keycode")
                kc_display = f"{kc:#x}" if isinstance(kc, int) else str(kc)
                self._tree.insert(
                    "", tk.END,
                    values=(kc_display, entry.get("vk"), entry.get("vk_with_shift"), entry.get("nomod")),
                )
            self._status_var.set(f"{len(result.get('mapping', []))} key(s)")

        self.app.run_async(lambda: self.app.client.get("/api/keymap"), done)
