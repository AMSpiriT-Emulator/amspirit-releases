"""Heat Map tab: a genuine 256x256 visual heatmap of RAM writes.

Same algorithm as hmTick() in amspirit-lite.html: each tick re-dumps the
selected bank's 64 KB, decays (or clears, in "instant" mode) the intensity
buffer, then bumps any byte that changed since the previous dump. Y = high
byte of the address, X = low byte -- one pixel per byte.

Simplification vs. the original page: only the currently-selected bank is
tracked (the page tracks every bank simultaneously via Promise.all so
switching banks doesn't lose history); switching banks here restarts that
bank's diff baseline, which just means one blank tick after a switch.
"""

from __future__ import annotations

import array
import tkinter as tk
from tkinter import ttk

from amspirit_debug_gui import theme
from amspirit_debug_gui.util import ThreadSafeMirror

# Identity colours, not theme colours: each one says "this dot is PC" and is
# the same hue amspirit-lite.html uses. Deliberately not in theme.py, which
# owns surfaces and roles -- these belong to the register they name. Defined
# once because the legend and the bitmap must agree or the overlay lies.
_OVERLAYS = (
    ("PC", "#00ff44"),
    ("SP", "#00ffff"),
    ("HL", "#ffff00"),
    ("IX", "#ff8800"),
    ("IY", "#ff44ff"),
)

_STOPS = [
    (0x0C, 0x0C, 0x0C),
    (0x4A, 0x00, 0x78),
    (0xFF, 0x40, 0x00),
    (0xFF, 0xD0, 0x00),
    (0xFF, 0xFF, 0xFF),
]


def _build_palette(n: int = 256) -> list[str]:
    palette = []
    segments = len(_STOPS) - 1
    for i in range(n):
        t = i / (n - 1)
        seg = min(int(t * segments), segments - 1)
        local_t = t * segments - seg
        r0, g0, b0 = _STOPS[seg]
        r1, g1, b1 = _STOPS[seg + 1]
        r = round(r0 + (r1 - r0) * local_t)
        g = round(g0 + (g1 - g0) * local_t)
        b = round(b0 + (b1 - b0) * local_t)
        palette.append(f"#{r:02x}{g:02x}{b:02x}")
    return palette


_PALETTE = _build_palette()
_ZOOM = 2  # 256x256 buffer displayed at 512x512


class HeatmapTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=8)
        self.app = app
        self._heat = array.array("f", [0.0]) * 65536
        self._prev: bytes | None = None
        self._prev_bank: int | None = None
        self._overlay_vars: dict[str, tk.BooleanVar] = {}
        self._build()
        self._live = ThreadSafeMirror(self._live_var, False)
        self._bank = ThreadSafeMirror(self._bank_var, self._bank_var.get())
        # Ticking used to run on its own 1s timer; now it's paced by the SSE
        # "frame" push instead, same as amspirit-lite.html's hmTick() call
        # from its frame listener.
        app.on_sse("frame", self._on_frame)

    def _build(self):
        top = ttk.Frame(self)
        top.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(top, text="Bank:", style="Muted.TLabel").pack(side=tk.LEFT)
        self._bank_var = tk.IntVar(value=0)
        ttk.Spinbox(top, from_=0, to=7, width=3, textvariable=self._bank_var, command=self._reset_baseline).pack(
            side=tk.LEFT, padx=(2, 10)
        )
        ttk.Label(top, text="Mode:", style="Muted.TLabel").pack(side=tk.LEFT)
        self._mode_var = tk.StringVar(value="accumulate")
        ttk.Combobox(top, textvariable=self._mode_var, values=["accumulate", "instant"], width=10,
                     state="readonly").pack(side=tk.LEFT, padx=(2, 10))
        ttk.Label(top, text="Decay:", style="Muted.TLabel").pack(side=tk.LEFT)
        self._decay_var = tk.StringVar(value="0.92")
        ttk.Combobox(top, textvariable=self._decay_var, values=["0.80", "0.92", "0.98", "1.00"], width=6,
                     state="readonly").pack(side=tk.LEFT, padx=(2, 10))
        self._live_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="Live", variable=self._live_var).pack(side=tk.LEFT)
        ttk.Button(top, text="Tick once", command=self._tick_once).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        ttk.Button(top, text="Clear", command=self._clear).pack(side=tk.LEFT, padx=(8, 0))

        overlay_row = ttk.Frame(self)
        overlay_row.pack(side=tk.TOP, fill=tk.X, pady=(6, 0))
        ttk.Label(overlay_row, text="Overlay:", style="Muted.TLabel").pack(side=tk.LEFT)
        for name, color in _OVERLAYS:
            var = tk.BooleanVar(value=name in ("PC", "SP"))
            self._overlay_vars[name] = var
            # Classic Checkbutton, not ttk: only this one can carry a
            # per-item foreground, and here the colour *is* the legend --
            # it matches the overlay dot drawn on the bitmap below.
            cb = tk.Checkbutton(overlay_row, text=name, variable=var,
                                foreground=color, selectcolor=theme.C["field_bg"],
                                background=theme.C["bg"],
                                activebackground=theme.C["bg"],
                                activeforeground=color)
            cb.pack(side=tk.LEFT, padx=(6, 0))

        size = 256 * _ZOOM
        self._canvas = tk.Canvas(self, width=size, height=size,
                                 background=theme.C["screen_bg"], highlightthickness=1,
                                 highlightbackground=theme.C["border"])
        self._canvas.pack(side=tk.TOP, pady=(8, 0))
        self._image_item = None
        self._photo = tk.PhotoImage(width=256, height=256)
        self._canvas.bind("<Motion>", self._on_hover)

        self._status_var = tk.StringVar()
        ttk.Label(self, textvariable=self._status_var, style="Muted.TLabel").pack(side=tk.TOP, anchor="w", pady=(6, 0))
        self._render()

    def _reset_baseline(self):
        self._prev = None

    def _clear(self):
        self._heat = array.array("f", [0.0]) * 65536
        self._prev = None
        self._render()

    def _on_frame(self, _data):
        if self._live.value and self.app.is_tab_active("heatmap")():
            self._tick_once()

    def _tick_once(self):
        self.app.run_async(self._tick_fetch, self._tick_apply)

    def _tick_fetch(self):
        bank = self._bank.value
        ram = bytes.fromhex(self.app.client.get(f"/api/ram?addr=0&len=65536&bank={bank}")["hex"])
        try:
            z80 = self.app.client.get("/api/z80")
        except Exception:  # noqa: BLE001 - overlay is best-effort, heatmap data is not
            z80 = {}
        return bank, ram, z80

    def _tick_apply(self, result, error):
        if error is not None:
            self._status_var.set(f"tick failed: {self.app.describe_error(error)}")
            return
        bank, ram, z80 = result
        if bank != self._prev_bank:
            self._prev = None
            self._prev_bank = bank
        mode = self._mode_var.get()
        decay = float(self._decay_var.get())
        heat = self._heat
        if self._prev is not None:
            if mode == "instant":
                for i in range(65536):
                    heat[i] = 0.0
            elif decay != 1.0:
                for i in range(65536):
                    heat[i] *= decay
            prev = self._prev
            for i in range(65536):
                if ram[i] != prev[i]:
                    heat[i] = min(1.0, heat[i] + 0.65)
        self._prev = ram
        self._z80 = z80
        self._render()
        self._status_var.set(f"bank {bank}, {sum(1 for h in heat if h > 0.01)} hot byte(s)")

    def _render(self):
        photo = self._photo
        heat = self._heat
        rows = [
            [_PALETTE[min(255, int(heat[row * 256 + col] * 255))] for col in range(256)]
            for row in range(256)
        ]
        photo.put(rows)  # single call: whole 256x256 image, one row per sublist
        zoomed = photo.zoom(_ZOOM, _ZOOM)
        self._zoomed_photo = zoomed  # keep alive
        if self._image_item is None:
            self._image_item = self._canvas.create_image(0, 0, anchor="nw", image=zoomed)
        else:
            self._canvas.itemconfigure(self._image_item, image=zoomed)
        self._canvas.delete("overlay")
        z80 = getattr(self, "_z80", {})
        for name, color in _OVERLAYS:
            if not self._overlay_vars[name].get():
                continue
            addr = z80.get(name) if name != "HL" else ((z80.get("H", 0) << 8) | z80.get("L", 0))
            if addr is None:
                continue
            col, row = addr & 0xFF, addr >> 8
            x, y = col * _ZOOM, row * _ZOOM
            self._canvas.create_oval(x - 2, y - 2, x + 2, y + 2, outline=color, width=2, tags="overlay")

    def _on_hover(self, event):
        col, row = event.x // _ZOOM, event.y // _ZOOM
        if 0 <= col < 256 and 0 <= row < 256:
            addr = (row << 8) | col
            heat = self._heat[addr]
            suffix = f"  heat:{round(heat * 100)}%" if heat > 0.01 else ""
            self._status_var.set(f"addr {addr:#06x}{suffix}")
