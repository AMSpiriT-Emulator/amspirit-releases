"""Dark theme, transcribed literally from amspirit-lite.html's stylesheet.

Every colour here is the same hex the HTML debug page uses, expanded to six
digits where CSS allowed three (`#6af` -> `#66aaff`). The point is that the
two frontends read as the same tool: when a colour question comes up, the
answer is "whatever the HTML does", not a fresh judgement call.

Tkinter has no cascade, so this module is the cascade. Nothing outside it
should contain a hex literal -- tabs ask for a token (`C["value"]`), a named
ttk style ("Value.TLabel"), or a font (`mono()`).

Two mechanisms, because Tk has two widget families:

* ttk widgets (Label, Button, Entry, Notebook, Treeview...) are themed by
  `ttk.Style` on top of "clam". It is the only built-in theme that honours
  background/border colours on every platform -- the native Windows and
  macOS themes silently ignore them, which is exactly the austerity we are
  removing.
* classic Tk widgets (Text, Canvas, Label...) ignore ttk entirely, so they
  are given defaults through the option database instead. That keeps the
  per-widget code free of colour, and means a widget added later inherits
  the theme without anyone remembering to.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

# -- palette ------------------------------------------------------------------

# Keys are roles, not appearances: "panel" rather than "dark grey", so a tab
# never has to decide whether its grey is the same grey as someone else's.
C = {
    # surfaces (body / .panel / borders)
    "bg": "#1c1c1c",
    "panel": "#252525",
    "panel_hi": "#2e2e2e",  # .tab-btn:hover
    "border": "#383838",
    # text (body / h1 / h2 / label / .rn)
    "fg": "#d0d0d0",
    "accent": "#66aaff",  # #6af -- h1, active tab, hover highlights
    "heading": "#8899bb",  # #89b -- h2
    "muted": "#888888",  # labels, addresses, the 11 status lines
    "dim": "#444444",  # disabled text, chart gridlines
    # data (.rv / .kv / .vv)
    "value": "#ffddaa",  # #fda -- register and field values, bold
    "key": "#88aacc",  # #8ac -- field names in key/value rows
    "val2": "#ccee88",  # #ce8 -- secondary values
    # buttons
    "btn_bg": "#2a3a5a",
    "btn_bg_hi": "#3a4a6a",
    "btn_border": "#3a4a6a",
    "btn_fg": "#c0d0f0",
    "btn_red_bg": "#5a1a1a",
    "btn_red_bg_hi": "#6a2a2a",
    "btn_red_border": "#7a3a3a",
    "btn_red_fg": "#ffaaaa",
    "btn_amber_bg": "#4a3a1a",
    "btn_amber_bg_hi": "#5a4a2a",
    "btn_amber_border": "#6a5a3a",
    "btn_amber_fg": "#ffcc88",
    # inputs (input/select/textarea)
    "field_bg": "#2a2a2a",
    "field_border": "#444444",
    # badges (.run / .pause)
    "run_bg": "#1a5a2a",
    "run_fg": "#66ff66",
    "pause_bg": "#5a2a1a",
    "pause_fg": "#ff9966",
    # status line (#status-line) and its error counterpart (button.red's fg)
    "ok": "#66ff99",  # #6f9
    "error": "#ffaaaa",
    # transient emphasis (.valflash / .hx:hover) -- see Change Flash in CONTEXT.md
    "flash_fg": "#ffffff",
    "flash_bg": "#2a2a00",
    "flash_accent": "#ffaa00",  # #ffa
    # plots and bitmaps, which want to be blacker than the page
    "plot_bg": "#0a0a0a",
    "plot_grid": "#333333",
    "plot_trace": "#6fdc6f",
    "screen_bg": "#000000",
}

# HTML is `13px/1.5 'Courier New', monospace`, and monospace everywhere --
# labels and buttons included. The mixed proportional/monospace look is a
# large part of what reads as "austere bricolage"; a debug tool that is
# uniformly monospace has an identity.
_FAMILY_PREFERENCE = (
    "Courier New",  # what the HTML asks for; present on Windows/macOS
    "DejaVu Sans Mono",  # the Linux default that actually ships everywhere
    "Liberation Mono",
    "Nimbus Mono PS",
    "Monospace",
)

BASE_SIZE = 9  # ~13px at 96dpi, i.e. the HTML's body size

_family: str | None = None


def mono(size: int | None = None, bold: bool = False) -> tuple:
    """The project's only font constructor.

    Resolved against what Tk actually has: "Courier New" is absent from most
    Linux boxes, and Tk silently substitutes a *proportional* face when asked
    for a missing family rather than another monospace one -- which is how a
    monospace-everywhere design quietly turns back into a ragged one.
    """
    if _family is None:  # apply_theme() has not run: only possible in tests
        raise RuntimeError("theme.apply_theme(root) must run before mono()")
    spec = (_family, BASE_SIZE if size is None else size)
    return (spec + ("bold",)) if bold else spec


def _resolve_family(root: tk.Misc) -> str:
    available = {name.lower() for name in tkfont.families(root)}
    for candidate in _FAMILY_PREFERENCE:
        if candidate.lower() in available:
            return candidate
    # TkFixedFont is Tk's own guaranteed monospace alias -- never missing.
    return tkfont.nametofont("TkFixedFont").actual("family")


# -- application --------------------------------------------------------------


def apply_theme(root: tk.Tk) -> ttk.Style:
    """Theme `root` and every widget created under it, present and future."""
    global _family
    _family = _resolve_family(root)
    base = mono()
    base_bold = mono(bold=True)

    root.configure(background=C["bg"])

    _apply_option_database(root, base)

    style = ttk.Style(root)
    style.theme_use("clam")
    _apply_ttk(style, base, base_bold)
    return style


def _apply_option_database(root: tk.Tk, base: tuple):
    """Defaults for classic Tk widgets, which ttk.Style cannot reach.

    Set on `root` rather than globally so a second Tk instance (tests) is
    unaffected. `insertbackground` matters as much as the rest: a black text
    caret on a #1c1c1c background is invisible, which is the sort of detail
    that makes a dark theme feel broken rather than dark.
    """
    for widget in ("Text", "Canvas", "Label", "Listbox", "Checkbutton", "Menu"):
        root.option_add(f"*{widget}.background", C["panel"])
        root.option_add(f"*{widget}.foreground", C["fg"])
        root.option_add(f"*{widget}.font", base)
        root.option_add(f"*{widget}.highlightThickness", 0)
    for widget in ("Text", "Listbox"):
        root.option_add(f"*{widget}.insertBackground", C["fg"])
        root.option_add(f"*{widget}.selectBackground", C["btn_bg_hi"])
        root.option_add(f"*{widget}.selectForeground", C["fg"])
        root.option_add(f"*{widget}.borderWidth", 1)
        root.option_add(f"*{widget}.relief", "solid")
    root.option_add("*Text.inactiveSelectBackground", C["btn_bg"])
    root.option_add("*Checkbutton.selectColor", C["field_bg"])
    root.option_add("*Checkbutton.activeBackground", C["panel"])
    root.option_add("*Checkbutton.activeForeground", C["fg"])
    # The Combobox dropdown is a classic Listbox that ttk does not own, so it
    # stays stubbornly light unless reached here.
    root.option_add("*TCombobox*Listbox.background", C["field_bg"])
    root.option_add("*TCombobox*Listbox.foreground", C["fg"])
    root.option_add("*TCombobox*Listbox.selectBackground", C["btn_bg"])
    root.option_add("*TCombobox*Listbox.selectForeground", C["btn_fg"])
    root.option_add("*TCombobox*Listbox.font", base)


def _apply_ttk(style: ttk.Style, base: tuple, base_bold: tuple):
    # Padding throughout follows the HTML's density (`button{padding:3px 10px}`,
    # `.row{gap:6px}`), which is markedly tighter than ttk's defaults. This is
    # not only taste: the window is 1180x760 and shares a screen with the
    # emulator, so vertical space spent on padding is information not shown.
    style.configure(".", background=C["bg"], foreground=C["fg"], font=base,
                    fieldbackground=C["field_bg"], bordercolor=C["border"],
                    darkcolor=C["bg"], lightcolor=C["bg"], troughcolor=C["field_bg"],
                    focuscolor=C["accent"], relief="flat")

    style.configure("TFrame", background=C["bg"])
    style.configure("TLabel", background=C["bg"], foreground=C["fg"], font=base)

    # -- label variants, one per role in the HTML's stylesheet ---------------
    style.configure("Heading.TLabel", foreground=C["heading"], font=base_bold)
    style.configure("Muted.TLabel", foreground=C["muted"])
    style.configure("Status.TLabel", foreground=C["ok"])
    style.configure("Error.TLabel", foreground=C["error"])
    style.configure("Key.TLabel", foreground=C["key"])
    style.configure("Value.TLabel", foreground=C["value"], font=base_bold)
    style.configure("Value2.TLabel", foreground=C["val2"])
    style.configure("Accent.TLabel", foreground=C["accent"])
    # Change Flash: same geometry as Value.TLabel so swapping between them
    # cannot reflow the layout mid-update.
    style.configure("Flash.TLabel", foreground=C["flash_fg"], font=base_bold)
    style.configure("Run.TLabel", background=C["run_bg"], foreground=C["run_fg"],
                    padding=(7, 1))
    style.configure("Pause.TLabel", background=C["pause_bg"], foreground=C["pause_fg"],
                    padding=(7, 1))

    # -- buttons ------------------------------------------------------------
    for name, bg, bg_hi, border, fg in (
        ("TButton", C["btn_bg"], C["btn_bg_hi"], C["btn_border"], C["btn_fg"]),
        ("Danger.TButton", C["btn_red_bg"], C["btn_red_bg_hi"], C["btn_red_border"],
         C["btn_red_fg"]),
        ("Amber.TButton", C["btn_amber_bg"], C["btn_amber_bg_hi"],
         C["btn_amber_border"], C["btn_amber_fg"]),
    ):
        style.configure(name, background=bg, foreground=fg, bordercolor=border,
                        lightcolor=border, darkcolor=border, font=base,
                        padding=(10, 3), relief="solid", borderwidth=1,
                        anchor="center")
        # `disabled` first: ttk resolves state maps top-down, and a disabled
        # button under the pointer must read as disabled, not as hovered.
        style.map(name,
                  background=[("disabled", bg), ("pressed", bg), ("active", bg_hi)],
                  foreground=[("disabled", C["dim"]), ("active", fg)],
                  relief=[("pressed", "solid")])

    # -- inputs -------------------------------------------------------------
    style.configure("TEntry", fieldbackground=C["field_bg"], foreground=C["fg"],
                    bordercolor=C["field_border"], lightcolor=C["field_border"],
                    darkcolor=C["field_border"], insertcolor=C["fg"],
                    padding=(4, 2), relief="solid", borderwidth=1)
    style.map("TEntry",
              fieldbackground=[("disabled", C["bg"])],
              foreground=[("disabled", C["dim"])],
              bordercolor=[("focus", C["accent"])],
              lightcolor=[("focus", C["accent"])],
              darkcolor=[("focus", C["accent"])])

    style.configure("TCombobox", fieldbackground=C["field_bg"], background=C["field_bg"],
                    foreground=C["fg"], arrowcolor=C["fg"],
                    bordercolor=C["field_border"], lightcolor=C["field_border"],
                    darkcolor=C["field_border"], padding=(4, 2),
                    relief="solid", borderwidth=1)
    style.map("TCombobox",
              fieldbackground=[("readonly", C["field_bg"]), ("disabled", C["bg"])],
              foreground=[("disabled", C["dim"])],
              arrowcolor=[("disabled", C["dim"]), ("active", C["accent"])],
              bordercolor=[("focus", C["accent"])],
              lightcolor=[("focus", C["accent"])],
              darkcolor=[("focus", C["accent"])])

    style.configure("TSpinbox", fieldbackground=C["field_bg"], foreground=C["fg"],
                    arrowcolor=C["fg"], bordercolor=C["field_border"],
                    lightcolor=C["field_border"], darkcolor=C["field_border"],
                    padding=(4, 2), relief="solid", borderwidth=1)

    for name in ("TCheckbutton", "TRadiobutton"):
        style.configure(name, background=C["bg"], foreground=C["fg"], font=base,
                        indicatorcolor=C["field_bg"], indicatorbackground=C["field_bg"],
                        bordercolor=C["field_border"], focuscolor=C["bg"],
                        padding=(2, 1))
        style.map(name,
                  background=[("active", C["bg"])],
                  foreground=[("disabled", C["dim"]), ("active", C["accent"])],
                  indicatorcolor=[("selected", C["accent"]),
                                  ("disabled", C["bg"])])

    style.configure("TScale", background=C["bg"], troughcolor=C["field_bg"],
                    bordercolor=C["border"], lightcolor=C["btn_bg_hi"],
                    darkcolor=C["btn_bg_hi"])
    style.map("TScale", background=[("active", C["bg"])])

    # -- containers ---------------------------------------------------------
    # `.panel` is #252525 on a #1c1c1c body: LabelFrames are the GUI's panels,
    # so they carry the lighter surface and the h2 colour on their title.
    style.configure("TLabelframe", background=C["panel"], bordercolor=C["border"],
                    lightcolor=C["border"], darkcolor=C["border"],
                    relief="solid", borderwidth=1, padding=6)
    style.configure("TLabelframe.Label", background=C["panel"], foreground=C["heading"],
                    font=base_bold)

    style.configure("TNotebook", background=C["bg"], bordercolor=C["border"],
                    lightcolor=C["bg"], darkcolor=C["bg"], borderwidth=0,
                    tabmargins=(0, 0, 0, 0))
    style.configure("TNotebook.Tab", background=C["panel"], foreground=C["muted"],
                    bordercolor=C["border"], lightcolor=C["panel"],
                    darkcolor=C["panel"], font=base, padding=(14, 4), borderwidth=1)
    style.map("TNotebook.Tab",
              background=[("selected", C["bg"]), ("active", C["panel_hi"])],
              foreground=[("selected", C["accent"]), ("active", C["fg"])],
              lightcolor=[("selected", C["bg"])],
              bordercolor=[("selected", "#4a6a9a")])

    style.configure("Treeview", background=C["panel"], fieldbackground=C["panel"],
                    foreground=C["fg"], bordercolor=C["border"],
                    lightcolor=C["border"], darkcolor=C["border"],
                    font=base, rowheight=18, relief="solid", borderwidth=1)
    style.map("Treeview",
              background=[("selected", C["btn_bg"])],
              foreground=[("selected", C["btn_fg"])])
    style.configure("Treeview.Heading", background=C["btn_bg"], foreground=C["btn_fg"],
                    bordercolor=C["btn_border"], lightcolor=C["btn_border"],
                    darkcolor=C["btn_border"], font=base, relief="solid",
                    borderwidth=1, padding=(4, 2))
    style.map("Treeview.Heading", background=[("active", C["btn_bg_hi"])])

    for orient in ("Vertical", "Horizontal"):
        style.configure(f"{orient}.TScrollbar", background=C["btn_bg"],
                        troughcolor=C["bg"], bordercolor=C["border"],
                        arrowcolor=C["fg"], lightcolor=C["btn_bg"],
                        darkcolor=C["btn_bg"], relief="flat", borderwidth=0)
        style.map(f"{orient}.TScrollbar",
                  background=[("active", C["btn_bg_hi"]), ("disabled", C["bg"])],
                  arrowcolor=[("disabled", C["dim"])])
