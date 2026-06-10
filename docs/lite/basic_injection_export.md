# AMSpiriT-Lite — BASIC Injection and Export

Files: `amspirit-helpers/inc/amspirit_basic.h`, `amspirit-helpers/src/amspirit_basic.cpp`

## Overview

AMSpiriT provides two-way BASIC program handling:

1. **BASIC Injection** — Tokenize ASCII BASIC source and write it directly into CPC RAM, bypassing disk/cassette loading
2. **BASIC Export** — Read a BASIC program from RAM, detokenize it, and export as readable ASCII source

This enables rapid development, debugging, and archival of Locomotive BASIC programs.

---

## BASIC Injection

### Purpose

Instead of creating a DSK file or using cassette images, developers and users can paste Locomotive BASIC code directly into the emulator. The code is tokenized server-side and written into the CPC's RAM at the standard address (`0x0170`), with automatic pointer updates.

### Source Format

BASIC programs must be in text format with:
- **Line numbers mandatory** — each statement starts with a line number (10, 20, etc.)
- **One statement per line** (statements can be concatenated with `:`)
- **Standard Locomotive BASIC keywords** (6128 superset)

Example:

```basic
10 MODE 1
20 INK 0,0:INK 1,26:INK 2,1
30 LOCATE 1,1
40 PRINT "HELLO FROM AMSPIRIT"
50 PRINT "Line 50"
60 GOTO 40
```

### Supported Keywords and Functions

The tokenizer supports all Locomotive BASIC keywords from the CPC 6128, including:

**Flow Control**: `IF`, `THEN`, `ELSE`, `GOTO`, `GOSUB`, `RETURN`, `FOR`, `NEXT`, `WHILE`, `WEND`, `REPEAT`, `UNTIL`, `EXIT`, `CALL`

**I/O**: `PRINT`, `INPUT`, `LINE INPUT`, `OPEN`, `CLOSE`, `LOAD`, `SAVE`, `BSAVE`, `BLOAD`, `CLS`, `LOCATE`

**Graphics**: `MODE`, `DRAW`, `FILL`, `PLOT`, `CIRCLE`, `PAINT`, `XDRAW`, `MOVE`, `WINDOW`

**Sound**: `SOUND`, `PLAY`, `ENVELOPE`

**Memory**: `POKE`, `DOKE`, `PEEK`, `DEEK`, `HIMEM`, `CLEAR`

**Colors**: `INK`, `PAPER`, `BORDER`, `PALETTE`

**Disk**: `DISC`, `CAT`, `RUN` (with filename)

**Functions**: `ABS`, `ASC`, `ATN`, `CHR$`, `COS`, `EXP`, `FIX`, `INT`, `LEN`, `LOG`, `MAX`, `MID$`, `MIN`, `PEEK`, `RND`, `SGN`, `SIN`, `SQR`, `STR$`, `TAN`, `VAL`, `UPPER$`, `LOWER$`, etc.

**Operators**: `+`, `-`, `*`, `/`, `MOD`, `AND`, `OR`, `XOR`, `NOT`, `=`, `<>`, `<`, `>`, `<=`, `>=`

### Methods

#### Command Line (SDL2)

```bash
amspirit-lite-sdl --basic myprogram.bas
```

The program is injected ~3 seconds after boot (allowing BASIC to initialize). Type `RUN` in the emulator to execute it.

#### Web Interface (Built-in HTML)

1. Click the **BASIC** tab
2. Paste or load your program source
3. Click **Inject**
4. Type `RUN` or `LIST` in the emulator

#### Web API

```bash
curl -X POST http://127.0.0.1:8765/api/basic \
     -H 'Content-Type: text/plain' \
     --data-binary @myprogram.bas
```

Optional query parameters:

| Parameter | Effect |
|---|---|
| `?reset=1` | Hard-reset before injection (clears all variables) |
| `?run=1` | Auto-type `RUN` after injection (starts the program immediately) |

Example: inject and auto-run:

