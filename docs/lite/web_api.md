# AMSpiriT-Lite — Embedded HTTP Debug Server

Files: `amspirit-helpers/inc/web_server.h`, `amspirit-helpers/src/web_server.cpp`

This file is the narrative companion to the machine-readable API contract
served by the API itself at `GET /api/doc` (list of endpoints) and
`GET /api/doc/<name>` (per-endpoint method/params/response shape, `<name>`
being the path under `/api/`, e.g. `/api/doc/config` for `/api/config`). The
source of truth for that structured contract is the table in
`amspirit-helpers/src/web_doc.cpp` — this markdown keeps the behavioral
nuance and gotchas (SHIFT stickiness, `CPC_COUNTRY`, caveats, full curl
examples) that don't reduce to structured data. **The two do not
auto-sync**: when adding or changing an endpoint, update the entry in
`web_doc.cpp`, the corresponding section below, and, if the endpoint is
wrapped there, `tools/mcp-emulator/server.py`.

## Overview

Minimal HTTP server started automatically by `amspirit-lite-sdl` and the Qt
frontend (`amspirit-lite-qt`). All endpoints behave identically on both.  
Single-threaded, one request at a time, no keep-alive.  
Listens only on `127.0.0.1:8765` (loopback only, never exposed on the network).  
If the port is occupied, the server simply remains disabled — no fatal error.

---

## C++ Interface (public)

### Structures

#### `WebServerOpts`

Configuration parameter passed to `web_server_start`. Must remain alive
as long as the server is running.

| Field | Type | Default | Role |
|---|---|---|---|
| `port` | `uint16_t` | `8765` | TCP listen port |
| `bind_addr` | `std::string` | `"127.0.0.1"` | Bind address |
| `p_freeze` | `bool*` | `nullptr` | Pointer to the emulator's pause flag |
| `p_fps` | `double*` | `nullptr` | Pointer to the current FPS counter |
| `p_frame_compute_ms` | `double*` | `nullptr` | Pointer to per-frame compute time (ms) |
| `p_emu_params` | `CORE_PARAM_IN*` | `nullptr` | Emulator configuration parameters (read + pending config) |
| `p_emu_state` | `CORE_PARAM_OUT*` | `nullptr` | Core output buffers (RAM access) |
| `html_path` | `std::string` | `""` | Path to an external HTML file; empty = embedded UI |
| `p_rom_lang` | `std::string*` | `nullptr` | Pointer to current ROM language string (FR/EN/SP/DA) |
| `p_ui_lang` | `std::string*` | `nullptr` | Pointer to current UI language code (en/fr/es/de) |
| `mtx` | `std::mutex` | — | Internal lock shared between server thread and main thread |
| `pending` | `WebPending` | — | Pending command (do not access directly, use `web_server_poll`) |
| `script_status` | `WebScriptStatus` | — | Scripting engine state (running / last error / `print()` capture), published each frame by `web_eval_tick` |
| `eval` | `WebEvalState` | — | Interactive-eval request **and** result slot — the one request/response route; driven by `web_eval_tick` |
| `audio_ring` | `AudioRing*` | `nullptr` | Audio recording ring buffer (init with `web_audio_ring_init`) |
| `frames` | `std::atomic<uint64_t>` | `0` | Completed emulated video frames; the frontend must bump this once per frame — source of `emu.frames` |
| `autotype_remaining` | `std::atomic<int>` | `0` | Characters/VK presses left to deliver, updated by the frontend each frame — source of `emu.autotyping`/`emu.autotype_remaining` |
| `tl_active` / `tl_steps_back` / `tl_steps_fwd` / `tl_rewound` / `tl_step_kind` | `bool` / `int` / `int` / `bool` / `std::string` | `false` / `0` / `0` / `false` / `""` | Timelapse state, written by the frontend each frame — source of the `tl_*` fields in `emu` (see `GET /api/state`) and consumed by `POST /api/tl_back` |
| `render_monitor` / `render_crt` | `int` / `CrtParams` | `0` / — | Current CRT monitor preset and shader parameters, written by the frontend each frame — source of `GET /api/render` |
| `debug_api` | `bool` | `false` | Set at startup: log every incoming request, response status, and SSE event |
| `audio_devices` / `audio_current_device` | `std::vector<std::string>` / `std::string` | `{}` / `""` | Audio device list and current selection, populated by the frontend at startup — source of `GET /api/audio/devices` |
| `audio_volume_pct` | `int` | `100` | Live output volume, snapshotted by the frontend each frame — source of `volume` in `GET /api/config` |

#### `WebPending`

Command to apply at the next iteration of the main loop.
Consumed by `web_server_poll`.

| Field | Type | Role |
|---|---|---|
| `active` | `bool` | `true` if a command is pending |
| `cpc_model` | `uint8_t` | New CPC model (`0xFF` = unchanged) |
| `crtc_type` | `uint8_t` | New CRTC type (`0xFF` = unchanged) |
| `ram_kb` | `int` | New total RAM in Ko, central 64 Ko included (`-1` = unchanged) |
| `do_soft_reset` | `bool` | Request a soft reset |
| `do_hard_reset` | `bool` | Request a hard reset |
| `set_pause` | `bool` | `true` if `pause_val` should be applied |
| `pause_val` | `bool` | New pause state requested |
| `ram_writes` | `std::vector<WebRamWrite>` | Queued RAM write/execute requests, applied in order (see below) |
| `autotype_string` | `std::string` | Non-empty = autotype this text (appended on successive calls) |
| `vk_presses` | `std::vector<uint16_t>` | Raw CPC VK codes to press and release |
| `script_text` | `std::string` | Non-empty = run this CSL or Lua script |
| `script_is_csl` | `bool` | `true` = CSL (default); `false` = raw Lua |
| `script_abort` | `bool` | `true` = abort the currently running script |
| `new_rom_lang` | `std::string` | Non-empty = change ROM language (`FR`/`EN`/`SP`/`DA`) |
| `new_ui_lang` | `std::string` | Non-empty = change UI language (`en`/`fr`/`es`/`de`) |
| `basic_source` | `std::string` | Non-empty = tokenize and inject this BASIC program |
| `reset_before_basic` | `bool` | Hard-reset before injection |
| `run_after_inject` | `bool` | Auto-type `RUN` after successful injection |
| `do_disk_create` | `bool` | Insert a blank disk into `disk_drive` |
| `disk_drive` | `uint8_t` | Drive for disk_create (0=A, 1=B) |
| `do_media_load` | `bool` | Load `media_data` (SNA/DSK/HFE/IPF/CPR/CRO/BIN; `.cdt` currently unsupported) — see `POST /api/media` |
| `media_data` | `std::vector<uint8_t>` | Raw uploaded file bytes |
| `media_name` | `std::string` | Filename hint (extension routes headerless `.bin`/`.amsdos`; ignored otherwise) |
| `media_drive` | `uint8_t` | Target drive for disk images (0=A, 1=B) |
| `do_remap` | `bool` | Apply a live keymap binding change |
| `remap_kc` | `uint32_t` | Platform keycode to remap |
| `remap_vk` | `uint16_t` | CPC VK for normal press |
| `remap_vk_s` | `uint16_t` | CPC VK for shifted press |
| `remap_nomod` | `bool` | Suppress CPC Shift while this key is active |
| `set_mapping_keyboard` | `bool` | Apply a keyboard mapping mode change |
| `mapping_keyboard_val` | `bool` | New keyboard mapping mode value |
| `do_step` | `bool` | Execute exactly one Z80 instruction then re-pause |
| `do_basic_step` | `bool` | Run until the BASIC statement/line advances then re-pause |
| `basic_step_byline` | `bool` | `true` = step to next BASIC line; `false` = next statement |
| `do_tl_back` | `bool` | Navigate the timelapse one step back (requires an active timelapse — see `POST /api/tl_back`) |
| `set_breakpoints` | `bool` | Replace the BASIC line-breakpoint set |
| `breakpoints` | `std::vector<uint16_t>` | BASIC line numbers to break on |
| `set_z80_breakpoints` | `bool` | Replace the Z80 PC breakpoint set |
| `z80_breakpoints` | `std::vector<uint32_t>` | Z80 PC addresses (≤0xFFFF flat, or bank-qualified >0xFFFF) |
| `do_run_to` | `bool` | Resume until a one-shot target then pause |
| `run_to_line` | `uint16_t` | Run-to target BASIC line (`0xFFFF` = use `run_to_addr`) |
| `run_to_addr` | `uint16_t` | Run-to target statement address from `0xAE1B` |
| `clear_codemap` | `bool` | Reset the executed-instruction bitmap and history |
| `set_monitor` | `bool` | Change CRT monitor preset |
| `monitor_val` | `int` | New `MonitorPreset` value |
| `set_crt` | `bool` | Apply new CRT shader parameters |
| `crt_val` | `CrtParams` | New full CRT shader parameter set |
| `set_screen_type` | `bool` | Change screen type (colour/green/ASIC) |
| `screen_type_val` | `int` | New `CRTC_TYPE_SCREEN` value (0–3) |
| `set_raster_bp` | `bool` | Arm/disarm the raster breakpoint — see `POST /api/raster_bp` |
| `raster_bp_enable` | `bool` | New armed state (`false` = disarm) |
| `raster_bp_x` | `uint16_t` | Target column, video-buffer space (0–1023) |
| `raster_bp_y` | `uint16_t` | Target line, video-buffer space (0–349) |
| `do_set_audio_device` | `bool` | Switch the audio output device (see `audio_device` in `POST /api/config`) |
| `new_audio_device` | `std::string` | Device name; empty = system default |
| `do_set_volume` | `bool` | Set the output volume (see `volume` in `POST /api/config`) |
| `new_volume_pct` | `int` | New volume, 0–100 percent |

