# AMSpiriT — Releases

This repository hosts the official binary releases of the **AMSpiriT** Amstrad CPC emulator family, along with user documentation.

---

## About the emulator

**AMSpiriT** is an accuracy-focused emulator for the **Amstrad CPC** family of home computers (CPC 464, 664, 6128, 6128 Plus, 464 Plus, GX4000). It faithfully emulates all five CRTC variants, the Gate Array, the Z80 CPU, the AY-3-8912 PSG sound chip, and the FDC disk controller.

Two editions are distributed here.

### AMSpiriT *(original)*

The original, feature-complete Windows desktop application written by **David MANUEL**. It offers a polished user interface, full media support (DSK, HFE, IPF, CDT, SNA, CPR), and is the reference implementation. Windows only.

### AMSpiriT Lite *(portable — experimental)*

A cross-platform port of the same emulation core, targeting Linux, macOS, and Windows. Three frontends are included:

| Frontend | Status | Notes |
|---|---|---|
| **SDL2** | Working | Minimal desktop UI; drag-and-drop media loading; embedded HTTP debug server |
| **Qt** | Experimental | Richer UI in progress; gamepad support via Qt5 Gamepad |
| **Libretro** | Partial | For use inside RetroArch |

AMSpiriT Lite exposes advanced developer features: a [Lua/CSL scripting engine](docs/scripting.md), a [REST debug API](docs/web_server_api.md), BASIC injection/export, and configurable keyboard mapping.

---

## Releases

Releases are published as GitHub Releases. Each release includes binaries for all supported platforms.

### Platforms

| Platform | Architecture | Frontend | Package |
|---|---|---|---|
| Windows | x86_64 | AMSpiriT (original) | Installer `.exe` |
| Windows | x86_64 | AMSpiriT Lite — SDL2 | `.zip` |
| Windows | x86_64 | AMSpiriT Lite — Qt | `.zip` |
| Linux | x86_64 | AMSpiriT Lite — SDL2 + Qt | AppImage / Flatpak |
| Linux | aarch64 | AMSpiriT Lite — SDL2 | AppImage |
| macOS | Apple Silicon (arm64) | AMSpiriT Lite — SDL2 + Qt | `.dmg` |

> Older CPUs (pre-SSE4.2 or pre-ARMv8.2) are not supported.

### Download

Go to the [**Releases**](../../releases) tab and pick the latest version. Each release page lists all available packages with checksums.

---

## Getting started

### Windows

1. **AMSpiriT (original)**: run the installer, then launch *AMSpiriT* from the Start menu.
2. **AMSpiriT Lite — Qt**: unzip the archive anywhere, then double-click `amspirit-lite-qt.exe`. All runtime DLLs are bundled.
3. **AMSpiriT Lite — SDL2**: unzip and run `amspirit-lite-sdl.exe`. Pass `--help` for CLI options.

### Linux

Download the AppImage, **make it executable**, and run it:

> **Required step — do not skip.** AppImages downloaded from the web are not executable by default. Without `chmod +x` the file will not launch.

```bash
chmod +x AMSpiriT-Lite-x86_64.AppImage
./AMSpiriT-Lite-x86_64.AppImage -R /path/to/ROMs
```

Or install via Flatpak (when available):

```bash
flatpak install amspirit-lite.flatpak
flatpak run org.amspirit.AMSpiriTLite
```

### macOS

Open the `.dmg`, drag *AMSpiriT Lite* to your Applications folder, and launch it. On first launch, macOS may require you to approve the app in **System Settings → Privacy & Security**.

---

## ROMs

The Amstrad CPC ROMs (OS + BASIC) are **not included** for copyright reasons. You need to supply your own. Legal ROM sets can be obtained from [www.amstrad.com](https://www.amstrad.com/pcw/rom/amsdos.htm) (Amstrad has given permission for personal use) or extracted from a real machine.

Place them in a directory and point the emulator to it:

```bash
amspirit-lite-sdl -R /path/to/roms/
```

Expected filenames vary by model; see the [user documentation](docs/) for details.

---

## Documentation

| Document | Description |
|---|---|
| [Help (English)](docs/amspirit-lite-help-en.html) | General user guide — keyboard shortcuts, loading media, settings |
| [Help (Français)](docs/amspirit-lite-help-fr.html) | Guide utilisateur en français |
| [Help (Español)](docs/amspirit-lite-help-es.html) | Guía de usuario en español |
| [Help (Deutsch)](docs/amspirit-lite-help-de.html) | Benutzerhandbuch auf Deutsch |
| [Keyboard configuration](docs/keyboard_config.md) | Custom keyboard layouts, hotkeys, `keymap.cfg` format |
| [Scripting (Lua/CSL)](docs/scripting.md) | Automation, regression testing, screen capture |
| [Web/REST API](docs/web_server_api.md) | Embedded HTTP debug server reference |
| [BASIC injection & export](docs/basic_injection_export.md) | Inject or dump Locomotive BASIC programs |
| [Snapshot slots](docs/snapshot_slots.md) | Quick-save / quick-load with gamepad support |
| [Changelog](docs/Changelog) | Full version history |

---

## Examples

The [`examples/`](examples/) directory contains ready-to-use files to get started quickly.

### BASIC programs (`.bas`)

Inject any of these into the emulator via **Tools → Inject BASIC** (Qt frontend) or the [BASIC injection API](docs/basic_injection_export.md):

| File | Description |
|---|---|
| [`print_char.bas`](examples/print_char.bas) | Prints all printable ASCII characters (32–127). Minimal "hello world" to verify injection works. |
| [`deuxlignes.bas`](examples/deuxlignes.bas) | Sound + graphics demo: animated drawing with AY sound. Tests SOUND, MOVE, DRAWR, and MODE. |
| [`labyrinth.bas`](examples/labyrinth.bas) | One-liner that draws random characters using CRTC register tricks. Stress-tests the display loop. |

### Web server test page

[`amspirit-lite-web-server-test.html`](examples/amspirit-lite-web-server-test.html) is a self-contained HTML page you can open in any browser to interact with the embedded HTTP debug server.

**Usage:**

1. Start AMSpiriT Lite with the web server enabled (it listens on `http://localhost:6128` by default).
2. Open `amspirit-lite-web-server-test.html` in your browser.
3. Use the buttons to send requests to every documented endpoint (reset, inject BASIC, read/write memory, take a screenshot, etc.) and inspect the JSON responses inline.

See the [Web/REST API reference](docs/web_server_api.md) for the full endpoint list.

---

## Supported media formats

| Format | Type | Notes |
|---|---|---|
| `.dsk` | Floppy disk image | Standard and extended DSK |
| `.hfe` | Floppy disk image | HxC format |
| `.ipf` / `.caps` | Floppy disk image | Protected originals (requires CAPS library) |
| `.cdt` | Cassette tape | CDT format |
| `.wav` | Cassette tape | Audio tape |
| `.sna` | Snapshot | V1 and V2 |
| `.cpr` | Cartridge | CPC Plus / GX4000 |

Drag and drop any supported file onto the emulator window to load it instantly.

---

## Source code

The source repositories live under the [AMSpiriT-Emulator](https://github.com/AMSpiriT-Emulator) GitHub organisation:

- **amspirit-lite** — cross-platform port (SDL2, Qt, Libretro frontends)

The original AMSpiriT (Windows) source is proprietary and not publicly available.

---

## License

**AMSpiriT Lite** is released under the terms described in `LICENSE` in each release archive.

The Amstrad CPC ROMs are the property of Amstrad plc, redistributed with permission for personal use only.
