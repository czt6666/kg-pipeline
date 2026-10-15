from __future__ import annotations

import json
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler


@dataclass
class ApiResult:
    status: int
    body: object


def to_json_bytes(body) -> bytes:
    return json.dumps(body, ensure_ascii=False).encode("utf-8")


class JsonHandler(BaseHTTPRequestHandler):
    def send_bytes(self, code: int, body: bytes, ctype: str = "application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_api(self, result: ApiResult):
        self.send_bytes(result.status, to_json_bytes(result.body))

    def start_event_stream(self):
        """Begin a text/event-stream response. No Content-Length: the body ends when the
        connection closes (BaseHTTPRequestHandler speaks HTTP/1.0 and closes after each
        response). X-Accel-Buffering stops nginx from buffering events until the end."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def send_event(self, event: str, data) -> None:
        self.wfile.write(f"event: {event}\ndata: ".encode("utf-8") + to_json_bytes(data) + b"\n\n")
        self.wfile.flush()

    def send_heartbeat(self) -> None:
        # An SSE comment line: ignored by clients, but it keeps bytes flowing so proxies
        # (nginx's 60s proxy_read_timeout) don't drop a connection that is just slow.
        self.wfile.write(b": ping\n\n")
        self.wfile.flush()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format, *args):
        return
