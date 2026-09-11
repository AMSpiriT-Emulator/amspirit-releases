# AMSpiriT - Releases

This repository hosts the official binary releases of the **AMSpiriT** Amstrad CPC emulator family, along with user documentation.

---

## About the emulator

**AMSpiriT** is an accuracy-focused emulator for the **Amstrad CPC** family of home computers (CPC 464, 664, 6128, 6128 Plus, 464 Plus, GX4000). It faithfully emulates all five CRTC variants, the Gate Array, the Z80 CPU, the AY-3-8912 PSG sound chip, and the FDC disk controller.

Two editions are distributed here.

### AMSpiriT *(original)*

The original, feature-complete Windows desktop application written by **David MANUEL**. It offers a polished user interface, full media support (DSK, HFE, IPF, CDT, SNA, CPR), and is the reference implementation. Windows only.

### AMSpiriT Lite *(portable - experimental)*

A cross-platform port of the same emulation core, targeting Linux, macOS, and Windows. Three frontends are included:

| Frontend | Status | Notes |
|---|---|---|
| **SDL2** | Working | Minimal desktop UI; drag-and-drop media loading; embedded HTTP debug server |
| **Qt** | Working | Richer UI in progress; gamepad support via Qt5 Gamepad |
| **Headless** | Working | For testing, automation, CI |
| **Libretro** | Partial | For use inside RetroArch |

