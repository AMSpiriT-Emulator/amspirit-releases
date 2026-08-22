"""HTTP client for AMSpiriT Lite's embedded debug server.

No Tkinter import here on purpose -- this module is reusable/testable on its
own, the same way cpc-validation's cpc-runner-amspirit keeps its HTTP helpers
free of anything specific to the caller. stdlib only (urllib.request), no
`requests` dependency -- consistent with that runner and with cpc-validation's
own minimal-dependency policy.

Endpoint reference: amspirit-lite/src/doc/web_server_api.md
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field


class AmspiritApiError(RuntimeError):
    """A non-2xx response, or one flagged as an error by the server itself.

    The server's contract (web_server_api.md): a 200 always means the request
    was applied; anything it can't act on comes back 400 with a machine
    readable body {"error": "...", "field": "..."} -- never a false 200.
    """

    def __init__(self, status: int, error: str, field_name: str | None = None):
        self.status = status
        self.error = error
        self.field = field_name
        msg = f'{error} (field: {field_name})' if field_name else error
        super().__init__(f"HTTP {status}: {msg}")


class AmspiritConnectionError(RuntimeError):
    """Server unreachable (connection refused/timed out/DNS failure)."""


@dataclass
class ApiResponse:
    status: int
    headers: dict = field(default_factory=dict)
    body: bytes = b""

    def json(self) -> dict:
        return json.loads(self.body) if self.body else {}


def compact_json(obj) -> bytes:
    """Serialise WITHOUT a space after ':'.

    Required for older builds whose hand-rolled JSON body scanner predates
    the whitespace-skipping fix (see cpc-runner-amspirit's compact_json
    docstring for the history) -- Python's default json.dumps emits a space
    after every colon, which used to read back as an empty string field on
    those builds while still answering 200. Cheap to keep emitting compact
    JSON for every released build's benefit.
    """
    return json.dumps(obj, separators=(",", ":")).encode()


class AmspiritClient:
    """Thin wrapper over the debug HTTP API.

    Every method may raise AmspiritApiError (a non-2xx response) or
    AmspiritConnectionError (server unreachable) -- callers decide how to
    surface those to the GUI (typically: a status label, never a crash).
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8765, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.timeout = timeout

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def request(
        self,
        method: str,
        path: str,
        body: bytes | None = None,
        content_type: str | None = None,
    ) -> ApiResponse:
        req = urllib.request.Request(self.base_url + path, data=body, method=method)
        if body is not None and content_type:
            req.add_header("Content-Type", content_type)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return ApiResponse(resp.status, dict(resp.headers), resp.read())
        except urllib.error.HTTPError as e:
            raw = e.read()
            error, field_name = _parse_error_body(raw)
            raise AmspiritApiError(e.code, error, field_name) from None
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
            raise AmspiritConnectionError(str(e)) from e

    # -- JSON convenience wrappers -------------------------------------------

    def get(self, path: str) -> dict:
        return self.request("GET", path).json()

    def post(self, path: str, body: dict | None = None) -> dict:
        data = compact_json(body) if body is not None else b""
        return self.request("POST", path, data, "application/json" if body is not None else None).json()

    def post_text(self, path: str, text: str) -> dict:
        return self.request("POST", path, text.encode("utf-8"), "text/plain").json()

    def post_empty(self, path: str) -> dict:
        return self.request("POST", path).json()

    def delete(self, path: str) -> dict:
        return self.request("DELETE", path).json()

    # -- raw (binary) responses ----------------------------------------------

    def get_raw(self, path: str) -> ApiResponse:
        return self.request("GET", path)

    def post_raw(self, path: str, data: bytes, content_type: str) -> ApiResponse:
        return self.request("POST", path, data, content_type)


def _parse_error_body(raw: bytes) -> tuple[str, str | None]:
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data.get("error", raw.decode(errors="replace")), data.get("field")
    except (json.JSONDecodeError, UnicodeDecodeError):
        pass
    return raw.decode(errors="replace") or "unknown error", None