#### `WebRamWrite`

| Field | Type | Role |
|---|---|---|
| `addr` | `uint16_t` | Destination address in CPC RAM |
| `data` | `std::vector<uint8_t>` | Bytes to write (empty = no write) |
| `exec` | `bool` | If `true`, redirect the PC to `entry` after the write |
| `entry` | `uint16_t` | Target PC when `exec == true` (default = `addr`) |
| `bank` | `int` | `0` = central RAM; `1..N` = extended-RAM page `N−1` |

`POST /api/ram` and `POST /api/exec` each push one `WebRamWrite` onto
`WebPending::ram_writes` rather than overwriting a single slot: several calls
landing in the same poll tick used to silently coalesce onto one overwritable
field, dropping every write but the last with no error (`{"ok":true}`
regardless). `web_dispatch_apply` now applies the whole queue in FIFO order.

Each call also returns a `seq` in its `{"ok":true,"seq":N}` response — the
value `GET /api/state`'s `emu.ram_apply_seq` will hold once that specific
write has actually been applied by the main thread. The old contract
acknowledged the request as soon as it was queued, not once applied, so a
client reading RAM back immediately after `{"ok":true}` could race the main
loop (worse for larger payloads / higher system load, with no fixed size
threshold). Poll `ram_apply_seq` until it is `>= seq` before trusting a
readback instead of blind retry-and-verify.

---

### Functions

```cpp
bool web_server_start(WebServerOpts* opts);
```
Creates the socket, binds, starts the background thread.  
Returns `false` if the port is occupied (server inactive, no exception).

```cpp
void web_server_stop();
```
Requests the thread to stop (`g_running = false`), closes the listen socket, joins the thread.  
Call this on application shutdown.

```cpp
bool web_server_poll(WebServerOpts* opts, WebPending& out);
```

```cpp
void web_events_push(WebServerOpts& opts, const WebEvent& evt);
```
Push an emulator event to all connected SSE clients.  
**Call only from the main (emulator) thread** — all register values in `WebEvent` must be resolved before calling (no core functions are called in SSE threads).  
No-op if no clients are connected (cheap check, no lock held when idle).

**`WebEvent` struct** (defined in `web_events.h`):

| Field | Type | Used by |
|---|---|---|
| `type` | `WebEvent::Type` | All — `FRAME`, `Z80_BP`, `BASIC_BP`, `PAUSE`, `RESET` |
| `pc`, `sp`, `ix`, `iy` | `uint16_t` | FRAME, Z80_BP |
| `a`, `f`, `b`, `c`, `d`, `e`, `h`, `l` | `uint8_t` | FRAME, Z80_BP |
| `fps` | `double` | FRAME |
| `frame` | `uint32_t` | FRAME |
| `paused` | `bool` | FRAME, PAUSE |
| `basic_line` | `uint16_t` | BASIC_BP |
| `basic_addr` | `uint16_t` | BASIC_BP |
| `is_hard` | `bool` | RESET |
Call **at the start of each frame** in the main loop (SDL thread).  
Returns `true` if a command is pending and copies it to `out` (then clears `pending`).  
The command must be applied immediately before resuming emulation.  
Thread-safe: takes `opts->mtx` internally.

---

## HTTP Endpoints

Base URL: `http://127.0.0.1:8765`

All responses include:
- `Access-Control-Allow-Origin: *`
- `Cache-Control: no-store`
- HTTP/1.0 protocol for regular requests, HTTP/1.1 for SSE connections

---

## Request bodies and errors

**A `200 {"ok":true}` means the request was applied.** An endpoint that cannot use
what it was sent answers `400` with an explanation instead — it never reports
success for a request it ignored:

```json
{ "error": "field \"vk\" must be between 0 and 255", "field": "vk" }
```

`field` names the offending key (body field or query parameter) and is omitted for
whole-body problems. A `400` is returned when:

| Case | Example body | Response |
|---|---|---|
| Body is not a JSON object | `RUN`, `` (empty), `{"text":"RUN"` | `expected a JSON object` / `empty body: …` / `unterminated JSON object` |
| Required field missing | `{}` on `/api/keytype` | `missing field "text": the characters to type` |
| Field of the wrong type | `{"vk":"157"}`, `{"addr":null}` | `field "vk" must be an integer` |
| Value out of range | `{"volume":150}` | `field "volume" must be between 0 and 100 (percent)` |
| Value not in the accepted set | `{"rom_lang":"XX"}` | `field "rom_lang" must be one of FR, EN, SP, DA` |
| Nothing recognised / nothing to do | `{"cpc_modle":2}`, `{"addr":256}` on `/api/ram` | `no recognised field: …` / `nothing to do: …` |

`JSON.stringify({addr:NaN})` emits `{"addr":null}`, which is the wrong-type case —
worth knowing, because it used to be accepted with a `200` and no effect.

**Whitespace is not significant.** Bodies are read by a small scanner that skips
spaces, tabs, CR and LF on both sides of each colon, so compact
(`{"text":"RUN"}`) and pretty-printed (`{ "text" : "RUN" }`, indented multi-line)
bodies are equivalent. Values are looked up by key, flatly: a field nested one
level down (`{"crt":{"curvature":0.02,…}}`) is found as well.

---

### `GET /api/events` — Server-Sent Events

Persistent push stream. The server keeps the connection open and writes events as they occur. Regular request/response endpoints are unaffected and continue to work normally.

**Connect (JavaScript)**:
```js
const es = new EventSource('http://127.0.0.1:8765/api/events');

es.addEventListener('frame',    e => console.log(JSON.parse(e.data)));
es.addEventListener('z80_bp',   e => console.log('Z80 breakpoint:', JSON.parse(e.data)));
es.addEventListener('basic_bp', e => console.log('BASIC breakpoint:', JSON.parse(e.data)));
es.addEventListener('pause',    e => console.log('Pause:', JSON.parse(e.data)));
es.addEventListener('reset',    e => console.log('Reset:', JSON.parse(e.data)));
```

**Topic filter** (optional query param — omit to receive all events):
```
GET /api/events?topics=z80_bp,basic_bp,pause
```

Available topics: `frame`, `z80_bp`, `basic_bp`, `pause`, `reset`

**Event types**:

| Event | Frequency | Payload |
|---|---|---|
| `frame` | Every 10 frames (~5 Hz) | Z80 snapshot + FPS + pause state |
| `z80_bp` | Immediate on hit | PC + full Z80 registers |
| `basic_bp` | Immediate on hit | BASIC line number + statement address |
| `pause` | On transition | `{"paused": true\|false}` |
| `reset` | On hard/soft reset | `{"hard": true\|false}` |

**`frame` payload**:
```json
{
  "pc": "0x1234", "sp": "0xC000",
  "a": 0, "f": 64, "b": 0, "c": 0,
  "d": 0, "e": 0, "h": 0, "l": 0,
  "ix": "0x0000", "iy": "0x0000",
  "fps": 50.0, "frame": 1234, "paused": false
}
```

**`z80_bp` payload**:
```json
{
  "pc": "0x4A3F",
  "a": 65, "f": 0, "b": 0, "c": 0,
  "d": 0, "e": 0, "h": 0, "l": 0,
  "sp": "0xBFF0", "ix": "0x0000", "iy": "0x0000"
}
```

**`basic_bp` payload**:
```json
{ "line": 100, "addr": "0x4B20" }
```

**Heartbeat**: A comment line (`: ping`) is sent every 15 seconds on idle connections to keep the TCP connection alive through proxies and firewalls. `EventSource` ignores comment lines automatically.

**Limits**: Maximum 8 simultaneous SSE clients. The per-client event queue is bounded at 32 events; oldest events are dropped when the client is too slow to drain it.

**WASM target**: SSE is not available on the WebAssembly build (no BSD sockets). The endpoint does not exist there; continue using polling endpoints.

---

### `GET /api/ping`

Lightweight connectivity probe used by the web UI to detect whether the server is reachable.

**Response**: `200 application/json` — `{"ok":true,"emu":{...}}` (same `emu` object as in `GET /api/state`)

**Pacing an automation client — read `emu.frames`, never `time.sleep()`**

`emu.frames` counts *completed emulated video frames* since startup (see `GET /api/state`). It is the only emulated-time clock exposed over plain HTTP, and the one an automated client must pace itself on:

