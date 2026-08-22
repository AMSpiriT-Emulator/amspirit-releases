# AMSpiriT Lite — Python Debug GUI

A Tkinter-based graphical debugger for **AMSpiriT-Lite** — an Amstrad CPC 6128 emulator with an embedded HTTP debug server.

## Features

- **Live Debugging**: Z80 CPU registers, step-by-step execution, breakpoints
- **BASIC Debugger**: Inspect program listing, variables, arrays; step through BASIC statements
- **Memory Inspector**: RAM dump, search; live ROM/RAM mapping display (1.14+)
- **Audio**: Waveform viewer, device/volume control, WAV export
- **Disk Management**: Create/save disk images, load media (SNA/DSK/HFE/IPF/CPR/CRO/BIN) (1.14+)
- **Scripting**: Run CSL or Lua scripts on the emulator's engine
- **Heat Map**: Visualize RAM writes as a 256×256 heatmap
- **CRT Rendering**: Control monitor presets and shader parameters
- **Keyboard**: Send text/key presses, view live 10×8 key matrix

## Requirements

- Python 3.7+
- Tkinter (usually included with Python; on Linux: `python3-tk`)
- **No external dependencies** — uses only stdlib (`urllib`, `tkinter`, `threading`, etc.)

## Installation

### Option 1: Run Directly from Git (Recommended)

```bash
cd /path/to/amspirit-releases
PYTHONPATH=tools/amspirit_lite_python_gui:$PYTHONPATH python3 -m amspirit_debug_gui --port 8765
```

### Option 2: Add to PYTHONPATH Permanently

```bash
export PYTHONPATH="/path/to/amspirit-releases/tools/amspirit_lite_python_gui:$PYTHONPATH"
python3 -m amspirit_debug_gui --port 8765
```

### Option 3: Install as Editable Package (Development)

```bash
cd /path/to/amspirit-releases/tools/amspirit_lite_python_gui
pip install -e .
amspirit_debug_gui --port 8765
```

## Usage

### Starting the GUI

The emulator's debug server must be running on port 8765 (default).

```bash
python3 -m amspirit_lite_python_gui [--host 127.0.0.1] [--port 8765]
```

**Options:**
- `--host` — Debug server host (default: `127.0.0.1`)
- `--port` — Debug server port (default: `8765`)

### Keyboard Tab

- Send text to the emulator's keyboard
- Special keys: Space, Backspace, Tab, Enter, Shift, Control, Alt, CapsLock, Escape, arrow keys, Delete
- Live 10×8 key matrix display (optional)

### CPU / Debug Tab

- **Registers**: View Z80 registers, single-step or step back (if timelapse active)
- **Memory**: Read/dump RAM at any address or bank; search hex patterns
- **Memory Map** (1.14+): View ROM/RAM mapping per 16 KB region; RMR, banking mode, extended-RAM page
- **Breakpoints**: Set Z80 PC breakpoints, view instruction history, clear codemap
- **Circuits**: Inspect Gate Array, CRTC, FDC, PSG register state
- **Screen**: Live screenshot (if paused), raster breakpoint arm/disarm by clicking

### BASIC Tab

- **Listing**: View current BASIC program with execution highlight
- **Variables**: Inspect scalar variables and arrays (with live decode from RAM)
- **Scan Pointers** (1.14+): Find RAM words pointing into the BASIC program (diagnostic tool)
- **Editor**: Inject/export BASIC code, load/save .bas files
- **Stepping**: Step by statement or line; run-to target line; line breakpoints

### Audio Tab

- Waveform viewer (last N seconds, configurable window)
- Audio device selector (SDL frontend)
- Volume control (SDL frontend)
- WAV export

### Disk Tab

- **Create**: Insert blank formatted disk into drive A or B
- **Save**: Export current disk as a DSK image
- **Load** (1.14+): Load media files (SNA/DSK/HFE/IPF/CPR/CRO/BIN) into a drive
  - For headerless `.bin` files, specify load address and optional entry point

### Poke Tab

