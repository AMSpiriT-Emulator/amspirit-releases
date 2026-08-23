"""Poke tab: write raw bytes to CPC RAM, optionally redirecting the PC.

RAM writes via POST /api/ram and POST /api/exec now return a sequence number
(1.14 API contract). The client must poll emu.ram_apply_seq (GET /api/state)
until it reaches that number before trusting a RAM readback — the HTTP
response only means the request was queued, not applied by the main thread.
This tab now waits for confirmation via poll_until_ram_seq before reporting
success."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from amspirit_debug_gui.util import parse_addr, parse_hex_bytes


class PokeTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=8)
        self.app = app
        self._build()

    def _build(self):
        write_frame = ttk.LabelFrame(self, text="Write bytes", padding=8)
        write_frame.pack(side=tk.TOP, fill=tk.X)

        row1 = ttk.Frame(write_frame)
        row1.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(row1, text="Address:", style="Muted.TLabel").pack(side=tk.LEFT)
        self._addr_var = tk.StringVar(value="0x4000")
        ttk.Entry(row1, textvariable=self._addr_var, width=10).pack(side=tk.LEFT, padx=(2, 10))
        ttk.Label(row1, text="Bank:", style="Muted.TLabel").pack(side=tk.LEFT)
        self._bank_var = tk.StringVar(value="0")
        ttk.Entry(row1, textvariable=self._bank_var, width=4).pack(side=tk.LEFT, padx=(2, 0))

        ttk.Label(write_frame, text="Bytes (hex, spaces/':' allowed):", style="Muted.TLabel").pack(side=tk.TOP, anchor="w", pady=(8, 2))
        self._data_var = tk.StringVar(value="3e 01")
        ttk.Entry(write_frame, textvariable=self._data_var).pack(side=tk.TOP, fill=tk.X)

        exec_row = ttk.Frame(write_frame)
        exec_row.pack(side=tk.TOP, fill=tk.X, pady=(8, 0))
        self._exec_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(exec_row, text="Then jump to (entry):", variable=self._exec_var).pack(side=tk.LEFT)
        self._entry_var = tk.StringVar()
        ttk.Entry(exec_row, textvariable=self._entry_var, width=10).pack(side=tk.LEFT, padx=(4, 0))

        ttk.Button(write_frame, text="Write", command=self._write).pack(side=tk.TOP, anchor="w", pady=(10, 0))

        exec_frame = ttk.LabelFrame(self, text="Execute at address (no write)", padding=8)
        exec_frame.pack(side=tk.TOP, fill=tk.X, pady=(10, 0))
        ttk.Label(exec_frame, text="Address:", style="Muted.TLabel").pack(side=tk.LEFT)
        self._exec_addr_var = tk.StringVar(value="0x4000")
        ttk.Entry(exec_frame, textvariable=self._exec_addr_var, width=10).pack(side=tk.LEFT, padx=(2, 10))
        ttk.Button(exec_frame, text="Execute", command=self._exec_only).pack(side=tk.LEFT)

        self._status_var = tk.StringVar()
        ttk.Label(self, textvariable=self._status_var, style="Muted.TLabel").pack(side=tk.TOP, anchor="w", pady=(10, 0))

    def _write(self):
        try:
            addr = parse_addr(self._addr_var.get())
            bank = int(self._bank_var.get() or 0)
            data = parse_hex_bytes(self._data_var.get())
        except ValueError as e:
            self._status_var.set(f"bad input: {e}")
            return
        body = {"addr": addr, "data": data.hex(), "bank": bank}
        if self._exec_var.get():
            body["exec"] = True
            entry = self._entry_var.get().strip()
            if entry:
                try:
                    body["entry"] = parse_addr(entry)
                except ValueError as e:
                    self._status_var.set(f"bad entry address: {e}")
                    return

        def done(result, error):
            if error is not None:
                self._status_var.set(f"write failed: {self.app.describe_error(error)}")
                return
            seq = result.get("seq")
            if seq is not None:
                self._status_var.set(f"queued write of {len(data)} byte(s) at {addr:#06x}…")
                def on_applied(applied):
                    if applied:
                        self._status_var.set(f"wrote {len(data)} byte(s) at {addr:#06x}")
                    else:
                        self._status_var.set("write queued but timed out waiting for confirmation")
                self.app.poll_until_ram_seq(seq, on_applied)
            else:
                self._status_var.set(f"wrote {len(data)} byte(s) at {addr:#06x}")

        self.app.run_async(lambda: self.app.client.post("/api/ram", body), done)

    def _exec_only(self):
        try:
            addr = parse_addr(self._exec_addr_var.get())
        except ValueError as e:
            self._status_var.set(f"bad input: {e}")
            return

        def done(result, error):
            if error is not None:
                self._status_var.set(f"exec failed: {self.app.describe_error(error)}")
                return
            seq = result.get("seq")
            if seq is not None:
                self._status_var.set(f"queued jump to {addr:#06x}…")
                def on_applied(applied):
                    if applied:
                        self._status_var.set(f"jumped to {addr:#06x}")
                    else:
                        self._status_var.set("jump queued but timed out waiting for confirmation")
                self.app.poll_until_ram_seq(seq, on_applied)
            else:
                self._status_var.set(f"jumped to {addr:#06x}")

        self.app.run_async(lambda: self.app.client.post("/api/exec", {"addr": addr}), done)
