"""Shared parsing/decoding helpers used by several tabs.

Kept Tk-free like api_client.py. The BASIC variable/array decoding here is a
direct port of parseBasicVars/parseBasicArrays/decodeCpcFloat from
amspirit-lite.html (Locomotive BASIC's in-RAM variable-chain layout) -- see
that file for the from-scratch derivation; this only mirrors it in Python.
"""

from __future__ import annotations


class ThreadSafeMirror:
    """A plain, GIL-safe shadow of a Tk variable's current value.

    Every Tk variable read or write must happen on the Tk main thread --
    PollingManager's `fetch`/`active` callables run on a background thread,
    where even a `.get()` on a tk.BooleanVar/StringVar/IntVar is unsafe. This
    mirrors one via `trace_add`, which fires on the main thread whenever the
    widget changes; background code reads `.value` instead of calling the
    Tk variable itself.
    """

    __slots__ = ("value",)

    def __init__(self, tk_var, initial):
        self.value = initial
        tk_var.trace_add("write", lambda *_a: setattr(self, "value", tk_var.get()))


# CORE_rVK_* codes (amspirit-core/inc/Core_Amspirit.h) for the keyboard tab's
# quick-key buttons. Subset mirrors cpc-runner-amspirit's VK_TABLE.
VK_TABLE = {
    "Space": 0x75,
    "Backspace": 0x90,
    "Tab": 0x91,
    "Enter": 0x92,
    "Shift": 0x93,
    "Control": 0x94,
    "Alt": 0x95,
    "CapsLock": 0x96,
    "Escape": 0x97,
    "Left": 0x98,
    "Up": 0x99,
    "Right": 0x9A,
    "Down": 0x9B,
    "Delete": 0x9C,
}

# CPC keyboard matrix labels (10 rows x 8 columns), physical-key names as
# ported verbatim from KMAT_LABELS in amspirit-lite.html.
KMAT_LABELS = [
    ["F.Hau", "F.Dro", "F.Bas", "Pn.9", "Pn.6", "Pn.3", "Pn.En", "Pn.."],
    ["F.Gau", "Copy", "Pn.7", "Pn.8", "Pn.5", "Pn.1", "Pn.2", "Pn.0"],
    ["CLR", "[", "Enter", "]", "Pn.4", "SHIFT", "ç", "CTRL"],
    ['"', "=", "à", "P", "+", "*", "?", ">"],
    ["0", "9", "O", "I", "L", "K", "M", "<"],
    ["8", "7", "U", "Y", "H", "J", "N", "SPACE"],
    ["6", "5", "R", "T", "G", "F", "B", "V"],
    ["4", "3", "E", "W", "S", "D", "C", "X"],
    ["1", "2", "ESC", "Q", "TAB", "A", "CAPSL", "Z"],
    ["J.hau", "J.bas", "J.gau", "J.dro", "J.fir", "---", "---", "DEL"],
]


def parse_addr(text: str) -> int:
    """Accepts decimal or 0x-prefixed hex, as the server's own query parsing does."""
    text = text.strip()
    return int(text, 16) if text.lower().startswith("0x") else int(text, 10)


def parse_hex_bytes(text: str) -> bytes:
    """Tolerates spaces and ':' between byte pairs, like POST /api/ram's `data` field."""
    cleaned = "".join(c for c in text if c not in " \t\n\r:")
    if len(cleaned) % 2:
        raise ValueError("odd number of hex digits")
    return bytes.fromhex(cleaned)


def decode_cpc_float(b: bytes, o: int) -> str:
    """5-byte Locomotive BASIC float: bytes 0-3 mantissa LE, byte 4 biased exponent.

    Bit 7 of byte 3 is the sign; the mantissa's implied MSB is always 1.
    """
    exp = b[o + 4]
    if exp == 0:
        return "0"
    sign = -1 if (b[o + 3] & 0x80) else 1
    m32 = ((b[o + 3] | 0x80) * 16777216) + b[o + 2] * 65536 + b[o + 1] * 256 + b[o + 0]
    mantissa = m32 / 4294967296
    v = sign * mantissa * (2 ** (exp - 128))
    if v == 0:
        return "0"
    a = abs(v)
    if 0.001 <= a < 1e10:
        return repr(float(f"{v:.9g}"))
    return f"{v:.6e}"