* **A reachable server does not mean a running machine.** The HTTP server answers before the emulation loop produces its first frame — a fraction of a second on the SDL2 frontend, but measured at **1.6 s on the Qt AppImage** (toolkit + OpenGL + FUSE startup). While `frames == 0` the Z80 has not executed a single cycle: `PC` is 0 and RAM still holds its post-reset fill, so a "screen is non-empty and stopped changing" boot heuristic is satisfied by a machine that has not booted at all. Wait for `frames > 0` first.
* **Wall clock ≠ emulated frames.** Typed input drains from the autotype queue at a few *emulated* frames per character (`POST /api/keytype`), and the frontends re-pace themselves against an absolute deadline after any stall, so `N × 20 ms` of sleeping is not `N` frames. Poll `emu.frames` until it has advanced by the budget you want instead — keystrokes sent early are silently swallowed by the booting firmware.

---

### `GET /` or `GET /index.html`

Returns the HTML/JS/CSS interface.  
If `WebServerOpts::html_path` points to a readable file, its content is served.  
Otherwise, the embedded UI in the binary is used.

**Response**: `200 text/html`

---

### `GET /api/state`

Instantaneous snapshot of the emulator's internal state.  
Direct read without lock (display-only data, accepts slight inconsistency).

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
  "crtc": {
    "regs": [63,40,46,142,38,0,25,30,0,7,0,0,48,0],
    "selected_reg": 0,
    "rasterline": 87,
    "vsync": false
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
    "frame_ms": 0.8,
    "frames": 4271,
    "paused": false,
    "cpc_model": 2,
    "crtc_type": 0,
    "autotyping": false,
    "autotype_remaining": 0,
    "tl_active": false,
    "tl_steps_back": 0,
    "tl_steps_fwd": 0,
    "tl_step_kind": "frame",
    "ram_apply_seq": 0
  }
}
```

**Notable fields:**

| Object | Field | Description |
|---|---|---|
| `z80` | `PC`…`L2` | Z80 registers, unsigned integer values |
| `z80` | `IFF1/IFF2` | Interrupt flip-flops (0 or 1) |
| `z80` | `IM` | Interrupt mode (0, 1 or 2) |
| `ga` | `mode` | Gate Array video mode (0, 1 or 2) |
| `ga` | `border_idx` | AMSTRAD color index of the border (0–31) |
| `ga` | `border_rgb` | Border color in packed RGB24 (`0xRRGGBB`) |
| `ga` | `ink_idx` | Array of 16 entries: AMSTRAD index of each PEN |
| `ga` | `ink_rgb` | Array of 16 entries: RGB24 color of each PEN |
| `psg` | `period_a/b/c` | Tone periods of channels A/B/C (12 bits) |
| `psg` | `vol_a/b/c` | Channel volumes (5 bits, bit 4 = envelope mode) |
| `psg` | `mixer` | Mixer register (R7) |
| `psg` | `noise` | Noise period (R6, 5 bits) |
| `psg` | `env_period` | 16-bit envelope period (R12<<8 \| R11) |
| `psg` | `env_shape` | Envelope shape (R13, 4 bits) |
| `crtc` | `regs` | Array of 14 hardware register values R0–R13 |
| `crtc` | `selected_reg` | Currently selected register (last write to `&BC00`) |
| `crtc` | `rasterline` | Current raster line within the frame |
| `crtc` | `vsync` | Current VSYNC output level |
| `fdc` | `msr` | Main Status Register of the PD765 |
| `fdc` | `sr0/sr1/sr2` | Status Registers 0/1/2 |
| `fdc` | `motor` | Drive motor state |
| `fdc` | `drive` | Active drive (0 or 1) |
| `emu` | `fps` | Current emulation speed |
| `emu` | `frame_ms` | Per-frame computation time in ms |
| `emu` | `frames` | Completed emulated frames since startup (0 = the emulation loop has not run yet; the clock an automation client must pace itself on — see `GET /api/ping`) |
| `emu` | `autotyping` | `true` while `POST /api/keytype` / `/api/keypress` still have characters or key presses to deliver |
| `emu` | `autotype_remaining` | How many are left (0 = idle). Counts bytes of the pending text plus queued VK presses |
| `emu` | `cpc_model` | CPC model: 0=464, 1=664, 2=6128, 4=6128+, 5=464+, 6=GX4000 |
| `emu` | `crtc_type` | CRTC type (0–4) |
| `emu` | `tl_active` | `true` if the timelapse is enabled and has at least one snapshot |
| `emu` | `tl_steps_back` / `tl_steps_fwd` | Steps available to navigate the timelapse backward/forward (context-filtered to `tl_step_kind`) |
| `emu` | `tl_step_kind` | Current step-context kind: `"frame"`, `"basic"`, or `"z80"` |
| `emu` | `ram_apply_seq` | Bumped once per queued `WebRamWrite` actually applied by the main thread; compare against the `seq` a `POST /api/ram`/`/api/exec` response returned before trusting a readback (see `WebRamWrite` above) |

---

### `GET /api/crtc`

Instantaneous snapshot of CRTC registers and selected counters.  
Direct read without lock (display-only data, accepts slight inconsistency).

**Response**: `200 application/json`

```json
{
  "regs": [63,40,46,142,38,0,25,30,0,7,0,0,48,0],
  "selected_reg": 0,
  "rasterline": 87,
  "vsync": false
}
```

| Field | Description |
|---|---|
| `regs[0]` R0 | Horizontal Total (chars per line − 1) |
| `regs[1]` R1 | Horizontal Displayed |
| `regs[2]` R2 | Horizontal Sync Position |
| `regs[3]` R3 | Sync Width (bits 3–0 = HSYNC width, bits 7–4 = VSYNC width) |
| `regs[4]` R4 | Vertical Total (char rows − 1) |
| `regs[5]` R5 | Vertical Total Adjust (raster lines) |
| `regs[6]` R6 | Vertical Displayed |
| `regs[7]` R7 | Vertical Sync Position |
| `regs[8]` R8 | Interlace and Skew |
| `regs[9]` R9 | Maximum Raster Address (scan lines per char row − 1) |
| `regs[10–11]` R10–R11 | Cursor Start / End Raster |
| `regs[12–13]` R12–R13 | Screen Start Address High / Low |
| `selected_reg` | Register currently selected (last `&BC00` write) |
| `rasterline` | Absolute raster line within the frame |
| `vsync` | Current VSYNC output level |

> **Note:** Internal counters (c0, c3h/v, c4, c5, c9), interlace mode,
> VMA addresses, and HSYNC are not yet exposed by the core API.

Also included in `GET /api/state` under the `"crtc"` key.

---

### `GET /api/config`

Returns the current configuration of `CORE_PARAM_IN`.

**Response**: `200 application/json`

```json
{
  "cpc_model": 2,
  "crtc_type": 0,
  "sound_output": 1,
  "freq_screen": 0,
  "extended_ram": 0,
  "ram_kb": 128,
  "rom_lang": "EN",
  "mapping_keyboard": false,
  "volume": 100
}
```

`extended_ram` is the raw `CORE_PARAM_IN.EXTENDED_RAM` index, which names the
*banked* half only (kept for existing clients). `ram_kb` is the machine's
**total** RAM in Ko — the 64 Ko of central RAM included — and is the unit
`POST /api/config` accepts, so the two round-trip.

Only 128, 192, 320 and 576 are ever reported. The core always provides one
banked 64 Ko bank on every model, so 128 Ko is the floor and no smaller machine
exists; and it delivers eight banks for every `CORE_EXTENDED_RAM_*` value at or
above 512 Ko, so larger indexes report 576.

`volume` is the live output volume (0–100). The frontend snapshots it every
frame, so it reflects changes made via hotkey (F7/F8), the mouse wheel, or this
endpoint. (SDL frontend; the Qt frontend has its own native volume widget.)

---

### `POST /api/config`

Enqueues a configuration or action command.  
The command is retrieved by `web_server_poll` at the next loop iteration
and applied by the main thread (including reset).

**Body**: `application/json` — all fields are optional.

```json
{
  "cpc_model":    2,
  "crtc_type":    0,
  "paused":       true,
  "do_soft_reset": false,
  "do_hard_reset": false
}
```

| Field | Type | Effect |
|---|---|---|
| `cpc_model` | integer | Change the CPC model (triggers an implicit reset on the application side) |
| `crtc_type` | integer | Change the CRTC type (same) |
| `ram_kb` | integer | **Total** RAM in Ko (central 64 Ko included): `128`, `192`, `320` or `576`. Any other value — including the banked sizes like `512` — is rejected (`400`, `field: ram_kb`) rather than clamped. Resizing the RAM forces a **hard reset** |
| `rom_lang` | string | ROM language: `"FR"`, `"EN"`, `"SP"`, `"DA"` |
| `paused` | boolean | Pause or resume emulation |
| `do_soft_reset` | boolean | Trigger a soft reset |
| `do_hard_reset` | boolean | Trigger a hard reset |
| `mapping_keyboard` | boolean | Enable/disable keyboard mapping mode |
| `volume` | integer | Set output volume 0–100 (SDL frontend; Qt uses its native widget) |
| `audio_device` | string | Switch the audio output device (`""` = system default). Device names come from `GET /api/audio/devices`. SDL frontend only |

**Success response**: `200 application/json` — `{"ok":true}`  
**Method error response**: `400 text/plain` — `Bad Request`

---

### `GET /api/ram?addr=<n>&len=<n>`

Reads a block of the 64 KB CPC RAM.

**Query parameters**:

| Parameter | Type | Default | Constraint |
|---|---|---|---|
| `addr` | integer (decimal or `0x` hex) | `0` | 0–65535 |
| `len` | integer | `256` | 1–65536 |
| `bank` | integer | `0` | `0` = central RAM; `1..N` = extended-RAM page `N−1` |
| `view` | string | (raw) | `cpu` = return memory **as the Z80 sees it** (lower/upper ROM overlays and RAM banking applied) instead of raw central RAM |

**Response**: `200 application/json`

```json
{
  "addr": 0,
  "len": 16,
  "hex": "c9000000000000000000000000000000"
}
```

`hex` is a lowercase ASCII hexadecimal string, `len × 2` characters long.

> **Known limitation — `bank=1..N` does not show live banked RAM.** These banks
> are read from `CORE_PARAM_OUT.Memory_Extended[]`, which is not the memory the
> Z80 actually uses: its 64 pointers are always non-null whatever
> `CORE_PARAM_IN.EXTENDED_RAM` is set to, and a byte the CPC writes into a
> paged-in bank (via `OUT (&7Fxx)`) never appears there. Measured against the
> prebuilt core by running real Z80 code. `bank=0` and `view=cpu` are
> unaffected — use `view=cpu` to inspect what is currently paged in at a given
> address. This predates the memory-size setting but becomes easier to hit now
> that more than 128 Ko can be selected.
With `view=cpu` the response also carries `"view":"cpu"`.

If `CORE_PARAM_OUT` is not provided in `WebServerOpts`, returns:
```json
{"error":"ram unavailable"}
```

---

### `POST /api/ram`

Writes bytes to CPC RAM and/or redirects the Z80 PC.  
Executed by `web_server_poll` at the next loop iteration.

**Body**: `application/json`

```json
{
  "addr": 4096,
  "data": "3e01cd00bb",
  "exec": true,
  "entry": 4096
}
```

| Field | Type | Role |
|---|---|---|
| `addr` | integer | Destination address (0–65535) |
| `data` | hex string | Bytes to write (spaces and `:` are tolerated, ignored) |
| `exec` | boolean | If `true`, the Z80 jumps to `entry` after the write |
| `entry` | integer | Target PC (default = `addr`) |

`data` empty + `exec: true` = simple PC redirection without write.

Queued rather than applied in place: several calls landing in the same poll
tick are all kept and applied in order (see `WebRamWrite` above).

**Response**: `200 application/json` — `{"ok":true,"seq":N}`, where `N` is the
value `GET /api/state`'s `emu.ram_apply_seq` will reach once this write has
actually been applied — poll it instead of immediately reading RAM back.

---

### `POST /api/exec`

Redirects the Z80 PC without RAM write.  
Shortcut equivalent to `POST /api/ram` with empty `data` and `exec: true`.

**Body**:

```json
{"addr": 4096}
```

**Response**: `200 application/json` — `{"ok":true,"seq":N}` (same `ram_apply_seq` contract as `POST /api/ram` above)

---

### `POST /api/keytype`

Sends a text string to the emulator as if it had been typed on the keyboard.
Successive calls accumulate in one queue, so text posted while a previous string
is still being typed is appended, never dropped.

**Body**: `application/json`

```json
{"text": "RUN\r"}
```

Use `\r` (carriage return) to simulate the Enter key.

```bash
curl -X POST http://127.0.0.1:8765/api/keytype \
     -H 'Content-Type: application/json' \
     -d '{"text":"RUN\r"}'
