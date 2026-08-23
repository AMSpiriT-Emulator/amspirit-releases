# amspirit-emulator MCP server

Experimental MCP server exposing the SDL2/Qt frontends' embedded debug web API
(`127.0.0.1:8765`, see `src/doc/web_server_api.md`) as tools, for piloting and
analysing a running emulator instance: state inspection, RAM read/write,
Z80/BASIC breakpoints and stepping, keyboard input, screenshots.

Not part of the build; not registered in `release.yml`/CI. A standalone
Python script for interactive use (e.g. debugging a homebrew program with an
LLM client attached).

## Setup

```bash
cd tools/mcp-emulator
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Start a frontend with the web server enabled (from its build directory, or
via `make debug`/`make release`):

```bash
./amspirit-lite-sdl --web-server
```

## Register with an MCP client

Claude Code:

```bash
claude mcp add amspirit-emulator -- /path/to/tools/mcp-emulator/.venv/bin/python /path/to/tools/mcp-emulator/server.py
```

Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "amspirit-emulator": {
      "command": "/path/to/tools/mcp-emulator/.venv/bin/python",
      "args": ["/path/to/tools/mcp-emulator/server.py"]
    }
  }
}
```

`AMSPIRIT_WEB_URL` overrides the default `http://127.0.0.1:8765` if the
frontend was started with a different `--web-server` port/bind address.

## Tools

| Tool | Wraps |
|---|---|
| `emu_state` | `GET /api/state` |
| `emu_ping` | `GET /api/ping` |
| `emu_control` | `POST /api/config` (pause/resume, soft/hard reset) |
| `ram_read` | `GET /api/ram` |
| `ram_write` | `POST /api/ram` |
| `z80_step` | `POST /api/step` |
| `z80_history` | `GET /api/history` |
| `z80_codemap` | `GET`/`DELETE /api/codemap` |
| `memory_map` | `GET /api/memmap` |
| `z80_breakpoints` | `POST /api/z80_bp` |
| `basic_state` | `GET /api/basic_state` |
| `basic_listing` | `GET /api/basic_listing` |
| `basic_export` | `GET /api/basic_export` |
| `basic_breakpoints` | `POST /api/basic_bp` |
| `basic_step` | `POST /api/basic_step` |
| `basic_runto` | `POST /api/basic_runto` |
| `keyboard_type` | `POST /api/keytype` (+ polls `emu.autotyping` to completion) |
| `keyboard_press` | `POST /api/keypress` |
| `screenshot` | `GET /api/screenshot` (returns a PNG image) |

Out of scope for this server: render/CRT, audio, disk, media loading, UI
language, live keymap remapping, and the CSL/Lua script engine — those are
configuration/content-loading endpoints rather than piloting/analysis, and
were left out to keep the tool list focused.

## Testing

No real Amstrad ROMs are checked into this repo (copyright), so this server
was validated against a mock HTTP server standing in for the documented API
shapes (`GET`/`POST` bodies and content types per `web_server_api.md`), not
against a booted machine. Point `AMSPIRIT_WEB_URL` at a real, ROM-booted
frontend and exercise a tool or two by hand before relying on this for actual
debugging.
