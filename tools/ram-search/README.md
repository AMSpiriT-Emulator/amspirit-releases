# AMSpiriT — RAM Search

A single self-contained HTML page (`amspirit-ram-search.html`) that implements
the classic "Cheat Engine"-style memory search against a running AMSpiriT
emulator, using its embedded web debug server as the backend. Open the file
directly in a browser — no build step, no server of its own.

## How it works

1. **Start a search.** Pick a value size (byte/word/dword), an address range,
   and whether you know the value you're looking for or not. The page reads
   the full 64K RAM snapshot from the emulator and keeps every address that
   could hold the value (all of them, if unknown).
2. **Play a bit, then filter.** Do something in the game that changes the
   value you're hunting (lose a life, score a point…), pick the matching
   filter (changed / increased / decreased / exact value / etc.) and hit
   *Scan again*. Repeat — the candidate list shrinks each round.
3. **Confirm and act.** Once few enough addresses remain, they're listed with
   their base/current/delta values. You can write a new value to any address
   ("Write") or lock it so it's continuously rewritten every 150 ms
   ("Freeze") — handy for infinite lives/health.

## Main options

- **Value size** — 1/2/4 bytes, little-endian.
- **Bank** — `0` for central RAM, `1..N` for extended RAM pages.
- **View** — `raw` (physical RAM) or `cpu` (post-banking, as the Z80 sees it
  through the current ROM/RAM configuration).
- **Range** — restrict the scan to a sub-range of the 64K address space to
  skip ROM/system variables and speed up narrowing.
- **Initial value** — start from *every* address (unknown value) or seed the
  search with a known exact value.
- **Live values** — poll the candidate list every second without doing a
  full filtering scan, just to watch values move in real time.

## Connecting to the emulator

The page talks to the emulator's `--web-server` debug API. By default it
targets `127.0.0.1:8765`. If it can't connect (wrong host, custom port, or
the emulator running on another machine on the network), use the **Server**
field to point it at a different `host:port` and click **Connect** — the
address is remembered in the browser for next time.

See `src/doc/web_server_api.md` in the main repository for the API this page
relies on.