```

**Response**: `200 application/json` — `{"ok":true}`

**Pacing** — *not* one character per frame (that claim was wrong):

| Character | Emulated frames | Why |
|---|---|---|
| plain | `autotype_speed` (default **4**) | press on frame 1, release at `speed / 2` |
| needs CPC SHIFT (uppercase, `"`, …) | `speed / 2 + 3` | the core's ~20 ms SHIFT anti-parasite has to drain |
| same character as the next one | **9** | its own longer press + guard frames, and CPC SHIFT held across the run — the core applies a release up to ~4 frames late and drops a press landing in that window, so `"HELLO"` used to arrive as `"HELO"` |

So `RUN"DIAG"` is ~45 frames (~0.9 s), not 9. Do not derive a frame budget from the
string length: poll instead.

**Completion** — `emu.autotyping` / `emu.autotype_remaining` (`GET /api/ping`,
`GET /api/state`) report whether characters or queued key presses are still to be
delivered. `autotyping` is true from the moment this endpoint returns, so a client
can post and then poll:

```bash
curl -sX POST .../api/keytype -H 'Content-Type: application/json' -d '{"text":"RUN\"DIAG\"\r"}'
until [ "$(curl -s .../api/ping | jq .emu.autotyping)" = false ]; do sleep 0.1; done
```

**Ordering with `/api/keypress`** — the VK queue is drained only once the text
queue is empty, so "type a command, then press Enter" is ordered by construction
whichever endpoint is used, even if the second request arrives mid-typing. (Before
this, the two ran as independent per-frame state machines: an Enter posted 0.3 s
into `RUN"DIAG"` executed `RUN` on its own and the rest of the string landed on the
next prompt.)

---

### `POST /api/basic`

Tokenizes an ASCII text Locomotive BASIC program and injects it directly
into CPC RAM at address `0x0170` at the next loop iteration.

BASIC program end pointers (`0xAE66`) are updated automatically.
The `AUTO` (`0xAC01`), `ERR` (`0xAD90`) and `PROTECT` (`0xAE2C`) flags are cleared.

After injection, type `RUN` or `LIST` in the emulator.

**Body**: `text/plain` — BASIC source with line numbers.

**Query parameters** (optional):

| Parameter | Type | Default | Effect |
|---|---|---|---|
| `reset` | `0` or `1` | `0` | Hard reset before injection |
| `run` | `0` or `1` | `0` | Auto-type `RUN` after injection |

Expected format: one statement per line, line number required.

```
10 MODE 1
20 BORDER 0
30 INK 0,0:INK 1,26
40 PRINT "HELLO"
50 GOTO 40
```

All Locomotive BASIC keywords, functions and operators of the 6128 are supported.  
Maximum size: from `0x0170` to `0xAE66` (~44 KB).

```bash
# Inline program
curl -X POST http://127.0.0.1:8765/api/basic \
     -H 'Content-Type: text/plain' \
     --data-binary '10 MODE 1
20 BORDER 0
30 INK 0,0:INK 1,26
40 PRINT "HELLO FROM AMSPIRIT"
50 GOTO 40'
```

```bash
# From a .bas file
curl -X POST http://127.0.0.1:8765/api/basic \
     -H 'Content-Type: text/plain' \
     --data-binary @myprog.bas
```

```bash
# Inject and launch automatically
curl -X POST http://127.0.0.1:8765/api/basic?run=1 \
     -H 'Content-Type: text/plain' \
     --data-binary '10 PRINT "LOOP":GOTO 10'
```

The window title bar confirms the injection:
- success: `BASIC injected — type LIST or RUN`
- failure (program too large): `BASIC inject failed: program too large`

**Response**: `200 application/json` — `{"ok":true}`

---

### `GET /api/basic_state`

Returns the current state of the Locomotive BASIC interpreter in RAM.

**Response**: `200 application/json`

```json
{
  "basic_ver": 11,
  "prog_start": 368,
  "txttop": 880,
  "vartop": 920,
  "arrend": 920,
  "prog_size": 512,
  "var_size": 40,
  "chain_heads_addr": 44471,
  "cur_linenum": 30,
  "stmt_addr": 44573
}
```

| Field | Description |
|---|---|
| `basic_ver` | BASIC version: `10` (464, BASIC 1.0) or `11` (others, BASIC 1.1) |
| `prog_start` | Program start address (always `0x0170` = 368) |
| `txttop` | End-of-program pointer (start of the variable area) |
| `vartop` | End of scalar variables / start of the array area |
| `arrend` | End of the array area |
| `prog_size` | Program size in bytes (`txttop − prog_start`) |
| `var_size` | Scalar-variable area size in bytes |
| `chain_heads_addr` | Address of the 27×2 scalar-variable anchor table (`0xADB7`) |
| `cur_linenum` | BASIC line being executed, derived from the text pointer at `0xAE1D`; `65535` (`0xFFFF`) in direct mode |
| `stmt_addr` | Current execution address (`0xAE1B`) — the statement currently being interpreted (statement-level granularity) |

---

### `GET /api/basic_export`

Detokenizes and exports the current BASIC program from RAM as source text.

**Query parameters** (optional):