- Write raw bytes to CPC RAM at any address/bank
- Optionally jump to a new PC address
- Or jump without writing (PC redirection only)
- Writes are now confirmed before reporting success (1.14 seq contract)

### Config Tab

- CPC Model (464, 664, 6128, 6128+, 464+, GX4000)
- CRTC Type (0–4)
- ROM Language (FR, EN, SP, DA)
- CRT Monitor Preset (Off, CTM644, GT65, TV)
- CRT Shader Parameters (curvature, scanline, sharpness, etc.)

### Script Tab

- Run CSL (Locomotive BASIC macro language) or Lua 5.4 scripts
- Sandboxed execution (no file I/O, limited stdlib)
- Live script state and error display

### Heat Map Tab

- Visual 256×256 RAM write heatmap (one pixel per byte)
- Decay/accumulation modes
- Bank selection
- Live overlay of Z80 register pointers

### Settings Tab

- Read-only keyboard layout and mapping display

## Project Structure

```
tools/amspirit_lite_python_gui/
├── README.md                    # This file
├── setup.py                     # Optional: pip install -e .
└── amspirit_debug_gui/          # Main package
    ├── __init__.py              # Package marker
    ├── __main__.py              # CLI entry point
    ├── app.py                   # Tk root, connection bar, polling manager
    ├── api_client.py            # HTTP client (stdlib urllib, no deps)
    ├── tab_*.py                 # Tab modules (10 tabs)
    └── util.py                  # Shared helpers (parsing, BASIC decode)
```

### API Client

All network I/O runs off the Tk main thread via `PollingManager` (background thread polling) and `run_async` (one-shot button actions). This keeps the GUI responsive even if the emulator stalls or the network is slow.

Error handling:
- `AmspiritApiError` — non-2xx responses with optional `field` hint
- `AmspiritConnectionError` — server unreachable

### Polling Manager

Registers periodic fetches (e.g., Z80 registers every 500ms) with optional `active` predicates that pause the poller when a tab isn't visible. Results are dropped on the main thread and tabulate via Tk `after()`.

## API Version Support

- **1.13 and earlier**: Full support
- **1.14**: Adds three new features
  - `POST /api/media` — Load media files (SNA/DSK/HFE/IPF/CPR/CRO/BIN)
  - `GET /api/memmap` — ROM/RAM mapping display
  - `GET /api/scan_ptr` — Diagnostic BASIC pointer scanner
  - `seq` contract for RAM writes (`POST /api/ram`, `POST /api/exec`) — client now waits for `emu.ram_apply_seq` confirmation

## Compatibility

- **SDL2 / Qt frontends**: Full support (all tabs work)
- **WASM build**: Limited (no `/api/media` endpoint due to NUL-terminated string marshaling; UI file picker used instead)
- **Python 3.7+**: Tested on 3.10; should work on any 3.7+

## Development

### Testing the GUI

```bash
# Syntax check
python3 -m py_compile *.py

# Run
PYTHONPATH=.:$PYTHONPATH python3 -m amspirit_lite_python_gui
```

### Adding a New Tab

1. Create `tab_newfeature.py` with a class `NewFeatureTab(ttk.Frame)`
2. Register in `app.py:_build_notebook()` — add to the `tabs` list
3. The tab receives `self.app` reference for client, poller, async helpers

### Debugging Network Issues

Set the `debug_api` flag in the emulator's web server (`web_server.cpp`) to log every HTTP request/response to stdout.

## Known Limitations

- Only one simultaneous client connection (emulator's web server)
- No keep-alive; each request opens a new TCP connection
- Large media uploads (>8 MB) not supported by the emulator's server
- `.cdt` (cassette) files not supported by `/api/media` endpoint (use drag-and-drop in the emulator's UI instead)
- Raster breakpoints work on SDL2/Qt but not all frontend combinations

## License

Same as AMSpiriT-Lite.

## See Also

- **AMSpiriT-Lite API Reference**: `docs/lite/web_api.md`
- **Scripting Reference**: `docs/lite/scripting.md`
- **Web UI**: `amspirit-lite.html` (embedded in the emulator, serves on `http://127.0.0.1:8765/`)
