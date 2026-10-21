# Migrating from AMSpiriT Lite 1.16 to 1.17

This guide covers the changes a client of AMSpiriT Lite must make when moving
from **1.16.x** to **1.17.0**: the HTTP API of the embedded debug server
(`--web-server`, see [web_server_api.md](web_server_api.md)) and the Lua
scripting API (see [scripting.md](scripting.md)).

The emulation core API (`Core_Amspirit.h`) has no breaking change in 1.17: the
only edit to the header is a documentation comment. If you link against the
core directly, you can rebuild without changes.

Most old spellings still work. The compatibility layer keeps old fields and
integer values accepted (they are not documented anymore), so a client that
only reads the new responses can be migrated gradually. The items marked
**breaking** are the ones that fail or misbehave without a change on your side.

## Summary

| # | Change | Kind |
|---|---|---|
| 1 | Command responses no longer carry `"ok"`; they return `{"cmd_seq":N}` | **Breaking** |
| 2 | `POST /api/ram` and `POST /api/exec` answer `{"seq","cmd_seq"}`; wait on `cmd_seq` | Breaking if you read `seq` |
| 3 | `GET /api/config` returns `cpc_model` as a name (`"6128"`), not an integer | **Breaking** |
| 4 | `GET /api/state`: `fdc.drive` is `"A"`/`"B"`, not `0`/`1` | **Breaking** |
| 5 | Booleans are `true`/`false` (query: `true`/`false`/`1`/`0`); other values are a `400` | Breaking for bad values only |
| 6 | Parameters are `snake_case`; `maskType` and `over=1` are legacy spellings | Deprecated |
| 7 | Key presses: `cpc_key` name replaces the CPC VK code `vk` | Deprecated (`vk` still accepted) |
| 8 | Pause/resume/reset/step move to `POST /api/run` | Deprecated fields in `POST /api/config` |
| 9 | Commands can fail after being accepted; check `emu.failed_cmds` or use `?wait=` | New behaviour |
| 10 | `reset` SSE event fires on every reset, from any source | **Behaviour change** |
| 11 | `POST /api/exec` pages ROM out before the jump | **Behaviour change** |
| 12 | RAM `bank` numbering is validated against the installed RAM | **Behaviour change** |
| 13 | Lua: `disk_insert("B", …)` works; `crtc_select`/`cpc_model` raise on failure | **Behaviour change** |

---

## 1. Command responses: no more `"ok"`

Every command (`POST`/`DELETE` that changes emulator state) used to answer
`{"ok":true,"cmd_seq":N}`. It now answers **`{"cmd_seq":N}`**. "Queued" is no
longer confused with "done": a `200` means the request was accepted.

Before:

```js
const r = await fetch('/api/keytype', {method: 'POST', body: JSON.stringify({text: 'RUN\r'})});
if (!(await r.json()).ok) throw new Error('refused');
```

After:

```js
const r = await fetch('/api/keytype', {method: 'POST', body: JSON.stringify({text: 'RUN\r'})});
if (!r.ok) throw new Error(await r.text()); // a 400 carries {"error","field"}
const {cmd_seq} = await r.json();
```

Check the HTTP status, not a body field. A `400` body is `{"error":"…","field":"…"}`
and names the offending field.

Affected: `POST /api/keytype`, `/api/keypress`, `/api/joystick`, `/api/basic`,
`/api/config`, `/api/run`, `/api/step`, `/api/z80`, `/api/script`, `/api/quit`,
`/api/breakpoints`, `/api/z80_bp`, `/api/media`, `/api/disk`, `/api/rewind/*`,
and `DELETE /api/script`.

## 2. RAM and exec writes: wait on `cmd_seq`

`POST /api/ram` and `POST /api/exec` used to return `{"ok":true,"seq":N}`, with
`seq` matched against `emu.ram_apply_seq`. They now return:

```json
{"seq": 12, "cmd_seq": 12}
```

- Use **`cmd_seq`** and compare it with `emu.applied_cmd_seq` (from
  `GET /api/ping` or `GET /api/state`).
