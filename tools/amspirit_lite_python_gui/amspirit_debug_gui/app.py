"""Tk root window: connection bar, tab notebook, and the background poller.

Network calls never run on the Tk main thread. PollingManager's worker
thread does the HTTP request and drops the result in a queue; the main
thread only drains that queue (via `root.after`) and touches widgets --
this is what keeps the GUI responsive if the emulator stalls or a request
times out, instead of freezing the whole window for up to `timeout` seconds.
"""

from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from tkinter import ttk

from amspirit_debug_gui import theme
from amspirit_debug_gui.api_client import AmspiritClient, AmspiritApiError, AmspiritConnectionError
from amspirit_debug_gui.sse_client import SseClient
from amspirit_debug_gui.tab_audio import AudioTab
from amspirit_debug_gui.tab_basic import BasicTab
from amspirit_debug_gui.tab_config import ConfigTab
from amspirit_debug_gui.tab_cpu import CpuTab
from amspirit_debug_gui.tab_disk import DiskTab
from amspirit_debug_gui.tab_heatmap import HeatmapTab
from amspirit_debug_gui.tab_keyboard import KeyboardTab
from amspirit_debug_gui.tab_poke import PokeTab
from amspirit_debug_gui.tab_script import ScriptTab
from amspirit_debug_gui.tab_settings import SettingsTab

MODEL_NAMES = {0: "464", 1: "664", 2: "6128", 4: "6128+", 5: "464+", 6: "GX4000"}
CRTC_NAMES = {0: "Type 0", 1: "Type 1", 2: "Type 2", 3: "Type 3", 4: "Type 4"}


class _PollTask:
    __slots__ = ("key", "interval", "fetch", "callback", "active", "next_due")

    def __init__(self, key, interval, fetch, callback, active):
        self.key = key
        self.interval = interval
        self.fetch = fetch
        self.callback = callback
        self.active = active
        self.next_due = 0.0


class PollingManager:
    """One background thread services every registered periodic HTTP fetch."""

    def __init__(self, root: tk.Tk):
        self._root = root
        self._tasks: dict[str, _PollTask] = {}
        self._lock = threading.Lock()
        self._queue: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._root.after(50, self._drain)

    def register(self, key, interval_ms, fetch, callback, active=None):
        with self._lock:
            self._tasks[key] = _PollTask(key, interval_ms / 1000.0, fetch, callback, active or (lambda: True))

    def unregister(self, key):
        with self._lock:
            self._tasks.pop(key, None)

    def trigger(self, key):
        """Make a registered task run on its very next tick, ignoring its interval."""
        with self._lock:
            task = self._tasks.get(key)
            if task:
                task.next_due = 0.0

    def stop(self):
        self._stop.set()

    def _run(self):
        while not self._stop.is_set():
            now = time.monotonic()
            with self._lock:
                due = [t for t in self._tasks.values() if now >= t.next_due and t.active()]
            for t in due:
                try:
                    result = t.fetch()
                    self._queue.put((t.callback, result, None))
                except Exception as e:  # noqa: BLE001 - handed to the callback, never kills the poller
                    self._queue.put((t.callback, None, e))
                t.next_due = time.monotonic() + t.interval
            time.sleep(0.05)

    def _drain(self):
        try:
            while True:
                callback, result, error = self._queue.get_nowait()
                try:
                    callback(result, error)
                except Exception:
                    pass  # a buggy tab callback must not kill the drain loop
        except queue.Empty:
            pass
        if not self._stop.is_set():
            self._root.after(50, self._drain)


