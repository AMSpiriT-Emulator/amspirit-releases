"""BASIC tab: listing, editor, stepping/breakpoints, and variables/arrays.

Variable/array decoding walks the same in-RAM Locomotive BASIC layout the
original page's JS decodes client-side (see util.parse_basic_vars /
parse_basic_arrays); the variables Panel issues the same chain of requests the
page does: GET /api/basic_state for the pointers, then three targeted
GET /api/ram reads (chain table, scalar zone, array zone).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from amspirit_debug_gui import theme
from amspirit_debug_gui.util import parse_basic_arrays, parse_basic_vars


class BasicTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=8)
        self.app = app
        self._listing_data = None
        self._basic_state = {}
        self._current_line = None
        self._var_items: dict[str, str] = {}
        self._array_items: dict[str, str] = {}
        self._build()

        # Three Panels, and the split between the first two is the whole point
        # of this tab. The listing *text* only changes when the program is
        # edited; the *highlight* moves with every statement executed. Driving
        # both from one refresh would force a choice between a frozen listing
        # and one that redraws -- losing scroll and selection -- five times a
        # second. So: text on wake, highlight on push.
        self._listing_panel = app.register_panel(
            self._listing_frame, "A", self._refresh_listing)
        self._state_panel = app.register_panel(
            self, "C", self._refresh_state, pause_tick=True)
        # Four chained requests per refresh. It keeps up when the program is
        # small and quietly runs slower when it is not, because the in-flight
        # guard drops ticks rather than queueing them.
        self._vars_panel = app.register_panel(
            self._vars_frame, "C", self._refresh_vars, pause_tick=True)

    def _build(self):
        info = ttk.Frame(self)
        info.pack(side=tk.TOP, fill=tk.X)
        self._info_var = tk.StringVar(value="(no BASIC state read yet)")
        ttk.Label(info, textvariable=self._info_var, font=theme.mono(9)).pack(side=tk.LEFT)

        controls = ttk.Frame(self)
        controls.pack(side=tk.TOP, fill=tk.X, pady=(6, 0))
        ttk.Button(controls, text="Step statement", command=lambda: self._step(line=False)).pack(side=tk.LEFT)
        ttk.Button(controls, text="Step line", command=lambda: self._step(line=True)).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(controls, text="◀ Step back", command=self._tl_back).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Label(controls, text="  Run to line:", style="Muted.TLabel").pack(side=tk.LEFT)
        self._runto_var = tk.StringVar()
        ttk.Entry(controls, textvariable=self._runto_var, width=6).pack(side=tk.LEFT)
        ttk.Button(controls, text="Go", command=self._run_to).pack(side=tk.LEFT, padx=(4, 0))

        bp_row = ttk.Frame(self)
        bp_row.pack(side=tk.TOP, fill=tk.X, pady=(6, 0))
        ttk.Label(bp_row, text="Line breakpoints (comma-separated):", style="Muted.TLabel").pack(side=tk.LEFT)
        self._bp_var = tk.StringVar()
        ttk.Entry(bp_row, textvariable=self._bp_var, width=24).pack(side=tk.LEFT, padx=(4, 6))
        ttk.Button(bp_row, text="Apply", command=self._apply_bp).pack(side=tk.LEFT)
        ttk.Button(bp_row, text="Clear", command=self._clear_bp).pack(side=tk.LEFT, padx=(6, 0))

        sub = ttk.Notebook(self)
        sub.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(8, 0))
        self._listing_frame = self._build_listing(sub)
        self._vars_frame = self._build_variables(sub)
        sub.add(self._listing_frame, text="Listing")
        sub.add(self._build_editor(sub), text="Editor")
        sub.add(self._vars_frame, text="Variables")

        self._status_var = tk.StringVar()
        ttk.Label(self, textvariable=self._status_var, style="Muted.TLabel").pack(side=tk.TOP, anchor="w", pady=(6, 0))

    def _build_listing(self, parent):
        frame = ttk.Frame(parent, padding=6)
        self._listing_text = tk.Text(frame, font=theme.mono(10))
        self._listing_text.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(6, 0))
        # Was a pale-yellow highlight, which only works on a light listing.
        # The dark equivalent is the HTML's own "you are here" pairing:
        # a near-black amber wash under amber text.
        self._listing_text.tag_configure("current", background=theme.C["flash_bg"],
                                         foreground=theme.C["flash_accent"])
        self._listing_text.configure(state=tk.DISABLED)
        return frame

    def _build_editor(self, parent):
        frame = ttk.Frame(parent, padding=6)
        btns = ttk.Frame(frame)
        btns.pack(side=tk.TOP, fill=tk.X)
        ttk.Button(btns, text="Inject", command=lambda: self._inject(reset=False, run=False)).pack(side=tk.LEFT)
        ttk.Button(btns, text="Inject + RUN", command=lambda: self._inject(reset=False, run=True)).pack(
            side=tk.LEFT, padx=(6, 0)
        )
        ttk.Button(btns, text="Reset + Inject + RUN", command=lambda: self._inject(reset=True, run=True)).pack(
            side=tk.LEFT, padx=(6, 0)
        )
        ttk.Button(btns, text="Export from CPC", command=self._export).pack(side=tk.LEFT, padx=(16, 0))
        ttk.Button(btns, text="Save .bas…", command=self._save_bas).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(btns, text="Load .bas…", command=self._load_bas).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(btns, text="Clear", command=lambda: self._editor.delete("1.0", tk.END)).pack(
            side=tk.LEFT, padx=(6, 0)
        )

        self._editor = tk.Text(frame, font=theme.mono(10))
        self._editor.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(6, 0))
        self._editor.insert("1.0", '10 PRINT "HELLO"\n20 GOTO 10\n')
        return frame

    def _build_variables(self, parent):
        frame = ttk.Frame(parent, padding=6)
        button_row = ttk.Frame(frame)
        button_row.pack(side=tk.TOP, fill=tk.X)
        ttk.Button(button_row, text="Scan pointers", command=self._scan_pointers).pack(side=tk.LEFT, padx=(8, 0))

        ttk.Label(frame, text="Scalars:", style="Muted.TLabel").pack(side=tk.TOP, anchor="w", pady=(8, 2))
        self._vars_tree = ttk.Treeview(frame, columns=("type", "value", "addr"), show="tree headings", height=8)
        self._vars_tree.heading("#0", text="Name")
        for col, label in (("type", "Type"), ("value", "Value"), ("addr", "Addr")):
            self._vars_tree.heading(col, text=label)
        self._vars_tree.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(frame, text="Arrays:", style="Muted.TLabel").pack(side=tk.TOP, anchor="w", pady=(8, 2))
        self._arrays_tree = ttk.Treeview(
            frame, columns=("type", "dims", "elements", "addr"), show="tree headings", height=6
        )
        self._arrays_tree.heading("#0", text="Name")
        for col, label in (("type", "Type"), ("dims", "Dims"), ("elements", "Elements (first 20)"), ("addr", "Addr")):
            self._arrays_tree.heading(col, text=label)
        self._arrays_tree.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(0, 0))
        return frame

    # -- state / listing -------------------------------------------------------

    def _refresh_state(self):
        def done(result, error):
            if error is not None:
                self._status_var.set(f"basic_state failed: {self.app.describe_error(error)}")
                return
            self._basic_state = result
            line = result.get("cur_linenum")
            line_txt = "direct mode" if line == 0xFFFF else str(line)
            self._info_var.set(
                f"loaded={result.get('loaded')}  size={result.get('prog_size')}B  "
                f"line={line_txt}  stmt_addr={result.get('stmt_addr'):#06x}  "
                f"basic_ver={result.get('basic_ver')}"
            )
            self._highlight_current()

        self._state_panel.run(lambda: self.app.client.get("/api/basic_state"), done)

    def _refresh_listing(self):
        def done(result, error):
            if error is not None:
                self._status_var.set(f"listing failed: {self.app.describe_error(error)}")
                return
            if result == self._listing_data:
                return  # identical program: redrawing would only lose the scroll
            self._listing_data = result
            self._render_listing()

        self._listing_panel.run(lambda: self.app.client.get("/api/basic_listing"), done)

    def _render_listing(self):
        self._listing_text.configure(state=tk.NORMAL)
        self._listing_text.delete("1.0", tk.END)
        if not self._listing_data:
            self._listing_text.configure(state=tk.DISABLED)
            return
        for line in self._listing_data.get("lines", []):
            parts = []
            for stmt in line.get("stmts", []):
                prefix = ":" if stmt.get("colon") else ""
                parts.append(f"{prefix}{stmt['text']}")
            text = f"{line['num']:>5} " + "".join(parts) + "\n"
            self._listing_text.insert(tk.END, text)
        self._listing_text.configure(state=tk.DISABLED)
        self._current_line = None  # the tag went with the old text
        self._highlight_current()

    def _highlight_current(self):
        """Move the "you are here" tag, and only if it actually moved.

        Called ~5 times a second. Re-tagging unconditionally would be cheap,
        but the `see()` below is not: scrolling the listing to the current line
        on every tick would make it impossible to look anywhere else while the
        program runs. Following execution should mean following it when it
        moves, not fighting the user's scrollbar continuously.
        """
        cur_line = self._basic_state.get("cur_linenum") if self._basic_state else None
        if cur_line == self._current_line:
            return
        self._current_line = cur_line
        self._listing_text.tag_remove("current", "1.0", tk.END)
        if not self._listing_data:
            return
        for idx, line in enumerate(self._listing_data.get("lines", [])):
            if line["num"] == cur_line:
                self._listing_text.tag_add("current", f"{idx + 1}.0", f"{idx + 1}.end")
                self._listing_text.see(f"{idx + 1}.0")
                break

    # -- step / run-to / breakpoints ---------------------------------------

    def _step(self, line: bool):
        path = "/api/basic_step?mode=line" if line else "/api/basic_step"

        def done(_result, error):
            self._status_var.set(f"step failed: {self.app.describe_error(error)}" if error else "stepped")
            if not error:
                self.app.invalidate()

        self.app.run_async(lambda: self.app.client.post_empty(path), done)

    def _tl_back(self):
        def done(_result, error):
            self._status_var.set(f"step back failed: {self.app.describe_error(error)}" if error else "stepped back")
            if not error:
                self.app.invalidate()

        self.app.run_async(lambda: self.app.client.post_empty("/api/tl_back"), done)

    def _run_to(self):
        line = self._runto_var.get().strip()
        if not line:
            return

        def done(_result, error):
            self._status_var.set(f"run-to failed: {self.app.describe_error(error)}" if error else f"ran to line {line}")
            if not error:
                self.app.invalidate()

        self.app.run_async(lambda: self.app.client.post_empty(f"/api/basic_runto?line={line}"), done)

    def _apply_bp(self):
        body = self._bp_var.get()

        def done(_result, error):
            self._status_var.set(
                f"breakpoints failed: {self.app.describe_error(error)}" if error else "breakpoints applied"
            )

        self.app.run_async(lambda: self.app.client.post_text("/api/basic_bp", body), done)

    def _clear_bp(self):
        self._bp_var.set("")
        self._apply_bp()

    # -- inject / export ------------------------------------------------------

    def _inject(self, reset: bool, run: bool):
        source = self._editor.get("1.0", tk.END)
        query = f"?reset={1 if reset else 0}&run={1 if run else 0}"

        def done(_result, error):
            self._status_var.set(
                f"inject failed: {self.app.describe_error(error)}" if error else "injected — type LIST or RUN"
            )
            if not error:
                self.app.invalidate()

        self.app.run_async(lambda: self.app.client.post_text(f"/api/basic{query}", source), done)

    def _export(self):
        def done(result, error):
            if error is not None:
                self._status_var.set(f"export failed: {self.app.describe_error(error)}")
                return
            self._editor.delete("1.0", tk.END)
            self._editor.insert("1.0", result.body.decode("utf-8", errors="replace"))
            self._status_var.set("exported from CPC")

        self.app.run_async(lambda: self.app.client.get_raw("/api/basic_export?verbose=1"), done)

    def _save_bas(self):
        path = filedialog.asksaveasfilename(defaultextension=".bas", filetypes=[("BASIC files", "*.bas")])
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(self._editor.get("1.0", tk.END))
        self._status_var.set(f"saved {path}")

    def _load_bas(self):
        path = filedialog.askopenfilename(filetypes=[("BASIC files", "*.bas"), ("All files", "*.*")])
        if not path:
            return
        with open(path, encoding="utf-8") as f:
            content = f.read()
        self._editor.delete("1.0", tk.END)
        self._editor.insert("1.0", content)
        self._status_var.set(f"loaded {path}")

    # -- variables ---------------------------------------------------------------

    def _refresh_vars(self):
        if not self._vars_panel.begin():
            return

        def fail(error):
            self._vars_panel.end()
            self._status_var.set(f"variables failed: {self.app.describe_error(error)}")

        def got_state(state, error):
            if error is not None:
                return fail(error)
            txttop, vartop, arrend = state["txttop"], state["vartop"], state["arrend"]
            chain_addr = state["chain_heads_addr"]

            def got_chain(chain_resp, error):
                if error is not None:
                    return fail(error)
                chain_bytes = bytes.fromhex(chain_resp["hex"])

                def got_zones(zones, error):
                    if error is not None:
                        return fail(error)
                    var_bytes, arr_bytes = zones
                    self._vars_panel.end()
                    self._populate_vars(parse_basic_vars(chain_bytes, var_bytes, txttop))
                    self._populate_arrays(parse_basic_arrays(arr_bytes))

                self._fetch_zones(txttop, vartop, arrend, got_zones)

            self.app.run_async(lambda: self.app.client.get(f"/api/ram?addr={chain_addr}&len=54"), got_chain)

        self.app.run_async(lambda: self.app.client.get("/api/basic_state"), got_state)

    def _fetch_zones(self, txttop, vartop, arrend, callback):
        var_len = max(0, vartop - txttop)
        arr_len = max(0, arrend - vartop)

        def fetch():
            var_bytes = b""
            if var_len:
                var_bytes = bytes.fromhex(self.app.client.get(f"/api/ram?addr={txttop}&len={var_len}")["hex"])
            arr_bytes = b""
            if arr_len:
                arr_bytes = bytes.fromhex(self.app.client.get(f"/api/ram?addr={vartop}&len={arr_len}")["hex"])
            return var_bytes, arr_bytes

        self.app.run_async(fetch, callback)

    def _populate_vars(self, variables):
        self._sync_tree(
            self._vars_tree, self._var_items,
            [(v["name"], (v["type"], v["value"], f"{v['addr']:#06x}")) for v in variables])

    def _populate_arrays(self, arrays):
        rows = []
        for a in arrays:
            elements = ", ".join(a["elements"][:20]) + ("…" if len(a["elements"]) > 20 else "")
            rows.append((a["name"], (a["type"], "×".join(str(d) for d in a["dims"]),
                                     elements, f"{a['addr']:#06x}")))
        self._sync_tree(self._arrays_tree, self._array_items, rows)

    def _sync_tree(self, tree, items: dict, rows):
        """Reconcile a Treeview against `rows` in place, flashing what changed.

        The obvious implementation -- delete every row, insert them again --
        would wipe the user's selection and any scroll position several times a
        second, which is the "never reconstruct" rule from CONTEXT.md. Rows are
        keyed by variable name, so only genuinely new or vanished variables
        move the tree structure at all.
        """
        seen = set()
        for index, (name, values) in enumerate(rows):
            seen.add(name)
            item = items.get(name)
            if item is None:
                items[name] = tree.insert("", index, text=name, values=values)
                continue
            if tuple(tree.item(item, "values")) != tuple(values):
                tree.item(item, values=values)
                self._flash_row(tree, item)
        for name in [n for n in items if n not in seen]:
            tree.delete(items.pop(name))

    def _flash_row(self, tree, item):
        """Change Flash for a Treeview row: two states, not a gradient.

        A Treeview tag carries a whole row's colour, so there is no per-glyph
        fade to be had here as there is in the RAM dump. A brief highlight that
        clears itself is enough to answer "which variable just moved?".
        """
        tree.tag_configure("changed", foreground=theme.C["flash_fg"])
        tree.item(item, tags=("changed",))
        tree.after(600, lambda: self._unflash_row(tree, item))

    @staticmethod
    def _unflash_row(tree, item):
        try:
            if tree.exists(item):
                tree.item(item, tags=())
        except tk.TclError:
            pass  # tree destroyed while the flash was pending

    def _scan_pointers(self):
        def done(result, error):
            if error is not None:
                self._status_var.set(f"scan_ptr failed: {self.app.describe_error(error)}")
                return
            candidates = result.get("candidates", [])
            self._status_var.set(f"txttop={result.get('txttop')}, {result.get('count', 0)} candidate(s) found")
            if candidates:
                detail = "\n".join(
                    f"@{c['addr']:#06x} → target {c['target']:#06x} (line {c['line']})"
                    for c in candidates
                )
                messagebox.showinfo("scan_ptr candidates", detail, parent=self)

        self.app.run_async(lambda: self.app.client.get("/api/scan_ptr"), done)