- `seq` and `emu.ram_apply_seq` are **deprecated**. They hold the same values as
  `cmd_seq` and `applied_cmd_seq`, and will be removed.
- The eval `seq` (`POST /api/eval` → `GET /api/eval?seq=N`) is a different
  counter. Do not compare it with `cmd_seq`.

```bash
SEQ=$(curl -s -X POST http://127.0.0.1:6128/api/ram -d '{"addr":16384,"data":"00ff"}' | jq .cmd_seq)
until [ "$(curl -s http://127.0.0.1:6128/api/ping | jq .emu.applied_cmd_seq)" -ge "$SEQ" ]; do sleep 0.05; done
```

Or let the server wait for you with `?wait=<ms>` (0–30000) on any command:
`200 {"cmd_seq":N,"applied":true}` once applied, `422` if refused at apply time,
`408` if still queued after the delay (it stays queued).

```bash
curl -s -X POST 'http://127.0.0.1:6128/api/ram?wait=2000' -d '{"addr":16384,"data":"00ff"}'
```

Writes that can now fail after acceptance (see item 9) are: `POST /api/media`,
`POST /api/ram` / `/api/exec` (RAM size changed before apply) and
`POST /api/disk` `create`.

## 3. `GET /api/config`: `cpc_model` is a name

```diff
- "cpc_model": 2,
+ "cpc_model": "6128",
```

Values: `"464"`, `"664"`, `"6128"`, `"6128+"`, `"464+"`, `"GX4000"`. The same
names are accepted by `POST /api/config`. Integers are still accepted on input
(legacy) but are not documented and must not be sent by new code.

`GET /api/config` also gains `last_reinit` (`"ok"`, `"fell_back_to_6128"`,
`"plus_firmware_missing"`, `"failed"` or `"none"`). Read it after the
`applied_cmd_seq` of a model, CRTC or ROM-language change has reached that
change's `cmd_seq`. A missing ROM is **not** a `400`, so this field is how you
detect it.

`GET /api/state` `emu.cpc_model` already used names in 1.16 and is unchanged.

## 4. `GET /api/state`: `fdc.drive`

```diff
- "fdc": { "drive": 0, … }
+ "fdc": { "drive": "A", … }
```

`"A"` or `"B"`. `fdc.drives[]` is still indexed 0 = A, 1 = B.

Also new in `GET /api/state`:

- `z80.int_pending`: INT asserted and not yet acknowledged (it stays `true`
  through a `di`).
- `emu.failed_cmds`: the 16 most recent commands refused at apply time
  (`[{"cmd_seq":12,"error":"…"}]`, oldest first).
- `emu.rw_step_frames`: frames one rewind step is worth.

`emu.ram_apply_seq` is deprecated (see item 2).

## 5. Booleans and parameter names

- **Booleans**: in a JSON body use `true`/`false`. In a query string use
  `true`, `false`, `1` or `0`. Anything else is now a `400`.
  Typical changes: `?crop=0` → `?crop=false`, `?verbose=1` → `?verbose=true`,
  `?run=1` → `?run=true`. The `0`/`1` forms still work.
- **Absent means not provided.** Do not send `-1` to mean "unused".
- **Names are `snake_case`**: `mask_type` (was `maskType`), `rw_slots`, etc.
  `maskType` is still accepted, not documented.
- **Closed vocabularies are named**: `"6128+"`, `"CTM644"`, drive `"A"`/`"B"`.
  A `400` lists the accepted values.
- `over=1` on the step endpoints is a legacy spelling of `over=true`.

## 6. Key presses: `cpc_key` replaces `vk`

`POST /api/keypress` took a CPC VK code (`{"vk":32}`). It now takes a key name
that matches the legend of the key on the keyboard of the ROM language:

```diff
- {"vk": 32}
+ {"cpc_key": "SPACE"}
```

New capabilities:

```json
{"cpc_key": "Q", "down": true}
{"cpc_key": "Q", "down": true, "frames": 50}
{"cpc_key": "Q", "down": false}
```

- Absent `down` is a one-shot press (as before). `down: true` holds the key;
  `down: false` releases it; `frames` (1–100000) releases it by itself.