class DebugGuiApp(tk.Tk):
    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        super().__init__()
        self.title("AMSpiriT Lite — Debug GUI")
        self.geometry("1180x760")

        # Before any widget is built: apply_theme() populates the option
        # database, which classic Tk widgets read once at construction time
        # and never again. A Text created before this call stays light.
        theme.apply_theme(self)

        self.client = AmspiritClient(host=host, port=port)
        self.poller = PollingManager(self)
        self._tab_keys: list[str] = []
        self.active_tab_key = ""

        # SSE setup happens before the notebook is built: tabs register their
        # own on_sse() listeners (CPU registers/screen, audio waveform, heatmap
        # ticks) from their __init__, which runs during _build_notebook().
        self._sse_listeners: dict[str, list] = {}
        self.sse = SseClient(lambda: self.client.base_url)

        self._build_connection_bar()
        self._build_notebook()
        self._build_status_bar()

        # "ping" stays a slow (1s) fallback poll purely for connection health --
        # same role it plays in amspirit-lite.html, which keeps its own
        # setInterval(refresh, 1000) running alongside SSE. Everything that
        # used to be its own fast poll timer (CPU registers/screen, audio
        # waveform, heatmap ticks) is now paced by the SSE "frame" push
        # instead -- see sse_client.py and each tab's app.on_sse("frame", ...).
        self.poller.register("ping", 1000, lambda: self.client.get("/api/ping"), self._on_ping)
        self.poller.trigger("ping")

        self.on_sse("pause", self._on_sse_pause)
        self.on_sse("__open__", lambda _data: self.poller.trigger("ping"))
        self._drain_sse()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # -- SSE (Server-Sent Events) ---------------------------------------------

    def on_sse(self, topic: str, callback):
        """Register `callback(data)` for every event of `topic` from /api/events.

        `data` is the parsed JSON payload, except for the synthetic topics
        "__open__" (data=None, stream established) and "__error__"
        (data=None, connection lost) that SseClient also emits.
        """
        self._sse_listeners.setdefault(topic, []).append(callback)

    def _drain_sse(self):
        for topic, data, _error in self.sse.drain():
            for callback in self._sse_listeners.get(topic, ()):
                try:
                    callback(data)
                except Exception:
                    pass  # a buggy tab listener must not kill the drain loop
        self.after(50, self._drain_sse)

    def _on_sse_pause(self, data):
        # Immediate badge/button update -- no need to wait for the next
        # 1s "ping" tick, same as amspirit-lite.html's own "pause" listener.
        self._set_paused(bool(data.get("paused")))

    # -- shared helpers used by tab modules ----------------------------------

    def is_tab_active(self, key: str):
        return lambda: self.active_tab_key == key

    def set_status(self, message: str, error: bool = False):
        self._status_var.set(message)
        self._status_label.configure(style="Error.TLabel" if error else "Status.TLabel")

    @staticmethod
    def describe_error(error: BaseException) -> str:
        if isinstance(error, AmspiritApiError):
            return error.error if not error.field else f"{error.error} [{error.field}]"
        if isinstance(error, AmspiritConnectionError):
            return "not connected"
        return str(error)

    # -- connection bar -------------------------------------------------------

    @staticmethod
    def _kv(parent, name: str) -> tk.StringVar:
        """One `name: value` pair, coloured like the HTML's `.kv`/`.vv` pair.

        Returns the StringVar holding the value, so callers keep a handle on
        the half that changes and none on the half that does not.
        """
        var = tk.StringVar(value="--")
        ttk.Label(parent, text=f"{name}:", style="Key.TLabel").pack(side=tk.LEFT)
        ttk.Label(parent, textvariable=var, style="Value2.TLabel").pack(
            side=tk.LEFT, padx=(3, 10))
        return var

    def _build_connection_bar(self):
        bar = ttk.Frame(self, padding=(6, 4))
        bar.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(bar, text="Host:", style="Key.TLabel").pack(side=tk.LEFT)
        self._host_var = tk.StringVar(value=self.client.host)
        ttk.Entry(bar, textvariable=self._host_var, width=14).pack(side=tk.LEFT, padx=(3, 8))

        ttk.Label(bar, text="Port:", style="Key.TLabel").pack(side=tk.LEFT)
        self._port_var = tk.StringVar(value=str(self.client.port))
        ttk.Entry(bar, textvariable=self._port_var, width=6).pack(side=tk.LEFT, padx=(3, 8))

        ttk.Button(bar, text="Connect", command=self._on_connect_clicked).pack(side=tk.LEFT, padx=(0, 10))

        # The Canvas takes the bar's own background, not the option-database
        # default: it sits *on* the bar, and a #252525 square on a #1c1c1c bar
        # would read as a panel rather than as a bare indicator.
        self._dot = tk.Canvas(bar, width=12, height=12, highlightthickness=0,
                              background=theme.C["bg"])
        self._dot.pack(side=tk.LEFT, padx=(0, 8))
        self._dot_item = self._dot.create_oval(1, 1, 11, 11, fill=theme.C["error"], outline="")

        self._model_var = self._kv(bar, "Model")
        self._crtc_var = self._kv(bar, "CRTC")
        self._fps_var = self._kv(bar, "FPS")

        # The HTML's run/pause badge. Redundant with the Pause button's label,
        # deliberately: the button says what clicking will do, the badge says
        # what the machine is doing, and only the badge is visible at a glance.
        self._run_badge = ttk.Label(bar, text="RUN", style="Run.TLabel")
        self._run_badge.pack(side=tk.LEFT, padx=(0, 10))

        self._pause_btn = ttk.Button(bar, text="Pause", command=self._toggle_pause)
        self._pause_btn.pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(bar, text="Soft Reset", style="Amber.TButton",
                   command=self._soft_reset).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(bar, text="Hard Reset", style="Danger.TButton",
                   command=self._hard_reset).pack(side=tk.LEFT)

        self._paused = False

    def _on_connect_clicked(self):
        self.client.host = self._host_var.get().strip() or "127.0.0.1"
        try:
            self.client.port = int(self._port_var.get().strip())
        except ValueError:
            self.set_status("port must be an integer", error=True)
            return
        self.poller.trigger("ping")
        self.sse.reconnect()

    def _on_ping(self, result, error):
        if error is not None:
            self._dot.itemconfigure(self._dot_item, fill=theme.C["error"])
            self._model_var.set("--")
            self._crtc_var.set("--")
            self._fps_var.set("--")
            self.set_status(f"disconnected: {self.describe_error(error)}", error=True)
            return
        self._dot.itemconfigure(self._dot_item, fill=theme.C["ok"])
        emu = result.get("emu", {})
        self._model_var.set(MODEL_NAMES.get(emu.get("cpc_model"), "?"))
        self._crtc_var.set(CRTC_NAMES.get(emu.get("crtc_type"), "?"))
        fps = emu.get("fps")
        self._fps_var.set(f"{fps:.1f}" if isinstance(fps, (int, float)) else "--")
        self._set_paused(bool(emu.get("paused")))
        self.set_status("connected")

    def _set_paused(self, paused: bool):
        """Single place that renders the paused flag, whatever reported it."""
        self._paused = paused
        self._pause_btn.configure(text="Resume" if paused else "Pause")
        self._run_badge.configure(text="PAUSE" if paused else "RUN",
                                  style="Pause.TLabel" if paused else "Run.TLabel")

    def _toggle_pause(self):
        self._post_config({"paused": not self._paused})

    def _soft_reset(self):
        self._post_config({"do_soft_reset": True})

    def _hard_reset(self):
        self._post_config({"do_hard_reset": True})

    def _post_config(self, body: dict):
        def done(_result, error):
            if error is not None:
                self.set_status(f"config update failed: {self.describe_error(error)}", error=True)
            else:
                self.poller.trigger("ping")

        self.run_async(lambda: self.client.post("/api/config", body), done)

    def run_async(self, fetch, on_done):
        """Run `fetch()` off the Tk thread; `on_done(result, error)` runs back on it.

        The one-shot counterpart to PollingManager: every button-triggered
        action (inject BASIC, poke, save disk, ...) uses this so a slow or
        unresponsive emulator never freezes the window.
        """

        def worker():
            try:
                result = fetch()
                error = None
            except Exception as e:  # noqa: BLE001 - handed to on_done, never raised on this thread
                result, error = None, e
            self.after(0, lambda: on_done(result, error))

        threading.Thread(target=worker, daemon=True).start()

    def poll_until_ram_seq(self, seq: int, on_done, max_retries: int = 20):
        """Poll GET /api/state until emu.ram_apply_seq >= seq, then call on_done(True) or on_done(False) on timeout.

        Used by tab_poke to wait for RAM writes to actually be applied (1.14 seq contract).
        Polls every 50ms with a max of max_retries attempts (~1s total by default).

        The HTTP polling loop runs entirely on a background thread -- like
        run_async, `self.client.get()` must never be called directly from a
        Tk `after()` callback, since that runs on the main thread and would
        block the whole window for up to `timeout` seconds per attempt.
        """

        def worker():
            for attempt in range(max_retries):
                try:
                    state = self.client.get("/api/state")
                    current_seq = state.get("emu", {}).get("ram_apply_seq", 0)
                    if current_seq >= seq:
                        self.after(0, lambda: on_done(True))
                        return
                except Exception:
                    pass
                time.sleep(0.05)
            self.after(0, lambda: on_done(False))

        threading.Thread(target=worker, daemon=True).start()

    # -- notebook -------------------------------------------------------------

    def _build_notebook(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=6, pady=(0, 6))

        tabs = [
            ("kbd", "Keyboard", KeyboardTab),
            ("cpu", "CPU / Debug", CpuTab),
            ("basic", "BASIC", BasicTab),
            ("audio", "Audio", AudioTab),
            ("heatmap", "Heat Map", HeatmapTab),
            ("poke", "Poke", PokeTab),
            ("script", "Script", ScriptTab),
            ("config", "Config", ConfigTab),
            ("disk", "Disk", DiskTab),
            ("settings", "Settings", SettingsTab),
        ]
        for key, label, cls in tabs:
            frame = cls(self.notebook, self)
            self.notebook.add(frame, text=label)
            self._tab_keys.append(key)
        self.active_tab_key = self._tab_keys[0]
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    def _on_tab_changed(self, _event=None):
        idx = self.notebook.index(self.notebook.select())
        self.active_tab_key = self._tab_keys[idx]

    # -- status bar -----------------------------------------------------------

    def _build_status_bar(self):
        bar = ttk.Frame(self, padding=(6, 2))
        bar.pack(side=tk.BOTTOM, fill=tk.X)
        self._status_var = tk.StringVar(value="starting…")
        self._status_label = ttk.Label(bar, textvariable=self._status_var,
                                       style="Status.TLabel")
        self._status_label.pack(side=tk.LEFT)

    def _on_close(self):
        self.poller.stop()
        self.sse.stop()
        self.destroy()
