"""Script tab: launch/stop a CSL or Lua script on the emulator's scripting engine."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from amspirit_debug_gui import theme


class ScriptTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=8)
        self.app = app
        self._build()
        app.poller.register(
            "script_state", 1000, lambda: app.client.get("/api/script"), self._on_state,
            active=app.is_tab_active("script"),
        )

    def _build(self):
        top = ttk.Frame(self)
        top.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(top, text="Language:", style="Muted.TLabel").pack(side=tk.LEFT)
        self._lang_var = tk.StringVar(value="csl")
        ttk.Radiobutton(top, text="CSL", value="csl", variable=self._lang_var).pack(side=tk.LEFT, padx=(4, 0))
        ttk.Radiobutton(top, text="Lua 5.4", value="lua", variable=self._lang_var).pack(side=tk.LEFT, padx=(4, 0))
        ttk.Button(top, text="Run", command=self._run).pack(side=tk.LEFT, padx=(16, 0))
        ttk.Button(top, text="Stop", command=self._stop).pack(side=tk.LEFT, padx=(6, 0))

        self._editor = tk.Text(self, font=theme.mono(10))
        self._editor.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(8, 0))
        self._editor.insert("1.0", 'print("hello from script")\n')

        self._state_var = tk.StringVar(value="(state unknown)")
        ttk.Label(self, textvariable=self._state_var, style="Muted.TLabel").pack(side=tk.TOP, anchor="w", pady=(6, 0))

    def _run(self):
        source = self._editor.get("1.0", tk.END)
        lang = self._lang_var.get()
        path = "/api/script" if lang == "csl" else "/api/script?lang=lua"

        def done(_result, error):
            if error is not None:
                self._state_var.set(f"launch failed: {self.app.describe_error(error)}")
            else:
                self.app.poller.trigger("script_state")

        self.app.run_async(lambda: self.app.client.post_text(path, source), done)

    def _stop(self):
        def done(_result, error):
            if error is not None:
                self._state_var.set(f"stop failed: {self.app.describe_error(error)}")
            else:
                self.app.poller.trigger("script_state")

        self.app.run_async(lambda: self.app.client.delete("/api/script"), done)

    def _on_state(self, result, error):
        if error is not None:
            self._state_var.set(f"read failed: {self.app.describe_error(error)}")
            return
        running = result.get("running")
        err = result.get("error", "")
        self._state_var.set(f"running={running}" + (f"  error: {err}" if err else ""))