- `SHIFT` is not synthesised by a hold: hold `{"cpc_key":"SHIFT","down":true}`
  alongside the key.
- **Digits `0`–`9` press nothing on their own** (known limitation). Type digits
  with `POST /api/keytype`.
- `vk` is still accepted (legacy). Code that sends `vk` for a one-shot press
  keeps working, but move to `cpc_key`: it is the same on every ROM language,
  and VK numbers are not.

For text, prefer `POST /api/keytype`, which handles the shift and control layer
from the characters.

Keytype note: `\r`, `\n` and `\r\n` each type RETURN. Typing advances only while
the machine runs, so a `keytype` sent during a pause waits for the resume. Wait
for `GET /api/ping` `emu.autotyping` to be `false` before assuming it is done.

## 7. Execution control: `POST /api/run`

Pause, resume, reset and single-stepping now have one endpoint. The fields
`paused`, `do_soft_reset` and `do_hard_reset` are no longer documented on
`POST /api/config`; they are still accepted but must not be used by new code.

```diff
- curl -X POST http://127.0.0.1:6128/api/config -d '{"paused":false}'
+ curl -X POST http://127.0.0.1:6128/api/run -d '{"action":"resume"}'

- curl -X POST http://127.0.0.1:6128/api/config -d '{"do_hard_reset":true}'
+ curl -X POST http://127.0.0.1:6128/api/run -d '{"action":"reset","kind":"hard"}'
```

```bash
curl -X POST http://127.0.0.1:6128/api/run -d '{"action":"pause"}'
curl -X POST http://127.0.0.1:6128/api/run -d '{"action":"step","over":true}'
curl -X POST http://127.0.0.1:6128/api/run -d '{"action":"step","target":"basic","unit":"line"}'
```

- `pause`/`resume` never clear breakpoints.
- `POST /api/step` and `POST /api/basic_step` remain as aliases. `POST /api/step`
  gains `?over=true` (step over a `CALL`).
- A parameter that does not belong to the `action` is a `400`.

`POST /api/config` now refuses a `cpc_model` / `crtc_type` pair the emulator
cannot build (a Plus or GX4000 runs only CRTC 3; a classic CPC runs anything but
3) with a `400`, instead of rewriting one of them. Without `crtc_type`, a Plus
takes CRTC 3.

Rewind: `POST /api/rewind/back` takes `rw_delta` (net steps, negative = back)
and `rw_navigate`. `POST /api/rewind/forward` is new.

## 8. Commands can fail after acceptance

Some commands are accepted, then refused when the emulation thread applies them.
Once `emu.applied_cmd_seq >= cmd_seq`, look for your command in
`emu.failed_cmds`:

- absent: it worked;
- present: `error` says why.

Or use `?wait=<ms>` (item 2), which returns `422` with the error directly.

## 9. Behaviour changes

These do not break a request's shape, but they change what happens. Review
them if your client depends on the old behaviour.

- **SSE `reset` event (`topics=reset`)** fires on every hard or soft reset, from
  any source: key, menu, model or RAM change, script or API. Before 1.17 it
  missed some paths.
- **`POST /api/exec` and `POST /api/ram`** page the ROMs out before the jump,
  like `POST /api/media` does for binaries: a target below `0x4000` pages out
  the lower ROM, a target at `0xC000` and above pages out the active upper ROM.
  Code that relied on the ROM staying visible must not rely on it. While the
  lower ROM is out, the interrupt vector at `0x38` reads RAM: run with
  interrupts disabled or install your own handler.
- **`POST /api/ram` `bank`** is validated against the installed RAM. A bank
  not installed at the current size is a `400` (`field: bank`); `addr` carrying
  past the last bank and `data` crossing a 64 Ko block are also `400`s. Nothing
  is queued. `bank` is always physical: there is no `view` on writes.
- **`POST /api/basic`** refuses a listing with no numbered line (`400`, nothing
  reset). Before, it replaced the program with an empty one. Type direct
  commands with `POST /api/keytype`.
- **`POST /api/keypress` hold semantics**: a held key stays down until released,
  its `frames` budget runs out, or a reset. A one-shot press of a held key
  releases it.