def parse_basic_vars(chain_bytes: bytes, var_bytes: bytes, txttop: int) -> list[dict]:
    """Walk the 27 scalar-variable chains anchored at 0xADB7 (54 bytes, A-Z + FN).

    Node layout: [0-1] next offset LE (0 = end) | name suffix (ASCII, last byte
    bit7 set) | type byte (0x01=INT 0x02=STR 0x04=REAL 0x05=DEF FN) | data.
    Offset -> index in var_bytes is `offset - 1` (var_bytes starts at txttop).
    """
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    out: list[dict] = []
    visited: set[int] = set()
    for i in range(27):
        ptr = chain_bytes[i * 2] | (chain_bytes[i * 2 + 1] << 8)
        safety = 0
        while ptr != 0 and safety < 200:
            safety += 1
            if ptr in visited:
                break
            visited.add(ptr)
            rel = ptr - 1
            if rel < 0 or rel + 3 > len(var_bytes):
                break
            next_ptr = var_bytes[rel] | (var_bytes[rel + 1] << 8)
            pos = rel + 2
            name_chars = []
            while pos < len(var_bytes):
                ch = var_bytes[pos]
                pos += 1
                name_chars.append(chr(ch & 0x7F))
                if ch & 0x80:
                    break
            name = "".join(name_chars).replace("\x00", "")
            if pos >= len(var_bytes):
                break
            tc = var_bytes[pos]
            pos += 1
            type_name, value = str(tc), "?"
            rec_end = pos
            if tc == 0x01:
                type_name = "%"
                if pos + 1 < len(var_bytes):
                    raw = var_bytes[pos] | (var_bytes[pos + 1] << 8)
                    value = str(raw if raw < 32768 else raw - 65536)
                rec_end = pos + 2
            elif tc == 0x02:
                type_name = "$"
                if pos + 2 < len(var_bytes):
                    str_len = var_bytes[pos]
                    value = '""' if str_len == 0 else f'"…" len={str_len}'
                rec_end = pos + 3
            elif tc == 0x04:
                type_name = "!"
                if pos + 4 < len(var_bytes):
                    value = decode_cpc_float(var_bytes, pos)
                rec_end = pos + 5
            elif tc == 0x05:
                type_name, value = "DEF FN", "…"
            out.append({"name": name, "type": type_name, "value": value, "addr": ptr})
            ptr = next_ptr
    return out


_ARRAY_ELEM_SIZE = {0x01: 2, 0x02: 3, 0x04: 5}
_ARRAY_TYPE_NAME = {0x01: "%", 0x02: "$", 0x04: "!"}


def parse_basic_arrays(arr_bytes: bytes) -> list[dict]:
    """Walk the array zone (vartop..arrend): name | type | recSize(2) | ndims | dims | data."""
    out: list[dict] = []
    pos = 0
    n = len(arr_bytes)
    while pos < n:
        rec_start = pos
        name_chars = []
        while pos < n:
            ch = arr_bytes[pos]
            pos += 1
            name_chars.append(chr(ch & 0x7F))
            if ch & 0x80:
                break
        name = "".join(name_chars).replace("\x00", "")
        if not name or pos >= n:
            break
        type_pos = pos
        tc = arr_bytes[pos]
        pos += 1
        elem_sz = _ARRAY_ELEM_SIZE.get(tc)
        if not elem_sz or pos + 3 > n:
            break
        rec_size = arr_bytes[pos] | (arr_bytes[pos + 1] << 8)
        pos += 2
        if rec_size < 4 or pos >= n:
            break
        ndims = arr_bytes[pos]
        pos += 1
        if ndims < 1 or ndims > 3 or pos + ndims * 2 > n:
            break
        dims = []
        for _ in range(ndims):
            dims.append(arr_bytes[pos] | (arr_bytes[pos + 1] << 8))
            pos += 2
        total = 1
        for d in dims:
            total *= d
        elements = []
        for _ in range(total):
            if pos + elem_sz > n or len(elements) >= 512:
                break
            if tc == 0x01:
                raw = arr_bytes[pos] | (arr_bytes[pos + 1] << 8)
                elements.append(str(raw if raw < 32768 else raw - 65536))
            elif tc == 0x02:
                length = arr_bytes[pos]
                elements.append('""' if length == 0 else f'"…" len={length}')
            elif tc == 0x04:
                elements.append(decode_cpc_float(arr_bytes, pos))
            pos += elem_sz
        out.append(
            {
                "name": name,
                "type": _ARRAY_TYPE_NAME.get(tc, "?"),
                "dims": dims,
                "elements": elements,
                "addr": rec_start,
            }
        )
        next_pos = type_pos + rec_size
        if next_pos <= type_pos:
            break
        pos = next_pos
    return out