AMSpiriT Lite exposes advanced developer features: 
 * a [Lua/CSL scripting engine](https://github.com/AMSpiriT-Emulator/amspirit-releases/blob/main/docs/lite/scripting.md)
 * a [REST debug API](https://github.com/AMSpiriT-Emulator/amspirit-releases/blob/main/docs/lite/web_api.md), 
 * [BASIC injection/export](https://github.com/AMSpiriT-Emulator/amspirit-releases/blob/main/docs/lite/basic_injection_export.md)


---

## Releases

Releases are published as GitHub Releases. Each release includes binaries for all supported platforms.

### Platforms

| Platform | Architecture | Frontend | Package |
|---|---|---|---|
| Windows | x86_64 | AMSpiriT (original) | `.zip` |
| Linux | x86_64 | AMSpiriT Lite - SDL + Qt | `AppImage` |
| Linux | aarch64 | AMSpiriT Lite - SDL2 +Qt| `AppImage` |
| macOS | Apple Silicon (arm64) | AMSpiriT Lite - SDL2 + Qt | `.dmg` |
| Windows | x86_64 | AMSpiriT Lite - SDL2 +Qt | `.zip` |

and Retro Arch for x86_64,aarch64, Apple Silicon, and Windows.

> Older CPUs (pre-SSE4.2 or pre-ARMv8.2) are not supported.

### Download

Go to the [**Releases**] tab and pick the latest version. Each release page lists all available packages with checksums.

---

## Getting started

### Windows

1. **AMSpiriT (original)**: run the installer, then launch *AMSpiriT* from the Start menu.
2. **AMSpiriT Lite - Qt**: unzip the archive anywhere, then double-click `amspirit-lite-qt.exe`. All runtime DLLs are bundled.
3. **AMSpiriT Lite - SDL2**: unzip and run `amspirit-lite-sdl.exe`. Pass `--help` for CLI options.

### Linux

Download the AppImage, **make it executable**, and run it:

> **Required step - do not skip.** AppImages downloaded from the web are not executable by default. Without `chmod +x` the file will not launch.

```bash
chmod +x AMSpiriT-Lite-x86_64.AppImage
./AMSpiriT-Lite-x86_64.AppImage 
```

### macOS

Open the `.dmg`, drag *AMSpiriT Lite* to your Applications folder, and launch it. On first launch, macOS may require you to approve the app in **System Settings → Privacy & Security**.

---

## Examples

The [`examples/`](examples/) directory contains ready-to-use files to get started quickly.

### BASIC programs (`.bas`)

Inject any of these into the emulator via **Tools → Inject BASIC** (Qt frontend) or the [BASIC injection API](docs/basic_injection_export.md):

You also can drag'n drop the files.

| File | Description |
|---|---|
| [`print_char.bas`](examples/print_char.bas) | Prints all printable ASCII characters (32–127). Minimal "hello world" to verify injection works. |
| [`deuxlignes.bas`](examples/deuxlignes.bas) | 2 lines animated drawing with sound. Tests SOUND, MOVE, DRAWR, and MODE. |
| [`labyrinth.bas`](examples/labyrinth.bas) | One-liner that draws random characters |

### Web server test page

[`amspirit-lite-web-server-test.html`](examples/amspirit-lite-web-server-test.html) is a self-contained HTML page you can open in any browser to interact with the embedded HTTP debug server. 

**Usage:**

1. Start AMSpiriT Lite with the web server enabled (it listens on `http://localhost:6345` by default).
2. Open `amspirit-lite-web-server-test.html` in your browser.
3. Use the buttons to send requests to every documented endpoint (reset, inject BASIC, read/write memory, take a screenshot, etc.) and inspect the JSON responses inline.

See the [Web/REST API reference](docs/web_server_api.md) for the full endpoint list.

### Debug GUI (Python/Tkinter)

[`amspirit-lite-python-gui/`](tools/amspirit-lite-python-gui/) is a desktop
GUI counterpart to the web server test page above, covering the same debug
API (keyboard, BASIC editor/stepping, CPU registers/RAM/breakpoints, a live
RAM heatmap, audio waveform, disk, scripting, CRT config) as a standalone
Python application instead of a browser page. Built with the Python
standard library only (Tkinter) - no `pip install` needed. It's the first
example here shipped as its own subdirectory rather than a single flat
file; see its own [README](examples/amspirit-lite-python-gui/README.md) for
requirements and usage.

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
| `.bin` / `.amsdos` | Raw binary | With an AMSDOS header, or headerless using the [`@` filename convention](#binary-files-and-the--filename-convention) below |

Drag and drop any supported file onto the emulator window to load it instantly.
Files changes are detected, and automatically reloaded. Great for developers. You can edit your bas file in an external editor and update it automatically when you save it on disk! Easy!

The Amstrad CPC ROMs are the property of Amstrad plc, redistributed with permission for personal use only.

### Binary files and the `@` filename convention

A `.bin` file with an **AMSDOS header** is self-describing: the emulator reads
its load address and, for an executable, its entry point straight from the
file.

A **headerless** raw binary carries no such information, so AMSpiriT Lite reads
it from the filename instead:

| Filename | Meaning |
|---|---|
| `game.bin` | No address — needs `--bin-address` on the command line, or it won't load |
| `game@1000.bin` | Load at `&1000`, don't run |
| `game@1000@2000.bin` | Load at `&1000`, then jump to `&2000` |

Addresses are **hexadecimal, four digits** (`&` and `0x` omitted). The first is
the origin, the second the entry point.

**Exporting.** In the Qt and ImGui frontends, **Tools → Save binary file** dumps
a slice of CPC memory. Give it an address and a length; if you leave *Prepend
AMSDOS header* unchecked, the filename proposed in the save dialog already
carries the convention — enter `1000` as the address and `2000` as the entry
point and you are offered `dump@1000@2000.bin`, which loads straight back with
a drag and drop. When a disk or tape is loaded, its name is used instead of
`dump` (`sorcery@1000@2000.bin`). The entry point is optional: without it you get
`dump@1000.bin`. The proposed name is only a suggestion; you can rename freely,
but a name without the `@` tokens will need `--bin-address` to reload.

With *Prepend AMSDOS header* checked, no `@` suffix is added — the addresses
live in the header, and having a second, renameable copy in the filename would
only let the two disagree.

**Extended memory.** The address field also accepts the `Bnn:hhhh` notation for
banks beyond the base 64K (`B04:2000`). Those addresses cannot go into a
filename — `:` is not a legal filename character on Windows — so exporting from
such a bank proposes a plain `dump.bin` and tells you so; reload it with
`--bin-address B04:2000`.

The entry point is always a plain CPU address (`2000`), never bank-prefixed:
the Z80 jumps to a 16-bit address, it has no notion of a bank.



---


# Development Team

* **AMSpiriT Original** version (Windows) and Core was written by Dmanu78 with Technical supervision by Longshot, and some support by Siko
* **AMSpirit Lite** was developed by Siko, Mac Port and VSCode plugins by Gurneyh
* **Basic Tokenizer** written by Tronic
* **Test Team**: Fred/Fugitif, LordHeavy, Ricolaoz, Ldir Hector

# Acknowledgments

AMSpiriT would never have reached its current accuracy level without the extraordinary documentation work of Longshot/Logon System, author of the "CRTC compendium", and the "Shaker" tool, invaluable sources of verified, tested, proven information. 

Thanks to Made and Ced for their illustrations and Logos.

Thanks also to AMSpiriT's discord members, and members of FORUM.SYSTEM-CFG forum  for their support.


--

Copyright (c) 2020-2026 David Manuel & AMSpiriT Team

This software is licensed under the Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International Public License. 
To view a copy of this license, visit http://creativecommons.org/licenses/by-nc-nd/4.0/ or see the LICENSE.txt file.
