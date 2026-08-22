"""Keyboard tab: send text/keys to the CPC, watch the live 10x8 key matrix."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from amspirit_debug_gui.util import KMAT_LABELS, VK_TABLE, ThreadSafeMirror

_IDLE_BG = "#e8e8e8"
_PRESSED_BG = "#2e7d32"


class KeyboardTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=8)
        self.app = app
        self._cells: dict[tuple[int, int], tk.Label] = {}
        self._hex_labels: dict[int, ttk.Label] = {}
        self._live_var = tk.BooleanVar(value=False)
        self._live = ThreadSafeMirror(self._live_var, False)
        self._build()
        app.poller.register(
            "kbd_matrix", 300, lambda: app.client.get("/api/keymatrix"),
            self._on_matrix, active=lambda: self._live.value and app.is_tab_active("kbd")(),
        )

    def _build(self):
        send_frame = ttk.LabelFrame(self, text="Type to CPC", padding=6)
        send_frame.pack(side=tk.TOP, fill=tk.X)

        self._text_var = tk.StringVar()
        entry = ttk.Entry(send_frame, textvariable=self._text_var)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        entry.bind("<Return>", lambda _e: self._send_text())
        ttk.Button(send_frame, text="Send", command=self._send_text).pack(side=tk.LEFT)
        ttk.Button(send_frame, text="Clear", command=lambda: self._text_var.set("")).pack(
            side=tk.LEFT, padx=(6, 0)
        )

        keys_frame = ttk.LabelFrame(self, text="Special keys", padding=6)
        keys_frame.pack(side=tk.TOP, fill=tk.X, pady=(8, 0))
        for name in VK_TABLE:
            ttk.Button(keys_frame, text=name, command=lambda n=name: self._send_vk(n)).pack(
                side=tk.LEFT, padx=2
            )

        matrix_frame = ttk.LabelFrame(self, text="CPC keyboard matrix", padding=6)
        matrix_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(8, 0))

        top = ttk.Frame(matrix_frame)
        top.pack(side=tk.TOP, fill=tk.X)
        ttk.Checkbutton(top, text="Live refresh (300ms)", variable=self._live_var).pack(side=tk.LEFT)
        ttk.Button(top, text="Refresh once", command=lambda: self.app.poller.trigger("kbd_matrix")).pack(
            side=tk.LEFT, padx=(8, 0)
        )

        grid = ttk.Frame(matrix_frame)
        grid.pack(side=tk.TOP, pady=(8, 0))
        for c in range(8):
            ttk.Label(grid, text=f"bit {c}", font=("Courier New", 8)).grid(row=0, column=c + 1)
        ttk.Label(grid, text="hex", font=("Courier New", 8)).grid(row=0, column=9)
        for r in range(10):
            ttk.Label(grid, text=f"Lg{r}", font=("Courier New", 8)).grid(row=r + 1, column=0, sticky="e", padx=(0, 4))
            for c in range(8):
                lbl = tk.Label(
                    grid, text=KMAT_LABELS[r][c], width=6, font=("Courier New", 8),
                    background=_IDLE_BG, relief=tk.RIDGE, borderwidth=1,
                )
                lbl.grid(row=r + 1, column=c + 1, padx=1, pady=1)
                self._cells[(r, c)] = lbl
            hexlbl = ttk.Label(grid, text="00", font=("Courier New", 8))
            hexlbl.grid(row=r + 1, column=9, padx=(4, 0))
            self._hex_labels[r] = hexlbl

        self._status_var = tk.StringVar()
        ttk.Label(self, textvariable=self._status_var, foreground="#555").pack(side=tk.TOP, anchor="w", pady=(6, 0))

    def _send_text(self):
        text = self._text_var.get()
        if not text:
            return
        text = text.replace("\\n", "\r").replace("\\r", "\r")

        def done(_result, error):
            if error is not None:
                self._status_var.set(f"send failed: {self.app.describe_error(error)}")
            else:
                self._status_var.set(f"sent {len(text)} character(s)")

        self.app.run_async(lambda: self.app.client.post("/api/keytype", {"text": text}), done)

    def _send_vk(self, name: str):
        vk = VK_TABLE[name]

        def done(_result, error):
            if error is not None:
                self._status_var.set(f"key {name} failed: {self.app.describe_error(error)}")
            else:
                self._status_var.set(f"sent {name}")

        self.app.run_async(lambda: self.app.client.post("/api/keypress", {"vk": vk}), done)

    def _on_matrix(self, result, error):
        if error is not None:
            self._status_var.set(f"matrix read failed: {self.app.describe_error(error)}")
            return
        matrix = result.get("matrix", [])
        # NB: the shipped web UI highlights bit==1 as "pressed" for this
        # endpoint (kmatUpdate in amspirit-lite.html) even though the API
        # doc's prose describes the row byte as active-low hardware state --
        # mirrored here to match the page's actual (not documented) behaviour.
        for r in range(min(len(matrix), 10)):
            byte = matrix[r]
            for c in range(8):
                pressed = (byte >> c) & 1
                cell = self._cells[(r, c)]
                cell.configure(
                    background=_PRESSED_BG if pressed else _IDLE_BG,
                    foreground="white" if pressed else "black",
                )
            self._hex_labels[r].configure(text=f"{byte:02X}")