```bash
curl -X POST 'http://127.0.0.1:8765/api/basic?run=1' \
     -H 'Content-Type: text/plain' \
     --data-binary '10 PRINT "HELLO"\n20 GOTO 10'
```

### Injection Process

1. **Tokenization**: ASCII source → token stream (4–6 bytes per token)
2. **Address calculation**: Starting at `0x0170` (standard Locomotive BASIC start)
3. **Pointer update**: Update end-of-program marker at `0xAE66` (464) or `0xAE68` (6128+)
4. **Flag clearing**: Clear `AUTO`, `ERR`, and `PROTECT` flags
5. **Validation**: Ensure program doesn't exceed RAM limits

### Size Limits

| Model | Max Size |
|---|---|
| **CPC 464** | `0x0170` to `0xAE85` (~44 KB) |
| **CPC 664 / 6128** | `0x0170` to `0xAE68` (~44 KB) |

If a program exceeds the limit, the title bar shows: `BASIC inject failed: program too large`

### Feedback

After injection, the title bar confirms:

- **Success**: `BASIC injected — type LIST or RUN`
- **Failure**: `BASIC inject failed: <reason>`

---

## BASIC Export

### Purpose

Read the currently loaded BASIC program from the emulated CPC's RAM and export it as readable ASCII source code. This enables:
- Preserving programs created in-emulator
- Archival of games and demos
- Debugging via source inspection

### Detokenization

The export process reverses tokenization:

1. **Token stream reading**: Start at `0x0170`, read line by line
2. **Token interpretation**: Convert each token back to ASCII keyword/symbol
3. **Formatting**: Reconstruct readable source with proper spacing

### Methods

#### Web Interface

1. Click the **BASIC** tab
2. Click **Export**
3. The program appears in the editor or is downloaded as `.bas`

#### Web API

```bash
# Export and save to a file
curl http://127.0.0.1:8765/api/basic_export > exported.bas

# Verbose output (extra whitespace for readability)
curl 'http://127.0.0.1:8765/api/basic_export?verbose=1' > exported_readable.bas
```

#### Check BASIC State

```bash
curl http://127.0.0.1:8765/api/basic_state
```

Response:

```json
{
  "loaded": true,
  "size": 2048,
  "lines": 42
}
```

| Field | Description |
|---|---|
| `loaded` | `true` if a BASIC program is in RAM |
| `size` | Size in bytes |
| `lines` | Number of BASIC lines |

### Query Parameters

#### `verbose=1`

Adds extra formatting for readability:

**Without `verbose`**:
```basic
10 PRINT "HELLO"
20 GOTO 10
```

**With `verbose=1`**:
```basic
10 PRINT "HELLO"
20 GOTO 10
```

(The difference is primarily internal spacing in complex expressions.)

---

## Workflow Examples

### Example 1: Develop and Archive a Program

```bash
# 1. Boot the emulator with web interface
amspirit-lite-sdl --web-server --no-splash &

# 2. Inject a BASIC program
curl -X POST 'http://127.0.0.1:8765/api/basic?run=1' \
     -H 'Content-Type: text/plain' \
     --data-binary <<'EOF'
10 MODE 1
20 BORDER 0
30 FOR I=0 TO 15
40 INK I,I
50 NEXT I
60 LOCATE 1,1
70 PRINT "Palette test"
80 END
EOF

# 3. After testing, export the program
curl http://127.0.0.1:8765/api/basic_export > palette_test.bas

# 4. Archive
cp palette_test.bas ~/amspirit_programs/
```

### Example 2: Rapid Development Loop

Using a Makefile:

```makefile
DEV_SERVER := http://127.0.0.1:8765

# Auto-tokenize and run
dev-inject:
	curl -X POST '$(DEV_SERVER)/api/basic?run=1' \
	     -H 'Content-Type: text/plain' \
	     --data-binary @src/game.bas

# Check state
dev-state:
	curl $(DEV_SERVER)/api/basic_state | jq '.'

# Export for backup
dev-export:
	curl $(DEV_SERVER)/api/basic_export > backup/game_$(shell date +%s).bas
```

### Example 3: CI Pipeline

