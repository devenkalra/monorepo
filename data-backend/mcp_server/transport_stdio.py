"""Stdio transport for the bldrdojo MCP scaffold.

Implements a minimal MCP-compatible JSON-RPC server over stdio using
Content-Length framed messages.
"""

from __future__ import annotations

import json
import sys
import traceback
from dataclasses import dataclass
from typing import Any

from mcp_server.server import BldrdojoMcpServer


@dataclass
class StdioMcpTransport:
    server: BldrdojoMcpServer
    protocol_version: str = "2024-11-05"
    server_name: str = "bldrdojo-data-backend"
    server_version: str = "0.1.0"

    def run(self) -> None:
        while True:
            message = self._read_message()
            if message is None:
                break

            response = self._handle_request(message)
            if response is not None:
                self._write_message(response)

    def _handle_request(self, request: dict[str, Any]) -> dict[str, Any] | None:
        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {})

        if not method:
            return self._error_response(request_id, -32600, "Invalid Request")

        try:
            if method == "initialize":
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": self.protocol_version,
                        "capabilities": {
                            "tools": {
                                "listChanged": False,
                            }
                        },
                        "serverInfo": {
                            "name": self.server_name,
                            "version": self.server_version,
                        },
                    },
                }

            if method == "notifications/initialized":
                return None

            if method == "ping":
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {},
                }

            if method == "tools/list":
                tools = self.server.list_tools()
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {"tools": tools},
                }

            if method == "tools/call":
                tool_name = params.get("name")
                arguments = params.get("arguments", {})
                session_id = self._extract_session_id(params)

                if not tool_name:
                    return self._error_response(request_id, -32602, "Missing tool name")

                result = self.server.call_tool(tool_name, arguments=arguments, session_id=session_id)
                text = json.dumps(result, ensure_ascii=True)

                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [{"type": "text", "text": text}],
                        "structuredContent": result,
                        "isError": not bool(result.get("ok", False)),
                    },
                }

            return self._error_response(request_id, -32601, f"Method not found: {method}")
        except Exception as exc:  # pragma: no cover - defensive guard
            details = {
                "message": str(exc),
                "traceback": traceback.format_exc(),
            }
            return self._error_response(request_id, -32603, "Internal error", details)

    @staticmethod
    def _extract_session_id(params: dict[str, Any]) -> str:
        if not isinstance(params, dict):
            return "default"
        if isinstance(params.get("session_id"), str):
            return params["session_id"]
        meta = params.get("_meta")
        if isinstance(meta, dict) and isinstance(meta.get("session_id"), str):
            return meta["session_id"]
        return "default"

    @staticmethod
    def _error_response(request_id: Any, code: int, message: str, data: Any | None = None) -> dict[str, Any]:
        err: dict[str, Any] = {
            "code": code,
            "message": message,
        }
        if data is not None:
            err["data"] = data
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": err,
        }

    @staticmethod
    def _read_message() -> dict[str, Any] | None:
        headers: dict[str, str] = {}

        while True:
            line = sys.stdin.buffer.readline()
            if not line:
                return None
            if line in (b"\r\n", b"\n"):
                break
            decoded = line.decode("utf-8").strip()
            if ":" in decoded:
                key, value = decoded.split(":", 1)
                headers[key.strip().lower()] = value.strip()

        content_length = int(headers.get("content-length", "0"))
        if content_length <= 0:
            return None

        raw = sys.stdin.buffer.read(content_length)
        if not raw:
            return None
        return json.loads(raw.decode("utf-8"))

    @staticmethod
    def _write_message(message: dict[str, Any]) -> None:
        payload = json.dumps(message, ensure_ascii=True).encode("utf-8")
        header = f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii")
        sys.stdout.buffer.write(header)
        sys.stdout.buffer.write(payload)
        sys.stdout.buffer.flush()


def main() -> None:
    transport = StdioMcpTransport(server=BldrdojoMcpServer())
    transport.run()


if __name__ == "__main__":
    main()
