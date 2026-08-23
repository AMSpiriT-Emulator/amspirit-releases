#!/usr/bin/env python3
"""MCP server exposing AMSpiriT-Lite's embedded debug web API (127.0.0.1:8765)
as tools for piloting and analysing a running emulator: state inspection,
RAM read/write, Z80/BASIC breakpoints and stepping, keyboard input, and
screenshots. See src/doc/web_server_api.md for the underlying HTTP contract,
or call the api_doc tool to fetch it from the running emulator itself.

Requires the SDL2 or Qt frontend running with --web-server.
"""

import os

import httpx
from mcp.server.mcpserver import Image, MCPServer

import z80dis

BASE_URL = os.environ.get("AMSPIRIT_WEB_URL", "http://127.0.0.1:8765")

mcp = MCPServer(
    name="amspirit-emulator",
    description="Pilot and inspect a running AMSpiriT-Lite emulator instance",
)

_client = httpx.Client(base_url=BASE_URL, timeout=5.0)


def _request(method: str, path: str, **kwargs):
    try:
        resp = _client.request(method, path, **kwargs)
    except httpx.ConnectError as exc:
        raise RuntimeError(
            f"cannot reach the emulator's web server at {BASE_URL} — is a frontend "
            "running with --web-server?"
        ) from exc
    ctype = resp.headers.get("content-type", "")
    if "application/json" in ctype:
        body = resp.json()
    elif "text/plain" in ctype:
        body = resp.text
    else:
        body = resp.content
    if isinstance(body, dict):
        body["_http_status"] = resp.status_code
    return body


@mcp.tool()
def api_doc(name: str | None = None) -> dict:
    """Discover the emulator's HTTP API contract. With no argument, list every
    endpoint (path, methods, summary). Pass name (the path segment under
    /api/, e.g. 'config' or 'ram') to get that endpoint's full detail: params
    (query/body, type, required/default) and response shape, for every HTTP
    method it supports. Use this instead of guessing an endpoint's shape."""
    if name:
        return _request("GET", f"/api/doc/{name}")
    return _request("GET", "/api/doc")


@mcp.tool()
def emu_state() -> dict:
    """Full emulator snapshot: Z80 registers, Gate Array, PSG, FDC and emu
    (fps/frames/paused/model) state. Use this to inspect what the machine is
    doing right now."""
    return _request("GET", "/api/state")


@mcp.tool()
def emu_ping() -> dict:
    """Lightweight connectivity probe returning the same 'emu' block as
    emu_state (fps, frames, paused, autotyping). Cheaper than emu_state for
    polling loops — e.g. waiting for emu.frames to advance or
    emu.autotyping to clear."""
    return _request("GET", "/api/ping")


@mcp.tool()
def emu_control(paused: bool | None = None, soft_reset: bool = False, hard_reset: bool = False) -> dict:
    """Pause/resume the emulator and/or trigger a soft or hard reset.
    Pausing is required before z80_step or ram_write with execute=True in
    some workflows. Omit paused to leave the pause state unchanged."""
    body = {}
    if paused is not None:
        body["paused"] = paused
    if soft_reset:
        body["do_soft_reset"] = True
    if hard_reset:
        body["do_hard_reset"] = True
    return _request("POST", "/api/config", json=body)


@mcp.tool()
def emu_quit() -> dict:
    """Shut the emulator down cleanly (disk autosave + config are flushed
    through the frontend's normal quit path). The HTTP response arrives
    before the process exits; any later tool call will fail to connect
    until the emulator is started again."""
    return _request("POST", "/api/quit")


@mcp.tool()
def ram_read(addr: int, length: int = 256, bank: int = 0, view: str = "raw") -> dict:
    """Read a block of CPC RAM. addr/length in 0-65535/1-65536. bank: 0 =
    central RAM, 1..N = extended-RAM page N-1. view='cpu' returns memory as
    the Z80 currently sees it (ROM overlays and banking applied) instead of
    raw central RAM. Returns hex-encoded bytes."""
    params = {"addr": addr, "len": length, "bank": bank}
    if view == "cpu":
        params["view"] = "cpu"
    return _request("GET", "/api/ram", params=params)


@mcp.tool()
def ram_write(addr: int, data_hex: str = "", execute: bool = False, entry: int | None = None) -> dict:
    """Write bytes to CPC RAM and/or redirect the Z80 PC. data_hex is a hex
    string of bytes to write (may be empty). If execute is true, the Z80
    jumps to entry (default: addr) after the write — pass data_hex="" with
    execute=True for a plain PC redirect with no write. Applied at the next
    emulator loop iteration."""
    body = {"addr": addr, "data": data_hex, "exec": execute}
    if entry is not None:
        body["entry"] = entry
    return _request("POST", "/api/ram", json=body)