| Parameter | Type | Default | Effect |
|---|---|---|---|
| `verbose` | `0` or `1` | `0` | Include extra whitespace for readability |

**Response**: `200 text/plain; charset=utf-8` — Locomotive BASIC source

```bash
curl http://127.0.0.1:8765/api/basic_export > exported.bas
curl http://127.0.0.1:8765/api/basic_export?verbose=1 > exported_readable.bas
```

If no BASIC program is loaded or RAM is unavailable, returns an empty response.

---

### `POST /api/keypress`

Sends a single virtual key code to the emulator (CPC-specific key).

**Body**: `application/json`

```json
{"vk": 32}
```

| Field | Type | Role |
|---|---|---|
| `vk` | integer | Virtual key code (0–0xFF, from `CORE_rVK_*` constants) |

This is an alternative to `/api/keytype` for sending pre-mapped CPC key codes directly, useful for non-ASCII keys (arrows, function keys, etc.).

Presses are queued and delivered *after* any pending `/api/keytype` text (see that
endpoint's **Ordering** note), and count towards `emu.autotype_remaining`.

**Shifted letter codes**: the `CORE_rVK_MAJ_*` range (uppercase letters) needs the
CPC SHIFT held alongside the key, which this endpoint now synthesises — pressing
`CORE_rVK_MAJ_R` (0x1F) produced nothing at all before. Prefer `/api/keytype` for
text: it resolves the whole shift/control layer from the characters themselves.

**Response**: `200 application/json` — `{"ok":true}`

---

### `GET /api/keymap`

Returns the current keyboard mapping as JSON.

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
    },
    ...
  ]
}
```

| Field | Description |
|---|---|
| `layout` | Current keyboard layout (`"FR"`, `"EN"`, `"US"`, `"ES"`, `"DA"`, `"DE"`, `"IT"`, `"PT"`, `"BE"`, `"SW"`, `"CA"`) |
| `mapping` | Array of key mappings; each entry describes one physical key |
| `sdl_keycode` | SDL2 key code from the event (internal identifier) |
| `vk` | CPC virtual key code without shift modifier |
| `vk_with_shift` | CPC virtual key code with shift modifier (`-1` if no shift variant) |
| `nomod` | `true` if shift is suppressed for this key when typed |

Used by the web interface to display the current keymap layout.

---

### `GET /api/script`

Returns the current state of the CSL/Lua scripting engine.

**Response**: `200 application/json`

```json
{"running": false, "error": ""}
```

| Field | Description |
|---|---|
| `running` | `true` if a script is currently running |
| `error` | Error message from the last script, empty if no error |
| `output` | Everything `print()` produced, newline-separated (capped at 64 KiB, then `[output truncated]`) |

```bash
curl http://127.0.0.1:8765/api/script
```

---

### `POST /api/script[?lang=lua]`

Launches a CSL or Lua script.  
The request body is the raw source of the script.  
By default the language is CSL (macro-language style Locomotive BASIC).  
Add `?lang=lua` for raw Lua 5.4.

> **Sandboxed.** A script arriving here did not necessarily come from you: the
> server answers with `Access-Control-Allow-Origin: *` and no token, so any page
> open in your browser can POST one. It therefore runs with a pruned stdlib —
> no `io`, `package`, `debug`, `require`, `dofile`, `loadfile`, no
> `os.execute`/`getenv`/`remove`/`rename`/`exit`, `load()` restricted to text
> chunks. Files go through the jailed `fs.*` table (see
> [scripting.md](scripting.md#file-access--fs)). A script loaded locally
> (`--script`, drag & drop) keeps the full stdlib. Start the emulator with
> `--lua-full-stdlib` to give network scripts the full stdlib too.

```bash
# CSL script
curl -X POST 'http://127.0.0.1:8765/api/script' \
     -H 'Content-Type: text/plain' \
     --data-binary @myscript.csl

# Lua script
curl -X POST 'http://127.0.0.1:8765/api/script?lang=lua' \
     -H 'Content-Type: text/plain' \
     --data-binary @myscript.lua
```

**Response**: `200 application/json` — `{"ok":true}`

---

### `GET /console`

Serves `amspirit-lite-console.html` — the interactive Lua console — taken from
the **same directory** as the `--web-html` UI file. No separate option: the two
pages travel together in every package, so a second path to keep in sync would
only be a second thing to get wrong. `404` with a hint if the file is not there.

It is a page of its own rather than a tab of the debug UI: it reloads without
disturbing the debugger's state and sits in a second browser tab beside it. The
Script tab of the main UI links to it.

The page also works opened straight from disk (`file://`) — it detects that and
targets `http://127.0.0.1:8765` absolutely, like the other standalone pages in
`src/assets/`.

---

### `POST /api/eval`

Evaluates **one Lua chunk** on the *persistent* interactive state: globals set
by one eval are still there for the next. This is the console endpoint.

Unlike every other POST on this API, an eval has an **answer**, so this route is
request/response: the POST issues a `seq`, and `GET /api/eval?seq=N` reads the
outcome back. Same contract as `ram_write_seq` / `ram_apply_seq` — acking the
queueing is not acking the result.

The body is the chunk, taken verbatim: **no CSL preprocessing on this route**
(CSL is a file format). A bare expression works — the chunk is tried as
`return <body>` first, like the stock `lua` REPL — so its value comes back in
`value`.

Sandboxed exactly like `POST /api/script`.

```bash
curl -X POST http://127.0.0.1:8765/api/eval --data-binary 'cpc.getZ80().PC'
# -> {"ok":true,"seq":1}
```

**Response**: `200 application/json` — `{"ok":true,"seq":<n>}`

`400` is returned rather than a `seq` when:

- an eval is **already queued** — overwriting it would lose the first line's
  result before anyone could read it;
- a script or eval is **still running** (`busy: …`). Accepting it would issue a
  `seq` the main thread could only reject, and that rejection would land on the
  running eval's result slot.

So `refused: true` on `GET /api/eval` is the rare race, not the normal path:
the check above reads a flag published once per frame.

---

### `GET /api/eval?seq=N`

Reads the outcome of eval `N`.

```bash
curl 'http://127.0.0.1:8765/api/eval?seq=1'
# -> {"seq":1,"known":true,"done":true,"refused":false,
#     "value":"38130","output":"","error":""}
```

| Field | Description |
|---|---|
| `known` | `false` = that seq is gone (a later eval superseded it), or was never issued |
| `done` | `false` while the chunk is **queued or running** — the main thread picks a request up on its next frame, and an eval may then `wait()` across further frames, so the first poll after the POST normally answers `known:true, done:false` |
| `refused` | `true` = the engine was busy (a script or another eval owns the frame loop) and **nothing ran** |
| `value` | Formatted return values, tab-separated; empty when the chunk returned nothing |
| `output` | `print()` capture, same cap as `/api/script` |
| `error` | Parse or runtime error, empty on success |

**Response**: `200 application/json`. Missing or non-positive `seq` → `400`.

---

### `DELETE /api/eval`

Drops the persistent interactive state — the console's "clear session". The
globals built up by previous evals are lost. Refused (logged, not an HTTP
error) if something is still running.

```bash
curl -X DELETE http://127.0.0.1:8765/api/eval
```

**Response**: `200 application/json` — `{"ok":true}`

---

### `DELETE /api/script`

Interrupts the currently running script.

```bash
curl -X DELETE http://127.0.0.1:8765/api/script
```

**Response**: `200 application/json` — `{"ok":true}`

---

## CPU Debugging Endpoints

These power the **CPU** tab (disassembler, single-step, executed-code map,
instruction history). Stepping requires the emulator to be paused.

### `POST /api/step`

Executes **exactly one Z80 instruction** then re-pauses. The emulator is
briefly resumed and stopped again once the PC has advanced past the current
instruction (so it works even though the CPU is already sitting on an
instruction boundary while paused).

**Response**: `200 application/json` — `{"ok":true}`

---

### `GET /api/history`

Returns the last 20 executed Z80 instructions (oldest first). The opcode bytes
are read from the **CPU-visible** memory (ROM/RAM mapping applied), so firmware
code shows the bytes actually fetched.

**Response**: `200 application/json`

```json
[
  {"pc":47426,"hex":"3E0100BB"},
  {"pc":47428,"hex":"CD00BB00"}
]
```

| Field | Description |
|---|---|
| `pc` | Address of the instruction |
| `hex` | Up to 4 opcode bytes at `pc`, uppercase hex |

---

### `GET /api/codemap` · `DELETE /api/codemap`

`GET` returns a 65536-bit bitmap (8192 bytes, hex) marking every address at
which an instruction has **started executing** since the last reset. Bit
`addr` is set when an instruction begins at that address. Used to colour
"code" vs "data" zones in the disassembler.

```json
{"hex":"0000....ffff"}
```

`DELETE` clears the bitmap (and the instruction history).

**Response**: `200 application/json` — `{"ok":true}` for `DELETE`.

---

## Memory-Map Endpoint

### `GET /api/screenshot`

