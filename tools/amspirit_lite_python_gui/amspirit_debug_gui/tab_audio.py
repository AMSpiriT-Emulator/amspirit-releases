"""Audio tab: waveform view, device/volume control, WAV export.

No FFT/spectrogram in this v1 (see the plan) -- reproducing those would mean
a manual DFT with no numpy available, out of proportion for a "minimal" GUI.
The waveform itself is genuinely drawn (Canvas polyline from decoded S16LE
samples), not an ASCII approximation.
"""

from __future__ import annotations

import struct
import tkinter as tk
from tkinter import filedialog, ttk

from amspirit_debug_gui.util import ThreadSafeMirror

WINDOW_CHOICES = ["0.1", "0.5", "1", "5", "10"]


class AudioTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=8)
        self.app = app
        self._build()
        self._live = ThreadSafeMirror(self._live_var, False)
        self._window = ThreadSafeMirror(self._window_var, self._window_var.get())
        # Waveform used to poll its own 500ms timer; now it's paced by the SSE
        # "frame" push (~5Hz), same as amspirit-lite.html's refreshAudio() call
        # from its frame listener.
        app.on_sse("frame", self._on_frame)
        app.poller.register(
            "audio_devices", 3000, lambda: app.client.get("/api/audio/devices"),
            self._on_devices, active=app.is_tab_active("audio"),
        )
        app.poller.trigger("audio_devices")

    def _build(self):
        top = ttk.Frame(self)
        top.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(top, text="Window (s):").pack(side=tk.LEFT)
        self._window_var = tk.StringVar(value="1")
        ttk.Combobox(top, textvariable=self._window_var, values=WINDOW_CHOICES, width=5, state="readonly").pack(
            side=tk.LEFT, padx=(2, 10)
        )
        self._live_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="Live refresh", variable=self._live_var).pack(side=tk.LEFT)
        ttk.Button(top, text="Refresh once", command=self._refresh_wave).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        ttk.Button(top, text="Save WAV…", command=self._save_wav).pack(side=tk.LEFT, padx=(8, 0))

        self._canvas = tk.Canvas(self, height=180, background="#0a0a0a", highlightthickness=1)
        self._canvas.pack(side=tk.TOP, fill=tk.X, pady=(8, 0))

        device_row = ttk.Frame(self)
        device_row.pack(side=tk.TOP, fill=tk.X, pady=(10, 0))
        ttk.Label(device_row, text="Output device:").pack(side=tk.LEFT)
        self._device_var = tk.StringVar()
        self._device_combo = ttk.Combobox(device_row, textvariable=self._device_var, state="readonly", width=32)
        self._device_combo.pack(side=tk.LEFT, padx=(4, 6))
        ttk.Button(device_row, text="Apply", command=self._apply_device).pack(side=tk.LEFT)

        vol_row = ttk.Frame(self)
        vol_row.pack(side=tk.TOP, fill=tk.X, pady=(6, 0))
        ttk.Label(vol_row, text="Volume:").pack(side=tk.LEFT)
        self._volume_var = tk.IntVar(value=100)
        ttk.Scale(vol_row, from_=0, to=100, orient=tk.HORIZONTAL, variable=self._volume_var,
                  command=lambda _v: self._on_volume_change()).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 6))
        self._volume_label = ttk.Label(vol_row, text="100%", width=5)
        self._volume_label.pack(side=tk.LEFT)

        self._status_var = tk.StringVar()
        ttk.Label(self, textvariable=self._status_var, foreground="#555").pack(side=tk.TOP, anchor="w", pady=(8, 0))

    def _on_frame(self, _data):
        if self._live.value and self.app.is_tab_active("audio")():
            self._refresh_wave()

    def _refresh_wave(self):
        self.app.run_async(
            lambda: self.app.client.get(f"/api/audio/record?seconds={self._window.value}"), self._on_wave
        )

    def _on_wave(self, result, error):
        self._canvas.delete("all")
        if error is not None:
            self._status_var.set(f"audio read failed: {self.app.describe_error(error)}")
            return
        stereo = result.get("stereo", False)
        raw = bytes.fromhex(result["hex"])
        sample_count = len(raw) // 2
        samples = struct.unpack(f"<{sample_count}h", raw)
        if stereo:
            samples = samples[0::2]  # left channel only, for a simple single trace
        if not samples:
            self._status_var.set("no audio data")
            return
        w = max(self._canvas.winfo_width(), 200)
        h = max(self._canvas.winfo_height(), 100)
        mid = h / 2
        scale = mid / 32768.0
        step = max(1, len(samples) // w)
        points = []
        for i in range(0, len(samples), step):
            x = i / len(samples) * w
            y = mid - samples[i] * scale
            points.extend((x, y))
        if len(points) >= 4:
            self._canvas.create_line(*points, fill="#6fdc6f")
        self._canvas.create_line(0, mid, w, mid, fill="#333")
        self._status_var.set(f"{result.get('hz', '?')} Hz, {result.get('filled_seconds', '?')}s buffered")

    def _on_devices(self, result, error):
        if error is not None:
            return
        devices = [""] + result.get("devices", [])
        self._device_combo.configure(values=devices)
        current = result.get("current", "")
        if not self._device_var.get():
            self._device_var.set(current)

    def _apply_device(self):
        device = self._device_var.get()

        def done(_result, error):
            self._status_var.set(
                f"device change failed: {self.app.describe_error(error)}" if error else f"device set to {device or '(default)'}"
            )

        self.app.run_async(lambda: self.app.client.post("/api/config", {"audio_device": device}), done)

    def _on_volume_change(self):
        value = self._volume_var.get()
        self._volume_label.configure(text=f"{value}%")

        def done(_result, error):
            if error is not None:
                self._status_var.set(f"volume change failed: {self.app.describe_error(error)}")

        self.app.run_async(lambda: self.app.client.post("/api/config", {"volume": value}), done)

    def _save_wav(self):
        path = filedialog.asksaveasfilename(defaultextension=".wav", filetypes=[("WAV audio", "*.wav")])
        if not path:
            return
        seconds = self._window_var.get()

        def done(result, error):
            if error is not None:
                self._status_var.set(f"WAV export failed: {self.app.describe_error(error)}")
                return
            with open(path, "wb") as f:
                f.write(result.body)
            self._status_var.set(f"saved {path}")

        self.app.run_async(lambda: self.app.client.get_raw(f"/api/audio/record?format=wav&seconds={seconds}"), done)