@mcp.tool()
def z80_step() -> dict:
    """Execute exactly one Z80 instruction then re-pause. The emulator must
    already be paused (see emu_control)."""
    return _request("POST", "/api/step")


@mcp.tool()
def z80_history() -> dict:
    """Return the last 20 executed Z80 instructions (oldest first), as
    {pc, hex} pairs — opcode bytes as the CPU actually fetched them."""
    return _request("GET", "/api/history")


@mcp.tool()
def z80_codemap(clear: bool = False) -> dict:
    """Get (or, if clear=True, reset) the 64KB executed-instruction bitmap:
    which addresses have been reached by the Z80 since the last reset. Useful
    for telling code from data in a memory region."""
    if clear:
        return _request("DELETE", "/api/codemap")
    return _request("GET", "/api/codemap")


@mcp.tool()
def memory_map() -> dict:
    """Current ROM/RAM mapping for each 16KB region (which ROM or RAM bank is
    mapped where) plus the RAM banking configuration (RMR, ram_mode,
    ram_page)."""
    return _request("GET", "/api/memmap")


@mcp.tool()
def z80_breakpoints(addresses: list[str]) -> dict:
    """Replace the set of Z80 PC breakpoints. Each address is decimal, hex
    ('0x...'), or bank-qualified ('Cx:YYYY', bank x, hex offset YYYY in
    extended RAM). Pass an empty list to clear all breakpoints. While set,
    the emulator pauses when the PC hits one."""
    return _request("POST", "/api/z80_bp", content=",".join(addresses))


@mcp.tool()
def basic_state() -> dict:
    """Locomotive BASIC interpreter state: program bounds, current line
    number and statement execution address."""
    return _request("GET", "/api/basic_state")


@mcp.tool()
def basic_listing() -> dict:
    """The current BASIC program decoded into lines and statements, each with
    its RAM address range and referenced variable names — use this to match
    basic_state's cur_linenum/stmt_addr against source text."""
    return _request("GET", "/api/basic_listing")


@mcp.tool()
def basic_export(verbose: bool = False) -> str:
    """Detokenize and export the current BASIC program from RAM as plain
    source text."""
    params = {"verbose": 1} if verbose else {}
    return _request("GET", "/api/basic_export", params=params)


@mcp.tool()
def basic_breakpoints(lines: list[int]) -> dict:
    """Replace the set of BASIC line breakpoints. Pass an empty list to clear
    all. While set, the emulator pauses when execution reaches one of these
    lines."""
    return _request("POST", "/api/basic_bp", content=",".join(str(n) for n in lines))


@mcp.tool()
def basic_step(mode: str = "statement") -> dict:
    """Resume and re-pause at the next BASIC statement (mode='statement',
    default) or the next BASIC line (mode='line'). Only meaningful while a
    program line is executing, not in direct mode."""
    params = {"mode": "line"} if mode == "line" else {}
    return _request("POST", "/api/basic_step", params=params)


@mcp.tool()
def basic_runto(line: int | None = None, addr: int | None = None) -> dict:
    """One-shot 'run to': resume and pause once execution reaches the given
    BASIC line number or statement address (an stmt_addr value from
    basic_listing). Pass exactly one of line or addr."""
    params = {}
    if line is not None:
        params["line"] = line
    if addr is not None:
        params["addr"] = addr
    return _request("POST", "/api/basic_runto", params=params)


@mcp.tool()
def keyboard_type(text: str, wait: bool = True, timeout_s: float = 10.0) -> dict:
    """Type text into the emulator as if on the keyboard (use \\r for Enter).
    Successive calls queue rather than overwrite. If wait is true (default),
    poll emu_ping until emu.autotyping clears (or timeout_s elapses) before
    returning, so the caller doesn't have to hand-roll that polling loop."""
    result = _request("POST", "/api/keytype", json={"text": text})
    if wait:
        import time

        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            state = _request("GET", "/api/ping")
            if not state.get("emu", {}).get("autotyping", False):
                break
            time.sleep(0.1)
    return result


@mcp.tool()
def keyboard_press(vk: int) -> dict:
    """Send a single CPC virtual key code (CORE_rVK_* constant, 0-0xFF).
    Delivered after any pending keyboard_type text. Prefer keyboard_type for
    plain text; use this for non-ASCII keys (arrows, function keys, ...)."""
    return _request("POST", "/api/keypress", json={"vk": vk})