Returns the current frame as a PNG — the whole point of the endpoint being that no
script, no file and no disk round-trip is involved. This is what the embedded UI's
screen view polls, and what an automation harness should use to capture the screen.

**Query parameters** (all optional; each defaults to the behaviour the UI relies
on, so `GET /api/screenshot` with no parameters keeps working exactly as before):

| Parameter | Default | Effect |
|---|---|---|
| `crop` | `1` | `1` = visible screen area only, `0` = full physical buffer (1024×350, sync borders included) |
| `live` | `1` while paused, else `0` | `1` = in-progress buffer (the frame being drawn), `0` = last settled frame |
| `full` | `1` | `1` = plain complete frame, `0` = composite (in-progress frame over the previous one, for debugging a partial screen) |

`live` is forced to `0` while the timelapse is rewound: the core does not snapshot
the in-progress backbuffer, so it would be stale.

**Response**: `200 image/png`, or `503 {"error":"no frame available"}` before the
first frame has been rendered.

**Response headers** — the geometry the PNG was cut from, and where the CTM beam
was when it was taken (video-buffer space, the same coordinates
`POST /api/raster_bp` takes):

| Header | Meaning |
|---|---|
| `X-Beam-X`, `X-Beam-Y` | beam position at capture time |
| `X-Crop-X`, `X-Crop-Y` | top-left of the returned area in the physical buffer |
| `X-Crop-W`, `X-Crop-H` | its size (`768×272` cropped, `1024×350` full) |

```bash
curl -s 'http://127.0.0.1:8765/api/screenshot?crop=1&full=1&live=0' -o screen.png
```

---

### `GET /api/memmap`

Returns the current ROM/RAM mapping for each 16 KB region, plus the RAM
banking configuration. Drives the memory-map bar in the CPU tab.

**Response**: `200 application/json`

```json
{
  "regions": [
    {"base":0,    "name":"0000","rom":true, "rom_bank":255},
    {"base":16384,"name":"4000","rom":false,"ram_bank":1,"ext":false},
    {"base":32768,"name":"8000","rom":false,"ram_bank":2,"ext":false},
    {"base":49152,"name":"C000","rom":true, "rom_bank":0}
  ],
  "rmr": 137,
  "ram_mode": 0,
  "ram_page": 0
}
```

| Field | Description |
|---|---|
| `regions[].base` / `name` | 16 KB region base address |
| `regions[].rom` | `true` if ROM is currently mapped at this region |
| `regions[].rom_bank` | ROM number (`255` = lower/firmware ROM, else upper-ROM number, e.g. 0 = BASIC, 7 = AMSDOS) — only when `rom` |
| `regions[].ram_bank` | Physical RAM bank (0–3 central; 4+ extended) — only when `!rom` |
| `regions[].ext` | `true` if this RAM bank comes from extended RAM |
| `rmr` | Gate Array RMR register value |
| `ram_mode` | RAM banking configuration (the `&7Fxx` value, 0–7) |
| `ram_page` | Extended-RAM page (0–3) |

---

## Render / CRT Endpoints

Drive the **Render** tab and mirror the Qt CRT-settings dialog.

### `GET /api/render`

Returns the current CRT monitor preset, screen type and shader parameters.

**Response**: `200 application/json`

```json
{
  "monitor": 1,
  "monitor_name": "CTM644",
  "screen_type": 0,
  "presets": ["Off","CTM644","GT65","TV"],
  "crt": {
    "curvature": 0.005, "scanline": 0.30, "sharpness": 0.80,
    "maskType": 4, "maskPitch": 3.0, "mask": 0.15,
    "halation": 0.12, "diffusion": 0.10, "convergence": 0.0,
    "brightness": 1.0, "persistence": 0.0
  }
}
```

| Field | Description |
|---|---|
| `monitor` / `monitor_name` | Current monitor preset index (0–3) and name |
| `screen_type` | Screen type: 0 = colour, 1 = green, 2 = colour (ASIC), 3 = green (ASIC) |
| `presets` | Available monitor preset names |
| `crt` | CRT shader parameters (see `POST /api/render`) |

### `POST /api/render`

Changes the monitor preset, screen type and/or CRT shader parameters. Any
subset of the keys may be sent. `crt` is applied as a whole set when present.

**Body**: `application/json`

```json
{ "monitor": 2 }
{ "screen_type": 1 }
{ "crt": { "curvature":0.005, "scanline":0.30, "sharpness":0.80,
           "maskType":4, "maskPitch":3.0, "mask":0.15, "halation":0.12,
           "diffusion":0.10, "convergence":0.0, "brightness":1.0, "persistence":0.0 } }
```

Selecting a `monitor` preset loads that preset's default parameters. Ranges:
`curvature` 0–0.03, `scanline`/`sharpness`/`mask`(≤0.25)/`halation`/`diffusion`/`persistence` 0–1,
`maskType` 0–4, `maskPitch` ~1–6, `convergence` −2…2, `brightness` 0.1–3.

**Response**: `200 application/json` — `{"ok":true}`

---

## BASIC Debugger Endpoints

These power the **BASIC** tab (live listing with current-line/statement
highlight, line/statement stepping, breakpoints, run-to, variable hover). They
rely on the Locomotive BASIC text pointers `0xAE1D` (current line) and `0xAE1B`
(current statement / execution address).

### `GET /api/basic_listing`

Returns the program decoded into lines and statements, each with its RAM
address range — used to render the listing and highlight the live execution
point (line via `cur_linenum`, statement via `stmt_addr`).

**Response**: `200 application/json`

```json
{
  "lines": [
    {
      "addr": 368, "num": 10,
      "stmts": [
        {"addr": 371, "end": 378, "colon": false, "text": "A=A+1", "vars": ["A"]},
        {"addr": 378, "end": 385, "colon": true,  "text": "GOTO 10", "vars": []}
      ]
    }
  ]
}
```

| Field | Description |
|---|---|
| `lines[].addr` / `num` | Line-record address and BASIC line number |
| `stmts[].addr` | Value `0xAE1B` holds while this statement runs (statement start) |
| `stmts[].end` | Exclusive upper bound of the statement's address range |
| `stmts[].colon` | `true` if a `:` should precede this statement when displayed |
| `stmts[].text` | Detokenized statement text |
| `stmts[].vars` | Variable names referenced (display form, e.g. `A%`, `MSG$`) — used for the hover tooltip |

---

### `POST /api/basic_step[?mode=line]`

Resumes the program and re-pauses once it advances:
- default (no `mode`): to the **next statement** (watches `0xAE1B`);
- `?mode=line`: to the **next BASIC line** (watches the line number).

Only meaningful while a program line is running (not in direct mode).

**Response**: `200 application/json` — `{"ok":true}`

---

### `POST /api/basic_bp`

Replaces the BASIC line-breakpoint set. Body is a comma-separated list of line
numbers (empty body clears all). While breakpoints exist, the emulator pauses
when execution reaches a breakpoint line.

```bash
curl -X POST http://127.0.0.1:8765/api/basic_bp -d '10,40,100'
curl -X POST http://127.0.0.1:8765/api/basic_bp -d ''     # clear all
```

**Response**: `200 application/json` — `{"ok":true}`

---

### `POST /api/basic_runto?line=<n>` · `POST /api/basic_runto?addr=<n>`

One-shot "run to": resumes and pauses when execution reaches the given BASIC
line (`line=`) or statement address (`addr=`, an `0xAE1B` value from
`/api/basic_listing`). The target is cleared once hit.

**Response**: `200 application/json` — `{"ok":true}`

---

### `GET /api/scan_ptr`

Diagnostic helper for locating BASIC pointers: scans RAM (outside the program
region) for 16-bit little-endian words that point **into** the program
`[0x170, txttop)`, and reports which BASIC line each points into. Pause on a
known line, then match the candidate whose `line` matches.

**Response**: `200 application/json`

```json
{"txttop":880,"candidates":[{"addr":44573,"target":373,"line":10}],"count":1}
```

---

## Per-Subsystem State Endpoints

Lightweight alternatives to `GET /api/state` when only one subsystem is needed.

### `GET /api/z80`

Returns Z80 registers only. Same payload as the `"z80"` object in `GET /api/state`.

**Response**: `200 application/json` — Z80 register object (see `/api/state` `"z80"` fields).

---

### `GET /api/ga`

Returns Gate Array state. Same payload as the `"ga"` object in `GET /api/state`.

**Response**: `200 application/json`

---

### `GET /api/psg`

Returns PSG (AY-3-8912) register state. Same payload as the `"psg"` object in `GET /api/state`.

**Response**: `200 application/json`

---

### `GET /api/fdc`

Returns FDC (PD765) register state. Same payload as the `"fdc"` object in `GET /api/state`.

**Response**: `200 application/json`

---

### `GET /api/keymatrix`

Returns the current state of the 10-row CPC keyboard matrix (raw hardware view, one byte per row).

**Response**: `200 application/json`

```json
{"matrix": [255,255,255,255,255,255,255,255,255,255]}
```

Each byte is a bitmask of the 8 keys in that row (0 = key pressed, 1 = released, CPC active-low convention).

---

