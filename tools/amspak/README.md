# amspak — AMSpiriT image cartridge packager

`amspak.py` embeds Amstrad CPC content (SNA / DSK / CDT / BAS / HFE /
IPF) inside a PNG, similar to PICO-8 : the resulting file behaves like
a normal image, but launches directly when dragged into the AMSpiriT
emulator.

The media is stored in a private PNG chunk `amSc` (a TLV list with
optional DEFLATE compression per entry); the description and autotype
metadata are stored in standard `iTXt` chunks prefixed `amspirit:*`. The
script depends on no external libraries (only `zlib` from the Python stdlib).

See also `doc/image-container.md` for the detailed binary format.

## Requirements

- Python 3 (no external dependencies).

## Usage

```bash
amspak.py <media...> -o output.png [options]
```

| Option | Purpose |
|---|---|
| `<media...>` | One or more `.dsk`, `.sna`, `.cdt`, `.bas`, `.hfe`, `.ipf` files to embed |
| `-o`, `--output` | Output PNG file (required) |
| `--label` | Cover image to inject the payload into (default: 1×1 black pixel) |
| `--description` | Text displayed in a popup on launch |
| `--boot` | Index (0-based) of the entry to start, if multiple media files are provided |
| `--no-compress` | Store media without compression |
| `--basic-inject` | For a boot `.bas` entry, use direct BASIC injection instead of keyboard autotype |

### Autotype family (last option wins)

| Option | Effect |
|---|---|
| `--autorun` | Automatically types `RUN"` + Enter |
| `--run <name>` | Automatically types `RUN"<name>` + Enter |
| `--autotype <text>` | Literally types `<text>` (`\n` = Enter) |

Priority: `--autorun` < `--run` < `--autotype`.

## Example: package `labyrinth.bas`

The `examples/` folder in the repository contains a small BASIC demo
program, `labyrinth.bas`, as well as a cover image `labyrinth.png` to
use as the cartridge jacket.

```bash
python3 amspak.py \
    --basic-inject ../../examples/labyrinth.bas \
    --label ../../examples/labyrinth.png \
    --description "Labyrinth - demo BASIC" \
    --autorun \
    -o labyrinth_cart.png
```

What happens:

1. `labyrinth.bas` is read and stored (compressed) in the `amSc` chunk of
   the output PNG, with the media type `BAS`.
2. `labyrinth.png` serves as the visible image for the cartridge (instead of
   the default 1×1 pixel) — this is the jacket visible in the game
   selector.
3. The description `"Labyrinth - demo BASIC"` is added as `iTXt` and
   will be displayed in a popup on load.
4. `--autorun` adds the metadata that automatically types `RUN"` + Enter
   on startup, which launches the embedded BASIC listing without manual
   intervention.

The resulting `labyrinth_cart.png` file is a valid PNG image (viewable
in any image viewer), but it can also be loaded into AMSpiriT: the
emulator detects the `amSc` chunk, extracts `labyrinth.bas`, injects it
into memory, then automatically types `RUN"` to launch the program.

### Verify the result

```bash
python3 amspak.py ../../examples/labyrinth.bas -o test.png
```

produces a minimal cartridge (1×1 jacket, no description, no autotype) —
useful for a quick test without a cover image.
