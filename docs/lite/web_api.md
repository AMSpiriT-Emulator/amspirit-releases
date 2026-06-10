# AMSpiriT-Lite Web API Documentation

The AMSpiriT-Lite emulator includes an embedded HTTP debug server that allows you to control the emulation, inject programs, monitor state, and execute scripts over a local HTTP interface.

## Server Overview

- **Base URL**: `http://127.0.0.1:8765`
- **Availability**: Localhost by default (can be exposed to any interface)
- **Auto-startup**: The web server starts automatically with the emulator once enabled.
- **Port**: Configurable; defaults to `8765`. If the port is occupied, the server remains disabled without errors

# Endpoints

## Connectivity & Health Check

### `GET /api/ping`

Lightweight connectivity probe to verify the server is reachable.

**Response**: `200 application/json`
```json
{"ok": true}
```

**Example**:
```bash
curl http://127.0.0.1:8765/api/ping
```

---

### `GET /`

Returns the web-based debug interface (HTML/JS/CSS).

**Response**: `200 text/html`

**Example**:
```bash
curl http://127.0.0.1:8765/
```

---

## Emulator State

### `GET /api/state`

Returns a comprehensive snapshot of the emulator's current state, including Z80 registers, Gate Array, PSG, FDC, and runtime metrics.

**Response**: `200 application/json`

```json
{
  "z80": {
    "PC": 1234, "SP": 65280,
    "A": 0, "F": 64, "B": 0, "C": 0,
    "D": 0, "E": 0, "H": 0, "L": 0,
    "A2": 0, "F2": 0, "B2": 0, "C2": 0,
    "D2": 0, "E2": 0, "H2": 0, "L2": 0,
    "IX": 0, "IY": 0, "I": 0, "R": 0,
    "IFF1": 1, "IFF2": 1, "IM": 1
  },
  "ga": {
    "mode": 1,
    "border_idx": 0,
    "border_rgb": 0,
    "hbl": false,
    "vbl": true,
    "ink_idx": [0,3,24,9,6,26,0,0,0,0,0,0,0,0,0,0],
    "ink_rgb": [0,255,16711680,65280,16776960,65535,0,0,0,0,0,0,0,0,0,0]
  },
  "psg": {
    "period_a": 0, "vol_a": 0,
    "period_b": 0, "vol_b": 0,
    "period_c": 0, "vol_c": 0,
    "mixer": 63, "noise": 0,
    "env_period": 0, "env_shape": 0
  },
  "fdc": {
    "msr": 128, "sr0": 0, "sr1": 0, "sr2": 0,
    "motor": false, "drive": 0
  },
  "emu": {
    "fps": 50.0,
    "frame": 0,
    "paused": false,
    "cpc_model": 2,
    "crtc_type": 0
  }
}
```

**Key fields**:
- `z80`: Z80 CPU state (registers, program counter, stack pointer, interrupt flags)
- `ga`: Gate Array state (video mode, border color, pen colors in RGB24)
- `psg`: PSG sound chip state (tone periods, volumes, envelope)
- `fdc`: Floppy Disk Controller state (motor, drive selection, status)
- `emu`: Emulator runtime (FPS, pause state, CPC model, CRTC type)

**Example**:
```bash
curl http://127.0.0.1:8765/api/state | jq '.z80.PC'
```

---

## Configuration

### `GET /api/config`

Retrieve the current emulator configuration.

**Response**: `200 application/json`

```json
{
  "cpc_model": 2,
  "crtc_type": 0,
  "sound_output": 1,
  "freq_screen": 0,
  "extended_ram": 0
}
```

**Fields**:
- `cpc_model`: 0=464, 1=664, 2=6128, 4=6128+, 5=464+, 6=GX4000
- `crtc_type`: CRTC variant (0–4)
- `sound_output`: 0=Mono, 1=Stereo
- `freq_screen`: 0=PAL (50 Hz), 1=NTSC (60 Hz)
- `extended_ram`: Extended RAM size (in 64 KB units)

**Example**:
```bash
curl http://127.0.0.1:8765/api/config
```

---

### `POST /api/config`

Change emulation configuration or request control actions (reset, pause).

**Body**: `application/json` — all fields optional

