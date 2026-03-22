from __future__ import annotations

import json
import sys
from typing import Any


class JsonRpcError(RuntimeError):
    def __init__(self, code: int, message: str, data: Any | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


_use_headers: bool | None = None


def read_message() -> dict[str, Any] | None:
    global _use_headers
    line = sys.stdin.buffer.readline()
    if not line:
        return None
    decoded = line.decode("utf-8").strip()
    if not decoded:
        return read_message()

    # First non-empty line decides the framing for the whole session.
    # Starts with '{' → newline-delimited JSON (Claude Desktop).
    # Otherwise → Content-Length headers (Codex / LSP-style).
    if _use_headers is None:
        _use_headers = not decoded.startswith("{")

    if not _use_headers:
        return json.loads(decoded)

    # LSP-style: parse headers until blank line, then read payload.
    headers: dict[str, str] = {}
    while True:
        if ":" in decoded:
            name, value = decoded.split(":", 1)
            headers[name.lower().strip()] = value.strip()
        # Read next header line.
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        decoded = line.decode("utf-8").strip()
        if not decoded:
            break

    content_length = headers.get("content-length")
    if content_length is None:
        raise JsonRpcError(-32700, "Missing Content-Length header.")
    payload = sys.stdin.buffer.read(int(content_length))
    if not payload:
        return None
    return json.loads(payload.decode("utf-8"))


def write_message(message: dict[str, Any]) -> None:
    encoded = json.dumps(message, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if _use_headers:
        sys.stdout.buffer.write(f"Content-Length: {len(encoded)}\r\n\r\n".encode("ascii"))
        sys.stdout.buffer.write(encoded)
    else:
        sys.stdout.buffer.write(encoded)
        sys.stdout.buffer.write(b"\n")
    sys.stdout.buffer.flush()

