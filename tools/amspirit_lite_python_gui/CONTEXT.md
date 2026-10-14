# Context — AMSpiriT Lite Debug GUI

Glossary for the Python/Tkinter debug GUI. Terms only: no implementation
details, no decisions, no roadmap.

## Demonstrator

What this GUI *is*. It exists to show what `amspirit-lite`'s REST/SSE debug
API makes possible, and to look and feel like a sibling of the HTML debug
page. It is not a complete debugging application, and completeness is not a
goal it is measured against. When a choice pits exhaustive coverage against
a clear demonstration of the API, the demonstration wins.

Contrast with the **HTML page** (`examples/amspirit-lite.html`), which is the
reference frontend: broader in scope, multilingual, and the place where a
feature appears first. The Demonstrator should *recall* it, not match it.

## Panel

One coherent view of some emulator state — the register grid, the RAM dump,
the BASIC listing, the keyboard matrix. A Panel is the unit that refreshes:
it has exactly one **Refresh Regime**, and it is the thing that is or is not
**Visible**.

A Panel is not the same as a tab. A tab may hold several Panels, and a Panel
may live several levels deep inside nested tabs.

## Visible

A Panel is Visible when every tab on the path from the window to that Panel
is the selected one. A Panel nested two levels deep inside an unselected
top-level tab is not Visible, even though its widgets exist.

Visibility is the gate on all network traffic: a Panel that is not Visible
issues no requests.

## Refresh Regime

How a Panel obtains its data. Every Panel has exactly one, named A, B or C.

- **Regime A — on wake.** The Panel fetches once, at the moment it becomes
  Visible, and then stays as it is until something **Invalidates** it. For
  state that does not change on its own while you watch it.

- **Regime B — polled while visible.** The Panel re-fetches on its own clock
  for as long as it is Visible. Reserved for state that changes without the
  emulator announcing it — the fallback when no **Push Event** covers it.

- **Regime C — pushed.** The Panel refreshes when the emulator says something
  changed, rather than on a clock of its own. For state that tracks
  execution. A Regime C Panel also refreshes on the **Pause Tick**, so that
  pausing the emulator does not silently freeze it.

## Push Event

Something the emulator announces the moment it happens, rather than
something a client discovers by asking. Drives **Regime C**.

Push Events are a fixed set defined by the API, and it is a meaningful fact
about a Panel that no Push Event covers its state — that is precisely what
forces it into **Regime B**.

## Pause Tick

The slow beat that keeps **Regime C** alive while the emulator is paused.
While paused the emulator announces nothing, but its state can still change
under single-stepping, timelapse navigation, and direct memory writes — so a
paused Panel is not a still Panel.

## Invalidation

An event that makes every Visible Panel's data untrustworthy at once,
regardless of its **Refresh Regime**, and forces a re-fetch. Distinct from a
Panel's own refresh, which concerns one Panel and its own state.

## Parameterised Action

A command the user issues with an argument — jump the RAM window to an
address, load a program from a file, insert a disc. Not a **Refresh**, even
when it results in new data appearing: there is nothing to refresh until the
user has said what they want.

The distinction matters because Refresh controls disappear as Panels become
live, and Parameterised Actions do not.

## Change Flash

Momentary emphasis on a value that just changed, fading back to normal. What
makes a densely-packed live Panel readable: without it, a grid of hex bytes
updating several times a second shows everything and communicates nothing.
