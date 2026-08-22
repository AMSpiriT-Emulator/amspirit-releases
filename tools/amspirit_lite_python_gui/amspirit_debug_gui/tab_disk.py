"""Disk tab: create a blank disk, save the current one, or load media per drive."""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import filedialog, ttk
from urllib.parse import quote

from amspirit_debug_gui.api_client import compact_json


class DiskTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=8)
        self.app = app
        self._build()

    def _build(self):
        for drive, letter in ((0, "A"), (1, "B")):
            frame = ttk.LabelFrame(self, text=f"Drive {letter}", padding=8)
            frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))
            ttk.Button(frame, text="Create blank disk", command=lambda d=drive: self._create(d)).pack(side=tk.LEFT)
            ttk.Button(frame, text="Save to .dsk…", command=lambda d=drive, l=letter: self._save(d, l)).pack(
                side=tk.LEFT, padx=(8, 0)
            )
            ttk.Button(frame, text="Load media…", command=lambda d=drive: self._load_media(d)).pack(
                side=tk.LEFT, padx=(8, 0)
            )

        bin_frame = ttk.LabelFrame(self, text="Binary (.bin) load options", padding=8)
        bin_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))
        row = ttk.Frame(bin_frame)
        row.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(row, text="Load address (hex, headerless .bin only):").pack(side=tk.LEFT)
        self._load_addr_var = tk.StringVar()
        ttk.Entry(row, textvariable=self._load_addr_var, width=8).pack(side=tk.LEFT, padx=(2, 8))
        ttk.Label(row, text="Entry point (hex, optional):").pack(side=tk.LEFT)
        self._entry_addr_var = tk.StringVar()
        ttk.Entry(row, textvariable=self._entry_addr_var, width=8).pack(side=tk.LEFT, padx=(2, 0))

        self._status_var = tk.StringVar()
        ttk.Label(self, textvariable=self._status_var, foreground="#555").pack(side=tk.TOP, anchor="w")

    def _create(self, drive: int):
        def done(_result, error):
            self._status_var.set(f"create failed: {self.app.describe_error(error)}" if error else f"blank disk inserted in drive {drive}")

        self.app.run_async(lambda: self.app.client.post("/api/disk", {"action": "create", "drive": drive}), done)

    def _save(self, drive: int, letter: str):
        path = filedialog.asksaveasfilename(defaultextension=".dsk", initialfile=f"disk_{letter}.dsk",
                                              filetypes=[("DSK images", "*.dsk")])
        if not path:
            return

        def done(result, error):
            if error is not None:
                self._status_var.set(f"save failed: {self.app.describe_error(error)}")
                return
            with open(path, "wb") as f:
                f.write(result.body)
            self._status_var.set(f"saved {path}")

        body = compact_json({"action": "save", "drive": drive})
        self.app.run_async(lambda: self.app.client.request("POST", "/api/disk", body, "application/json"), done)

    def _load_media(self, drive: int):
        filetypes = [
            ("All Supported", "*.sna *.dsk *.hfe *.ipf *.cpr *.cro *.bin"),
            ("SNA snapshots", "*.sna"),
            ("DSK disk images", "*.dsk"),
            ("HFE images", "*.hfe"),
            ("IPF images", "*.ipf"),
            ("CPR cartridges", "*.cpr"),
            ("CRO ROM sets", "*.cro"),
            ("BIN files", "*.bin"),
            ("All files", "*.*"),
        ]
        path = filedialog.askopenfilename(filetypes=filetypes)
        if not path:
            return

        try:
            with open(path, "rb") as f:
                data = f.read()
            if not data:
                self._status_var.set("load failed: file is empty")
                return
        except IOError as e:
            self._status_var.set(f"load failed: {e}")
            return

        filename = os.path.basename(path)
        name_param = filename

        if filename.lower().endswith((".bin", ".amsdos")):
            addr = self._load_addr_var.get().strip()
            entry = self._entry_addr_var.get().strip()
            if addr:
                name_param = f"{os.path.splitext(filename)[0]}@{addr}"
                if entry:
                    name_param += f"@{entry}"
                name_param += ".bin"

        def done(_result, error):
            if error is not None:
                self._status_var.set(f"load failed: {self.app.describe_error(error)}")
            else:
                self._status_var.set(f"queued {filename} into drive {drive} — check emulator log / GET /api/fdc or /api/basic_state")

        url = f"/api/media?name={quote(name_param)}&drive={drive}"
        self.app.run_async(
            lambda: self.app.client.post_raw(url, data, "application/octet-stream"), done
        )