## Audio Endpoints

### `GET /api/audio`

Returns a snapshot of the last N mixed audio frames directly from the emulator's 64 KB circular sound buffer.

**Query parameters**:

| Parameter | Type | Default | Description |
|---|---|---|---|
| `frames` | integer | `512` | Number of S16LE frames to return (1–2048) |

**Response**: `200 application/json`

```json
{"stereo": false, "frames": 512, "hex": "0000..."}
```

`hex` is lowercase S16LE PCM data (`frames × bytes_per_frame × 2` characters).

---

### `GET /api/audio/record`

Returns audio from the ring buffer (filled by `web_audio_push` each frame).
Supports both JSON (for spectrum analysis) and WAV download.

**Query parameters**:

| Parameter | Type | Default | Description |
|---|---|---|---|
| `seconds` | float | `2.0` | Duration of the window to return (capped to available history) |
| `frames` | integer | `2048` | Output frame count for JSON mode |
| `offset` | float | `0.0` | Seconds before the end of the recording to start |
| `format` | string | — | `wav` = return a PCM WAV attachment instead of JSON |

**JSON response** (`200 application/json`):

```json
{
  "stereo": false, "hz": 44100, "frames": 2048,
  "seconds": 2.0, "cap_seconds": 30.0, "filled_seconds": 5.2,
  "hex": "..."
}
```

**WAV response** (`200 audio/wav`): attachment `cpc_audio.wav`, standard PCM-16.

Requires the ring buffer to be initialised by the frontend via `web_audio_ring_init()`.

---

### `GET /api/audio/devices`

Lists the audio output devices available on this machine, and which one is currently selected. Names come from `WebServerOpts::audio_devices`, populated by the frontend at startup; feed one back via `POST /api/config` (`audio_device` field).

**Response**: `200 application/json`

```json
{"devices": ["", "HDA Intel PCH", "USB Audio"], "current": ""}
```

An empty device name means "system default".

```bash
curl http://127.0.0.1:8765/api/audio/devices
```

---

## Z80 Breakpoints

### `POST /api/z80_bp`

Replaces the Z80 PC breakpoint set. While breakpoints are active, the emulator pauses when the PC hits a breakpoint address.

**Body**: comma-separated list of addresses — decimal, hex (`0x…`), or bank-qualified (`Cx:YYYY` where `x` is the bank number 0–N and `YYYY` is a hex offset within the bank). Empty body clears all.

```bash
# Flat address
curl -X POST http://127.0.0.1:8765/api/z80_bp -d '0xC000,0xBD19'

# Bank-qualified (extended RAM: C4 = bank 4, offset 0x0200)
curl -X POST http://127.0.0.1:8765/api/z80_bp -d 'C4:0200'

# Clear all
curl -X POST http://127.0.0.1:8765/api/z80_bp -d ''
```

**Response**: `200 application/json` — `{"ok":true}`

---

## Timelapse & Raster Debugging

### `POST /api/tl_back`

Navigates the timelapse one step back. Only meaningful while a timelapse is active (`emu.tl_active`, see `GET /api/state`) — check `emu.tl_steps_back` first to know if there is anywhere to go.

```bash
curl -X POST http://127.0.0.1:8765/api/tl_back
```

**Response**: `200 application/json` — `{"ok":true}`

---

### `GET /api/beam`

Returns the current CTM beam position and the crop rectangle for a given `crop=` mode, in the same video-buffer coordinate space as `POST /api/raster_bp` and the `X-Beam-*`/`X-Crop-*` headers of `GET /api/screenshot`.

**Not** what the Screen tab's crosshair uses — that reads the screenshot response's own `X-Beam-*`/`X-Crop-*` headers instead, so the position matches the exact pixels returned in the same response (a separate request here would race against the beam continuing to move). Kept as a standalone query for other tooling.

**Query parameters**:

| Parameter | Type | Default | Effect |
|---|---|---|---|
| `crop` | `0` or `1` | `1` | `1` = crop rectangle is the visible screen area, `0` = full physical buffer |

**Response**: `200 application/json`

```json
{"x": 412, "y": 87, "cx": 96, "cy": 39, "cw": 768, "ch": 272}
```

```bash
curl 'http://127.0.0.1:8765/api/beam?crop=1'
```

---

### `POST /api/raster_bp?x=<n>&y=<n>&enable=<0|1>`

Arms or disarms a raster breakpoint at a pixel in video-buffer space (same coordinates as `GET /api/beam` and the crop headers of `GET /api/screenshot`). Missing `x`/`y`, or `enable=0`, disarms it.

**Query parameters**:

| Parameter | Type | Default | Effect |
|---|---|---|---|
| `x` | integer | — | Target column, 0–65535 |
| `y` | integer | — | Target line, 0–65535 |
| `enable` | `0` or `1` | `1` if both `x`/`y` given, else `0` | `0` disarms regardless of `x`/`y` |

```bash
# Arm at (256, 120)
curl -X POST 'http://127.0.0.1:8765/api/raster_bp?x=256&y=120'

# Disarm
curl -X POST 'http://127.0.0.1:8765/api/raster_bp?enable=0'
```

**Response**: `200 application/json` — `{"ok":true}`  
**Error**: `400 application/json` — `{"error":"query parameter \"x\" must be between 0 and 65535","field":"x"}`

---

## UI Language

### `GET /api/lang`

Returns the current UI language.

**Response**: `200 application/json` — `{"lang":"en"}` (values: `en`, `fr`, `es`, `de`)

---

### `POST /api/lang`

Changes the UI language.

**Body**: `application/json` — `{"lang":"fr"}`

**Response**: `200 application/json` — `{"ok":true}`  
**Error**: `400 application/json` — `{"error":"invalid lang"}`

---

## Disk Endpoints

### `POST /api/disk`

Disk management: create a blank disk or save (download) the current disk image.

**Body**: `application/json`

| Field | Type | Values | Effect |
|---|---|---|---|
| `action` | string | `"create"` | Insert a blank formatted DSK into the given drive |
| `action` | string | `"save"` | Export the current DSK image as a file download |
| `drive` | integer | `0` (A) or `1` (B) | Target drive (default `0`) |

```bash
# Create a blank disk in drive A
curl -X POST http://127.0.0.1:8765/api/disk \
     -H 'Content-Type: application/json' \
     -d '{"action":"create","drive":0}'

# Download current disk A as a DSK file
curl -X POST http://127.0.0.1:8765/api/disk \
     -H 'Content-Type: application/json' \
     -d '{"action":"save","drive":0}' -o disk_A.dsk
```

**Create response**: `200 application/json` — `{"ok":true}`  
**Save response**: `200 application/octet-stream` — attachment `disk_A.dsk` (or `disk_B.dsk`)  
**Save error** (no disk or failed): `500 application/json` — `{"error":"no disk or save failed"}`

---

## Media Loading

### `POST /api/media?name=<filename>&drive=<0|1>`

Loads a media file into the emulator from the raw request body — the SNA/DSK/
HFE/IPF/CPR/CRO/BIN counterpart of drag-and-drop or the frontend's `Ctrl+O`
file picker (`.cdt` is not currently supported here, see the format table
below). The format is autodetected from content (magic bytes), same as
everywhere else in the app; `name` only matters for a headerless raw
`.bin`/`.amsdos` payload, which cannot be autodetected and is instead routed
by extension (see below).

**Body**: `application/octet-stream` — the raw file bytes.

**Query parameters**:

| Parameter | Type | Default | Effect |
|---|---|---|---|
| `name` | string (URL-encoded) | — | Filename, e.g. `game.dsk`. Required for `.bin`/`.amsdos`; used to label the loaded media otherwise. |
| `drive` | `0` or `1` | `0` | Target floppy drive for DSK/HFE/IPF images (A/B) |