@mcp.tool()
def screenshot(crop: bool = True, full: bool = True) -> Image:
    """Capture the current emulator frame as a PNG image — the fastest way
    for an agent to 'see' the screen. crop=True returns just the visible
    screen area; full=True returns the plain settled frame rather than a
    partial-frame composite."""
    params = {"crop": 1 if crop else 0, "full": 1 if full else 0}
    data = _request("GET", "/api/screenshot", params=params)
    if isinstance(data, dict):
        raise RuntimeError(data.get("error", "no frame available"))
    return Image(data=data, format="png")


def _fetch_ram(addr: int = 0, length: int = 65536, bank: int = 0, view: str = "raw") -> bytearray:
    """Fetch a RAM window as a bytearray, addressed by absolute address (not
    relative to addr — index [addr] holds the byte at that CPC address)."""
    resp = ram_read(addr, length, bank, view)
    if "hex" not in resp:
        raise RuntimeError(resp.get("error", "ram read failed"))
    raw = bytes.fromhex(resp["hex"])
    buf = bytearray(65536)
    for i, b in enumerate(raw):
        a = (addr + i) & 0xFFFF
        buf[a] = b
    return buf


@mcp.tool()
def disassemble(addr: int, count: int = 32, bank: int = 0, view: str = "cpu") -> list[dict]:
    """Disassemble count Z80 instructions starting at addr, reading live RAM
    from the emulator. Ported from the embedded web debugger's JS
    disassembler (z80dis). view='cpu' (default) sees ROM/RAM banking as the
    Z80 does; view='raw' reads central RAM directly. Returns a list of
    {addr, mnem, ops, size, hex} in ascending address order."""
    mem = _fetch_ram(0, 65536, bank, view)
    out = []
    pc = addr & 0xFFFF
    for _ in range(count):
        mnem, ops, size = z80dis.decode(mem, pc)
        opcode_hex = bytes(mem[(pc + i) & 0xFFFF] for i in range(size)).hex().upper()
        out.append({"addr": pc, "mnem": mnem, "ops": ops, "size": size, "hex": opcode_hex})
        pc = (pc + size) & 0xFFFF
    return out


@mcp.tool()
def analyze_code_zones(start_addr: int, bank: int = 0, view: str = "cpu", limit: int = 20000) -> dict:
    """Static code/data analysis of the whole 64KB address space, walking
    control flow (jp/jr/call/djnz/rst) from start_addr — ported from the
    embedded web debugger's z80analyze. Returns a compact list of contiguous
    [start, end) address ranges classified as 'code' (reached by the static
    walk) so an agent doesn't have to reason about a 65536-entry bitmap
    directly. Combine with z80_codemap for addresses actually executed at
    runtime (dynamic dispatch, self-modifying code, etc. that static
    analysis can miss)."""
    mem = _fetch_ram(0, 65536, bank, view)
    code = z80dis.analyze(mem, start_addr, limit)
    ranges = []
    run_start = None
    for a in range(65536):
        is_code = code[a] != 0
        if is_code and run_start is None:
            run_start = a
        elif not is_code and run_start is not None:
            ranges.append({"start": run_start, "end": a, "kind": "code"})
            run_start = None
    if run_start is not None:
        ranges.append({"start": run_start, "end": 65536, "kind": "code"})
    covered = sum(r["end"] - r["start"] for r in ranges)
    return {"ranges": ranges, "code_bytes": covered, "data_bytes": 65536 - covered}


@mcp.tool()
def disassemble_range(start_addr: int, end_addr: int, bank: int = 0, view: str = "cpu") -> list[dict]:
    """Disassemble every instruction from start_addr up to (excluding)
    end_addr, without following control flow — a straight linear sweep.
    Useful once analyze_code_zones (or z80_codemap) has told you a range is
    code, to get the full listing for annotation. Returns a list of
    {addr, mnem, ops, size, hex}; may include garbage decodes across data
    embedded in the range, same as any linear Z80 disassembler."""
    mem = _fetch_ram(0, 65536, bank, view)
    out = []
    pc = start_addr & 0xFFFF
    end_addr = max(0, min(end_addr, 65536))  # allow 65536 as an exclusive upper bound
    while pc < end_addr:
        mnem, ops, size = z80dis.decode(mem, pc)
        opcode_hex = bytes(mem[(pc + i) & 0xFFFF] for i in range(size)).hex().upper()
        out.append({"addr": pc, "mnem": mnem, "ops": ops, "size": size, "hex": opcode_hex})
        pc += size
    return out


if __name__ == "__main__":
    mcp.run(transport="stdio")