```json
{
  "cpc_model": 2,
  "crtc_type": 0,
  "rom_lang": "FR",
  "paused": false,
  "do_soft_reset": false,
  "do_hard_reset": false
}
```

**Fields**:
| Field | Type | Effect |
|---|---|---|
| `cpc_model` | integer | Change CPC model (triggers reset) |
| `crtc_type` | integer | Change CRTC type (triggers reset) |
| `rom_lang` | string | ROM language: `"FR"`, `"EN"`, `"ES"`, `"DA"` |
| `paused` | boolean | Pause (`true`) or resume (`false`) emulation |
| `do_soft_reset` | boolean | Trigger a soft reset |
| `do_hard_reset` | boolean | Trigger a hard reset |

**Response**: `200 application/json`
```json
{"ok": true}
```

**Examples**:
```bash
# Pause the emulator
curl -X POST http://127.0.0.1:8765/api/config \
  -H 'Content-Type: application/json' \
  -d '{"paused": true}'

# Soft reset
curl -X POST http://127.0.0.1:8765/api/config \
  -H 'Content-Type: application/json' \
  -d '{"do_soft_reset": true}'

# Switch to English ROM and reset
curl -X POST http://127.0.0.1:8765/api/config \
  -H 'Content-Type: application/json' \
  -d '{"rom_lang": "EN", "do_hard_reset": true}'
```

---

## Memory Access

### `GET /api/ram?addr=<address>&len=<length>`

Read a block of CPC RAM.

**Query parameters**:
| Parameter | Type | Default | Range |
|---|---|---|---|
| `addr` | integer (decimal or `0x` hex) | 0 | 0–65535 |
| `len` | integer | 256 | 1–16384 |

**Response**: `200 application/json`

```json
{
  "addr": 0,
  "len": 16,
  "hex": "c9000000000000000000000000000000"
}
```

**Example**:
```bash
# Read 16 bytes from address 0x0000
curl 'http://127.0.0.1:8765/api/ram?addr=0x0000&len=16'

# Read 256 bytes starting at address 16384
curl 'http://127.0.0.1:8765/api/ram?addr=16384&len=256'
```

---

### `POST /api/ram`

Write bytes to CPC RAM and optionally redirect the Z80 program counter.

**Body**: `application/json`

```json
{
  "addr": 4096,
  "data": "3e01cd00bb",
  "exec": true,
  "entry": 4096
}
```

**Fields**:
| Field | Type | Description |
|---|---|---|
| `addr` | integer | Destination address in RAM (0–65535) |
| `data` | hex string | Bytes to write (spaces and `:` are tolerated and ignored) |
| `exec` | boolean | If `true`, the Z80 PC jumps to `entry` after the write |
| `entry` | integer | Target PC address (default = `addr`) |

**Response**: `200 application/json`
```json
{"ok": true}
```

**Examples**:
```bash
# Write a simple Z80 instruction (LD A, 0x01)
curl -X POST http://127.0.0.1:8765/api/ram \
  -H 'Content-Type: application/json' \
  -d '{
    "addr": 4096,
    "data": "3e01",
    "exec": true
  }'

# Write with readable formatting (colons and spaces are ignored)
curl -X POST http://127.0.0.1:8765/api/ram \
  -H 'Content-Type: application/json' \
  -d '{
    "addr": 4096,
    "data": "3e:01 cd:00:bb",
    "exec": true
  }'
```

---

### `POST /api/exec`

Redirect the Z80 program counter without writing to RAM.

**Body**: `application/json`

```json
{"addr": 4096}
```

**Response**: `200 application/json`
```json
{"ok": true}
```

**Example**:
```bash
# Jump Z80 execution to address 0x1000
curl -X POST http://127.0.0.1:8765/api/exec \
  -H 'Content-Type: application/json' \
  -d '{"addr": 0x1000}'
```

---

## Keyboard Input

### `POST /api/keytype`

Send a text string to the emulator as if typed on the keyboard.

Successive calls accumulate in a queue; characters are sent one per frame. Use `\r` for the Enter key.

**Body**: `application/json`

```json
{"text": "LOAD\"GAME.BAS\"\r"}
```

**Response**: `200 application/json`
```json
{"ok": true}
```

