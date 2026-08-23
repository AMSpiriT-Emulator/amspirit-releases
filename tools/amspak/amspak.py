#!/usr/bin/env python3
# =============================================================================
# amspak — AMSpiriT image-cartridge packer
#
# Embeds Amstrad CPC content (SNA / DSK / CDT / BAS / HFE / IPF) inside a PNG,
# PICO-8 style, so the file boots when dropped onto the emulator. Reference:
# doc/image-container.md.
#
# The media payload goes in one private `amSc` PNG chunk (TLV list, optional
# per-entry DEFLATE); the description + autotype metadata go in standard iTXt
# chunks with `amspirit:*` keywords. No third-party deps — stdlib zlib only.
#
# Usage:
#   amspak game.dsk --label cover.png --description "..." --run GAME -o cart.png
#   amspak game.dsk -o cart.png                       # minimal, autotype RUN"
#   amspak listing.bas --autotype 'RUN"\n' -o cart.png
#   amspak a.dsk b.dsk -o cart.png --boot 0           # multi-entry
#
# The autotype family mirrors the amspirit-lite launch flags:
#   --autorun            → auto-type RUN"↵
#   --run <name>         → auto-type RUN"<name>↵
#   --autotype <string>  → strict: type the literal string (\n = Enter)
# Precedence (last wins): --autorun < --run < --autotype.
# =============================================================================

import argparse
import os
import struct
import sys
import zlib

# media_type enum — keep in sync with amspirit_image_container.h
MT_SNA = 1
MT_DSK = 2
MT_CDT = 3
MT_BAS = 4
MT_FDC = 5

EXT_TO_TYPE = {
    ".sna": MT_SNA,
    ".dsk": MT_DSK,
    ".cdt": MT_CDT,
    ".bas": MT_BAS,
    ".hfe": MT_FDC,
    ".ipf": MT_FDC,
    ".raw": MT_FDC,  # CAPS
}

PNG_SIG = b"\x89PNG\r\n\x1a\n"


def media_type_for(path):
    ext = os.path.splitext(path)[1].lower()
    if ext not in EXT_TO_TYPE:
        sys.exit(f"amspak: unknown media extension '{ext}' for {path}")
    return EXT_TO_TYPE[ext]


def png_chunk(ctype: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(ctype + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + ctype + data + struct.pack(">I", crc)


def itxt_chunk(keyword: str, text: str) -> bytes:
    # iTXt, uncompressed, no language / translated keyword.
    body = keyword.encode("latin-1") + b"\x00" + b"\x00\x00" + b"\x00" + b"\x00" + text.encode("utf-8")
    return png_chunk(b"iTXt", body)


def build_amsc(entries, compress: bool, basic_inject: bool) -> bytes:
    flags = (0x01 if compress else 0) | (0x02 if basic_inject else 0)
    body = b"AMSP" + bytes([1, flags, len(entries), 0])
    for media_type, name, blob in entries:
        payload = zlib.compress(blob, 9) if compress else blob
        name_b = name.encode("utf-8")
        if len(name_b) > 255:
            name_b = name_b[:255]
        body += bytes([media_type, len(name_b)]) + name_b
        body += struct.pack(">I", len(payload)) + payload
    return png_chunk(b"amSc", body)


def minimal_png_1x1() -> bytes:
    # A valid 1×1 opaque black PNG, used when no --label cover image is given.
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)  # 1x1, 8-bit, truecolor
    raw = b"\x00\x00\x00\x00"  # filter byte + RGB
    idat = zlib.compress(raw, 9)
    return PNG_SIG + png_chunk(b"IHDR", ihdr) + png_chunk(b"IDAT", idat) + png_chunk(b"IEND", b"")


def split_png_chunks(blob: bytes):
    if blob[:8] != PNG_SIG:
        sys.exit("amspak: --label file is not a PNG")
    pos = 8
    chunks = []
    while pos + 8 <= len(blob):
        (length,) = struct.unpack(">I", blob[pos : pos + 4])
        ctype = blob[pos + 4 : pos + 8]
        data = blob[pos + 8 : pos + 8 + length]
        chunks.append((ctype, data))
        pos += 12 + length
        if ctype == b"IEND":
            break
    return chunks


def main():
    ap = argparse.ArgumentParser(description="Pack CPC media into a PNG image cartridge.")
    ap.add_argument("media", nargs="+", help="media file(s): .dsk .sna .cdt .bas .hfe .ipf")
    ap.add_argument("-o", "--output", required=True, help="output .png")
    ap.add_argument("--label", help="cover PNG to embed the payload into (default: 1×1)")
    ap.add_argument("--description", help="text shown in a popup at launch")
    ap.add_argument("--boot", type=int, default=None, help="0-based index of the entry to boot")
    ap.add_argument("--no-compress", action="store_true", help="store media uncompressed")
    ap.add_argument("--basic-inject", action="store_true",
                    help="for a .bas boot entry, use BASIC injection instead of autotype")
    grp = ap.add_argument_group("autotype (last wins)")
    grp.add_argument("--autorun", action="store_true", help='auto-type RUN"')
    grp.add_argument("--run", metavar="NAME", help='auto-type RUN"NAME')
    grp.add_argument("--autotype", metavar="STR", help="strict literal autotype (\\n = Enter)")
    args = ap.parse_args()

    entries = []
    for path in args.media:
        with open(path, "rb") as f:
            blob = f.read()
        entries.append((media_type_for(path), os.path.basename(path), blob))

    # Base image: the cover, or a 1×1 placeholder.
    if args.label:
        with open(args.label, "rb") as f:
            base = f.read()
        chunks = split_png_chunks(base)
    else:
        chunks = split_png_chunks(minimal_png_1x1())

    amsc = build_amsc(entries, compress=not args.no_compress, basic_inject=args.basic_inject)

    text_chunks = b""
    if args.description:
        text_chunks += itxt_chunk("amspirit:description", args.description)
    if args.boot is not None:
        text_chunks += itxt_chunk("amspirit:boot", str(args.boot))
    # Autotype family — emit in precedence order; the decoder resolves last-wins.
    if args.autorun:
        text_chunks += itxt_chunk("amspirit:autorun", "1")
    if args.run is not None:
        text_chunks += itxt_chunk("amspirit:run", args.run)
    if args.autotype is not None:
        text_chunks += itxt_chunk("amspirit:autotype", args.autotype)

    # Reassemble: signature, IHDR, our amSc + iTXt (after IHDR, before IEND),
    # then the rest of the original chunks (IDAT…, IEND).
    out = bytearray(PNG_SIG)
    inserted = False
    for ctype, data in chunks:
        if not inserted and ctype != b"IHDR":
            out += amsc + text_chunks
            inserted = True
        out += png_chunk(ctype, data)
    if not inserted:  # pathological: no chunks after IHDR
        out += amsc + text_chunks

    with open(args.output, "wb") as f:
        f.write(out)
    print(f"amspak: wrote {args.output} ({len(entries)} entr"
          f"{'y' if len(entries) == 1 else 'ies'}, {len(out)} bytes)")


if __name__ == "__main__":
    main()
