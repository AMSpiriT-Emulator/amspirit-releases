"""SSE client for AMSpiriT Lite's `GET /api/events` push stream.

Mirrors amspirit-lite.html's `sseStart()`: a single persistent connection
delivers `frame` (~5 Hz), `z80_bp`, `basic_bp`, `pause`, and `reset` events,
which the GUI uses to drive the same refreshes a poll timer would -- but the
moment something happens, not on the next tick. Reconnects with the same
2s -> 30s capped backoff on failure.

No Tkinter import here on purpose, same reasoning as api_client.py: this
runs entirely on a background thread and only ever touches the queue.
"""

from __future__ import annotations

import json
import queue
import threading
import urllib.request
from typing import Callable


class SseClient:
    """Runs the SSE read loop on a background thread.

    Results land in a queue as (topic, data, error) tuples for the Tk thread
    to drain -- same split as PollingManager. Two synthetic topics report
    connection state: "__open__" (stream established) and "__error__"
    (data is None, error is the exception).
    """

    def __init__(self, get_base_url: Callable[[], str]):
        # A callable, not a fixed URL, so a Host/Port change picked up by
        # reconnect() always dials wherever the connection bar points now.
        self._get_base_url = get_base_url
        self._queue: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._redial = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def reconnect(self):
        """Drop the current connection (if any) and redial immediately."""
        self._redial.set()

    def stop(self):
        self._stop.set()
        self._redial.set()

    def drain(self) -> list[tuple[str, dict | None, BaseException | None]]:
        events = []
        try:
            while True:
                events.append(self._queue.get_nowait())
        except queue.Empty:
            pass
        return events

    # -- background thread ---------------------------------------------------

    def _run(self):
        backoff = 2.0
        while not self._stop.is_set():
            self._redial.clear()
            try:
                self._read_stream()
                backoff = 2.0  # a clean stream close is not a failure
            except Exception as e:  # noqa: BLE001 - surfaced as a connection error
                self._queue.put(("__error__", None, e))
                if self._redial.wait(backoff):
                    continue
                backoff = min(backoff * 2, 30.0)

    def _read_stream(self):
        url = self._get_base_url() + "/api/events"
        req = urllib.request.Request(url, headers={"Accept": "text/event-stream"})
        # No read timeout: the server sends a ": ping" heartbeat every 15s,
        # so a stalled connection is detected by its absence rather than by
        # a fixed deadline that would otherwise force spurious reconnects.
        with urllib.request.urlopen(req) as resp:
            self._queue.put(("__open__", None, None))
            event_name = None
            data_lines: list[str] = []
            for raw_line in resp:
                if self._stop.is_set() or self._redial.is_set():
                    return
                line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
                if line.startswith(":"):
                    continue  # heartbeat / comment line
                if not line:
                    if event_name and data_lines:
                        self._dispatch(event_name, "\n".join(data_lines))
                    event_name, data_lines = None, []
                    continue
                if line.startswith("event:"):
                    event_name = line[len("event:"):].strip()
                elif line.startswith("data:"):
                    data_lines.append(line[len("data:"):].strip())
        raise ConnectionError("SSE stream closed by server")

    def _dispatch(self, event_name: str, data_text: str):
        try:
            data = json.loads(data_text) if data_text else {}
        except json.JSONDecodeError:
            return
        self._queue.put((event_name, data, None))
