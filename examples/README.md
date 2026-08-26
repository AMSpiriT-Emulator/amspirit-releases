# AMSpiriT Lite — Debug GUI (Python/Tkinter)

A desktop GUI counterpart to [`amspirit-lite-web-server-test.html`](../amspirit-lite-web-server-test.html)
and to `amspirit-lite`'s own embedded web debug UI. It drives the same
[REST debug API](../../docs/lite/web_api.md) over plain HTTP — no changes to
`amspirit-lite` are required, and no browser either.

Built with **Tkinter** (Python's standard-library GUI toolkit) and nothing
else: no `pip install` is needed. This is the first example in this
repository shipped as its own subdirectory/package rather than a single
flat file, since it's split into one module per tab.

## Requirements

- Python ≥ 3.10
- A Python build with Tk 8.6+ (the `tkinter` module). On Linux this is
  usually a separate distro package — e.g. `python3-tkinter` (Fedora),
  `python3-tk` (Debian/Ubuntu). Tk 8.6 reads PNG images natively, which the
  CPU tab's screenshot view relies on.

## Usage

Start AMSpiriT Lite with the web server enabled (`--web-server`, default
port `8765`), then:

```bash
cd amspirit-lite-debug-gui
python3 -m amspirit_debug_gui --host 127.0.0.1 --port 8765
```

Both flags default to `127.0.0.1:8765`, so plain `python3 -m
amspirit_debug_gui` works out of the box against a local instance. The
host/port fields in the app's top bar can also be changed and reconnected
at any time without restarting.

## What's covered

Every tab from the embedded web UI, minus three features that would need a
real rendering/DSP stack disproportionate to a "minimal" GUI:

| Tab | Covered | Not ported (v1) |
|---|---|---|
| Keyboard | text/key send, live 10×8 key matrix | — |
| CPU / Debug | Z80 registers, step/step-back, RAM hex dump + search, Z80 breakpoints, instruction history, GA/CRTC/FDC/PSG panels, live screenshot with click-to-arm raster breakpoint | full Z80 mnemonic disassembler (hex/ASCII dump covers the same ground textually) |
| BASIC | listing with current-line highlight, editor (inject/export/save/load), stepping, line breakpoints, run-to, scalar variables + arrays table | — |
| Audio | waveform (genuine Canvas plot, not ASCII art), device/volume, WAV export | FFT spectrum / spectrogram (would need a manual DFT — no numpy dependency here) |
| Heat Map | genuine 256×256 visual heatmap (Canvas + PhotoImage), accumulate/instant/decay, PC/SP/HL/IX/IY overlay | tracks one bank at a time (the web UI tracks all banks concurrently) |
| Poke | write bytes + optional exec, execute-at-address | — |
| Script | run/stop CSL or Lua | — |
| Config | model/CRTC/ROM language, CRT monitor preset + shader parameters | no CRT preview (this GUI has no video renderer — same as the sliders-only limitation already accepted for this control) |
| Disk | create blank disk, save current disk to `.dsk` | — |
| Settings | read-only keymap view | remapping (the server supports it; this UI, like the original page, never calls it) |

Also out of scope for v1: the original page's `en/fr/es/de` UI language
switcher — this GUI is English-only.

## Design notes

- `api_client.py` is a plain `urllib.request` wrapper (stdlib only, no
  `requests`) and has no Tkinter dependency — it mirrors the same patterns
  used by `cpc-validation`'s `cpc-runner-amspirit` adapter.
- All HTTP calls run on a background thread (`app.py`'s `PollingManager`
  for periodic refreshes, `DebugGuiApp.run_async` for one-shot button
  actions); the Tk main thread only ever touches widgets, so a slow or
  unreachable emulator never freezes the window.
