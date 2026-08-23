"""Change Flash for tk.Text: emphasise what just changed, then fade it back.

See CONTEXT.md. Without this, a 256-byte hex dump refreshing five times a
second shows everything and communicates nothing -- the eye has no way to
find the two bytes that moved. With it, the dump becomes an observer.

The fade is the point, not decoration. A binary highlight at 5 Hz leaves an
active region (the stack, a screen buffer) permanently lit, which is the same
as not highlighting at all. Decaying over ~0.7s means a byte that changed once
stands out and a byte that changes constantly settles into a steady glow.

Implemented as N tags of decreasing intensity plus a timer that demotes each
range one level per step. Tags, not per-character rewrites, so a flash costs
nothing to maintain and disappears on its own.
"""

from __future__ import annotations

import tkinter as tk


def _lerp_hex(hot: str, cold: str, t: float) -> str:
    """Blend two #rrggbb colours, t=0 -> hot, t=1 -> cold."""
    h = [int(hot[i:i + 2], 16) for i in (1, 3, 5)]
    c = [int(cold[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(a + (b - a) * t):02x}" for a, b in zip(h, c))


class DecayingFlash:
    """Fading emphasis over ranges of one Text widget."""

    def __init__(self, text: tk.Text, hot: str, cold: str, levels: int = 6,
                 step_ms: int = 120):
        self._text = text
        self._step_ms = step_ms
        self._tags = [f"flash{i}" for i in range(levels)]
        for i, tag in enumerate(self._tags):
            # Level 0 is the hot colour; the last level is one step short of
            # `cold`, so a range always reaches normal by being *untagged*
            # rather than by fading into an indistinguishable tag.
            text.tag_configure(tag, foreground=_lerp_hex(hot, cold, i / levels))
        # Flashes must win over any other tag on the same characters.
        for tag in self._tags:
            text.tag_raise(tag)
        self._running = False

    def flash(self, start: str, end: str):
        """Mark a range as just-changed, at full intensity."""
        for tag in self._tags:
            self._text.tag_remove(tag, start, end)
        self._text.tag_add(self._tags[0], start, end)
        if not self._running:
            self._running = True
            self._text.after(self._step_ms, self._decay)

    def clear(self):
        for tag in self._tags:
            self._text.tag_remove(tag, "1.0", tk.END)

    def _decay(self):
        try:
            alive = self._demote()
        except tk.TclError:
            return  # widget destroyed
        self._running = alive
        if alive:
            self._text.after(self._step_ms, self._decay)

    def _demote(self) -> bool:
        """Move every tagged range down one intensity level; drop the coldest.

        Walked from the coldest level up, so each level is emptied before the
        one above it is poured into it -- otherwise a range would cascade
        through every level in a single step and vanish immediately.
        """
        alive = False
        for i in range(len(self._tags) - 1, -1, -1):
            ranges = self._text.tag_ranges(self._tags[i])
            if not ranges:
                continue
            self._text.tag_remove(self._tags[i], "1.0", tk.END)
            if i + 1 < len(self._tags):
                for start, end in zip(ranges[0::2], ranges[1::2]):
                    self._text.tag_add(self._tags[i + 1], start, end)
                alive = True
        return alive
