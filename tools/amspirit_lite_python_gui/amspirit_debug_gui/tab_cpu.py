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

from amspirit_debug_gui import theme
from amspirit_debug_gui.flash import DecayingFlash
from amspirit_debug_gui.util import parse_addr, parse_hex_bytes

# Column geometry of one dump row, as laid out by _dump_line(). Hard-coded
# rather than derived because _patch_dump() addresses individual characters by
# (line, column) to rewrite a single byte in place -- the alternative, redrawing
# the row, would throw away the user's scroll position five times a second.
_COL_HEX = 8            # "0x0000" + two spaces
_COL_ASCII = _COL_HEX + 47 + 2   # 16 bytes as "xx " (47 chars) + two spaces
_BYTES_PER_ROW = 16

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

        # Six Panels, one per sub-view. Each refreshes only while it is the
        # visible one -- opening "CPU / Debug" no longer costs nine requests
        # for the eight sub-views nobody is looking at.
        #
        # `pause_tick` on registers and memory: single-stepping and poking are
        # exactly the things done while paused, and they must be seen to work.
        # The screen and the circuits genuinely stop when the emulator does.
        self._reg_panel = app.register_panel(
            self._reg_frame, "C", self._refresh_z80, pause_tick=True)
        self._mem_panel = app.register_panel(
            self._mem_frame, "C", self._refresh_dump, pause_tick=True)
        self._memmap_panel = app.register_panel(
            self._memmap_frame, "C", self._refresh_memmap)
        self._history_panel = app.register_panel(
            self._history_frame, "C", self._refresh_history)
        # One Panel per circuit page, not one for the group: they live in a
        # nested notebook, so only the selected one is Visible.
        self._circuit_panels = {
            key: app.register_panel(page, "C", lambda k=key: self._refresh_circuit(k))
            for key, page in self._circuit_pages.items()
        }
        self._screen_panel = app.register_panel(
            self._screen_frame, "C", self._refresh_screenshot,
            gate=self._live_screen_var.get)

        # A breakpoint hit is the one thing that must not wait for the next
        # ~5Hz frame tick -- and it arrives precisely when frames stop.
        app.on_sse("z80_bp", self._on_z80_bp)

    # -- layout ----------------------------------------------------------------

    def _build(self):
        sub = ttk.Notebook(self)
        sub.pack(fill=tk.BOTH, expand=True)
        # Each sub-frame is kept: it is the widget whose visibility gates its
        # Panel, so the refresh machinery can ask Tk directly rather than
        # tracking which tab is selected.
        self._reg_frame = self._build_registers(sub)
        self._mem_frame = self._build_memory(sub)
        self._memmap_frame = self._build_memmap(sub)
        self._history_frame = self._build_breakpoints(sub)
        self._circuits_frame = self._build_circuits(sub)
        self._screen_frame = self._build_screen(sub)
        sub.add(self._reg_frame, text="Registers")
        sub.add(self._mem_frame, text="Memory")
        sub.add(self._memmap_frame, text="Memory Map")
        sub.add(self._history_frame, text="Breakpoints / History")
        sub.add(self._circuits_frame, text="Circuits")
        sub.add(self._screen_frame, text="Screen")

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
                ttk.Label(row_frame, text=f"{name}:", width=5, anchor="e",
                          style="Muted.TLabel").pack(side=tk.LEFT)
                ttk.Label(row_frame, textvariable=var, width=7,
                          style="Value.TLabel").pack(side=tk.LEFT, padx=(2, 10))

        btns = ttk.Frame(frame)
        btns.pack(side=tk.TOP, anchor="w", pady=(10, 0))
        ttk.Button(btns, text="Step (1 instruction)", command=self._step).pack(side=tk.LEFT)
        ttk.Button(btns, text="◀ Step Back", command=self._tl_back).pack(side=tk.LEFT, padx=(6, 0))

        self._reg_status_var = tk.StringVar()
        ttk.Label(frame, textvariable=self._reg_status_var, style="Muted.TLabel").pack(side=tk.TOP, anchor="w", pady=(6, 0))
        return frame

    def _build_memory(self, parent):
        frame = ttk.Frame(parent, padding=8)
        row = ttk.Frame(frame)
        row.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(row, text="Address:", style="Muted.TLabel").pack(side=tk.LEFT)
        self._mem_addr_var = tk.StringVar(value="0x0000")
        addr_entry = ttk.Entry(row, textvariable=self._mem_addr_var, width=10)
        addr_entry.pack(side=tk.LEFT, padx=(2, 8))
        ttk.Label(row, text="Length:", style="Muted.TLabel").pack(side=tk.LEFT)
        self._mem_len_var = tk.StringVar(value="256")
        ttk.Entry(row, textvariable=self._mem_len_var, width=8).pack(side=tk.LEFT, padx=(2, 8))
        ttk.Label(row, text="Bank:", style="Muted.TLabel").pack(side=tk.LEFT)
        self._mem_bank_var = tk.StringVar(value="0")
        ttk.Entry(row, textvariable=self._mem_bank_var, width=4).pack(side=tk.LEFT, padx=(2, 8))
        # No longer "Read": the dump reads itself. This *moves the window*,
        # which is why the entries are only consulted when it is pressed --
        # sampling them every tick would fire requests at half-typed addresses.
        ttk.Button(row, text="Go", command=self._go_to_address).pack(side=tk.LEFT)
        addr_entry.bind("<Return>", lambda _e: self._go_to_address())

        search_row = ttk.Frame(frame)
        search_row.pack(side=tk.TOP, fill=tk.X, pady=(6, 0))
        ttk.Label(search_row, text="Find hex:", style="Muted.TLabel").pack(side=tk.LEFT)
        self._search_var = tk.StringVar()
        ttk.Entry(search_row, textvariable=self._search_var, width=24).pack(side=tk.LEFT, padx=(2, 8))
        ttk.Button(search_row, text="Find in dump", command=self._search_dump).pack(side=tk.LEFT)

        self._dump_text = tk.Text(frame, height=24, font=theme.mono(10), wrap="none")
        self._dump_text.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(8, 0))
        self._dump_text.configure(state=tk.DISABLED)
        self._dump_flash = DecayingFlash(self._dump_text, theme.C["flash_accent"],
                                         theme.C["fg"])
        self._dump_bytes = b""
        # The window the live refresh reads, committed by "Go" -- distinct from
        # what the entries currently contain, which is whatever is being typed.
        self._dump_base_addr = 0
        self._dump_len = 256
        self._dump_bank = 0

        self._mem_status_var = tk.StringVar()
        ttk.Label(frame, textvariable=self._mem_status_var, style="Muted.TLabel").pack(side=tk.TOP, anchor="w", pady=(4, 0))
        return frame

    def _build_memmap(self, parent):
        frame = ttk.Frame(parent, padding=8)
        row = ttk.Frame(frame)
        row.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(row, text="ROM/RAM Mapping:", style="Muted.TLabel").pack(side=tk.LEFT)

        regions_frame = ttk.LabelFrame(frame, text="16 KB Regions", padding=8)
        regions_frame.pack(side=tk.TOP, fill=tk.X, pady=(8, 0))
        for addr, name in [(0, "0000"), (0x4000, "4000"), (0x8000, "8000"), (0xC000, "C000")]:
            self._create_region_widget(regions_frame, addr, name)

        info_row = ttk.Frame(frame)
        info_row.pack(side=tk.TOP, fill=tk.X, pady=(8, 0))
        ttk.Label(info_row, text="RMR:", style="Muted.TLabel").pack(side=tk.LEFT)
        self._memmap_rmr_var = tk.StringVar(value="--")
        ttk.Label(info_row, textvariable=self._memmap_rmr_var, font=theme.mono(10)).pack(side=tk.LEFT, padx=(4, 12))
        ttk.Label(info_row, text="RAM Mode:", style="Muted.TLabel").pack(side=tk.LEFT)
        self._memmap_mode_var = tk.StringVar(value="--")
        ttk.Label(info_row, textvariable=self._memmap_mode_var, font=theme.mono(10)).pack(side=tk.LEFT, padx=(4, 12))
        ttk.Label(info_row, text="RAM Page:", style="Muted.TLabel").pack(side=tk.LEFT)
        self._memmap_page_var = tk.StringVar(value="--")
        ttk.Label(info_row, textvariable=self._memmap_page_var, font=theme.mono(10)).pack(side=tk.LEFT, padx=(4, 0))

        self._memmap_status_var = tk.StringVar()
        ttk.Label(frame, textvariable=self._memmap_status_var, style="Muted.TLabel").pack(side=tk.TOP, anchor="w", pady=(8, 0))
        return frame

    def _create_region_widget(self, parent, addr, name):
        region_frame = ttk.Frame(parent)
        region_frame.pack(side=tk.TOP, fill=tk.X, pady=2)
        ttk.Label(region_frame, text=f"{name}:", width=6, style="Key.TLabel").pack(side=tk.LEFT)
        var = tk.StringVar(value="--")
        self._memmap_region_vars[addr] = var
        ttk.Label(region_frame, textvariable=var, style="Value2.TLabel").pack(side=tk.LEFT, padx=(4, 0))

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

        self._memmap_panel.run(lambda: self.app.client.get("/api/memmap"), done)

    def _build_breakpoints(self, parent):
        frame = ttk.Frame(parent, padding=8)
        row = ttk.Frame(frame)
        row.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(row, text="Z80 breakpoints (comma-separated, hex/decimal/Cx:YYYY):", style="Muted.TLabel").pack(side=tk.LEFT)
        self._bp_var = tk.StringVar()
        ttk.Entry(row, textvariable=self._bp_var).pack(side=tk.TOP, fill=tk.X, pady=(4, 0))
        btns = ttk.Frame(frame)
        btns.pack(side=tk.TOP, fill=tk.X, pady=(6, 0))
        ttk.Button(btns, text="Apply", command=self._apply_bp).pack(side=tk.LEFT)
        ttk.Button(btns, text="Clear all", command=self._clear_bp).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(btns, text="Clear codemap", command=self._clear_codemap).pack(side=tk.LEFT, padx=(6, 0))

        ttk.Label(frame, text="Last 20 executed instructions (oldest first):", style="Muted.TLabel").pack(
            side=tk.TOP, anchor="w", pady=(12, 2)
        )
        self._history_text = tk.Text(frame, height=14, font=theme.mono(10))
        self._history_text.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self._history_text.configure(state=tk.DISABLED)

        self._bp_status_var = tk.StringVar()
        ttk.Label(frame, textvariable=self._bp_status_var, style="Muted.TLabel").pack(side=tk.TOP, anchor="w", pady=(4, 0))
        return frame

    def _build_circuits(self, parent):
        frame = ttk.Frame(parent, padding=8)
        sub = ttk.Notebook(frame)
        sub.pack(fill=tk.BOTH, expand=True)
        self._circuit_vars: dict[str, tk.StringVar] = {}
        self._circuit_pages: dict[str, ttk.Frame] = {}
        for key, label in (("ga", "Gate Array"), ("crtc", "CRTC"), ("fdc", "FDC"), ("psg", "PSG")):
            page = ttk.Frame(sub, padding=8)
            sub.add(page, text=label)
            var = tk.StringVar(value="(not read yet)")
            self._circuit_vars[key] = var
            self._circuit_pages[key] = page
            ttk.Label(page, textvariable=var, justify=tk.LEFT, font=theme.mono(10)).pack(
                side=tk.TOP, anchor="nw"
            )
        return frame

    def _build_screen(self, parent):
        frame = ttk.Frame(parent, padding=8)
        top = ttk.Frame(frame)
        top.pack(side=tk.TOP, fill=tk.X)
        self._live_screen_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="Live refresh", variable=self._live_screen_var).pack(side=tk.LEFT)
        ttk.Button(top, text="Refresh once", command=self._refresh_screenshot).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        ttk.Button(top, text="Disarm raster breakpoint", command=self._disarm_raster_bp).pack(
            side=tk.LEFT, padx=(8, 0)
        )

        # The CPC's own output: black, not the panel grey, so the emulated
        # border stays distinguishable from the widget it sits in.
        self._screen_label = tk.Label(frame, background=theme.C["screen_bg"],
                                      text="(no frame yet)", foreground=theme.C["muted"])
        self._screen_label.pack(side=tk.TOP, pady=(8, 0))
        self._screen_label.bind("<Button-1>", self._on_screen_click)
        self._screen_photo = None
        self._crop = {"x": 0, "y": 0, "w": 1, "h": 1}

        self._screen_status_var = tk.StringVar()
        ttk.Label(frame, textvariable=self._screen_status_var, style="Muted.TLabel").pack(side=tk.TOP, anchor="w", pady=(6, 0))
        return frame

    # -- registers ---------------------------------------------------------

    def _on_z80_bp(self, data):
        """SSE "z80_bp": a breakpoint hit both stops the frames and is the
        moment the state matters most, so it invalidates everything at once
        rather than refreshing this tab's two panels and leaving the rest of
        the window showing pre-breakpoint values."""
        self._reg_status_var.set(f"Z80 breakpoint @ {data.get('pc', '????')}")
        self.app.invalidate()

    def _refresh_z80(self):
        self._reg_panel.run(lambda: self.app.client.get("/api/z80"), self._on_z80)

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
                # A step moves the whole machine, not just the registers: the
                # dump, the memory map and the history are all stale now, and
                # no "frame" event will say so while paused.
                self.app.invalidate()
        return done

    # -- memory --------------------------------------------------------------

    def _go_to_address(self):
        """Commit the entries as the window the live dump reads from."""
        try:
            self._dump_base_addr = parse_addr(self._mem_addr_var.get())
            self._dump_len = int(self._mem_len_var.get())
            self._dump_bank = int(self._mem_bank_var.get() or 0)
        except ValueError as e:
            self._mem_status_var.set(f"bad input: {e}")
            return
        self._dump_bytes = b""  # force a relayout at the new address
        self._refresh_dump()

    def _refresh_dump(self):
        addr, length, bank = self._dump_base_addr, self._dump_len, self._dump_bank

        def done(result, error):
            if error is not None:
                self._mem_status_var.set(f"read failed: {self.app.describe_error(error)}")
                return
            self._apply_dump(bytes.fromhex(result["hex"]))

        self._mem_panel.run(
            lambda: self.app.client.get(f"/api/ram?addr={addr}&len={length}&bank={bank}"), done
        )

    def _apply_dump(self, data: bytes):
        """Show `data`, touching only the characters whose bytes actually moved.

        Rewriting the whole Text would reset the scroll position and any
        selection several times a second, which is the difference between a
        live dump and an unusable one (see CONTEXT.md, and the "never
        reconstruct" rule this Panel is the hardest case for).
        """
        if len(data) != len(self._dump_bytes):
            self._dump_bytes = data
            self._relayout_dump()
            self._mem_status_var.set(
                f"{len(data)} byte(s) from {self._dump_base_addr:#06x}"
                f"{f' bank {self._dump_bank}' if self._dump_bank else ''}")
            return

        previous, self._dump_bytes = self._dump_bytes, data
        changed = [i for i in range(len(data)) if data[i] != previous[i]]
        if not changed:
            return
        # Patching is cheaper than redrawing only while the changes are sparse:
        # each byte costs four Tk calls, so a window over screen RAM -- where
        # nearly every byte moves every frame -- would cost more in tag
        # bookkeeping than the redraw it was avoiding. Past half the window,
        # redraw instead, and skip the flash: "everything changed" is not a
        # useful thing to highlight.
        if len(changed) * 2 > len(data):
            self._relayout_dump(keep_scroll=True)
            return
        self._dump_text.configure(state=tk.NORMAL)
        for offset in changed:
            self._patch_byte(offset, data[offset])
        self._dump_text.configure(state=tk.DISABLED)

    def _patch_byte(self, offset: int, value: int):
        line = offset // _BYTES_PER_ROW + 1
        col = offset % _BYTES_PER_ROW
        for start_col, text in ((_COL_HEX + col * 3, f"{value:02x}"),
                                (_COL_ASCII + col, chr(value) if 32 <= value < 127 else ".")):
            start = f"{line}.{start_col}"
            end = f"{line}.{start_col + len(text)}"
            self._dump_text.replace(start, end, text)
            self._dump_flash.flash(start, end)

    def _relayout_dump(self, keep_scroll: bool = False):
        """Full redraw, for a new window or a wholesale change.

        `keep_scroll` restores the viewport afterwards: a redraw driven by the
        data changing must not move the user, whereas a redraw driven by "Go"
        should land at the top of the new address.
        """
        data = self._dump_bytes
        top = self._dump_text.yview()[0] if keep_scroll else None
        lines = []
        for row_start in range(0, len(data), _BYTES_PER_ROW):
            chunk = data[row_start:row_start + _BYTES_PER_ROW]
            hex_part = " ".join(f"{b:02x}" for b in chunk)
            ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
            lines.append(f"{self._dump_base_addr + row_start:#06x}  {hex_part:<47}  {ascii_part}")
        self._dump_flash.clear()
        self._dump_text.configure(state=tk.NORMAL)
        self._dump_text.delete("1.0", tk.END)
        self._dump_text.insert("1.0", "\n".join(lines))
        self._dump_text.configure(state=tk.DISABLED)
        if top is not None:
            self._dump_text.yview_moveto(top)

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

        self._history_panel.run(lambda: self.app.client.get("/api/history"), done)

    # -- circuits --------------------------------------------------------------

    def _refresh_circuit(self, key: str):
        def done(result, error):
            if error is not None:
                self._circuit_vars[key].set(f"read failed: {self.app.describe_error(error)}")
                return
            self._circuit_vars[key].set("\n".join(f"{k}: {v}" for k, v in result.items()))

        self._circuit_panels[key].run(lambda: self.app.client.get(f"/api/{key}"), done)

    # -- screen ------------------------------------------------------------------

    def _fetch_screenshot(self):
        return self.app.client.get_raw("/api/screenshot?crop=1&full=1&live=0")

    def _refresh_screenshot(self):
        self._screen_panel.run(self._fetch_screenshot, self._on_screenshot)

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
