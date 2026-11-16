# AMSpiriT-Lite — Embedded HTTP Debug Server

> **Documented version: AMSpiriT Lite 1.17.8.** Use this version or a newer
> one — ideally exactly 1.17.8, so the doc matches the binary. If your build
> differs, treat the running instance as authoritative: query `GET /api/doc`
> (and `GET /api/doc/<name>`) for the endpoints it actually serves.

Files: `amspirit-helpers/inc/web_server.h`, `amspirit-helpers/src/web_server.cpp`

This file is the narrative companion to the machine-readable API contract
served by the API itself at `GET /api/doc` (list of endpoints) and
`GET /api/doc/<name>` (per-endpoint method/params/response shape, `<name>`
being the path under `/api/`, e.g. `/api/doc/config` for `/api/config`). The
source of truth is the **route record** — the table in
`amspirit-helpers/src/web_handle.cpp`, whose shape is declared in
`web_doc.h`. The router, `GET /api/doc` and the summary table below are
projections of it; this markdown keeps the behavioral nuance and gotchas
(SHIFT stickiness, `CPC_COUNTRY`, caveats, full curl examples) that don't
reduce to structured data.

Adding or changing an endpoint means editing the record, then this file's
section and summary row. **That is checked, not trusted**:
`scripts/check-api-contract.py` (run by `make test` as `api-contract`) fails
when the record describes a path this file has no section or summary row for,
when the summary table lists a path the record does not know, or when an
`@mcp.tool()` wrapper in `tools/mcp-emulator/server.py` calls an undocumented
endpoint or silently drops an enum value. Params a wrapper simply does not
expose are reported, not failed — a wrapper is allowed to be partial.

## Overview

Minimal HTTP server started automatically by `amspirit-lite-sdl` and the Qt
frontend (`amspirit-lite-qt`). All endpoints behave identically on both.  
Single-threaded, one request at a time, no keep-alive.  
Listens only on `127.0.0.1:6128` (loopback only, never exposed on the network).  
If the port is occupied, the server simply remains disabled — no fatal error.

---

## C++ Interface (public)

### Structures

#### `WebServerOpts`

Configuration parameter passed to `web_server_start`. Must remain alive
as long as the server is running.

| Field | Type | Default | Role |
|---|---|---|---|
| `port` | `uint16_t` | `6128` | TCP listen port |
| `bind_addr` | `std::string` | `"127.0.0.1"` | Bind address |
| `p_freeze` | `bool*` | `nullptr` | Pointer to the emulator's pause flag |
| `p_fps` | `double*` | `nullptr` | Pointer to the current FPS counter |
| `p_frame_compute_ms` | `double*` | `nullptr` | Pointer to per-frame compute time (ms) |
| `p_emu_params` | `CORE_PARAM_IN*` | `nullptr` | Emulator configuration parameters (read + pending config) |
| `p_emu_state` | `CORE_PARAM_OUT*` | `nullptr` | Core output buffers (RAM access) |
| `html_path` | `std::string` | `""` | Path to an external HTML file; empty = embedded UI |
| `p_rom_lang` | `std::string*` | `nullptr` | Pointer to current ROM language string (FR/EN/SP/DA) |
| `p_ui_lang` | `std::string*` | `nullptr` | Pointer to current UI language code (en/fr/es/de) |
| `plugins` / `plugin_dir` / `plugin_dirs` | `PluginHost*` / `std::string` / `std::vector<std::string>` | `nullptr` / `""` / empty | The frontend's plugin host, its user plugin directory and every directory plugins are taken from (empty = just `plugin_dir`) — source of `/api/plugins` |
| `mtx` | `std::mutex` | — | Internal lock shared between server thread and main thread |
| `pending` | `WebPending` | — | Pending command (do not access directly, use `web_server_poll`) |
| `script_status` | `WebScriptStatus` | — | Scripting engine state (running / last error / `print()` capture), published each frame by `web_eval_tick` |
| `eval` | `WebEvalState` | — | Interactive-eval request **and** result slot — the one request/response route; driven by `web_eval_tick` |
| `audio_ring` | `AudioRing*` | `nullptr` | Audio recording ring buffer (init with `web_audio_ring_init`) |
| `frames` | `std::atomic<uint64_t>` | `0` | Completed emulated video frames; the frontend must bump this once per frame — source of `emu.frames` |
| `autotype_remaining` | `std::atomic<int>` | `0` | Characters/VK presses left to deliver, updated by the frontend each frame — source of `emu.autotyping`/`emu.autotype_remaining` |
| `rw_active` / `rw_steps_back` / `rw_steps_fwd` / `rw_rewound` / `rw_step_kind` | `bool` / `int` / `int` / `bool` / `std::string` | `false` / `0` / `0` / `false` / `""` | Rewind state, written by the frontend each frame — source of the `rw_*` fields in `emu` (see `GET /api/state`) and consumed by `POST /api/rewind/back` |
| `rw_enabled` / `rw_interval` / `rw_slots` / `rw_mem_cap_mb` / `rw_mem_auto` | `bool` / `int` / `int` / `int` / `bool` | `false` / `10` / `100` / `128` / `false` | Rewind configuration, written by the frontend each frame — source of the `rw_*` fields of `GET /api/config` |
| `machine_sounds_live` | `MachineSoundsChange` | — | Machine sounds switches/volumes, written by the frontend each frame — source of the `machine_sounds_*` fields of `/api/config` |
| `render_monitor` / `render_crt` | `int` / `CrtParams` | `0` / — | Current CRT monitor preset and shader parameters, written by the frontend each frame — source of `GET /api/render` |
| `debug_api` | `bool` | `false` | Set at startup: log every incoming request, response status, and SSE event |
| `audio_devices` / `audio_current_device` | `std::vector<std::string>` / `std::string` | `{}` / `""` | Audio device list and current selection, populated by the frontend at startup — source of `GET /api/audio/devices` |
| `audio_volume_pct` | `int` | `100` | Live master volume, snapshotted by the frontend each frame — source of `volume` in `GET /api/config` |
| `cpc_volume_pct` | `int` | `100` | Live CPC mixer gain, snapshotted by the frontend each frame — source of `cpc_volume` in `GET /api/config` |

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
| `cpu_ops` | `std::vector<WebCpuOp>` | Queued RAM write/execute (`/api/ram`, `/api/exec`) and register (`/api/z80`) requests, applied in arrival order (see below) |
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
| `disk_create_cmd` | `uint64_t` | `cmd_seq` of that request, for `emu.failed_cmds` |
| `media_loads` | `std::vector<WebMediaLoad>` | `POST /api/media` uploads (`cmd`, `data`, `name`, `drive`, `crtc_keep`, `pause`, `cro_group`), applied in arrival order |
| `do_remap` | `bool` | Apply a live keymap binding change |
| `remap_host_cp` | `uint32_t` | Host character to remap |
| `remap_types_cp` | `uint32_t` | CPC character it should now produce |
| `remap_cmd` | `uint64_t` | `cmd_seq` of that request, for `emu.failed_cmds` |
| `set_mapping_keyboard` | `bool` | Apply a keyboard mapping mode change |
| `mapping_keyboard_val` | `bool` | New keyboard mapping mode value |
| `do_step` | `bool` | Execute exactly one Z80 instruction then re-pause |
| `do_basic_step` | `bool` | Run until the BASIC statement/line advances then re-pause |
| `basic_step_byline` | `bool` | `true` = step to next BASIC line; `false` = next statement |
| `step_over` | `bool` | With `do_step` / `do_basic_step`: step over a `CALL` / `GOSUB` |
| `clear_breakpoints` | `bool` | Drop every breakpoint (BASIC, Z80, raster, pending run-to / step-over) |
| `do_rw_back` / `rw_delta` / `rw_navigate` | `bool` / `int` / `bool` | Move the rewind: net steps (`<0` back, `>0` forward) and whether to navigate without dropping the future (requires an active rewind — see `POST /api/rewind/back`) |
| `set_breakpoints` | `bool` | Replace the BASIC line-breakpoint set |
| `breakpoints` | `std::vector<uint16_t>` | BASIC line numbers to break on |
| `set_z80_breakpoints` | `bool` | Replace the Z80 PC breakpoint set |
| `z80_breakpoints` | `std::vector<MemLoc>` | Resolved breakpoint locations: RAM bank, upper ROM, firmware ROM, or an as-yet-unresolved CPU address |
| `do_run_to` | `bool` | Resume until a one-shot target then pause |
| `run_to_line` | `uint16_t` | Run-to target BASIC line (`0xFFFF` = use `run_to_addr`) |
| `run_to_addr` | `uint16_t` | Run-to target statement address from `0xAE1B` |
| `clear_codemap` | `bool` | Reset the code map (every RAM bank and ROM) and the history |
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
| `do_set_cpc_volume` | `bool` | Set the CPC mixer gain (see `cpc_volume` in `POST /api/config`) |
| `new_cpc_volume_pct` | `int` | New CPC gain, 0–100 percent |
| `set_rewind` | `bool` | Reconfigure the rewind buffer (see `rw_*` in `POST /api/config`) |
| `rw_enabled` / `rw_interval` / `rw_slots` / `rw_mem_cap_mb` / `rw_mem_auto` | `int` | New rewind settings; `-1` = unchanged |
| `history_size` | `int` | New Z80 history depth; `-1` = unchanged |
| `machine_sounds` | `MachineSoundsChange` | New machine sounds switches/volumes; each field `-1` = unchanged |

#### `WebRamWrite`

| Field | Type | Role |
|---|---|---|
| `addr` | `uint16_t` | Destination address in CPC RAM |
| `data` | `std::vector<uint8_t>` | Bytes to write (empty = no write) |
| `exec` | `bool` | If `true`, redirect the PC to `entry` after the write |
| `entry` | `uint16_t` | Target PC when `exec == true` (default = `addr`) |
| `bank` | `int` | 16K bank (`B00`–`B103`); numbering in `GET /api/ram` |
| `cmd` | `uint64_t` | `cmd_seq` of the request that queued it, for `emu.failed_cmds` |

`POST /api/ram`, `POST /api/exec` and `POST /api/z80` share one queue,
applied in the order the requests arrived: several calls landing in the same
poll tick are all kept, and a `POST /api/z80` `{"PC":…}` followed by a
`POST /api/exec` ends on the exec's PC.

The response is `{"seq":N,"cmd_seq":M}` with `N == M`. **To wait for
the write, poll `emu.applied_cmd_seq >= cmd_seq`**, like every other command
(see *Commands: accepted now, applied later*). `seq` and `emu.ram_apply_seq`
are **deprecated** and will be removed: `seq` is a duplicate of `cmd_seq`,
`ram_apply_seq` a duplicate of `applied_cmd_seq`.

`applied_cmd_seq` also advances when the write is dropped at application (e.g.
the RAM size changed after the request was accepted): look for your `cmd_seq`
in `emu.failed_cmds`, or read the bytes back with `GET /api/ram`.

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

Base URL: `http://127.0.0.1:6128`

All responses include:
- `Access-Control-Allow-Origin: *`
- `Cache-Control: no-store`
- HTTP/1.0 protocol for regular requests, HTTP/1.1 for SSE connections

---

## Commands: accepted now, applied later

A request that changes the machine — pause/resume, step, breakpoints, RAM or
register writes, media, reset… — is a **command**: the server accepts it at
once but the emulation loop applies it on its next iteration, so a read made
right after the response still shows the old state.

Every command's response is `{"cmd_seq":N}` (no `ok`: queued is not done),
strictly increasing across all commands. `GET /api/ping` (and `GET /api/state`) report `emu.applied_cmd_seq`:
once it is `>= cmd_seq`, the command has been applied **and** the emulation has
run after it — a `POST /api/step` has executed its instruction. A command whose
effect spans frames (resume, BASIC step, run-to) is then *started*; watch
`emu.paused` or the SSE `pause`/`z80_bp` events for its end.

```bash
seq=$(curl -s -X POST http://127.0.0.1:6128/api/step | jq .cmd_seq)
until [ "$(curl -s http://127.0.0.1:6128/api/ping | jq .emu.applied_cmd_seq)" -ge "$seq" ]; do :; done
curl -s http://127.0.0.1:6128/api/z80   # the stepped state
```

**Which number to compare** — one rule: take the number a response is named
after.

| Response field | Compare with | Applies to |
|---|---|---|
| `cmd_seq` | `emu.applied_cmd_seq` (`/api/ping`, `/api/state`) | every command, including `POST /api/ram` and `/api/exec` — **use this one** |
| `seq` in a `POST /api/ram` / `/api/exec` response | `emu.ram_apply_seq` | **deprecated**: same values as `cmd_seq` / `emu.applied_cmd_seq` |
| `seq` in `POST /api/eval` | `GET /api/eval?seq=N` | a Lua eval's outcome, unrelated to the two above |

`cmd_seq` and the deprecated RAM `seq` are the same number; the eval `seq` is an
independent counter, never comparable with them.

**Did it work?** A few commands can still fail after being accepted — the
check needs the emulation thread: `POST /api/media` (a file the emulator
cannot load, or the core refuses), `POST /api/ram` / `/api/exec` (the RAM size
changed before the write applied), `POST /api/disk` `create`. Once
`emu.applied_cmd_seq >= cmd_seq`, look for your `cmd_seq` in `emu.failed_cmds`
(`[{"cmd_seq":12,"error":"…"}]`, the 16 most recent failures, oldest first):
absent means it worked; present, `error` says why and what to do instead.