```bash
#!/bin/bash
# test_basic.sh — regression test a BASIC program

SERVER="http://127.0.0.1:8765"

# Launch emulator with web server
amspirit-lite-sdl --web-server --no-splash &
EMU_PID=$!
sleep 2

# Inject test program
curl -sf -X POST "$SERVER/api/basic?run=1" \
     -H 'Content-Type: text/plain' \
     --data-binary @tests/test.bas || { kill $EMU_PID; exit 1; }

# Wait for script to complete (via web API or polling)
sleep 5

# Export result for inspection
curl -sf "$SERVER/api/basic_export" > test_output.bas

# Check for expected output
if grep -q "PASS" test_output.bas; then
    echo "TEST PASSED"
    kill $EMU_PID
    exit 0
else
    echo "TEST FAILED"
    kill $EMU_PID
    exit 1
fi
```

---

## Technical Details

### Token Format

Locomotive BASIC tokens are single bytes or multi-byte sequences:

- **0x00–0x7F**: Single-byte tokens (keywords, operators)
- **0x80–0xFF**: Multi-byte sequences (extended tokens, symbols)

For example:
- `0x9E` = `PRINT`
- `0xAC` = `NEXT`
- Space, digits, and punctuation are stored as ASCII

### RAM Addresses

| Address | Purpose |
|---|---|
| `0x0170` | Start of BASIC program |
| `0xAC01` | `AUTO` flag (464) |
| `0xAD90` | `ERR` flag |
| `0xAE2C` | `PROTECT` flag |
| `0xAE68` (464) / `0xAE85` (6128) | **TXTTOP** — start of free memory |

When a program is injected, **TXTTOP** is updated to point immediately after the program, and the three flags are cleared.

### Detokenization Challenges

Some edge cases in detokenization:

1. **Binary data in strings**: If a string contains raw bytes that look like tokens, they are correctly preserved as literal characters
2. **Line continuation**: CPC BASIC does not support line continuation; long lines are stored as single tokens
3. **Comments**: Comments (`REM`) are tokenized and stored; they round-trip correctly
4. **Special characters**: String delimiters, operators, and punctuation are preserved exactly

---

## Known Limitations

- **No structure preservation**: Injected programs start fresh (no variables preserved from before)
- **No syntax checking**: The tokenizer doesn't validate semantic correctness (type mismatches, undefined functions, etc.); errors appear at runtime
- **Drive B ignored**: Programs can be loaded from either drive, but only drive A is supported
- **Implicit END**: If a program has no `END` statement, execution continues to the next line or stops (same as on real CPC)
- **ROM language**: The tokenizer always uses the 6128 ROM token set; some obscure extensions (e.g., CPC Plus-only keywords) may not be supported

---

## Examples of Complete Programs

### Hello World

```basic
10 CLS
20 PRINT "HELLO, WORLD!"
30 END
```

### Simple Calculator

```basic
10 MODE 1
20 CLS
30 INPUT "Enter first number: ";A
40 INPUT "Enter second number: ";B
50 INPUT "Enter operation (+,-,*,/): ";O$
60 IF O$="+" THEN C=A+B
70 IF O$="-" THEN C=A-B
80 IF O$="*" THEN C=A*B
90 IF O$="/" THEN C=A/B
100 PRINT "Result: ";C
110 END
```

### Graphics Test

```basic
10 MODE 1
20 BORDER 0
30 INK 0,0:INK 1,26:INK 2,1:INK 3,20
40 FILL 1,1,1
50 CIRCLE 80,100,50
60 PLOT 200,100
70 DRAW 300,200
80 LOCATE 1,20
90 PRINT "Graphics test complete"
100 END
```

---

## Debugging

### Check what's in RAM

```bash
# Get the raw bytes
curl 'http://127.0.0.1:8765/api/ram?addr=0x0170&len=256' | jq '.hex'

# Detokenize manually
curl http://127.0.0.1:8765/api/basic_export
```

### Re-export with verbose formatting

```bash
curl 'http://127.0.0.1:8765/api/basic_export?verbose=1'
```
