# AMSpiriT-Lite — Scripting CSL / Lua

The scripting engine allows you to automate the emulator: regression tests, demonstrations, sequential screen captures, automatic keyboard input.

Scripts execute **frame by frame** via a Lua coroutine. The `wait*` / `cpc.wait*` functions yield control to the emulator and resume at the next frame when the condition is met — without blocking the main loop.

---

## Loading a Script

### Command Line

```bash
amspirit-lite-sdl --script test.csl
amspirit-lite-sdl --script bench.lua
```

### Drag and Drop

Drop a `.csl` or `.lua` file on the emulator window.

### Web API (`--web-server`)

```bash
# Execute a CSL script (default)
curl -X POST http://127.0.0.1:8765/api/script \
     --data-binary @test.csl

# Execute raw Lua
curl -X POST 'http://127.0.0.1:8765/api/script?lang=lua' \
     --data-binary @bench.lua

# Read status
curl http://127.0.0.1:8765/api/script
# → {"running":true,"error":""}

# Stop the current script
curl -X DELETE http://127.0.0.1:8765/api/script
```

The embedded debug interface (accessible at `http://127.0.0.1:8765`) has a Script panel with editor, CSL/Lua selector, and Execute / Stop buttons.

---

## Script Format

### Extension `.lua` — Raw Lua 5.4

The file is passed directly to the Lua interpreter. All Lua 5.4 syntax is available.

### Other extensions (`.csl`, `.txt`, etc.) — CSL

CSL is a minimal preprocessor on top of Lua. It transforms a "command language" style into valid Lua, then executes it.

Transformation rules:

| CSL | Generated Lua |
|---|---|
| `reset hard` | `reset("hard")` |
| `disk_insert A 'game.dsk'` | `disk_insert("A", "game.dsk")` |
| `wait 2000000` | `wait(2000000)` |
| `; comment` | `-- comment` |
| `\(RET)` in a string | `\n` |
| `\(ESC)` in a string | `\x1b` |

A recognized name followed by arguments without parentheses is automatically parenthesized. Pure Lua code is passed through unchanged — both styles are mixable in the same `.csl` file.

---

## Global Functions (historical CSL compatibility)

These functions have existed since the beginning and remain available without a prefix.

### Synchronization

```lua
wait(usec)           -- wait N microseconds (rounded up to the next frame)
wait_frames(n)       -- wait N frames (1 frame = ~20 ms at 50 Hz)
wait_vsyncoffon()    -- wait for the next VSYNC rising edge
wait_driveonoff(n)   -- wait N drive motor ON/OFF cycles (default 1)
wait_ssm0000()       -- wait for the ED 00 ED 00 sequence in the Z80
```

### Machine Control

```lua
reset()              -- hard reset (default)
reset("soft")        -- soft reset
reset("hard")
crtc_select(n)       -- change CRTC type (0–4) and reinitialize
cpc_model(n)         -- change CPC model (CORE_CPC_* constant) and reinitialize
```

### Media

```lua
disk_insert([drive,] path)   -- insert a DSK/HFE/IPF into drive A
                              -- the drive parameter ("A"/"B") is parsed but ignored
disk_dir(path)               -- search prefix for disk_insert
tape_insert(path)            -- insert a CDT/WAV cassette
tape_dir(path)
tape_play()
tape_stop()
tape_rewind()
snapshot_load(path)          -- load an SNA snapshot
snapshot_dir(path)
```

### Keyboard

```lua
key_output(text)             -- type text into the CPC (wait for input to complete)
keyboard_write(b0,...,b15)   -- write directly to the CPC keyboard matrix (16 bytes)
key_delay(press_us, between_us [, cr_us])
                             -- configure typing delays (in microseconds)
```

Special sequences in `key_output`:

| Sequence | Key |
|---|---|
| `\(RET)` | Enter |
| `\(ESC)` | Escape |
| `\(TAB)` | Tab |
| `\(DEL)` | Delete |
| `\(ARL)` `\(ARR)` `\(ARU)` `\(ARD)` | Arrow keys |
| `\(FN0)`…`\(FN9)` | Function keys |
| `\(SHI)` `\(CTR)` `\(CAP)` | Modifiers |

### Screenshots

```lua
screenshot()                 -- take a screenshot (name/directory configurable)
screenshot_name(name)        -- filename without extension
screenshot_dir(path)         -- destination directory
```

### Loading Subscripts

```lua
csl_load(path)               -- load and execute a CSL/Lua file synchronously
                             -- wait() called in the subscript does not work
                             -- (Lua limitation: yield through pcall is forbidden)
```

### Miscellaneous

```lua
csl_version(str)             -- log the script version (informational)
poke(addr, value)            -- write a byte to CPC RAM
```

---

## Table `cpc` — Hardware Access

All hardware access and control functions are grouped under `cpc`.

### Z80 Registers

```lua
local z80 = cpc.getZ80()
```

Returns a table with all registers:

| Key | Register |
|---|---|
| `PC`, `SP` | Program counter, stack pointer |
| `A`, `F`, `B`, `C`, `D`, `E`, `H`, `L` | Main registers |
| `A2`, `F2`, `B2`, `C2`, `D2`, `E2`, `H2`, `L2` | Alternate registers |
| `IX`, `IY` | Index registers |
| `I`, `R` | Interrupt / refresh registers |
| `IFF1`, `IFF2` | Interrupt flip-flops (0 or 1) |
| `IM` | Interrupt mode (0, 1 or 2) |

```lua
cpc.setZ80({PC=0x4000, A=0x3E})   -- partial update, other registers unchanged
```

Example — wait for the PC to reach an address:

```lua
repeat
  cpc.waitFrames(1)
  local z = cpc.getZ80()
until z.PC == 0xBB00
cpc.screenshot("result")
```

### RAM

```lua
local data = cpc.getRam(addr, len)
-- returns a Lua binary string of `len` bytes starting at `addr`
-- string.byte(data, 1)  → first byte
-- string.byte(data, i)  → byte at offset i (1-indexed)
```

```lua
cpc.setRam(addr, data)
-- `data` is a Lua binary string
-- cpc.setRam(0x4000, "\x3E\x01\xCD\x00\xBB")
```

Example — read a calculation result:

```lua
reset("soft")
wait_frames(200)
local result = cpc.getRam(0x8000, 2)
local lo = string.byte(result, 1)
local hi = string.byte(result, 2)
local val = lo + hi * 256
print(string.format("Result: %d (0x%04X)", val, val))
```

Example — inject a program and execute it:

```lua
local code = "\x3E\x42\x32\x00\x80\x76"  -- LD A,0x42 / LD (0x8000),A / HALT
cpc.setRam(0x4000, code)
cpc.setZ80({PC = 0x4000})
wait_frames(5)
local mem = cpc.getRam(0x8000, 1)
print("Written by Z80:", string.byte(mem, 1))
```

### Control

```lua
cpc.reset()           -- hard reset (default)
cpc.reset("soft")
cpc.reset("hard")

cpc.pause(true)       -- pause emulation
cpc.pause(false)      -- resume
```

### Gate Array

```lua
local ga = cpc.getGateArray()
-- ga.mode          : video mode (0, 1 or 2)
-- ga.border        : AMSTRAD color index of the border (0–31)
-- ga.border_rgb    : RGB24 color of the border (0xRRGGBB)
-- ga.inks[1..16]   : AMSTRAD index of each ink (1-indexed)
-- ga.inks_rgb[1..16] : RGB24 color of each ink
```

### PSG AY-3-8912

```lua
local psg = cpc.getPSG()
-- psg.period_a / psg.vol_a   : channel A — period (12 bits) and volume (5 bits)
-- psg.period_b / psg.vol_b   : channel B
-- psg.period_c / psg.vol_c   : channel C
-- psg.mixer                  : register R7
-- psg.noise                  : noise period (5 bits)
-- psg.env_period             : envelope period (16 bits)
-- psg.env_shape              : envelope shape (4 bits)
```

### Synchronization Aliases

```lua
cpc.wait(usec)
cpc.waitFrames(n)
cpc.waitVSync()
cpc.waitDrive(n)
```

Identical to the corresponding global functions.

---

## Table `amspirit` — Emulator Metainformation

```lua
local v = amspirit.getVersion()
-- returns the core version in hexadecimal, e.g. "20400"

local cfg = amspirit.getConfig()
-- cfg.model        : CPC model (0=464, 1=664, 2=6128, 4=6128+, 5=464+, 6=GX4000)
-- cfg.crtc         : CRTC type (0–4)
-- cfg.sound_output : 0=mono, 1=stereo
-- cfg.freq_screen  : 0=PAL 50 Hz, 1=NTSC 60 Hz
-- cfg.extended_ram : extended RAM (0 = none)

amspirit.screenshot(dir, name)
-- equivalent to screenshot_dir(dir) + screenshot_name(name) + screenshot()
```

---

## Complete Examples

### Automatic Regression Test

```csl
; test_basic.csl
csl_version '1.0'
reset hard
disk_insert A 'tests/basic_test.dsk'
wait_frames 150
key_output 'RUN"TEST"\(RET)'
wait_frames 500
screenshot_dir './results'
screenshot_name 'basic_test_final'
screenshot
```

### Conditional Lua Script

```lua
-- Verify that a program loads correctly and produces the expected value
cpc.reset("hard")
disk_insert("tests/prog.dsk")
cpc.waitFrames(100)
key_output('RUN"PROG"\n')
cpc.waitFrames(300)

local mem = cpc.getRam(0x9000, 2)
local result = string.byte(mem, 1) + string.byte(mem, 2) * 256
if result == 0x1234 then
    amspirit.screenshot("./results", "pass")
    print("PASS")
else
    amspirit.screenshot("./results", "fail")
    print(string.format("FAIL — expected 0x1234, got 0x%04X", result))
end
```

### Execution from a Shell (CI)

```bash
#!/bin/bash
# Launch the emulator with the web UI, execute a script and wait for completion

amspirit-lite-sdl --web-server --no-splash &
PID=$!
sleep 2  # allow time for the emulator to start

curl -sf -X POST http://127.0.0.1:8765/api/script \
     --data-binary @ci/regression.csl

# Wait for the script to complete
while true; do
    STATUS=$(curl -sf http://127.0.0.1:8765/api/script)
    RUNNING=$(echo "$STATUS" | grep -o '"running":true')
    [ -z "$RUNNING" ] && break
    sleep 1
done

ERROR=$(curl -sf http://127.0.0.1:8765/api/script | grep -o '"error":"[^"]*"')
kill $PID
[ "$ERROR" = '"error":""' ] && echo "OK" || { echo "ERROR: $ERROR"; exit 1; }
```

---

## Known Limitations

- `csl_load` cannot call `wait*` in the loaded subscript (Lua limitation: `lua_yield` through `lua_pcall` raises an error). Use `csl_load` only for configuration files without waits.
- Drive B (`disk_insert B ...`) is parsed but ignored — only drive A is supported.
- `wait_ssm0000` requires SSM mode to be active. It is activated automatically when a script calls this function, or manually with `--ssm`.
- `cpc.setRam` takes only a Lua binary string. To build byte sequences: `string.char(0x3E, 0x01, 0xCD, 0x00, 0xBB)`.