**Waiting in the request: `?wait=<ms>`.** Added to any command's `POST`
(0–30000, default 0 = answer at once, so several commands can be sent back to
back without waiting), it holds the answer until the command is applied and
returns its outcome: `200 {"cmd_seq":N,"applied":true}`, `422 {"error":"…","cmd_seq":N}`
when it was refused at apply time (the `failed_cmds` entry), or
`408 {"error":"…","cmd_seq":N}` when still queued after the delay (the command
stays queued: it may apply later). An invalid `wait` is a `400`, nothing queued.
The WASM build ignores it (single thread: nothing could apply the command).

```bash
curl -s -X POST 'http://127.0.0.1:6128/api/media?name=game.dsk&wait=3000' --data-binary @game.dsk
```

## Parameter conventions

One rule per kind of parameter, the same on every endpoint:

- **Booleans** are `true`/`false` in a JSON body, and `true`, `false`, `1` or `0` in a query string. Anything else is a `400`.
- **Absent means not provided.** There is no "-1 = unused" value: leave the parameter out.
- **Names are `snake_case`** (`mask_type`, `rw_slots`); only Z80 register names (`PC`, `SP`, …) keep their case.
- **A closed vocabulary is named**, not numbered (`"6128+"`, `"CTM644"`, drive `A`/`B`); a `400` lists the accepted values.

Spellings older than these (`maskType`, `over=1`, `paused` in `/api/config`) are still accepted but no longer documented.

## Request bodies and errors

**A `200` means the request was accepted** (a command: queued, see above). An endpoint that cannot use
what it was sent answers `400` with an explanation instead — it never reports
success for a request it ignored:

```json
{ "error": "field \"frames\" must be between 1 and 100000", "field": "frames" }
```

`field` names the offending key (body field or query parameter) and is omitted for
whole-body problems. A `400` is returned when:

| Case | Example body | Response |
|---|---|---|
| Body is not a JSON object | `RUN`, `` (empty), `{"text":"RUN"` | `expected a JSON object` / `empty body: …` / `unterminated JSON object` |
| Required field missing | `{}` on `/api/keytype` | `missing field "text": the characters to type` |
| Field of the wrong type | `{"frames":"5"}`, `{"addr":null}` | `field "frames" must be an integer` |
| Value out of range | `{"volume":150}` | `field "volume" must be between 0 and 100 (percent)` |
| Value not in the accepted set | `{"rom_lang":"XX"}` | `field "rom_lang" must be one of FR, EN, SP, DA` |
| Nothing recognised / nothing to do | `{"cpc_modle":2}`, `{"addr":256}` on `/api/ram` | `no recognised field: …` / `nothing to do: …` |

**A method the path does not document answers `405 Method Not Allowed`**, never
`400` or `404`. The response carries an `Allow` header and the same list in the
body, both taken from the endpoint record — so a client never has to guess which
methods a path accepts:

```
$ curl -i -X PUT http://127.0.0.1:6128/api/ram
HTTP/1.1 405 Method Not Allowed
Allow: GET, POST

{"error":"method not allowed","allow":["GET","POST"]}
```

This was normalised: it used to be `400` on `/api/config`, `/api/codemap`,
`/api/keymap`, `/api/render`, `/api/lang`, `/api/script` and `/api/eval`, and
`404` everywhere else — including `/api/ram`, which documents two methods. See
`docs/adr/0003-methode-non-documentee-repond-405.md`.

`JSON.stringify({addr:NaN})` emits `{"addr":null}`, which is the wrong-type case —
worth knowing, because it used to be accepted with a `200` and no effect.

**Whitespace is not significant.** Bodies are read by a small scanner that skips
spaces, tabs, CR and LF on both sides of each colon, so compact
(`{"text":"RUN"}`) and pretty-printed (`{ "text" : "RUN" }`, indented multi-line)
bodies are equivalent.

**Keys are matched flatly, at any depth — this is deliberate, and clients rely on
it.** The scanner looks for `"key"` followed by a colon anywhere in the body, so
these two are equivalent:

```json
{ "curvature": 0.02, "scanline": 0.5 }
{ "crt": { "curvature": 0.02, "scanline": 0.5 } }
```

The debug UI sends the nested form for `POST /api/render`; `curl` examples here
use the flat one. The consequence to know: a key of the same name at *any* depth
wins, so an unrelated nested object carrying a documented key name will be read.
Bodies are small and endpoint-specific, so this has never bitten in practice —
but it means the wire format is "these keys, somewhere", not a schema. See
`docs/adr/0004-lecteur-json-plat-conserve.md` for why this was kept rather than
replaced with a nesting-aware parser.

---

### `GET /api/events` — Server-Sent Events

Persistent push stream. The server keeps the connection open and writes events as they occur. Regular request/response endpoints are unaffected and continue to work normally.

**Connect (JavaScript)**:
```js
const es = new EventSource('http://127.0.0.1:6128/api/events');

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
| `z80_bp` | Immediate on hit | PC + Z80 registers + `ticks` at the stop |
| `basic_bp` | Immediate on hit | BASIC line number + statement address |
| `pause` | On transition | `{"paused": true\|false}` |
| `reset` | On every hard/soft reset — key, menu, model or RAM change, script or API | `{"hard": true\|false}` |

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
  "sp": "0xBFF0", "ix": "0x0000", "iy": "0x0000",
  "ticks": 85400000
}
```

`ticks` is the tick counter at the stop (see `emu.ticks`): subtracting two
`z80_bp` events times the code between the two breakpoints in NOPs, without a
single HTTP round trip. To run to the next breakpoint, listen on
`?topics=z80_bp` and `POST /api/run {"action":"resume"}`; the event describes
the stop, and `GET /api/state` (which includes `beam`) completes it.

**`basic_bp` payload**:
```json
{ "line": 100, "addr": "0x4B20" }
```

**Heartbeat**: A comment line (`: ping`) is sent every 15 seconds on idle connections to keep the TCP connection alive through proxies and firewalls. `EventSource` ignores comment lines automatically.

**Limits**: Maximum 8 simultaneous SSE clients. The per-client event queue is bounded at 32 events; oldest events are dropped when the client is too slow to drain it.

**WASM target**: SSE is not available on the WebAssembly build (no BSD sockets). The endpoint does not exist there; continue using polling endpoints.

---

### `GET /api/doc`

Lists every documented endpoint: one row per path, the methods it accepts, and
the first operation's summary. Projection of the route record — nothing here is
written by hand. The response also carries a top-level `license` field pointing
at `GET /api/license` — see below; this is the reason it is a field on `/api/doc`
itself rather than only its own separate row, since a client that only ever
calls `/api/doc` still sees it.

```bash
curl -s http://127.0.0.1:6128/api/doc
# {"license":{"summary":"…","url":"/api/license"},"endpoints":[{"path":"/api/ping","methods":["GET"],"summary":"…"}, …]}
```

A row carrying `"prefix":true` (only `/api/doc/`) is a prefix: append a name to
it — see below.

### `GET /api/doc/<name>`

Full detail for one endpoint: every operation, its parameters (query or body,
type, required-or-default) and its response. `<name>` is the path segment
under `/api/` — `/api/doc/ram` describes `/api/ram`. The only prefix-matched
route on this API. Answers `404` for a name the record does not know.

A JSON response is described by **`fields`**, one entry per field: `name` is
its dotted path from the root (`emu.frames`; array elements appear as `name[]`,
e.g. `endpoints[].path`), plus `type`, a one-line `desc`, an `example` value
(JSON text) and `optional: true` when the field may be absent. Nested objects
are listed before their children. The list is exhaustive: the test suite checks
it against what the endpoints really return. The signals a chip publishes
beyond its base fields (`GET /api/ga`, `GET /api/crtc`, and the same objects in
`GET /api/state`) are listed as the loaded core reports them, at the time of
the request.

A non-JSON response (HTML page, SSE stream, PNG, plain text) has no `fields`,
but a one-line **`response`** saying what it carries.

```bash
curl -s http://127.0.0.1:6128/api/doc/ping
# {"path":"/api/ping","operations":[{"method":"GET","summary":"…","params":[],
#   "fields":[{"name":"ok","type":"bool","desc":"…","example":"true"},
#             {"name":"emu","type":"object","desc":"…"},
#             {"name":"emu.fps","type":"float","desc":"…","example":"50.0"}, …]}]}
```

### `GET /api/license`

AMSpiriT's license (CC BY-NC-ND 4.0) and an attribution request, addressed to
whoever — human or AI agent — is building something on top of this API. This is
not prompt injection: it is a plain, honest statement of the project's actual
license terms and a request to be credited, surfaced the same way every other
piece of this API's contract is (`GET /api/doc` lists it, this section
documents it). Nothing here asks a client to do anything beyond what the
license and a courtesy attribution already imply.

```bash
curl -s http://127.0.0.1:6128/api/license
# {"project":"AMSpiriT","license":"CC BY-NC-ND 4.0","license_url":"…",
#  "project_url":"…","notice_for_agents":"…","suggested_credit":"…"}
```

### `GET /api/ping`

Lightweight connectivity probe used by the web UI to detect whether the server is reachable.

**Response**: `200 application/json` — `{"ok":true,"emu":{...},"frontend":"lite","version":"1.15.4","core":2491682}` (`emu` is the same object as in `GET /api/state`; `frontend` identifies which client answered — other protocol-compatible emulators would report a different value here — `version` is that frontend's version, `core` the emulation core's build number)

**Pacing an automation client — read `emu.frames`, never `time.sleep()`**

`emu.frames` counts *completed emulated video frames* since startup (see `GET /api/state`). It is the emulated-time clock an automated client must pace itself on — `emu.ticks` is finer (one per NOP) but restarts from 0 on every hard reset, SNA load and rewind step, so it times code, it does not pace a session:

* **A reachable server does not mean a running machine.** The HTTP server answers before the emulation loop produces its first frame — a fraction of a second on the SDL2 frontend, but measured at **1.6 s on the Qt AppImage** (toolkit + OpenGL + FUSE startup). While `frames == 0` the Z80 has not executed a single cycle: `PC` is 0 and RAM still holds its post-reset fill, so a "screen is non-empty and stopped changing" boot heuristic is satisfied by a machine that has not booted at all. Wait for `frames > 0` first.
* **Wall clock ≠ emulated frames.** Typed input drains from the autotype queue at a few *emulated* frames per character (`POST /api/keytype`), and the frontends re-pace themselves against an absolute deadline after any stall, so `N × 20 ms` of sleeping is not `N` frames. Poll `emu.frames` until it has advanced by the budget you want instead — keystrokes sent early are silently swallowed by the booting firmware.

---

### `GET /` or `GET /index.html`

Returns the HTML/JS/CSS interface.  
If `WebServerOpts::html_path` points to a readable file, its content is served.  
Otherwise, the embedded UI in the binary is used.

**Response**: `200 text/html`

