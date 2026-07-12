"""Small ASGI request-size guard for the public MCP endpoint."""

from __future__ import annotations

import json
from typing import Awaitable, Callable


_Receive = Callable[[], Awaitable[dict]]
_Send = Callable[[dict], Awaitable[None]]


class _RequestBodyTooLarge(Exception):
    pass


class MCPRequestBodyLimitMiddleware:
    """Reject oversized MCP requests before JSON-RPC parsing or tool dispatch."""

    def __init__(self, app, *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max(0, int(max_bytes))

    async def __call__(self, scope: dict, receive: _Receive, send: _Send) -> None:
        if (
            self.max_bytes <= 0
            or scope.get("type") != "http"
            or not str(scope.get("path", "")).startswith("/mcp")
            or str(scope.get("method", "GET")).upper() not in {"POST", "PUT", "PATCH"}
        ):
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        raw_length = headers.get(b"content-length", b"").decode("latin-1").strip()
        if raw_length:
            try:
                declared_length = int(raw_length)
            except ValueError:
                await self._send_json(send, 400, "invalid Content-Length")
                return
            if declared_length < 0:
                await self._send_json(send, 400, "invalid Content-Length")
                return
            if declared_length > self.max_bytes:
                await self._send_too_large(send)
                return

        received = 0
        response_started = False

        async def limited_receive() -> dict:
            nonlocal received
            message = await receive()
            if message.get("type") == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _RequestBodyTooLarge
            return message

        async def tracked_send(message: dict) -> None:
            nonlocal response_started
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except _RequestBodyTooLarge:
            if response_started:
                raise
            await self._send_too_large(send)

    async def _send_too_large(self, send: _Send) -> None:
        await self._send_json(
            send,
            413,
            f"MCP request body exceeds {self.max_bytes} bytes",
        )

    @staticmethod
    async def _send_json(send: _Send, status: int, error: str) -> None:
        body = json.dumps({"error": error}, separators=(",", ":")).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body, "more_body": False})
