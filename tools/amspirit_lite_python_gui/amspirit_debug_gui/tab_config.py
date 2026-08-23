"""Config tab: CPC model/CRTC/ROM language, and CRT monitor preset + shader parameters.

The CRT shader itself isn't reimplemented here (this GUI has no video
renderer) -- these controls only push numeric parameters to the emulator,
same limitation already accepted for this kind of control in the plan.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

MODEL_CHOICES = [("464", 0), ("664", 1), ("6128", 2), ("6128+", 4), ("464+", 5), ("GX4000", 6)]
CRTC_CHOICES = [(f"Type {i}", i) for i in range(5)]
ROM_LANG_CHOICES = ["FR", "EN", "SP", "DA"]
SCREEN_TYPE_CHOICES = [("Colour", 0), ("Green", 1), ("Colour (ASIC)", 2), ("Green (ASIC)", 3)]

CRT_PARAMS = [
    ("curvature", 0.0, 0.03),
    ("scanline", 0.0, 1.0),
    ("sharpness", 0.0, 1.0),
    ("maskType", 0, 4),
    ("maskPitch", 1.0, 6.0),
    ("mask", 0.0, 0.25),
    ("halation", 0.0, 1.0),
    ("diffusion", 0.0, 1.0),
    ("convergence", -2.0, 2.0),
    ("brightness", 0.1, 3.0),
    ("persistence", 0.0, 1.0),
]


class ConfigTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=8)
        self.app = app
        self._crt_vars: dict[str, tk.DoubleVar] = {}
        self._build()
        # Regime A, and this is the case that shows why Regime C is not a
        # universal upgrade: these widgets are *inputs*. A live refresh would
        # yank a slider out from under the user mid-drag. Reading once on
        # arrival is not a limitation here, it is the correct behaviour.
        self._panel = app.register_panel(self, "A", self._refresh_render)

    def _build(self):
        model_frame = ttk.LabelFrame(self, text="Machine", padding=8)
        model_frame.pack(side=tk.TOP, fill=tk.X)
        row = ttk.Frame(model_frame)
        row.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(row, text="Model:", style="Muted.TLabel").pack(side=tk.LEFT)
        self._model_var = tk.StringVar(value=MODEL_CHOICES[2][0])
        ttk.Combobox(row, textvariable=self._model_var, values=[n for n, _ in MODEL_CHOICES], width=8,
                     state="readonly").pack(side=tk.LEFT, padx=(2, 12))
        ttk.Label(row, text="CRTC:", style="Muted.TLabel").pack(side=tk.LEFT)
        self._crtc_var = tk.StringVar(value=CRTC_CHOICES[0][0])
        ttk.Combobox(row, textvariable=self._crtc_var, values=[n for n, _ in CRTC_CHOICES], width=8,
                     state="readonly").pack(side=tk.LEFT, padx=(2, 12))
        ttk.Label(row, text="ROM language:", style="Muted.TLabel").pack(side=tk.LEFT)
        self._rom_lang_var = tk.StringVar(value="EN")
        ttk.Combobox(row, textvariable=self._rom_lang_var, values=ROM_LANG_CHOICES, width=5,
                     state="readonly").pack(side=tk.LEFT, padx=(2, 12))
        ttk.Button(row, text="Apply (resets)", command=self._apply_machine).pack(side=tk.LEFT)

        render_frame = ttk.LabelFrame(self, text="Display & CRT", padding=8)
        render_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(10, 0))

        top = ttk.Frame(render_frame)
        top.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(top, text="Monitor preset:", style="Muted.TLabel").pack(side=tk.LEFT)
        self._monitor_var = tk.StringVar()
        self._monitor_combo = ttk.Combobox(top, textvariable=self._monitor_var, width=14, state="readonly")
        self._monitor_combo.pack(side=tk.LEFT, padx=(2, 12))
        ttk.Label(top, text="Screen type:", style="Muted.TLabel").pack(side=tk.LEFT)
        self._screen_type_var = tk.StringVar(value=SCREEN_TYPE_CHOICES[0][0])
        ttk.Combobox(top, textvariable=self._screen_type_var, values=[n for n, _ in SCREEN_TYPE_CHOICES], width=14,
                     state="readonly").pack(side=tk.LEFT, padx=(2, 12))
        ttk.Button(top, text="Apply monitor/screen", command=self._apply_monitor).pack(side=tk.LEFT)

        sliders = ttk.Frame(render_frame)
        sliders.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(10, 0))
        for name, lo, hi in CRT_PARAMS:
            var = tk.DoubleVar(value=0.0)
            self._crt_vars[name] = var
            row = ttk.Frame(sliders)
            row.pack(side=tk.TOP, fill=tk.X, pady=1)
            ttk.Label(row, text=f"{name}:", width=12, anchor="e").pack(side=tk.LEFT)
            ttk.Scale(row, from_=lo, to=hi, orient=tk.HORIZONTAL, variable=var).pack(
                side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 6)
            )
            value_label = ttk.Label(row, width=6)
            value_label.pack(side=tk.LEFT)
            var.trace_add("write", lambda *_a, v=var, lbl=value_label: lbl.configure(text=f"{v.get():.3f}"))

        ttk.Button(render_frame, text="Apply CRT parameters", command=self._apply_crt).pack(
            side=tk.TOP, anchor="w", pady=(10, 0)
        )

        self._status_var = tk.StringVar()
        ttk.Label(self, textvariable=self._status_var, style="Muted.TLabel").pack(side=tk.TOP, anchor="w", pady=(10, 0))

    def _apply_machine(self):
        model = dict(MODEL_CHOICES)[self._model_var.get()]
        crtc = dict(CRTC_CHOICES)[self._crtc_var.get()]
        body = {"cpc_model": model, "crtc_type": crtc, "rom_lang": self._rom_lang_var.get()}

        def done(_result, error):
            self._status_var.set(f"apply failed: {self.app.describe_error(error)}" if error else "applied (reset triggered)")

        self.app.run_async(lambda: self.app.client.post("/api/config", body), done)

    def _refresh_render(self):
        def done(result, error):
            if error is not None:
                self._status_var.set(f"read failed: {self.app.describe_error(error)}")
                return
            presets = result.get("presets", [])
            self._monitor_combo.configure(values=presets)
            self._monitor_var.set(result.get("monitor_name", presets[0] if presets else ""))
            screen_type = result.get("screen_type", 0)
            name = next((n for n, v in SCREEN_TYPE_CHOICES if v == screen_type), SCREEN_TYPE_CHOICES[0][0])
            self._screen_type_var.set(name)
            for key, value in result.get("crt", {}).items():
                if key in self._crt_vars:
                    self._crt_vars[key].set(value)
            self._status_var.set("render config refreshed")

        self._panel.run(lambda: self.app.client.get("/api/render"), done)

    def _apply_monitor(self):
        presets = list(self._monitor_combo["values"])
        try:
            monitor_idx = presets.index(self._monitor_var.get())
        except ValueError:
            monitor_idx = 0
        screen_type = dict(SCREEN_TYPE_CHOICES)[self._screen_type_var.get()]
        body = {"monitor": monitor_idx, "screen_type": screen_type}

        def done(_result, error):
            self._status_var.set(f"apply failed: {self.app.describe_error(error)}" if error else "monitor/screen applied")

        self.app.run_async(lambda: self.app.client.post("/api/render", body), done)

    def _apply_crt(self):
        crt = {name: self._crt_vars[name].get() for name, *_ in CRT_PARAMS}
        crt["maskType"] = int(crt["maskType"])

        def done(_result, error):
            self._status_var.set(f"apply failed: {self.app.describe_error(error)}" if error else "CRT parameters applied")

        self.app.run_async(lambda: self.app.client.post("/api/render", {"crt": crt}), done)