The scripts and stylesheets the page loads beside itself (`disasm.js`) are
served from the same directory as `html_path`: `GET /<name>` with a bare file
name ending in `.js` or `.css`. A name with a directory, `..`, a `%` escape or
another extension is never looked up on disk; it gets the API's `404`, like a
missing file.

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
    "IFF1": 1, "IFF2": 1, "IM": 1, "int_pending": false, "ticks": 85400000
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
    // + whatever signals the loaded core publishes (see below)
    "view": "live"
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
    "motor": false, "drive": "A", "spin_us": 0,
    "drives": [
      {"connected": true, "disk": true, "track": 0, "steps": 0, "step_us": 0, "dir": 0, "changes": 1},
      {"connected": false, "disk": false, "track": 0, "steps": 0, "step_us": 0, "dir": 0, "changes": 0}
    ]
  },
  "beam": {"x": 320, "y": 150, "cx": 32, "cy": 24, "cw": 768, "ch": 544},
  "emu": {
    "fps": 50.0,
    "frame_ms": 0.8,
    "frames": 4271,
    "ticks": 85400000,
    "paused": false,
    "cpc_model": "6128",
    "crtc_type": 0,
    "autotyping": false,
    "autotype_remaining": 0,
    "rw_active": false,
    "rw_steps_back": 0,
    "rw_steps_fwd": 0,
    "rw_step_kind": "frame",
    "rw_step_frames": 10,
    "rw_captures": 0,
    "rw_bytes_avg": 0,
    "rw_bytes_max": 0,
    "rw_bytes_total": 0,
    "rw_capture_us_avg": 0,
    "rw_capture_us_max": 0,
    "rw_capture_hist": [0, 0, 0, 0, 0, 0],
    "rw_restores": 0,
    "rw_restore_us_avg": 0,
    "rw_restore_us_max": 0,
    "rw_restore_hist": [0, 0, 0, 0, 0, 0],
    "ram_apply_seq": 0,
    "applied_cmd_seq": 0
  }
}
```

**Notable fields:**

| Object | Field | Description |
|---|---|---|
| `z80` | `PC`…`L2` | Z80 registers, unsigned integer values |
| `z80` | `IFF1/IFF2` | Interrupt flip-flops (0 or 1) |
| `z80` | `int_pending` | INT asserted and not yet acknowledged: stays `true` through a `di` and is taken at the next `ei` (an `ei:halt` then wakes at once) |
| `z80` | `IM` | Interrupt mode (0, 1 or 2) |
| `z80` | `ticks` | Same value as `emu.ticks` |
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
| `crtc` | *(more)* | Extra signals depend on the loaded core's published capabilities — never a fixed list, see `GET /api/crtc` below |
| `crtc` | `view` | `"z80"` or `"live"`: which CRTC values these are, see `GET /api/crtc` below |
| `fdc` | `msr` | Main Status Register of the PD765 |
| `fdc` | `sr0/sr1/sr2` | Status Registers 0/1/2 |
| `fdc` | `motor` | Drive motor state |
| `fdc` | `drive` | Active drive: `"A"` or `"B"` |
| `fdc` | `spin_us` | Motor inertia, shared by both drives: 0 (stopped) to 400000 (full speed); rises on spin-up, falls on spin-down |
| `fdc` | `drives[]` | Per-drive mechanical state, index 0 = A, 1 = B |
| `fdc.drives[]` | `connected` / `disk` | Drive present (B only when enabled) / disk inserted |
| `fdc.drives[]` | `track` | Physical head position |
| `fdc.drives[]` | `steps` | Cumulative head steps since start-up (never reset; diff two reads to count steps) |
| `fdc.drives[]` | `step_us` | Time between the last two steps, in µs (large = isolated step) |
| `fdc.drives[]` | `dir` | Direction of the last step: `1` inwards, `-1` towards track 0, `0` none yet |
| `fdc.drives[]` | `changes` | Cumulative disk changes: +1 per ejection and per insertion; replacing the disk in the drive increases it while `disk` stays true |
| `beam` | `x`…`ch` | Same object as `GET /api/beam` (default crop) |
| `emu` | `fps` | Current emulation speed |
| `emu` | `frame_ms` | Per-frame computation time in ms |
| `emu` | `frames` | Completed emulated frames since startup (0 = the emulation loop has not run yet; the clock an automation client must pace itself on — see `GET /api/ping`) |
| `emu` | `ticks` | NOPs (1 µs each) since the last hard reset, SNA load or rewind step — not reset by a soft reset. Subtract two readings to time code within one run |
| `emu` | `autotyping` | `true` while `POST /api/keytype` / `/api/keypress` still have characters or key presses to deliver |
| `emu` | `autotype_remaining` | How many are left (0 = idle). Counts bytes of the pending text plus queued VK presses |
| `emu` | `cpc_model` | CPC model name: `"464"`, `"664"`, `"6128"`, `"6128+"`, `"464+"`, `"GX4000"` (the same name `GET /api/config` returns and `POST /api/config` accepts) |
| `emu` | `crtc_type` | CRTC type (0–4) |
| `emu` | `rw_active` | `true` if the rewind is enabled and has at least one snapshot |
| `emu` | `rw_steps_back` / `rw_steps_fwd` | Steps available to navigate the rewind backward/forward (context-filtered to `rw_step_kind`) |
| `emu` | `rw_step_kind` | Current step-context kind: `"frame"`, `"basic"`, or `"z80"` |
| `emu` | `rw_step_frames` | Frames one step is worth: `rw_interval` for `"frame"` steps, `0` for `"z80"`/`"basic"` |
| `emu` | `rw_captures` | Rewind points captured since the rewind was last (re)configured |
| `emu` | `rw_bytes_avg` / `rw_bytes_max` | Mean / largest size of a captured point, in bytes |
| `emu` | `rw_bytes_total` | Memory held by the rewind history right now, in bytes |
| `emu` | `rw_capture_us_avg` / `rw_capture_us_max` | Mean / worst capture time of a point, in microseconds |
| `emu` | `rw_capture_hist` | Captures per duration band: <0.25 ms, <0.5 ms, <1 ms, <2 ms, <5 ms, ≥5 ms |
| `emu` | `rw_restores` | States reloaded (points and returns to live) |
| `emu` | `rw_restore_us_avg` / `rw_restore_us_max` | Mean / worst restore time, in microseconds |
| `emu` | `rw_restore_hist` | Restores per duration band, same bands as `rw_capture_hist` |
| `emu` | `applied_cmd_seq` | Highest `cmd_seq` applied, the emulation having run after it (see *Commands: accepted now, applied later*) |
| `emu` | `failed_cmds` | Commands accepted but refused when applied, `[{"cmd_seq","error"}]`, the 16 most recent, oldest first (see *Did it work?*) |
| `emu` | `ram_apply_seq` | **Deprecated**: same value as `applied_cmd_seq`, use that |

---

### `GET /api/crtc`

CRTC registers and selected counters: the **Lecture CRTC à l'arrêt**
(`GLOSSARY.md`).

- **Stopped at an instruction start** (Z80/BASIC/raster breakpoint, run-to,
  single step, pause at a frame end): the values **as the Z80 sees them**,
  `view = "z80"`. There the live CRTC lags 2 ticks behind the Z80; the loop
  computes the corrected read once per stop, on the emulation thread, and
  recomputes it after any command applied while stopped. The screen and the
  machine state are the same before and after.
- **Running, or stopped mid-instruction** (runaway-cap stop): the direct read,
  `view = "live"`.

Registers and published signals always come from the same view. In a public
core build the published signals are absent and only the registers benefit
from the Z80 view.

**Response**: `200 application/json`

```json
{
  "regs": [63,40,46,142,38,0,25,30,0,7,0,0,48,0],
  "selected_reg": 0,
  // + whatever signals the loaded core publishes (see below)
  "view": "z80"
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
| `view` | `"z80"` = as the Z80 sees them (stop at an instruction start); `"live"` = direct read |

> **Note:** Beyond `regs[]`/`selected_reg`, the response may carry additional
> internal counters/signals — this repo hardcodes none of their names or ids.
> The *loaded core* is the sole source of truth for that list (see "capacités
> du core" in `GLOSSARY.md`); query it live with `GET /api/doc/crtc`, which
> reflects exactly what the running core exposes. Same mechanism for
> `GET /api/ga` beyond its base fields.

Also included in `GET /api/state` under the `"crtc"` key.

---

### `GET /api/config`

Returns the current configuration of `CORE_PARAM_IN`.

**Response**: `200 application/json`

```json
{
  "cpc_model": "6128",
  "crtc_type": 0,
  "sound_output": 1,
  "freq_screen": 0,
  "extended_ram": 0,
  "ram_kb": 128,
  "rom_lang": "EN",
  "mapping_keyboard": false,
  "volume": 100,
  "cpc_volume": 100,
  "rw_enabled": false,
  "rw_interval": 10,
  "rw_slots": 100,
  "rw_mem_cap_mb": 128,
  "rw_mem_auto": false,
  "history_size": 20,
  "last_reinit": "ok"
}
```

`extended_ram` is the raw `CORE_PARAM_IN.EXTENDED_RAM` index, which names the
*banked* half only (kept for existing clients). `ram_kb` is the machine's
**total** RAM in Ko — the 64 Ko of central RAM included — and is the unit
`POST /api/config` accepts, so the two round-trip.

Only 64, 128, 192, 320 and 576 are ever reported. `extended_ram` 0 is the
model's built-in RAM: 64 Ko on a 464 / 664 / 464+ / GX4000, 128 Ko on a
6128 / 6128+, so a 6128 never reports 64. A GX4000 takes no memory expansion:
it always reports 64. The core delivers eight banks for
every `CORE_EXTENDED_RAM_*` value at or above 512 Ko, so larger indexes report
576.

`volume` is the live output volume (0–100). The frontend snapshots it every
frame, so it reflects changes made via hotkey (F7/F8), the mouse wheel, or this
endpoint. (SDL frontend; the Qt frontend has its own native volume widget.)

`cpc_volume` is the CPC mixer gain (0–100, default 100): the machine's own sound
(PSG, beeper), applied before the machine sounds are added and before the master
`volume`. Neither one changes what `/api/audio` records. Plugins play through their
own audio layer, outside both: their volume is the `p_volume` parameter of
`GET/POST /api/plugins`.

`rw_enabled` / `rw_interval` / `rw_slots` / `rw_mem_cap_mb` / `rw_mem_auto` are the rewind
configuration — whether the snapshot buffer is on, frames between snapshots,
buffer capacity, the memory ceiling of the history in MiB, and whether that ceiling is automatic — as set by the CLI, the config file, the Qt/imgui Rewind menu or `POST /api/config`.
`history_size` is the depth of the Z80 instruction history (`GET /api/history`).

`last_reinit` says whether the last `cpc_model` / `crtc_type` / `rom_lang` change
made through `POST /api/config` really loaded the machine's firmware — missing
ROM files are not a 400, since the `POST` only acks the queueing. Read it once
`GET /api/ping`'s `emu.applied_cmd_seq` has reached the `cmd_seq` the `POST` returned: `"ok"`; `"fell_back_to_6128"` (that model's ROMs
are missing, a 6128 runs instead); `"plus_firmware_missing"` (no OS cartridge
for that Plus/GX4000 in this ROM language); `"failed"` (no ROM at all — the
machine has no firmware; switch to a model whose ROMs exist); `"none"` before
any change. The emulator keeps running in every case.

**Machine sounds.** The object also carries
`machine_sounds_drive`, `machine_sounds_tape`, `machine_sounds_tape_signal`, `machine_sounds_keyboard`
(booleans, derived: on = volume > 0) and `machine_sounds_drive_volume`, `machine_sounds_tape_volume`,
`machine_sounds_keyboard_volume`, `machine_sounds_keyboard_user_volume` (0–100, 0 = off): the mechanical sounds of the drive, tape
and keyboard, mixed on top of the CPC audio.

---

### `POST /api/config`

Enqueues a configuration change. Pause, resume, reset and stepping are not settings: they live in `POST /api/run`.
Every field `GET /api/config` returns is settable here under the same name, except the read-only ones
(`sound_output`, `freq_screen`, `extended_ram`, `last_reinit`), so a GET body can be edited and sent back.  
The command is retrieved by `web_server_poll` at the next loop iteration
and applied by the main thread (including reset).

**Body**: `application/json` — all fields are optional.

```json
{
  "cpc_model":    "6128",
  "crtc_type":    0,
  "volume":       80
}
```

| Field | Type | Effect |
|---|---|---|
| `cpc_model` | string | Change the CPC model: `"464"`, `"664"`, `"6128"`, `"6128+"`, `"464+"` or `"GX4000"` (triggers an implicit reset on the application side). Without `crtc_type`, a Plus takes CRTC 3 and a classic keeps its CRTC unless it was 3 (then 1). A new model keeps an expansion above 128 Ko (192, 320, 576), but gets its built-in RAM (64 Ko, or 128 Ko on a 6128 / 6128+) for a 64 or 128 Ko machine, unless `ram_kb` comes in the same request |
| `crtc_type` | integer | Change the CRTC type (same), `0`–`4`. A Plus/GX4000 runs only `3`, a classic CPC anything but `3`; a pair the emulator cannot build — against the model in the request, else the one queued or running — is rejected (`400`) rather than rewritten |
| `ram_kb` | integer | **Total** RAM in Ko (central 64 Ko included): `64`, `128`, `192`, `320` or `576`. Any other value — including the banked sizes like `512` — is rejected (`400`, `field: ram_kb`) rather than clamped. `64` is rejected too on a 6128 / 6128+, which has 128 Ko built in, and anything but `64` on a GX4000, which takes no memory expansion (both against the model in the request, else the one queued or running). Resizing the RAM forces a **hard reset** |
| `rom_lang` | string | ROM language: `"FR"`, `"EN"`, `"SP"`, `"DA"` |
| `mapping_keyboard` | boolean | Enable/disable keyboard mapping mode |
| `volume` | integer | Set master volume 0–100: the CPC and the machine sounds, not the plugins (SDL frontend; Qt uses its native widget) |
| `cpc_volume` | integer | Set the CPC mixer gain 0–100: the machine's own sound (PSG, beeper) only, below the master. Plugin volumes go through `POST /api/plugins` (`set_param`, parameter `p_volume`) |
| `audio_device` | string | Switch the audio output device (`""` = system default). Device names come from `GET /api/audio/devices`. SDL frontend only |
| `rw_enabled` | boolean | Enable/disable the rewind buffer |
| `rw_interval` | integer | Frames between rewind snapshots, 1–500 (50 = 1 s). `1` = one snapshot per frame, the setting for debugging |
| `rw_slots` | integer | Rewind buffer capacity, 10–2000 snapshots. A point is the machine state (chips + RAM) plus the image of the visible screen zone, run-length encoded: ~0.15 MB on a 128 KB CPC, ~0.6 MB at 576 KB |
| `rw_mem_cap_mb` | integer | Memory ceiling of the rewind history, 8–4096 MiB (default 128, which holds the default 100 points even at 576 KB). Beyond it the oldest points are dropped, so fewer than `rw_slots` points may be reachable; the rewind window really reached is points × `rw_interval` ÷ 50 seconds of emulation. Persisted like the other rewind settings. In auto mode (`rw_mem_auto`) it reports the peak memory the history reached |
| `rw_mem_auto` | boolean | Automatic memory ceiling: nothing is dropped below 4096 MiB and `rw_mem_cap_mb` follows the peak reached; switching it off makes that peak the ceiling. Persisted |
| `history_size` | integer | Depth of the Z80 instruction history, 1–100000 (default 20). Resizing empties it and clears the rewind buffer. Not persisted |
| `machine_sounds_drive` / `machine_sounds_tape` / `machine_sounds_keyboard` | boolean | **Experimental.** Drive, tape and keyboard sounds on/off (keyboard = keys typed by the emulator: autotype, scripts). Alias of the volume: `false` sets it to 0, `true` restores the default only if it is 0; a volume in the same body wins |
| `machine_sounds_tape_signal` | boolean | **Experimental.** Also hear the tape data signal |
| `machine_sounds_drive_volume` / `machine_sounds_tape_volume` / `machine_sounds_keyboard_volume` | integer | **Experimental.** Volume of each source, 0–100; 0 = off. For the keyboard: keys typed by the emulator (autotype, scripts, API) |
| `machine_sounds_keyboard_user_volume` | integer | **Experimental.** Volume of the sounds of keys typed by the user, 0–100; 0 = off (default). The keyboard boolean is on when either keyboard volume is non-zero; `false` zeroes both, `true` restores only `machine_sounds_keyboard_volume` |

Any `rw_*` change reconfigures the rewind buffer, which **clears** its history
(same as the Qt/imgui Rewind settings dialog). Out-of-range values are rejected
(`400`, `field: rw_*`), not clamped.

The rewind history is also emptied, identically on every frontend, when a disk
is inserted or ejected (any drive) and when the machine is rebuilt: CPC model,
CRTC or ROM-language change, RAM resize. The configuration is kept; recording
restarts from the next point, so there is no stepping back before the change.

The `machine_sounds_*` fields are persisted like the settings menus.

**Success response**: `200 application/json` — `{"cmd_seq":N}`  
**Method error response**: `400 text/plain` — `Bad Request`

---

### `POST /api/quit`

Orderly application shutdown, available on every frontend that runs the web
server. The quit rides the frontend's **normal exit path**: disk autosave is
flushed to the host files (Qt/imgui prompt on a failed flush, SDL/headless log
it), and desktop frontends save their config (the headless frontend never
writes the shared config — by design). The request is queued and applied by
the main thread on its next frame, so the response is always
sent before the process exits.

**Response**: `200 application/json` — `{"cmd_seq":N}`

---

### `GET /api/ram?addr=<n>&len=<n>`

Reads a block of the 64 KB CPC RAM.

**Query parameters**:

| Parameter | Type | Default | Constraint |
|---|---|---|---|
| `addr` | integer (decimal or `0x` hex) | `0` | 0–65535 |
| `len` | integer | `256` | 1–65536 |
| `bank` | integer | `0` | 16K bank (`B00`–`B103`). `0–3` = the four 16K slices of the base 64K (`3` = `#C000`, the default screen), `4–7` = first extension block, `8+` = further blocks; installed banks = `ram_kb`/16 (128 Ko = `0–7`, 576 Ko = `0–35`). An `addr` above `0x3FFF` carries into the next bank, so `bank=0&addr=0xC000` is `bank=3&addr=0` and `bank=4&addr=0&len=65536` reads a whole 64 Ko block. A read continues into the following banks of the same 64K block (`4N..4N+3`) and stops at its end |
| `view` | `raw`\|`cpu`\|`fw` | `raw` | `raw` = the bank itself; `cpu` = return memory **as the Z80 sees it** (lower/upper ROM overlays and RAM banking applied); `fw` = firmware/ROM view — a flat 32 Ko image (lower ROM + the currently active upper ROM), independent of `addr`'s RAM banking |

> **Strict validation.** `addr`, `len`, `bank` and `view` are type- and
> range-checked: a non-numeric or out-of-range value is rejected with `400`
> and a `{"error":...,"field":...}` body. There is no combined `Bnn:hhhh`
> string form on this endpoint — use `bank=` and `addr=` (which itself carries
> past `0x3FFF` into `bank`, so the two forms are equivalent). `Bnn:hhhh` is
> the notation used by `POST /api/z80_bp` instead, whose body is a **list** of
> addresses rather than one range, so each entry needs to name its own kind.
> A `bank` past the installed RAM (`GET /api/config` `ram_kb`: 128 Ko = `B00`–`B07`)
> is refused with `400` (`field: bank`), the same rule as `POST /api/ram`.

**Response**: `200 application/json`

```json
{
  "addr": 0,
  "len": 16,
  "hex": "c9000000000000000000000000000000"
}
```

`hex` is a lowercase ASCII hexadecimal string, `len × 2` characters long. `addr`
echoes the address **as requested**, not the index the read landed on inside the
bank64 — so a client can re-send the `bank`/`addr` pair it got back and read the
same bytes.

> **⚠ `bank` changed unit without changing name.** It used to count 64 Ko
> *bank64s*; it now counts 16 Ko **banks**, the CPC's own unit — so a caller
> written before this change means `bank=4*N` where it says `bank=N`. Nothing can
> detect it: `bank=1` is valid under both readings. See
> [GLOSSARY.md](../../GLOSSARY.md) for *bank* vs *bank64*.
>
> `bank=4+` reflects the same RAM the Z80 reads and writes once that bank is
> paged in — consistent with `view=cpu`, which shows the currently mapped
> bank at a given CPU address.
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
| `addr` | integer (decimal or `0x` hex string) | Destination address (0–65535) |
| `data` | hex string | Bytes to write (spaces and `:` are tolerated, ignored) |
| `exec` | boolean | If `true`, the Z80 jumps to `entry` after the write |
| `entry` | integer | Target PC (default = `addr`) |
| `bank` | integer | 16K bank to write into, same numbering and validation as `GET /api/ram`'s `bank` (128 Ko = `0–7`, extension `4–7`); `addr` carries into the next bank, and `data` must stay inside one 64K block (`4N..4N+3`), else `400` `field: data` |

`data` empty + `exec: true` = simple PC redirection without write.

> **Writes are always physical.** There is no `view` field: `bank` + `addr`
> address the RAM banks themselves, like `GET /api/ram`'s default `view=raw`,
> never the Z80's mapped view (ROM overlays, current banking). To read back
> what a write produced, use `GET /api/ram` with the same `bank`/`addr` and
> the default `raw` view.

A write that could not land in full is refused with `400` and nothing is
queued (no exec either):

| `field` | Cause | Recovery |
|---|---|---|
| `addr` | `bank` + `addr` carries past the last bank (`B103`) | lower `addr` or `bank` |
| `data` | the bytes run past the end of their 64K block (banks `4N`–`4N+3`) | split the write at the block boundary |
| `bank` | the bank is not installed at the current RAM size | `POST /api/config` `ram_kb`, wait for its `cmd_seq` in `GET /api/ping` `emu.applied_cmd_seq`, then write |

Like loading a binary through `POST /api/media`, `exec` pages out the lower
ROM (target below `0x4000`) or the active upper ROM (target at `0xC000` and
above) before the jump, so injected code runs instead of the ROM. While the
lower ROM is out, the interrupt vector at `0x38` reads RAM: run with
interrupts disabled or install your own handler.

Queued rather than applied in place: several calls landing in the same poll
tick are all kept and applied in arrival order, together with `POST /api/exec`
and `POST /api/z80` (see `WebRamWrite` above).

**Response**: `200 application/json` — `{"seq":N,"cmd_seq":M}`. Wait
for `GET /api/ping` `emu.applied_cmd_seq >= M` before reading RAM back. `N`
(deprecated) equals `M`.

---

### `POST /api/exec`

Redirects the Z80 PC without RAM write.  
Shortcut equivalent to `POST /api/ram` with empty `data` and `exec: true`,
including the ROM paging described there.

**Body**:

```json
{"addr": 4096}
```

**Response**: `200 application/json` — `{"seq":N,"cmd_seq":M}` (same two counters as `POST /api/ram` above: wait on `cmd_seq`)

---

### `POST /api/keytype`

Sends a text string to the emulator as if it had been typed on the keyboard.
Successive calls accumulate in one queue, so text posted while a previous string
is still being typed is appended, never dropped.

**Body**: `application/json`

```json
{"text": "RUN\r"}
```

`\r`, `\n` or `\r\n` each type one RETURN (Enter). Typing — like a
`POST /api/keypress` frappe and the `frames` budget of a key or joystick
hold — advances only while the machine runs: sent during a pause, it waits for
the resume. Typing is done when `GET /api/ping`'s `emu.autotyping` is `false`.

```bash
curl -X POST http://127.0.0.1:6128/api/keytype \
     -H 'Content-Type: application/json' \
     -d '{"text":"RUN\r"}'
```

**Response**: `200 application/json` — `{"cmd_seq":N}`

**Pacing** — *not* one character per frame (that claim was wrong):

| Character | Emulated frames | Why |
|---|---|---|
| plain | `autotype_speed` (default **4**) | press on frame 1, release at `speed / 2` |
| needs CPC SHIFT (uppercase, `"`, …) | `speed / 2 + 3` | the core's ~20 ms SHIFT anti-parasite has to drain |
| same character as the next one | **9** | its own longer press + guard frames, and CPC SHIFT held across the run — the core applies a release up to ~4 frames late and drops a press landing in that window, so `"HELLO"` used to arrive as `"HELO"` |

So `RUN"DIAG"` is ~45 frames (~0.9 s), not 9. Do not derive a frame budget from the
string length: poll instead.

**Disk accesses** — between two keystrokes, typing waits while the drive motor runs
or the FDC executes a command, and resumes once the access is over (AMSDOS keeps the
motor on ~2 s after it); a key already down is released on time, never held through
the access (the firmware would auto-repeat it). The wait is capped at 5 s, so a
program that leaves the motor on only slows typing down. Otherwise characters were lost: sector transfers run with interrupts off, so
the firmware does not scan the keyboard, and the program doing the access (`CAT`,
`LOAD`…) reads no input, so type-ahead overflowed the firmware's key buffer. Text
posted as `"CAT\rPRINT 1\r"` therefore types `PRINT 1` after the catalogue.

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
| `reset` | boolean | `false` | Hard reset before injection |
| `run` | boolean | `false` | Auto-type `RUN` after injection |

Expected format: one statement per line, line number required.
A listing without any numbered line is refused with `400` before anything
is queued (no reset either): it would replace the program in RAM with an
empty one. Type direct commands (`PRINT 1`, `CLS`) with `POST /api/keytype`.

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
curl -X POST http://127.0.0.1:6128/api/basic \
     -H 'Content-Type: text/plain' \
     --data-binary '10 MODE 1
20 BORDER 0
30 INK 0,0:INK 1,26
40 PRINT "HELLO FROM AMSPIRIT"
50 GOTO 40'
```

```bash
# From a .bas file
curl -X POST http://127.0.0.1:6128/api/basic \
     -H 'Content-Type: text/plain' \
     --data-binary @myprog.bas
```

```bash
# Inject and launch automatically
curl -X POST http://127.0.0.1:6128/api/basic?run=true \
     -H 'Content-Type: text/plain' \
     --data-binary '10 PRINT "LOOP":GOTO 10'
```

The window title bar confirms the injection:
- success: `BASIC injected — type LIST or RUN`
- failure (program too large): `BASIC inject failed: program too large`

**Response**: `200 application/json` — `{"cmd_seq":N}`

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
| `verbose` | boolean | `false` | Include extra whitespace for readability |

**Response**: `200 text/plain; charset=utf-8` — Locomotive BASIC source

```bash
curl http://127.0.0.1:6128/api/basic_export > exported.bas
curl http://127.0.0.1:6128/api/basic_export?verbose=true > exported_readable.bas
```

If no BASIC program is loaded or RAM is unavailable, returns an empty response.

---

### `POST /api/keypress`

Presses, holds or releases a single CPC key, named by its legend on the keyboard of the ROM language.

**Body**: `application/json`

```json
{"cpc_key": "SPACE"}
{"cpc_key": "Q", "down": true}
{"cpc_key": "Q", "down": true, "frames": 50}
{"cpc_key": "Q", "down": false}
```

| Field | Type | Role |
|---|---|---|
| `cpc_key` | string | CPC key name, case-insensitive: `A`–`Z`, `0`–`9` (no effect on their own, see below), `F0`–`F9` (numeric keypad), `SPACE`, `ENTER`, `TAB`, `ESC`, `DEL`, `CLR`, `COPY`, `SHIFT`, `CTRL`, `CAPS_LOCK`, `LEFT`, `RIGHT`, `UP`, `DOWN`, `F_DOT` and the punctuation keys `- ^ @ [ ] : ; , . / \` |
| `down` | boolean | Absent: one-shot press (a *frappe*). `true`: hold the key. `false`: release it |
| `frames` | integer | Only with `down:true`, 1–100000: release by itself after this many emulated frames |

A name is the legend of a key on the CPC keyboard **of the ROM language**: `"Q"` is the key that types `q`. Which matrix position that key lights depends on the language (on an FR ROM, `A`/`Q`, `W`/`Z` and `M` sit where an EN keyboard has other keys, as on an AZERTY CPC), so the same name works whichever ROM is loaded, but never read a name off the matrix of `GET /api/keymatrix` with a fixed table. A capital or shifted glyph is the key with `SHIFT` held (hold `{"cpc_key":"SHIFT","down":true}` first).

**Known limitation: the digit keys `0`–`9` press nothing on their own**, on FR and EN ROMs alike (with `SHIFT` held the key appears in the matrix, which types the symbol, not the digit). Type digits with `POST /api/keytype`. The other names behave as described. An unknown name answers 400 with the list of valid ones.

This is an alternative to `/api/keytype` for keys that have no text form (arrows, `COPY`, function keys, `CTRL`…) and for holding or releasing a key.

Presses are queued and delivered *after* any pending `/api/keytype` text (see that
endpoint's **Ordering** note), and count towards `emu.autotype_remaining`.

**Holding a key.** A plain press lasts about one emulated frame, too short to be
seen by a client polling `GET /api/keymatrix` on the wall clock, and too short for a
game that samples its input every few frames. With `down:true` the key stays down
until `down:false`, until the `frames` budget runs out, or until a hard or soft reset.
Several keys can be held at once, one call each. Releasing a key that is not held
succeeds and does nothing. A hold does not wait behind `/api/keytype` text.

The `frames` budget belongs to the hold, not to the key: releasing the key cancels it, and holding the key again replaces it, so an earlier budget never cuts a later hold short.

A key stays down as long as *any* source holds it: if the host keyboard also holds
the same key, releasing the hold does not let go of it, and the reverse.

Limits: a hold does not synthesise SHIFT — hold `SHIFT` alongside the key. A one-shot press of a key that is currently held releases
it; do not mix the two on the same key. A held key is an ordinary key of the CPC
matrix, so it takes part in the keyboard clash like a physical one: pressing other
keys of the same column can make the CPC see ghost or missing keys. Changing the
focus of the Qt window can drop a held key for a few frames before it comes back.
A script that writes the matrix itself (Lua `keyboard_write`) bypasses the hold and
can let go of a held key without the API noticing.

`frames` without `down:true` (absent or `false`), or outside 1–100000, is a `400`.

**Response**: `200 application/json` — `{"cmd_seq":N}`

---

### `POST /api/joystick`

Holds a joystick state (directions and fire buttons) on port 0, like a gamepad
would, until it is released.

**Body**: `application/json`

```json
{"up": true, "fire1": true}
{"right": true, "frames": 50}
{"release": true}
```

| Field | Type | Role |
|---|---|---|
| `up`, `down`, `left`, `right` | boolean | Directions, default `false` |
| `fire1`, `fire2`, `fire3` | boolean | Fire buttons (SPACE, CONTROL, ALT), default `false` |
| `frames` | integer | 1–100000: let go by itself after this many emulated frames. Absent: until released |
| `release` | boolean | `true` lets go of everything the API holds; cannot be combined with a state or `frames` |
| `port` | integer | Only `0` exists; any other value is a `400` |

Each call states the **whole** joystick wanted, not a change: a direction left out is
released. The state is merged with a real gamepad by OR, so neither source cancels
the other. A hard or soft reset releases it. The `frames` budget belongs to the state
currently held: `release` cancels it and a new call replaces it, so an earlier budget
never cuts a later state short.

When no joystick is connected, the first call connects a digital one, as plugging a
gamepad would. A joystick already chosen (analogue, mapped) is left as it is.

The state is digital. If the user picked an analogue or mapped joystick, the core
ignores it and the call still answers `200`; the choice made in the frontend wins.

The joystick does **not** appear in `GET /api/keymatrix`: to check it, read it from
a CPC program (`JOY(0)`: bit 0 up, 1 down, 2 left, 3 right, `0x10` fire 1, `0x20`
fire 2, `0x40` fire 3). Plugging in or switching off a real gamepad while the API
holds a state can cut the joystick until the next call.

**Response**: `200 application/json` — `{"cmd_seq":N}`

---

### `GET /api/keymap`

Returns the current keyboard mapping as JSON: `keys[]` (one entry per host
character, with the CPC character it types: `{"host_key":"a","types":"a"}`, plus
`shift`/`ctrl` when the CPC has to hold that modifier) and `hotkeys[]` (the
emulator's own shortcuts, `host_key` being the name the frontend's toolkit gives
the key, `"F6"`). The table follows the ROM language: on an FR ROM the digit row
is typed with SHIFT, as on a real AZERTY CPC. An entry set by hand in
`keymap.cfg` to a key no CPC character maps to carries `"custom":true` instead of
`types`. The exact field list is `GET /api/doc/keymap`.

Every `types` this returns is accepted by `POST /api/keymap`.

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
curl http://127.0.0.1:6128/api/script
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
curl -X POST 'http://127.0.0.1:6128/api/script' \
     -H 'Content-Type: text/plain' \
     --data-binary @myscript.csl

# Lua script
curl -X POST 'http://127.0.0.1:6128/api/script?lang=lua' \
     -H 'Content-Type: text/plain' \
     --data-binary @myscript.lua
```

**Response**: `200 application/json` — `{"cmd_seq":N}`

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
targets `http://127.0.0.1:6128` absolutely, like the other standalone pages in
`src/assets/`.

---

### `POST /api/eval`

Evaluates **one Lua chunk** on the *persistent* interactive state: globals set
by one eval are still there for the next. This is the console endpoint.

Unlike every other POST on this API, an eval has an **answer**, so this route is
request/response: the POST issues a `seq`, and `GET /api/eval?seq=N` reads the
outcome back. Same contract as `cmd_seq` / `applied_cmd_seq` — acking the
queueing is not acking the result.

The body is the chunk, taken verbatim: **no CSL preprocessing on this route**
(CSL is a file format). A bare expression works — the chunk is tried as
`return <body>` first, like the stock `lua` REPL — so its value comes back in
`value`.

Sandboxed exactly like `POST /api/script`.

```bash
curl -X POST http://127.0.0.1:6128/api/eval --data-binary 'cpc.getZ80().PC'
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
curl 'http://127.0.0.1:6128/api/eval?seq=1'
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
curl -X DELETE http://127.0.0.1:6128/api/eval
```

**Response**: `200 application/json` — `{"ok":true}`

---

### `DELETE /api/script`

Interrupts the currently running script.

```bash
curl -X DELETE http://127.0.0.1:6128/api/script
```

**Response**: `200 application/json` — `{"cmd_seq":N}`

---

## CPU Debugging Endpoints

These power the **CPU** tab (disassembler, single-step, executed-code map,
instruction history). Stepping requires the emulator to be paused.

### `POST /api/run`

Execution control in one place: pause, resume, reset, step. Queued like every command.

**Body**: `application/json`

| Field | Type | Effect |
|---|---|---|
| `action` | `pause`, `resume`, `reset`, `step` | Required. `pause`/`resume` act like the Pause key and never clear breakpoints; an SSE `pause` event is emitted only when the state changes |
| `kind` | `soft` (default), `hard` | `reset` only. Applied after any `cpc_model`/`crtc_type`/`rom_lang`/`ram_kb` change of the same `POST /api/config` (each of those resets the machine itself), before any RAM write or exec |
| `target` | `z80` (default), `basic` | `step` only: one Z80 instruction, or one BASIC statement |
| `over` | boolean | `step` only: step over a `CALL` (`z80`) or a `GOSUB` (`basic`) |
| `unit` | `statement` (default), `line` | `step` with `target` `basic` only: stop at the next statement or the next line |

A parameter that does not belong with the `action` is a `400` naming it. Steps follow the rules of
`POST /api/step` and `POST /api/basic_step` below, which remain as aliases.

```bash
curl -X POST http://127.0.0.1:6128/api/run -d '{"action":"pause"}'
curl -X POST http://127.0.0.1:6128/api/run -d '{"action":"step","over":true}'
curl -X POST http://127.0.0.1:6128/api/run -d '{"action":"step","target":"basic","unit":"line"}'
curl -X POST http://127.0.0.1:6128/api/run -d '{"action":"reset","kind":"hard"}'
```

**Response**: `200 application/json` — `{"cmd_seq":N}`

---

### `POST /api/step[?over=true]`

Executes **exactly one Z80 instruction** then re-pauses. The emulator is
briefly resumed and stopped again once the PC has advanced past the current
instruction (so it works even though the CPU is already sitting on an
instruction boundary while paused). Pause first, wait for that command's
`cmd_seq`, then step; the new registers are in `GET /api/state` once the
step's `cmd_seq` is applied.

`?over=true` steps **over** a `CALL nn` / `CALL cc,nn`: the subroutine runs and
the CPU pauses on the instruction after the `CALL` (a breakpoint inside the
subroutine, or any other stop, ends the step-over there). On any other
instruction it is a plain step. `over` other than `true`, `false`, `1` or `0` → `400`.

**Response**: `200 application/json` — `{"cmd_seq":N}`

---

### `GET /api/history`

Returns the last executed Z80 instructions (oldest first), with the registers
as they were just before each one.

The history holds **20** instructions by default. To trace further back — for
instance to find how the program reached a crash — raise the depth with
`POST /api/config` `{"history_size":N}` (1–100000, ~24 bytes per entry), let the
program run to the point of interest, pause, then read it. Resizing empties the
history (and clears the rewind buffer). The current depth is `history_size` in
`GET /api/config`.

**Query parameters**:

| Parameter | Default | Description |
|---|---|---|
| `n` | all | Return only the `n` most recent entries (1–100000) |

**Response**: `200 application/json`

```json
[
  {"pc":47426,"hex":"3E0100BB","current_hex":"3E0100BB"},
  {"pc":47428,"hex":"CD00BB00","current_hex":"CD00BB00"}
]
```

| Field | Description |
|---|---|
| `pc` | Address of the instruction |
| `hex` | Up to 4 opcode bytes **as they were fetched when this instruction ran** — captured at execution time, immutable afterwards |
| `current_hex` | The same 4 bytes, **read now** from the CPU-visible mapping (ROM/RAM overlay applied). Differs from `hex` exactly when the code has since been self-modified, or when the bank paged into that window has changed |

---

### `GET /api/codemap` · `DELETE /api/codemap`

The **carte de code**: every byte at which an instruction has **started
executing** since the last reset, kept per physical memory (each RAM bank, the
firmware ROM, each upper ROM). A mark made while a ROM was paged stays on that
ROM: it never shows on the RAM paged at the same CPU address later, and a bank
switched in at `#4000` does not inherit the marks of the previous one. Used to
colour "code" vs "data" zones in the disassembler.

Without parameters, `GET` returns the CPU view through the live mapping: a
65536-bit bitmap (8192 bytes, hex), bit `addr` set when an instruction began at
the byte now visible at `addr`. Byte `i` covers addresses `8i..8i+7`, bit 0 =
`8i`.

```json
{"hex":"0000....ffff"}
```

**Query parameters** (all optional; any of them switches to the full answer
below):

| Parameter | Effect |
|---|---|
| `view` | `cpu` (default) = the Z80's mapping; `fw` = firmware ROM + selected upper ROM, 32K |
| `bank` | 16K bank (`Bnn:` numbering): this bank and the next ones up to the end of its 64K block, like `GET /api/ram`. A bank the current RAM size does not have → `400` field `bank` |
| `ram` | `1`/`true` adds the bytes of the view |
| `map` | CPU view only: read it through this mapping CPU instead of the live one — four slot names `FW` (firmware ROM), `Rnn` (upper ROM) or `Bnn` (bank), hex, comma-separated: `FW,B01,B02,R00`. Malformed, naming a bank not installed, or combined with `bank`/`view=fw` → `400` field `map` |

```json
{"view":"cpu","map":"FW,B01,B02,R00","hex":"0000....","ram":"3e01...."}
```

| Field | Meaning |
|---|---|
| `view` | `cpu`, `fw` or `bank` |
| `map` | The 16K spaces shown, in address order (`FW,R07` for `view=fw`, `B04,B05,B06,B07` for `bank=4`) |
| `hex` | Their marks, 2048 bytes per space |
| `ram` | Their bytes (only with `ram`). An upper ROM other than the selected one reads as zeros until it has run code once |

`hex`, `ram` and `map` are read together between two frames (the emulation loop
holds a lock while a frame runs), so they always describe the same instant. A
debugger that keeps `map` fixed while the machine runs sees a listing that does
not jump each time the firmware pages a ROM in or out.

`DELETE` clears the marks of every memory (RAM banks and ROMs) and the
instruction history.

**Response**: `200 application/json` — `{"cmd_seq":N}` for `DELETE`.

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
| `crop` | `true` | `true` = visible screen area only, `false` = full physical buffer (1024×350, sync borders included) |
| `live` | `true` while paused, else `false` | `true` = in-progress buffer (the frame being drawn), `false` = last settled frame |
| `full` | `true` | `true` = plain complete frame, `false` = composite (in-progress frame over the previous one, for debugging a partial screen) |

`live` is forced to `0` while the rewind is rewound: the core does not snapshot
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
curl -s 'http://127.0.0.1:6128/api/screenshot?crop=true&full=true&live=false' -o screen.png
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
| `regions[].ram_bank` | Physical 16 Ko **bank** (0–3 = base 64K, 4+ = extension) — only when `!rom`. The numbering has always been per 16 Ko, so it matches `Bnn:` |
| `regions[].ext` | `true` if this bank comes from extended RAM |
| `rmr` | Gate Array RMR register value |
| `ram_mode` | RAM banking configuration (the `&7Fxx` value, 0–7) |
| `ram_page` | bank64 selected by the RAM configuration (0–3) |

---

### `DELETE /api/cartridge`

Eject the cartridge: its banks leave `GET /api/rommap` and the machine hard-resets. The CPC model is left as is (a `.cpr` had switched it to 6128+: `POST /api/config` `cpc_model` to go back).

```bash
curl -X DELETE http://127.0.0.1:6128/api/cartridge
```

**Response**: `200 application/json` — `{"cmd_seq":N}`

---

### `GET /api/rommap`

Returns the ROM catalog (`rom_registry`): which firmware, extension
(`R<n>:`) and cartridge-bank ROMs are currently loaded, and from which
source file. Distinct from `GET /api/memmap`, which describes the live CPU
memory mapping — `/api/rommap` is bookkeeping of load/unload events, not a
snapshot of what's paged in right now.

**Response**: `200 application/json`

```json
{
  "fw": {"loaded": true, "os_source": "os_6128.rom", "basic_source": "basic_6128.rom"},
  "ext_rom": [{"number": 7, "loaded": true, "source": "amsdos.rom"}],
  "cartridge_bank": [{"number": 0, "loaded": true, "source": "game.cpr"}],
  "cro": null
}
```

| Field | Description |
|---|---|
| `fw.loaded` | `true` once a firmware ROM pair (OS + BASIC) has been loaded |
| `fw.os_source` | Source file the lower (OS) ROM was loaded from, or `null` when unloaded |
| `fw.basic_source` | Source file the upper (BASIC) ROM was loaded from, or `null` when unloaded. A CRO container that packs both halves into one file reports the same value as `fw.os_source` |
| `ext_rom[].number` | Extension ROM number (`R<n>:`), e.g. 7 = AMSDOS |
| `ext_rom[].source` | Source file (a `.rom` for a single extension ROM, or the `.cro` container it came from) |
| `cartridge_bank[].number` | CPC+ cartridge bank number (0-31) actually populated by the loaded CPR or CRO |
| `cartridge_bank[].source` | `.cpr` or `.cro` file it was loaded from |
| `cro` | The CRO media in the machine, or `null` when the media is not a CRO. A system CRO (`CPC_*.cro`, `GX4000.cro`) never appears here |
| `cro.source` | The CRO file, or the upload's `name` |
| `cro.group` | The loaded group, `{"gnum": n, "label": "…"}`: only its ROMs are in the lists above |
| `cro.groups[]` | Every group of the file, in file order: `gnum`, `label`, `rom_count`, `bankable` (same objects as the `POST /api/media` refusal). Load another with `POST /api/media` `cro_group` |

`ext_rom` and `cartridge_bank` are sparse lists: only currently-loaded
numbers appear. Reloading the same number overwrites its entry. Loading a
`CORE_CARTRIDGE_SYSTEM` CPR (the OS cartridge) also unloads `fw` and
`R7:` — the core replaces both internally, so the catalog reflects that
rather than claiming a ROM the core has just erased is still loaded. A
`CORE_CARTRIDGE_STD` CPR touches neither.

A CRO with cartridge banks replaces every previous bank; on a Plus it also
drops the extension ROMs it does not redefine, and `fw` when it provides
bank 0. A CRO without banks only adds entries. Only the loaded group of a
CRO is in the machine, so only its ROMs appear.

---

## Render / CRT Endpoints

Drive the **Render** tab and mirror the Qt CRT-settings dialog.

### `GET /api/render`

Returns the current CRT monitor preset, screen type and shader parameters.

**Response**: `200 application/json`

```json
{
  "monitor": "CTM644",
  "screen_type": 0,
  "monitor_cal": "auto",
  "presets": ["Off","CTM644","GT65","TV"],
  "crt": {
    "curvature": 0.005, "scanline": 0.30, "sharpness": 0.80,
    "mask_type": 4, "mask_pitch": 3.0, "mask": 0.15,
    "halation": 0.12, "diffusion": 0.10, "convergence": 0.0,
    "brightness": 1.0, "persistence": 0.0
  }
}
```

| Field | Description |
|---|---|
| `monitor` | Current monitor preset: `"Off"`, `"CTM644"`, `"GT65"` or `"TV"` |
| `screen_type` | Screen type: 0 = colour, 1 = green, 2 = colour (ASIC), 3 = green (ASIC) |
| `monitor_cal` | Monitor calibration: `"auto"`, `"ctm"` or `"cm14"` (see `POST /api/render`) |
| `presets` | The accepted `monitor` values |
| `crt` | CRT shader parameters (see `POST /api/render`) |

### `POST /api/render`

Changes the monitor preset, screen type and/or CRT shader parameters. Any
subset of the keys may be sent. `crt` is applied as a whole set when present.

**Body**: `application/json`

```json
{ "monitor": "GT65" }
{ "screen_type": 1 }
{ "monitor_cal": "cm14" }
{ "crt": { "curvature":0.005, "scanline":0.30, "sharpness":0.80,
           "mask_type":4, "mask_pitch":3.0, "mask":0.15, "halation":0.12,
           "diffusion":0.10, "convergence":0.0, "brightness":1.0, "persistence":0.0 } }
```

`monitor_cal` picks the monitor the CPC is plugged into, which sets the
horizontal framing of the visible-screen crop (`crop=true` screenshots, the
"Visible screen only" view). `"auto"` (default) assumes the monitor matching the
CRTC, so the frame is centred. `"ctm"` (CTM640/644, calibrated for CRTC 0/1/2)
and `"cm14"` (CPC+ monitor, calibrated for CRTC 3/4) force one monitor: the
other CRTC family then shows the frame shifted 16 px (CRTC 3/4 on a CTM: left;
CRTC 0/1/2 on a CM14: right). The full frame is unaffected.

Selecting a `monitor` preset loads that preset's default parameters. Ranges:
`curvature` 0–0.03, `scanline`/`sharpness`/`mask`(≤0.25)/`halation`/`diffusion`/`persistence` 0–1,
`mask_type` 0–4, `mask_pitch` ~1–6, `convergence` −2…2, `brightness` 0.1–3.

**Response**: `200 application/json` — `{"cmd_seq":N}`

---

## BASIC Debugger Endpoints

These power the **BASIC** tab (live listing with current-line/statement
highlight, line/statement stepping, breakpoints, run-to, variable hover). They
rely on the Locomotive BASIC text pointers `0xAE1D` (current line) and `0xAE1B`
(current statement / execution address).

The CRT shader block takes eleven parameters, all optional and all validated:
`curvature`, `scanline`, `sharpness`, `mask_pitch`, `mask`, `halation`,
`diffusion`, `convergence`, `brightness`, `persistence` (numbers) and `mask_type`
(integer). A non-numeric value is a `400`, not a silent fallback to the default —
that changed in 1.14.4, see the changelog.

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

### `POST /api/basic_step[?mode=line][&over=true]`

Resumes the program and re-pauses once it advances:
- default (no `mode`): to the **next statement** (watches `0xAE1B`);
- `?mode=line`: to the **next BASIC line** (watches the line number).

With no program line running (direct mode, `cur_linenum` 65535 in
`GET /api/basic_state`) it executes one Z80 instruction instead, as the
native F7 key does.

`?over=true` steps **over** a `GOSUB`: the subroutine runs and execution pauses
on the following statement. Any other statement is a plain step; in direct
mode it is a Z80 step-over (see `POST /api/step`). `over` other than `true`, `false`,
`1` or `0` → `400`; so is a `mode` other than `line`.

**Response**: `200 application/json` — `{"cmd_seq":N}`

---

### `POST /api/basic_bp`

**Deprecated: use `PUT /api/breakpoints`** (`{"basic":[{"line":100}]}` — no statement address to look up).

Replaces the BASIC breakpoint set. Body is a comma-separated list of decimal
statement addresses — the `stmt_addr` of `GET /api/basic_listing` — (empty body
clears all). While breakpoints exist, the emulator pauses when execution
reaches one of those statements.

```bash
curl -X POST http://127.0.0.1:6128/api/basic_bp -d '4660,4702'
curl -X POST http://127.0.0.1:6128/api/basic_bp -d ''     # clear all
```

**Response**: `200 application/json` — `{"cmd_seq":N}`

---

### `POST /api/basic_runto?line=<n>` · `POST /api/basic_runto?addr=<n>`

One-shot "run to": resumes and pauses when execution reaches the given BASIC
line (`line=`) or statement address (`addr=`, an `0xAE1B` value from
`/api/basic_listing`). The target is cleared once hit.

**Response**: `200 application/json` — `{"cmd_seq":N}`

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

### `POST /api/z80`

Writes Z80 registers. Executed by `web_server_poll` at the next loop iteration
— same queue as `POST /api/ram` and `POST /api/exec`, applied in arrival order.

**Body**: `application/json`, one optional integer field per register — a
**partial update**: a field that is absent leaves that register unchanged.
Same semantics as the Lua `cpc.setZ80({...})` binding ([scripting.md](scripting.md)),
reachable here without a script.

```json
{"PC": 16384, "A": 62}
```

| Field | Range | Field | Range |
|---|---|---|---|
| `PC`, `SP`, `IX`, `IY` | 0–65535 | `A`, `F`, `B`, `C`, `D`, `E`, `H`, `L` | 0–255 |
| `A2`, `F2`, `B2`, `C2`, `D2`, `E2`, `H2`, `L2` | 0–255 | `I`, `R` | 0–255 |
| `IFF1`, `IFF2` | 0 or 1 | `IM` | 0–2 |

Every field is validated (type and range) by the router before the handler
runs, same as `POST /api/ram`'s `addr`/`bank`. At least one field is required.

**Response**: `200 application/json` — `{"cmd_seq":N}`

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

Returns FDC (PD765) register state and the per-drive mechanical state (motor inertia, head position, step counter). Same payload as the `"fdc"` object in `GET /api/state`; fields are described in its table.

**Response**: `200 application/json`

---

### `GET /api/keymatrix`

Returns the current state of the 10-row CPC keyboard matrix (raw hardware view, one byte per row).

**Response**: `200 application/json`

```json
{"matrix": [255,255,255,255,255,255,255,255,255,255]}
```

Each byte is a bitmask of the 8 keys in that row (0 = key pressed, 1 = released, CPC active-low convention).

The matrix is hardware, but what each position *types* depends on the ROM language (on an FR ROM the A and Q positions are swapped, as on an AZERTY CPC), so a position has no name that holds for every language: this endpoint does not name keys.

---

## CPC+ / ASIC Endpoints

CPC+ hardware sprites and their ink palette, read from the core's `Core_Info_Reg_GA`
`ASIC_Sprite_*` fields (filled only when the emulated model carries the ASIC 40489 —
6128+, 464+, GX4000). Both endpoints answer `400` on a classic CPC.

### `GET /api/asic/sprites`

Returns the 16 hardware sprites: position, zoom and pixel bitmap.

**Response**: `200 application/json`, or `400 {"error":"current model is not a CPC+/GX4000 (no ASIC)"}`.

```json
{"sprites": [
  {"id": 0, "display": true, "x": 100, "y": 50, "zoom_x": 0, "zoom_y": 0, "pixels": "0000...0f0f"}
]}
```

- `x`/`y`: signed screen position.
- `zoom_x`/`zoom_y`: magnification shift factor — `0` = ×1, `1` = ×2, `2` = ×4.
- `pixels`: 256 lowercase hex nibbles, row-major (16×16), one 4bpp ink index (0-15) per
  pixel — `0` is transparent. Look each non-zero nibble up in `GET /api/asic/palette`.

---

### `GET /api/asic/palette`

Returns the 16-entry sprite ink palette (index 0 is the transparent placeholder,
1-15 are the hardware sprite ink registers).

**Response**: `200 application/json`, or `400 {"error":"current model is not a CPC+/GX4000 (no ASIC)"}`.

```json
{"palette": [
  {"idx": 0, "rgb444": 0, "rgb": 0},
  {"idx": 1, "rgb444": 3852, "rgb": 16711680}
]}
```

- `rgb444`: raw packed 12-bit hardware color (`0x0RGB`).
- `rgb`: resolved 24-bit RGB (`0xRRGGBB`), ready for a canvas `fillStyle`.

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
curl http://127.0.0.1:6128/api/audio/devices
```

---

## Plugins

A plugin is a native library that emulates a hardware extension plugged into the CPC. They live in the plugin directory (`<config dir>/plugins`) or in the directory the package ships (AppImage, Flatpak), searched after it; `--plugin PATH` can also attach one from elsewhere for the session.

A plugin is native code run with the user's rights, and the API is open to any web page: it can only attach files **already in a plugin directory**, named by plain file name, never by path.

### `GET /api/plugins`

Lists the plugin files of every plugin directory (once per file name, the user directory winning over the shipped one) and which ones are attached. The description and parameters of a plugin are only known once it is attached.

**Response**: `200 application/json`

```json
{"supported": true, "dir": "/home/u/.config/amspirit-lite/plugins",
 "plugins": [
   {"file": "m4board.so", "attached": true, "name": "M4 Board", "version": "0.3.1",
    "description": "SD card interface", "connectors": ["expansion"],
    "params": [{"key": "rate", "label": "Rate", "type": "int", "live": false,
                "default": "10", "value": "10", "min": 1, "max": 100}]},
   {"file": "other.so", "attached": false}]}
```

`supported` is false on builds that cannot load plugins; every POST then answers `501`.

### `POST /api/plugins`

Body: `{"action": "attach"|"detach"|"set_param", "file": "m4board.so"}`, plus:

| Field | For | Role |
|---|---|---|
| `params` | `attach` | Initial parameters, `"key=value,key=value"` (the same grammar as `--plugin`) |
| `key`, `value` | `set_param` | The parameter and its new value, as text |

The request is validated, then queued like the other commands (`{"cmd_seq":N}`). It worked when `GET /api/ping` `emu.applied_cmd_seq >= N` and `N` is not in `emu.failed_cmds`; a refusal carries the reason (for instance a port already claimed by another plugin).

A parameter marked `live` changes at once; any other restarts the plugin (detach + attach) to take the new value. On the native frontends (SDL2, Qt, imgui) the plugins attached at exit are saved with the settings and come back at the next launch; the headless frontend never writes its config.

```bash
curl -X POST http://127.0.0.1:6128/api/plugins -d '{"action":"attach","file":"m4board.so","params":"rate=20"}'
```

---

## Z80 Breakpoints

### `POST /api/z80_bp`

**Deprecated: use `PUT /api/breakpoints`**, which takes the same locations in a `z80` list.

Replaces the Z80 PC breakpoint set. While breakpoints are active, the emulator pauses when the PC hits a breakpoint address.

**Body**: comma-separated list, each entry either

- a **CPU address** — decimal or `0x…` hex, `0`–`65535`. Note that bare digits are read as **decimal** here (`100` is 100, not `0x100`), unlike the shared notation's bare form;
- a **physical location** — `Bnn:hhhh`, where `nn` is a 16 Ko bank index in **hex** (`B00`–`B103`) and `hhhh` a hex offset. An offset above `0x3FFF` carries into the bank, so `B00:4100` is the same byte as `B01:0100`;
- a **ROM location** — `Rnn:hhhh` (upper ROM `nn`, hex) or `FW:hhhh` (firmware ROM), offset `0000`–`3FFF`. These are the forms `GET /api/breakpoints` emits, so its `z80` list can be edited and posted back as it is.

A CPU address names no byte on its own — what it points at depends on the paging — so it is **resolved against the live mapping when the set is applied**, and stored as the RAM bank or ROM that actually holds it. The log line says where it landed. A breakpoint therefore fires on a byte, not on an address: paging a different bank into that slot will not trigger it.

Resuming — `paused:false`, `POST /api/step`, a BASIC step — always executes the instruction at the current PC, even when a breakpoint sits on it, whatever stopped the CPU there (breakpoint, step, pause). The breakpoint fires again as soon as PC comes back to it. Replacing the set while paused does not change this.

The deprecated `Cx:` form is still accepted, as a **decimal** bank index (which is what it meant on this endpoint), with a warning naming the `B` form. Empty body clears all.

(`GET`/`POST /api/ram` take a plain `bank=`/`addr=` pair instead of this string form: a list of heterogeneous locations needs a self-describing token per entry, a single contiguous range does not.)

```bash
# CPU address (resolved to a bank or ROM on apply)
curl -X POST http://127.0.0.1:6128/api/z80_bp -d '0xC000,0xBD19'

# Physical location (extended RAM: bank 4, offset 0x0200)
curl -X POST http://127.0.0.1:6128/api/z80_bp -d 'B04:0200'

# Clear all
curl -X POST http://127.0.0.1:6128/api/z80_bp -d ''
```

**Response**: `200 application/json` — `{"cmd_seq":N}`

### `GET /api/breakpoints`

Everything currently armed to stop the emulation, the three kinds together: the Z80 set above, the BASIC set and the raster breakpoint. It is refreshed every frame, so it also shows what was set from the native window (screen click, `Ctrl+F9`), not only what came through the API. Like every command, a `POST` is visible here only after its `cmd_seq` is applied.

```json
{"z80":["B04:2000","R07:0100","FW:0038"],"basic":[{"line":100,"stmt":2,"addr":4660}],"raster":{"x":256,"y":120}}
```

- `z80` — normalised locations (`Bnn:hhhh`, `Rnn:hhhh`, `FW:hhhh`), in the order they were set. A CPU address posted earlier appears already resolved to the bank or ROM it landed in.
- `basic` — one object per armed statement: `line` and `stmt` (0-based index within the line, as in `lines[].stmts[]` of `GET /api/basic_listing`) and `addr`, the statement address (`stmt_addr` while it runs). `line`/`stmt` are absent when the program no longer holds that address.
- `raster` — `{x, y}` in video-buffer coordinates, or `null` when disarmed.

To remove one breakpoint, read this document, drop the entry and `PUT` the rest back.

### `PUT /api/breakpoints`

Writes the document `GET /api/breakpoints` returns. Each kind present is
**replaced as a whole**; a kind left out is left alone; `"raster":null` disarms.
Everything is validated before anything is queued, so one bad entry (a BASIC line
the program does not have, an unreadable location) is a `400` naming it and
changes nothing. The three kinds are applied together under one `cmd_seq`.

```json
{"z80":["B04:2000","FW:0038","0xC000"],
 "basic":[{"line":100},{"line":120,"stmt":2}],
 "raster":{"x":256,"y":120}}
```

- `z80` — locations in the notation of the Z80 section above (`Bnn:hhhh`, `Rnn:hhhh`, `FW:hhhh`, or a CPU address resolved when applied).
- `basic` — `{"line":N}` is the first statement of line `N`; `"stmt"` picks a later one, 0-based. The line must exist in the program (`GET /api/basic_listing`). `[]` clears. A bare integer is still read as a statement address.
- `raster` — `{"x":N,"y":N}` in video-buffer space, 0–65535.

```bash
curl -X PUT http://127.0.0.1:6128/api/breakpoints -d '{"basic":[{"line":100}]}'
curl -X PUT http://127.0.0.1:6128/api/breakpoints -d '{"z80":[],"raster":null}'
```

**Response**: `200 application/json` — `{"cmd_seq":N}`

### `DELETE /api/breakpoints`

Clears every breakpoint at once — Z80, BASIC, raster, and a pending run-to or
step-over — like the native `Ctrl+F9`. A paused machine stays paused. Connected
debug pages receive a `bp_clear` event on `GET /api/events`.

**Response**: `200 application/json` — `{"cmd_seq":N}`

---

## Rewind & Raster Debugging

### `POST /api/rewind/back`

Steps the rewind back. Only meaningful while a rewind is active (`emu.rw_active`, see `GET /api/state`) — check `emu.rw_steps_back` first to know if there is anywhere to go.

| Query | Default | Meaning |
|---|---|---|
| `n` | `1` | Snapshots to go back (steps past the oldest are ignored) |
| `mode` | `drop` | `navigate`: only navigate, like the native back key, so `POST /api/rewind/forward` can return to where you were |

A restored point rewrites the machine state and the screen image without running a frame, so the displayed picture is the point's own. The emulated tick counter (`emu.ticks`, and the `cycle` argument of plugin callbacks) can go backwards after a restore.

With `mode=drop` the step is destructive: the snapshot becomes the live state and the future beyond it is dropped (`emu.rw_steps_fwd` stays 0). One step is `emu.rw_step_frames` frames when `emu.rw_step_kind` is `"frame"`, otherwise one Z80 instruction or BASIC statement.

```bash
curl -X POST "http://127.0.0.1:6128/api/rewind/back?n=3&mode=navigate"
```

### `POST /api/rewind/forward`

Steps forward `n` snapshots (`?n=`, default 1), the mirror of `back?mode=navigate`. Refused with `400` (field `n`) when `emu.rw_steps_fwd` is 0; steps past the live state are ignored. The machine stays paused.

**Using rewind for debugging** (notably for AI agents): the default setting —
one snapshot every 10 frames — is meant for rewinding a game, and each step back
jumps 0.2 s. To go back in time frame by frame, set the step to **1 frame** and
size the buffer for the window you need to analyse:

```bash
curl -X POST http://127.0.0.1:6128/api/config \
     -d '{"rw_enabled":true,"rw_interval":1,"rw_slots":300}'   # 300 points x 1 frame = 6 s of emulation; ~50 MB at 128 KB
```

Let the program run up to (or past) the moment of interest, pause
(`POST /api/run {"action":"pause"}`), then call `POST /api/rewind/back` repeatedly, inspecting the
machine at each step (`GET /api/state`, `GET /api/ram`, `GET /api/history`,
screenshots). Mind the memory: a point weighs ~0.15 MB (128 KB CPC) to ~0.6 MB (576 KB), and `rw_mem_cap_mb` (default 128) drops the oldest points beyond it — raise it for a long window.

**Response**: `200 application/json` — `{"cmd_seq":N}`

---

### `GET /api/beam`

Returns the current CTM beam position and the crop rectangle for a given `crop=` mode, in the same video-buffer coordinate space as `POST /api/raster_bp` and the `X-Beam-*`/`X-Crop-*` headers of `GET /api/screenshot`.

**Not** what the Screen tab's crosshair uses — that reads the screenshot response's own `X-Beam-*`/`X-Crop-*` headers instead, so the position matches the exact pixels returned in the same response (a separate request here would race against the beam continuing to move). Kept as a standalone query for other tooling.

**Query parameters**:

| Parameter | Type | Default | Effect |
|---|---|---|---|
| `crop` | boolean | `true` | `true` = crop rectangle is the visible screen area, `false` = full physical buffer |

**Response**: `200 application/json`

```json
{"x": 412, "y": 87, "cx": 96, "cy": 39, "cw": 768, "ch": 272}
```

```bash
curl 'http://127.0.0.1:6128/api/beam?crop=true'
```

---

### `POST /api/raster_bp?x=<n>&y=<n>&enable=<bool>`

**Deprecated: use `PUT /api/breakpoints`** (`{"raster":{"x":256,"y":120}}`, or `"raster":null`).

Arms or disarms a raster breakpoint at a pixel in video-buffer space (same coordinates as `GET /api/beam` and the crop headers of `GET /api/screenshot`). Missing `x` or `y`, or `enable=false`, disarms it.

**Query parameters**:

| Parameter | Type | Default | Effect |
|---|---|---|---|
| `x` | integer | — | Target column, 0–65535 |
| `y` | integer | — | Target line, 0–65535 |
| `enable` | boolean | `true` if both `x`/`y` given, else `false` | `false` disarms regardless of `x`/`y` |

```bash
# Arm at (256, 120)
curl -X POST 'http://127.0.0.1:6128/api/raster_bp?x=256&y=120'

# Disarm
curl -X POST 'http://127.0.0.1:6128/api/raster_bp?enable=false'
```

**Response**: `200 application/json` — `{"cmd_seq":N}`  
**Error**: `400 application/json` — `{"error":"field \"x\" must be between 0 and 65535","field":"x"}`

---

## UI Language

### `GET /api/lang`

Returns the current UI language.

**Response**: `200 application/json` — `{"lang":"en"}` (values: `en`, `fr`, `es`, `de`)

---

### `POST /api/lang`

Changes the UI language.

**Body**: `application/json` — `{"lang":"fr"}`

**Response**: `200 application/json` — `{"cmd_seq":N}`  
**Error**: `400 application/json` — `{"error":"invalid lang"}`

---

## Disk Endpoints

### `GET /api/disk?drive=<A|B>`

Scored/sorted catalog of the disk mounted on a drive, computed by the same
disk-autorun heuristic that drives `--autorun`, Ctrl+drop, and the Qt/imgui
"Drive A"/"Drive B" menu (see `doc/keyboard.md`'s sibling, the disk-autorun
spec, for the heuristic itself). `catalog` is only populated for an `amsdos`
disk; `cpm` and `unknown` disks always report an empty list.

**Query parameters**:

| Parameter | Type | Default | Effect |
|---|---|---|---|
| `drive` | string | `A` | Drive to read: `A` or `B` |

**Response**: `200 application/json`

```json
{
  "drive": "A",
  "type": "amsdos",
  "catalog": [
    {"name": "GAME", "ext": "BIN", "hidden": false, "read_only": false, "score": 110},
    {"name": "README", "ext": "TXT", "hidden": false, "read_only": false, "score": -1}
  ]
}
```

`type` is one of `"amsdos"`, `"cpm"`, or `"unknown"` (no disk, or an
unrecognized/corrupt catalog). `score` is only meaningful relative to other
entries on the same disk — higher sorts first; it is not comparable across
disks or across requests to different drives.

**Error**: `400 application/json` — `{"error":"field \"drive\" must be A or B"}`

---

### `POST /api/disk`

Disk management: create a blank disk, eject the disk, or save (download) the current disk image.

**Body**: `application/json`

| Field | Type | Values | Effect |
|---|---|---|---|
| `action` | string | `"create"` | Insert a blank formatted DSK into the given drive |
| `action` | string | `"save"` | Export the current DSK image as a file download |
| `action` | string | `"eject"` | Empty the drive; unsaved writes are flushed to the disk's file first |
| `drive` | string | `A` | Target drive: `A` or `B` |

```bash
# Create a blank disk in drive A
curl -X POST http://127.0.0.1:6128/api/disk \
     -H 'Content-Type: application/json' \
     -d '{"action":"create","drive":"A"}'

# Download current disk A as a DSK file
curl -X POST http://127.0.0.1:6128/api/disk \
     -H 'Content-Type: application/json' \
     -d '{"action":"save","drive":"A"}' -o disk_A.dsk
```

**Create / eject response**: `200 application/json` — `{"cmd_seq":N}`  
**Save response**: `200 application/octet-stream` — attachment `disk_A.dsk` (or `disk_B.dsk`)  
**Save error** (no disk or failed): `500 application/json` — `{"error":"no disk or save failed"}`

---

## Media Loading

### `POST /api/media?name=<filename>&drive=<A|B>&crtc=<keep|sna>&cro_group=<n>`

Loads a media file into the emulator from the raw request body — the SNA/DSK/
HFE/IPF/CDT/CPR/CRO/BIN counterpart of drag-and-drop or the frontend's `Ctrl+O`
file picker. The format is autodetected from content (magic bytes), same as
everywhere else in the app; `name` only matters for a headerless raw
`.bin`/`.amsdos` payload, which cannot be autodetected and is instead routed
by extension (see below).

**Body**: `application/octet-stream` — the raw file bytes.

**Query parameters**:

| Parameter | Type | Default | Effect |
|---|---|---|---|
| `name` | string (URL-encoded) | — | Filename, e.g. `game.dsk`. Required for `.bin`/`.amsdos`; used to label the loaded media otherwise. |
| `drive` | `A` or `B` | `A` | Target floppy drive for DSK/HFE/IPF images |
| `crtc` | `keep` or `sna` | `sna` | SNA only. A v3 snapshot names its CRTC type (byte `0xA4`) and loading it switches the machine to it. `keep` puts back the CRTC emulated before the load — so `POST /api/config {"crtc_type":N}` then `?crtc=keep` runs the snapshot on CRTC N without a hard reset. Only within the same side of the Plus boundary: CRTC 3 (Plus ASIC) and 0/1/2/4 (classic) do not mix; across it the snapshot's CRTC is used and a warning is logged. Read the outcome in `emu.crtc_type` once `emu.applied_cmd_seq` reaches the `cmd_seq`. |
| `cro_group` | integer | — | CRO only (ignored for other formats): `GNUM` of the group to load. Required when the CRO holds several groups; a single-group CRO needs none. Checked at once against the file, see below |
| `pause` | boolean | `false` | `true` pauses right after a successful load, before its first instruction runs, so breakpoints can be armed on start-up code that runs once. Resume with `POST /api/run {"action":"resume"}`: the instruction at the entry PC then runs even under a breakpoint, so set breakpoints on a later address. Not applied when the load fails |

A CRO holding several groups loads only one, and there is no default group.
Sent without `cro_group`, it is refused with `400` at once; a `cro_group` the
file lacks is refused the same way. Both bodies list the file's groups, so the
client can retry; `reason` tells the two apart:

```json
{"error": "CRO with 3 groups: name the one to load with the cro_group query parameter",
 "field": "cro_group", "reason": "cro_group_required",
 "groups": [{"gnum": 0, "label": "Cartouche Basic Amstrad_FR.cpr", "rom_count": 4, "bankable": true},
            {"gnum": 1, "label": "Burnin Rubber & Locomotive Basic_FR.cpr", "rom_count": 8, "bankable": true},
            {"gnum": 2, "label": "AMSDOS seule (classique)", "rom_count": 1, "bankable": false}]}
```

`reason` is `cro_group_unknown` for a `cro_group` the file lacks. `bankable`
says the group has cartridge banks: loading it switches a classic model to a
6128+. `GET /api/rommap` `cro` shows the loaded group.

A `.cpr` carries no CRTC type: loading one puts a classic machine on a 6128 Plus and a Plus or GX4000 on CRTC 3, whatever a previous SNA had imposed.

An uploaded disk has no file on the host: what the CPC writes to it stays in
memory and is never autosaved; `POST /api/disk {"action":"save"}` returns the
image to keep it. Before a disk is replaced, the outgoing disk's unsaved writes
go back to its file; an image the core refuses puts the previous disk back in
the drive.

Like the other mutating routes, the request only enqueues the load; it is
applied on the main thread at the next loop iteration (`Core_*` calls are not
safe from the web server's thread). The response confirms the upload was
queued, not that the load succeeded — wait for `emu.applied_cmd_seq` to reach
the returned `cmd_seq`, then look for that `cmd_seq` in `emu.failed_cmds`
(absent = loaded). Two uploads sent back to back both load, in order. Plain
text named `.bas` (BASIC source: send it to `POST /api/basic`) or `.csl`/`.lua`
(send it to `POST /api/script`) is refused with `400` at once.

Supported formats and how each is detected:

| Format | Detection | Notes |
|---|---|---|
| `.sna` snapshot | content (`MV - SNA` magic) | Restores the full machine state |
| `.dsk` (standard/extended) | content (`MV - CPCEMU` / `MV - CPC Disk-File` / `EXTENDED CPC DSK` magic) | Inserted into `drive` |
| `.hfe` | content (`HXCPICFE` magic) | Inserted into `drive` |
| `.ipf` | content (`CAPS` magic) | Inserted into `drive` |
| `.cdt` tape | content (`ZXTape!` magic) | Inserted in the tape deck |
| `.cpr` cartridge | content (`RIFF...AMS` magic) | Loaded as a standard cartridge; a classic model switches to a 6128+ first. Hard reset afterwards. A file the core rejects is not loaded (listed in `emu.failed_cmds`) but the model switch stays: `POST /api/config` `cpc_model` to go back |
| `.cro` ROM container | content (`RIFF...CRO ` magic) | Validated as a whole first: an invalid file loads nothing (listed in `emu.failed_cmds`, the log names the error). One group is loaded (`cro_group`, see above). A group with cartridge banks replaces the cartridge and switches a classic model to a 6128+; one without banks adds its ROMs. The current CRO sent again (same `name`, e.g. another `cro_group`) first rebuilds the machine on the model and system ROMs it was first loaded on, so nothing of the previous group stays. Hard reset afterwards |
| `.bin`/`.amsdos` | **filename extension**, not content | AMSDOS-header binaries load directly; a headerless raw binary needs an explicit load address via `name=game@4000.bin` (optionally `@ENTRY`), e.g. `name=game@4000@4000.bin`. Addresses are four hex digits, flat 16-bit — no `Bnn:` prefix (its `:` is illegal in a Windows filename). The Qt/imgui **Save binary file** dialog writes names in this same form |
| anything else | fallback — no signature matched | Treated as a headerless binary: loads only with an address in `name`, else listed in `emu.failed_cmds` |

```bash
# Insert a DSK into drive A
curl -X POST 'http://127.0.0.1:6128/api/media?name=game.dsk&drive=A' \
     -H 'Content-Type: application/octet-stream' \
     --data-binary @game.dsk

# Restore a snapshot
curl -X POST 'http://127.0.0.1:6128/api/media?name=save.sna' \
     -H 'Content-Type: application/octet-stream' \
     --data-binary @save.sna

# Headerless raw binary, load address 0x4000
curl -X POST 'http://127.0.0.1:6128/api/media?name=game@4000.bin' \
     -H 'Content-Type: application/octet-stream' \
     --data-binary @game.bin
```

**Response**: `200 application/json` — `{"cmd_seq":N}`
**Error** (empty body): `400 application/json` — `{"error":"empty body: expected the raw media file bytes"}`

**Native-transport only**: this endpoint requires the socket server (SDL2/Qt/
SDL2-imgui native builds). The WASM build's `ams_web_request` bridge marshals
the body as a NUL-terminated C string and cannot carry arbitrary binary data,
so `/api/media` is not usable there — use the browser's own file-open UI on
that target instead.

---

### `GET /api/snapshot`

Saves the current machine state as a `.sna` snapshot and streams it back in the response. The emulator writes no file: the client keeps the bytes wherever it wants, so this works against a remote emulator too. The snapshot is the same one `save_snapshot_to` writes for the snapshot keys and the CSL `snapshot` function.

No parameters.

```bash
curl -s http://127.0.0.1:6128/api/snapshot -o amspirit_snapshot.sna

# Load it back later (same machine or another one)
curl -X POST 'http://127.0.0.1:6128/api/media?name=amspirit_snapshot.sna' \
     -H 'Content-Type: application/octet-stream' \
     --data-binary @amspirit_snapshot.sna
```

**Response**: `200 application/octet-stream` — attachment `amspirit_snapshot.sna`  
**Error** (the core could not write a snapshot): `500 application/json` — `{"error":"snapshot failed"}`

The state is read live on the web thread, without a lock, like `GET /api/state`, so a snapshot taken while the emulator runs may not be a consistent instant. Pause first (`POST /api/run {"action":"pause"}`) for a clean image.

---

## Keyboard Remapping

### `POST /api/keymap`

Remaps one host key: it types another CPC character from now on.

**Body**: `application/json`

| Field | Type | Role |
|---|---|---|
| `host_key` | string | The host key to remap, as the character it types (`"w"`, `"é"`) or `U+XXXX` — one character, never a key name |
| `types` | string | The CPC character it should now produce: one of the `types` of `GET /api/keymap` (a character, or `U+XXXX`) |

```bash
curl -X POST http://127.0.0.1:6128/api/keymap \
     -H 'Content-Type: application/json' \
     -d '{"host_key":"w","types":"z"}'
```

The binding copies the entry of the *CPC character* from the ROM language's
table, so a remap follows the firmware's nationalisation, SHIFT included: on an
FR ROM, `"types":"1"` holds SHIFT, as typing `1` does. It does not name a
physical CPC key — for that, use `POST /api/keypress`. A `types` the CPC does not
type for the current ROM language is refused with 400.

The remap is applied by the emulation loop (`applied_cmd_seq >= cmd_seq`) and
saved to the keymap file as an **override** of the language table: only the
entries that differ are written, so a later ROM-language change is not frozen
out. A **stale** `keymap.cfg` silently overrides the table — delete it to undo.

**Response**: `200 application/json` — `{"cmd_seq":N}`  
**Error**: `400 application/json` — e.g. `{"error":"missing field \"host_key\": ...","field":"host_key"}` (see "Request bodies and errors" above)

---

## Endpoint Summary Table

| Method | Path | Description |
|---|---|---|
| GET | `/` | HTML web interface |
| GET | `/api/doc` | List every documented endpoint (projection of the route record) |
| GET | `/api/doc/<name>` | Full detail for one endpoint: operations, params, response shape |
| GET | `/api/events` | Server-Sent Events stream, one message per emulated frame |
| GET | `/api/license` | License (CC BY-NC-ND 4.0) and attribution request, addressed to tools/agents built on this API |
| GET | `/api/ping` | Lightweight connectivity probe (also returns emu state) |
| GET | `/api/state` | Full emulator state: Z80 / GA / PSG / FDC / emu |
| GET | `/api/z80` | Z80 registers only |
| POST | `/api/z80` | Write Z80 registers (partial update) |
| GET | `/api/ga` | Gate Array registers only |
| GET | `/api/psg` | PSG registers only |
| GET | `/api/fdc` | FDC registers + per-drive mechanical state |
| GET | `/api/keymatrix` | Raw 10-row CPC keyboard matrix |
| GET | `/api/crtc` | CRTC register/counter snapshot |
| GET | `/api/asic/sprites` | CPC+ ASIC hardware sprites (position, zoom, pixel bitmap); 400 on non-CPC+ |
| GET | `/api/asic/palette` | CPC+ ASIC sprite ink palette (16 entries); 400 on non-CPC+ |
| GET | `/api/config` | Current emulator configuration |
| POST | `/api/config` | Change model, CRTC, language, reset, pause, keyboard mapping, rewind |
| POST | `/api/quit` | Orderly app shutdown (flushes disk autosave + config) |
| GET | `/api/lang` | Current UI language (`en`/`fr`/`es`/`de`) |
| POST | `/api/lang` | Change UI language |
| GET | `/api/ram?addr=N&len=N[&bank=N][&view=cpu]` | Read bytes from RAM (raw, a given 16K bank, or CPU-visible view) |
| POST | `/api/ram` | Write bytes to RAM (optional execution) |
| POST | `/api/exec` | Redirect Z80 PC |
| POST | `/api/run` | Execution control: pause, resume, reset, step (Z80 or BASIC) |
| POST | `/api/step[?over=true]` | Execute one Z80 instruction (or step over a CALL), then pause |
| POST | `/api/z80_bp` | Deprecated: use `PUT /api/breakpoints`. Set/clear Z80 PC breakpoints |
| GET | `/api/breakpoints` | Everything armed: Z80, BASIC and raster breakpoints |
| PUT | `/api/breakpoints` | Replace the Z80, BASIC and/or raster breakpoints with the document GET returns |
| DELETE | `/api/breakpoints` | Clear every breakpoint (Z80, BASIC, raster) |
| GET | `/api/history` | Last executed Z80 instructions (depth set by `history_size`) |
| GET | `/api/codemap` | Code map per RAM bank / ROM, as a view (code/data zones) |
| DELETE | `/api/codemap` | Reset the code map of every memory + history |
| GET | `/api/memmap` | ROM/RAM mapping per 16 KB region + RAM banking config |
| DELETE | `/api/cartridge` | Eject the cartridge (banks leave the ROM catalog) and hard-reset |
| GET | `/api/rommap` | ROM catalog: loaded firmware/extension/cartridge-bank ROMs and their sources |
| GET | `/api/screenshot[?crop=N&live=N&full=N]` | Current frame as a PNG (+ beam/crop headers) |
| GET | `/api/render` | Current CRT monitor preset, screen type, shader params |
| POST | `/api/render` | Change monitor preset / screen type / CRT shader params |
| GET | `/api/audio` | Audio snapshot (last N frames from emulator buffer) |
| GET | `/api/audio/record[?format=wav]` | Ring-buffer audio window (JSON or WAV download) |
| GET | `/api/audio/devices` | List audio output devices and the current selection |
| GET | `/api/plugins` | Plugin files of the plugin directory, which are attached, their parameters |
| POST | `/api/plugins` | Attach, detach or configure a plugin of the plugin directory |
| GET | `/api/disk?drive=<A\|B>` | Scored/sorted catalog of the disk mounted on a drive (disk-autorun heuristic) |
| POST | `/api/disk` | Create blank disk or save/download current disk image |
| POST | `/api/media?name=N&drive=N` | Load a SNA/DSK/HFE/IPF/CDT/CPR/CRO/BIN file from the request body |
| GET | `/api/snapshot` | Current machine state as a `.sna` file (streamed, not written on the emulator's disk) |
| POST | `/api/rewind/back[?n=N&mode=navigate]` | Step the rewind back N snapshots (destructive unless `mode=navigate`) |
| POST | `/api/rewind/forward[?n=N]` | Step the rewind forward N snapshots (after `back?mode=navigate` or a native back step) |
| GET | `/api/beam[?crop=N]` | Current CTM beam position + crop rectangle |
| POST | `/api/raster_bp?x=N&y=N&enable=N` | Arm/disarm a raster breakpoint |
| POST | `/api/keytype` | Send text to the emulator (autotype) |
| POST | `/api/keypress` | Press, hold or release a single CPC key, by name |
| POST | `/api/joystick` | Hold a joystick state (directions and fire buttons) until released |
| GET | `/api/keymap` | Host key to CPC character mapping, plus the emulator hotkeys |
| POST | `/api/keymap` | Remap one host key to type another CPC character |
| POST | `/api/basic[?reset=true][?run=true]` | Inject a Locomotive BASIC program into RAM |
| GET | `/api/basic_state` | BASIC interpreter state (pointers, current line/statement) |
| GET | `/api/basic_export[?verbose=true]` | Export (detokenize) the current BASIC program as source |
| GET | `/api/basic_listing` | Structured listing: lines + statements + RAM addresses + referenced vars |
| POST | `/api/basic_step[?mode=line][&over=true]` | Step to the next BASIC statement (or line, or over a GOSUB) |
| POST | `/api/basic_bp` | Deprecated: use `PUT /api/breakpoints`. Set the BASIC breakpoint set (comma-separated statement addresses) |
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
        for (const WebCpuOp& op : pending.cpu_ops) {
            if (op.is_z80) {
                for (const WebZ80RegWrite& r : op.regs)
                    Core_z80_Write_Register(r.core_reg, r.value);
                continue;
            }
            const WebRamWrite& w = op.ram;
            uint8_t* ram = emu_state.Memory_RAM;
            for (size_t i = 0; i < w.data.size(); ++i)
                ram[w.addr + i] = w.data[i];
            if (w.exec)
                Core_z80_Write_Register(CORE_Z80_REGISTRE_PC, w.entry);
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