Like the other mutating routes, the request only enqueues the load; it is
applied on the main thread at the next loop iteration (`Core_*` calls are not
safe from the web server's thread). The response confirms the upload was
queued, not that the load succeeded — check the application log, or a
follow-up `GET /api/state` / `GET /api/fdc` (disk activity) or `GET
/api/basic_state` (SNA restores BASIC state) to confirm the effect.

Supported formats and how each is detected:

| Format | Detection | Notes |
|---|---|---|
| `.sna` snapshot | content (`MV - SNA` magic) | Restores the full machine state |
| `.dsk` (standard/extended) | content (`MV - CPCEMU` / `MV - CPC Disk-File` / `EXTENDED CPC DSK` magic) | Inserted into `drive` |
| `.hfe` | content (`HXCPICFE` magic) | Inserted into `drive` |
| `.ipf` | content (`CAPS` magic) | Inserted into `drive` |
| `.cpr` cartridge | content (`RIFF...AMS` magic) | Loaded as a standard cartridge |
| `.cro` ROM set | content (`RIFF...CRO ` magic) | Triggers a hard reset |
| `.bin`/`.amsdos` | **filename extension**, not content | AMSDOS-header binaries load directly; a headerless raw binary needs an explicit load address via `name=game@4000.bin` (optionally `@ENTRY`), e.g. `name=game@4000@4000.bin` |
| anything else (including `.cdt` tape) | fallback — no signature matched | **Known limitation**: unlike `.bin`/`.amsdos`, `.cdt` has no content signature and is *not* routed by filename extension either — the `name=` hint only special-cases `.bin`/`.amsdos`. A `.cdt` posted here currently falls through to the raw-binary path and will not load as a tape. This also affects SDL2/Qt drag-and-drop, not just this endpoint; tracked separately, not fixed by this doc update. |

```bash
# Insert a DSK into drive A
curl -X POST 'http://127.0.0.1:8765/api/media?name=game.dsk&drive=0' \
     -H 'Content-Type: application/octet-stream' \
     --data-binary @game.dsk

# Restore a snapshot
curl -X POST 'http://127.0.0.1:8765/api/media?name=save.sna' \
     -H 'Content-Type: application/octet-stream' \
     --data-binary @save.sna

# Headerless raw binary, load address 0x4000
curl -X POST 'http://127.0.0.1:8765/api/media?name=game@4000.bin' \
     -H 'Content-Type: application/octet-stream' \
     --data-binary @game.bin
```

**Response**: `200 application/json` — `{"ok":true}`
**Error** (empty body): `400 application/json` — `{"error":"empty body: expected the raw media file bytes"}`

**Native-transport only**: this endpoint requires the socket server (SDL2/Qt/
SDL2-imgui native builds). The WASM build's `ams_web_request` bridge marshals
the body as a NUL-terminated C string and cannot carry arbitrary binary data,
so `/api/media` is not usable there — use the browser's own file-open UI on
that target instead.

---

## Keyboard Remapping

### `POST /api/keymap`

Applies a live keymap binding change — remaps a physical key to a different CPC VK code.

**Body**: `application/json`

| Field | Type | Role |
|---|---|---|
| `kc` | hex string | Platform keycode (SDL keycode as `"0x..."`or decimal) |
| `vk` | integer | CPC VK code for normal press (0–0xFF) |
| `vk_s` | integer | CPC VK code for shifted press (omit or same as `vk` if no distinction) |
| `nomod` | boolean | Suppress CPC Shift while this key is active |

```bash
curl -X POST http://127.0.0.1:8765/api/keymap \
     -H 'Content-Type: application/json' \
     -d '{"kc":"0x61","vk":1,"vk_s":1,"nomod":false}'
```

**Response**: `200 application/json` — `{"ok":true}`  
**Error**: `400 application/json` — e.g. `{"error":"missing field \"kc\": the platform keycode to remap","field":"kc"}` (see "Request bodies and errors" above)

---

## Endpoint Summary Table

| Method | Path | Description |
|---|---|---|
| GET | `/` | HTML web interface |
| GET | `/api/ping` | Lightweight connectivity probe (also returns emu state) |
| GET | `/api/state` | Full emulator state: Z80 / GA / PSG / FDC / emu |
| GET | `/api/z80` | Z80 registers only |
| GET | `/api/ga` | Gate Array registers only |
| GET | `/api/psg` | PSG registers only |
| GET | `/api/fdc` | FDC registers only |
| GET | `/api/keymatrix` | Raw 10-row CPC keyboard matrix |
| GET | `/api/config` | Current emulator configuration |
| POST | `/api/config` | Change model, CRTC, language, reset, pause, keyboard mapping |
| GET | `/api/lang` | Current UI language (`en`/`fr`/`es`/`de`) |
| POST | `/api/lang` | Change UI language |
| GET | `/api/ram?addr=N&len=N[&bank=N][&view=cpu]` | Read bytes from RAM (raw, extended bank, or CPU-visible view) |
| POST | `/api/ram` | Write bytes to RAM (optional execution) |
| POST | `/api/exec` | Redirect Z80 PC |
| POST | `/api/step` | Execute one Z80 instruction, then pause |
| POST | `/api/z80_bp` | Set/clear Z80 PC breakpoints |
| GET | `/api/history` | Last 20 executed Z80 instructions |
| GET | `/api/codemap` | Executed-instruction bitmap (code/data zones) |
| DELETE | `/api/codemap` | Reset the executed-instruction bitmap + history |
| GET | `/api/memmap` | ROM/RAM mapping per 16 KB region + RAM banking config |
| GET | `/api/screenshot[?crop=N&live=N&full=N]` | Current frame as a PNG (+ beam/crop headers) |
| GET | `/api/render` | Current CRT monitor preset, screen type, shader params |
| POST | `/api/render` | Change monitor preset / screen type / CRT shader params |
| GET | `/api/audio` | Audio snapshot (last N frames from emulator buffer) |
| GET | `/api/audio/record[?format=wav]` | Ring-buffer audio window (JSON or WAV download) |
| GET | `/api/audio/devices` | List audio output devices and the current selection |
| POST | `/api/disk` | Create blank disk or save/download current disk image |
| POST | `/api/media?name=N&drive=N` | Load a SNA/DSK/HFE/IPF/CPR/CRO/BIN file from the request body (`.cdt` currently unsupported, see endpoint docs) |
| POST | `/api/tl_back` | Navigate the timelapse one step back |
| GET | `/api/beam[?crop=N]` | Current CTM beam position + crop rectangle |
| POST | `/api/raster_bp?x=N&y=N&enable=N` | Arm/disarm a raster breakpoint |
| POST | `/api/keytype` | Send text to the emulator (autotype) |
| POST | `/api/keypress` | Send a single CPC virtual key code |
| GET | `/api/keymap` | Current keyboard mapping as JSON (for UI display) |
| POST | `/api/keymap` | Apply a live keymap binding change |
| POST | `/api/basic[?reset=1][?run=1]` | Inject a Locomotive BASIC program into RAM |
| GET | `/api/basic_state` | BASIC interpreter state (pointers, current line/statement) |
| GET | `/api/basic_export[?verbose=1]` | Export (detokenize) the current BASIC program as source |
| GET | `/api/basic_listing` | Structured listing: lines + statements + RAM addresses + referenced vars |
| POST | `/api/basic_step[?mode=line]` | Step to the next BASIC statement (or line) |
| POST | `/api/basic_bp` | Set the BASIC line-breakpoint set (comma-separated line numbers) |
| POST | `/api/basic_runto?line=N` / `?addr=N` | Run to a BASIC line / statement, then pause |
| GET | `/api/scan_ptr` | Diagnostic: find RAM words pointing into the BASIC program |
| GET | `/console` | Interactive Lua console page (see below) |
| GET | `/api/script` | CSL/Lua scripting engine state + `print()` capture |
| POST | `/api/script[?lang=lua]` | Launch a CSL or Lua script (sandboxed) |
| DELETE | `/api/script` | Stop the current script |
| POST | `/api/eval` | Evaluate one Lua chunk on the persistent state; returns a `seq` |
| GET | `/api/eval?seq=N` | Outcome of eval `N` (value / output / error) |
| DELETE | `/api/eval` | Drop the persistent interactive state |

---

## Integration into the Main Loop

```cpp
WebServerOpts ws_opts;
ws_opts.p_emu_params = &emu_params;
ws_opts.p_emu_state  = &emu_state;
ws_opts.p_freeze     = &g_freeze;
ws_opts.p_fps        = &g_fps;
web_server_start(&ws_opts);

// --- main loop ---
while (!quit) {
    WebPending pending;
    if (web_server_poll(&ws_opts, pending)) {
        if (pending.set_pause)
            g_freeze = pending.pause_val;
        if (pending.do_soft_reset)
            Core_Soft_Reset();
        if (pending.do_hard_reset)
            Core_Hard_Reset();
        if (pending.cpc_model != 0xFF || pending.crtc_type != 0xFF) {
            // apply the new model / CRTC then reset
        }
        // Applied in FIFO order: several requests queued in the same tick must
        // all land, not coalesce onto a single overwritable slot.
        for (const WebRamWrite& w : pending.ram_writes) {
            uint8_t* ram = emu_state.Memory_RAM;
            for (size_t i = 0; i < w.data.size(); ++i)
                ram[w.addr + i] = w.data[i];
            if (w.exec)
                Core_z80_Write_Register(CORE_Z80_REGISTRE_PC, w.entry);
            ws_opts.ram_apply_seq.fetch_add(1, std::memory_order_relaxed);
        }
    }
    // Runs a queued POST /api/eval and publishes what GET /api/script and
    // GET /api/eval serve. Once per frame, outside the poll: unlike the
    // requests above, an eval has a result the web thread reads back later.
    web_eval_tick(ws_opts, g_csl_script, emu_params, emu_state, params, cbs);
    // ... emulation frame ...
}

web_server_stop();
```

---

## Known Limitations

- Only one simultaneous client (accept + handle + close are sequential).
- No keep-alive; each request opens a new TCP connection.
- Headers are capped at 64 KB; the body (used by `/api/media`) is read per the
  request's `Content-Length`, capped at 8 MB. No chunked transfer-encoding.
- No authentication: reserved for localhost only.
- State read (`/api/state`) without lock — data is consistent frame-by-frame.