**Examples**:
```bash
# Type "RUN" and press Enter
curl -X POST http://127.0.0.1:8765/api/keytype \
  -H 'Content-Type: application/json' \
  -d '{"text":"RUN\r"}'

# Load a BASIC program
curl -X POST http://127.0.0.1:8765/api/keytype \
  -H 'Content-Type: application/json' \
  -d '{"text":"LOAD\"GAME\"\r"}'
```

---

### `POST /api/keypress`

Send a single CPC virtual key code.

Useful for non-ASCII keys (arrows, function keys) that cannot be represented as text.

**Body**: `application/json`

```json
{"vk": 32}
```

**Fields**:
| Field | Type | Description |
|---|---|---|
| `vk` | integer | Virtual key code (0–255, see CPC key tables) |

**Response**: `200 application/json`
```json
{"ok": true}
```

**Example**:
```bash
# Send Up arrow key (example VK code 0x40)
curl -X POST http://127.0.0.1:8765/api/keypress \
  -H 'Content-Type: application/json' \
  -d '{"vk": 0x40}'
```

---

### `GET /api/keymap`

Retrieve the current keyboard mapping configuration.

Used primarily by the web UI to display which keys are active.

**Response**: `200 application/json`

```json
{
  "layout": "FR",
  "mapping": [
    {
      "sdl_keycode": 32,
      "vk": 48,
      "vk_with_shift": -1,
      "nomod": false
    }
  ]
}
```

**Fields**:
- `layout`: Current layout (`"FR"`, `"EN"`, `"ES"`, `"DA"`, etc.)
- `mapping`: Array of key mappings

**Example**:
```bash
curl http://127.0.0.1:8765/api/keymap | jq '.layout'
```

---

## BASIC Programs

### `POST /api/basic[?reset=1][?run=1]`

Tokenize and inject a Locomotive BASIC program directly into CPC RAM at address 0x0170.

Program end pointers and status flags are updated automatically. After injection, type `LIST` or `RUN` in the emulator to see the program.

**Body**: `text/plain` — BASIC source with line numbers

**Query parameters** (optional):
| Parameter | Values | Effect |
|---|---|---|
| `reset` | `0`, `1` | Hard reset before injection (default: 0) |
| `run` | `0`, `1` | Auto-type `RUN` after injection (default: 0) |

**Maximum size**: ~44 KB (from 0x0170 to 0xAE66)

**Response**: `200 application/json`
```json
{"ok": true}
```

**Window title feedback**:
- Success: `BASIC injected — type LIST or RUN`
- Failure: `BASIC inject failed: program too large`

**Examples**:
```bash
# Simple inline program
curl -X POST http://127.0.0.1:8765/api/basic \
  -H 'Content-Type: text/plain' \
  --data-binary '10 MODE 1
20 BORDER 0
30 INK 0,0:INK 1,26
40 PRINT "HELLO WORLD"
50 GOTO 40'

# From a .bas file
curl -X POST http://127.0.0.1:8765/api/basic \
  -H 'Content-Type: text/plain' \
  --data-binary @myprog.bas

# Inject and auto-run
curl -X POST 'http://127.0.0.1:8765/api/basic?run=1' \
  -H 'Content-Type: text/plain' \
  --data-binary '10 PRINT "INFINITE LOOP"
20 GOTO 10'

# Reset, inject, and run
curl -X POST 'http://127.0.0.1:8765/api/basic?reset=1&run=1' \
  -H 'Content-Type: text/plain' \
  --data-binary @program.bas
```

---

### `GET /api/basic_state`

Get the current state of the BASIC program loaded in RAM.

**Response**: `200 application/json`

```json
{
  "loaded": true,
  "size": 2048,
  "lines": 42
}
```

**Fields**:
- `loaded`: Whether a BASIC program is present in RAM
- `size`: Program size in bytes
- `lines`: Number of BASIC lines

**Example**:
```bash
curl http://127.0.0.1:8765/api/basic_state
```

---

### `GET /api/basic_export[?verbose=1]`

Export (detokenize) the current BASIC program from RAM as human-readable source code.

**Query parameters** (optional):
| Parameter | Values | Effect |
|---|---|---|
| `verbose` | `0`, `1` | Include extra whitespace for readability (default: 0) |

