# Curve Injector

A single-file web tool (`curve_injector.html`) that lets you draw a byte curve and 
write it live into the emulated RAM of **AMSpiriT** through its local REST API.
It's handy for tweaking lookup tables (wobble, raster, color sequences…) while 
a demo or program is running.

## Quick start

1. Start AMSpiriT with its REST API enabled (default `http://127.0.0.1:6128`).
2. Open `curve_injector.html` **locally** (`file://…`) on the same machine.
3. Click **Check emulator connection**. The status pill should turn green.
4. Set the target **Address** and **Length**, shape the curve, then click
   **Apply to RAM (live)**. You can also enable **Auto-inject on change**.

> If the page is served over `https://`, the browser blocks calls to
> `http://127.0.0.1` (mixed content). The preview and source export still work.

## Features

| Section | What it does |
|---|---|
| **Memory target** | Address (`49152`, `#C000` or `0xC000`), length (2–65536 samples), optional auto-inject with a debounce delay (ms). |
| **Curve source** | Three modes: **Parametric** (waveform plus parameters), **Equation** (JavaScript `f(i)`), **Free draw** (mouse). |
| **Output encoding** | Controls how raw curve values become bytes: **Data** or **Gate Array** (see below). |
| **Output preview** | Shows the bytes that will actually be written, after encoding. |
| **Configuration** | Export/import the full setup as JSON. |
| **Apply** | Check connection, read RAM back into the editor, write the curve, copy the `fantams` source. |

### Curve source modes

- **Parametric**: waveforms are sine, triangle, sawtooth, square, pulse,
  random noise and interleaved ramp. Parameters are center, amplitude, period,
  phase and duty cycle. You can edit each parameter's min/max range. This is the
  only mode you can drive over MIDI.
- **Equation**: a JavaScript expression that takes `i` (index), `n` (length)
  and `t = i/n`, with full `Math` available. Example:
  `128 + 100*Math.sin(2*Math.PI*i/64)`.
- **Free draw**: paint values with the mouse. **Read from emulator** loads the
  current RAM content into this mode.

### Output encoding

- **Data**: 1 or 2 bytes per sample (2 bytes = little-endian).
  Pipeline: `raw value → clamp (saturate | modulo) → AND mask → OR mask → encode`.
  For example, `AND #1E, OR #40` gives even values in `#40–#5E`.
- **Gate Array**: each value picks an ink from a CPC **gradient** (rings,
  single-hue ramps, hue drifts, hue cycle) and is written as its hardware
  **Gate Array code** (`#40–#5F`), not the BASIC ink number. This mode always
  writes 1 byte and has no masks.

### MIDI control

Click **Enable MIDI** (Web MIDI API, Chromium-based browsers) to drive the
waveform and each parametric parameter from a controller. Use **Learn** to bind
a parameter to the next CC you move. The defaults are CC 19–24. Mappings are
kept in `localStorage` and included in the exported JSON. **Reset MIDI mapping**
restores the defaults.


## API endpoints used

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/ping` | Connection check |
| `GET` | `/api/ram?addr=&len=&view=cpu` | Read RAM into the editor |
| `POST` | `/api/ram` `{addr, data}` | Inject the encoded curve (hex string) |
