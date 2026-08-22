"""CPU / Debug tab: Z80 registers, step controls, RAM dump, breakpoints,
instruction history, GA/CRTC/FDC/PSG circuit panels, and the live screen.

A full Z80 mnemonic disassembler (the original page's "Disassembler" panel)
is intentionally NOT ported -- see the plan/README: it's a standalone effort
(a full opcode table) out of proportion for this GUI's v1. The raw hex/ASCII
RAM dump below covers the same ground textually.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from amspirit_debug_gui.util import ThreadSafeMirror, parse_addr, parse_hex_bytes

Z80_FIELDS = [
    ["PC", "SP", "IX", "IY", "I", "R"],
    ["A", "F", "B", "C", "D", "E", "H", "L"],
    ["A2", "F2", "B2", "C2", "D2", "E2", "H2", "L2"],
    ["IFF1", "IFF2", "IM"],
]


class CpuTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=8)
        self.app = app
        self._z80_labels: dict[str, tk.StringVar] = {}
        self._memmap_region_vars: dict[int, tk.StringVar] = {}
        self._build()

        self._live_screen = ThreadSafeMirror(self._live_screen_var, False)

        app.poller.register("cpu_z80", 500, lambda: app.client.get("/api/z80"), self._on_z80,
                              active=app.is_tab_active("cpu"))
        app.poller.register("cpu_screen", 500, self._fetch_screenshot, self._on_screenshot,
                              active=lambda: self._live_screen.value and app.is_tab_active("cpu")())

    # -- layout ----------------------------------------------------------------

    def _build(self):
        sub = ttk.Notebook(self)
        sub.pack(fill=tk.BOTH, expand=True)
        sub.add(self._build_registers(sub), text="Registers")
        sub.add(self._build_memory(sub), text="Memory")
        sub.add(self._build_memmap(sub), text="Memory Map")
        sub.add(self._build_breakpoints(sub), text="Breakpoints / History")
        sub.add(self._build_circuits(sub), text="Circuits")
        sub.add(self._build_screen(sub), text="Screen")

    def _build_registers(self, parent):
        frame = ttk.Frame(parent, padding=8)
        grid = ttk.Frame(frame)
        grid.pack(side=tk.TOP, anchor="w")
        for row_fields in Z80_FIELDS:
            row_frame = ttk.Frame(grid)
            row_frame.pack(side=tk.TOP, anchor="w", pady=2)
            for name in row_fields:
                var = tk.StringVar(value="--")
                self._z80_labels[name] = var
                ttk.Label(row_frame, text=f"{name}:", width=5, anchor="e").pack(side=tk.LEFT)
                ttk.Label(row_frame, textvariable=var, width=7, foreground="#1a5aab",
                          font=("Courier New", 10, "bold")).pack(side=tk.LEFT, padx=(2, 10))

        btns = ttk.Frame(frame)
        btns.pack(side=tk.TOP, anchor="w", pady=(10, 0))
        ttk.Button(btns, text="Step (1 instruction)", command=self._step).pack(side=tk.LEFT)
        ttk.Button(btns, text="◀ Step Back", command=self._tl_back).pack(side=tk.LEFT, padx=(6, 0))

        self._reg_status_var = tk.StringVar()
        ttk.Label(frame, textvariable=self._reg_status_var, foreground="#555").pack(side=tk.TOP, anchor="w", pady=(6, 0))
        return frame

    def _build_memory(self, parent):
        frame = ttk.Frame(parent, padding=8)
        row = ttk.Frame(frame)
        row.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(row, text="Address:").pack(side=tk.LEFT)
        self._mem_addr_var = tk.StringVar(value="0x0000")
        ttk.Entry(row, textvariable=self._mem_addr_var, width=10).pack(side=tk.LEFT, padx=(2, 8))
        ttk.Label(row, text="Length:").pack(side=tk.LEFT)
        self._mem_len_var = tk.StringVar(value="256")
        ttk.Entry(row, textvariable=self._mem_len_var, width=8).pack(side=tk.LEFT, padx=(2, 8))
        ttk.Label(row, text="Bank:").pack(side=tk.LEFT)
        self._mem_bank_var = tk.StringVar(value="0")
        ttk.Entry(row, textvariable=self._mem_bank_var, width=4).pack(side=tk.LEFT, padx=(2, 8))
        ttk.Button(row, text="Read", command=self._read_ram).pack(side=tk.LEFT)

        search_row = ttk.Frame(frame)
        search_row.pack(side=tk.TOP, fill=tk.X, pady=(6, 0))
        ttk.Label(search_row, text="Find hex:").pack(side=tk.LEFT)
        self._search_var = tk.StringVar()
        ttk.Entry(search_row, textvariable=self._search_var, width=24).pack(side=tk.LEFT, padx=(2, 8))
        ttk.Button(search_row, text="Find in dump", command=self._search_dump).pack(side=tk.LEFT)

        self._dump_text = tk.Text(frame, height=24, font=("Courier New", 10), wrap="none")
        self._dump_text.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(8, 0))
        self._dump_text.configure(state=tk.DISABLED)
        self._dump_bytes = b""
        self._dump_base_addr = 0

        self._mem_status_var = tk.StringVar()
        ttk.Label(frame, textvariable=self._mem_status_var, foreground="#555").pack(side=tk.TOP, anchor="w", pady=(4, 0))
        return frame

    def _build_memmap(self, parent):
        frame = ttk.Frame(parent, padding=8)
        row = ttk.Frame(frame)
        row.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(row, text="ROM/RAM Mapping:").pack(side=tk.LEFT)
        ttk.Button(row, text="Refresh", command=self._refresh_memmap).pack(side=tk.LEFT, padx=(10, 0))

        regions_frame = ttk.LabelFrame(frame, text="16 KB Regions", padding=8)
        regions_frame.pack(side=tk.TOP, fill=tk.X, pady=(8, 0))
        for addr, name in [(0, "0000"), (0x4000, "4000"), (0x8000, "8000"), (0xC000, "C000")]:
            self._create_region_widget(regions_frame, addr, name)

        info_row = ttk.Frame(frame)
        info_row.pack(side=tk.TOP, fill=tk.X, pady=(8, 0))
        ttk.Label(info_row, text="RMR:").pack(side=tk.LEFT)
        self._memmap_rmr_var = tk.StringVar(value="--")
        ttk.Label(info_row, textvariable=self._memmap_rmr_var, font=("Courier New", 10)).pack(side=tk.LEFT, padx=(4, 12))
        ttk.Label(info_row, text="RAM Mode:").pack(side=tk.LEFT)
        self._memmap_mode_var = tk.StringVar(value="--")
        ttk.Label(info_row, textvariable=self._memmap_mode_var, font=("Courier New", 10)).pack(side=tk.LEFT, padx=(4, 12))
        ttk.Label(info_row, text="RAM Page:").pack(side=tk.LEFT)
        self._memmap_page_var = tk.StringVar(value="--")
        ttk.Label(info_row, textvariable=self._memmap_page_var, font=("Courier New", 10)).pack(side=tk.LEFT, padx=(4, 0))

        self._memmap_status_var = tk.StringVar()
        ttk.Label(frame, textvariable=self._memmap_status_var, foreground="#555").pack(side=tk.TOP, anchor="w", pady=(8, 0))
        return frame

    def _create_region_widget(self, parent, addr, name):
        region_frame = ttk.Frame(parent)
        region_frame.pack(side=tk.TOP, fill=tk.X, pady=2)
        ttk.Label(region_frame, text=f"{name}:", width=6, font=("Courier New", 10, "bold")).pack(side=tk.LEFT)
        var = tk.StringVar(value="--")
        self._memmap_region_vars[addr] = var
        ttk.Label(region_frame, textvariable=var, font=("Courier New", 9), foreground="#0066cc").pack(side=tk.LEFT, padx=(4, 0))

    def _refresh_memmap(self):
        def done(result, error):
            if error is not None:
                self._memmap_status_var.set(f"read failed: {self.app.describe_error(error)}")
                return
            self._memmap_rmr_var.set(str(result.get("rmr", "--")))
            self._memmap_mode_var.set(str(result.get("ram_mode", "--")))
            self._memmap_page_var.set(str(result.get("ram_page", "--")))
            for region in result.get("regions", []):
                addr = region.get("base")
                if addr in self._memmap_region_vars:
                    if region.get("rom"):
                        bank = region.get("rom_bank", 255)
                        bank_label = "FW" if bank == 255 else f"ROM{bank}"
                        text = f"ROM {bank_label}"
                    else:
                        ext = " (ext)" if region.get("ext") else ""
                        text = f"RAM bank {region.get('ram_bank', '?')}{ext}"
                    self._memmap_region_vars[addr].set(text)
            self._memmap_status_var.set("memmap refreshed")

        self.app.run_async(lambda: self.app.client.get("/api/memmap"), done)

    def _build_breakpoints(self, parent):
        frame = ttk.Frame(parent, padding=8)
        row = ttk.Frame(frame)
        row.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(row, text="Z80 breakpoints (comma-separated, hex/decimal/Cx:YYYY):").pack(side=tk.LEFT)
        self._bp_var = tk.StringVar()
        ttk.Entry(row, textvariable=self._bp_var).pack(side=tk.TOP, fill=tk.X, pady=(4, 0))
        btns = ttk.Frame(frame)
        btns.pack(side=tk.TOP, fill=tk.X, pady=(6, 0))
        ttk.Button(btns, text="Apply", command=self._apply_bp).pack(side=tk.LEFT)
        ttk.Button(btns, text="Clear all", command=self._clear_bp).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(btns, text="Clear codemap", command=self._clear_codemap).pack(side=tk.LEFT, padx=(6, 0))

        ttk.Label(frame, text="Last 20 executed instructions (oldest first):").pack(
            side=tk.TOP, anchor="w", pady=(12, 2)
        )
        self._history_text = tk.Text(frame, height=14, font=("Courier New", 10))
        self._history_text.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self._history_text.configure(state=tk.DISABLED)
        ttk.Button(frame, text="Refresh history", command=self._refresh_history).pack(side=tk.TOP, anchor="w", pady=(6, 0))

        self._bp_status_var = tk.StringVar()
        ttk.Label(frame, textvariable=self._bp_status_var, foreground="#555").pack(side=tk.TOP, anchor="w", pady=(4, 0))
        return frame

    def _build_circuits(self, parent):
        frame = ttk.Frame(parent, padding=8)
        sub = ttk.Notebook(frame)
        sub.pack(fill=tk.BOTH, expand=True)
        self._circuit_vars: dict[str, tk.StringVar] = {}
        for key, label in (("ga", "Gate Array"), ("crtc", "CRTC"), ("fdc", "FDC"), ("psg", "PSG")):
            page = ttk.Frame(sub, padding=8)
            sub.add(page, text=label)
            var = tk.StringVar(value="(not read yet)")
            self._circuit_vars[key] = var
            ttk.Label(page, textvariable=var, justify=tk.LEFT, font=("Courier New", 10)).pack(
                side=tk.TOP, anchor="nw"
            )
            ttk.Button(page, text="Refresh", command=lambda k=key: self._refresh_circuit(k)).pack(
                side=tk.TOP, anchor="w", pady=(8, 0)
            )
        return frame

    def _build_screen(self, parent):
        frame = ttk.Frame(parent, padding=8)
        top = ttk.Frame(frame)
        top.pack(side=tk.TOP, fill=tk.X)
        self._live_screen_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="Live refresh (500ms)", variable=self._live_screen_var).pack(side=tk.LEFT)
        ttk.Button(top, text="Refresh once", command=lambda: self.app.poller.trigger("cpu_screen")).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        ttk.Button(top, text="Disarm raster breakpoint", command=self._disarm_raster_bp).pack(
            side=tk.LEFT, padx=(8, 0)
        )

        self._screen_label = tk.Label(frame, background="#000", text="(no frame yet)", foreground="#888")
        self._screen_label.pack(side=tk.TOP, pady=(8, 0))
        self._screen_label.bind("<Button-1>", self._on_screen_click)
        self._screen_photo = None
        self._crop = {"x": 0, "y": 0, "w": 1, "h": 1}

        self._screen_status_var = tk.StringVar()
        ttk.Label(frame, textvariable=self._screen_status_var, foreground="#555").pack(side=tk.TOP, anchor="w", pady=(6, 0))
        return frame

    # -- registers ---------------------------------------------------------

    def _on_z80(self, result, error):
        if error is not None:
            self._reg_status_var.set(f"read failed: {self.app.describe_error(error)}")
            return
        for name, var in self._z80_labels.items():
            value = result.get(name)
            if value is None:
                continue
            var.set(f"{value:#06x}" if name not in ("IFF1", "IFF2", "IM") else str(value))

    def _step(self):
        self.app.run_async(lambda: self.app.client.post_empty("/api/step"), self._after_step("stepped"))

    def _tl_back(self):
        self.app.run_async(lambda: self.app.client.post_empty("/api/tl_back"), self._after_step("stepped back"))

    def _after_step(self, verb):
        def done(_result, error):
            if error is not None:
                self._reg_status_var.set(f"{verb} failed: {self.app.describe_error(error)}")
            else:
                self._reg_status_var.set(verb)
                self.app.poller.trigger("cpu_z80")
        return done

    # -- memory --------------------------------------------------------------

    def _read_ram(self):
        try:
            addr = parse_addr(self._mem_addr_var.get())
            length = int(self._mem_len_var.get())
            bank = int(self._mem_bank_var.get() or 0)
        except ValueError as e:
            self._mem_status_var.set(f"bad input: {e}")
            return

        def done(result, error):
            if error is not None:
                self._mem_status_var.set(f"read failed: {self.app.describe_error(error)}")
                return
            self._dump_bytes = bytes.fromhex(result["hex"])
            self._dump_base_addr = addr
            self._render_dump()
            self._mem_status_var.set(f"read {len(self._dump_bytes)} byte(s) from {addr:#06x}")

        self.app.run_async(
            lambda: self.app.client.get(f"/api/ram?addr={addr}&len={length}&bank={bank}"), done
        )

    def _render_dump(self, highlight_offset: int = -1, highlight_len: int = 0):
        lines = []
        data = self._dump_bytes
        for row_start in range(0, len(data), 16):
            chunk = data[row_start:row_start + 16]
            hex_part = " ".join(f"{b:02x}" for b in chunk)
            ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
            lines.append(f"{self._dump_base_addr + row_start:#06x}  {hex_part:<47}  {ascii_part}")
        self._dump_text.configure(state=tk.NORMAL)
        self._dump_text.delete("1.0", tk.END)
        self._dump_text.insert("1.0", "\n".join(lines))
        self._dump_text.configure(state=tk.DISABLED)

    def _search_dump(self):
        try:
            needle = parse_hex_bytes(self._search_var.get())
        except ValueError as e:
            self._mem_status_var.set(f"bad hex: {e}")
            return
        if not needle:
            return
        idx = self._dump_bytes.find(needle)
        if idx < 0:
            self._mem_status_var.set("not found in current dump")
        else:
            self._mem_status_var.set(f"found at {self._dump_base_addr + idx:#06x}")

    # -- breakpoints / history -----------------------------------------------

    def _apply_bp(self):
        body = self._bp_var.get()

        def done(_result, error):
            self._bp_status_var.set(
                f"apply failed: {self.app.describe_error(error)}" if error else "breakpoints applied"
            )

        self.app.run_async(lambda: self.app.client.post_text("/api/z80_bp", body), done)

    def _clear_bp(self):
        self._bp_var.set("")
        self._apply_bp()

    def _clear_codemap(self):
        def done(_result, error):
            self._bp_status_var.set(
                f"clear failed: {self.app.describe_error(error)}" if error else "codemap + history cleared"
            )

        self.app.run_async(lambda: self.app.client.delete("/api/codemap"), done)

    def _refresh_history(self):
        def done(result, error):
            if error is not None:
                self._bp_status_var.set(f"history read failed: {self.app.describe_error(error)}")
                return
            lines = [f"{e['pc']:#06x}  {e['hex']}" for e in result]
            self._history_text.configure(state=tk.NORMAL)
            self._history_text.delete("1.0", tk.END)
            self._history_text.insert("1.0", "\n".join(lines))
            self._history_text.configure(state=tk.DISABLED)

        self.app.run_async(lambda: self.app.client.get("/api/history"), done)

    # -- circuits --------------------------------------------------------------

    def _refresh_circuit(self, key: str):
        def done(result, error):
            if error is not None:
                self._circuit_vars[key].set(f"read failed: {self.app.describe_error(error)}")
                return
            self._circuit_vars[key].set("\n".join(f"{k}: {v}" for k, v in result.items()))

        self.app.run_async(lambda: self.app.client.get(f"/api/{key}"), done)

    # -- screen ------------------------------------------------------------------

    def _fetch_screenshot(self):
        return self.app.client.get_raw("/api/screenshot?crop=1&full=1&live=0")

    def _on_screenshot(self, result, error):
        if error is not None:
            self._screen_status_var.set(f"screenshot failed: {self.app.describe_error(error)}")
            return
        try:
            photo = tk.PhotoImage(data=result.body)
        except tk.TclError:
            self._screen_status_var.set("this Tk build cannot decode PNG images")
            return
        self._screen_photo = photo  # keep a reference alive
        self._screen_label.configure(image=photo, text="")
        headers = result.headers
        try:
            self._crop = {
                "x": int(headers.get("X-Crop-X", 0)),
                "y": int(headers.get("X-Crop-Y", 0)),
                "w": int(headers.get("X-Crop-W", photo.width())),
                "h": int(headers.get("X-Crop-H", photo.height())),
            }
            beam = f"beam=({headers.get('X-Beam-X')},{headers.get('X-Beam-Y')})"
        except (TypeError, ValueError):
            beam = ""
        self._screen_status_var.set(f"{photo.width()}x{photo.height()} {beam}")

    def _on_screen_click(self, event):
        photo = self._screen_photo
        if photo is None:
            return
        w, h = photo.width(), photo.height()
        if w <= 0 or h <= 0:
            return
        crop = self._crop
        buf_x = crop["x"] + int(event.x * crop["w"] / w)
        buf_y = crop["y"] + int(event.y * crop["h"] / h)

        def done(_result, error):
            self._screen_status_var.set(
                f"raster bp failed: {self.app.describe_error(error)}" if error
                else f"raster breakpoint armed at ({buf_x},{buf_y})"
            )

        self.app.run_async(lambda: self.app.client.post_empty(f"/api/raster_bp?x={buf_x}&y={buf_y}"), done)

    def _disarm_raster_bp(self):
        def done(_result, error):
            self._screen_status_var.set(
                f"disarm failed: {self.app.describe_error(error)}" if error else "raster breakpoint disarmed"
            )

        self.app.run_async(lambda: self.app.client.post_empty("/api/raster_bp?enable=0"), done)