**Response**: `200 text/plain; charset=utf-8` — BASIC source code

**Examples**:
```bash
# Export compact
curl http://127.0.0.1:8765/api/basic_export > exported.bas

# Export with readability formatting
curl http://127.0.0.1:8765/api/basic_export?verbose=1 > exported_readable.bas

# View in terminal
curl http://127.0.0.1:8765/api/basic_export?verbose=1
```

---

## Scripting

### `GET /api/script`

Get the current state of the scripting engine (CSL or Lua).

**Response**: `200 application/json`

```json
{
  "running": false,
  "error": ""
}
```

**Fields**:
- `running`: `true` if a script is currently executing
- `error`: Error message from the last script (empty if no error)

**Example**:
```bash
curl http://127.0.0.1:8765/api/script
```

---

### `POST /api/script[?lang=lua]`

Launch a script (CSL macro-language or raw Lua 5.4).

**Body**: `text/plain` — script source code

**Query parameters** (optional):
| Parameter | Values | Effect |
|---|---|---|
| `lang` | `lua` | Use Lua 5.4 instead of CSL (default: CSL) |

**Response**: `200 application/json`
```json
{"ok": true}
```

**Examples**:
```bash
# Run a CSL script from file
curl -X POST 'http://127.0.0.1:8765/api/script' \
  -H 'Content-Type: text/plain' \
  --data-binary @test.csl

# Run a Lua script
curl -X POST 'http://127.0.0.1:8765/api/script?lang=lua' \
  -H 'Content-Type: text/plain' \
  --data-binary @automation.lua

# Inline Lua
curl -X POST 'http://127.0.0.1:8765/api/script?lang=lua' \
  -H 'Content-Type: text/plain' \
  --data-binary 'print("Hello from Lua")'
```

---

### `DELETE /api/script`

Stop the currently running script.

**Response**: `200 application/json`
```json
{"ok": true}
```

**Example**:
```bash
curl -X DELETE http://127.0.0.1:8765/api/script
```

---

## Quick Reference

| HTTP Method | Endpoint | Purpose |
|---|---|---|
| GET | `/` | Web interface |
| GET | `/api/ping` | Health check |
| GET | `/api/state` | CPU/hardware state snapshot |
| GET | `/api/config` | Current configuration |
| POST | `/api/config` | Change config / reset / pause |
| GET | `/api/ram?addr=N&len=N` | Read RAM bytes |
| POST | `/api/ram` | Write RAM bytes and/or redirect PC |
| POST | `/api/exec` | Redirect Z80 PC only |
| POST | `/api/keytype` | Send text string (autotype) |
| POST | `/api/keypress` | Send single CPC key code |
| GET | `/api/keymap` | Current keyboard layout |
| POST | `/api/basic` | Inject BASIC program |
| GET | `/api/basic_state` | BASIC program metadata |
| GET | `/api/basic_export` | Export BASIC as source |
| GET | `/api/script` | Scripting engine state |
| POST | `/api/script` | Launch script (CSL or Lua) |
| DELETE | `/api/script` | Stop script |

---

## Tips & Tricks

### Continuous Monitoring

Monitor the emulator state in real-time:
```bash
watch -n 0.1 "curl -s http://127.0.0.1:8765/api/state | jq '.z80.PC'"
```

### Inject & Run Programs

Quickly test a BASIC program:
```bash
curl -X POST 'http://127.0.0.1:8765/api/basic?run=1' \
  -H 'Content-Type: text/plain' \
  --data-binary @test.bas
```

### Automate with Scripts

Use Lua or CSL to automate testing, record state, or drive the emulator:
```bash
curl -X POST 'http://127.0.0.1:8765/api/script?lang=lua' \
  -H 'Content-Type: text/plain' \
  --data-binary 'for i=1,100 do api.state() end'
```

### Debug Z80 State

Export and inspect CPU state:
```bash
curl http://127.0.0.1:8765/api/state | jq '.z80 | {PC, SP, A, F}'
```

---

## Limitations

- Only one request at a time (sequential HTTP handling)
- No persistent connections (HTTP/1.0, no keep-alive)
- Request size limited to 64 KB
- No authentication
- State reads may have microsecond inconsistencies (state snapshots are frame-aligned)