- **`POST /api/media`** accepts `crtc=keep` (keep the emulated CRTC for an SNA
  instead of the one it names) and `?wait=`.
- **`/api/joystick`** is new: it holds a joystick state on port 0. Each call
  states the whole joystick; a direction left out is released.
- **CORS** preflight now allows `PUT` (no effect on existing clients).

## 10. Other new endpoints

- `GET /api/breakpoints`: the armed breakpoints (published each frame).
- `GET /api/plugins`: the frontend's plugin host (see [plugins.md](../../doc/plugins.md)).
- `POST /api/run`: see item 7.
- `POST /api/joystick`: see item 9.
- `POST /api/snapshot` and `POST /api/rewind/forward`.

For the complete, current list, query `GET /api/doc` (endpoints) and
`GET /api/doc/<name>` (parameters and response shape) on the running instance.
That is the source of truth for the build you are talking to.

## Lua scripting (`--script`, `POST /api/script`)

Scripts sent over the API run in the sandbox: no `io`, `package`, `debug` or
`require`, and files only through the jailed `fs.*`. That is unchanged.

**Breaking-ish:**

- `disk_insert("B", path)` now inserts into drive B. In 1.16 the drive
  parameter was ignored and the disk always went to A. Check any script that
  passed `"B"` by mistake.
- `crtc_select(n)` and `cpc_model(...)` rebuild the machine like the menus and
  `POST /api/config` do, and **raise a script error** when the firmware does not
  load. Select the model first: a CRTC the model cannot carry is refused.
- Scripts cannot load cartridges (`.cpr`/`.cro`) or binaries; use
  `POST /api/media`. `gate_array`, `rom_dir`, `rom_config`, `snapshot_version`
  and `key_from_file` are accepted and ignored.

**Additions:**

- `disk_eject([drive])`: empty drive A (default) or B, saving its writes first.
- `disk_insert([drive,] path)` takes `"A"` or `"B"`.
- `snapshot_load(path [, keep_crtc])`: `keep_crtc = true` keeps the emulated CRTC.
- `memory_exp(n)`: `0` = 128 Ko, `1` = 320 Ko, `4` = 576 Ko; hard reset.
  `2` (silicon disc) and `3` (4M) are not emulated and raise an error.
- `cpc.getRam(addr, len [, bank])` and `cpc.setRam(addr, data [, bank])`: the
  optional `bank` counts 16 Ko banks (bank 4 is the first bank of the first
  expansion). Without `bank`, both act on the base 64 Ko. A bank the machine
  does not have, or a write crossing its 64 Ko block, raises an error; nothing
  is written. `poke` stays on the base 64 Ko.
- `cpc.getZ80()` returns `int_pending`. `ticks` is read-only.
- `wait_frames(n)` and `wait(usec)` count only frames the machine runs: a pause
  holds them.
- `cpc.setZ80({PC=…})` writes PC as is, without touching ROM paging (same as
  `POST /api/z80`). `POST /api/exec` is the call that pages a covering ROM out.

## Checklist

- [ ] Replace `resp.ok` checks with HTTP status checks (item 1).
- [ ] Wait on `cmd_seq` and `emu.applied_cmd_seq`, not `seq` / `ram_apply_seq` (item 2).
- [ ] Accept `cpc_model` as a string from `GET /api/config` (item 3).
- [ ] Read `fdc.drive` as `"A"`/`"B"` (item 4).
- [ ] Send `true`/`false` for booleans; stop sending `-1` for "unused" (item 5).
- [ ] Use `cpc_key` for key presses; type digits with `/api/keytype` (item 6).
- [ ] Move pause/resume/reset/step to `POST /api/run` (item 7).
- [ ] Check `emu.failed_cmds` or use `?wait=` for writes that can be refused (item 8).
- [ ] Re-check code that depends on the SSE `reset` event, ROM visibility after
      `exec`, or `POST /api/basic` replacing a program (item 9).
- [ ] Lua: check `disk_insert` calls that pass `"B"`, and wrap `crtc_select` /
      `cpc_model` in `pcall` if the firmware may be missing (section above).
